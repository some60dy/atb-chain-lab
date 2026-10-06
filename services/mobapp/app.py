"""Step 1a - mobapp.atbmarket.com mobile registration API.
Hard-coded Basic creds (reg_user:basic*88password!prod99) recovered from the APK.
"""
import base64
import os
import time

from flask import Flask, request, jsonify
import atblog

app = Flask(__name__)
REG_USER = "reg_user"
REG_PASS = "basic*88password!prod99"

FAKE_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJyZWciLCJwaG9uZSI6IjM4MCIsImlhdCI6MTcwMH0."
    "S1gn4tur3Pr0dReg1str4t10nT0k3n0000"
)


def _check_basic(hdr):
    if not hdr or not hdr.startswith("Basic "):
        return None
    try:
        raw = base64.b64decode(hdr.split(" ", 1)[1]).decode("utf-8", "replace")
        user, _, pw = raw.partition(":")
        return user, pw
    except Exception:
        return None


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


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80)
