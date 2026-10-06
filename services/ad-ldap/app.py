"""Step 8 - DC-MAIN-01.atbmarket.com Active Directory / LDAP (HTTP mock).

The real LDAP wire protocol is intentionally NOT implemented here; a small HTTP
API stands in so the lab can exercise "bind" + "search" behaviour over HTTP.

Valid bind creds were reused from the Moodle leak:
    bind DN:  education@atbmarket.com
    password: Edu003868$
"""
import base64

from flask import Flask, request, jsonify
import atblog

app = Flask(__name__)

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


@app.route("/")
def index():
    return (
        "<html><head><title>DC-MAIN-01</title></head>"
        "<body><h1>DC-MAIN-01 (Active Directory)</h1></body></html>"
    )


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
