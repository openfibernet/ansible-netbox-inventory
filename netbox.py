#!/usr/bin/env python

from pprint import pprint
import os, yaml, json, sys, argparse, logging, re, datetime

try:
    import pynetbox
    from netaddr import *
except ImportError, e:
    sys.exit("Please install required python modules: pynetbox netaddr")

class NetboxInventory:
    def __init__(self):
        self.config = self.load_config()

        if self.config['debug']:
            logging.basicConfig(filename='netbox_inventory.log', level=logging.DEBUG)

        self.netbox = self.connect_netbox(self.config['url'], self.config['token'])
        self.result = {
            "all": {
                "hosts": []
            },
            "_meta": {
                "hostvars": {}
            },
            "ungrouped": {
                "vars": {
                    "dns_entries": [],
                    "vlans": {}
                }
            }
        }

    def load_config(self):
        with open(os.path.join(os.path.dirname(__file__), "netbox.yml"), 'r') as stream:
            try:
                return yaml.load(stream)
            except yaml.YAMLError as exc:
                print(exc)

    def connect_netbox(self, url, token):
        try:
            return pynetbox.api(url, token=token)
        except requests.exceptions.ConnectionError:
            sys.exit("Failed to connect to netbox instance")
        except AttributeError:
            sys.exit("Failed to connect to netbox instance")

    def lookup_ip_for_interfaces(self, interfaces, device):
        ips = self.netbox.ipam.ip_addresses.filter(device=device)
        for ip in ips:
            if ip.family == 4:
                interfaces[ip.interface.name]['v4_address'].append(str(ip.address))
                self.create_dns_records_v4(ip.interface.name, device, str(ip.address))
            elif ip.family == 6:
                interfaces[ip.interface.name]['v6_address'].append(str(ip.address))
                self.create_dns_records_v6(ip.interface.name, device, str(ip.address))

        return interfaces

    def sanitize_dns_name(self, name):
        return re.sub("[^a-z\d-]+", "-", name.lower())

    def create_dns_record(self, domain, record_name, record_type, value):
        return {
           "domain": domain,
           "record_name": record_name,
           "record_type": record_type,
           "record_value": value
        }

    def create_dns_records_v4(self, interface, device, ip):
        ip = str(IPNetwork(ip).ip)
        pre = ip.split(".")
        record_name = pre.pop()
        domain = ".".join(pre[::-1] + ['in-addr', 'arpa'])
        intf = self.sanitize_dns_name(interface)

        self.result['ungrouped']['vars']['dns_entries'].append(
            self.create_dns_record(domain, record_name, "PTR", ".".join([intf, device.name, self.config['dns_name']]))
        )
        self.result['ungrouped']['vars']['dns_entries'].append(
            self.create_dns_record(self.config['dns_name'], ".".join([intf, device.name, self.config['dns_name']]), "A", ip)
        )

    def create_dns_records_v6(self, interface, device, ip):
        ip = str(IPNetwork(ip).ip)
        pre = ip.split(".")
        record_name = pre.pop()
        domain = ".".join(pre[::-1] + ['in-addr', 'arpa'])
        intf = self.sanitize_dns_name(interface)

        self.result['ungrouped']['vars']['dns_entries'].append(
            self.create_dns_record(self.config['dns_name'], ".".join([intf, device.name, self.config['dns_name']]), "AAAA", ip)
        )
        self.result['ungrouped']['vars']['dns_entries'].append(
            self.create_dns_record(self.config['ipv6_ptr_domain'], IPAddress(ip).reverse_dns, "PTR", ".".join([intf, device.name, self.config['dns_name']]))
        )

    def lookup_circuits(self, circuit_id, interface_id, mtu_size, interface_mode, vlans = {}):
        circuit = self.netbox.circuits.circuits.get(circuit_id)

        if circuit.tenant != None:
            tenant = circuit.tenant.name
            tenant_desc = circuit.tenant.description
        else:
            tenant = "default"
            tenant_desc = ""

        description = "%s: %s [%s] {%s} (%s)" % (circuit.type.name.upper(), tenant, circuit.provider.name, circuit.cid, tenant_desc)

        c = self.return_interface(description, circuit.type.name, interface_id, mtu_size, interface_mode, vlans)

        c['cid'] = circuit.cid
        c['circuit_description'] = circuit.description
        c['provider'] = circuit.provider.name
        if circuit.type.name == "Peering":
            c['exchange'] = circuit.provider.name
        return c

    def clean_interface_mode(self, mode):
        if mode == None:
            return 'Untagged'
        return mode.label

    def create_slug(self, text):
        slug = re.sub("[^A-Z\d-]*", "", text.upper())
        return slug if len(slug) <= 32 else slug[0:32]

    def save_vlan_global(self, vlan_id, vlan_name):
        if vlan_id not in self.result['ungrouped']['vars']['vlans']:
            self.result['ungrouped']['vars']['vlans'][vlan_id] = {
                "name": vlan_name,
                "slug": self.create_slug(vlan_name)
            }

    def return_vlans(self, interface):
        r = []

        if self.clean_interface_mode(interface.mode) == 'Access' and interface.untagged_vlan != None:
            self.save_vlan_global(interface.untagged_vlan.vid, interface.untagged_vlan.name)
            r.append(int(interface.untagged_vlan.vid))
        else:
            for v in interface.tagged_vlans:
                self.save_vlan_global(v['vid'], v['name'])
                r.append(int(v['vid']))

        return r

    def get_interfaces(self, device):
        interfaces = {}
        intf = self.netbox.dcim.interfaces.filter(device=device)
        for i in intf:
            if i.circuit_termination is not None:
                interfaces[i.name] = self.lookup_circuits(i.circuit_termination.circuit.id, i.id, i.mtu, self.clean_interface_mode(i.mode), self.return_vlans(i))
            elif i.lag is not None:
                interfaces[i.name] = self.return_interface(i.description, 'Bond', i.id, i.mtu, self.clean_interface_mode(i.mode), self.return_vlans(i))
                interfaces[i.name]['bond'] = i.lag.name
            else:
                interfaces[i.name] = self.return_interface(i.description, 'Interface', i.id, i.mtu, self.clean_interface_mode(i.mode), self.return_vlans(i))

        return self.lookup_ip_for_interfaces(interfaces, device)

    def return_interface(self, description, int_type, id, mtu='', interface_mode='Untagged', vlans=[]):
        intf = { 'description': description, 'type': int_type, 'id': id, 'interface_mode': interface_mode, 'vlans': vlans, 'v4_address': [], 'v6_address': [] }

        if mtu != None:
            intf['mtu'] = mtu

        return intf

    def create_group_entry(self, group, hostname):
        if group not in self.result:
            self.result[group] = {}
            self.result[group]["hosts"] = []

        self.result[group]["hosts"].append(hostname)

    def fetch_netbox_devices(self):
        for host in self.netbox.dcim.devices.filter(status=1):
            if host.name == None:
                continue

            h = host.name
            self.result["all"]["hosts"].append(h)

            # Create hostgroups by device_role, device_type and site
            self.create_group_entry(host.device_role.slug, h)
            self.create_group_entry(host.device_type.slug, h)
            self.create_group_entry(host.site.slug, h)

            if not host in self.result["_meta"]["hostvars"]:
                self.result["_meta"]["hostvars"][h] = { "interfaces": {}}

            if host.virtual_chassis != None:
                self.result["_meta"]["hostvars"][h]['virtual_chassis'] = []
                vc_members = self.netbox.dcim.devices.filter(virtual_chassis_id=host.virtual_chassis.id)
                for vcm in vc_members:
                    if vcm.vc_position == 0 or vcm.vc_position == 1:
                        role = 'routing-engine'
                    else:
                        role = 'line-card'

                    self.result["_meta"]["hostvars"][h]['virtual_chassis'].append({ 'serial': vcm.serial, 'role': role, 'device_name': vcm.name, 'vc_position': vcm.vc_position })

            if host.custom_fields != None:
                for k,v in host.custom_fields.items():
                    self.result["_meta"]["hostvars"][h][k] = v

            self.result["_meta"]["hostvars"][h]['site'] = host.site.slug
            self.result["_meta"]["hostvars"][h]['serial'] = host.serial
            self.result["_meta"]["hostvars"][h]['siteid'] = host.site.id
            self.result["_meta"]["hostvars"][h]['model'] = host.device_type.slug
            self.result["_meta"]["hostvars"][h]['manufacturer'] = host.device_type.manufacturer.slug

            # Lookup site details
            site = self.netbox.dcim.sites.filter(slug=host.site.slug)
            if len(site) > 0:
                self.result["_meta"]["hostvars"][h]['latitude'] = site[0].latitude
                self.result["_meta"]["hostvars"][h]['longitude'] = site[0].longitude

            self.result["_meta"]["hostvars"][h]["interfaces"] = self.get_interfaces(host)
            if host.primary_ip != None:
                self.result["_meta"]["hostvars"][h]['ansible_ssh_host'] = str(host.primary_ip.address.ip)

        return self.result

    def fetch_virtual_machines(self):
        for host in self.netbox.virtualization.virtual_machines.filter(status=1):
            self.result["all"]["hosts"].append(host.name)

            # Create hostgroups by cluster, role
            if host.cluster is not None:
                self.create_group_entry(host.cluster.name, host.name)
            if host.role is not None:
                self.create_group_entry(host.role.slug, host.name)

            if not host in self.result["_meta"]["hostvars"]:
                self.result["_meta"]["hostvars"][host.name] = {}

            if host.primary_ip != None:
                self.result["_meta"]["hostvars"][host.name]['ansible_ssh_host'] = str(IPNetwork(host.primary_ip.address).ip)

        return self.result

class OFNetboxInventory(NetboxInventory):
    def __init__(self):
        NetboxInventory.__init__(self)

    def get_interfaces(self, device):
        interfaces = {}
        intf = self.netbox.dcim.interfaces.filter(device=device)
        for i in intf:
            if i.form_factor.label == 'Link Aggregation Group (LAG)':
                interfaces[i.name] = self.return_interface(i.description, 'Backbone', i.id, i.mtu, self.clean_interface_mode(i.mode), self.return_vlans(i))
            elif i.mgmt_only:
                interfaces[i.name] = self.return_interface('OOB - Management', 'Management', i.id, i.mtu)
            elif i.interface_connection is not None:
                description = "CORE: %s %s" % (i.interface_connection.interface.device.name, i.interface_connection.interface.name)
                if i.lag is not None:
                    interfaces[i.name] = self.return_interface(description, 'Bond', i.id, i.mtu, self.clean_interface_mode(i.mode), self.return_vlans(i))
                    interfaces[i.name]['bond'] = i.lag.name
                else:
                    interfaces[i.name] = self.return_interface(description, 'Backbone', i.id, i.mtu, self.clean_interface_mode(i.mode), self.return_vlans(i))
            elif i.circuit_termination is not None:
                interfaces[i.name] = self.lookup_circuits(i.circuit_termination.circuit.id, i.id, i.mtu, self.clean_interface_mode(i.mode), self.return_vlans(i))
            elif i.form_factor.label == 'Virtual' and i.name.startswith('lo0'):
                interfaces[i.name] = self.return_interface(i.description, 'Loopback', i.id, i.mtu)
            elif i.form_factor.label == 'Virtual' and (i.name.startswith('lt-') or i.name.startswith('rlt')):
                interfaces[i.name] = self.return_interface(i.description, 'LogicalTunnel', i.id, i.mtu)
            elif i.form_factor.label == 'Virtual' and i.name.startswith('ps'):
                interfaces[i.name] = self.return_interface(i.description, 'LogicalTunnel', i.id, i.mtu, self.clean_interface_mode(i.mode), self.return_vlans(i))
            elif i.untagged_vlan is not None:
                interfaces[i.name] = self.return_interface(i.description, 'Untagged', i.id, i.mtu, self.clean_interface_mode(i.mode), self.return_vlans(i))
            elif i.mode != None and i.mode.label == 'Tagged All':
                interfaces[i.name] = self.return_interface(i.description, 'TaggedAll', i.id, i.mtu, self.clean_interface_mode(i.mode), self.return_vlans(i))
            elif len(i.tagged_vlans) > 0:
                interfaces[i.name] = self.return_interface(i.description, 'Tagged', i.id, i.mtu, self.clean_interface_mode(i.mode), self.return_vlans(i))

        return self.lookup_ip_for_interfaces(interfaces, device)

    def return_vlans(self, interface):
        v = { 'inner': [], 'outer': '' }

        if self.clean_interface_mode(interface.mode) == 'Access' and interface.untagged_vlan != None:
            v['inner'].append(int(interface.untagged_vlan.vid))
            return v
        else:
            vlans = interface.tagged_vlans

        if len(vlans) == 0 and self.clean_interface_mode(interface.mode) != 'Untagged':
            logging.debug("Unexpected vlan configuration for interface with id %s" % interface.id)
        if len(vlans) > 0:
            for l in vlans:
                if l['vid'] not in v['inner']:
                    v['inner'].append(l['vid'])
                if 'group' in l and l['group'] != None:
                    v['outer'] = l['group']['outervid']

        return v


def modification_date(filename):
    t = os.path.getmtime(filename)
    return datetime.datetime.fromtimestamp(t)

def cache_inventory(cache_file):
    n = NetboxInventory()
    n.fetch_virtual_machines()
    hosts = n.fetch_netbox_devices()

    cache = json.dumps(hosts, sort_keys=True, indent=3)
    with open(cache_file, 'w') as f:
        f.write(cache)

    print(cache)

def load_cache(cache_file):
    with open(cache_file) as json_data:
        print(json.dumps(json.load(json_data), sort_keys=True, indent=3))

if __name__ == "__main__":
    cache_file = '/tmp/ansible_nb_%s.json' % (os.getlogin())

    parser = argparse.ArgumentParser(add_help=True, description='A simple dynamic inventory for Ansible from Netbox')
    parser.add_argument('--list', action='store_true', default=False, dest='inventory_mode', help='Print JSON output')
    parser.add_argument('--flushcache', action='store_true', default=False, dest='flush_cache', help='Overwrite cache file')

    if parser.parse_args().flush_cache:
        cache_inventory(cache_file)
    elif parser.parse_args().inventory_mode:
        if os.path.isfile(cache_file):
            mtime = modification_date(cache_file)
            to_date = datetime.datetime.now() - datetime.timedelta(hours=3)
            if mtime >= to_date:
                load_cache(cache_file)
                exit(0)

        cache_inventory(cache_file)
    else:
        parser.print_help()
