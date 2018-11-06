# Ansible-Netbox-Inventory

Place the netbox.py and netbox.yml file in your ansible repository under the /inventory/ directory.

Create a read only token by logging into the netbox admin -> Users -> Tokens

Edit netbox.yml and change:

* the domain name of your netbox instance
* your token
* the domain name you want to use to generate PTR records (optional)
* set debug: true if you want to see what URLs are getting requested (optional)

# Usage

    pip install -r requirements.txt

You can manually run the plugin to verify if it's working by running:

    ./inventory/netbox.py --list

This generates the full inventory and caches it on /tmp/ansible_nb_<username>.json. By default it caches for 3 hours.

You can override the cache by running:

    ./inventory/netbox.py --flushcache
