"""Step 6b - zb-app-p01 Zabbix 6.0 frontend (internal, no host port).

Auth is a signed `zbx_session` cookie: base64(JSON{"sessionid","sign"}) where
    sign = HMAC-SHA256(session_key, compact-JSON-of-the-cookie-without-"sign")
and `session_key` lives in the Zabbix DB `config` table. A forged admin session
row (INSERTed via Grafana's over-privileged data source, step 6a) plus a matching
signed cookie unlock the UI as Admin. Administration → Scripts lets Admin create
a script and run it on a host — the Zabbix server executes it as **root**.

Browser-clickable: set the forged cookie, then navigate Hosts → run script.
Also exposes /api_jsonrpc.php so the reference solver can drive it headless.
"""
import base64
import hashlib
import hmac
import json
import os
import subprocess

import pymysql
from flask import Flask, request, Response, redirect
import atblog

app = Flask(__name__)

DB = {
    "host": os.environ.get("ZABBIX_DB_HOST", "zabbix-db"),
    "db": os.environ.get("ZABBIX_DB_NAME", "zabbix"),
    "user": os.environ.get("ZABBIX_DB_USER", "grafana"),
    "password": os.environ.get("ZABBIX_DB_PASS", "Gr4f4na_DS_ro"),
}

# scripts created through the UI/API this process-lifetime: name -> command
SCRIPTS = {}


def _db():
    return pymysql.connect(host=DB["host"], user=DB["user"], password=DB["password"],
                           database=DB["db"], connect_timeout=8, autocommit=True,
                           cursorclass=pymysql.cursors.DictCursor)


def _session_key():
    try:
        with _db() as conn, conn.cursor() as cur:
            cur.execute("SELECT session_key FROM config LIMIT 1")
            row = cur.fetchone()
            return (row or {}).get("session_key", "")
    except Exception:
        return ""


def _expected_sign(key, signed_json):
    return hmac.new(key.encode(), signed_json.encode(), hashlib.sha256).hexdigest()


def _valid_session(sessionid):
    """True if `sessionid` is an active session for a Super-admin (roleid 3)."""
    try:
        with _db() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT s.userid, s.status, u.roleid FROM sessions s "
                "JOIN users u ON u.userid = s.userid WHERE s.sessionid=%s",
                (sessionid,))
            row = cur.fetchone()
    except Exception:
        return None
    if not row or row["status"] != 0 or row["roleid"] != 3:
        return None
    return row["userid"]


def _auth():
    """Verify the zbx_session cookie end-to-end; return userid or None."""
    cookie = request.cookies.get("zbx_session", "")
    if not cookie:
        return None
    try:
        obj = json.loads(base64.b64decode(cookie).decode("utf-8", "replace"))
        sessionid = obj.get("sessionid", "")
        sign = obj.get("sign", "")
    except Exception:
        return None
    if not sessionid or not sign:
        return None
    signed = {k: v for k, v in obj.items() if k != "sign"}
    signed_json = json.dumps(signed, separators=(",", ":"))
    key = _session_key()
    if not key or not hmac.compare_digest(sign, _expected_sign(key, signed_json)):
        return None
    return _valid_session(sessionid)


def _run_as_root(command):
    proc = subprocess.run(["/bin/sh", "-c", command], capture_output=True,
                          text=True, timeout=15)
    return (proc.stdout or "") + (proc.stderr or "")


# ------------------------------------------------------------------ styling
_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Open Sans',Arial,sans-serif;background:#0e1013;color:#f2f2f2}
a{color:#4796e4;text-decoration:none}
.top{background:#121417;border-bottom:2px solid #d31f26;padding:10px 18px;
     display:flex;align-items:center;gap:18px}
.brand{font-weight:800;color:#d31f26;font-size:18px}
.top a{color:#c9ccd1;font-size:14px}.top a:hover{color:#fff}
.wrap{max-width:960px;margin:0 auto;padding:22px 18px}
h1{font-size:19px;margin-bottom:12px}
.muted{color:#8b9097;font-size:13px}
.card{background:#16191d;border:1px solid #262b31;border-radius:5px;padding:18px;margin-top:16px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{border-bottom:1px solid #262b31;padding:9px 10px;text-align:left}
th{color:#8b9097;font-weight:600;font-size:12px;text-transform:uppercase}
label{display:block;font-size:12px;text-transform:uppercase;color:#8b9097;margin:12px 0 5px}
input,select{width:100%;background:#0e1013;border:1px solid #2b3139;border-radius:3px;
     color:#f2f2f2;padding:9px 11px;font-size:14px}
.btn{margin-top:14px;background:#d31f26;color:#fff;border:none;border-radius:3px;
     padding:9px 16px;font-weight:600;cursor:pointer}.btn:hover{background:#e8343b}
.btn.sm{margin:0;padding:5px 11px;font-size:13px}
pre{background:#05070a;border:1px solid #262b31;border-radius:4px;padding:12px;
    margin-top:12px;overflow:auto;color:#73e67a;font-family:'JetBrains Mono',monospace;font-size:13px}
.deny{max-width:420px;margin:12vh auto 0;text-align:center}
"""


def _page(body):
    nav = ('<a href="/zabbix.php?action=dashboard">Monitoring</a>'
           '<a href="/zabbix.php?action=host.list">Hosts</a>'
           '<a href="/zabbix.php?action=script.list">Administration</a>')
    return Response(f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zabbix</title><style>{_CSS}</style></head><body>
<div class="top"><span class="brand">ZABBIX</span>{nav}
<span style="flex:1"></span><span class="muted">zb-app-p01 · 6.0.18</span></div>
{body}</body></html>""", mimetype="text/html")


def _denied():
    return _page("""<div class="card deny"><h1>Not authorised</h1>
<div class="muted">You are not logged in. The Zabbix frontend requires a valid
<code>zbx_session</code> cookie signed with the frontend session key.</div></div>"""), 401


# ----------------------------------------------------------------- UI routes
@app.get("/")
def index():
    return redirect("/zabbix.php?action=dashboard")


@app.get("/zabbix.php")
def zbx():
    ip = atblog.client_ip(request)
    action = request.args.get("action", "dashboard")
    userid = _auth()
    if not userid:
        atblog.log("zabbix.ui_unauth", ip, action=action)
        return _denied()
    atblog.log("zabbix.forged_session_accepted", ip, action=action, userid=userid)

    if action == "host.list":
        return _host_list()
    if action == "script.list":
        return _script_list()
    return _page(f"""<div class="wrap"><h1>Global view</h1>
<div class="card"><div class="muted">Logged in as userid {userid} (Super admin).</div>
<p style="margin-top:10px">Jump to <a href="/zabbix.php?action=host.list">Hosts</a>
or <a href="/zabbix.php?action=script.list">Administration → Scripts</a>.</p></div></div>""")


def _host_list():
    try:
        with _db() as conn, conn.cursor() as cur:
            cur.execute("SELECT hostid, host, name, agent_ip, agent_port FROM hosts")
            hosts = cur.fetchall()
    except Exception as exc:
        hosts = []
    opts = "".join(f'<option value="{h["host"]}">{h["host"]}</option>' for h in hosts)
    rows = ""
    for h in hosts:
        rows += (f'<tr><td>{h["name"]}</td><td><code>{h["host"]}</code></td>'
                 f'<td>{h["agent_ip"]}:{h["agent_port"]}</td>'
                 f'<td><a class="btn sm" href="/zabbix.php?action=script.list">Scripts…</a></td></tr>')
    scripts = "".join(f'<option value="{n}">{n}</option>' for n in SCRIPTS)
    run_form = (f"""<form method="post" action="/script.exec" style="margin-top:6px">
      <label>Run script on host</label>
      <select name="host">{opts}</select>
      <label>Script</label><select name="script">{scripts}</select>
      <button class="btn" type="submit">Execute now</button></form>"""
                if SCRIPTS else '<div class="muted" style="margin-top:8px">No scripts yet — create one in Administration → Scripts.</div>')
    return _page(f"""<div class="wrap"><h1>Monitoring → Hosts</h1>
<div class="card"><table><tr><th>Name</th><th>Host</th><th>Agent</th><th></th></tr>
{rows}</table></div>
<div class="card">{run_form}</div></div>""")


def _script_list():
    rows = "".join(
        f'<tr><td>{n}</td><td><code>{c}</code></td><td>Script</td>'
        f'<td>Server (root)</td></tr>' for n, c in SCRIPTS.items())
    return _page(f"""<div class="wrap"><h1>Administration → Scripts</h1>
<div class="card"><table><tr><th>Name</th><th>Command</th><th>Type</th><th>Execute on</th></tr>
{rows or '<tr><td colspan=4 class="muted">No scripts defined.</td></tr>'}</table></div>
<div class="card"><h1 style="font-size:16px">Create script</h1>
<form method="post" action="/script.create">
  <label>Name</label><input name="name" value="recon" required>
  <label>Commands</label><input name="command" value="id; hostname" required>
  <label>Execute on</label><select name="execute_on"><option>Zabbix server</option></select>
  <button class="btn" type="submit">Add & run</button>
</form></div></div>""")


@app.post("/script.create")
def script_create_ui():
    ip = atblog.client_ip(request)
    if not _auth():
        return _denied()
    name = request.form.get("name", "script")
    command = request.form.get("command", "")
    SCRIPTS[name] = command
    output = _run_as_root(command)
    atblog.log("zabbix.script_create_rce", ip, script=name, command=command,
               output=output[:300], msg="command executed as root via Zabbix script")
    return _page(f"""<div class="wrap"><h1>Script "{name}" executed</h1>
<div class="card"><div class="muted">Execute on: Zabbix server · ran as the server process (root)</div>
<pre>{output or '(no output)'}</pre>
<a class="btn sm" href="/zabbix.php?action=host.list">← Hosts</a></div></div>""")


@app.post("/script.exec")
def script_exec_ui():
    ip = atblog.client_ip(request)
    if not _auth():
        return _denied()
    name = request.form.get("script", "")
    host = request.form.get("host", "")
    command = SCRIPTS.get(name, "")
    output = _run_as_root(command)
    atblog.log("zabbix.script_create_rce", ip, script=name, host=host,
               command=command, output=output[:300],
               msg="script executed on host as root via Zabbix")
    return _page(f"""<div class="wrap"><h1>{name} → {host}</h1>
<div class="card"><pre>{output or '(no output)'}</pre>
<a class="btn sm" href="/zabbix.php?action=host.list">← Hosts</a></div></div>""")


# ---------------------------------------------------- headless JSON-RPC path
@app.post("/api_jsonrpc.php")
def api_jsonrpc():
    ip = atblog.client_ip(request)
    body = request.get_json(silent=True) or {}
    rpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {}) or {}
    if not _auth():
        atblog.log("zabbix.auth_fail", ip, method=method)
        return {"jsonrpc": "2.0", "error": {"code": -32602, "message": "Not authorised"}, "id": rpc_id}
    if method == "script.create":
        command = params.get("command", "")
        output = _run_as_root(command)
        atblog.log("zabbix.script_create_rce", ip, command=command, output=output[:300],
                   msg="command executed as root via Zabbix script.create")
        return {"jsonrpc": "2.0", "result": {"scriptids": ["1"], "output": output}, "id": rpc_id}
    return {"jsonrpc": "2.0", "result": [], "id": rpc_id}


@app.get("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80, threaded=True)
