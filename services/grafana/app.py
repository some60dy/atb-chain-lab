"""Step 6b - Grafana (grafana.atbmarket.com) with reused creds + DB write.

Reused ATB creds log the attacker in. Grafana's Zabbix datasource then writes a
forged admin session straight into the Zabbix DB (simulated via an internal
HTTP call to the Zabbix service).
"""
import os

import requests
from flask import Flask, request, jsonify
import atblog

app = Flask(__name__)

ZABBIX_URL = os.environ.get("ZABBIX_URL", "http://zabbix")

# Reused ATB credentials (same password as other ATB systems).
REUSED_USER = "education@atbmarket.com"
REUSED_PASS = "Edu003868$"


@app.post("/login")
def login():
    ip = atblog.client_ip(request)
    data = request.get_json(silent=True) or request.form
    user = data.get("user") or data.get("username") or ""
    password = data.get("password") or ""
    if user == REUSED_USER and password == REUSED_PASS:
        atblog.log("grafana.login_reused_creds", ip, user=user)
        return jsonify(ok=True, message="Logged in")
    atblog.log("grafana.login_fail", ip, user=user)
    return jsonify(ok=False), 401


@app.post("/api/zabbix/forge")
def zabbix_forge():
    ip = atblog.client_ip(request)
    body = request.get_json(silent=True) or {}
    sessionid = body.get("sessionid", "")
    userid = body.get("userid", 0)
    secret = body.get("secret", "")
    payload = {"sessionid": sessionid, "userid": userid, "secret": secret}

    atblog.log("grafana.zabbix_db_write", ip, sessionid=sessionid, userid=userid,
               msg="forged admin session written into Zabbix DB via Grafana datasource")

    try:
        resp = requests.post(
            f"{ZABBIX_URL}/_internal/insert_session", json=payload, timeout=10,
        )
        try:
            return jsonify(resp.json())
        except Exception:
            return jsonify(ok=True)
    except Exception as exc:
        atblog.log("grafana.zabbix_unreachable", ip, error=str(exc))
        return jsonify(ok=True)


@app.get("/")
def index():
    return "<html><body><h1>Grafana</h1></body></html>"


@app.get("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80)
