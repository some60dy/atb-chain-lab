"""One-shot provisioning of the real Zabbix 6.0 (zb-app-p01) through its API.

Creates the ATB estate (host groups, monitored hosts, a few users), logs into the
web frontend once so it generates config.session_key, then replaces the default
Admin password with a random one nobody knows. Idempotent: if Admin/zabbix no
longer works, the instance is already provisioned and we exit.
"""
import os
import secrets
import string
import sys
import time

import requests

WEB = os.environ.get("ZBX_WEB", "http://zabbix-web:8080")
API = WEB + "/api_jsonrpc.php"


def rpc(method, params, auth=None):
    body = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    if auth:
        body["auth"] = auth
    r = requests.post(API, json=body, timeout=30).json()
    if "error" in r:
        raise RuntimeError(f"{method}: {r['error']}")
    return r["result"]


def wait_api():
    for _ in range(120):
        try:
            print("zabbix api", rpc("apiinfo.version", {}), flush=True)
            return
        except Exception:
            time.sleep(5)
    sys.exit("zabbix api never came up")


def randpw(n=28):
    alphabet = string.ascii_letters + string.digits + "!#%+-_"
    return "".join(secrets.choice(alphabet) for _ in range(n))


GROUPS = ["ATB/Prod/Web", "ATB/Prod/DB", "ATB/Infra", "ATB/CI", "ATB/Backup",
          "ATB/Stores", "ATB/Mail", "ATB/Monitoring"]

# (host, visible name, group, dns, templates)
HOSTS = [
    ("sp-web-p01", "Supplier portal (SuiteCRM)", "ATB/Prod/Web", "sp-web-p01", ["Linux by Zabbix agent"]),
    ("www-p01", "E-shop www.atbmarket.com", "ATB/Prod/Web", "www.atbmarket.com", ["Linux by Zabbix agent"]),
    ("mobapp-p01", "Mobile API mobapp.atbmarket.com", "ATB/Prod/Web", "mobapp.atbmarket.com", ["Linux by Zabbix agent"]),
    ("edu-p01", "LMS education.atbmarket.com", "ATB/Prod/Web", "education.atbmarket.com", ["Linux by Zabbix agent"]),
    ("db-ishop-p01", "MySQL ishop", "ATB/Prod/DB", "db-ishop-p01", ["Linux by Zabbix agent"]),
    ("supplier-db", "MySQL supplier portal", "ATB/Prod/DB", "supplier-db.atbmarket.com", ["Linux by Zabbix agent"]),
    ("pgsql-dev-storeplus", "PostgreSQL store-plus (dev)", "ATB/Prod/DB", "pgsql-dev.store-plus.atbmarket.com", ["Linux by Zabbix agent"]),
    ("erpdb", "Oracle EBS PROD", "ATB/Prod/DB", "erpdb", ["ICMP Ping"]),
    ("retaildb", "Oracle RMS retekdb", "ATB/Prod/DB", "retaildb", ["ICMP Ping"]),
    ("ISMEDOC-DB", "Oracle M.E.Doc", "ATB/Prod/DB", "ISMEDOC-DB", ["ICMP Ping"]),
    ("jenkins.atbmarket.com", "CI / Jenkins", "ATB/CI", "jenkins.atbmarket.com", ["Linux by Zabbix agent"]),
    ("sh-harb-p01", "Harbor registry", "ATB/CI", "harbor.atbmarket.com", ["Linux by Zabbix agent"]),
    ("gitlab-p01", "GitLab", "ATB/CI", "gitlab-p01", ["Linux by Zabbix agent"]),
    ("bastion-main-p01", "Bastion (jump host)", "ATB/Infra", "bastion-main-p01", ["Linux by Zabbix agent"]),
    ("DC-MAIN-01", "Domain controller", "ATB/Infra", "DC-MAIN-01.atbmarket.com", ["ICMP Ping"]),
    ("squid-proxy", "Egress proxy", "ATB/Infra", "squid-proxy", ["Linux by Zabbix agent"]),
    ("bkp-atman", "Backup (CIFS //bkp-atman/BACKUP)", "ATB/Backup", "bkp-atman", ["ICMP Ping"]),
    ("ex.atbmarket.com", "Exchange / OWA", "ATB/Mail", "ex.atbmarket.com", ["ICMP Ping"]),
    ("grafana.atbmarket.com", "Grafana", "ATB/Monitoring", "grafana.atbmarket.com", ["Linux by Zabbix agent"]),
] + [
    (f"store-{city}-{n:03d}", f"Store {city.title()} #{n}", "ATB/Stores",
     f"store-{city}-{n:03d}.atbmarket.com", ["ICMP Ping"])
    for city, n in [("kyiv", 1), ("kyiv", 2), ("dnipro", 1), ("lviv", 1), ("kharkiv", 1), ("odesa", 1)]
]


def main():
    wait_api()
    try:
        tok = rpc("user.login", {"username": "Admin", "password": "zabbix"})
    except RuntimeError:
        print("already provisioned", flush=True)
        return

    # one browser login so the frontend generates config.session_key
    s = requests.Session()
    s.get(WEB + "/index.php", timeout=30)
    s.post(WEB + "/index.php", data={"name": "Admin", "password": "zabbix",
                                     "autologin": "1", "enter": "Sign in"}, timeout=30)

    gids = {}
    for g in GROUPS:
        found = rpc("hostgroup.get", {"filter": {"name": [g]}}, tok)
        gids[g] = found[0]["groupid"] if found else rpc("hostgroup.create", {"name": g}, tok)["groupids"][0]

    tpl_names = sorted({t for h in HOSTS for t in h[4]})
    tids = {t["host"]: t["templateid"]
            for t in rpc("template.get", {"filter": {"host": tpl_names}, "output": ["templateid", "host"]}, tok)}

    for host, name, group, dns, tpls in HOSTS:
        if rpc("host.get", {"filter": {"host": [host]}}, tok):
            continue
        rpc("host.create", {
            "host": host, "name": name,
            "groups": [{"groupid": gids[group]}],
            "interfaces": [{"type": 1, "main": 1, "useip": 0, "ip": "", "dns": dns, "port": "10050"}],
            "templates": [{"templateid": tids[t]} for t in tpls if t in tids],
            "inventory_mode": 0,
        }, tok)

    # ops added a check on the CIFS backup share that jenkins mounts
    jh = rpc("host.get", {"filter": {"host": ["jenkins.atbmarket.com"]},
                          "selectInterfaces": ["interfaceid"]}, tok)[0]
    key = "system.run[df -h /mnt/BACKUP | tail -1]"
    if not rpc("item.get", {"hostids": jh["hostid"], "filter": {"key_": key}}, tok):
      rpc("item.create", {
        "hostid": jh["hostid"], "interfaceid": jh["interfaces"][0]["interfaceid"],
        "name": "Backup share //bkp-atman/BACKUP: usage",
        "key_": key,
        "type": 0, "value_type": 4, "delay": "10m",
        "description": "nightly root/home tarballs from linux hosts land on //bkp-atman/BACKUP (mounted on jenkins)",
    }, tok)

    # a few real-looking accounts with passwords nobody will ever learn
    usrgrps = {g["name"]: g["usrgrpid"] for g in rpc("usergroup.get", {"output": ["usrgrpid", "name"]}, tok)}
    roles = {r["name"]: r["roleid"] for r in rpc("role.get", {"output": ["roleid", "name"]}, tok)}
    for alias, first, last, role in [("o.kravets", "Oleh", "Kravets", "Admin role"),
                                     ("noc", "NOC", "Duty", "User role"),
                                     ("svc.reports", "Reports", "Service", "User role")]:
        if rpc("user.get", {"filter": {"username": [alias]}}, tok):
            continue
        rpc("user.create", {"username": alias, "name": first, "surname": last,
                            "passwd": randpw(), "roleid": roles[role],
                            "usrgrps": [{"usrgrpid": usrgrps["Zabbix administrators"]}]}, tok)

    admin = rpc("user.get", {"filter": {"username": ["Admin"]}}, tok)[0]
    rpc("user.update", {"userid": admin["userid"], "passwd": randpw()}, tok)
    print("provisioned: %d hosts; Admin password rotated" % len(HOSTS), flush=True)


if __name__ == "__main__":
    main()
