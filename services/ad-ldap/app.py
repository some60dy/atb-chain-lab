"""Step 8 - DC-MAIN-01.atbmarket.com Active Directory / LDAP (HTTP mock).

The real LDAP wire protocol is intentionally NOT implemented here; a small HTTP
API stands in so the lab can exercise "bind" + "search" behaviour over HTTP.

Valid bind creds were reused from the Moodle leak:
    bind DN:  education@atbmarket.com
    password: Edu003868$
"""
import base64
import html

from flask import (
    Flask, request, jsonify, session, redirect, url_for,
)
import atblog

app = Flask(__name__)
# Lab-only signing key for the browser "directory portal" session cookie.
app.secret_key = "atb-lab-ad-ldap-portal-not-secret"

VALID_DN = "education@atbmarket.com"
VALID_PW = "Edu003868$"

SEARCH_TOTAL = 68250

# ~5 sample directory objects that look like real AD accounts.
SAMPLE = [
    {
        "cn": "Olha Koval",
        "mail": "o.koval@atbmarket.com",
        "sAMAccountName": "o.koval",
        "memberOf": [
            "CN=Domain Users,CN=Users,DC=atbmarket,DC=com",
            "CN=Finance,OU=Groups,DC=atbmarket,DC=com",
        ],
        "objectSid": "S-1-5-21-3623811015-3361044348-30300820-1104",
        "department": "Finance",
    },
    {
        "cn": "Andriy Bondarenko",
        "mail": "a.bondarenko@atbmarket.com",
        "sAMAccountName": "a.bondarenko",
        "memberOf": [
            "CN=Domain Users,CN=Users,DC=atbmarket,DC=com",
            "CN=IT Admins,OU=Groups,DC=atbmarket,DC=com",
            "CN=Domain Admins,CN=Users,DC=atbmarket,DC=com",
        ],
        "objectSid": "S-1-5-21-3623811015-3361044348-30300820-512",
        "department": "IT",
    },
    {
        "cn": "Iryna Tkachenko",
        "mail": "i.tkachenko@atbmarket.com",
        "sAMAccountName": "i.tkachenko",
        "memberOf": [
            "CN=Domain Users,CN=Users,DC=atbmarket,DC=com",
            "CN=HR,OU=Groups,DC=atbmarket,DC=com",
        ],
        "objectSid": "S-1-5-21-3623811015-3361044348-30300820-2087",
        "department": "Human Resources",
    },
    {
        "cn": "Serhii Melnyk",
        "mail": "s.melnyk@atbmarket.com",
        "sAMAccountName": "s.melnyk",
        "memberOf": [
            "CN=Domain Users,CN=Users,DC=atbmarket,DC=com",
            "CN=Logistics,OU=Groups,DC=atbmarket,DC=com",
        ],
        "objectSid": "S-1-5-21-3623811015-3361044348-30300820-3391",
        "department": "Logistics",
    },
    {
        "cn": "Education Service",
        "mail": "education@atbmarket.com",
        "sAMAccountName": "education",
        "memberOf": [
            "CN=Domain Users,CN=Users,DC=atbmarket,DC=com",
            "CN=Service Accounts,OU=Groups,DC=atbmarket,DC=com",
        ],
        "objectSid": "S-1-5-21-3623811015-3361044348-30300820-1337",
        "department": "Service Accounts",
    },
]


def _basic_creds(hdr):
    """Return (user, pw) from an Authorization: Basic header, or None."""
    if not hdr or not hdr.startswith("Basic "):
        return None
    try:
        raw = base64.b64decode(hdr.split(" ", 1)[1]).decode("utf-8", "replace")
        user, _, pw = raw.partition(":")
        return user, pw
    except Exception:
        return None


def _submitted_creds():
    """Pull (bind_dn, password) from form, json, or Basic auth header."""
    body = request.get_json(silent=True) or {}
    form = request.form or {}
    bind_dn = (
        form.get("bind_dn") or form.get("user")
        or body.get("bind_dn") or body.get("user")
    )
    password = form.get("password") or body.get("password")
    if bind_dn is None or password is None:
        creds = _basic_creds(request.headers.get("Authorization", ""))
        if creds:
            bind_dn = bind_dn if bind_dn is not None else creds[0]
            password = password if password is not None else creds[1]
    return bind_dn or "", password or ""


def _is_valid(bind_dn, password):
    return bind_dn == VALID_DN and password == VALID_PW


# ---------------------------------------------------------------------------
# Clickable "directory portal" browser UI (wraps the same bind/search logic).
# ---------------------------------------------------------------------------

_PAGE_CSS = """
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #eef1f5; color: #1f2733;
  }
  .topbar {
    background: #0b3d66; color: #fff; padding: 14px 20px;
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 8px;
  }
  .topbar .brand { font-weight: 600; font-size: 18px; letter-spacing: .3px; }
  .topbar .brand small { display: block; font-weight: 400; opacity: .8;
    font-size: 12px; }
  .topbar a { color: #cfe3f5; text-decoration: none; font-size: 14px; }
  .topbar a:hover { text-decoration: underline; }
  .wrap { max-width: 860px; margin: 0 auto; padding: 20px 16px 48px; }
  .card {
    background: #fff; border: 1px solid #d7dde6; border-radius: 8px;
    padding: 20px; margin: 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,.06);
  }
  h1 { font-size: 20px; margin: 0 0 4px; }
  h2 { font-size: 16px; margin: 0 0 12px; color: #0b3d66; }
  label { display: block; font-size: 13px; font-weight: 600; margin: 12px 0 4px; }
  input[type=text], input[type=password] {
    width: 100%; padding: 10px 12px; border: 1px solid #b9c2cf;
    border-radius: 6px; font-size: 14px; background: #fff; color: #1f2733;
  }
  button {
    margin-top: 16px; background: #0b3d66; color: #fff; border: none;
    padding: 11px 18px; border-radius: 6px; font-size: 14px; cursor: pointer;
  }
  button:hover { background: #0d4b7f; }
  .hint { font-size: 12px; color: #6b7684; margin-top: 10px; }
  .err { background: #fdecea; border: 1px solid #f5c6c2; color: #a3221b;
    padding: 10px 12px; border-radius: 6px; font-size: 14px; margin-bottom: 8px; }
  .searchbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-end; }
  .searchbar .grow { flex: 1 1 240px; }
  .searchbar button { margin-top: 0; }
  .total { font-size: 13px; color: #6b7684; margin: 4px 0 0; }
  table { width: 100%; border-collapse: collapse; margin-top: 4px; }
  th, td { text-align: left; padding: 10px 12px; font-size: 14px;
    border-bottom: 1px solid #edf0f4; }
  th { font-size: 12px; text-transform: uppercase; letter-spacing: .4px;
    color: #6b7684; }
  tr.row:hover { background: #f3f7fc; }
  tr.row td a { color: #0b3d66; text-decoration: none; font-weight: 600; }
  tr.row td a:hover { text-decoration: underline; }
  .attrs { list-style: none; padding: 0; margin: 0; }
  .attrs li { padding: 8px 0; border-bottom: 1px solid #edf0f4;
    display: flex; flex-wrap: wrap; gap: 6px; }
  .attrs .k { flex: 0 0 150px; font-weight: 600; color: #6b7684;
    font-size: 13px; }
  .attrs .v { flex: 1 1 200px; font-size: 14px; word-break: break-word; }
  .back { display: inline-block; margin-bottom: 8px; font-size: 14px;
    color: #0b3d66; text-decoration: none; }
  .back:hover { text-decoration: underline; }
"""


def _page(title, body, authed=False):
    nav = (
        '<a href="/directory">Directory</a> &nbsp; <a href="/signout">Sign out</a>'
        if authed else ""
    )
    return (
        "<!doctype html><html lang=\"en\"><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)}</title>"
        f"<style>{_PAGE_CSS}</style></head><body>"
        "<div class=\"topbar\"><div class=\"brand\">ATBMARKET Directory"
        "<small>DC-MAIN-01 &middot; Active Directory</small></div>"
        f"<div>{nav}</div></div>"
        f"<div class=\"wrap\">{body}</div></body></html>"
    )


def _authed():
    return session.get("bind_dn") == VALID_DN


@app.get("/")
def index():
    if _authed():
        return redirect(url_for("directory"))
    err = request.args.get("err")
    err_html = (
        '<div class="err">Invalid credentials (49). Check the bind DN and '
        'password.</div>' if err else ""
    )
    body = (
        '<div class="card">'
        "<h1>Sign in</h1>"
        '<h2>LDAP bind &mdash; atbmarket.com</h2>'
        f"{err_html}"
        '<form method="post" action="/login">'
        '<label for="bind_dn">Bind DN</label>'
        '<input type="text" id="bind_dn" name="bind_dn" '
        'placeholder="user@atbmarket.com" autocomplete="username" autofocus>'
        '<label for="password">Password</label>'
        '<input type="password" id="password" name="password" '
        'autocomplete="current-password">'
        "<button type=\"submit\">Bind &amp; sign in</button>"
        '<p class="hint">Authenticate with a valid directory account to browse '
        "the ATBMARKET address book.</p>"
        "</form></div>"
    )
    return _page("Sign in - ATBMARKET Directory", body)


@app.post("/login")
def login():
    ip = atblog.client_ip(request)
    bind_dn, password = _submitted_creds()
    if _is_valid(bind_dn, password):
        atblog.log("ad.bind_reused_creds", ip, bind_dn=bind_dn,
                   msg="LDAP bind with reused Moodle credentials")
        session["bind_dn"] = VALID_DN
        return redirect(url_for("directory"))
    atblog.log("ad.bind_fail", ip, bind_dn=bind_dn)
    return redirect(url_for("index", err=1))


@app.get("/signout")
def signout():
    session.pop("bind_dn", None)
    return redirect(url_for("index"))


@app.get("/directory")
def directory():
    if not _authed():
        return redirect(url_for("index"))
    ip = atblog.client_ip(request)

    q = (request.args.get("q") or "").strip()
    if q:
        ldap_filter = f"(anr={q})"
        atblog.log("ad.search", ip, filter=ldap_filter, count=SEARCH_TOTAL,
                   msg="LDAP search returned directory")
        ql = q.lower()
        rows = [
            o for o in SAMPLE
            if ql in o["cn"].lower()
            or ql in o["mail"].lower()
            or ql in o["sAMAccountName"].lower()
            or ql in o["department"].lower()
        ]
    else:
        rows = SAMPLE

    search_val = html.escape(q)
    tr = []
    for o in SAMPLE:
        if o not in rows:
            continue
        san = html.escape(o["sAMAccountName"])
        tr.append(
            '<tr class="row">'
            f'<td><a href="/directory/{san}">{html.escape(o["cn"])}</a></td>'
            f'<td>{html.escape(o["mail"])}</td>'
            f'<td>{html.escape(o["department"])}</td>'
            "</tr>"
        )
    if not tr:
        table = '<p class="hint">No sample accounts match that filter.</p>'
    else:
        table = (
            '<table><thead><tr><th>Name</th><th>Email</th>'
            "<th>Department</th></tr></thead><tbody>"
            + "".join(tr) + "</tbody></table>"
        )

    body = (
        '<div class="card">'
        "<h1>Directory</h1>"
        '<h2>Global address list</h2>'
        '<form method="get" action="/directory" class="searchbar">'
        '<div class="grow"><label for="q">Search accounts</label>'
        f'<input type="text" id="q" name="q" value="{search_val}" '
        'placeholder="name, sAMAccountName, department..."></div>'
        "<button type=\"submit\">Search</button>"
        "</form>"
        f'<p class="total">Directory contains <strong>{SEARCH_TOTAL:,}</strong> '
        f"objects. Showing {len(tr)} sample account(s).</p>"
        f"{table}"
        "</div>"
    )
    return _page("Directory - ATBMARKET", body, authed=True)


@app.get("/directory/<sam>")
def directory_entry(sam):
    if not _authed():
        return redirect(url_for("index"))
    obj = next((o for o in SAMPLE if o["sAMAccountName"] == sam), None)
    if obj is None:
        body = (
            '<a class="back" href="/directory">&larr; Back to directory</a>'
            '<div class="card"><h1>Not found</h1>'
            '<p class="hint">No directory object with that sAMAccountName.</p>'
            "</div>"
        )
        return _page("Not found - ATBMARKET", body, authed=True), 404

    member_of = "<br>".join(html.escape(g) for g in obj["memberOf"])
    rows = [
        ("cn", html.escape(obj["cn"])),
        ("mail", html.escape(obj["mail"])),
        ("sAMAccountName", html.escape(obj["sAMAccountName"])),
        ("department", html.escape(obj["department"])),
        ("objectSid", html.escape(obj["objectSid"])),
        ("memberOf", member_of),
    ]
    items = "".join(
        f'<li><span class="k">{k}</span><span class="v">{v}</span></li>'
        for k, v in rows
    )
    body = (
        '<a class="back" href="/directory">&larr; Back to directory</a>'
        '<div class="card">'
        f"<h1>{html.escape(obj['cn'])}</h1>"
        f'<h2>{html.escape(obj["mail"])}</h2>'
        f'<ul class="attrs">{items}</ul>'
        "</div>"
    )
    return _page(f"{obj['cn']} - ATBMARKET", body, authed=True)


@app.post("/bind")
def bind():
    ip = atblog.client_ip(request)
    bind_dn, password = _submitted_creds()
    if _is_valid(bind_dn, password):
        atblog.log("ad.bind_reused_creds", ip, bind_dn=bind_dn,
                   msg="LDAP bind with reused Moodle credentials")
        return jsonify(ok=True, dn=VALID_DN)
    atblog.log("ad.bind_fail", ip, bind_dn=bind_dn)
    return jsonify(ok=False, error="invalid credentials (49)"), 401


@app.route("/search", methods=["GET", "POST"])
def search():
    ip = atblog.client_ip(request)
    bind_dn, password = _submitted_creds()
    if not _is_valid(bind_dn, password):
        atblog.log("ad.search_unauth", ip, bind_dn=bind_dn)
        return jsonify(ok=False, error="invalid credentials (49)"), 401

    ldap_filter = (
        request.values.get("filter")
        or (request.get_json(silent=True) or {}).get("filter")
        or "(objectClass=user)"
    )
    atblog.log("ad.search", ip, filter=ldap_filter, count=SEARCH_TOTAL,
               msg="LDAP search returned directory")
    return jsonify(total=SEARCH_TOTAL, filter=ldap_filter, sample=SAMPLE)


@app.get("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80)
