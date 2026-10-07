"""Step 6a - grafana.atbmarket.com (internal, no host port).

Grafana with a reused ATB login (education@atbmarket.com:Edu003868$). Once in,
the "Zabbix DB" MySQL data source is reachable from the Explore view and runs
arbitrary SQL. That data-source account (`grafana`) is over-privileged on the
Zabbix schema, so the attacker can read `config.session_key` and INSERT a forged
admin row into `sessions` — the setup for the Zabbix takeover (step 6b).

Everything here is a browser-clickable UI; no host port, reach it after pivoting
from the supplier web-shell (curl / port-forward to http://grafana.atbmarket.com).
"""
import os
import secrets

import pymysql
from flask import Flask, request, Response, redirect, make_response
import atblog

app = Flask(__name__)

# Reused ATB credentials (same password as Moodle / AD service account).
REUSED_USER = "education@atbmarket.com"
REUSED_PASS = "Edu003868$"

# "Zabbix DB" data source — an over-privileged MySQL account on the Zabbix schema.
DS = {
    "host": os.environ.get("ZABBIX_DB_HOST", "zabbix-db"),
    "db": os.environ.get("ZABBIX_DB_NAME", "zabbix"),
    "user": os.environ.get("ZABBIX_DB_USER", "grafana"),
    "password": os.environ.get("ZABBIX_DB_PASS", "Gr4f4na_DS_ro"),
}

_SESSIONS = set()  # active grafana web-session tokens


# ------------------------------------------------------------------ styling
_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',Roboto,-apple-system,Arial,sans-serif;background:#0b0c0e;
     color:#d8d9da;min-height:100vh}
a{color:#ff9830;text-decoration:none}
.top{display:flex;align-items:center;gap:12px;padding:12px 20px;background:#111217;
     border-bottom:1px solid #22252b}
.logo{font-weight:800;font-size:18px;color:#fff}.logo span{color:#ff9830}
.top .sp{flex:1}.top .u{font-size:13px;color:#8e8e8e}
.wrap{max-width:980px;margin:0 auto;padding:24px 20px}
h1{font-size:20px;font-weight:600;margin-bottom:4px}
.muted{color:#8e8e8e;font-size:13px}
.panel{background:#181b1f;border:1px solid #22252b;border-radius:6px;padding:18px;margin-top:18px}
label{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.4px;
      color:#8e8e8e;margin:14px 0 6px}
input,select,textarea{width:100%;background:#0b0c0e;border:1px solid #2c3235;
      border-radius:4px;color:#d8d9da;padding:10px 12px;font-size:14px;font-family:inherit}
textarea{font-family:'JetBrains Mono',monospace;min-height:110px;white-space:pre}
input:focus,textarea:focus,select:focus{outline:none;border-color:#ff9830}
.btn{display:inline-block;margin-top:16px;background:#ff9830;color:#111;border:none;
     border-radius:4px;padding:10px 18px;font-size:14px;font-weight:600;cursor:pointer}
.btn:hover{background:#ffb357}
table{width:100%;border-collapse:collapse;margin-top:14px;font-size:13px}
th,td{border:1px solid #2c3235;padding:7px 10px;text-align:left;
      font-family:'JetBrains Mono',monospace}
th{background:#22252b;color:#fff}
.err{color:#ff5286;margin-top:12px;font-family:monospace;font-size:13px}
.ok{color:#73bf69;margin-top:12px;font-size:13px}
.login{max-width:380px;margin:9vh auto 0}
.chip{display:inline-block;background:#22252b;border-radius:3px;padding:2px 8px;
      font-size:12px;margin:2px 4px 2px 0;cursor:pointer;color:#ccccdc}
"""


def _page(body, user=None):
    bar = (f'<div class="u">{user} &nbsp;·&nbsp; <a href="/logout">sign out</a></div>'
           if user else '')
    return Response(f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Grafana</title><style>{_CSS}</style></head><body>
<div class="top"><div class="logo">◉ Graf<span>ana</span></div><div class="sp"></div>{bar}</div>
{body}
</body></html>""", mimetype="text/html")


def _token():
    return request.cookies.get("grafana_session", "")


def _logged_in():
    return _token() in _SESSIONS


# --------------------------------------------------------------------- auth
@app.route("/login", methods=["GET", "POST"])
def login():
    ip = atblog.client_ip(request)
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form
        user = (data.get("user") or data.get("username") or "").strip()
        password = data.get("password") or ""
        if user == REUSED_USER and password == REUSED_PASS:
            tok = secrets.token_hex(16)
            _SESSIONS.add(tok)
            atblog.log("grafana.login_reused_creds", ip, user=user,
                       msg="Grafana login with reused ATB credentials")
            if request.is_json:
                return {"ok": True, "token": tok}
            resp = make_response(redirect("/explore"))
            resp.set_cookie("grafana_session", tok, httponly=True)
            return resp
        atblog.log("grafana.login_fail", ip, user=user)
        if request.is_json:
            return {"ok": False}, 401
        return _login_page(error="Invalid username or password")
    if _logged_in():
        return redirect("/explore")
    return _login_page()


def _login_page(error=""):
    err = f'<div class="err">{error}</div>' if error else ""
    return _page(f"""
<div class="panel login">
  <h1>Welcome to Grafana</h1>
  <div class="muted">ATB Monitoring · sign in to continue</div>
  <form method="post" action="/login">
    <label>Email or username</label>
    <input name="user" autofocus placeholder="email">
    <label>Password</label>
    <input name="password" type="password" placeholder="password">
    <button class="btn" type="submit">Log in</button>
    {err}
  </form>
</div>""")


@app.get("/logout")
def logout():
    _SESSIONS.discard(_token())
    resp = make_response(redirect("/login"))
    resp.delete_cookie("grafana_session")
    return resp


# ------------------------------------------------------------- Explore / SQL
@app.route("/explore", methods=["GET", "POST"])
def explore():
    ip = atblog.client_ip(request)
    if not _logged_in():
        return redirect("/login")

    result_html = ""
    sql = ""
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form
        sql = (data.get("sql") or "").strip()
        rows, cols, err, meta = _run_sql(sql, ip)
        if err:
            result_html = f'<div class="err">{err}</div>'
            if request.is_json:
                return {"ok": False, "error": err}, 400
        else:
            if request.is_json:
                return {"ok": True, "columns": cols, "rows": rows, "meta": meta}
            result_html = _render_table(cols, rows, meta)

    examples = (
        'SELECT session_key FROM config',
        'SELECT userid, username, roleid FROM users',
        'SELECT hostid, host, agent_ip FROM hosts',
    )
    chips = "".join(
        f'<span class="chip" onclick="document.getElementById(\'sql\').value='
        f'{q!r}">{q}</span>' for q in examples
    )
    return _page(f"""
<div class="wrap">
  <h1>Explore</h1>
  <div class="muted">Data source: <b>Zabbix DB</b> (MySQL · {DS['host']}/{DS['db']} · user <code>{DS['user']}</code>)</div>
  <div class="panel">
    <form method="post" action="/explore">
      <label>SQL query</label>
      <textarea id="sql" name="sql" spellcheck="false">{sql or 'SELECT session_key FROM config'}</textarea>
      <div style="margin-top:8px">{chips}</div>
      <button class="btn" type="submit">Run query</button>
    </form>
    {result_html}
  </div>
</div>""", user=REUSED_USER)


def _run_sql(sql, ip):
    """Execute arbitrary SQL through the over-privileged data-source account."""
    if not sql:
        return None, None, "empty query", None
    low = sql.lower()
    atblog.log("grafana.datasource_query", ip, sql=sql[:300],
               msg="SQL executed via Grafana Zabbix data source")
    if "insert" in low and "sessions" in low:
        atblog.log("grafana.zabbix_session_forged", ip, sql=sql[:300],
                   msg="forged session row INSERTed into Zabbix DB via Grafana")
    try:
        conn = pymysql.connect(
            host=DS["host"], user=DS["user"], password=DS["password"],
            database=DS["db"], connect_timeout=8, autocommit=True,
            cursorclass=pymysql.cursors.Cursor,
        )
    except Exception as exc:
        atblog.log("grafana.datasource_unreachable", ip, error=str(exc))
        return None, None, f"data source error: {exc}", None
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description:
                cols = [d[0] for d in cur.description]
                rows = [list(r) for r in cur.fetchall()]
                return rows, cols, None, f"{len(rows)} row(s)"
            return [], [], None, f"{cur.rowcount} row(s) affected"
    except Exception as exc:
        return None, None, f"SQL error: {exc}", None
    finally:
        conn.close()


def _render_table(cols, rows, meta):
    if not cols:
        return f'<div class="ok">OK — {meta}</div>'
    head = "".join(f"<th>{c}</th>" for c in cols)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(f"<td>{'' if v is None else v}</td>" for v in r) + "</tr>"
    return f'<div class="ok">{meta}</div><table><tr>{head}</tr>{body}</table>'


@app.get("/")
def index():
    return redirect("/explore" if _logged_in() else "/login")


@app.get("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80, threaded=True)
