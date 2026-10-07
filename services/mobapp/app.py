"""Step 1a - mobapp.atbmarket.com mobile registration API.
Hard-coded Basic creds (reg_user:basic*88password!prod99) recovered from the APK.
"""
import base64
import io
import os
import time
import zipfile

from flask import Flask, request, jsonify, send_file, Response
import atblog

app = Flask(__name__)
REG_USER = "reg_user"
REG_PASS = "basic*88password!prod99"

API_BASE = "https://mobapp.atbmarket.com"
APK_PATH = os.environ.get("ATB_APK_PATH", "/tmp/atb-market.apk")

FAKE_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJyZWciLCJwaG9uZSI6IjM4MCIsImlhdCI6MTcwMH0."
    "S1gn4tur3Pr0dReg1str4t10nT0k3n0000"
)


def _basic_b64():
    return base64.b64encode(f"{REG_USER}:{REG_PASS}".encode()).decode()


def _android_bundle():
    """A React-Native style index.android.bundle that embeds the API base URL and
    the hard-coded Basic creds, so `strings`/`grep` on it reveals the secret -
    reproducing the real decompile-the-APK recon (see docs/apk-recon.md)."""
    b64 = _basic_b64()
    return (
        "// ATB Market - React Native bundle (minified)\n"
        "// __BUNDLE_START__\n"
        "var __DEV__=false;\n"
        "__d(function(g,r,i,a,m,e,d){\n"
        "  'use strict';\n"
        "  // --- generated API client config ---\n"
        '  var API_BASE="' + API_BASE + '";\n'
        '  var REGISTER_PATH="/register/login";\n'
        "  // hard-coded service credential for the registration API\n"
        "  // plaintext basic pair: " + REG_USER + ":" + REG_PASS + "\n"
        '  var AUTH_HEADER="Authorization: Basic ' + b64 + '";\n'
        "  function registerLogin(phoneNumber){\n"
        "    return fetch(API_BASE+REGISTER_PATH,{\n"
        "      method:'POST',\n"
        "      headers:{'Content-Type':'application/json',\n"
        "               'Authorization':'Basic " + b64 + "'},\n"
        "      body:JSON.stringify({phoneNumber:phoneNumber})\n"
        "    });\n"
        "  }\n"
        "  m.exports={registerLogin:registerLogin,API_BASE:API_BASE};\n"
        "},0,[]);\n"
        "// __BUNDLE_END__\n"
    )


def _android_manifest():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android"\n'
        '    package="ua.com.atbmarket" android:versionCode="80048"\n'
        '    android:versionName="8.0.48">\n'
        '  <uses-permission android:name="android.permission.INTERNET"/>\n'
        '  <application android:label="ATB Market" android:allowBackup="true">\n'
        '    <activity android:name=".MainActivity" android:exported="true">\n'
        '      <intent-filter>\n'
        '        <action android:name="android.intent.action.MAIN"/>\n'
        '        <category android:name="android.intent.category.LAUNCHER"/>\n'
        '      </intent-filter>\n'
        '    </activity>\n'
        '  </application>\n'
        '</manifest>\n'
    )


def build_apk(path=APK_PATH):
    """Build the downloadable 'APK' (really a ZIP) once, containing a readable
    assets/index.android.bundle with the embedded creds + a minimal manifest."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("AndroidManifest.xml", _android_manifest())
        zf.writestr("assets/index.android.bundle", _android_bundle())
        zf.writestr(
            "META-INF/MANIFEST.MF",
            "Manifest-Version: 1.0\r\nCreated-By: ATB Mobile Build\r\n\r\n",
        )
        zf.writestr(
            "resources.arsc",
            "ATB Market resource table (lab stub)\n",
        )
    return path


def _check_basic(hdr):
    if not hdr or not hdr.startswith("Basic "):
        return None
    try:
        raw = base64.b64decode(hdr.split(" ", 1)[1]).decode("utf-8", "replace")
        user, _, pw = raw.partition(":")
        return user, pw
    except Exception:
        return None


@app.get("/")
def index():
    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ATB Market - Mobile App</title>
<style>
  :root { --atb-red:#e2001a; --atb-dark:#1c1c1c; --bg:#f4f5f7; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
         background:var(--bg); color:var(--atb-dark); line-height:1.5; }
  header { background:var(--atb-red); color:#fff; padding:18px 16px; text-align:center; }
  header .logo { font-size:26px; font-weight:800; letter-spacing:1px; }
  header .tag { font-size:13px; opacity:.9; }
  .wrap { max-width:430px; margin:0 auto; padding:16px; }
  .hero { background:#fff; border-radius:16px; padding:22px 18px; margin-top:16px;
          box-shadow:0 4px 18px rgba(0,0,0,.08); text-align:center; }
  .phone { font-size:54px; line-height:1; }
  .hero h1 { font-size:22px; margin:12px 0 6px; }
  .hero p { font-size:14px; color:#555; margin:0 0 18px; }
  .btn { display:block; width:100%; background:var(--atb-red); color:#fff; text-decoration:none;
         font-size:17px; font-weight:700; padding:14px; border-radius:12px; margin-top:8px; }
  .btn:active { background:#b80016; }
  .features { list-style:none; padding:0; margin:18px 0 0; }
  .features li { background:#fff; border-radius:12px; padding:12px 14px; margin-bottom:10px;
                 font-size:14px; box-shadow:0 2px 8px rgba(0,0,0,.05); }
  .features li b { color:var(--atb-red); }
  .dev { background:#fff; border-radius:12px; padding:16px; margin-top:18px;
         box-shadow:0 2px 8px rgba(0,0,0,.05); font-size:13px; }
  .dev h2 { font-size:15px; margin:0 0 8px; }
  code { background:#f0f0f0; padding:2px 6px; border-radius:5px; font-size:12px;
         font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
  footer { text-align:center; font-size:11px; color:#999; padding:22px 16px; }
</style>
</head>
<body>
  <header>
    <div class="logo">ATB Market</div>
    <div class="tag">Your neighbourhood store, in your pocket</div>
  </header>
  <div class="wrap">
    <div class="hero">
      <div class="phone">&#128241;</div>
      <h1>Shop. Scan. Save.</h1>
      <p>Browse weekly deals, collect loyalty points and register your phone number
         for personalised offers - all from the official ATB Market app.</p>
      <a class="btn" href="/download/atb-market.apk">&#11015; Download APK</a>
    </div>
    <ul class="features">
      <li><b>Loyalty card</b> - digital card, points and coupons in one tap.</li>
      <li><b>Weekly catalogue</b> - every promo, updated each Thursday.</li>
      <li><b>Phone registration</b> - quick OTP sign-up for new members.</li>
    </ul>
    <div class="dev">
      <h2>Developers / API</h2>
      <p>The app registers new members against our mobile registration API on
         <code>mobapp.atbmarket.com</code>. Clients send a JSON phone number to
         <code>POST /register/login</code> and receive a session token plus an OTP
         challenge. Service health is at <code>GET /healthz</code>.</p>
      <p>API access requires the app's provisioned HTTP Basic service credential
         (shipped with the mobile client build).</p>
    </div>
  </div>
  <footer>&copy; ATB Market - lab environment. All data fictional.</footer>
</body>
</html>"""
    return Response(html, mimetype="text/html")


@app.get("/download/atb-market.apk")
def download_apk():
    ip = atblog.client_ip(request)
    atblog.log("mobapp.apk_download", ip, path="/download/atb-market.apk",
               file="atb-market.apk", msg="ATB mobile app package downloaded")
    if not os.path.exists(APK_PATH):
        build_apk(APK_PATH)
    return send_file(
        APK_PATH,
        mimetype="application/vnd.android.package-archive",
        as_attachment=True,
        download_name="atb-market.apk",
    )


@app.post("/register/login")
def register_login():
    ip = atblog.client_ip(request)
    creds = _check_basic(request.headers.get("Authorization", ""))
    body = request.get_json(silent=True) or {}
    phone = body.get("phoneNumber", "")
    if not creds:
        atblog.log("mobapp.auth_missing", ip, path="/register/login")
        return jsonify(error="missing basic auth"), 401
    user, pw = creds
    if user == REG_USER and pw == REG_PASS:
        atblog.log("mobapp.hardcoded_cred_used", ip, user=user, phone=phone,
                   msg="APK hard-coded reg credentials accepted")
        return jsonify(token=FAKE_TOKEN, message="Auth OTP was sent..."), 201
    atblog.log("mobapp.auth_fail", ip, user=user, phone=phone)
    return jsonify(error="invalid credentials"), 401


@app.get("/healthz")
def healthz():
    return "ok", 200


# Build the downloadable package once at startup.
try:
    build_apk(APK_PATH)
except OSError:
    pass


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80)
