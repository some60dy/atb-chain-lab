"""Steps 3-5 - supplier.atbmarket.com (SuiteCRM 7.10.25 on sp-web-p01).

Faithfully reproduces the chain in the write-up:
  3. open self-registration -> GeneratePassword (GUID link) -> Changenewpassword
  4. LFI through Import::RefreshMapping (importFile=<path>) reads arbitrary files
     (config.php, config_override.php -> Oracle/RMS/MEDOC creds, /etc/hostname, cmdline)
  5. phar-polyglot PHP deserialization RCE, bypassing a Cloudflare-style WAF that
     only inspects the first ~180 KB of the body (pad with 200 KB of 'A').

Everything runs inside the isolated container; the web-shell executes real
commands as the unprivileged `nginx` user (uid 993) to mirror the report.
"""
import base64
import os
import re
import secrets
import subprocess
import time
import uuid

from flask import Flask, request, Response, send_from_directory
import atblog

app = Flask(__name__)

UPLOAD_DIR = "/app/upload"
WAF_SCAN_LIMIT = 180 * 1024           # Cloudflare WAF inspects ~first 180 KB only
os.makedirs(UPLOAD_DIR, exist_ok=True)

# in-memory "CRM" state
USERS = {}                             # user_name -> {guid, password}
RESET_GUIDS = {}                       # guid -> user_name
SESSIONS = {}                          # PHPSESSID -> user_name


def current_user():
    return SESSIONS.get(request.cookies.get("PHPSESSID", ""))


def html(body, status=200):
    return Response(body, status=status, mimetype="text/html")


# ---------------------------------------------------------------- UI views
# Inline-CSS, offline, mobile-friendly SuiteCRM 7.10.25 look-and-feel.
_BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Helvetica,Arial,sans-serif;color:#2b2f33;
     background:#eef1f4;-webkit-font-smoothing:antialiased}
a{color:#f08377;text-decoration:none}a:hover{text-decoration:underline}
.wm{font-size:30px;font-weight:700;letter-spacing:.5px;color:#fff}
.wm span{color:#f08377}
.muted{color:#8a9199;font-size:13px}
input,select{width:100%;padding:11px 12px;border:1px solid #cfd6dd;border-radius:4px;
     font-size:14px;background:#fff;margin-top:6px}
input:focus,select:focus{outline:none;border-color:#f08377;
     box-shadow:0 0 0 2px rgba(240,131,119,.18)}
label{display:block;font-size:12px;font-weight:600;color:#60666c;
     text-transform:uppercase;letter-spacing:.4px;margin-top:16px}
.btn{display:inline-block;width:100%;margin-top:22px;padding:12px;border:none;
     border-radius:4px;background:#f08377;color:#fff;font-size:15px;font-weight:600;
     cursor:pointer}
.btn:hover{background:#e86f62}
"""

_LOGIN_CSS = _BASE_CSS + """
body{display:flex;align-items:center;justify-content:center;min-height:100vh;
     background:linear-gradient(135deg,#232a31 0%,#2f3a44 100%);padding:16px}
.card{width:100%;max-width:380px;background:#fff;border-radius:8px;
     box-shadow:0 10px 40px rgba(0,0,0,.35);overflow:hidden}
.head{background:#2b333b;padding:28px 32px 24px;text-align:center}
.sub{color:#aeb6bd;font-size:13px;margin-top:6px}
.body{padding:26px 32px 30px}
.foot{text-align:center;padding:16px;border-top:1px solid #eef1f4;
     color:#9aa1a8;font-size:12px}
.reg{text-align:center;margin-top:18px;font-size:13px}
"""


def login_page(error=""):
    err = (f'<div style="color:#c0392b;font-size:13px;margin-top:14px">{error}</div>'
           if error else "")
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SuiteCRM</title><style>{_LOGIN_CSS}</style></head><body>
<div class="card">
  <div class="head">
    <div class="wm">Suite<span>CRM</span></div>
    <div class="sub">ATB Supplier Portal</div>
  </div>
  <div class="body">
    <form method="post" action="/index.php?action=Login">
      <label>User Name</label>
      <input type="text" name="user_name" autocomplete="username" placeholder="user name">
      <label>Password</label>
      <input type="password" name="password" autocomplete="current-password" placeholder="password">
      <button class="btn" type="submit">Log In</button>
      {err}
    </form>
    <div class="reg">New supplier?
      <a href="/index.php?action=Signup">Register as a supplier</a>
    </div>
  </div>
  <div class="foot">SuiteCRM 7.10.25</div>
</div>
</body></html>"""


_PANEL_CSS = _BASE_CSS + """
body{min-height:100vh}
.wrap{display:flex;min-height:100vh}
.side{width:230px;background:#2b333b;color:#cfd6dd;flex-shrink:0}
.side .brand{padding:22px 24px;border-bottom:1px solid #3a434c}
.side .brand .wm{font-size:22px}
.side nav a{display:block;padding:13px 24px;color:#cfd6dd;font-size:14px;
     border-left:3px solid transparent}
.side nav a:hover{background:#333c45;text-decoration:none}
.side nav a.active{background:#333c45;border-left-color:#f08377;color:#fff;font-weight:600}
.main{flex:1;min-width:0}
.top{background:#fff;border-bottom:1px solid #e1e6ea;padding:16px 28px;
     font-size:18px;font-weight:600;color:#2b333b}
.content{padding:28px}
.box{background:#fff;border:1px solid #e1e6ea;border-radius:6px;
     padding:26px;max-width:620px}
.box h2{font-size:16px;margin-bottom:4px}
.hint{color:#8a9199;font-size:13px;margin-bottom:12px}
.resp{margin-top:20px;border:1px solid #e1e6ea;border-radius:6px;background:#fff;
     max-width:620px}
.resp .lbl{padding:10px 14px;border-bottom:1px solid #e1e6ea;font-size:12px;
     font-weight:600;color:#60666c;text-transform:uppercase;letter-spacing:.4px}
.resp iframe{width:100%;height:220px;border:none}
@media(max-width:720px){.wrap{flex-direction:column}.side{width:100%}
     .side nav{display:flex;flex-wrap:wrap}.side nav a{border-left:none}}
"""


def _panel(title, active, inner):
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SuiteCRM</title><style>{_PANEL_CSS}</style></head><body>
<div class="wrap">
  <aside class="side">
    <div class="brand"><div class="wm">Suite<span>CRM</span></div>
      <div class="muted" style="color:#8a9199;margin-top:4px">ATB Supplier Portal</div></div>
    <nav>
      <a href="/index.php?action=index">Home</a>
      <a href="/index.php?action=Signup">Suppliers</a>
      <a class="{ 'active' if active=='import' else '' }"
         href="/index.php?module=Import&amp;action=index">Import</a>
      <a href="/index.php?action=Logout">Log Out</a>
    </nav>
  </aside>
  <main class="main">
    <div class="top">{title}</div>
    <div class="content">{inner}</div>
  </main>
</div>
</body></html>"""


def signup_page():
    inner = """
    <div class="box">
      <h2>Register as a Supplier</h2>
      <div class="hint">Create a supplier account. A password-reset link
        will be generated for you to set your password.</div>
      <form method="post" target="respframe"
            action="/index.php?entryPoint=GeneratePassword">
        <input type="hidden" name="link" value="0">
        <label>Email / User Name</label>
        <input type="text" name="user_name" placeholder="supplier@example.com" required>
        <button class="btn" type="submit">Register</button>
      </form>
      <div class="hint" style="margin-top:16px">
        Already registered? <a href="/index.php?action=Login">Back to login</a>
      </div>
    </div>
    <div class="resp">
      <div class="lbl">Status</div>
      <iframe name="respframe" title="status"></iframe>
    </div>"""
    return _panel("Supplier Registration", "signup", inner)


def change_password_page(guid, msg=""):
    note = f'<div class="hint" style="margin-top:14px">{msg}</div>' if msg else ""
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SuiteCRM</title><style>{_LOGIN_CSS}</style></head><body>
<div class="card"><div class="head"><div class="wm">Suite<span>CRM</span></div>
<div class="sub">Set your password</div></div><div class="body">
<form method="post" action="/index.php?entryPoint=Changenewpassword&amp;guid={guid}">
  <label>New password</label><input type="password" name="password1" required>
  <label>Confirm password</label><input type="password" name="password2" required>
  <button class="btn" type="submit">Save</button>{note}
</form></div></div></body></html>"""


def import_page():
    inner = """
    <div class="box">
      <h2>Import &amp; Field Mapping</h2>
      <div class="hint">Upload a data file and refresh the import field mapping.</div>
      <form method="post" target="respframe"
            action="/index.php?module=Import&amp;action=RefreshMapping"
            enctype="multipart/form-data">
        <label>Import file / mapping source</label>
        <input type="text" name="importFile" placeholder="/path/to/import.csv">
        <label>Attachment</label>
        <input type="file" name="file">
        <button class="btn" type="submit">Import file / Refresh mapping</button>
      </form>
    </div>
    <div class="resp">
      <div class="lbl">Server response</div>
      <iframe name="respframe" title="server response"></iframe>
    </div>"""
    return _panel("Import", "import", inner)


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
        atblog.log("supplier.self_registration", ip, user=user,
                   msg="unmoderated supplier account created")
        return html("<div>registration complete</div>", 200)

    if entry == "GeneratePassword":
        user = form.get("user_name", "")
        guid = str(uuid.uuid4())
        RESET_GUIDS[guid] = user
        USERS.setdefault(user, {"password": None})["guid"] = guid
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
        USERS[user]["password"] = p1
        RESET_GUIDS.pop(guid, None)
        atblog.log("supplier.password_changed", ip, user=user, guid=guid,
                   msg="account password set via GUID link")
        return html(login_page("Password saved — please log in."), 200)

    if action == "Login" and request.method == "POST":
        user = form.get("user_name", "")
        pw = form.get("password", "")
        if user in USERS and USERS[user].get("password") and USERS[user]["password"] == pw:
            sid = secrets.token_hex(16)
            SESSIONS[sid] = user
            atblog.log("supplier.login", ip, user=user, msg="supplier portal login")
            resp = Response(status=302, headers={"Location": "/index.php?module=Import&action=index"})
            resp.set_cookie("PHPSESSID", sid, httponly=True)
            return resp
        atblog.log("supplier.login_fail", ip, user=user)
        return html(login_page("You must specify a valid username and password."), 401)

    if action == "Logout":
        SESSIONS.pop(request.cookies.get("PHPSESSID", ""), None)
        return html(login_page())

    if module == "Import" and not current_user():
        atblog.log("supplier.unauth_import", ip, action=action)
        return html(login_page("Your session has expired. Please log in."), 401)

    # ----------------------------------------------- step 4/5: Import mapping
    if module == "Import" and action in ("RefreshMapping", "Save"):
        return import_refresh(ip, action)

    # ----------------------------------------- GET-only SuiteCRM UI views
    # These only render for plain GET navigations and never match the
    # exploit's entryPoint / module=Import&action=RefreshMapping|Save branches
    # above, so the chain is unaffected.
    if request.method == "GET":
        if action == "index" and not module and current_user():
            return html(import_page())
        if action == "Login" or (not entry and not module and not action):
            return html(login_page())
        if action == "Signup":
            return html(signup_page())
        if module == "Import" and action == "index":
            return html(import_page())

    return html("<html><title>SuiteCRM</title><body>ATB Supplier Portal</body></html>")


# ------------------------------------------------------ GET /  (login view)
@app.get("/")
def root():
    return html(login_page())


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
    app.run(host="0.0.0.0", port=80, threaded=True)
