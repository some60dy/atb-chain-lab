"""Step 6a - grafana.atbmarket.com (internal, no host port).

ATB Monitoring Grafana. Login is LDAP-backed; the e-learning service account
(education@atbmarket.com:Edu003868$) reuses its AD password here. Once in, the
"Zabbix DB" MySQL data source runs whatever SQL Explore (or /api/ds/query)
sends it. That data-source account (`grafana`) is over-privileged on the Zabbix
schema, so the attacker can read `config.session_key` and INSERT a forged admin
row into `sessions` — the setup for the Zabbix takeover (step 6b).

Reach it after pivoting from the supplier web-shell
(curl / port-forward to http://grafana.atbmarket.com:3000).
"""
import datetime
import decimal
import html
import json
import os
import re
import secrets
import threading
import time
from urllib.parse import quote, urlencode

import pymysql
from flask import Flask, request, Response, redirect, make_response, jsonify, send_from_directory

import atblog
import gdata as G
import gmetrics as M

app = Flask(__name__, static_folder=None)
app.json.sort_keys = False
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Reused ATB credentials (same password as Moodle / AD service account).
REUSED_USER = "education@atbmarket.com"
REUSED_PASS = "Edu003868$"
ME = next(u for u in G.USERS if u["login"] == REUSED_USER)

# "Zabbix DB" data source — an over-privileged MySQL account on the Zabbix schema.
DS = {
    "host": os.environ.get("ZABBIX_DB_HOST", "zabbix-db"),
    "db": os.environ.get("ZABBIX_DB_NAME", "zabbix"),
    "user": os.environ.get("ZABBIX_DB_USER", "grafana"),
    "password": os.environ.get("ZABBIX_DB_PASS", "Gr4f4na_DS_ro"),
}

# token -> per-session state (prefs, stars, recently viewed, query history)
_SESSIONS = {}
DEFAULT_SQL = "SELECT hostid, host, name, status FROM hosts WHERE status IN (0, 1) AND flags IN (0, 4) ORDER BY host"
_LOCK = threading.Lock()
STARTED = time.time()
ASSET_V = "a3f9c1e2"


def _db():
    return pymysql.connect(host=DS["host"], user=DS["user"], password=DS["password"],
                           database=DS["db"], connect_timeout=8, read_timeout=30,
                           autocommit=True, cursorclass=pymysql.cursors.Cursor)


E = lambda s: html.escape("" if s is None else str(s), quote=True)  # noqa: E731


def _jsdump(o):
    return json.dumps(o, default=_jsonable).replace("</", "<\\/")


def _jsonable(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", "replace")
    if isinstance(v, datetime.timedelta):
        return str(v)
    return str(v)


# ===================================================================== auth
def _token():
    return request.cookies.get("grafana_session", "")


def _sess():
    return _SESSIONS.get(_token())


def _logged_in():
    s = _sess()
    if s:
        s["seen"] = time.time()
    return s is not None


def _new_session(ip):
    tok = secrets.token_hex(16)
    _SESSIONS[tok] = {
        "created": time.time(), "seen": time.time(), "ip": ip,
        "ua": request.headers.get("User-Agent", "")[:200],
        "prefs": {"theme": "dark", "timezone": "browser", "weekStart": "", "homeDashboardUID": "",
                  "language": "en-US"},
        "stars": ["zbx-hosts", "sp-portal", "atb-web-fe"],
        "recent": ["zbx-hosts", "atb-web-fe", "node-linux"],
        "history": [
            {"ts": time.time() - 6 * 86400, "ds": "zbx-mysql", "starred": True,
             "q": "SELECT hostid, host, name, status FROM hosts WHERE status IN (0, 1) AND flags IN (0, 4) ORDER BY host"},
            {"ts": time.time() - 6 * 86400 + 120, "ds": "zbx-mysql", "starred": False,
             "q": "SELECT h.host, n.ip, n.dns, n.port, n.available\nFROM hosts h JOIN interface n ON n.hostid = h.hostid\n"
                  "WHERE h.status = 0 ORDER BY h.host"},
            {"ts": time.time() - 4 * 86400, "ds": "zbx-mysql", "starred": False,
             "q": "SELECT FROM_UNIXTIME(MAX(lastaccess)) AS last_login FROM sessions"},
            {"ts": time.time() - 2 * 86400, "ds": "prom-prod", "starred": False,
             "q": 'sum by (instance) (rate(nginx_http_requests_total{job="nginx"}[5m]))'},
        ],
    }
    return tok


def _unauth_api():
    return jsonify({"message": "Unauthorized", "statusCode": 401}), 401


@app.before_request
def _gate():
    p = request.path
    if p in ("/login", "/logout", "/healthz", "/api/health", "/favicon.ico", "/robots.txt",
             "/user/password/send-reset-email") or p.startswith("/public/"):
        return None
    if _logged_in():
        return None
    if p.startswith("/api/"):
        return _unauth_api()
    if p == "/explore" and request.method == "POST":
        return redirect("/login")
    nxt = request.full_path.rstrip("?")
    return redirect("/login" + ("?redirect=" + quote(nxt, safe="") if p != "/" else ""))


@app.route("/login", methods=["GET", "POST"])
def login():
    ip = atblog.client_ip(request)
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form
        user = (data.get("user") or data.get("username") or "").strip()
        password = data.get("password") or ""
        if user.lower() in (REUSED_USER, "education") and password == REUSED_PASS:
            tok = _new_session(ip)
            atblog.log("grafana.login_reused_creds", ip, user=user,
                       msg="Grafana login with reused ATB credentials")
            if request.is_json:
                resp = make_response(jsonify({"ok": True, "token": tok, "message": "Logged in",
                                              "redirectUrl": "/"}))
            else:
                nxt = request.args.get("redirect") or data.get("redirect") or "/"
                if not nxt.startswith("/") or nxt.startswith("//"):
                    nxt = "/"
                resp = make_response(redirect(nxt))
            resp.set_cookie("grafana_session", tok, httponly=True, samesite="Lax", max_age=7 * 86400)
            return resp
        atblog.log("grafana.login_fail", ip, user=user)
        if request.is_json:
            return jsonify({"ok": False, "message": "Invalid username or password"}), 401
        return _login_page(error="Invalid username or password", user=user), 401
    if _logged_in():
        return redirect("/")
    return _login_page()


def _login_page(error="", user=""):
    err = (f'<div class="alert alert-error"><span class="alert-icon">!</span>{E(error)}</div>'
           if error else "")
    red = request.args.get("redirect", "")
    return _bare_page("Grafana", f"""
<div class="login-wrap">
 <div class="login-bg"></div>
 <div class="login-box">
  <div class="login-logo">{LOGO_SVG}</div>
  <h1 class="login-title">Welcome to Grafana</h1>
  {err}
  <form method="post" action="/login{('?redirect=' + quote(red, safe='')) if red else ''}" class="login-form">
   <label for="user">Email or username</label>
   <input id="user" name="user" autofocus autocomplete="username" placeholder="email or username" value="{E(user)}">
   <label for="current-password">Password</label>
   <div class="pw-wrap"><input id="current-password" name="password" type="password"
     autocomplete="current-password" placeholder="password">
     <button type="button" class="pw-eye" onclick="var i=document.getElementById('current-password');i.type=i.type==='password'?'text':'password'" aria-label="Show password">{ic('eye')}</button></div>
   <button class="btn btn-primary btn-block" type="submit">Log in</button>
   <div class="login-links"><a href="/user/password/send-reset-email">Forgot your password?</a></div>
  </form>
 </div>
 <div class="login-footer">
   <a href="#" onclick="return false">{ic('doc')} Documentation</a> |
   <a href="#" onclick="return false">{ic('question')} Support</a> |
   <a href="#" onclick="return false">{ic('comments')} Community</a> |
   <span>Open Source</span> | <span>v{G.VERSION} ({G.COMMIT})</span>
 </div>
</div>""")


@app.route("/user/password/send-reset-email", methods=["GET", "POST"])
def reset_pw():
    if request.method == "POST":
        body = ('<p class="muted">Your account is managed by LDAP. Password resets are handled by the '
                'IT service desk (ext. 4400) via the AD self-service portal.</p>')
    else:
        body = ('<form method="post"><label>User</label><input name="userOrEmail" placeholder="Email or username">'
                '<button class="btn btn-primary btn-block" type="submit">Send reset email</button></form>')
    return _bare_page("Grafana", f"""<div class="login-wrap"><div class="login-bg"></div><div class="login-box">
  <div class="login-logo">{LOGO_SVG}</div><h1 class="login-title">Reset password</h1>
  <p class="muted" style="margin-bottom:12px">Enter your information to get a reset link sent to you</p>
  {body}<div class="login-links"><a href="/login">Back to login</a></div></div></div>""")


@app.get("/logout")
def logout():
    _SESSIONS.pop(_token(), None)
    resp = make_response(redirect("/login"))
    resp.delete_cookie("grafana_session")
    return resp


# ==================================================================== icons
_ICONS = {
    "home": '<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h5v-6h4v6h5V10"/>',
    "star": '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z"/>',
    "apps": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
            '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "compass": '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    "plug": '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0z"/><path d="M12 17v4"/>',
    "cog": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    "question": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14"/><path d="M12 17h.01"/>',
    "bars": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "sync": '<path d="M20 11a8 8 0 0 0-14.6-4.5L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.6 4.5L20 16"/><path d="M20 20v-4h-4"/>',
    "zoomout": '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4M8 11h6"/>',
    "share": '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/>',
    "save": '<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v6h8V3M8 21v-7h8v7"/>',
    "folder": '<path d="M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
    "dash": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2 20a7 7 0 0 1 14 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 13.5a7 7 0 0 1 4 6.5"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "doc": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
    "comments": '<path d="M4 5h16v11H9l-5 4z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "angle": '<path d="m6 9 6 6 6-6"/>',
    "angler": '<path d="m9 6 6 6-6 6"/>',
    "db": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "shield": '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "signout": '<path d="M9 21H5V3h4M16 17l5-5-5-5M21 12H9"/>',
    "check": '<path d="m5 12 5 5 9-10"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "play": '<path d="M7 4v16l13-8z"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
    "split": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14"/>',
    "keyboard": '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "monitor": '<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
}


def ic(name, size=16, cls=""):
    return (f'<svg class="ic {cls}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
            f'{_ICONS.get(name, "")}</svg>')


LOGO_SVG = ('<svg class="gf-logo" viewBox="0 0 64 64" width="32" height="32"><defs>'
            '<linearGradient id="lg" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#fcee1f"/>'
            '<stop offset="1" stop-color="#f15b2a"/></linearGradient></defs>'
            '<path fill="url(#lg)" d="M58.6 28.3c-.1-1.1-.3-2.4-.7-3.9-.4-1.4-1-3-1.8-4.7-.9-1.6-2-3.3-3.4-5'
            '-.6-.7-1.2-1.3-1.8-2 1-3.9-1.2-7.3-1.2-7.3-3.7-.2-6.1 1.2-7 1.8-.2-.1-.3-.1-.4-.2-.6-.3-1.3-.5'
            '-2-.7-.7-.2-1.4-.4-2.1-.5-.1 0-.2 0-.4-.1C36.4 1.3 31.2-.2 31.2-.2 28.6 1.5 28.1 4.6 28.1 4.6'
            's0 .1-.1.2c-.3.1-.6.2-.9.3-.4.1-.8.3-1.3.4-.4.2-.8.3-1.3.5-.9.4-1.7.8-2.6 1.3-.8.5-1.7 1-2.5'
            ' 1.5-.1 0-.1-.1-.1-.1-8.1-3.1-15.2.6-15.2.6-.7 8.6 3.2 14 4 15-.2.5-.4 1.1-.6 1.6-.6 2-1.1 4'
            '-1.3 6.2 0 .3-.1.6-.1.9C.6 31.2-1.9 36.7 4 41.8c.4 1.1.8 2.3 1.3 3.4.8 1.8 1.7 3.5 2.8 5'
            '-.2-.1 4.9 1.9 10.9.7 1.8 1.6 3.9 2.8 6 3.6.8.3 1.5.6 2.3.8.8.3 1.5.5 2.3.6.3.1.5.1.8.2 2.3'
            ' 3.3 6.4 3.8 6.4 3.8l.5-.6c2.4-1.9 2.7-5.8 2.7-6.4.4-.1.7-.3 1.1-.4 3.9-1.8 7-4.9 9-8.6-1.5'
            '.4-3.1.6-4.7.6-.8 0-1.6-.1-2.4-.2-.8-.1-1.6-.3-2.4-.5-3-.9-5.7-2.6-7.6-4.9-1-1.1-1.8-2.4-2.3'
            '-3.8-.6-1.4-.9-2.8-1-4.3-.1-.7-.1-1.5 0-2.2 0-.4.1-.7.1-1.1.1-.4.1-.7.2-1.1.3-1.5.9-2.9 1.6'
            '-4.2 1.5-2.6 3.8-4.6 6.4-5.8 1.3-.6 2.7-1 4.1-1.2.7-.1 1.4-.1 2.2-.1h.5c.2 0 .3 0 .5.1 3 .3'
            ' 5.9 1.5 8.1 3.5 1.2 1 2.1 2.2 2.9 3.5.8 1.3 1.3 2.7 1.6 4.1.1.4.2.7.2 1.1v.3c0 .1 0 .2.1.3'
            'v.9c0 .2 0 .5-.1.7 0 .3-.1.5-.1.8 0 .3-.1.5-.1.8-.1.5-.3 1-.5 1.5-.3 1-.8 1.9-1.4 2.8-1.1'
            ' 1.7-2.7 3.1-4.4 4.1-.9.5-1.8.9-2.8 1.2-1 .3-1.9.4-2.9.5h-.9c-.4 0-.7 0-1-.1-.3 0-.5-.1-.8'
            '-.1 0 0 .1.1.1.1 1.3 1.6 2.6 2.4 2.6 2.4 4.5-.1 8.2-3.9 9.3-5.4.1-.1.1-.2.1-.2l.1-.1c1.7-.1'
            ' 3.2-.4 4.6-1 0 0 .7-4.4-.8-7.6 0 0 .1-.1.1-.1.5-.5.9-1.1 1.3-1.7 2.7-4 3.2-8.9 2.4-11.8z"/>'
            '<circle cx="34" cy="32" r="7" fill="url(#lg)"/></svg>')

NAV = [
    ("home", "Home", "/", "home", []),
    ("starred", "Starred", "/dashboards?starred=true", "star", []),
    ("dashboards", "Dashboards", "/dashboards", "apps",
     [("Playlists", "/playlists"), ("Snapshots", "/dashboard/snapshots"), ("Library panels", "/library-panels")]),
    ("explore", "Explore", "/explore", "compass", []),
    ("alerting", "Alerting", "/alerting/list", "bell",
     [("Alert rules", "/alerting/list"), ("Contact points", "/alerting/notifications"),
      ("Notification policies", "/alerting/routes"), ("Silences", "/alerting/silences")]),
    ("connections", "Connections", "/connections", "plug",
     [("Add new connection", "/connections/add-new-connection"), ("Data sources", "/connections/datasources")]),
    ("admin", "Administration", "/admin", "cog",
     [("Default preferences", "/org"), ("Settings", "/admin/settings"), ("Organizations", "/admin/orgs"),
      ("Stats and license", "/admin/stats"), ("Plugins", "/plugins"), ("Users", "/admin/users"),
      ("Teams", "/org/teams"), ("Service accounts", "/org/serviceaccounts")]),
]


def _avatar(name, size=24):
    initials = "".join(w[0] for w in re.split(r"[\s._@-]+", name) if w)[:2].upper() or "?"
    hue = sum(map(ord, name)) % 360
    return (f'<span class="avatar" style="width:{size}px;height:{size}px;font-size:{size * .42:.0f}px;'
            f'background:hsl({hue},45%,38%)">{E(initials)}</span>')


def _shell(title, body, crumbs=(), active="", boot=None, page_class="", kiosk=False):
    s = _sess() or {}
    prefs = s.get("prefs", {})
    theme = prefs.get("theme", "dark")
    stars = set(s.get("stars", []))
    nav_html = []
    for key, label, href, icon, children in NAV:
        open_ = " open" if key == active else ""
        sub = ""
        if key == "starred":
            sub = "".join(f'<a class="nav-sub" href="{G.dash_url(G.DASH_BY_UID[u])}">{E(G.DASH_BY_UID[u]["title"])}</a>'
                          for u in s.get("stars", []) if u in G.DASH_BY_UID)
        elif children:
            sub = "".join(f'<a class="nav-sub" href="{h}">{E(lbl)}</a>' for lbl, h in children)
        tog = (f'<button class="nav-tog" onclick="this.closest(\'.nav-item\').classList.toggle(\'open\')">'
               f'{ic("angle", 14)}</button>' if sub else "")
        nav_html.append(f'<div class="nav-item{open_}"><div class="nav-row{" active" if key == active else ""}">'
                        f'<a href="{href}">{ic(icon)}<span>{label}</span></a>{tog}</div>'
                        f'<div class="nav-children">{sub}</div></div>')
    crumb_html = '<a href="/">Home</a>'
    for c in crumbs:
        if isinstance(c, tuple):
            crumb_html += f'<span class="sep">{ic("angler", 12)}</span><a href="{c[1]}">{E(c[0])}</a>'
        else:
            crumb_html += f'<span class="sep">{ic("angler", 12)}</span><span>{E(c)}</span>'
    bootdata = {
        "user": {"id": ME["id"], "login": ME["login"], "email": ME["email"], "name": ME["name"],
                 "orgId": 1, "orgName": "Main Org.", "orgRole": ME["role"], "isGrafanaAdmin": True,
                 "theme": theme, "timezone": prefs.get("timezone", "browser"),
                 "weekStart": prefs.get("weekStart", "")},
        "settings": {"buildInfo": {"version": G.VERSION, "commit": G.COMMIT, "edition": "Open Source",
                                   "env": "production"}, "appSubUrl": "", "defaultDatasource": "Zabbix DB"},
        "stars": sorted(stars),
    }
    page = boot or {}
    return Response(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta name="theme-color" content="#000"><title>{E(title)} - Grafana</title>
<link rel="icon" type="image/svg+xml" href="/public/img/fav32.svg">
<link rel="stylesheet" href="/public/build/grafana.dark.{ASSET_V}.css">
</head><body class="theme-{E(theme)} {page_class}{' kiosk' if kiosk else ''}">
<div class="app">
<header class="topbar">
  <button class="tb-btn menu-btn" id="menuBtn" title="Toggle menu">{ic('bars')}</button>
  <a href="/" class="tb-logo" title="Go to home">{LOGO_SVG}</a>
  <nav class="crumbs">{crumb_html}</nav>
  <div class="tb-spacer"></div>
  <button class="tb-search" id="searchBtn">{ic('search')}<span>Search or jump to...</span><kbd>ctrl+k</kbd></button>
  <div class="tb-spacer"></div>
  <div class="dd"><button class="tb-btn" data-dd>{ic('plus')}{ic('angle', 12)}</button>
   <div class="dd-menu right"><a href="/dashboard/import">Import dashboard</a><a href="/alerting/new">New alert rule</a></div></div>
  <div class="dd"><button class="tb-btn" data-dd>{ic('question')}</button>
   <div class="dd-menu right"><a href="#" onclick="return false">{ic('doc')} Documentation</a>
    <a href="#" onclick="return false">{ic('question')} Support</a>
    <a href="#" onclick="return false">{ic('comments')} Community</a>
    <a href="#" id="kbdBtn">{ic('keyboard')} Keyboard shortcuts</a>
    <div class="dd-foot">Grafana v{G.VERSION} ({G.COMMIT})</div></div></div>
  <div class="dd"><button class="tb-btn tb-user" data-dd>{_avatar(ME['name'] or ME['login'])}</button>
   <div class="dd-menu right"><div class="dd-head"><b>{E(ME['name'])}</b><br><span class="muted">{E(ME['email'])}</span></div>
    <a href="/profile">{ic('user')} Profile</a><a href="/profile/notifications">{ic('bell')} Notification history</a>
    <a href="/profile/password">{ic('lock')} Change password</a><div class="dd-sep"></div>
    <a href="/logout">{ic('signout')} Sign out</a></div></div>
</header>
<aside class="megamenu" id="megamenu"><div class="mm-head"><span>ATB Monitoring</span></div>{''.join(nav_html)}</aside>
<main class="main {page_class}">{body}</main>
</div>
<div id="tooltip" class="tooltip"></div>
<div id="modalRoot"></div>
<script>window.grafanaBootData={_jsdump(bootdata)};window.__page={_jsdump(page)};</script>
<script src="/public/build/app.{ASSET_V}.js"></script>
</body></html>""", mimetype="text/html")


def _bare_page(title, body):
    return Response(f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>{E(title)}</title>
<link rel="icon" type="image/svg+xml" href="/public/img/fav32.svg">
<link rel="stylesheet" href="/public/build/grafana.dark.{ASSET_V}.css"></head>
<body class="theme-dark">{body}</body></html>""", mimetype="text/html")


def _page_header(title, sub="", icon=None, actions=""):
    i = f'<span class="ph-icon">{ic(icon, 24)}</span>' if icon else ""
    return (f'<div class="page-header"><div class="ph-title">{i}<div><h1>{E(title)}</h1>'
            f'{f"<div class=ph-sub>{sub}</div>" if sub else ""}</div></div>'
            f'<div class="ph-actions">{actions}</div></div>')


def _tabs(items, active):
    return '<div class="tabs">' + "".join(
        f'<a class="tab{" active" if href == active else ""}" href="{href}">{E(lbl)}</a>' for lbl, href in items
    ) + "</div>"


def _ago(seconds):
    s = int(seconds)
    if s < 60:
        return "< 1 minute" if s > 5 else "Now"
    for div, unit in ((31536000, "year"), (2592000, "month"), (604800, "week"), (86400, "day"),
                      (3600, "hour"), (60, "minute")):
        if s >= div:
            n = s // div
            return f"{n} {unit}{'s' if n > 1 else ''}"
    return "Now"


def _table(headers, rows, cls="table"):
    h = "".join(f"<th>{x}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'


# ============================================================= time / query
_REL = re.compile(r"now(?:([+-])(\d+)([smhdwMy]))?(?:/([smhdwMy]))?$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800, "M": 2592000, "y": 31536000}


def parse_time(v, now=None, end=False):
    now = now or time.time()
    if v is None or v == "":
        return now
    s = str(v).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        x = float(s)
        return x / 1000.0 if x > 1e11 else x
    m = _REL.match(s)
    if not m:
        try:
            return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return now
    t = now
    if m.group(1):
        d = int(m.group(2)) * _UNIT[m.group(3)]
        t = t - d if m.group(1) == "-" else t + d
    if m.group(4):
        u = _UNIT[m.group(4)]
        off = 3 * 3600
        t = ((t + off) // u) * u - off + (u - 1 if end else 0)
    return t


NICE = [15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400]


def pick_interval(t_from, t_to, max_points=600, floor=60):
    raw = max(1.0, (t_to - t_from) / max(1, max_points))
    for n in NICE:
        if n >= raw and n >= floor:
            return n
    return NICE[-1]


def _ival_s(spec):
    spec = str(spec).strip().strip("'\"")
    m = re.fullmatch(r"(\d+)([smhdw]?)", spec)
    if not m:
        return 60
    return int(m.group(1)) * _UNIT.get(m.group(2) or "s", 1)


def expand_macros(sql, t_from, t_to, interval):
    f, t = int(t_from), int(t_to)
    sql = sql.replace("$__interval_ms", str(interval * 1000)).replace("$__interval", f"{interval}s")
    sql = re.sub(r"\$__unixEpochFilter\(\s*([^)]+?)\s*\)", lambda m: f"{m.group(1)} >= {f} AND {m.group(1)} <= {t}", sql)
    sql = re.sub(r"\$__timeFilter\(\s*([^)]+?)\s*\)",
                 lambda m: f"{m.group(1)} BETWEEN FROM_UNIXTIME({f}) AND FROM_UNIXTIME({t})", sql)
    sql = re.sub(r"\$__unixEpochGroupAlias\(\s*([^,]+?)\s*,\s*([^)]+?)\s*\)",
                 lambda m: f"FLOOR({m.group(1)}/{_ival_s(m.group(2))})*{_ival_s(m.group(2))} AS time", sql)
    sql = re.sub(r"\$__unixEpochGroup\(\s*([^,]+?)\s*,\s*([^)]+?)\s*\)",
                 lambda m: f"FLOOR({m.group(1)}/{_ival_s(m.group(2))})*{_ival_s(m.group(2))}", sql)
    sql = re.sub(r"\$__timeGroupAlias\(\s*([^,]+?)\s*,\s*([^)]+?)\s*\)",
                 lambda m: f"UNIX_TIMESTAMP({m.group(1)}) DIV {_ival_s(m.group(2))} * {_ival_s(m.group(2))} AS time",
                 sql)
    sql = sql.replace("$__unixEpochFrom()", str(f)).replace("$__unixEpochTo()", str(t))
    sql = sql.replace("$__timeFrom()", f"FROM_UNIXTIME({f})").replace("$__timeTo()", f"FROM_UNIXTIME({t})")
    return sql


def _audit_sql(sql, ip):
    low = sql.lower()
    atblog.log("grafana.datasource_query", ip, sql=sql[:300],
               msg="SQL executed via Grafana Zabbix data source")
    if "insert" in low and "sessions" in low:
        atblog.log("grafana.zabbix_session_forged", ip, sql=sql[:300],
                   msg="forged session row INSERTed into Zabbix DB via Grafana")


# known (provisioned) panel / variable queries are not audited as ad-hoc SQL
def _tmpl_regex(raw):
    rx = re.escape(raw)
    rx = re.sub(r"\\\$\\\{?[A-Za-z_]\w*\\\}?", lambda m: m.group(0) if "__" in m.group(0) else r"[^']*", rx)
    return re.compile(rx, re.S)


_KNOWN_SQL = []
for _d in G.DASHBOARDS:
    for _p in _d["panels"]:
        for _t in _p.get("targets", []):
            if _t.get("rawSql"):
                _KNOWN_SQL.append(_tmpl_regex(_t["rawSql"]))
    for _v in _d["templating"]["list"]:
        if _v["type"] == "query" and _v["datasource"]["type"] == "mysql":
            _KNOWN_SQL.append(_tmpl_regex(_v["query"]))


def _is_known(sql):
    return any(r.fullmatch(sql) for r in _KNOWN_SQL)


def _cell(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, datetime.datetime):
        return v.replace(tzinfo=v.tzinfo or datetime.timezone.utc).timestamp() * 1000
    if isinstance(v, datetime.date):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8")
        except UnicodeDecodeError:
            return "0x" + v.hex()
    if isinstance(v, datetime.timedelta):
        return str(v)
    return v


def sql_exec(sql):
    conn = _db()
    try:
        with conn.cursor() as cur:
            t0 = time.time()
            cur.execute(sql)
            ms = (time.time() - t0) * 1000
            if cur.description:
                cols = [d[0] for d in cur.description]
                types = [d[1] for d in cur.description]
                rows = cur.fetchmany(10000)
                return cols, types, rows, None, ms
            return [], [], [], cur.rowcount, ms
    finally:
        conn.close()


_TIME_TYPES = {7, 10, 12, 14}  # TIMESTAMP, DATE, DATETIME, NEWDATE
_NUM_TYPES = {0, 1, 2, 3, 4, 5, 8, 9, 13, 246}


def sql_frame(ref, sql, cols, types, rows, affected, ms, fmt):
    fields, values = [], []
    for i, c in enumerate(cols):
        col = [_cell(r[i]) for r in rows]
        ftype = "string"
        if types[i] in _TIME_TYPES:
            ftype = "time"
        elif types[i] in _NUM_TYPES:
            ftype = "number"
        if c.lower() in ("time", "time_sec") and ftype == "number":
            ftype = "time"
            col = [None if v is None else (v * 1000 if v < 1e11 else v) for v in col]
        fields.append({"name": c, "type": ftype, "typeInfo": {"frame": ftype, "nullable": True}})
        values.append(col)
    meta = {"executedQueryString": sql, "typeVersion": [0, 0],
            "custom": {"rowsAffected": affected} if affected is not None else None,
            "stats": [{"displayName": "Query time", "unit": "ms", "value": round(ms, 1)}]}
    if fmt == "time_series" and not any(f["type"] == "time" for f in fields) and fields:
        meta["notices"] = [{"severity": "info", "text": "No time column found — showing result as table"}]
    return {"schema": {"refId": ref, "meta": meta, "fields": fields}, "data": {"values": values}}


def _legend(fmt, labels, expr):
    if fmt:
        return re.sub(r"\{\{\s*([A-Za-z_]\w*)\s*\}\}", lambda m: labels.get(m.group(1), ""), fmt)
    name = labels.get("__name__", "")
    rest = ", ".join(f'{k}="{v}"' for k, v in sorted(labels.items()) if k != "__name__")
    return f"{name}{{{rest}}}" if rest else (name or expr)


def prom_frames(ref, q, t_from, t_to, interval):
    expr = (q.get("expr") or "").strip()
    if not expr:
        return []
    lv = M.label_values(expr)
    if lv is not None:
        return [{"schema": {"refId": ref, "fields": [{"name": "text", "type": "string"}]},
                 "data": {"values": [lv]}}]
    instant = bool(q.get("instant")) and not q.get("range")
    res = M.prom_eval(expr, t_from, t_to, interval, instant=instant or q.get("format") == "table")
    frames = []
    if q.get("format") == "table":
        keys = sorted({k for lb, _ in res for k in lb if k != "__name__"})
        fields = [{"name": k, "type": "string"} for k in keys] + [{"name": "Value", "type": "number"}]
        vals = [[] for _ in fields]
        for lb, pts in res:
            for i, k in enumerate(keys):
                vals[i].append(lb.get(k, ""))
            vals[-1].append(pts[-1][1])
        return [{"schema": {"refId": ref, "meta": {"executedQueryString": f"Expr: {expr}"}, "fields": fields},
                 "data": {"values": vals}}]
    for lb, pts in res:
        name = _legend(q.get("legendFormat", ""), lb, expr)
        frames.append({"schema": {"refId": ref, "name": name,
                                  "meta": {"executedQueryString": f"Expr: {expr}\nStep: {interval}s"},
                                  "fields": [{"name": "Time", "type": "time"},
                                             {"name": "Value", "type": "number",
                                              "labels": {k: v for k, v in lb.items() if k != "__name__"},
                                              "config": {"displayNameFromDS": name}}]},
                       "data": {"values": [[p[0] * 1000 for p in pts], [p[1] for p in pts]]}})
    return frames


def testdata_frames(ref, q, t_from, t_to, interval):
    sc = q.get("scenarioId", "random_walk")
    n = int(q.get("seriesCount") or 1)
    frames = []
    for s in range(n):
        ts, vs, v = [], [], 50.0
        start = int(t_from // interval * interval)
        for t in range(start, int(t_to) + 1, interval):
            if sc == "random_walk":
                v += (M._h("tdw", s, t) - 0.5) * 10
            else:
                v = 50 + 40 * M._smooth(f"td{s}", t, 1800)
            ts.append(t * 1000)
            vs.append(round(v, 3))
        frames.append({"schema": {"refId": ref, "name": f"{ref}-series{'' if n == 1 else s}",
                                  "fields": [{"name": "time", "type": "time"},
                                             {"name": f"{ref}-series", "type": "number"}]},
                       "data": {"values": [ts, vs]}})
    return frames


def ds_query(body, ip, audit=True):
    now = time.time()
    t_from = parse_time(body.get("from", "now-6h"), now)
    t_to = parse_time(body.get("to", "now"), now, end=True)
    results = {}
    for q in body.get("queries", []):
        ref = q.get("refId", "A")
        ds = q.get("datasource") or {}
        if isinstance(ds, str):
            ds = {"uid": G.DS_BY_NAME.get(ds, {}).get("uid", ds)}
        dsm = G.DS_BY_UID.get(ds.get("uid")) or (G.DATASOURCES[0] if not ds.get("uid") else None)
        mdp = int(q.get("maxDataPoints") or 600)
        try:
            if dsm is None:
                raise ValueError(f"data source not found")
            if dsm["type"] == "mysql":
                raw = q.get("rawSql") or ""
                if not raw.strip():
                    results[ref] = {"status": 200, "frames": []}
                    continue
                interval = pick_interval(t_from, t_to, mdp, 60)
                expanded = expand_macros(raw, t_from, t_to, interval)
                if audit and not _is_known(raw):
                    _audit_sql(raw, ip)
                cols, types, rows, aff, ms = sql_exec(expanded)
                results[ref] = {"status": 200, "frames": [
                    sql_frame(ref, expanded, cols, types, rows, aff, ms, q.get("format", "time_series"))]}
            elif dsm["type"] == "prometheus":
                interval = pick_interval(t_from, t_to, mdp, 30)
                results[ref] = {"status": 200, "frames": prom_frames(ref, q, t_from, t_to, interval)}
            elif dsm["type"] == "grafana-testdata-datasource":
                interval = pick_interval(t_from, t_to, mdp, 15)
                results[ref] = {"status": 200, "frames": testdata_frames(ref, q, t_from, t_to, interval)}
            else:
                raise ValueError("query: plugin does not support backend queries via /api/ds/query; "
                                 "use the Zabbix DB direct connection")
        except M.PromError as exc:
            results[ref] = {"status": 400, "error": str(exc), "frames": []}
        except pymysql.MySQLError as exc:
            if isinstance(exc, pymysql.err.OperationalError) and exc.args and exc.args[0] in (2003, 2005, 2013):
                atblog.log("grafana.datasource_unreachable", ip, error=str(exc))
                msg = f"failed to connect to server - please inspect Grafana server log for details"
            else:
                code = exc.args[0] if exc.args else ""
                msg = f"Error {code}: {exc.args[1] if len(exc.args) > 1 else exc}"
            results[ref] = {"status": 400, "error": msg, "errorSource": "downstream", "frames": []}
        except Exception as exc:
            results[ref] = {"status": 500, "error": str(exc), "frames": []}
    return {"results": results}


# ==================================================== Explore (SQL console)
def _run_sql(sql, ip):
    """Execute arbitrary SQL through the over-privileged data-source account."""
    if not sql:
        return None, None, "empty query", None
    _audit_sql(sql, ip)
    try:
        conn = _db()
    except Exception as exc:
        atblog.log("grafana.datasource_unreachable", ip, error=str(exc))
        return None, None, f"data source error: {exc}", None
    try:
        with conn.cursor() as cur:
            cur.execute(expand_macros(sql, time.time() - 3600, time.time(), 60))
            if cur.description:
                cols = [d[0] for d in cur.description]
                rows = [[_cell(v) for v in r] for r in cur.fetchall()]
                return rows, cols, None, f"{len(rows)} row(s)"
            return [], [], None, f"{cur.rowcount} row(s) affected"
    except Exception as exc:
        return None, None, f"SQL error: {exc}", None
    finally:
        conn.close()


def _add_history(ds_uid, q):
    s = _sess()
    if not s or not q.strip():
        return
    h = s["history"]
    if h and h[-1]["q"] == q and h[-1]["ds"] == ds_uid:
        h[-1]["ts"] = time.time()
        return
    h.append({"ts": time.time(), "ds": ds_uid, "q": q, "starred": False})
    del h[:-200]


@app.route("/explore", methods=["GET", "POST"])
def explore():
    ip = atblog.client_ip(request)
    server_result = ""
    sql = ""
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form
        sql = (data.get("sql") or "").strip()
        rows, cols, err, meta = _run_sql(sql, ip)
        _add_history("zbx-mysql", sql)
        if err:
            if request.is_json:
                return jsonify({"ok": False, "error": err}), 400
            server_result = f'<div class="alert alert-error">{E(err)}</div>'
        else:
            if request.is_json:
                return jsonify({"ok": True, "columns": cols, "rows": rows, "meta": meta})
            if cols:
                server_result = (f'<div class="muted small">{E(meta)}</div>' +
                                 _table([E(c) for c in cols],
                                        [[E("NULL" if v is None else v) for v in r] for r in rows], "table data"))
            else:
                server_result = f'<div class="alert alert-success">OK — {E(meta)}</div>'
    left = {}
    try:
        left = json.loads(request.args.get("left", "{}"))
    except ValueError:
        pass
    ds_uid = left.get("datasource") or "zbx-mysql"
    queries = left.get("queries") or [{"refId": "A", "rawSql": sql or DEFAULT_SQL,
                                       "format": "table"}]
    rng = left.get("range") or {"from": "now-1h", "to": "now"}
    s = _sess()
    boot = {"page": "explore", "datasource": ds_uid, "queries": queries, "range": rng,
            "datasources": [{"uid": d["uid"], "name": d["name"], "type": d["type"], "typeName": d["typeName"],
                             "isDefault": d["isDefault"]} for d in G.DATASOURCES if d["uid"] != "zbx-api"],
            "history": list(reversed(s["history"]))[:50], "metrics": M.METRIC_NAMES}
    body = f"""
<div class="explore">
 <div class="ex-toolbar">
  <h2>{ic('compass', 18)} Explore</h2>
  <div class="ds-picker" id="dsPicker"></div>
  <div class="tb-spacer"></div>
  <button class="btn btn-secondary btn-sm" id="exSplit" title="Split the pane">{ic('split')} Split</button>
  <button class="btn btn-secondary btn-sm" id="exAddToDash">{ic('apps')} Add to dashboard</button>
  <div id="exTime"></div>
  <button class="btn btn-primary btn-sm" id="exRun">{ic('sync')} Run query</button>
 </div>
 <div class="ex-body">
  <form method="post" action="/explore" id="exForm" class="ex-queries">
   <div id="exQueries"><div class="query-row">
     <div class="qr-head"><span class="ref">A</span><span class="muted">(Zabbix DB)</span></div>
     <textarea name="sql" class="code" rows="5" spellcheck="false">{E(sql or queries[0].get('rawSql', '') or DEFAULT_SQL)}</textarea>
     <button class="btn btn-primary btn-sm" type="submit">Run query</button></div></div>
  </form>
  <div class="ex-actions" id="exActions"></div>
  <div id="exResults">{server_result}</div>
 </div>
</div>"""
    return _shell("Explore", body, ["Explore"], "explore", boot, page_class="page-explore")


# ================================================================== pages
def _rec_view(uid):
    s = _sess()
    if s is None:
        return
    r = [u for u in s["recent"] if u != uid]
    r.insert(0, uid)
    s["recent"] = r[:20]


@app.get("/")
def index():
    s = _sess()
    home = s["prefs"].get("homeDashboardUID") or G.HOME_UID
    return _render_dashboard(home if home in G.DASH_BY_UID else G.HOME_UID, home_page=True)


@app.get("/d/<uid>")
@app.get("/d/<uid>/<slug>")
def dashboard_view(uid, slug=None):
    if uid not in G.DASH_BY_UID:
        return _shell("Not found", '<div class="page"><div class="empty-state"><h2>Dashboard not found</h2>'
                      '<p class="muted">Dashboard not found</p><a class="btn btn-primary" href="/dashboards">'
                      'Browse dashboards</a></div></div>', ["Dashboards"], "dashboards"), 404
    d = G.DASH_BY_UID[uid]
    want = G.slug(d["title"])
    if slug != want:
        qs = ("?" + request.query_string.decode()) if request.query_string else ""
        return redirect(f"/d/{uid}/{want}{qs}")
    return _render_dashboard(uid)


def _render_dashboard(uid, home_page=False):
    d = G.DASH_BY_UID[uid]
    s = _sess()
    if not home_page or uid != G.HOME_UID:
        _rec_view(uid)
    folder = G.FOLDER_BY_UID.get(d["folderUid"])
    crumbs = [("Dashboards", "/dashboards")]
    if folder:
        crumbs.append((folder["title"], f"/dashboards/f/{folder['uid']}/{G.slug(folder['title'])}"))
    crumbs.append(d["title"])
    if home_page and uid == G.HOME_UID:
        crumbs = []
    kiosk = request.args.get("kiosk") is not None
    dash = json.loads(json.dumps(d))
    # server-side data for dashlist / alertlist panels
    for p in dash["panels"]:
        if p["type"] == "dashlist":
            lst = s["stars"] if p["options"].get("showStarred") else s["recent"]
            p["_items"] = [{"title": G.DASH_BY_UID[u]["title"], "url": G.dash_url(G.DASH_BY_UID[u]),
                            "folder": (G.FOLDER_BY_UID.get(G.DASH_BY_UID[u]["folderUid"]) or {}).get("title",
                                                                                                      "General")}
                           for u in lst if u in G.DASH_BY_UID and u != uid][:8]
    boot = {"page": "dashboard", "dashboard": dash,
            "meta": {"slug": G.slug(d["title"]), "url": G.dash_url(d), "folderTitle": (folder or {}).get("title", "General"),
                     "folderUid": (folder or {}).get("uid", ""), "isStarred": uid in s["stars"],
                     "provisioned": True, "provisionedExternalId": f"{uid}.json", "canSave": False,
                     "isHome": home_page},
            "now": time.time()}
    body = '<div class="dashboard" id="dashboard"></div>'
    return _shell(d["title"] if not (home_page and uid == G.HOME_UID) else "Home", body, crumbs,
                  "home" if home_page else "dashboards", boot, page_class="page-dashboard", kiosk=kiosk)


@app.get("/dashboards")
@app.get("/dashboards/f/<fuid>")
@app.get("/dashboards/f/<fuid>/<slug>")
def browse(fuid=None, slug=None):
    s = _sess()
    starred_only = request.args.get("starred") == "true"
    folder = G.FOLDER_BY_UID.get(fuid) if fuid else None
    if fuid and not folder:
        return redirect("/dashboards")
    rows = []

    def drow(d, indent=False):
        f = G.FOLDER_BY_UID.get(d["folderUid"])
        tags = "".join(f'<span class="tag" style="--h:{sum(map(ord, t)) % 360}" data-tag="{E(t)}">{E(t)}</span>'
                       for t in d["tags"])
        star = "starred" if d["uid"] in s["stars"] else ""
        return (f'<tr class="b-row{" indent" if indent else ""}" data-title="{E(d["title"].lower())}" '
                f'data-tags="{E(",".join(d["tags"]))}" data-folder="{E(d["folderUid"] or "")}">'
                f'<td><a href="{G.dash_url(d)}">{ic("apps")} {E(d["title"])}</a></td>'
                f'<td class="muted">{ic("folder", 14)} {E(f["title"]) if f else "Dashboards"}</td>'
                f'<td>{tags}</td><td><button class="star-btn {star}" data-uid="{d["uid"]}" title="Mark as favorite">'
                f'{ic("star")}</button></td></tr>')

    if starred_only:
        title, sub = "Starred", "Dashboards you have marked as favorites"
        for u in s["stars"]:
            if u in G.DASH_BY_UID:
                rows.append(drow(G.DASH_BY_UID[u]))
    elif folder:
        title, sub = folder["title"], ""
        for d in G.DASHBOARDS:
            if d["folderUid"] == folder["uid"]:
                rows.append(drow(d))
    else:
        title, sub = "Dashboards", "Create and manage dashboards to visualize your data"
        for f in G.FOLDERS:
            n = sum(1 for d in G.DASHBOARDS if d["folderUid"] == f["uid"])
            rows.append(f'<tr class="b-folder" data-folder="{f["uid"]}"><td><button class="fold-tog">{ic("angler", 14)}</button>'
                        f'<a href="/dashboards/f/{f["uid"]}/{G.slug(f["title"])}">{ic("folder")} {E(f["title"])}</a>'
                        f' <span class="muted small">{n}</span></td><td></td><td></td><td></td></tr>')
            for d in G.DASHBOARDS:
                if d["folderUid"] == f["uid"]:
                    rows.append(drow(d, indent=True).replace('class="b-row indent"',
                                                             'class="b-row indent fold-child" style="display:none"'))
        for d in G.DASHBOARDS:
            if not d["folderUid"]:
                rows.append(drow(d))
    alltags = sorted({t for d in G.DASHBOARDS for t in d["tags"]})
    crumbs = [("Dashboards", "/dashboards"), title] if (folder or starred_only) else ["Dashboards"]
    ph_actions = ('<div class="dd"><button class="btn btn-primary" data-dd>New ' + ic("angle", 12) +
                  '</button><div class="dd-menu right"><a href="/dashboard/new">New dashboard</a>'
                  '<a href="/dashboards/folder/new">New folder</a><a href="/dashboard/import">Import</a></div></div>')
    body = f"""<div class="page">{_page_header(title, sub, actions=ph_actions)}
<div class="browse-filters">
 <div class="input-icon">{ic('search')}<input id="bSearch" placeholder="Search for dashboards and folders"></div>
 <select id="bTag"><option value="">Filter by tag</option>{''.join(f'<option>{E(t)}</option>' for t in alltags)}</select>
 <label class="chk"><input type="checkbox" id="bStarred" {'checked' if starred_only else ''}> Starred</label>
 <div class="tb-spacer"></div><span class="muted small">Sort: Alphabetically (A–Z)</span>
</div>
<table class="table browse" id="browseTbl"><thead><tr><th style="width:45%">Name</th><th>Location</th><th>Tags</th><th style="width:40px"></th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan=4 class="muted">No dashboards found</td></tr>'}</tbody></table></div>"""
    return _shell(title, body, crumbs[:-1] + [crumbs[-1]] if crumbs else [], "starred" if starred_only else "dashboards",
                  {"page": "browse"})


def _empty_page(title, crumbs, active, heading, text, icon="apps", btn=None):
    b = f'<a class="btn btn-primary" href="{btn[1]}">{E(btn[0])}</a>' if btn else ""
    return _shell(title, f'<div class="page">{_page_header(title)}<div class="empty-state">{ic(icon, 48)}'
                         f'<h2>{E(heading)}</h2><p class="muted">{text}</p>{b}</div></div>', crumbs, active)


@app.get("/dashboard/snapshots")
def snapshots():
    return _empty_page("Snapshots", [("Dashboards", "/dashboards"), "Snapshots"], "dashboards",
                       "You haven't created a snapshot yet",
                       "Snapshots are a way to share an interactive dashboard publicly. Open a dashboard and "
                       "click Share &rarr; Snapshot.", "share")


@app.get("/library-panels")
def library_panels():
    return _empty_page("Library panels", [("Dashboards", "/dashboards"), "Library panels"], "dashboards",
                       "You haven't created any library panels yet",
                       "Create a library panel from any existing dashboard panel through the panel context menu.",
                       "layers")


@app.get("/playlists")
def playlists():
    rows = ""
    for p in G.PLAYLISTS:
        items = ", ".join(E(G.DASH_BY_UID[u]["title"]) for u in p["items"])
        rows += (f'<div class="card"><div class="card-h"><b>{E(p["name"])}</b>'
                 f'<span class="muted small">every {p["interval"]}</span></div><div class="muted small">{items}</div>'
                 f'<div class="card-actions"><a class="btn btn-secondary btn-sm" href="/playlists/play/{p["uid"]}">'
                 f'{ic("play")} Start playlist</a><button class="btn btn-secondary btn-sm" data-share="/playlists/play/{p["uid"]}?kiosk">'
                 f'{ic("share")} Share</button></div></div>')
    body = f'<div class="page">{_page_header("Playlists", "Groups of dashboards that are displayed in a sequence")}' \
           f'<div class="cards">{rows}</div></div>'
    return _shell("Playlists", body, [("Dashboards", "/dashboards"), "Playlists"], "dashboards")


@app.get("/playlists/play/<uid>")
def playlist_play(uid):
    p = next((x for x in G.PLAYLISTS if x["uid"] == uid), None)
    if not p:
        return redirect("/playlists")
    d = G.DASH_BY_UID[p["items"][0]]
    return redirect(f"{G.dash_url(d)}?kiosk&playlist={uid}&pi=0")


@app.route("/dashboard/new")
@app.route("/dashboard/import")
@app.route("/dashboards/folder/new")
@app.route("/alerting/new")
def not_allowed():
    what = {"/dashboard/new": "New dashboard", "/dashboard/import": "Import dashboard",
            "/dashboards/folder/new": "New folder", "/alerting/new": "New alert rule"}[request.path]
    return _shell(what, f'<div class="page">{_page_header(what)}<div class="alert alert-info">{ic("info")} '
                        'This instance is provisioned from the <code>grafana-dashboards</code> repository '
                        '(<code>/etc/grafana/provisioning</code>). Changes made in the UI would be overwritten '
                        'on the next deploy — open a merge request instead.</div></div>',
                  [what], "dashboards")


# ---------------------------------------------------------------- alerting
_ALERT_CACHE = {"t": 0, "v": None}


def _cmp(op, v, thr):
    return v > thr if op == ">" else v < thr


def eval_rules():
    if _ALERT_CACHE["v"] is not None and time.time() - _ALERT_CACHE["t"] < 30:
        return _ALERT_CACHE["v"]
    out = []
    now = time.time()
    for r in G.ALERT_RULES:
        inst, health, err = [], "ok", ""
        try:
            if r["ds"]["type"] == "prometheus":
                for lb, pts in M.prom_eval(r["query"], now - 300, now, 60, instant=True):
                    v = pts[-1][1]
                    inst.append({"labels": {k: v2 for k, v2 in lb.items() if k != "__name__"}, "value": v})
            else:
                cols, types, rows, _, _ = sql_exec(r["query"])
                for row in rows:
                    inst.append({"labels": {"metric": str(row[0])}, "value": float(row[1] or 0)})
        except Exception as exc:
            health, err = "error", str(exc)[:200]
        for i in inst:
            i["state"] = "Alerting" if _cmp(r["op"], i["value"], r["threshold"]) else "Normal"
            i["labels"].update(r["labels"])
            i["labels"]["alertname"] = r["title"]
            i["labels"]["grafana_folder"] = G.FOLDER_BY_UID[r["folder"]]["title"]
            seed = int(M._h(r["uid"], "since") * 5 * 86400)
            i["activeAt"] = now - (seed if i["state"] == "Alerting" else 0)
        firing = [i for i in inst if i["state"] == "Alerting"]
        state = "firing" if firing else "inactive"
        if health == "error":
            state = "error"
        out.append(dict(r, state=state, health=health, lastError=err, instances=inst,
                        lastEvaluation=now - (now % 60)))
    _ALERT_CACHE.update(t=time.time(), v=out)
    return out


_ALERT_TABS = [("Alert rules", "/alerting/list"), ("Contact points", "/alerting/notifications"),
               ("Notification policies", "/alerting/routes"), ("Silences", "/alerting/silences")]


@app.get("/alerting")
@app.get("/alerting/list")
def alert_list():
    rules = eval_rules()
    nf = sum(1 for r in rules if r["state"] == "firing")
    nn = sum(1 for r in rules if r["state"] == "inactive")
    ne = sum(1 for r in rules if r["state"] == "error")
    html_ = ""
    for f in G.FOLDERS:
        rs = [r for r in rules if r["folder"] == f["uid"]]
        if not rs:
            continue
        groups = {}
        for r in rs:
            groups.setdefault(r["group"], []).append(r)
        for g, lst in groups.items():
            items = ""
            for r in lst:
                st = {"firing": ("Firing", "bad"), "inactive": ("Normal", "ok"), "error": ("Error", "warn")}[r["state"]]
                inst_rows = "".join(
                    f'<tr><td><span class="badge {"bad" if i["state"] == "Alerting" else "ok"}">'
                    f'{i["state"]}</span></td><td>{"".join(f"<span class=lbl>{E(k)}={E(v)}</span>" for k, v in i["labels"].items() if k not in ("alertname", "grafana_folder"))}</td>'
                    f'<td>{E(round(i["value"], 3))}</td><td class="muted">{E(_ago(now_s() - i["activeAt"])) if i["state"] == "Alerting" else "-"}</td></tr>'
                    for i in r["instances"])
                items += f"""<div class="rule" data-state="{r['state']}">
 <div class="rule-h" onclick="this.parentNode.classList.toggle('open')">{ic('angler', 14, 'caret')}
  <span class="badge {st[1]}">{st[0]}</span><b>{E(r['title'])}</b><span class="tb-spacer"></span>
  <span class="muted small">{len(r['instances'])} instance(s) · evaluated every {r['interval']} for {r['for']}</span>
  <a class="btn btn-secondary btn-xs" href="/alerting/grafana/{r['uid']}/view" onclick="event.stopPropagation()">{ic('eye', 14)} View</a></div>
 <div class="rule-b"><div class="rule-meta"><div><span class="muted">Summary</span><br>{E(r['summary'])}</div>
  <div><span class="muted">Data source</span><br>{E(G.DS_BY_UID[r['ds']['uid']]['name'])}</div>
  <div><span class="muted">Condition</span><br>B: Reduce(A, last) {E(r['op'])} {r['threshold']}</div>
  <div><span class="muted">Labels</span><br>{''.join(f'<span class=lbl>{E(k)}={E(v)}</span>' for k, v in r['labels'].items())}</div></div>
  <pre class="code-block">{E(r['query'])}</pre>
  {_table(['State', 'Labels', 'Value', 'Active since'], []).replace('<tbody></tbody>', '<tbody>' + inst_rows + '</tbody>')}
  {f'<div class="alert alert-error">{E(r["lastError"])}</div>' if r['lastError'] else ''}</div></div>"""
            html_ += (f'<div class="rule-group"><div class="rg-h">{ic("folder", 14)} {E(f["title"])} '
                      f'<span class="muted">&rsaquo;</span> {E(g)}<span class="tb-spacer"></span>'
                      f'<span class="muted small">{len(lst)} rules</span></div>{items}</div>')
    body = f"""<div class="page">{_page_header('Alerting', 'Learn about problems in your systems moments after they occur', 'bell')}
{_tabs(_ALERT_TABS, '/alerting/list')}
<div class="browse-filters"><div class="input-icon">{ic('search')}<input id="ruleSearch" placeholder="Search by name or label"></div>
 <div class="seg" id="ruleState"><button class="on" data-s="">All</button><button data-s="firing">Firing</button>
 <button data-s="inactive">Normal</button><button data-s="error">Error</button></div></div>
<div class="rule-stats"><b>{len(rules)} rules:</b> <span class="t-bad">{nf} firing</span>, <span class="t-ok">{nn} normal</span>{f', <span class="t-warn">{ne} error</span>' if ne else ''}</div>
<h3 class="sec-h">Grafana-managed</h3>{html_}</div>"""
    return _shell("Alert rules", body, [("Alerting", "/alerting/list"), "Alert rules"], "alerting", {"page": "alerts"})


def now_s():
    return time.time()


@app.get("/alerting/grafana/<uid>/view")
def alert_view(uid):
    r = next((x for x in eval_rules() if x["uid"] == uid), None)
    if not r:
        return redirect("/alerting/list")
    explore_left = quote(json.dumps({"datasource": r["ds"]["uid"], "queries": [
        {"refId": "A", ("expr" if r["ds"]["type"] == "prometheus" else "rawSql"): r["query"],
         "format": "table" if r["ds"]["type"] == "mysql" else "time_series"}], "range": {"from": "now-1h", "to": "now"}}))
    inst = "".join(
        f'<tr><td><span class="badge {"bad" if i["state"] == "Alerting" else "ok"}">{i["state"]}</span></td>'
        f'<td>{"".join(f"<span class=lbl>{E(k)}={E(v)}</span>" for k, v in i["labels"].items())}</td>'
        f'<td>{round(i["value"], 3)}</td></tr>' for i in r["instances"])
    body = f"""<div class="page">{_page_header(r['title'], E(r['summary']), 'bell',
        f'<a class="btn btn-secondary" href="/explore?left={explore_left}">{ic("compass")} View in Explore</a>')}
<div class="kv"><div><span>State</span><b class="t-{'bad' if r['state'] == 'firing' else 'ok'}">{'Firing' if r['state'] == 'firing' else 'Normal'}</b></div>
<div><span>Folder</span>{E(G.FOLDER_BY_UID[r['folder']]['title'])}</div><div><span>Evaluation group</span>{E(r['group'])} (every {r['interval']})</div>
<div><span>Pending period</span>{r['for']}</div><div><span>Health</span>{r['health']}</div><div><span>Rule UID</span><code>{r['uid']}</code></div></div>
<h3 class="sec-h">Query</h3><div class="muted small">A — {E(G.DS_BY_UID[r['ds']['uid']]['name'])}</div><pre class="code-block">{E(r['query'])}</pre>
<h3 class="sec-h">Expressions</h3><pre class="code-block">B = Reduce(A, Last, Strict)\nC = Threshold(B {E(r['op'])} {r['threshold']})  -- condition</pre>
<h3 class="sec-h">Instances</h3>{_table(['State', 'Labels', 'Value'], []).replace('<tbody></tbody>', '<tbody>' + inst + '</tbody>')}</div>"""
    return _shell(r["title"], body, [("Alerting", "/alerting/list"), ("Alert rules", "/alerting/list"), r["title"]],
                  "alerting")


@app.get("/alerting/notifications")
def contact_points():
    rows = [[f'<b>{E(c["name"])}</b>', f'<span class="badge info">{E(c["type"])}</span>', E(c["settings"]),
             '<span class="muted">Last delivery attempt: ' + ("2 hours ago" if c["type"] == "email" else "4 days ago") + '</span>']
            for c in G.CONTACT_POINTS]
    body = (f'<div class="page">{_page_header("Alerting", "", "bell")}{_tabs(_ALERT_TABS, "/alerting/notifications")}'
            f'<div class="section-note">Choose how to notify your contact points when an alert instance fires</div>'
            f'{_table(["Contact point", "Integration", "Settings", "Health"], rows)}</div>')
    return _shell("Contact points", body, [("Alerting", "/alerting/list"), "Contact points"], "alerting")


@app.get("/alerting/routes")
def routes():
    body = f"""<div class="page">{_page_header("Alerting", "", "bell")}{_tabs(_ALERT_TABS, "/alerting/routes")}
<div class="policy root"><div class="pol-h"><b>Default policy</b><span class="muted small">All alert instances will be handled by the default policy if no other matching policies are found.</span></div>
<div class="pol-b">Delivered to <span class="badge info">NOC e-mail</span> · Grouped by <span class="lbl">grafana_folder</span><span class="lbl">alertname</span> · Timing: group wait 30s, group interval 5m, repeat 4h</div>
<div class="policy"><div class="pol-h"><span class="lbl">severity = critical</span></div><div class="pol-b">Delivered to <span class="badge info">Telegram NOC</span> · continue matching · repeat 1h</div></div>
<div class="policy"><div class="pol-h"><span class="lbl">team = ecom</span></div><div class="pol-b">Delivered to <span class="badge info">E-commerce on-call</span> · Inherited timing</div></div>
<div class="policy"><div class="pol-h"><span class="lbl">team =~ infra|noc</span></div><div class="pol-b">Delivered to <span class="badge info">NOC e-mail</span> · Mute timings: <span class="lbl">sat-night-maintenance</span></div></div>
</div></div>"""
    return _shell("Notification policies", body, [("Alerting", "/alerting/list"), "Notification policies"], "alerting")


@app.get("/alerting/silences")
def silences():
    body = (f'<div class="page">{_page_header("Alerting", "", "bell")}{_tabs(_ALERT_TABS, "/alerting/silences")}'
            f'<div class="empty-state">{ic("bell", 48)}<h2>You haven\'t created any silences yet</h2>'
            f'<p class="muted">Silences stop notifications from being sent for a period of time.</p></div>'
            f'<h3 class="sec-h">Expired silences</h3>'
            + _table(["State", "Matching labels", "Alerts", "Period", "Created by"], [
                ['<span class="badge">Expired</span>', '<span class="lbl">instance=sp-web-p01</span>', "0",
                 "2026-09-27 01:00 — 2026-09-27 05:00", "d.kovalenko"],
                ['<span class="badge">Expired</span>', '<span class="lbl">alertname=Zabbix agent unreachable</span>'
                 '<span class="lbl">metric=bkp-atman</span>', "0", "2026-09-14 22:00 — 2026-09-15 08:00",
                 "i.bondarenko"]]) + "</div>")
    return _shell("Silences", body, [("Alerting", "/alerting/list"), "Silences"], "alerting")


# ------------------------------------------------------------- connections
_DS_LOGO = {"mysql": ("#00758f", "My"), "prometheus": ("#e6522c", "P"),
            "alexanderzobnin-zabbix-datasource": ("#d40000", "Z"), "grafana-testdata-datasource": ("#f5a623", "T"),
            "postgres": ("#336791", "Pg"), "loki": ("#f2cc0c", "L"), "elasticsearch": ("#00bfb3", "E")}


def _dslogo(t, size=40):
    c, txt = _DS_LOGO.get(t, ("#555", "?"))
    return (f'<span class="ds-logo" style="width:{size}px;height:{size}px;background:{c};font-size:{size * .38:.0f}px">'
            f'{txt}</span>')


@app.get("/connections")
@app.get("/datasources")
def connections_root():
    return redirect("/connections/datasources")


@app.get("/connections/datasources")
def ds_list():
    cards = ""
    for d in G.DATASOURCES:
        cards += (f'<a class="ds-card" href="/connections/datasources/edit/{d["uid"]}">{_dslogo(d["type"])}'
                  f'<div><div class="ds-name">{E(d["name"])}{" <span class=badge>default</span>" if d["isDefault"] else ""}</div>'
                  f'<div class="muted small">{E(d["typeName"])} | {E(d["url"] or "—")}</div></div>'
                  f'<div class="tb-spacer"></div><span class="btn btn-secondary btn-sm" '
                  f'onclick="event.preventDefault();location.href=\'/explore?left=\'+encodeURIComponent(JSON.stringify({{datasource:\'{d["uid"]}\'}}))">Explore</span></a>')
    body = (f'<div class="page">{_page_header("Data sources", "View and manage your connected data source connections", "db", "<a class=\"btn btn-primary\" href=\"/connections/datasources/new\">" + ic("plus") + " Add new data source</a>")}'
            f'<div class="browse-filters"><div class="input-icon">{ic("search")}<input id="dsSearch" placeholder="Search by name or type"></div></div>'
            f'<div class="ds-cards">{cards}</div></div>')
    return _shell("Data sources", body, [("Connections", "/connections"), "Data sources"], "connections", {"page": "dslist"})


@app.get("/connections/datasources/new")
@app.get("/connections/add-new-connection")
def ds_new():
    types = [("prometheus", "Prometheus", "Time series databases"), ("loki", "Loki", "Logging & document databases"),
             ("elasticsearch", "Elasticsearch", "Logging & document databases"), ("mysql", "MySQL", "SQL"),
             ("postgres", "PostgreSQL", "SQL"), ("alexanderzobnin-zabbix-datasource", "Zabbix", "Plugins"),
             ("grafana-testdata-datasource", "TestData", "Others")]
    cards = "".join(f'<div class="ds-card add" data-add="{t}">{_dslogo(t)}<div><div class="ds-name">{n}</div>'
                    f'<div class="muted small">{c}</div></div></div>' for t, n, c in types)
    body = (f'<div class="page">{_page_header("Add data source", "Choose a data source type")}'
            f'<div class="browse-filters"><div class="input-icon">{ic("search")}<input placeholder="Filter by name or type"></div></div>'
            f'<div class="ds-cards">{cards}</div></div>')
    return _shell("Add data source", body, [("Connections", "/connections"), ("Data sources", "/connections/datasources"),
                                            "Add data source"], "connections", {"page": "dsnew"})


@app.get("/connections/datasources/edit/<uid>")
@app.get("/datasources/edit/<uid>")
def ds_edit(uid):
    d = G.DS_BY_UID.get(uid) or next((x for x in G.DATASOURCES if str(x["id"]) == uid), None)
    if not d:
        return redirect("/connections/datasources")

    def fld(label, val, help_="", typ="text", disabled=True, ph=""):
        return (f'<div class="field"><label>{E(label)}{f" <span class=help title=\"{E(help_)}\">{ic("info", 13)}</span>" if help_ else ""}</label>'
                f'<input type="{typ}" value="{E(val)}" placeholder="{E(ph)}" {"disabled" if disabled else ""}></div>')

    def secret(label):
        return (f'<div class="field"><label>{E(label)}</label><div class="secret"><input value="configured" disabled>'
                f'<button class="btn btn-secondary btn-sm" type="button" disabled>Reset</button></div></div>')

    def sw(label, on, help_=""):
        return (f'<div class="field inline"><label>{E(label)}</label><span class="switch{" on" if on else ""}"></span>'
                f'{f"<span class=muted small>{E(help_)}</span>" if help_ else ""}</div>')

    jd = d["jsonData"]
    if d["type"] == "mysql":
        form = f"""<h3 class="sec-h">Connection</h3>{fld('Host URL', d['url'], 'MySQL host:port')}{fld('Database name', d['database'])}
<h3 class="sec-h">Authentication</h3>{fld('Username', d['user'])}{secret('Password')}
{sw('Use TLS Client Auth', False)}{sw('With CA Cert', False)}{sw('Skip TLS Verification', True)}
<h3 class="sec-h">Additional settings</h3>{fld('Session timezone', jd.get('timezone') or '', 'Specify the time zone used in the database session', ph='(default)')}
{fld('Max open', jd['maxOpenConns'])}{sw('Auto max idle', jd['maxIdleConnsAuto'])}{fld('Max lifetime', jd['connMaxLifetime'])}
<div class="alert alert-warning">{ic('info')} <div><b>User permission</b><br>The database user should only be granted SELECT permissions on the specified database &amp; tables you want to query. Grafana does not validate that queries are safe so queries can contain any SQL statement. For example, statements like <code>USE otherdb;</code> and <code>DROP TABLE user;</code> would be executed.</div></div>"""
    elif d["type"] == "prometheus":
        form = f"""<h3 class="sec-h">Connection</h3>{fld('Prometheus server URL', d['url'])}
<h3 class="sec-h">Authentication</h3><div class="field"><label>Authentication methods</label><input value="No Authentication" disabled></div>
{sw('Add self-signed certificate', False)}{sw('TLS Client Authentication', False)}{sw('Skip TLS certificate validation', False)}
<h3 class="sec-h">Advanced settings</h3>{fld('Scrape interval', jd['timeInterval'])}{fld('Query timeout', '60s')}{fld('HTTP method', jd['httpMethod'])}
{fld('Prometheus type', jd['prometheusType'])}{fld('Prometheus version', jd['prometheusVersion'])}{fld('Cache level', jd['cacheLevel'])}
{sw('Incremental querying (beta)', False)}{sw('Disable recording rules (beta)', False)}"""
    elif d["type"].startswith("alexanderzobnin"):
        form = f"""<h3 class="sec-h">Connection</h3>{fld('URL', d['url'])}{fld('Access', 'Server (default)')}
<h3 class="sec-h">Zabbix API details</h3>{fld('Auth type', 'User and password')}{fld('Username', jd['username'])}{secret('Password')}
{sw('Trends', jd['trends'])}{fld('After', jd['trendsFrom'])}{fld('Range', jd['trendsRange'])}{fld('Cache TTL', jd['cacheTTL'])}{fld('Timeout', jd['timeout'])}
<h3 class="sec-h">Direct DB Connection</h3>{sw('Enable', jd['dbConnectionEnable'])}{fld('Data Source', jd['dbConnectionDatasourceName'])}
<h3 class="sec-h">Other</h3>{sw('Disable acknowledges for read-only users', jd['disableReadOnlyUsersAck'])}"""
    else:
        form = '<p class="muted">The TestData data source is used to generate fake data for testing panels.</p>'
    prov = ('<div class="alert alert-info">' + ic("info") + ' This data source was added by config and cannot be '
            'modified using the UI. Please contact your server admin to update this data source.</div>') if d["readOnly"] else ""
    tabs = _tabs([("Settings", f"/connections/datasources/edit/{d['uid']}"),
                  ("Dashboards", f"/connections/datasources/edit/{d['uid']}#dashboards")],
                 f"/connections/datasources/edit/{d['uid']}")
    body = f"""<div class="page ds-edit">
<div class="page-header"><div class="ph-title">{_dslogo(d['type'], 48)}<div><h1>{E(d['name'])}</h1>
<div class="ph-sub">Type: {E(d['typeName'])}</div></div></div>
<div class="ph-actions"><a class="btn btn-secondary" href="/explore?left={quote(json.dumps({'datasource': d['uid']}))}">Explore data</a>
<a class="btn btn-secondary" href="/dashboards">Build a dashboard</a></div></div>
{tabs}{prov}
<div class="field"><label>Name</label><div class="row"><input value="{E(d['name'])}" disabled>
<span class="field inline" style="margin:0 0 0 16px"><label>Default</label><span class="switch{' on' if d['isDefault'] else ''}"></span></span></div></div>
{form}
<div id="dsTestResult"></div>
<div class="form-actions"><button class="btn btn-destructive" disabled>Delete</button>
<button class="btn btn-primary" id="dsTest" data-uid="{d['uid']}">{'Test' if d['readOnly'] else 'Save &amp; test'}</button></div>
</div>"""
    return _shell(d["name"], body, [("Connections", "/connections"), ("Data sources", "/connections/datasources"),
                                    d["name"]], "connections", {"page": "dsedit", "uid": d["uid"]})


def ds_health(d):
    if d["type"] == "mysql":
        try:
            sql_exec("SELECT 1")
            return 200, {"status": "OK", "message": "Database Connection OK"}
        except Exception as exc:
            return 400, {"status": "ERROR", "message": f"failed to connect to server - {exc}"}
    if d["type"] == "prometheus":
        return 200, {"status": "OK", "message": "Successfully queried the Prometheus API."}
    if d["type"].startswith("alexanderzobnin"):
        try:
            import requests
            r = requests.get(os.environ.get("ZABBIX_URL", "http://zabbix"), timeout=4)
            if r.status_code < 500:
                return 200, {"status": "OK", "message": "Zabbix API version: 6.0.18, DB connector type: MySQL"}
            return 400, {"status": "ERROR", "message": f"Zabbix API returned HTTP {r.status_code}"}
        except Exception as exc:
            return 400, {"status": "ERROR", "message": f"Post \"{d['url']}\": {exc.__class__.__name__}"}
    return 200, {"status": "OK", "message": "Data source is working"}


# ------------------------------------------------------------------- admin
_USR_TABS = [("Users", "/admin/users"), ("Organization users", "/org/users")]


@app.get("/admin")
def admin_home():
    cards = [("Default preferences", "/org", "Manage preferences across an organization", "cog"),
             ("Settings", "/admin/settings", "View the settings defined in your Grafana config", "doc"),
             ("Organizations", "/admin/orgs", "Isolated instances of Grafana running on the same server", "layers"),
             ("Stats and license", "/admin/stats", "Usage statistics and license information", "info"),
             ("Plugins", "/plugins", "Extend the Grafana experience with plugins", "plug"),
             ("Users", "/admin/users", "Manage users in Grafana", "user"),
             ("Teams", "/org/teams", "Groups of users that have common dashboard and permission needs", "users"),
             ("Service accounts", "/org/serviceaccounts", "Use service accounts to run automated workloads in Grafana",
              "monitor")]
    c = "".join(f'<a class="nav-card" href="{h}">{ic(i, 22)}<div><b>{t}</b><div class="muted small">{s}</div></div></a>'
                for t, h, s, i in cards)
    return _shell("Administration", f'<div class="page">{_page_header("Administration", "Manage server-wide settings and access to resources such as organizations, users, and licenses", "cog")}'
                                    f'<div class="nav-cards">{c}</div></div>', ["Administration"], "admin")


def _ulink(u):
    return f'/admin/users/edit/{u["id"]}'


@app.get("/admin/users")
@app.get("/org/users")
def admin_users():
    rows = []
    for u in G.USERS:
        seen = time.time() - (time.time() - _last_seen(u))
        badges = "".join(f'<span class="badge info">{b}</span>' for b in u["authLabels"])
        rows.append([f'<a href="{_ulink(u)}">{_avatar(u["name"] or u["login"])}</a>',
                     f'<a href="{_ulink(u)}">{E(u["login"])}</a>', f'<a href="{_ulink(u)}">{E(u["email"])}</a>',
                     E(u["name"]), "Main Org." + (" (+1)" if u["id"] in (1, 3) else ""),
                     E(_ago(seen)), (ic("shield", 14, "t-ok") if u["isGrafanaAdmin"] else "") + " " + badges,
                     '<span class="badge ok">Active</span>'])
    org = request.path == "/org/users"
    body = (f'<div class="page">{_page_header("Users", "Manage and create users across the whole Grafana server", "user", "<button class=\"btn btn-primary\" disabled>New user</button>")}'
            f'{_tabs(_USR_TABS, request.path)}<div class="browse-filters"><div class="input-icon">{ic("search")}'
            f'<input id="uSearch" placeholder="Search user by login, email, or name"></div>'
            f'<div class="seg"><button class="on">All users</button><button>Active last 30 days</button></div></div>'
            + _table(["", "Login", "Email", "Name", "Belongs to", "Last active", "Origin", ""], rows, "table users")
            + f'<div class="muted small" style="margin-top:8px">{len(G.USERS)} users · 1 page</div></div>')
    return _shell("Users", body, [("Administration", "/admin"), "Users"], "admin", {"page": "users"})


def _last_seen(u):
    if u["login"] == REUSED_USER:
        return 0
    return u["lastSeen"]


@app.get("/admin/users/edit/<int:uid>")
def admin_user(uid):
    u = next((x for x in G.USERS if x["id"] == uid), None)
    if not u:
        return redirect("/admin/users")
    teams = [t for t in G.TEAMS if uid in t["members"]]
    sess_rows = []
    if u["login"] == REUSED_USER:
        for tok, s in list(_SESSIONS.items())[-10:]:
            sess_rows.append([E(_ago(time.time() - s["seen"])), E(datetime.datetime.fromtimestamp(s["created"]).strftime("%Y-%m-%d %H:%M")),
                              E(s["ip"]), E(_browser(s["ua"])),
                              '<span class="badge">current</span>' if tok == _token() else ""])
    orgs = [["Main Org.", E(u["role"]), ""]]
    if uid in (1, 3):
        orgs.append(["ATB Suppliers", "Viewer", ""])
    ldap = ('<div class="alert alert-info">' + ic("info") + ' This user is synced via LDAP – all changes must be done '
            'in LDAP or mappings.</div>') if "LDAP" in u["authLabels"] else ""
    body = f"""<div class="page">{_page_header(u['name'] or u['login'], '', 'user')}{ldap}
<h3 class="sec-h">User information</h3>{_table(['', ''], [['Name', E(u['name'])], ['Email', E(u['email'])], ['Username', E(u['login'])], ['Password', '******']], 'table kvt')}
<h3 class="sec-h">Permissions</h3>{_table(['', ''], [['Grafana Admin', ('Yes ' + ic('shield', 14, 't-ok')) if u['isGrafanaAdmin'] else 'No']], 'table kvt')}
<h3 class="sec-h">Organizations</h3>{_table(['Name', 'Role', ''], orgs)}
<h3 class="sec-h">Teams</h3>{_table(['Team', 'Email'], [[f'<a href="/org/teams/edit/{t["id"]}/members">{E(t["name"])}</a>', E(t['email'])] for t in teams]) if teams else '<p class="muted">Not a member of any team</p>'}
<h3 class="sec-h">Sessions</h3>{_table(['Last seen', 'Logged on', 'IP address', 'Browser and OS', ''], sess_rows) if sess_rows else '<p class="muted">No active sessions</p>'}
<div class="form-actions"><button class="btn btn-destructive" disabled>Delete user</button><button class="btn btn-secondary" disabled>Disable user</button></div></div>"""
    return _shell(u["login"], body, [("Administration", "/admin"), ("Users", "/admin/users"), u["login"]], "admin")


def _browser(ua):
    ua = ua or ""
    b = "Chrome" if "Chrome" in ua else "Firefox" if "Firefox" in ua else "curl" if "curl" in ua else \
        "Python" if "python" in ua.lower() else "Other"
    o = "Linux" if "Linux" in ua else "Windows" if "Windows" in ua else "macOS" if "Mac" in ua else ""
    return f"{b} {('on ' + o) if o else ''}".strip()


@app.get("/org/teams")
def teams():
    rows = [[_avatar(t["name"]), f'<a href="/org/teams/edit/{t["id"]}/members">{E(t["name"])}</a>', E(t["email"]),
             str(len(t["members"]))] for t in G.TEAMS]
    body = (f'<div class="page">{_page_header("Teams", "Groups of users that have common dashboard and permission needs", "users", "<button class=\"btn btn-primary\" disabled>New Team</button>")}'
            f'<div class="browse-filters"><div class="input-icon">{ic("search")}<input placeholder="Search teams"></div></div>'
            + _table(["", "Name", "Email", "Members"], rows) + "</div>")
    return _shell("Teams", body, [("Administration", "/admin"), "Teams"], "admin")


@app.get("/org/teams/edit/<int:tid>")
@app.get("/org/teams/edit/<int:tid>/<tab>")
def team(tid, tab="members"):
    t = next((x for x in G.TEAMS if x["id"] == tid), None)
    if not t:
        return redirect("/org/teams")
    rows = []
    for m in t["members"]:
        u = next(x for x in G.USERS if x["id"] == m)
        rows.append([_avatar(u["name"] or u["login"]), E(u["login"]), E(u["email"]), E(u["name"]),
                     "Admin" if m == t["members"][0] else "Member"])
    body = (f'<div class="page">{_page_header(t["name"], E(t["email"]), "users")}'
            + _tabs([("Members", f"/org/teams/edit/{tid}/members"), ("Settings", f"/org/teams/edit/{tid}/settings")],
                    f"/org/teams/edit/{tid}/{tab}")
            + (_table(["", "Login", "Email", "Name", "Permission"], rows) if tab == "members" else
               f'<div class="field"><label>Name</label><input value="{E(t["name"])}" disabled></div>'
               f'<div class="field"><label>Email</label><input value="{E(t["email"])}" disabled></div>'
               f'<div class="field"><label>Home dashboard</label><input value="Default" disabled></div>')
            + "</div>")
    return _shell(t["name"], body, [("Administration", "/admin"), ("Teams", "/org/teams"), t["name"]], "admin")


@app.get("/org/serviceaccounts")
def service_accounts():
    rows = [[_avatar(s["name"]), f'<b>{E(s["name"])}</b>', E(s["login"]), E(s["role"]),
             f'{s["tokens"]} token{"s" if s["tokens"] != 1 else ""}',
             '<span class="badge">Disabled</span>' if s["isDisabled"] else '<span class="badge ok">Active</span>']
            for s in G.SERVICE_ACCOUNTS]
    body = (f'<div class="page">{_page_header("Service accounts", "Use service accounts to run automated workloads in Grafana", "monitor", "<button class=\"btn btn-primary\" disabled>Add service account</button>")}'
            + _table(["", "Account", "ID", "Roles", "Tokens", ""], rows) + "</div>")
    return _shell("Service accounts", body, [("Administration", "/admin"), "Service accounts"], "admin")


@app.get("/admin/orgs")
def orgs():
    rows = [[str(o["id"]), f'<a href="/admin/orgs/edit/{o["id"]}">{E(o["name"])}</a>',
             '<button class="btn btn-destructive btn-xs" disabled>' + ic("trash", 14) + '</button>'] for o in G.ORGS]
    body = (f'<div class="page">{_page_header("Organizations", "Isolated instances of Grafana running on the same server", "layers", "<button class=\"btn btn-primary\" disabled>New org</button>")}'
            + _table(["ID", "Name", ""], rows) + "</div>")
    return _shell("Organizations", body, [("Administration", "/admin"), "Organizations"], "admin")


@app.get("/admin/orgs/edit/<int:oid>")
def org_edit(oid):
    o = next((x for x in G.ORGS if x["id"] == oid), None)
    if not o:
        return redirect("/admin/orgs")
    members = G.USERS if oid == 1 else [u for u in G.USERS if u["id"] in (1, 3)]
    rows = [[E(u["login"]), E(u["email"]), E(u["name"]), E(u["role"] if oid == 1 else "Viewer")] for u in members]
    body = (f'<div class="page">{_page_header(o["name"], "", "layers")}<div class="field"><label>Name</label>'
            f'<input value="{E(o["name"])}" disabled></div><h3 class="sec-h">Organization users</h3>'
            + _table(["Login", "Email", "Name", "Role"], rows) + "</div>")
    return _shell(o["name"], body, [("Administration", "/admin"), ("Organizations", "/admin/orgs"), o["name"]], "admin")


@app.get("/admin/settings")
def settings():
    rows = ""
    for sec, kv in G.SETTINGS.items():
        rows += f'<tr><td class="sec" colspan="2">{E(sec)}</td></tr>'
        for k, v in kv.items():
            rows += f'<tr><td style="padding-left:24px">{E(k)}</td><td><code>{E(v)}</code></td></tr>'
    body = (f'<div class="page">{_page_header("Settings", "View the settings defined in your Grafana config", "doc")}'
            f'<div class="alert alert-info">{ic("info")} These system settings are defined in grafana.ini or custom.ini '
            f'(or overridden in ENV variables). To change these you currently need to restart Grafana.</div>'
            f'<table class="table settings"><tbody>{rows}</tbody></table></div>')
    return _shell("Settings", body, [("Administration", "/admin"), "Settings"], "admin")


def _stats():
    return {"dashboards": len(G.DASHBOARDS), "folders": len(G.FOLDERS), "users": len(G.USERS),
            "admins": sum(u["role"] == "Admin" for u in G.USERS), "editors": sum(u["role"] == "Editor" for u in G.USERS),
            "viewers": sum(u["role"] == "Viewer" for u in G.USERS), "orgs": len(G.ORGS),
            "playlists": len(G.PLAYLISTS), "snapshots": 0, "tags": len({t for d in G.DASHBOARDS for t in d["tags"]}),
            "starred": len((_sess() or {}).get("stars", [])), "alerts": len(G.ALERT_RULES),
            "datasources": len(G.DATASOURCES), "activeUsers": 4, "activeSessions": len(_SESSIONS),
            "dailyActiveUsers": 3, "monthlyActiveUsers": 7, "stars": 9, "libraryPanels": 0}


@app.get("/admin/stats")
def stats():
    st = _stats()
    cards = [("Total dashboards", st["dashboards"]), ("Total users", st["users"]), ("Active users (last 30 days)", st["monthlyActiveUsers"]),
             ("Active sessions", st["activeSessions"]), ("Total data sources", st["datasources"]), ("Total alert rules", st["alerts"]),
             ("Total folders", st["folders"]), ("Total playlists", st["playlists"]), ("Total snapshots", 0),
             ("Total tags", st["tags"]), ("Total orgs", st["orgs"]), ("Library panels", 0)]
    c = "".join(f'<div class="stat-card"><div class="muted small">{E(k)}</div><div class="big">{v}</div></div>' for k, v in cards)
    body = (f'<div class="page">{_page_header("Stats and license", "Usage statistics and license information", "info")}'
            f'<div class="stat-cards">{c}</div><h3 class="sec-h">License</h3>'
            f'<div class="card"><b>Open Source</b><p class="muted small">Grafana v{G.VERSION} ({G.COMMIT}) — AGPLv3. '
            f'There is no enterprise license installed.</p></div></div>')
    return _shell("Stats and license", body, [("Administration", "/admin"), "Stats and license"], "admin")


@app.get("/plugins")
def plugins():
    cards = ""
    for pid, name, ptype, ver, author, sig, core, desc in G.PLUGINS:
        badge = '<span class="badge">Core</span>' if core else f'<span class="badge info">{"Signed" if sig == "grafana" else "Community"}</span>'
        cards += (f'<a class="plugin-card" href="/plugins/{pid}" data-type="{ptype}" data-name="{E(name.lower())}">'
                  f'<div class="pc-h">{_dslogo(pid if pid in _DS_LOGO else ptype, 32)}<div><b>{E(name)}</b>'
                  f'<div class="muted small">By {E(author)}</div></div></div>'
                  f'<div class="pc-f">{badge}<span class="muted small">{ptype}</span>'
                  f'<span class="tb-spacer"></span><span class="badge ok">Installed</span></div></a>')
    body = (f'<div class="page">{_page_header("Plugins", "Extend the Grafana experience with panel plugins and apps. To find more data sources go to Connections.", "plug")}'
            f'<div class="browse-filters"><div class="input-icon">{ic("search")}<input id="pSearch" placeholder="Search Grafana plugins"></div>'
            f'<select id="pType"><option value="">All types</option><option value="datasource">Data sources</option>'
            f'<option value="panel">Panels</option><option value="app">Applications</option></select>'
            f'<div class="seg"><button class="on">Installed</button><button disabled>All</button></div></div>'
            f'<div class="plugin-cards">{cards}</div></div>')
    return _shell("Plugins", body, [("Administration", "/admin"), "Plugins"], "admin", {"page": "plugins"})


@app.get("/plugins/<pid>")
def plugin(pid):
    p = next((x for x in G.PLUGINS if x[0] == pid), None)
    if not p:
        return redirect("/plugins")
    pid, name, ptype, ver, author, sig, core, desc = p
    extra = ""
    if pid == "alexanderzobnin-zabbix-app":
        extra = ('<h3 class="sec-h">Configuration</h3><p>App is <b>enabled</b>. Included: Zabbix data source, '
                 'Problems panel, dashboards "Zabbix System Status", "Zabbix Server Dashboard".</p>')
    body = f"""<div class="page">{_page_header(name, f'By {E(author)} | {E(ver)} | {ptype}', None,
        '<span class="badge ok">Installed</span>' + (' <button class="btn btn-destructive" disabled>Uninstall</button>' if not core else ''))}
<div class="plugin-detail"><div><h3 class="sec-h">Overview</h3><p>{E(desc)}.</p>{extra}</div>
<div class="kv side"><div><span>Version</span>{E(ver)}</div><div><span>Signature</span>{'Core' if core else sig}</div>
<div><span>Plugin ID</span><code>{pid}</code></div><div><span>Dependencies</span>Grafana &gt;=9.0.0</div></div></div></div>"""
    return _shell(name, body, [("Administration", "/admin"), ("Plugins", "/plugins"), name], "admin")


@app.route("/org", methods=["GET"])
def org_prefs():
    body = f"""<div class="page">{_page_header('Default preferences', 'Manage preferences across an organization', 'cog')}
<div class="field"><label>Organization name</label><input value="Main Org." disabled></div>
<h3 class="sec-h">Preferences</h3>
<div class="field"><label>Interface theme</label><div class="seg"><button>Default</button><button class="on">Dark</button><button>Light</button></div></div>
<div class="field"><label>Home Dashboard</label><input value="General/ATB NOC — Home" disabled></div>
<div class="field"><label>Timezone</label><input value="Europe/Kyiv" disabled></div>
<div class="field"><label>Week start</label><input value="Monday" disabled></div>
<div class="form-actions"><button class="btn btn-primary" disabled>Save</button></div></div>"""
    return _shell("Default preferences", body, [("Administration", "/admin"), "Default preferences"], "admin")


@app.get("/profile")
def profile():
    s = _sess()
    p = s["prefs"]
    dash_opts = "".join(f'<option value="{d["uid"]}" {"selected" if p.get("homeDashboardUID") == d["uid"] else ""}>'
                        f'{E(d["title"])}</option>' for d in G.DASHBOARDS)
    sess_rows = [[E(_ago(time.time() - x["seen"])), E(datetime.datetime.fromtimestamp(x["created"]).strftime("%Y-%m-%d %H:%M")),
                  E(x["ip"]), E(_browser(x["ua"])), '<span class="badge">current</span>' if tok == _token() else ""]
                 for tok, x in list(_SESSIONS.items())[-10:]]
    teams = [t for t in G.TEAMS if ME["id"] in t["members"]]

    def seg(name, opts, cur):
        return '<div class="seg" data-pref="' + name + '">' + "".join(
            f'<button type="button" data-v="{v}" class="{"on" if cur == v else ""}">{E(lbl)}</button>' for v, lbl in opts) + "</div>"

    body = f"""<div class="page">{_page_header(ME['name'], '', 'user')}
<div class="alert alert-info">{ic('info')} This user is synced via LDAP – all changes must be done in LDAP or mappings.</div>
<h3 class="sec-h">Edit profile</h3>
<div class="field"><label>Name {ic('lock', 13)}</label><input value="{E(ME['name'])}" disabled></div>
<div class="field"><label>Email {ic('lock', 13)}</label><input value="{E(ME['email'])}" disabled></div>
<div class="field"><label>Username {ic('lock', 13)}</label><input value="{E(ME['login'])}" disabled></div>
<h3 class="sec-h">Preferences</h3>
<form id="prefsForm">
<div class="field"><label>Interface theme</label>{seg('theme', [('dark', 'Dark'), ('light', 'Light')], p['theme'])}</div>
<div class="field"><label>Home Dashboard</label><select name="homeDashboardUID"><option value="">Default</option>{dash_opts}</select></div>
<div class="field"><label>Timezone</label><select name="timezone">{''.join(f'<option value="{v}" {"selected" if p["timezone"] == v else ""}>{l}</option>' for v, l in [('browser', 'Browser Time'), ('utc', 'Coordinated Universal Time'), ('Europe/Kyiv', 'Europe/Kyiv')])}</select></div>
<div class="field"><label>Week start</label><select name="weekStart">{''.join(f'<option value="{v}" {"selected" if p["weekStart"] == v else ""}>{l}</option>' for v, l in [('', 'Default'), ('monday', 'Monday'), ('sunday', 'Sunday')])}</select></div>
<div class="field"><label>Language</label><select name="language"><option>English</option><option disabled>Українська (coming soon)</option></select></div>
<div class="form-actions"><button class="btn btn-primary" type="submit">Save</button></div></form>
<h3 class="sec-h">Organizations</h3>{_table(['Name', 'Role', ''], [['Main Org.', ME['role'], '<span class="badge">Current</span>']])}
<h3 class="sec-h">Teams</h3>{_table(['', 'Name', 'Email', 'Members'], [[_avatar(t['name']), E(t['name']), E(t['email']), str(len(t['members']))] for t in teams])}
<h3 class="sec-h">Sessions</h3>{_table(['Last seen', 'Logged on', 'IP address', 'Browser and OS', ''], sess_rows)}
</div>"""
    return _shell("Profile", body, ["Profile"], "", {"page": "profile"})


@app.route("/profile/password", methods=["GET", "POST"])
def change_password():
    msg = ""
    if request.method == "POST":
        msg = ('<div class="alert alert-error">' + ic("info") + ' Cannot change password: user is synced via LDAP. '
               'Use the AD self-service portal.</div>')
    body = f"""<div class="page">{_page_header('Change your password', '', 'lock')}{msg}
<div class="alert alert-info">{ic('info')} You cannot change password when signed in with LDAP or auth proxy.</div>
<form method="post"><div class="field"><label>Old password</label><input type="password" name="oldPassword"></div>
<div class="field"><label>New password</label><input type="password" name="newPassword"></div>
<div class="field"><label>Confirm password</label><input type="password" name="confirmNew"></div>
<div class="form-actions"><button class="btn btn-primary" type="submit">Change Password</button><a class="btn btn-secondary" href="/profile">Cancel</a></div></form></div>"""
    return _shell("Change password", body, [("Profile", "/profile"), "Change password"], "")


@app.get("/profile/notifications")
def notif_history():
    rules = eval_rules()
    rows = []
    for r in rules:
        for i in r["instances"]:
            if i["state"] == "Alerting":
                rows.append(['<span class="badge bad">Firing</span>', E(r["title"]),
                             E(", ".join(f"{k}={v}" for k, v in i["labels"].items() if k in ("metric", "instance"))),
                             E(_ago(time.time() - i["activeAt"]) + " ago")])
    body = (f'<div class="page">{_page_header("Notification history", "", "bell")}'
            + (_table(["State", "Rule", "Instance", "When"], rows) if rows else
               '<div class="empty-state"><h2>No notifications</h2></div>') + "</div>")
    return _shell("Notification history", body, [("Profile", "/profile"), "Notification history"], "")


# ===================================================================== API
def _dash_search_hit(d, s):
    f = G.FOLDER_BY_UID.get(d["folderUid"])
    hit = {"id": d["id"], "uid": d["uid"], "title": d["title"], "uri": f"db/{G.slug(d['title'])}",
           "url": G.dash_url(d), "slug": "", "type": "dash-db", "tags": d["tags"],
           "isStarred": d["uid"] in s["stars"], "sortMeta": 0}
    if f:
        hit.update(folderId=f["id"], folderUid=f["uid"], folderTitle=f["title"],
                   folderUrl=f"/dashboards/f/{f['uid']}/{G.slug(f['title'])}")
    return hit


@app.get("/api/search")
def api_search():
    s = _sess()
    q = (request.args.get("query") or "").lower()
    typ = request.args.get("type", "")
    starred = request.args.get("starred") == "true"
    tags = request.args.getlist("tag")
    fuids = request.args.getlist("folderUIDs")
    out = []
    if typ in ("", "dash-folder") and not starred and not tags:
        for f in G.FOLDERS:
            if q in f["title"].lower():
                out.append({"id": f["id"], "uid": f["uid"], "title": f["title"], "uri": f"db/{G.slug(f['title'])}",
                            "url": f"/dashboards/f/{f['uid']}/{G.slug(f['title'])}", "slug": "", "type": "dash-folder",
                            "tags": [], "isStarred": False, "sortMeta": 0})
    if typ in ("", "dash-db"):
        for d in G.DASHBOARDS:
            if q and q not in d["title"].lower():
                continue
            if starred and d["uid"] not in s["stars"]:
                continue
            if tags and not set(tags) <= set(d["tags"]):
                continue
            if fuids and (d["folderUid"] or "general") not in fuids:
                continue
            out.append(_dash_search_hit(d, s))
    lim = int(request.args.get("limit") or 1000)
    return jsonify(out[:lim])


@app.get("/api/dashboards/uid/<uid>")
def api_dash(uid):
    d = G.DASH_BY_UID.get(uid)
    if not d:
        return jsonify({"message": "Dashboard not found"}), 404
    s = _sess()
    f = G.FOLDER_BY_UID.get(d["folderUid"])
    return jsonify({"meta": {"type": "db", "canSave": False, "canEdit": False, "canAdmin": True, "canStar": True,
                             "canDelete": False, "slug": G.slug(d["title"]), "url": G.dash_url(d),
                             "expires": "0001-01-01T00:00:00Z", "created": "2023-02-14T09:12:44Z",
                             "updated": "2026-08-21T13:05:10Z", "updatedBy": "Anonymous", "createdBy": "Anonymous",
                             "version": d["version"], "hasAcl": False, "isFolder": False,
                             "folderId": f["id"] if f else 0, "folderUid": f["uid"] if f else "",
                             "folderTitle": f["title"] if f else "General",
                             "folderUrl": f"/dashboards/f/{f['uid']}/{G.slug(f['title'])}" if f else "",
                             "provisioned": True, "provisionedExternalId": f"{uid}.json",
                             "isStarred": uid in s["stars"],
                             "annotationsPermissions": {"dashboard": {"canAdd": False, "canEdit": False, "canDelete": False},
                                                        "organization": {"canAdd": False, "canEdit": False, "canDelete": False}}},
                    "dashboard": {k: v for k, v in d.items() if k != "folderUid"}})


@app.get("/api/dashboards/home")
def api_dash_home():
    return api_dash(_sess()["prefs"].get("homeDashboardUID") or G.HOME_UID)


@app.route("/api/dashboards/db", methods=["POST"])
@app.route("/api/dashboards/uid/<uid>", methods=["DELETE"])
def api_dash_save(uid=None):
    return jsonify({"message": "Cannot save provisioned dashboard", "status": "provisioned-dashboard"}), 400


@app.get("/api/dashboards/tags")
def api_tags():
    cnt = {}
    for d in G.DASHBOARDS:
        for t in d["tags"]:
            cnt[t] = cnt.get(t, 0) + 1
    return jsonify([{"term": t, "count": c} for t, c in sorted(cnt.items())])


@app.get("/api/folders")
def api_folders():
    return jsonify([{"id": f["id"], "uid": f["uid"], "title": f["title"]} for f in G.FOLDERS])


@app.get("/api/folders/<uid>")
def api_folder(uid):
    f = G.FOLDER_BY_UID.get(uid)
    if not f:
        return jsonify({"message": "folder not found"}), 404
    return jsonify({"id": f["id"], "uid": f["uid"], "title": f["title"],
                    "url": f"/dashboards/f/{f['uid']}/{G.slug(f['title'])}", "hasAcl": False, "canSave": True,
                    "canEdit": True, "canAdmin": True, "canDelete": True, "createdBy": "Anonymous",
                    "created": "2023-02-14T09:12:44Z", "updatedBy": "Anonymous", "updated": "2023-02-14T09:12:44Z",
                    "version": 1})


def _ds_json(d):
    out = {k: v for k, v in d.items() if k not in ("typeName",)}
    out.update(typeLogoUrl=f"public/app/plugins/datasource/{d['type']}/img/logo.svg", withCredentials=False,
               basicAuthUser="", secureJsonFields=d["secureJsonFields"], version=1)
    return out


@app.get("/api/datasources")
def api_datasources():
    return jsonify([{k: v for k, v in _ds_json(d).items() if k not in ("secureJsonFields", "version", "withCredentials")}
                    for d in G.DATASOURCES])


@app.get("/api/datasources/uid/<uid>")
@app.get("/api/datasources/<int:did>")
@app.get("/api/datasources/name/<name>")
def api_datasource(uid=None, did=None, name=None):
    d = (G.DS_BY_UID.get(uid) if uid else next((x for x in G.DATASOURCES if x["id"] == did), None) if did
         else G.DS_BY_NAME.get(name))
    if not d:
        return jsonify({"message": "Data source not found"}), 404
    return jsonify(_ds_json(d))


@app.get("/api/datasources/id/<name>")
def api_datasource_id(name):
    d = G.DS_BY_NAME.get(name)
    return (jsonify({"id": d["id"]}) if d else (jsonify({"message": "Data source not found"}), 404))


@app.route("/api/datasources/uid/<uid>", methods=["PUT", "DELETE"])
@app.route("/api/datasources/<int:did>", methods=["PUT", "DELETE"])
@app.route("/api/datasources", methods=["POST"])
def api_datasource_write(uid=None, did=None):
    return jsonify({"message": "Cannot modify provisioned data source", "traceID": ""}), 403


@app.get("/api/datasources/uid/<uid>/health")
@app.get("/api/datasources/<int:did>/health")
def api_ds_health(uid=None, did=None):
    d = G.DS_BY_UID.get(uid) if uid else next((x for x in G.DATASOURCES if x["id"] == did), None)
    if not d:
        return jsonify({"message": "Data source not found"}), 404
    code, body = ds_health(d)
    return jsonify(body), code


@app.get("/api/datasources/uid/<uid>/resources/<path:rest>")
@app.get("/api/datasources/proxy/uid/<uid>/<path:rest>")
def api_ds_resources(uid, rest):
    if uid != "prom-prod":
        return jsonify({"message": "not found"}), 404
    if rest.endswith("label/__name__/values"):
        return jsonify({"status": "success", "data": M.METRIC_NAMES})
    m = re.search(r"label/([A-Za-z_]\w*)/values$", rest)
    if m:
        return jsonify({"status": "success", "data": sorted({s.labels[m.group(1)] for s in M.CATALOG
                                                            if m.group(1) in s.labels})})
    if rest.endswith("labels"):
        return jsonify({"status": "success", "data": sorted({k for s in M.CATALOG for k in s.labels})})
    if rest.endswith("status/buildinfo"):
        return jsonify({"status": "success", "data": {"version": "2.47.0", "revision": "efa34a5840661c29c2e362efa76bc3a70dccb335"}})
    return jsonify({"status": "error", "errorType": "not_found", "error": "unknown endpoint"}), 404


@app.post("/api/ds/query")
def api_ds_query():
    ip = atblog.client_ip(request)
    body = request.get_json(silent=True) or {}
    known = bool(request.headers.get("X-Dashboard-Uid"))
    res = ds_query(body, ip, audit=True)
    if not known:
        for q in body.get("queries", []):
            dsu = (q.get("datasource") or {}).get("uid") if isinstance(q.get("datasource"), dict) else q.get("datasource")
            txt = q.get("rawSql") or q.get("expr") or ""
            if txt:
                _add_history(dsu or "zbx-mysql", txt)
    code = 200 if all(r.get("status", 200) < 400 for r in res["results"].values()) else 207
    if len(res["results"]) == 1 and code != 200:
        code = list(res["results"].values())[0]["status"]
    return jsonify(res), code


@app.route("/api/query-history", methods=["GET", "POST"])
def api_query_history():
    s = _sess()
    if request.method == "POST":
        b = request.get_json(silent=True) or {}
        for q in b.get("queries", []):
            _add_history(b.get("datasourceUid", "zbx-mysql"), q.get("rawSql") or q.get("expr") or "")
        return jsonify({"result": {"uid": secrets.token_hex(7)}})
    res = [{"uid": f"qh{i}", "datasourceUid": h["ds"], "createdBy": ME["id"], "createdAt": int(h["ts"]),
            "comment": "", "starred": h["starred"],
            "queries": [{"refId": "A", "datasource": {"uid": h["ds"]},
                         ("rawSql" if h["ds"] == "zbx-mysql" else "expr"): h["q"]}]}
           for i, h in enumerate(reversed(s["history"]))]
    return jsonify({"result": {"totalCount": len(res), "queryHistory": res, "page": 1, "perPage": 100}})


@app.get("/api/health")
def api_health():
    return jsonify({"commit": G.COMMIT, "database": "ok", "version": G.VERSION})


@app.get("/api/login/ping")
def api_ping():
    return jsonify({"message": "Logged in"})


def _user_json(u):
    return {"id": u["id"], "email": u["email"], "name": u["name"], "login": u["login"], "theme": "",
            "orgId": 1, "isGrafanaAdmin": u["isGrafanaAdmin"], "isDisabled": False,
            "isExternal": "LDAP" in u["authLabels"], "isExternallySynced": "LDAP" in u["authLabels"],
            "isGrafanaAdminExternallySynced": False, "authLabels": u["authLabels"],
            "updatedAt": "2026-09-30T07:14:02Z", "createdAt": u["created"] + "T10:00:00Z", "avatarUrl": "/avatar/" +
            format(abs(hash(u["email"])) % (16 ** 32), "032x")}


@app.get("/api/user")
def api_user():
    j = _user_json(ME)
    j["theme"] = _sess()["prefs"]["theme"]
    return jsonify(j)


@app.get("/api/user/orgs")
def api_user_orgs():
    return jsonify([{"orgId": 1, "name": "Main Org.", "role": ME["role"]}])


@app.get("/api/user/teams")
def api_user_teams():
    return jsonify([_team_json(t) for t in G.TEAMS if ME["id"] in t["members"]])


@app.route("/api/user/preferences", methods=["GET", "PUT", "PATCH"])
def api_prefs():
    s = _sess()
    if request.method != "GET":
        b = request.get_json(silent=True) or {}
        for k in ("theme", "timezone", "weekStart", "homeDashboardUID", "language"):
            if k in b and isinstance(b[k], str) and len(b[k]) < 64:
                s["prefs"][k] = b[k]
        return jsonify({"message": "Preferences updated"})
    p = dict(s["prefs"])
    p.update(homeDashboardId=0, queryHistory={"homeTab": ""}, navbar={"bookmarkUrls": []})
    return jsonify(p)


@app.route("/api/user/stars/dashboard/uid/<uid>", methods=["POST", "DELETE"])
def api_star(uid):
    s = _sess()
    if uid not in G.DASH_BY_UID:
        return jsonify({"message": "Dashboard not found"}), 404
    if request.method == "POST":
        if uid not in s["stars"]:
            s["stars"].append(uid)
        return jsonify({"message": "Dashboard starred!"})
    s["stars"] = [x for x in s["stars"] if x != uid]
    return jsonify({"message": "Dashboard unstarred"})


@app.get("/api/user/stars")
def api_stars():
    return jsonify(_sess()["stars"])


@app.get("/api/users")
@app.get("/api/users/search")
@app.get("/api/org/users")
def api_users():
    q = (request.args.get("query") or "").lower()
    us = [u for u in G.USERS if q in (u["login"] + u["email"] + u["name"]).lower()]
    if request.path == "/api/org/users":
        return jsonify([{"orgId": 1, "userId": u["id"], "email": u["email"], "name": u["name"], "login": u["login"],
                         "role": u["role"], "lastSeenAt": "", "lastSeenAtAge": _ago(_last_seen(u)),
                         "authLabels": u["authLabels"], "isDisabled": False} for u in us])
    items = [{"id": u["id"], "name": u["name"], "login": u["login"], "email": u["email"],
              "isAdmin": u["isGrafanaAdmin"], "isDisabled": False, "lastSeenAt": "",
              "lastSeenAtAge": _ago(_last_seen(u)), "authLabels": u["authLabels"]} for u in us]
    if request.path == "/api/users/search":
        return jsonify({"totalCount": len(items), "users": items, "page": 1, "perPage": 1000})
    return jsonify(items)


@app.get("/api/users/<int:uid>")
def api_user_id(uid):
    u = next((x for x in G.USERS if x["id"] == uid), None)
    return jsonify(_user_json(u)) if u else (jsonify({"message": "user not found"}), 404)


@app.get("/api/users/lookup")
def api_user_lookup():
    q = request.args.get("loginOrEmail", "")
    u = next((x for x in G.USERS if q in (x["login"], x["email"])), None)
    return jsonify(_user_json(u)) if u else (jsonify({"message": "user not found"}), 404)


def _team_json(t):
    return {"id": t["id"], "uid": f"team{t['id']:03d}", "orgId": 1, "name": t["name"], "email": t["email"],
            "avatarUrl": "", "memberCount": len(t["members"]), "permission": 0}


@app.get("/api/teams/search")
def api_teams():
    q = (request.args.get("query") or request.args.get("name") or "").lower()
    ts = [_team_json(t) for t in G.TEAMS if q in t["name"].lower()]
    return jsonify({"totalCount": len(ts), "teams": ts, "page": 1, "perPage": 1000})


@app.get("/api/teams/<int:tid>/members")
def api_team_members(tid):
    t = next((x for x in G.TEAMS if x["id"] == tid), None)
    if not t:
        return jsonify({"message": "Team not found"}), 404
    return jsonify([{"orgId": 1, "teamId": tid, "userId": m, "email": u["email"], "login": u["login"],
                     "name": u["name"], "permission": 0}
                    for m in t["members"] for u in G.USERS if u["id"] == m])


@app.get("/api/serviceaccounts/search")
def api_sa():
    return jsonify({"totalCount": len(G.SERVICE_ACCOUNTS), "serviceAccounts": [
        dict(s, orgId=1, avatarUrl="", accessControl={}) for s in G.SERVICE_ACCOUNTS], "page": 1, "perPage": 30})


@app.get("/api/org")
def api_org():
    return jsonify({"id": 1, "name": "Main Org.", "address": G.ORGS[0]["address"]})


@app.get("/api/orgs")
def api_orgs():
    return jsonify([{"id": o["id"], "name": o["name"]} for o in G.ORGS])


@app.get("/api/orgs/<int:oid>")
def api_org_id(oid):
    o = next((x for x in G.ORGS if x["id"] == oid), None)
    return jsonify(o) if o else (jsonify({"message": "Organization not found"}), 404)


@app.get("/api/plugins")
def api_plugins():
    typ = request.args.get("type")
    return jsonify([{"name": n, "type": t, "id": pid, "enabled": True, "pinned": False,
                     "info": {"author": {"name": a, "url": ""}, "description": desc, "version": v,
                              "updated": "2023-11-29"}, "latestVersion": v, "hasUpdate": False,
                     "defaultNavUrl": f"/plugins/{pid}", "category": "", "state": "", "signature": "internal" if core else "valid",
                     "signatureType": sig if not core else "", "signatureOrg": a}
                    for pid, n, t, v, a, sig, core, desc in G.PLUGINS if not typ or t == typ])


@app.get("/api/plugins/<pid>/settings")
def api_plugin_settings(pid):
    p = next((x for x in G.PLUGINS if x[0] == pid), None)
    if not p:
        return jsonify({"message": "Plugin not found, no installed plugin with that id"}), 404
    return jsonify({"name": p[1], "type": p[2], "id": pid, "enabled": True, "pinned": pid.endswith("-app"),
                    "info": {"author": {"name": p[4]}, "description": p[7], "version": p[3]},
                    "jsonData": {}, "secureJsonFields": {}})


@app.get("/api/admin/settings")
def api_admin_settings():
    return jsonify(G.SETTINGS)


@app.get("/api/admin/stats")
def api_admin_stats():
    return jsonify(_stats())


@app.get("/api/frontend/settings")
def api_frontend_settings():
    return jsonify({
        "datasources": {d["name"]: {"id": d["id"], "uid": d["uid"], "type": d["type"], "name": d["name"],
                                    "url": f"/api/datasources/proxy/uid/{d['uid']}", "isDefault": d["isDefault"],
                                    "access": "proxy", "readOnly": d["readOnly"],
                                    "meta": {"id": d["type"], "name": d["typeName"]}} for d in G.DATASOURCES},
        "defaultDatasource": "Zabbix DB", "appUrl": "http://grafana.atbmarket.com:3000/", "appSubUrl": "",
        "authProxyEnabled": False, "ldapEnabled": True, "samlEnabled": False, "anonymousEnabled": False,
        "disableLoginForm": False, "allowOrgCreate": False, "alertingEnabled": False,
        "unifiedAlertingEnabled": True, "exploreEnabled": True, "helpEnabled": True,
        "buildInfo": {"version": G.VERSION, "commit": G.COMMIT, "buildstamp": G.BUILD_TS, "edition": "Open Source",
                      "env": "production", "latestVersion": "", "hasUpdate": False, "hideVersion": False},
        "featureToggles": {"publicDashboards": True, "topnav": True, "correlations": True},
        "rendererAvailable": False, "minRefreshInterval": "5s", "liveEnabled": True,
        "licenseInfo": {"expiry": 0, "stateInfo": "", "edition": "Open Source", "enabledFeatures": {}},
    })


@app.get("/api/prometheus/grafana/api/v1/rules")
def api_rules():
    groups = {}
    for r in eval_rules():
        key = (r["folder"], r["group"])
        g = groups.setdefault(key, {"name": r["group"], "file": G.FOLDER_BY_UID[r["folder"]]["title"],
                                    "rules": [], "interval": 60, "lastEvaluation": "", "evaluationTime": 0.01})
        g["rules"].append({"state": r["state"], "name": r["title"], "query": r["query"], "duration": 300,
                           "annotations": {"summary": r["summary"], "__alertId__": r["uid"]},
                           "alerts": [{"labels": i["labels"], "annotations": {"summary": r["summary"]},
                                       "state": i["state"], "activeAt": datetime.datetime.utcfromtimestamp(
                                           i["activeAt"]).strftime("%Y-%m-%dT%H:%M:%SZ"), "value": str(i["value"])}
                                      for i in r["instances"]],
                           "health": r["health"], "lastError": r["lastError"], "type": "alerting",
                           "labels": r["labels"], "uid": r["uid"], "folderUid": r["folder"]})
    return jsonify({"status": "success", "data": {"groups": list(groups.values())}})


@app.get("/api/v1/provisioning/alert-rules")
def api_prov_rules():
    return jsonify([{"uid": r["uid"], "orgID": 1, "folderUID": r["folder"], "ruleGroup": r["group"],
                     "title": r["title"], "condition": "C", "for": r["for"], "labels": r["labels"],
                     "annotations": {"summary": r["summary"]}, "noDataState": "NoData", "execErrState": "Error",
                     "isPaused": False, "provenance": "file",
                     "data": [{"refId": "A", "datasourceUid": r["ds"]["uid"],
                               "model": {("expr" if r["ds"]["type"] == "prometheus" else "rawSql"): r["query"]}},
                              {"refId": "B", "datasourceUid": "__expr__", "model": {"type": "reduce", "reducer": "last"}},
                              {"refId": "C", "datasourceUid": "__expr__",
                               "model": {"type": "threshold", "conditions": [{"evaluator": {
                                   "type": "gt" if r["op"] == ">" else "lt", "params": [r["threshold"]]}}]}}]}
                    for r in G.ALERT_RULES])


@app.get("/api/v1/provisioning/contact-points")
def api_contact_points():
    return jsonify([{"uid": f"cp{i}", "name": c["name"], "type": c["type"], "disableResolveMessage": False,
                     "settings": {"addresses": c["settings"]} if c["type"] == "email" else {"chatid": "-1001738264410"},
                     "provenance": "file"} for i, c in enumerate(G.CONTACT_POINTS)])


@app.get("/api/annotations")
def api_annotations():
    return jsonify([])


@app.get("/api/playlists")
def api_playlists():
    return jsonify([{"id": p["id"], "uid": p["uid"], "name": p["name"], "interval": p["interval"]} for p in G.PLAYLISTS])


@app.route("/api/<path:rest>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def api_404(rest):
    return jsonify({"message": "Not found"}), 404


# ================================================================== static
@app.get("/public/build/<name>")
def public_build(name):
    if name.endswith(".css"):
        return send_from_directory(STATIC, "grafana.css", mimetype="text/css", max_age=3600)
    if name.endswith(".js"):
        return send_from_directory(STATIC, "grafana.js", mimetype="application/javascript", max_age=3600)
    return "", 404


FAV = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" x1="0" y1="1" '
       'x2="0" y2="0"><stop offset="0" stop-color="#fcee1f"/><stop offset="1" stop-color="#f15b2a"/></linearGradient>'
       '</defs><circle cx="32" cy="32" r="26" fill="none" stroke="url(#g)" stroke-width="9"/>'
       '<circle cx="32" cy="32" r="8" fill="url(#g)"/></svg>')


@app.get("/public/img/<name>")
@app.get("/favicon.ico")
def favicon(name=None):
    return Response(FAV, mimetype="image/svg+xml")


@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@app.get("/healthz")
def healthz():
    return "ok", 200


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify({"message": "Not found"}), 404
    if not _logged_in():
        return redirect("/login")
    return _shell("Page not found", f'<div class="page"><div class="empty-state">{ic("search", 48)}'
                                    f'<h2>Page not found</h2><p class="muted">We\'re looking but can\'t seem to find '
                                    f'this page.</p><a class="btn btn-primary" href="/">Go home</a></div></div>',
                  ["Page not found"]), 404


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=3000, threaded=True)
