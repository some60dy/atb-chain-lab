"""Step 6c - Zabbix 6.0 (zb-app-p01) with forged-session auth bypass + RCE.

A forged admin session is written into the Zabbix DB (by Grafana's datasource),
then a HMAC-signed `zbx_session` cookie unlocks the JSON-RPC API. The
`script.create` method runs arbitrary commands as root (uid=0).
"""
import base64
import hashlib
import hmac
import json
import subprocess

from flask import Flask, request, jsonify
import atblog

app = Flask(__name__)

# Zabbix frontend session signing key (recovered from zabbix.conf.php).
SESSION_KEY = "713a5c3bc0688c7106abfdd90bfcd0d1"

# In-memory session store: sessionid -> {"userid","secret","status"}.
SESSIONS = {}


def _expected_sign(sessionid):
    return hmac.new(
        SESSION_KEY.encode("utf-8"),
        sessionid.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _verify_cookie(cookie_val):
    """Decode base64->json {"sessionid","sign"}, verify HMAC + live session.

    Returns the sessionid on success, else None.
    """
    try:
        raw = base64.b64decode(cookie_val).decode("utf-8", "replace")
        obj = json.loads(raw)
        sessionid = obj.get("sessionid", "")
        sign = obj.get("sign", "")
    except Exception:
        return None
    if not sessionid or not sign:
        return None
    if not hmac.compare_digest(sign, _expected_sign(sessionid)):
        return None
    sess = SESSIONS.get(sessionid)
    if not sess or sess.get("status") != 0:
        return None
    return sessionid


@app.post("/_internal/insert_session")
def insert_session():
    ip = atblog.client_ip(request)
    body = request.get_json(silent=True) or {}
    sessionid = body.get("sessionid", "")
    userid = body.get("userid", 0)
    secret = body.get("secret", "")
    SESSIONS[sessionid] = {"userid": userid, "secret": secret, "status": 0}
    atblog.log("zabbix.session_inserted", ip, sessionid=sessionid, userid=userid)
    return jsonify(ok=True)


@app.post("/api_jsonrpc.php")
def api_jsonrpc():
    ip = atblog.client_ip(request)
    body = request.get_json(silent=True) or {}
    rpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {}) or {}

    cookie_val = request.cookies.get("zbx_session", "")
    sessionid = _verify_cookie(cookie_val)
    if not sessionid:
        atblog.log("zabbix.auth_fail", ip, method=method)
        return jsonify({
            "jsonrpc": "2.0",
            "error": {"code": -32602, "message": "Not authorised"},
            "id": rpc_id,
        })

    atblog.log("zabbix.forged_session_accepted", ip, sessionid=sessionid)

    if method == "script.create":
        command = params.get("command", "")
        proc = subprocess.run(
            ["/bin/sh", "-c", command],
            capture_output=True, text=True, timeout=15,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        atblog.log("zabbix.script_create_rce", ip, command=command,
                   output=output[:300],
                   msg="remote command executed as root via Zabbix script.create")
        return jsonify({
            "jsonrpc": "2.0",
            "result": {"scriptids": ["1"], "output": output},
            "id": rpc_id,
        })

    return jsonify({"jsonrpc": "2.0", "result": [], "id": rpc_id})


@app.get("/")
def index():
    return "<html><body><h1>Zabbix 6.0</h1></body></html>"


@app.get("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80)
