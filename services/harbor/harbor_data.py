"""Static catalogue for the sh-harb-p01 Harbor emulation.

Pure data: projects, repositories, base images, Trivy CVE pools, users,
members, robots and labels. app.py turns this into artifacts / manifests.
"""

HARBOR_VERSION = "v2.11.1-6b7ecba1"
TRIVY_VERSION = "v0.50.1"
REGISTRY_HOST = "harbor.atbmarket.com"

# ---------------------------------------------------------------------------
# Users (only the ones with a "pw" can log in; the rest are display-only).
# ---------------------------------------------------------------------------
USERS = {
    "admin": {"id": 1, "pw": "Hrb#2u7Lm!Xq4sKe9Tz", "admin": True,
              "email": "devops@atbmarket.com", "realname": "Harbor Admin",
              "created": 1290},
    "o.bondarenko": {"id": 3, "admin": True, "email": "o.bondarenko@atbmarket.com",
                     "realname": "Oleh Bondarenko", "created": 1201},
    "i.melnyk": {"id": 4, "admin": False, "email": "i.melnyk@atbmarket.com",
                 "realname": "Ihor Melnyk", "created": 1140},
    "s.tkachenko": {"id": 5, "admin": False, "email": "s.tkachenko@atbmarket.com",
                    "realname": "Serhii Tkachenko", "created": 1098},
    "v.kravets": {"id": 6, "admin": False, "email": "v.kravets@atbmarket.com",
                  "realname": "Vitalii Kravets", "created": 1031},
    "a.lysenko": {"id": 7, "admin": False, "email": "a.lysenko@atbmarket.com",
                  "realname": "Andrii Lysenko", "created": 977},
    "reg_user": {"id": 8, "pw": "basic*88password!prod99", "admin": False,
                 "email": "mobile-ci@atbmarket.com",
                 "realname": "Mobile CI registry user", "created": 960},
    "m.savchenko": {"id": 9, "admin": False, "email": "m.savchenko@atbmarket.com",
                    "realname": "Maryna Savchenko", "created": 702},
    "y.hnatiuk": {"id": 10, "admin": False, "email": "y.hnatiuk@atbmarket.com",
                  "realname": "Yurii Hnatiuk", "created": 611},
    "n.petrenko": {"id": 11, "admin": False, "email": "n.petrenko@atbmarket.com",
                   "realname": "Nazar Petrenko", "created": 455},
    "k.shevchuk": {"id": 12, "admin": False, "email": "k.shevchuk@atbmarket.com",
                   "realname": "Kateryna Shevchuk", "created": 203},
}

# ---------------------------------------------------------------------------
# Projects. quota in GiB (-1 = unlimited). created = days before reference.
# ---------------------------------------------------------------------------
PROJECTS = [
    {"id": 1, "name": "library", "public": True, "owner": "admin", "created": 1290,
     "quota": -1, "auto_scan": True, "severity": "", "registry": None,
     "members": [("admin", "Project Admin"), ("o.bondarenko", "Project Admin"),
                 ("i.melnyk", "Maintainer")],
     "labels": []},
    {"id": 2, "name": "ishop", "public": True, "owner": "o.bondarenko", "created": 1188,
     "quota": 200, "auto_scan": True, "severity": "", "registry": None,
     "members": [("o.bondarenko", "Project Admin"), ("s.tkachenko", "Maintainer"),
                 ("i.melnyk", "Developer"), ("m.savchenko", "Guest"),
                 ("k.shevchuk", "Developer")],
     "labels": [("release-candidate", "#F57600", "Passed QA, awaiting prod rollout"),
                ("hotfix", "#C92100", "Out-of-band fix")]},
    {"id": 3, "name": "storeplus", "public": True, "owner": "o.bondarenko", "created": 1102,
     "quota": 150, "auto_scan": False, "severity": "", "registry": None,
     "members": [("o.bondarenko", "Project Admin"), ("v.kravets", "Maintainer"),
                 ("i.melnyk", "Developer"), ("m.savchenko", "Guest")],
     "labels": [("excise", "#0072A3", "Excise stamp integration")]},
    {"id": 4, "name": "mobapp", "public": True, "owner": "a.lysenko", "created": 979,
     "quota": 100, "auto_scan": True, "severity": "", "registry": None,
     "members": [("a.lysenko", "Project Admin"), ("reg_user", "Developer"),
                 ("i.melnyk", "Maintainer"), ("m.savchenko", "Guest")],
     "labels": [("android", "#62A420", ""), ("ios", "#004A70", "")]},
    {"id": 5, "name": "supplier-portal", "public": True, "owner": "y.hnatiuk", "created": 870,
     "quota": 50, "auto_scan": False, "severity": "", "registry": None,
     "members": [("y.hnatiuk", "Project Admin"), ("i.melnyk", "Developer")],
     "labels": []},
    {"id": 6, "name": "education", "public": True, "owner": "i.melnyk", "created": 812,
     "quota": 40, "auto_scan": False, "severity": "", "registry": None,
     "members": [("i.melnyk", "Project Admin"), ("k.shevchuk", "Developer")],
     "labels": []},
    {"id": 7, "name": "monitoring", "public": True, "owner": "n.petrenko", "created": 455,
     "quota": 30, "auto_scan": True, "severity": "", "registry": None,
     "members": [("n.petrenko", "Project Admin"), ("o.bondarenko", "Maintainer"),
                 ("i.melnyk", "Developer")],
     "labels": []},
    {"id": 8, "name": "infra", "public": False, "owner": "o.bondarenko", "created": 1150,
     "quota": 60, "auto_scan": True, "severity": "high", "registry": None,
     "members": [("o.bondarenko", "Project Admin"), ("i.melnyk", "Maintainer"),
                 ("n.petrenko", "Developer")],
     "labels": [("edge", "#8939AD", "Runs on edge/LB nodes")]},
    {"id": 9, "name": "loyalty", "public": False, "owner": "v.kravets", "created": 640,
     "quota": 40, "auto_scan": False, "severity": "", "registry": None,
     "members": [("v.kravets", "Project Admin"), ("k.shevchuk", "Developer"),
                 ("reg_user", "Guest")],
     "labels": []},
    {"id": 10, "name": "dockerhub-proxy", "public": True, "owner": "admin", "created": 730,
     "quota": 80, "auto_scan": False, "severity": "", "registry": "docker-hub",
     "members": [("admin", "Project Admin"), ("o.bondarenko", "Project Admin")],
     "labels": []},
]

GLOBAL_LABELS = [
    ("prod", "#318700", "Deployed to production"),
    ("staging", "#F38B00", "Deployed to staging"),
    ("deprecated", "#565656", "Do not use for new deployments"),
    ("pci-scope", "#C92100", "Card-data environment"),
    ("do-not-delete", "#004A70", "Excluded from retention"),
]

ROBOTS = [
    # name, level, project, description, created(days), expires(days or -1), perms
    ("robot$ishop+gitlab-ci", "project", "ishop", "GitLab CI push for ishop/*", 840, -1,
     "push, pull, create tag, read artifact"),
    ("robot$storeplus+gitlab-ci", "project", "storeplus", "GitLab CI push for storeplus/*",
     800, -1, "push, pull, create tag"),
    ("robot$supplier-portal+deploy", "project", "supplier-portal", "deploy key sp-web-p01",
     610, -1, "pull"),
    ("robot$monitoring+ci", "project", "monitoring", "exporters build", 400, 365, "push, pull"),
    ("robot$infra+ansible", "project", "infra", "ansible edge rollout", 520, -1, "pull"),
    ("robot$k8s-prod-puller", "system", "*", "image pulls for k8s-prod (all projects)",
     700, -1, "pull (all projects)"),
    ("robot$trivy-mirror", "system", "*", "offline DB mirror job", 300, 90, "read"),
]

REGISTRIES = [
    ("docker-hub", "Docker Hub", "https://hub.docker.com", "Healthy", 730),
    ("gitlab-registry", "Docker Registry", "https://registry.gitlab-p01.atbmarket.com",
     "Unhealthy", 512),
]

# ---------------------------------------------------------------------------
# Trivy CVE catalogue: id -> (pool, package, installed, fixed, severity, cvss, cwe, title)
# ---------------------------------------------------------------------------
VULNS = {
    # Alpine OS packages
    "CVE-2023-38545": ("alpine", "curl", "8.4.0-r0", "8.5.0-r0", "Critical", 9.8, "CWE-787",
                       "curl: heap based buffer overflow in the SOCKS5 proxy handshake"),
    "CVE-2024-2398": ("alpine", "libcurl", "8.4.0-r0", "8.7.1-r0", "Medium", 5.9, "CWE-772",
                      "curl: HTTP/2 push headers memory-leak"),
    "CVE-2024-6119": ("alpine", "libssl3", "3.1.4-r1", "3.1.7-r0", "High", 7.5, "CWE-843",
                      "openssl: Possible denial of service in X.509 name checks"),
    "CVE-2024-0727": ("alpine", "libcrypto3", "3.1.4-r1", "3.1.4-r5", "Medium", 5.5, "CWE-476",
                      "openssl: denial of service via null dereference in PKCS12 parsing"),
    "CVE-2023-6129": ("alpine", "libcrypto3", "3.1.4-r1", "3.1.4-r3", "Medium", 6.5, "CWE-787",
                      "openssl: POLY1305 MAC implementation corrupts vector registers on PowerPC"),
    "CVE-2024-4741": ("alpine", "libssl3", "3.1.4-r1", "3.1.6-r0", "Low", 0.0, "CWE-416",
                      "openssl: Use After Free with SSL_free_buffers"),
    "CVE-2023-42363": ("alpine", "busybox", "1.36.1-r5", "1.36.1-r7", "Medium", 5.5, "CWE-416",
                       "busybox: use-after-free in awk"),
    "CVE-2023-42366": ("alpine", "busybox", "1.36.1-r5", "1.36.1-r16", "Medium", 5.5, "CWE-787",
                       "busybox: heap-buffer-overflow in awk"),
    "CVE-2023-52425": ("alpine", "libexpat", "2.5.0-r1", "2.6.0-r0", "High", 7.5, "CWE-400",
                       "expat: parsing large tokens can trigger a denial of service"),
    "CVE-2024-45491": ("alpine", "libexpat", "2.5.0-r1", "2.6.3-r0", "Critical", 9.8, "CWE-190",
                       "libexpat: Integer Overflow or Wraparound in dtdCopy"),
    "CVE-2024-45492": ("alpine", "libexpat", "2.5.0-r1", "2.6.3-r0", "Critical", 9.8, "CWE-190",
                       "libexpat: integer overflow in nextScaffoldPart"),
    # Debian bookworm
    "CVE-2023-4911": ("debian", "libc6", "2.36-9+deb12u1", "2.36-9+deb12u3", "High", 7.8, "CWE-787",
                      "glibc: buffer overflow in ld.so leading to privilege escalation (Looney Tunables)"),
    "CVE-2024-2961": ("debian", "libc6", "2.36-9+deb12u1", "2.36-9+deb12u7", "High", 8.8, "CWE-787",
                      "glibc: Out of bounds write in iconv may lead to remote code execution"),
    "CVE-2024-33599": ("debian", "libc-bin", "2.36-9+deb12u1", "2.36-9+deb12u7", "High", 8.1, "CWE-121",
                       "glibc: stack-based buffer overflow in netgroup cache"),
    "CVE-2023-45853": ("debian", "zlib1g", "1:1.2.13.dfsg-1", "", "Critical", 9.8, "CWE-190",
                       "zlib: integer overflow and resultant heap-based buffer overflow in zipOpenNewFileInZip4_6"),
    "CVE-2024-6387": ("debian", "openssh-client", "1:9.2p1-2+deb12u1", "1:9.2p1-2+deb12u3", "High", 8.1,
                      "CWE-364", "openssh: regreSSHion - race condition in sshd's SIGALRM handler"),
    "CVE-2023-44487": ("debian", "libnghttp2-14", "1.52.0-1", "1.52.0-1+deb12u1", "High", 7.5, "CWE-400",
                       "HTTP/2: Multiple HTTP/2 enabled web servers are vulnerable to a DDoS attack (Rapid Reset)"),
    "CVE-2024-28182": ("debian", "libnghttp2-14", "1.52.0-1", "1.52.0-1+deb12u2", "Medium", 5.3, "CWE-770",
                       "nghttp2: CONTINUATION frames DoS"),
    "CVE-2023-50495": ("debian", "libncursesw6", "6.4-4", "", "Medium", 6.5, "CWE-400",
                       "ncurses: segmentation fault via _nc_wrap_entry()"),
    "CVE-2022-27943": ("debian", "libstdc++6", "12.2.0-14", "", "Low", 5.5, "CWE-674",
                       "binutils: libiberty/rust-demangle.c stack exhaustion"),
    "CVE-2011-3389": ("debian", "libgnutls30", "3.7.9-2", "", "Medium", 5.9, "CWE-326",
                      "HTTPS: block-wise chosen-plaintext attack against SSL/TLS (BEAST)"),
    "CVE-2005-2541": ("debian", "tar", "1.34+dfsg-1.2", "", "Low", 0.0, "",
                      "tar: does not properly warn the user when extracting setuid or setgid files"),
    "CVE-2023-31484": ("debian", "perl-base", "5.36.0-7", "5.36.0-7+deb12u1", "High", 8.1, "CWE-295",
                       "perl: CPAN.pm does not verify TLS certificates when downloading distributions"),
    "CVE-2024-45490": ("debian", "libexpat1", "2.5.0-1", "2.5.0-1+deb12u1", "Critical", 9.8, "CWE-611",
                       "libexpat: Negative Length Parsing Vulnerability in libexpat"),
    "CVE-2023-52426": ("debian", "libexpat1", "2.5.0-1", "", "Low", 5.5, "CWE-776",
                       "expat: recursive XML entity expansion vulnerability"),
    "CVE-2024-26461": ("debian", "libgssapi-krb5-2", "1.20.1-2+deb12u1", "", "Low", 5.3, "CWE-770",
                       "krb5: Memory leak at /krb5/src/lib/gssapi/krb5/k5sealv3.c"),
    # Ubuntu jammy
    "CVE-2024-6387@u": ("ubuntu", "openssh-client", "1:8.9p1-3ubuntu0.6", "1:8.9p1-3ubuntu0.10", "High",
                        8.1, "CWE-364", "openssh: regreSSHion - race condition in sshd's SIGALRM handler"),
    "CVE-2023-4911@u": ("ubuntu", "libc6", "2.35-0ubuntu3.1", "2.35-0ubuntu3.4", "High", 7.8, "CWE-787",
                        "glibc: buffer overflow in ld.so leading to privilege escalation (Looney Tunables)"),
    "CVE-2024-2961@u": ("ubuntu", "libc6", "2.35-0ubuntu3.1", "2.35-0ubuntu3.7", "High", 8.8, "CWE-787",
                        "glibc: Out of bounds write in iconv may lead to remote code execution"),
    "CVE-2023-38545@u": ("ubuntu", "curl", "7.81.0-1ubuntu1.13", "7.81.0-1ubuntu1.14", "High", 9.8,
                         "CWE-787", "curl: heap based buffer overflow in the SOCKS5 proxy handshake"),
    "CVE-2023-29491": ("ubuntu", "libtinfo6", "6.3-2ubuntu0.1", "", "Medium", 7.8, "CWE-787",
                       "ncurses: Local users can trigger security-relevant memory corruption via malformed data"),
    "CVE-2024-28085": ("ubuntu", "bsdutils", "1:2.37.2-4ubuntu3", "1:2.37.2-4ubuntu3.3", "Medium", 8.4,
                       "CWE-150", "util-linux: CVE-2024-28085: wall: escape sequence injection"),
    "CVE-2023-5678": ("ubuntu", "libssl3", "3.0.2-0ubuntu1.10", "3.0.2-0ubuntu1.12", "Low", 5.3, "CWE-606",
                      "openssl: Generating excessively long X9.42 DH keys or checking excessively long X9.42 DH keys or parameters may be very slow"),
    "CVE-2016-2781": ("ubuntu", "coreutils", "8.32-4.1ubuntu1", "", "Low", 6.5, "CWE-20",
                      "coreutils: Non-privileged session can escape to the parent session in chroot"),
    # Node.js (npm)
    "CVE-2024-21508": ("node", "mysql2", "3.6.0", "3.9.4", "Critical", 9.8, "CWE-94",
                       "mysql2: Remote Code Execution (RCE) via the readCodeFor function"),
    "CVE-2024-29041": ("node", "express", "4.18.2", "4.19.2", "Medium", 6.1, "CWE-601",
                       "express: cause malformed URLs to be evaluated"),
    "CVE-2024-43796": ("node", "express", "4.18.2", "4.20.0", "Low", 5.0, "CWE-79",
                       "express: Improper Input Handling in Express Redirects"),
    "CVE-2024-45590": ("node", "body-parser", "1.20.1", "1.20.3", "High", 7.5, "CWE-405",
                       "body-parser: Denial of Service Vulnerability in body-parser"),
    "CVE-2024-45296": ("node", "path-to-regexp", "0.1.7", "0.1.10", "High", 7.5, "CWE-1333",
                       "path-to-regexp: Backtracking regular expressions cause ReDoS"),
    "CVE-2024-37890": ("node", "ws", "8.13.0", "8.17.1", "High", 7.5, "CWE-476",
                       "nodejs-ws: denial of service when handling a request with many HTTP headers"),
    "CVE-2023-45857": ("node", "axios", "1.5.1", "1.6.0", "Medium", 6.5, "CWE-352",
                       "axios: exposure of confidential data stored in cookies"),
    "CVE-2024-39338": ("node", "axios", "1.5.1", "1.7.4", "High", 7.5, "CWE-918",
                       "axios: Server-Side Request Forgery"),
    "CVE-2024-4068": ("node", "braces", "3.0.2", "3.0.3", "High", 7.5, "CWE-1050",
                      "braces: fails to limit the number of characters it can handle"),
    "CVE-2022-25883": ("node", "semver", "7.3.8", "7.5.2", "Medium", 5.3, "CWE-1333",
                       "nodejs-semver: Regular expression denial of service"),
    "CVE-2023-42282": ("node", "ip", "2.0.0", "2.0.1", "Critical", 9.8, "CWE-918",
                       "nodejs-ip: arbitrary code execution via the isPublic() function"),
    "CVE-2024-28849": ("node", "follow-redirects", "1.15.3", "1.15.6", "Medium", 6.5, "CWE-200",
                       "follow-redirects: Possible credential leak"),
    "CVE-2024-21538": ("node", "cross-spawn", "7.0.3", "7.0.5", "High", 7.5, "CWE-1333",
                       "cross-spawn: regular expression denial of service"),
    "CVE-2023-26136": ("node", "tough-cookie", "2.5.0", "4.1.3", "Medium", 6.5, "CWE-1321",
                       "tough-cookie: prototype pollution in cookie memstore"),
    # Python (pip)
    "CVE-2024-35195": ("python", "requests", "2.31.0", "2.32.0", "Medium", 5.6, "CWE-670",
                       "requests: subsequent requests to the same host ignore cert verification"),
    "CVE-2024-3651": ("python", "idna", "3.4", "3.7", "Medium", 6.2, "CWE-400",
                      "python-idna: potential DoS via resource consumption via specially crafted inputs to idna.encode()"),
    "CVE-2024-39689": ("python", "certifi", "2023.7.22", "2024.7.4", "Low", 7.5, "CWE-345",
                       "python-certifi: Remove root certificates from GLOBALTRUST"),
    "CVE-2024-6345": ("python", "setuptools", "65.5.1", "70.0.0", "High", 8.8, "CWE-94",
                      "pypa/setuptools: Remote code execution via download functions in the package_index module"),
    "CVE-2023-5752": ("python", "pip", "23.2.1", "23.3", "Low", 3.3, "CWE-77",
                      "pip: Mercurial configuration injectable in repo revision when installing via pip"),
    "CVE-2024-1135": ("python", "gunicorn", "20.1.0", "22.0.0", "High", 7.5, "CWE-444",
                      "python-gunicorn: HTTP Request Smuggling due to improper validation of Transfer-Encoding headers"),
    "CVE-2024-34069": ("python", "Werkzeug", "2.3.7", "3.0.3", "High", 7.5, "CWE-94",
                       "python-werkzeug: user may execute code on a developer's machine"),
    "CVE-2024-22195": ("python", "Jinja2", "3.1.2", "3.1.3", "Medium", 5.4, "CWE-79",
                       "jinja2: HTML attribute injection when passing user input as keys to xmlattr filter"),
    "CVE-2023-50782": ("python", "cryptography", "41.0.4", "42.0.0", "High", 7.5, "CWE-385",
                       "python-cryptography: Bleichenbacher timing oracle attack against RSA decryption"),
    "CVE-2024-26130": ("python", "cryptography", "41.0.4", "42.0.4", "High", 7.5, "CWE-476",
                       "cryptography: NULL pointer dereference with pkcs12.serialize_key_and_certificates"),
    # .NET (nuget)
    "CVE-2024-21907": ("dotnet", "Newtonsoft.Json", "12.0.1", "13.0.1", "High", 7.5, "CWE-755",
                       "Newtonsoft.Json: Improper Handling of Exceptional Conditions"),
    "CVE-2024-30105": ("dotnet", "System.Text.Json", "6.0.0", "8.0.4", "High", 7.5, "CWE-835",
                       "dotnet: DoS in System.Text.Json"),
    "CVE-2024-43485": ("dotnet", "System.Text.Json", "6.0.0", "8.0.5", "High", 7.5, "CWE-407",
                       "dotnet: Denial of Service in System.Text.Json"),
    "CVE-2023-29331": ("dotnet", "System.Security.Cryptography.Pkcs", "6.0.1", "6.0.3", "High", 7.5,
                       "CWE-400", "dotnet: Denial of Service with Client Certificates using .NET Kestrel"),
    "CVE-2024-38095": ("dotnet", "System.Formats.Asn1", "6.0.0", "8.0.1", "High", 7.5, "CWE-400",
                       "dotnet: DoS when parsing X.509 Content and ObjectIdentifiers"),
    "CVE-2024-32655": ("dotnet", "Npgsql", "6.0.4", "6.0.11", "High", 8.1, "CWE-190",
                       "Npgsql: SQL Injection via Protocol Message Size Overflow"),
    "CVE-2024-0057": ("dotnet", "Microsoft.AspNetCore.App.Runtime", "6.0.25", "6.0.26", "Critical", 9.1,
                      "CWE-20", "dotnet: X509 Certificate Chain Building security feature bypass"),
    # PHP
    "CVE-2024-4577": ("php", "php", "8.1.20", "8.1.29", "Critical", 9.8, "CWE-78",
                      "php: Command injection via argument injection in PHP-CGI on Windows"),
    "CVE-2023-3824": ("php", "php", "8.1.20", "8.1.22", "Critical", 9.8, "CWE-121",
                      "php: phar Buffer mismanagement"),
    "CVE-2024-2756": ("php", "php", "8.1.20", "8.1.28", "Medium", 6.5, "CWE-284",
                      "php: __Host-/__Secure- cookie bypass due to partial CVE-2022-31629 fix"),
    "CVE-2024-5458": ("php", "php", "8.1.20", "8.1.29", "Medium", 5.3, "CWE-20",
                      "php: Filter bypass in filter_var (FILTER_VALIDATE_URL)"),
    "CVE-2024-8925": ("php", "php", "8.1.20", "8.1.30", "Medium", 5.3, "CWE-1286",
                      "php: Erroneous parsing of multipart form data"),
    "CVE-2023-3823": ("php", "php", "8.1.20", "8.1.22", "High", 8.6, "CWE-611",
                      "php: XML loading external entity without being enabled"),
    # Go (gobinary)
    "CVE-2024-24790": ("go", "stdlib", "1.21.5", "1.21.11", "Critical", 9.8, "CWE-180",
                       "golang: net/netip: Unexpected behavior from Is methods for IPv4-mapped IPv6 addresses"),
    "CVE-2023-45288": ("go", "stdlib", "1.21.5", "1.21.9", "High", 7.5, "CWE-400",
                       "golang: net/http, x/net/http2: unlimited number of CONTINUATION frames causes DoS"),
    "CVE-2024-34156": ("go", "stdlib", "1.21.5", "1.22.7", "High", 7.5, "CWE-674",
                       "encoding/gob: golang: Calling Decoder.Decode on a message which contains deeply nested structures can cause a panic"),
    "CVE-2023-39325": ("go", "golang.org/x/net", "v0.15.0", "0.17.0", "High", 7.5, "CWE-770",
                       "golang: net/http, x/net/http2: rapid stream resets can cause excessive work"),
    "CVE-2023-48795": ("go", "golang.org/x/crypto", "v0.14.0", "0.17.0", "Medium", 5.9, "CWE-354",
                       "ssh: Prefix truncation attack on Binary Packet Protocol (BPP) (Terrapin)"),
    "CVE-2024-45337": ("go", "golang.org/x/crypto", "v0.14.0", "0.31.0", "Critical", 9.1, "CWE-285",
                       "golang.org/x/crypto/ssh: Misuse of ServerConfig.PublicKeyCallback may cause authorization bypass"),
    "CVE-2023-47108": ("go", "go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc",
                       "v0.42.0", "0.46.0", "High", 7.5, "CWE-770",
                       "opentelemetry-go-contrib: DoS vulnerability in otelgrpc due to unbound cardinality metrics"),
    # Java (jar)
    "CVE-2021-44228": ("java", "org.apache.logging.log4j:log4j-core", "2.14.1", "2.15.0", "Critical", 10.0,
                       "CWE-502", "log4j-core: Remote code execution in Log4j 2.x when logs contain an attacker-controlled string value"),
    "CVE-2021-45046": ("java", "org.apache.logging.log4j:log4j-core", "2.14.1", "2.16.0", "Critical", 9.0,
                       "CWE-917", "log4j-core: DoS in log4j 2.x with thread context message pattern and context lookup pattern"),
    "CVE-2022-1471": ("java", "org.yaml:snakeyaml", "1.30", "2.0", "High", 8.3, "CWE-502",
                      "SnakeYaml: Constructor Deserialization Remote Code Execution"),
    "CVE-2022-22965": ("java", "org.springframework:spring-beans", "5.3.17", "5.3.18", "Critical", 9.8,
                       "CWE-94", "spring-framework: RCE via Data Binding on JDK 9+ (Spring4Shell)"),
    "CVE-2024-1597": ("java", "org.postgresql:postgresql", "42.3.3", "42.3.9", "Critical", 10.0, "CWE-89",
                      "pgjdbc: PostgreSQL JDBC Driver allows attacker to inject SQL if using PreferQueryMode=SIMPLE"),
    "CVE-2022-42889": ("java", "org.apache.commons:commons-text", "1.9", "1.10.0", "Critical", 9.8, "CWE-94",
                       "apache-commons-text: variable interpolation RCE (Text4Shell)"),
    "CVE-2020-36518": ("java", "com.fasterxml.jackson.core:jackson-databind", "2.12.3", "2.12.6.1", "High", 7.5,
                       "CWE-787", "jackson-databind: denial of service via a large depth of nested objects"),
}

# Extra SBOM packages per pool (name, version, type, license)
SBOM_EXTRA = {
    "alpine": [("alpine-baselayout", "3.4.3-r1", "apk", "GPL-2.0-only"),
               ("ca-certificates-bundle", "20230506-r0", "apk", "MPL-2.0 AND MIT"),
               ("musl", "1.2.4-r2", "apk", "MIT"), ("zlib", "1.3-r2", "apk", "Zlib"),
               ("apk-tools", "2.14.0-r2", "apk", "GPL-2.0-only")],
    "debian": [("base-files", "12.4+deb12u2", "deb", "GPL-2.0"),
               ("bash", "5.2.15-2+b2", "deb", "GPL-3.0"), ("coreutils", "9.1-1", "deb", "GPL-3.0"),
               ("dpkg", "1.21.22", "deb", "GPL-2.0"), ("libssl3", "3.0.11-1~deb12u2", "deb", "Apache-2.0"),
               ("ca-certificates", "20230311", "deb", "MPL-2.0")],
    "ubuntu": [("base-files", "12ubuntu4.4", "deb", "GPL-2.0"), ("bash", "5.1-6ubuntu1", "deb", "GPL-3.0"),
               ("dpkg", "1.21.1ubuntu2.2", "deb", "GPL-2.0"), ("tzdata", "2023c-0ubuntu0.22.04.2", "deb", "PD")],
    "node": [("lodash", "4.17.21", "npm", "MIT"), ("dotenv", "16.3.1", "npm", "BSD-2-Clause"),
             ("pino", "8.15.0", "npm", "MIT"), ("joi", "17.10.2", "npm", "BSD-3-Clause"),
             ("ioredis", "5.3.2", "npm", "MIT")],
    "python": [("urllib3", "2.0.7", "python-pkg", "MIT"), ("click", "8.1.7", "python-pkg", "BSD-3-Clause"),
               ("Flask", "2.3.3", "python-pkg", "BSD-3-Clause"), ("wheel", "0.41.2", "python-pkg", "MIT")],
    "dotnet": [("Microsoft.EntityFrameworkCore", "6.0.21", "nuget", "MIT"),
               ("Serilog.AspNetCore", "6.1.0", "nuget", "Apache-2.0"),
               ("Swashbuckle.AspNetCore", "6.5.0", "nuget", "MIT"),
               ("Polly", "7.2.4", "nuget", "BSD-3-Clause")],
    "php": [("composer", "2.6.5", "binary", "MIT"), ("monolog/monolog", "2.9.1", "composer", "MIT"),
            ("phpmailer/phpmailer", "6.8.1", "composer", "LGPL-2.1"),
            ("guzzlehttp/guzzle", "7.8.0", "composer", "MIT")],
    "go": [("github.com/prometheus/client_golang", "v1.17.0", "gomod", "Apache-2.0"),
           ("github.com/alecthomas/kingpin/v2", "v2.3.2", "gomod", "MIT"),
           ("google.golang.org/protobuf", "v1.31.0", "gomod", "BSD-3-Clause")],
    "java": [("org.springframework.boot:spring-boot", "2.6.5", "jar", "Apache-2.0"),
             ("com.zaxxer:HikariCP", "4.0.3", "jar", "Apache-2.0"),
             ("org.apache.kafka:kafka-clients", "2.8.1", "jar", "Apache-2.0")],
}

_ALPINE_ROOT = [
    ("/bin/sh -c #(nop) ADD file:d0764a717d1e9d0aff3fa84779b11bfa0afe4430dcb6b46d965b209167639ba0 in / ", False),
    ('/bin/sh -c #(nop)  CMD ["/bin/sh"]', True),
]
_DEBIAN_ROOT = [
    ("/bin/sh -c #(nop) ADD file:9deb26e1dbc258df4b0d5b8a3ad4b1fbbfb5c7d1e3b7f3b8b6b1b7e18d2bb4a1 in / ", False),
    ('/bin/sh -c #(nop)  CMD ["bash"]', True),
]
_UBUNTU_ROOT = [
    ("/bin/sh -c #(nop)  ARG RELEASE", True),
    ("/bin/sh -c #(nop)  ARG LAUNCHPAD_BUILD_ARCH", True),
    ("/bin/sh -c #(nop)  LABEL org.opencontainers.image.ref.name=ubuntu", True),
    ("/bin/sh -c #(nop)  LABEL org.opencontainers.image.version=22.04", True),
    ("/bin/sh -c #(nop) ADD file:63d5ab3ef0aab308c0e71cb67292c5467f60deafa9b0418cbb220affcd078444 in / ", False),
    ('/bin/sh -c #(nop)  CMD ["/bin/bash"]', True),
]

# Base images: image ref, OS, env, history (created_by, empty_layer), size MB, pools
BASES = {
    "alpine": {
        "image": "alpine:3.18.5", "os": "alpine 3.18.5", "size": 3.3, "pools": ["alpine"],
        "env": ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"],
        "history": _ALPINE_ROOT,
    },
    "node18": {
        "image": "node:18.19.0-alpine3.18", "os": "alpine 3.18.5", "size": 41.2,
        "pools": ["alpine", "node"],
        "env": ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "NODE_VERSION=18.19.0", "YARN_VERSION=1.22.19"],
        "history": _ALPINE_ROOT + [
            ("ENV NODE_VERSION=18.19.0", True),
            ("RUN /bin/sh -c addgroup -g 1000 node && adduser -u 1000 -G node -s /bin/sh -D node "
             "&& apk add --no-cache libstdc++ && apk add --no-cache --virtual .build-deps curl "
             "&& ARCH= OPENSSL_ARCH='linux*' && alpineArch=\"$(apk --print-arch)\" ... "
             "&& node --version && npm --version # buildkit", False),
            ("ENV YARN_VERSION=1.22.19", True),
            ("RUN /bin/sh -c apk add --no-cache --virtual .build-deps-yarn curl gnupg tar "
             "&& for key in 6A010C5166006599AA17F08146C2130DFD2497F5 ; do gpg --batch --keyserver "
             "hkps://keys.openpgp.org --recv-keys \"$key\" ; done && curl -fsSLO --compressed "
             "\"https://yarnpkg.com/downloads/$YARN_VERSION/yarn-v$YARN_VERSION.tar.gz\" ... "
             "&& yarn --version # buildkit", False),
            ("COPY docker-entrypoint.sh /usr/local/bin/ # buildkit", False),
            ('ENTRYPOINT ["docker-entrypoint.sh"]', True),
            ('CMD ["node"]', True),
        ],
    },
    "python311": {
        "image": "python:3.11.6-slim-bookworm", "os": "debian 12.2", "size": 45.6,
        "pools": ["debian", "python"],
        "env": ["PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "LANG=C.UTF-8", "GPG_KEY=A035C8C19219BA821ECEA86B64E628F8D684696D",
                "PYTHON_VERSION=3.11.6", "PYTHON_PIP_VERSION=23.2.1",
                "PYTHON_SETUPTOOLS_VERSION=65.5.1"],
        "history": _DEBIAN_ROOT + [
            ("ENV PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", True),
            ("ENV LANG=C.UTF-8", True),
            ("RUN /bin/sh -c set -eux; apt-get update; apt-get install -y --no-install-recommends "
             "ca-certificates netbase tzdata ; rm -rf /var/lib/apt/lists/* # buildkit", False),
            ("ENV GPG_KEY=A035C8C19219BA821ECEA86B64E628F8D684696D", True),
            ("ENV PYTHON_VERSION=3.11.6", True),
            ("RUN /bin/sh -c set -eux; savedAptMark=\"$(apt-mark showmanual)\"; apt-get update; "
             "apt-get install -y --no-install-recommends dpkg-dev gcc gnupg libbluetooth-dev "
             "libbz2-dev libc6-dev libdb-dev libexpat1-dev libffi-dev libgdbm-dev liblzma-dev "
             "libncursesw5-dev libreadline-dev libsqlite3-dev libssl-dev make tk-dev uuid-dev "
             "wget xz-utils zlib1g-dev ; ... ./configure --enable-loadable-sqlite-extensions "
             "--enable-optimizations --enable-option-checking=fatal --enable-shared --with-lto "
             "--with-system-expat --without-ensurepip ; make -j \"$nproc\" ; make install; "
             "... python3 --version # buildkit", False),
            ("RUN /bin/sh -c set -eux; for src in idle3 pydoc3 python3 python3-config; do "
             "dst=\"$(echo \"$src\" | tr -d 3)\"; [ -s \"/usr/local/bin/$src\" ]; "
             "[ ! -e \"/usr/local/bin/$dst\" ]; ln -svT \"$src\" \"/usr/local/bin/$dst\"; done # buildkit", False),
            ("ENV PYTHON_PIP_VERSION=23.2.1", True),
            ("ENV PYTHON_SETUPTOOLS_VERSION=65.5.1", True),
            ("RUN /bin/sh -c set -eux; savedAptMark=\"$(apt-mark showmanual)\"; apt-get update; "
             "apt-get install -y --no-install-recommends wget; wget -O get-pip.py "
             "\"$PYTHON_GET_PIP_URL\"; ... python get-pip.py --disable-pip-version-check "
             "--no-cache-dir --no-compile \"pip==$PYTHON_PIP_VERSION\" "
             "\"setuptools==$PYTHON_SETUPTOOLS_VERSION\" ; rm -f get-pip.py; pip --version # buildkit", False),
            ('CMD ["python3"]', True),
        ],
    },
    "aspnet6": {
        "image": "mcr.microsoft.com/dotnet/aspnet:6.0.25-bookworm-slim", "os": "debian 12.2",
        "size": 76.4, "pools": ["debian", "dotnet"],
        "env": ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "ASPNETCORE_URLS=http://+:80", "DOTNET_RUNNING_IN_CONTAINER=true",
                "DOTNET_VERSION=6.0.25", "ASPNET_VERSION=6.0.25"],
        "history": _DEBIAN_ROOT + [
            ("ENV ASPNETCORE_URLS=http://+:80 DOTNET_RUNNING_IN_CONTAINER=true", True),
            ("RUN /bin/sh -c apt-get update && apt-get install -y --no-install-recommends "
             "ca-certificates libc6 libgcc-s1 libicu72 libssl3 libstdc++6 tzdata zlib1g "
             "&& rm -rf /var/lib/apt/lists/* # buildkit", False),
            ("ENV DOTNET_VERSION=6.0.25", True),
            ("COPY /dotnet /usr/share/dotnet # buildkit", False),
            ("RUN /bin/sh -c ln -s /usr/share/dotnet/dotnet /usr/bin/dotnet # buildkit", False),
            ("ENV ASPNET_VERSION=6.0.25", True),
            ("COPY /shared/Microsoft.AspNetCore.App /usr/share/dotnet/shared/Microsoft.AspNetCore.App "
             "# buildkit", False),
        ],
    },
    "nginx": {
        "image": "nginx:1.24.0-alpine", "os": "alpine 3.18.5", "size": 17.1, "pools": ["alpine"],
        "env": ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "NGINX_VERSION=1.24.0", "PKG_RELEASE=1"],
        "history": _ALPINE_ROOT + [
            ("/bin/sh -c #(nop)  LABEL maintainer=NGINX Docker Maintainers <docker-maint@nginx.com>", True),
            ("/bin/sh -c #(nop)  ENV NGINX_VERSION=1.24.0", True),
            ("/bin/sh -c #(nop)  ENV PKG_RELEASE=1", True),
            ("/bin/sh -c set -x && addgroup -g 101 -S nginx && adduser -S -D -H -u 101 -h "
             "/var/cache/nginx -s /sbin/nologin -G nginx -g nginx nginx && apkArch=\"$(cat "
             "/etc/apk/arch)\" && nginxPackages=\" nginx=${NGINX_VERSION}-r${PKG_RELEASE} \" ... "
             "&& ln -sf /dev/stdout /var/log/nginx/access.log && ln -sf /dev/stderr "
             "/var/log/nginx/error.log", False),
            ("/bin/sh -c #(nop) COPY file:7b307b62e82255f040c9812421a30090bf9abf3685f27b02d77fcca99f997911 "
             "in / ", False),
            ("/bin/sh -c #(nop) COPY file:5c18272734349488bd0c94ec8d382c872c1a0a435cca13bd4671353d6021d2cb "
             "in /docker-entrypoint.d ", False),
            ('/bin/sh -c #(nop)  ENTRYPOINT ["/docker-entrypoint.sh"]', True),
            ("/bin/sh -c #(nop)  EXPOSE 80", True),
            ("/bin/sh -c #(nop)  STOPSIGNAL SIGQUIT", True),
            ('/bin/sh -c #(nop)  CMD ["nginx" "-g" "daemon off;"]', True),
        ],
    },
    "php81": {
        "image": "php:8.1.20-apache-bookworm", "os": "debian 12.2", "size": 162.5,
        "pools": ["debian", "php"],
        "env": ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "PHPIZE_DEPS=autoconf dpkg-dev file g++ gcc libc-dev make pkg-config re2c",
                "PHP_INI_DIR=/usr/local/etc/php", "APACHE_CONFDIR=/etc/apache2",
                "APACHE_ENVVARS=/etc/apache2/envvars", "PHP_VERSION=8.1.20"],
        "history": _DEBIAN_ROOT + [
            ("/bin/sh -c #(nop)  ENV PHPIZE_DEPS=autoconf dpkg-dev file g++ gcc libc-dev make "
             "pkg-config re2c", True),
            ("/bin/sh -c set -eux; apt-get update; apt-get install -y --no-install-recommends "
             "$PHPIZE_DEPS ca-certificates curl xz-utils ; rm -rf /var/lib/apt/lists/*", False),
            ("/bin/sh -c #(nop)  ENV PHP_INI_DIR=/usr/local/etc/php", True),
            ("/bin/sh -c #(nop)  ENV APACHE_CONFDIR=/etc/apache2", True),
            ("/bin/sh -c #(nop)  ENV APACHE_ENVVARS=/etc/apache2/envvars", True),
            ("/bin/sh -c set -eux; apt-get update; apt-get install -y --no-install-recommends "
             "apache2; rm -rf /var/lib/apt/lists/*; ... a2dismod mpm_event && a2enmod mpm_prefork", False),
            ("/bin/sh -c #(nop)  ENV PHP_VERSION=8.1.20", True),
            ("/bin/sh -c set -eux; savedAptMark=\"$(apt-mark showmanual)\"; ... ./configure "
             "--build=\"$gnuArch\" --with-config-file-path=\"$PHP_INI_DIR\" --enable-option-checking=fatal "
             "--with-mhash --with-pic --enable-ftp --enable-mbstring --enable-mysqlnd --with-password-argon2 "
             "--with-sodium=shared --with-pdo-sqlite=/usr --with-curl --with-iconv --with-openssl "
             "--with-readline --with-zlib --with-apxs2 --disable-cgi ... ; make -j \"$(nproc)\"; make install", False),
            ("/bin/sh -c #(nop) COPY multi:869bd2ad0b7dc8ac4a2b5d4ae1e5f29ec71d2e66853b6c4d0d5d1b2c3a6a4de5 "
             "in /usr/local/bin/ ", False),
            ('/bin/sh -c #(nop)  ENTRYPOINT ["docker-php-entrypoint"]', True),
            ("/bin/sh -c #(nop)  STOPSIGNAL SIGWINCH", True),
            ("/bin/sh -c #(nop)  WORKDIR /var/www/html", True),
            ("/bin/sh -c #(nop)  EXPOSE 80", True),
            ('/bin/sh -c #(nop)  CMD ["apache2-foreground"]', True),
        ],
    },
    "busybox": {
        "image": "quay.io/prometheus/busybox-linux-amd64:glibc", "os": "busybox 1.36.1",
        "size": 2.6, "pools": ["go"],
        "env": ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"],
        "history": [
            ("/bin/sh -c #(nop) ADD file:7e9002edaafd4e4579b65c8f0aaabde1aeb7fd3f8d95579f7a6c0b1d3ab3a0a1 in / ", False),
            ('/bin/sh -c #(nop)  CMD ["sh"]', True),
            ("/bin/sh -c #(nop)  LABEL maintainer=The Prometheus Authors <prometheus-developers@googlegroups.com>", True),
            ("/bin/sh -c #(nop) COPY dir:a2e2b8f0f8c7d3e1f6d4b9f0a1e3c5d7b9a1c3e5f7a9b1d3e5f7a9c1e3b5d7f9 in / ", False),
        ],
    },
    "jre11": {
        "image": "eclipse-temurin:11.0.13_8-jre-focal", "os": "ubuntu 20.04", "size": 89.7,
        "pools": ["ubuntu", "java"],
        "env": ["PATH=/opt/java/openjdk/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "LANG=en_US.UTF-8", "LANGUAGE=en_US:en", "LC_ALL=en_US.UTF-8",
                "JAVA_VERSION=jdk-11.0.13+8", "JAVA_HOME=/opt/java/openjdk"],
        "history": _UBUNTU_ROOT + [
            ("/bin/sh -c #(nop)  ENV LANG=en_US.UTF-8 LANGUAGE=en_US:en LC_ALL=en_US.UTF-8", True),
            ("/bin/sh -c apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y "
             "--no-install-recommends tzdata curl wget ca-certificates fontconfig locales "
             "&& echo \"en_US.UTF-8 UTF-8\" >> /etc/locale.gen && locale-gen en_US.UTF-8 "
             "&& rm -rf /var/lib/apt/lists/*", False),
            ("/bin/sh -c #(nop)  ENV JAVA_VERSION=jdk-11.0.13+8", True),
            ("/bin/sh -c set -eux; ARCH=\"$(dpkg --print-architecture)\"; ... curl -LfsSo "
             "/tmp/openjdk.tar.gz ${BINARY_URL}; ... tar -xf /tmp/openjdk.tar.gz --strip-components=1; "
             "rm -rf /tmp/openjdk.tar.gz;", False),
            ("/bin/sh -c #(nop)  ENV JAVA_HOME=/opt/java/openjdk PATH=/opt/java/openjdk/bin:/usr/local/sbin:"
             "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", True),
        ],
    },
    "jdk17": {
        "image": "eclipse-temurin:17.0.9_9-jdk-jammy", "os": "ubuntu 22.04", "size": 196.0,
        "pools": ["ubuntu", "node"],
        "env": ["PATH=/opt/java/openjdk/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "JAVA_HOME=/opt/java/openjdk", "LANG=en_US.UTF-8", "LANGUAGE=en_US:en",
                "LC_ALL=en_US.UTF-8", "JAVA_VERSION=jdk-17.0.9+9"],
        "history": _UBUNTU_ROOT + [
            ("ENV JAVA_HOME=/opt/java/openjdk", True),
            ("ENV PATH=/opt/java/openjdk/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", True),
            ("ENV LANG=en_US.UTF-8 LANGUAGE=en_US:en LC_ALL=en_US.UTF-8", True),
            ("RUN /bin/sh -c set -eux; apt-get update; DEBIAN_FRONTEND=noninteractive apt-get install -y "
             "--no-install-recommends tzdata curl wget ca-certificates fontconfig locales p11-kit binutils "
             "; echo \"en_US.UTF-8 UTF-8\" >> /etc/locale.gen; locale-gen en_US.UTF-8; "
             "rm -rf /var/lib/apt/lists/* # buildkit", False),
            ("ENV JAVA_VERSION=jdk-17.0.9+9", True),
            ("RUN /bin/sh -c set -eux; ARCH=\"$(dpkg --print-architecture)\"; ... wget --progress=dot:giga "
             "-O /tmp/openjdk.tar.gz ${BINARY_URL}; ... tar --extract --file /tmp/openjdk.tar.gz "
             "--directory \"$JAVA_HOME\" --strip-components 1 --no-same-owner ; rm -f /tmp/openjdk.tar.gz "
             "${JAVA_HOME}/lib/src.zip; # buildkit", False),
            ("RUN /bin/sh -c set -eux; echo \"Verifying install ...\"; fileEncoding=\"$(echo "
             "'System.out.println(System.getProperty(\"file.encoding\"))' | jshell -s -)\"; ... "
             "echo \"Complete.\" # buildkit", False),
            ('CMD ["jshell"]', True),
        ],
    },
}

# ---------------------------------------------------------------------------
# Repositories. Each entry:
#   base, desc, env (app env, appended/overriding base env), steps (Dockerfile
#   instructions after FROM; ENV lines are generated from env automatically),
#   cmd/entrypoint, workdir, expose, user, versions [(tags, days_ago, size_delta_mb)],
#   app_mb, pulls, force (CVE ids always present), scan (False = not scanned),
#   files (path->content for the application COPY layer).
# ---------------------------------------------------------------------------
REPOS = {
    # ---------------- library (mirrored base images) ----------------
    "library/alpine": {
        "base": "alpine", "desc": "Mirrored Alpine base image. Pin by digest in Dockerfiles.",
        "env": [], "steps": [], "app_mb": 0, "pulls": 4812, "base_only": True,
        "versions": [(["3.18.5", "3.18"], 301, 0), (["3.17.6"], 330, -0.1)],
    },
    "library/node": {
        "base": "node18", "desc": "Node.js 18 LTS (alpine) - base for ishop / mobapp services.",
        "env": [], "steps": [], "app_mb": 0, "pulls": 2264, "base_only": True,
        "versions": [(["18.19.0-alpine3.18", "18-alpine"], 290, 0), (["18.17.1-alpine3.18"], 402, -0.4)],
    },
    "library/python": {
        "base": "python311", "desc": "Python 3.11 slim (bookworm).", "env": [], "steps": [],
        "app_mb": 0, "pulls": 1530, "base_only": True,
        "versions": [(["3.11.6-slim-bookworm", "3.11-slim"], 288, 0)],
    },
    "library/dotnet-aspnet": {
        "base": "aspnet6", "desc": "ASP.NET Core 6 runtime (bookworm-slim). EOL Nov 2024 - migrate to 8.0.",
        "env": [], "steps": [], "app_mb": 0, "pulls": 1977, "base_only": True,
        "versions": [(["6.0.25-bookworm-slim", "6.0"], 296, 0), (["6.0.21-bullseye-slim"], 420, 2.1)],
    },
    "library/nginx": {
        "base": "nginx", "desc": "nginx stable (alpine).", "env": [], "steps": [], "app_mb": 0,
        "pulls": 1349, "base_only": True,
        "versions": [(["1.24.0-alpine", "stable-alpine"], 299, 0)],
    },
    # ---------------- ishop ----------------
    "ishop/api": {
        "base": "node18",
        "desc": "ishop.atbmarket.com public REST API (catalogue, cart, orders, loyalty bridge).\n"
                "Build: GitLab CI `ishop/api` -> `docker build -t harbor.atbmarket.com/ishop/api:$TAG .`\n"
                "Owner: ishop backend team (s.tkachenko).",
        "env": ["NODE_ENV=production", "PORT=3000",
                "MYSQL_DSN=mysql://ishop:rEQaZ55o7x_E53oC@10.0.7.118:3306/ishop",
                "REDIS_URL=redis://ishop-redis-p01:6379/2", "LOG_LEVEL=info", "TZ=Europe/Kyiv"],
        "workdir": "/srv/app", "user": "node", "expose": "3000",
        "steps": [("WORKDIR", "/srv/app"),
                  ("COPY", "package.json package-lock.json ./"),
                  ("RUN", "npm ci --omit=dev && npm cache clean --force"),
                  ("COPY", "dist/ ./dist/"),
                  ("USER", "node")],
        "cmd": ["node", "dist/server.js"], "app_mb": 38.4, "pulls": 6211,
        "force": ["CVE-2024-21508", "CVE-2024-29041"],
        "versions": [(["2.14.3", "latest"], 4, 0), (["2.14.2"], 18, -0.2), (["2.13.0"], 47, -1.6),
                     ([], 52, -1.7), (["2.12.5"], 91, -3.0)],
        "labels": ["prod"],
        "files": {"srv/app/package.json": '{\n  "name": "ishop-api",\n  "version": "2.14.3",\n'
                  '  "private": true,\n  "main": "dist/server.js",\n  "dependencies": {\n'
                  '    "axios": "1.5.1",\n    "body-parser": "1.20.1",\n    "express": "4.18.2",\n'
                  '    "ioredis": "5.3.2",\n    "joi": "17.10.2",\n    "mysql2": "3.6.0",\n'
                  '    "pino": "8.15.0",\n    "ws": "8.13.0"\n  }\n}\n'},
    },
    "ishop/web": {
        "base": "nginx", "desc": "ishop storefront SPA (static bundle served by nginx).",
        "env": ["TZ=Europe/Kyiv"],
        "steps": [("COPY", "nginx/default.conf /etc/nginx/conf.d/default.conf"),
                  ("COPY", "build/ /usr/share/nginx/html/")],
        "app_mb": 9.6, "pulls": 3120, "expose": "80",
        "versions": [(["5.3.1", "latest"], 6, 0), (["5.3.0"], 21, -0.1), (["5.2.4"], 60, -0.8)],
        "labels": ["prod"],
    },
    "ishop/worker": {
        "base": "node18", "desc": "Background jobs: order export to 1C, e-mail notifications, price sync.",
        "env": ["NODE_ENV=production", "QUEUE=ishop-jobs", "AMQP_HOST=mq-ishop-p01",
                "CONCURRENCY=8", "TZ=Europe/Kyiv"],
        "workdir": "/srv/worker", "user": "node",
        "steps": [("WORKDIR", "/srv/worker"), ("COPY", "package*.json ./"),
                  ("RUN", "npm ci --omit=dev"), ("COPY", "dist/ ./dist/"), ("USER", "node")],
        "cmd": ["node", "dist/worker.js"], "app_mb": 31.0, "pulls": 2088,
        "versions": [(["1.9.0", "latest"], 11, 0), (["1.8.2"], 40, -0.3)],
        "labels": ["prod"],
    },
    "ishop/search-indexer": {
        "base": "python311", "desc": "Rebuilds the Elasticsearch product index nightly.",
        "env": ["PYTHONDONTWRITEBYTECODE=1", "PYTHONUNBUFFERED=1",
                "ES_URL=http://es-ishop-p01:9200", "INDEX_PREFIX=ishop-products", "BATCH_SIZE=500"],
        "workdir": "/opt/indexer",
        "steps": [("WORKDIR", "/opt/indexer"), ("COPY", "requirements.txt ."),
                  ("RUN", "pip install --no-cache-dir -r requirements.txt"), ("COPY", "indexer/ ./indexer/")],
        "cmd": ["python", "-m", "indexer", "--full"], "app_mb": 22.3, "pulls": 412,
        "versions": [(["0.7.2", "latest"], 33, 0), (["0.7.1"], 75, -0.2)],
    },
    "ishop/img-resizer": {
        "base": "node18", "desc": "On-the-fly product image thumbnails (sharp).",
        "env": ["NODE_ENV=production", "PORT=8080", "CACHE_DIR=/var/cache/img", "MAX_WIDTH=1600"],
        "workdir": "/srv/app", "user": "node", "expose": "8080",
        "steps": [("WORKDIR", "/srv/app"), ("RUN", "apk add --no-cache vips"),
                  ("COPY", "package*.json ./"), ("RUN", "npm ci --omit=dev"), ("COPY", "src/ ./src/"),
                  ("USER", "node")],
        "cmd": ["node", "src/index.js"], "app_mb": 54.8, "pulls": 980,
        "versions": [(["1.2.0", "latest"], 64, 0), (["1.1.3"], 140, -2.0)],
        "labels": ["prod"],
    },
    # ---------------- storeplus ----------------
    "storeplus/excise.api": {
        "base": "aspnet6",
        "desc": "Store-Plus excise stamp registry API (scanned excise marks -> ASU database).\n"
                "Image built by `storeplus/excise` pipeline, deployed to sp-k8s-p01.",
        "env": ["ASPNETCORE_ENVIRONMENT=Production",
                "PG_DSN=postgresql://asu:Qw123456@pgsql-dev.store-plus.atbmarket.com:5432/asu",
                "Logging__LogLevel__Default=Information", "TZ=Europe/Kyiv"],
        "workdir": "/app", "expose": "80",
        "steps": [("WORKDIR", "/app"), ("EXPOSE", "80"), ("COPY", "--from=build /app/publish .")],
        "entrypoint": ["dotnet", "Excise.Api.dll"], "app_mb": 24.9, "pulls": 3874,
        "force": ["CVE-2024-32655", "CVE-2024-21907"],
        "versions": [(["3.2.0", "latest"], 26, 0), (["3.1.7"], 58, -0.1), (["3.1.5"], 103, -0.4)],
        "labels": ["prod"],
    },
    "storeplus/gateway": {
        "base": "aspnet6", "desc": "YARP reverse proxy in front of Store-Plus APIs.",
        "env": ["ASPNETCORE_ENVIRONMENT=Production", "ReverseProxy__Clusters__excise__Destinations__d1__Address=http://excise-api",
                "TZ=Europe/Kyiv"],
        "workdir": "/app", "expose": "80",
        "steps": [("WORKDIR", "/app"), ("EXPOSE", "80"), ("COPY", "--from=build /app/publish .")],
        "entrypoint": ["dotnet", "StorePlus.Gateway.dll"], "app_mb": 8.1, "pulls": 3511,
        "versions": [(["1.4.2", "latest"], 39, 0), (["1.4.1"], 110, -0.1)],
        "labels": ["prod"],
    },
    "storeplus/inventory.api": {
        "base": "aspnet6", "desc": "Shelf / warehouse stock API for Store-Plus terminals.",
        "env": ["ASPNETCORE_ENVIRONMENT=Production", "Inventory__PageSize=200",
                "Inventory__CacheSeconds=30", "TZ=Europe/Kyiv"],
        "workdir": "/app", "expose": "80",
        "steps": [("WORKDIR", "/app"), ("EXPOSE", "80"), ("COPY", "--from=build /app/publish .")],
        "entrypoint": ["dotnet", "Inventory.Api.dll"], "app_mb": 19.7, "pulls": 2903,
        "versions": [(["2.0.3", "latest"], 15, 0), (["2.0.1"], 44, -0.2), (["1.9.9"], 120, -2.5)],
        "labels": ["prod"],
    },
    "storeplus/pos-sync": {
        "base": "jre11", "desc": "LEGACY - POS receipts sync (Spring Boot). Replaced by inventory.api, "
                                 "still runs on 3 regional nodes.",
        "env": ["SPRING_PROFILES_ACTIVE=prod", "JAVA_OPTS=-Xms256m -Xmx768m", "SYNC_INTERVAL=300",
                "TZ=Europe/Kyiv"],
        "workdir": "/opt/pos-sync", "expose": "8080",
        "steps": [("WORKDIR", "/opt/pos-sync"), ("COPY", "target/pos-sync-0.9.4.jar app.jar"),
                  ("EXPOSE", "8080")],
        "entrypoint": ["sh", "-c", "java $JAVA_OPTS -jar app.jar"], "app_mb": 61.2, "pulls": 840,
        "force": ["CVE-2021-44228", "CVE-2021-45046", "CVE-2022-22965"],
        "versions": [(["0.9.4", "latest"], 1006, 0), (["0.9.3"], 1080, -0.3)],
        "labels": ["deprecated"],
    },
    # ---------------- mobapp ----------------
    "mobapp/cicd": {
        "base": "jdk17",
        "desc": "Build image for the ATB mobile app (React Native: Android SDK + Node + Gradle).\n"
                "Used by the mobile pipeline to build/sign the APK and push the backend images.",
        "env": ["CI=true", "ANDROID_SDK_ROOT=/opt/android-sdk", "ANDROID_BUILD_TOOLS=34.0.0",
                "GRADLE_USER_HOME=/cache/gradle", "NODE_MAJOR=18",
                "REG_BASIC=reg_user:basic*88password!prod99"],
        "workdir": "/builds",
        "steps": [("RUN", "apt-get update && apt-get install -y --no-install-recommends git unzip "
                          "openssh-client && rm -rf /var/lib/apt/lists/*"),
                  ("RUN", "curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && apt-get install -y nodejs "
                          "&& npm i -g yarn@1.22.19"),
                  ("RUN", "mkdir -p $ANDROID_SDK_ROOT/cmdline-tools && cd /tmp && curl -fsSLo tools.zip "
                          "https://dl.google.com/android/repository/commandlinetools-linux-10406996_latest.zip "
                          "&& unzip -q tools.zip -d $ANDROID_SDK_ROOT/cmdline-tools && yes | "
                          "$ANDROID_SDK_ROOT/cmdline-tools/cmdline-tools/bin/sdkmanager "
                          "\"platforms;android-34\" \"build-tools;34.0.0\" \"platform-tools\""),
                  ("COPY", "scripts/ /usr/local/bin/"),
                  ("WORKDIR", "/builds")],
        "cmd": ["bash"], "app_mb": 912.0, "pulls": 1460,
        "versions": [(["2024.09", "latest"], 21, 0), (["2024.06"], 110, -14.0), (["2023.12"], 300, -61.0)],
    },
    "mobapp/backend": {
        "base": "node18", "desc": "BFF for the mobile app (auth, catalogue, push tokens).",
        "env": ["NODE_ENV=production", "PORT=3000", "ISHOP_API=http://ishop-api.ishop.svc:3000",
                "PUSH_GATEWAY=http://push-gateway:8080", "TZ=Europe/Kyiv"],
        "workdir": "/srv/app", "user": "node", "expose": "3000",
        "steps": [("WORKDIR", "/srv/app"), ("COPY", "package*.json ./"), ("RUN", "npm ci --omit=dev"),
                  ("COPY", "build/ ./build/"), ("USER", "node")],
        "cmd": ["node", "build/main.js"], "app_mb": 35.1, "pulls": 2780,
        "versions": [(["4.6.0", "latest"], 9, 0), (["4.5.2"], 30, -0.4)],
        "labels": ["prod"],
    },
    "mobapp/push-gateway": {
        "base": "busybox", "desc": "FCM/APNs fan-out service (Go).",
        "env": ["LISTEN_ADDR=:8080", "FCM_PROJECT=atb-market-mobile", "APNS_TOPIC=ua.atbmarket.app"],
        "workdir": "/", "expose": "8080", "user": "nobody",
        "steps": [("COPY", "push-gateway /bin/push-gateway"), ("USER", "nobody"), ("EXPOSE", "8080")],
        "entrypoint": ["/bin/push-gateway"], "app_mb": 14.2, "pulls": 1190,
        "versions": [(["1.3.1", "latest"], 57, 0)],
        "labels": ["prod"],
    },
    # ---------------- supplier-portal ----------------
    "supplier-portal/suitecrm": {
        "base": "php81", "desc": "Supplier portal (SuiteCRM 7.x + custom modules). Prod host: sp-web-p01.",
        "env": ["APACHE_DOCUMENT_ROOT=/var/www", "PHP_MEMORY_LIMIT=512M", "PHP_UPLOAD_MAX_FILESIZE=64M",
                "TZ=Europe/Kyiv"],
        "workdir": "/var/www",
        "steps": [("RUN", "docker-php-ext-install mysqli pdo_mysql zip gd soap ldap imap"),
                  ("RUN", "a2enmod rewrite headers"),
                  ("COPY", "--chown=www-data:www-data suitecrm/ /var/www/"),
                  ("WORKDIR", "/var/www")],
        "app_mb": 118.0, "pulls": 211, "force": ["CVE-2023-3824"],
        "versions": [(["7.14.2", "latest"], 72, 0), (["7.13.4"], 240, -5.0)],
    },
    "supplier-portal/cron": {
        "base": "php81", "desc": "SuiteCRM scheduler (cron.php every minute).",
        "env": ["APACHE_DOCUMENT_ROOT=/var/www", "CRON_SCHEDULE=* * * * *", "TZ=Europe/Kyiv"],
        "workdir": "/var/www",
        "steps": [("RUN", "apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*"),
                  ("COPY", "crontab /etc/cron.d/suitecrm")],
        "cmd": ["cron", "-f"], "app_mb": 3.0, "pulls": 98,
        "versions": [(["7.14.2", "latest"], 72, 0)],
    },
    # ---------------- education ----------------
    "education/moodle": {
        "base": "php81", "desc": "edu.atbmarket.com - Moodle 4.1 LTS with local plugins (moco_news, atb_theme).",
        "env": ["MOODLE_WWWROOT=https://education.atbmarket.com", "MOODLE_DATAROOT=/var/moodledata",
                "PHP_MAX_INPUT_VARS=5000", "TZ=Europe/Kyiv"],
        "workdir": "/var/www/html",
        "steps": [("RUN", "docker-php-ext-install mysqli opcache intl zip gd soap exif"),
                  ("COPY", "--chown=www-data:www-data moodle/ /var/www/html/"),
                  ("VOLUME", "/var/moodledata")],
        "app_mb": 286.0, "pulls": 154,
        "versions": [(["4.1.6", "latest"], 120, 0), (["4.1.3"], 260, -3.0)],
    },
    # ---------------- monitoring ----------------
    "monitoring/node-exporter": {
        "base": "busybox", "desc": "Prometheus node_exporter, ATB build with textfile collectors.",
        "env": [], "expose": "9100", "user": "nobody",
        "steps": [("COPY", "node_exporter /bin/node_exporter"), ("EXPOSE", "9100"), ("USER", "nobody")],
        "entrypoint": ["/bin/node_exporter"], "app_mb": 19.9, "pulls": 9120,
        "versions": [(["1.7.0", "latest"], 140, 0), (["1.6.1"], 260, -0.3)],
    },
    "monitoring/blackbox-exporter": {
        "base": "busybox", "desc": "HTTP/TCP/ICMP probes for public endpoints.",
        "env": [], "expose": "9115", "user": "nobody",
        "steps": [("COPY", "blackbox_exporter /bin/blackbox_exporter"),
                  ("COPY", "blackbox.yml /etc/blackbox_exporter/config.yml"), ("EXPOSE", "9115"),
                  ("USER", "nobody")],
        "entrypoint": ["/bin/blackbox_exporter"], "cmd": ["--config.file=/etc/blackbox_exporter/config.yml"],
        "app_mb": 21.4, "pulls": 702,
        "versions": [(["0.24.0", "latest"], 150, 0)],
    },
    "monitoring/zabbix-agent2": {
        "base": "alpine", "desc": "Zabbix agent 2 for container hosts (passive checks).",
        "env": ["ZBX_SERVER_HOST=zb-app-p01", "ZBX_HOSTNAMEITEM=system.hostname",
                "ZBX_PASSIVE_ALLOW=true", "ZBX_ACTIVE_ALLOW=false"],
        "expose": "10050", "user": "zabbix",
        "steps": [("RUN", "apk add --no-cache zabbix-agent2=6.0.18-r0 tini"),
                  ("COPY", "zabbix_agent2.conf /etc/zabbix/zabbix_agent2.conf"),
                  ("EXPOSE", "10050"), ("USER", "zabbix")],
        "entrypoint": ["/sbin/tini", "--"], "cmd": ["zabbix_agent2", "-f"], "app_mb": 24.1, "pulls": 2310,
        "versions": [(["6.0.18", "latest"], 180, 0)],
    },
    "monitoring/promtail": {
        "base": "busybox", "desc": "Log shipper for k8s nodes.",
        "env": ["LOKI_URL=http://loki-p01:3100/loki/api/v1/push"],
        "steps": [("COPY", "promtail /usr/bin/promtail"), ("COPY", "config.yml /etc/promtail/config.yml")],
        "entrypoint": ["/usr/bin/promtail"], "cmd": ["-config.file=/etc/promtail/config.yml"],
        "app_mb": 72.6, "pulls": 4400, "scan": False,
        "versions": [(["2.9.2", "latest"], 95, 0)],
    },
    # ---------------- infra (private) ----------------
    "infra/haproxy": {
        "base": "alpine", "desc": "Edge HAProxy (TLS offload for *.atbmarket.com).",
        "env": ["HAPROXY_VERSION=2.8.3"], "expose": "443",
        "steps": [("RUN", "apk add --no-cache haproxy=2.8.3-r0 socat"),
                  ("COPY", "haproxy.cfg /usr/local/etc/haproxy/haproxy.cfg"), ("EXPOSE", "80 443")],
        "cmd": ["haproxy", "-f", "/usr/local/etc/haproxy/haproxy.cfg", "-W", "-db"],
        "app_mb": 9.2, "pulls": 388,
        "versions": [(["2.8.3-atb2", "latest"], 63, 0), (["2.8.3-atb1"], 77, 0)],
        "labels": ["prod"],
    },
    "infra/certbot": {
        "base": "python311", "desc": "Let's Encrypt renewals (DNS-01).",
        "env": ["CERTBOT_VERSION=2.7.4", "RENEW_CRON=17 3 * * *"],
        "steps": [("RUN", "pip install --no-cache-dir certbot==2.7.4 certbot-dns-rfc2136")],
        "cmd": ["certbot", "renew", "--quiet"], "app_mb": 18.4, "pulls": 120,
        "versions": [(["2.7.4", "latest"], 200, 0)],
    },
    "infra/ansible-runner": {
        "base": "python311", "desc": "Ansible execution image for infra playbooks.",
        "env": ["ANSIBLE_FORCE_COLOR=true", "ANSIBLE_HOST_KEY_CHECKING=False",
                "ANSIBLE_STDOUT_CALLBACK=yaml"],
        "steps": [("RUN", "apt-get update && apt-get install -y --no-install-recommends openssh-client "
                          "sshpass rsync && rm -rf /var/lib/apt/lists/*"),
                  ("RUN", "pip install --no-cache-dir ansible-core==2.15.5 jmespath netaddr")],
        "cmd": ["ansible-playbook", "--version"], "app_mb": 96.0, "pulls": 512,
        "versions": [(["2.15.5", "latest"], 110, 0)],
    },
    # ---------------- loyalty (private) ----------------
    "loyalty/bonus-api": {
        "base": "aspnet6", "desc": "ATB loyalty card bonus balance API.",
        "env": ["ASPNETCORE_ENVIRONMENT=Staging",
                "RABBITMQ_URL=amqp://bonus:Bonus_Stg2023@mq-loyalty-s01:5672/bonus",
                "TZ=Europe/Kyiv"],
        "workdir": "/app", "expose": "80",
        "steps": [("WORKDIR", "/app"), ("COPY", "--from=build /app/publish .")],
        "entrypoint": ["dotnet", "Loyalty.Bonus.Api.dll"], "app_mb": 17.0, "pulls": 77,
        "versions": [(["0.8.1", "latest"], 190, 0)],
        "labels": ["staging"],
    },
    "loyalty/coupon-worker": {
        "base": "node18", "desc": "Personal coupon generation worker.",
        "env": ["NODE_ENV=production", "BATCH=1000"], "workdir": "/srv/app", "user": "node",
        "steps": [("WORKDIR", "/srv/app"), ("COPY", "package*.json ./"), ("RUN", "npm ci --omit=dev"),
                  ("COPY", "dist/ ./dist/"), ("USER", "node")],
        "cmd": ["node", "dist/index.js"], "app_mb": 26.0, "pulls": 40,
        "versions": [(["0.3.0", "latest"], 205, 0)],
    },
    # ---------------- dockerhub-proxy (proxy cache) ----------------
    "dockerhub-proxy/library/redis": {
        "base": "alpine", "desc": "", "proxy": True,
        "env": ["REDIS_VERSION=7.2.3"], "expose": "6379",
        "steps": [("RUN", "addgroup -S -g 1000 redis && adduser -S -G redis -u 999 redis"),
                  ("RUN", "apk add --no-cache redis=7.2.3-r0"), ("EXPOSE", "6379")],
        "cmd": ["redis-server"], "app_mb": 11.6, "pulls": 702, "scan": False,
        "versions": [(["7.2-alpine"], 34, 0)],
    },
    "dockerhub-proxy/library/postgres": {
        "base": "alpine", "desc": "", "proxy": True,
        "env": ["PG_MAJOR=15", "PG_VERSION=15.5", "PGDATA=/var/lib/postgresql/data", "LANG=en_US.utf8"],
        "expose": "5432",
        "steps": [("RUN", "set -eux; addgroup -g 70 -S postgres; adduser -u 70 -S -D -G postgres "
                          "-H -h /var/lib/postgresql -s /bin/sh postgres"),
                  ("RUN", "apk add --no-cache --virtual .build-deps bison coreutils dpkg-dev gcc "
                          "make openssl-dev ... && make install-world-bin"),
                  ("VOLUME", "/var/lib/postgresql/data"), ("EXPOSE", "5432")],
        "entrypoint": ["docker-entrypoint.sh"], "cmd": ["postgres"], "app_mb": 86.0, "pulls": 233,
        "scan": False, "versions": [(["15-alpine"], 70, 0)],
    },
}

# Pushers (for audit logs) per project
PUSHERS = {
    "library": "o.bondarenko", "ishop": "robot$ishop+gitlab-ci", "storeplus": "robot$storeplus+gitlab-ci",
    "mobapp": "reg_user", "supplier-portal": "y.hnatiuk", "education": "i.melnyk",
    "monitoring": "robot$monitoring+ci", "infra": "o.bondarenko", "loyalty": "v.kravets",
    "dockerhub-proxy": "admin",
}
PULLERS = {
    "library": ["robot$ishop+gitlab-ci", "robot$storeplus+gitlab-ci", "i.melnyk"],
    "supplier-portal": ["robot$supplier-portal+deploy"], "infra": ["robot$infra+ansible"],
    "mobapp": ["reg_user", "robot$k8s-prod-puller"], "education": ["i.melnyk"],
    "loyalty": ["k.shevchuk"],
}
DEFAULT_PULLERS = ["robot$k8s-prod-puller"]
