[![OpenFiber](https://www.openfiber.net/wp-content/uploads/2018/08/OpenFiber_GraphicAssets_PrimaryLockup_Horizontal_Small.png)](https://openfiber.net)

# Ansible-Netbox-Inventory



[Ansible](https://www.ansible.com/) dynamic inventory for [NetBox](https://github.com/digitalocean/netbox). This tool assumes a stock NetBox install, where possible custom fields are exposed. The intention is provide a good starting ground for utilizing Ansible with NetBox data for generating configuration files and related tasks.

---

## Install
    pip install -r requirements.txt

Create a read only token by logging into the NetBox admin -> Users -> Tokens

Create a `netbox.yml` (see `netbox.yml-dist` as an example) and adjust the following:

* the hostname of your netbox instance
* your token
* the domain name you want to use to generate PTR records (optional)
* set debug: true if you want to see what URLs are getting requested (optional)

Place the `netbox.py` and `netbox.yml` file in your ansible repository under the `/inventory/` directory.

## Usage
You can manually run the plugin to verify if it's working by running:

    ./inventory/netbox.py --list

This generates the full inventory and caches it on `/tmp/ansible_nb_<username>.json`. By default it caches for 3 hours.

You can override the cache by running:

    ./inventory/netbox.py --flushcache
    
Ansible by default will source the `inventory/` directory, otherwise this can be explicitly set with: 

    ansible-playbook -i cust_inventory_dir/ playbook.yml
    
## Example output
Note: Sample output is shortened for brevity. Device Types are dumped as groups, each device's interfaces are available as host variables. An `ungrouped` group exists with DNS entires for all defined interfaces and VLAN's.
```
{
   "border-routers": {
      "hosts": [
         "gw-sfo01",
         "gw-oak02"
      ]
   }, 
   "vm-servers": {
      "hosts": [
         "zerocool"
      ]
   },    
   "_meta": {
      "hostvars": {
         "gw-sfo01": {
            "community": null, 
            "interfaces": {
               "ae0": {
                  "description": "", 
                  "id": 31, 
                  "interface_mode": "Tagged", 
                  "type": "Interface", 
                  "v4_address": [], 
                  "v6_address": [], 
                  "vlans": [
                     100,  
                     200
                  ]
               }, 
               ...
               "ge-0/0/9": {
                  "description": "Customer #ABC", 
                  "id": 10, 
                  "interface_mode": "Access", 
                  "type": "Interface", 
                  "v4_address": [], 
                  "v6_address": [], 
                  "vlans": [
                     100
                  ]
               }, 
               "vlan.200": {
                  "description": "", 
                  "id": 32, 
                  "interface_mode": "Untagged", 
                  "type": "Interface", 
                  "v4_address": [
                     "203.0.113.19/24"
                  ], 
                  "v6_address": [], 
                  "vlans": []
               },
               "xe-0/1/2": {
                  "bond": "ae0", 
                  "description": "", 
                  "id": 29, 
                  "interface_mode": "Untagged", 
                  "type": "Bond", 
                  "v4_address": [], 
                  "v6_address": [], 
                  "vlans": []
               }, 
            }, 
            "latitude": null, 
            "longitude": null, 
            "manufacturer": "juniper", 
            "model": "mx10003", 
            "serial": "BH0210xxx", 
            "site": "sfo", 
            "siteid": 3, 
            "status": null
         }, 
...         
         "zerocool": {
            "community": null, 
            "interfaces": {
               "eth0": {
                  "description": "", 
                  "id": 25, 
                  "interface_mode": "Untagged", 
                  "mtu": 1500, 
                  "type": "Interface", 
                  "v4_address": [
                     "203.0.113.20/24"
                  ], 
                  "v6_address": [], 
                  "vlans": []
               }
            }, 
            "latitude": null, 
            "longitude": null, 
            "manufacturer": "supermicro", 
            "model": "6016t-mt", 
            "serial": "", 
            "site": "oak", 
            "siteid": 3, 
            "status": null
         }, 
...
   }, 
   "ungrouped": {
      "vars": {
         "dns_entries": [
            {
               "domain": "226.45.94.in-addr.arpa", 
               "record_name": "19", 
               "record_type": "PTR", 
               "record_value": "eth0.zerocool.domain.net"
            }, 
            {
               "domain": "domain.net", 
               "record_name": "eth0.zerocool.domain.net", 
               "record_type": "A", 
               "record_value": "203.0.113.20"
            }, 
...
         ], 
         "vlans": {
            "100": {
               "name": "CUSTOMERSEASTBAY", 
               "slug": "Customers - East Bay"
            }, 
            "200": {
               "name": "PEERINGNORTHBAY", 
               "slug": "Peering - North Bay"
            }
...
```
