"""Step 8 - sh-harb-p01 Harbor container registry (Harbor 2.x emulation).

A browsable Harbor portal + Harbor API v2.0 + Docker Registry v2 API over an
in-memory catalogue (harbor_data.py). Public projects can be browsed and
pulled anonymously; several images bake DB credentials into their image config
ENV, visible in Build History, the artifact API, manifests/config blobs and
the convenience /image/<repo>/env endpoint.
"""
import base64
import gzip
import hashlib
import io
import json
import os
import tarfile
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from html import escape
from urllib.parse import quote, unquote

from flask import (Flask, Response, abort, jsonify, redirect, request,
                   session)

import atblog
import harbor_data as D

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config.update(SESSION_COOKIE_NAME="sid", SESSION_COOKIE_HTTPONLY=True)

REF = datetime(2026, 10, 6, 9, 12, 0, tzinfo=timezone.utc)   # build timeline anchor
BOOT = datetime.now(timezone.utc)
SEVS = ["Critical", "High", "Medium", "Low", "None", "Unknown"]
SEV_RANK = {s: i for i, s in enumerate(SEVS)}
REPORT_MT = "application/vnd.security.vulnerability.report; version=1.1"
MANIFEST_MT = "application/vnd.docker.distribution.manifest.v2+json"
CONFIG_MT = "application/vnd.docker.container.image.v1+json"
LAYER_MT = "application/vnd.docker.image.rootfs.diff.tar.gzip"
ICON = "sha256:0048162a053eef4d4ce3fe7518615bef084403614f8bca43b40ae2e762e11e06"

# Env keys that carry hard-coded credentials (feeds harbor.creds_in_layer).
_SECRET_KEYS = ("PG_DSN", "MYSQL_DSN", "REG_BASIC", "RABBITMQ_URL")

BASE_RUNTIME = {  # inherited Cmd / Entrypoint / WorkingDir of each base image
    "alpine": (["/bin/sh"], None, ""), "node18": (["node"], ["docker-entrypoint.sh"], ""),
    "python311": (["python3"], None, ""), "aspnet6": (None, None, ""),
    "nginx": (["nginx", "-g", "daemon off;"], ["/docker-entrypoint.sh"], ""),
    "php81": (["apache2-foreground"], ["docker-php-entrypoint"], "/var/www/html"),
    "busybox": (["sh"], None, ""), "jre11": (None, None, ""), "jdk17": (["jshell"], None, ""),
}


def _h(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _hn(*parts):
    return int(_h(*parts)[:8], 16)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _ui_time(dt):
    if dt is None:
        return ""
    h = dt.hour % 12 or 12
    return f"{dt.month}/{dt.day}/{dt.strftime('%y')}, {h}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def _fmt_size(n):
    for unit, div in (("GiB", 1 << 30), ("MiB", 1 << 20), ("KiB", 1 << 10)):
        if n >= div:
            return f"{n / div:.2f}{unit}"
    return f"{n}B"


# ---------------------------------------------------------------------------
# Catalogue build (deterministic, done once at import)
# ---------------------------------------------------------------------------
_LAYER_CACHE = {}


def _make_layer(key, files=None, dirs=()):
    """Deterministic gzipped tar -> (gz bytes, diff_id, digest)."""
    if key in _LAYER_CACHE:
        return _LAYER_CACHE[key]
    raw = io.BytesIO()
    mtime = 1600000000 + _hn("layer", key) % 90000000
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        seen = set()
        for d in dirs:
            d = d.strip("/")
            if not d or d in seen:
                continue
            seen.add(d)
            ti = tarfile.TarInfo(d + "/")
            ti.type, ti.mode, ti.mtime = tarfile.DIRTYPE, 0o755, mtime
            tf.addfile(ti)
        for path, content in sorted((files or {}).items()):
            data = content.encode()
            ti = tarfile.TarInfo(path)
            ti.size, ti.mode, ti.mtime = len(data), 0o644, mtime
            tf.addfile(ti, io.BytesIO(data))
    raw_b = raw.getvalue()
    gz = io.BytesIO()
    with gzip.GzipFile(fileobj=gz, mode="wb", mtime=0) as g:
        g.write(raw_b)
    gz_b = gz.getvalue()
    out = (gz_b, "sha256:" + hashlib.sha256(raw_b).hexdigest(),
           "sha256:" + hashlib.sha256(gz_b).hexdigest())
    _LAYER_CACHE[key] = out
    return out


def _dirs_from(cmd):
    out = []
    cmd = cmd.replace("/bin/sh -c", " ").replace("# buildkit", " ")
    for tok in cmd.replace('"', " ").replace(";", " ").split():
        if tok.startswith("/") and len(tok) > 1 and "$" not in tok:
            parts = tok.strip("/").split("/")
            for i in range(1, min(len(parts), 4) + 1):
                out.append("/".join(parts[:i]))
    return out or ["tmp"]


def _merge_env(base_env, app_env):
    order, vals = [], {}
    for item in base_env + app_env:
        k, _, v = item.partition("=")
        if k not in vals:
            order.append(k)
        vals[k] = v
    return [f"{k}={vals[k]}" for k in order]


BLOBS = {}          # digest -> (bytes, media type)
REPOS = {}          # repo name -> dict
ARTIFACTS = {}      # repo name -> [artifact dicts], newest first
PROJECTS = {p["name"]: p for p in D.PROJECTS}
PROJECTS_BY_ID = {p["id"]: p for p in D.PROJECTS}


def _vulns_for(repo, spec, base, idx):
    if spec.get("scan") is False or spec.get("proxy"):
        return None
    pools = base["pools"][:1] if spec.get("base_only") else base["pools"]
    force = set(spec.get("force", []))
    thr = 30 + 14 * idx
    out = []
    for vid, (pool, pkg, ver, fix, sev, score, cwe, title) in D.VULNS.items():
        if pool not in pools:
            continue
        if vid in force or _hn(repo, vid) % 100 < thr or (spec.get("base_only") and _hn(vid) % 100 < 60):
            out.append({"id": vid.split("@")[0], "package": pkg, "version": ver, "fix_version": fix,
                        "severity": sev, "score": score, "cwe": cwe, "description": title})
    out.sort(key=lambda v: (SEV_RANK[v["severity"]], -v["score"], v["id"]))
    return out


def _build():
    rid = 0
    aid = 0
    for repo, spec in D.REPOS.items():
        rid += 1
        proj = PROJECTS[repo.split("/", 1)[0]]
        base = D.BASES[spec["base"]]
        b_cmd, b_ep, b_wd = BASE_RUNTIME[spec["base"]]
        env = _merge_env(base["env"], spec.get("env", []))
        REPOS[repo] = {"id": rid, "name": repo, "project": proj, "spec": spec,
                       "short": repo.split("/", 1)[1], "desc": spec.get("desc", ""),
                       "pulls": spec.get("pulls", 0)}
        arts = []
        for idx, (tags, days, delta) in enumerate(spec["versions"]):
            aid += 1
            ver = tags[0] if tags else f"untagged-{idx}"
            created = REF - timedelta(days=days, minutes=_hn(repo, ver, "m") % 600)
            push = created + timedelta(seconds=40 + _hn(repo, ver, "p") % 200)
            # --- history -------------------------------------------------
            hist = list(base["history"])
            salt_base = spec["base"] if not spec.get("base_only") else f"{repo}:{ver}"
            n_base = len(hist)
            if not spec.get("base_only"):
                labels = {}
                if not spec.get("proxy"):
                    labels = {"org.opencontainers.image.version": ver,
                              "org.opencontainers.image.revision": _h(repo, ver, "rev")[:40],
                              "org.opencontainers.image.vendor": "ATB-Market",
                              "org.opencontainers.image.created": _iso(created)}
                    hist.append(("LABEL " + " ".join(f"{k}={v}" for k, v in labels.items()), True))
                for e in spec.get("env", []):
                    hist.append((f"ENV {e}", True))
                for instr, arg in spec.get("steps", []):
                    if instr == "RUN":
                        hist.append((f"RUN /bin/sh -c {arg} # buildkit", False))
                    elif instr in ("COPY", "ADD", "WORKDIR"):
                        hist.append((f"{instr} {arg} # buildkit", False))
                    else:
                        hist.append((f"{instr} {arg}", True))
                if spec.get("expose") and not any(s[0] == "EXPOSE" for s in spec.get("steps", [])):
                    hist.append((f"EXPOSE map[{spec['expose']}/tcp:{{}}]", True))
                if spec.get("entrypoint"):
                    hist.append(("ENTRYPOINT " + json.dumps(spec["entrypoint"]), True))
                if spec.get("cmd"):
                    hist.append(("CMD " + json.dumps(spec["cmd"]), True))
            else:
                labels = {}
            # --- layers ----------------------------------------------------
            nonempty = [i for i, (_, empty) in enumerate(hist) if not empty]
            app_layers = [i for i in nonempty if i >= n_base]
            base_layers = [i for i in nonempty if i < n_base]
            last_copy = max((i for i in app_layers if hist[i][0].startswith("COPY")), default=None)
            total_mb = base["size"] + spec.get("app_mb", 0) + delta
            layers, diff_ids, nominal = [], [], []
            for i in nonempty:
                cmd = hist[i][0]
                if i == 0 or "ADD file:" in cmd and i < n_base:
                    files = {"etc/os-release": f'PRETTY_NAME="{base["os"]}"\nNAME="{base["os"].split()[0]}"\n'
                                               f'VERSION_ID="{base["os"].split()[-1]}"\n'}
                    lay = _make_layer(("base", salt_base, i), files=files, dirs=["bin", "etc", "usr", "var"])
                elif i == last_copy and spec.get("files"):
                    lay = _make_layer(("app", repo, ver, i), files=spec["files"], dirs=_dirs_from(cmd))
                elif i < n_base:
                    lay = _make_layer(("base", salt_base, i), dirs=_dirs_from(cmd))
                else:
                    lay = _make_layer(("app", repo, ver, i), dirs=_dirs_from(cmd))
                if i < n_base:
                    w = base["size"] / max(len(base_layers), 1)
                    share = w * (0.55 if i == 0 and len(base_layers) > 1 else 1)
                else:
                    share = (spec.get("app_mb", 0) + delta) / max(len(app_layers), 1)
                nominal.append(max(int(share * 1048576), 32))
                layers.append(lay)
                diff_ids.append(lay[1])
                BLOBS[lay[2]] = (lay[0], LAYER_MT)
            size = max(int(total_mb * 1048576), sum(nominal))
            # --- config / manifest -----------------------------------------
            cmd_v = spec.get("cmd") if spec.get("cmd") else (None if spec.get("entrypoint") else b_cmd)
            ep_v = spec.get("entrypoint") or b_ep
            exposed = {}
            if spec.get("expose"):
                for p in str(spec["expose"]).split():
                    exposed[f"{p}/tcp"] = {}
            cfg_inner = {"Env": env, "Cmd": cmd_v, "WorkingDir": spec.get("workdir", b_wd)}
            if ep_v:
                cfg_inner["Entrypoint"] = ep_v
            if exposed:
                cfg_inner["ExposedPorts"] = exposed
            if spec.get("user"):
                cfg_inner["User"] = spec["user"]
            if labels:
                cfg_inner["Labels"] = labels
            h_created = created - timedelta(minutes=len(hist))
            history = []
            for j, (cb, empty) in enumerate(hist):
                t = (REF - timedelta(days=300 + _hn(spec["base"]) % 60, minutes=len(hist) - j)) \
                    if j < n_base and not spec.get("base_only") else h_created + timedelta(seconds=j * 7)
                ent = {"created": _iso(t), "created_by": cb}
                if "# buildkit" in cb:
                    ent["comment"] = "buildkit.dockerfile.v0"
                if empty:
                    ent["empty_layer"] = True
                history.append(ent)
            config = {"architecture": "amd64", "config": cfg_inner, "created": _iso(created),
                      "history": history, "os": "linux",
                      "rootfs": {"type": "layers", "diff_ids": diff_ids}}
            cfg_b = json.dumps(config, indent=None).encode()
            cfg_d = "sha256:" + hashlib.sha256(cfg_b).hexdigest()
            BLOBS[cfg_d] = (cfg_b, CONFIG_MT)
            manifest = {"schemaVersion": 2, "mediaType": MANIFEST_MT, "name": repo,
                        "config": {"mediaType": CONFIG_MT, "size": len(cfg_b), "digest": cfg_d,
                                   "Env": env, "Cmd": cmd_v or ep_v},
                        "layers": [{"mediaType": LAYER_MT, "size": len(l[0]), "digest": l[2]}
                                   for l in layers]}
            man_b = json.dumps(manifest, indent=3).encode()
            digest = "sha256:" + hashlib.sha256(man_b).hexdigest()
            vulns = _vulns_for(repo, spec, base, idx)
            if vulns is not None:
                scan_end = push + timedelta(seconds=25 + _hn(digest) % 90) if proj["auto_scan"] \
                    else REF - timedelta(days=_hn(digest) % 6, hours=6)
                if scan_end < push:
                    scan_end = push + timedelta(minutes=3)
            else:
                scan_end = None
            pull_age = timedelta(minutes=5 + _hn(digest, "pull") % 2000) if idx == 0 else \
                timedelta(days=min(days, 3 + idx * 9), minutes=_hn(digest, "pull") % 900)
            pulled = (spec.get("pulls", 0) > 0) and not (idx >= 3)
            art_labels = []
            if idx == 0:
                art_labels = list(spec.get("labels", []))
            elif idx == len(spec["versions"]) - 1 and idx >= 2:
                art_labels = ["deprecated"]
            arts.append({
                "id": aid, "repo": repo, "idx": idx, "tags": tags, "digest": digest,
                "created": created, "push": push, "pull_age": pull_age if pulled else None,
                "size": size, "config": config, "config_b": cfg_b, "config_digest": cfg_d,
                "manifest_b": man_b, "env": env, "vulns": vulns, "scan_end": scan_end,
                "labels": art_labels, "nominal": nominal, "history": hist,
            })
        ARTIFACTS[repo] = arts


_build()

# Backwards-compatible view: repo -> env of newest artifact.
CATALOG = {r: a[0]["env"] for r, a in ARTIFACTS.items()}


def _pull_time(art):
    return (datetime.now(timezone.utc) - art["pull_age"]) if art["pull_age"] else None


def _find_art(repo, ref):
    for a in ARTIFACTS.get(repo, []):
        if a["digest"] == ref or ref in a["tags"]:
            return a
    return None


def _scan_summary(art):
    if art["vulns"] is None:
        return None
    counts = {}
    for v in art["vulns"]:
        counts[v["severity"]] = counts.get(v["severity"], 0) + 1
    top = min(counts, key=lambda s: SEV_RANK[s]) if counts else "None"
    return {"total": len(art["vulns"]), "fixable": sum(1 for v in art["vulns"] if v["fix_version"]),
            "counts": counts, "severity": top}


def _leaked_secrets(env):
    out = []
    for item in env:
        key, _, val = item.partition("=")
        if key in _SECRET_KEYS:
            out.append(val)
    return out


def _log_pull(event, repo, ip, env=None, **extra):
    atblog.log(event, ip, repo=repo, **extra)
    for secret in _leaked_secrets(env if env is not None else CATALOG[repo]):
        atblog.log("harbor.creds_in_layer", ip, repo=repo, secret=secret,
                   msg="hard-coded DB credentials found in image config")


# ---------------------------------------------------------------------------
# Auth / visibility
# ---------------------------------------------------------------------------
def _check_pw(user, pw):
    u = D.USERS.get(user)
    return bool(u and u.get("pw") and u["pw"] == pw)


def current_user():
    if "u" in session and session["u"] in D.USERS:
        return session["u"]
    auth = request.authorization
    if auth and auth.type == "basic" and auth.username:
        if _check_pw(auth.username, auth.password or ""):
            return auth.username
        atblog.log("harbor.login_fail", atblog.client_ip(request), user=auth.username,
                   via="basic", path=request.path)
    return None


def is_admin(user):
    return bool(user and D.USERS.get(user, {}).get("admin"))


def role_in(user, proj):
    if not user:
        return None
    for name, role in proj["members"]:
        if name == user:
            return role
    return "Project Admin" if is_admin(user) else None


def can_see(user, proj):
    return proj["public"] or role_in(user, proj) is not None


def visible_projects(user):
    return [p for p in D.PROJECTS if can_see(user, p)]


def project_repos(proj):
    return [r for r in REPOS.values() if r["project"] is proj]


def _proj_lookup(key):
    key = unquote(str(key))
    if key.isdigit() and int(key) in PROJECTS_BY_ID:
        return PROJECTS_BY_ID[int(key)]
    return PROJECTS.get(key)


def _proj_usage(proj):
    seen, total = set(), 0
    for r in project_repos(proj):
        for a in ARTIFACTS[r["name"]]:
            for n, d in zip(a["nominal"], [x["digest"] for x in json.loads(a["manifest_b"])["layers"]]):
                if d not in seen:
                    seen.add(d)
                    total += n
            total += len(a["config_b"])
    return total


# ---------------------------------------------------------------------------
# HTML shell
# ---------------------------------------------------------------------------
_CSS = """
:root{--blue:#0072a3;--blue-d:#004d8a;--line:#d7d7d7;--txt:#565656;--hdr:#25333d}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;font-family:"Metropolis","Avenir Next","Helvetica Neue",Helvetica,Arial,sans-serif;
 font-size:14px;color:var(--txt);background:#fafafa}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
header{height:60px;background:var(--hdr);color:#fff;display:flex;align-items:center;padding:0 0 0 22px;
 position:fixed;top:0;left:0;right:0;z-index:5}
header .brand{display:flex;align-items:center;gap:10px;color:#fff;font-size:20px;font-weight:300;
 letter-spacing:.5px;min-width:198px}
header .brand:hover{text-decoration:none}
header form{margin-left:12px;flex:0 1 420px}
header input{width:100%;background:transparent;border:0;border-bottom:1px solid #8c9ba5;color:#fff;
 padding:6px 4px 6px 26px;font-size:14px;outline:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16'%3E%3Ccircle cx='6.5' cy='6.5' r='5' fill='none' stroke='%23c6d0d6' stroke-width='1.6'/%3E%3Cpath d='M10.5 10.5l4 4' stroke='%23c6d0d6' stroke-width='1.6'/%3E%3C/svg%3E");
 background-repeat:no-repeat;background-position:2px 8px}
header input::placeholder{color:#9fb0ba}
header .right{margin-left:auto;display:flex;align-items:center;height:100%}
header .right>a,header .right>span,header details>summary{color:#e6ecef;padding:0 18px;height:60px;
 display:flex;align-items:center;font-size:13px;border-left:1px solid #3a4a55;cursor:pointer;list-style:none}
header details{position:relative}header details>summary::-webkit-details-marker{display:none}
header .menu{position:absolute;right:6px;top:56px;background:#fff;border:1px solid var(--line);
 border-radius:3px;box-shadow:0 2px 6px rgba(0,0,0,.2);min-width:180px;padding:6px 0}
header .menu a{display:block;color:#333;padding:7px 18px;font-size:13px}
header .menu a:hover{background:#eee;text-decoration:none}
nav{position:fixed;top:60px;bottom:0;left:0;width:220px;background:#eee;border-right:1px solid var(--line);
 padding-top:18px;overflow:auto}
nav a{display:flex;align-items:center;gap:10px;color:#333;padding:7px 20px;font-size:14px}
nav a.on{background:#fff;color:#000;font-weight:500;box-shadow:inset 3px 0 0 var(--blue)}
nav a:hover{background:#e3e3e3;text-decoration:none}
nav .grp{padding:14px 20px 6px;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#777}
nav a.sub{padding-left:46px;font-size:13px}
nav svg{flex:0 0 16px}
main{margin:60px 0 0 220px;padding:22px 32px 40px;min-height:calc(100% - 60px)}
.crumbs{font-size:13px;margin-bottom:6px}.crumbs a{color:var(--blue)}
h1{font-size:24px;font-weight:300;color:#000;margin:4px 0 4px;word-break:break-all}
h1 small{font-size:13px;color:#777;font-weight:400;margin-left:8px}
h2{font-size:18px;font-weight:300;color:#000;margin:24px 0 10px}
h3{font-size:15px;font-weight:500;color:#333;margin:18px 0 8px}
.sub-h{color:#777;font-size:13px;margin-bottom:14px}
.tabs{display:flex;gap:26px;border-bottom:1px solid var(--line);margin:16px 0 18px;flex-wrap:wrap}
.tabs a{padding:9px 0;color:var(--txt);border-bottom:3px solid transparent;margin-bottom:-1px;font-size:14px}
.tabs a.on{color:#000;border-bottom-color:var(--blue)}.tabs a:hover{text-decoration:none;color:#000}
.toolbar{display:flex;align-items:center;gap:8px;margin:6px 0 10px;flex-wrap:wrap}
.toolbar .flt{margin-left:auto}
.btn{display:inline-flex;align-items:center;height:32px;padding:0 12px;border:1px solid var(--blue);
 color:var(--blue);background:#fff;border-radius:3px;font-size:11px;font-weight:600;letter-spacing:.1em;
 text-transform:uppercase;cursor:pointer;font-family:inherit}
.btn:hover{background:#e3f5fc;text-decoration:none}
.btn.primary{background:var(--blue);color:#fff}.btn.primary:hover{background:var(--blue-d)}
.btn[disabled],.btn.dis{border-color:#ccc;color:#aaa;background:#f4f4f4;cursor:not-allowed}
input.f,select.f{height:32px;border:0;border-bottom:1px solid #9a9a9a;background:transparent;font:inherit;
 padding:0 6px;min-width:200px;outline:none}
input.f:focus{border-bottom-color:var(--blue)}
.grid{background:#fff;border:1px solid var(--line);border-radius:3px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#fafafa;color:#333;font-weight:600;text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);
 white-space:nowrap;font-size:12px}
td{padding:9px 12px;border-bottom:1px solid #e8e8e8;vertical-align:top}
tr:last-child td{border-bottom:0}tbody tr:hover td{background:#f5f9fb}
.foot{display:flex;justify-content:flex-end;padding:8px 12px;font-size:12px;color:#777;border-top:1px solid var(--line);
 background:#fafafa}
.mono{font-family:"SFMono-Regular",Menlo,Consolas,monospace;font-size:12px}
.pill{display:inline-block;font-size:11px;line-height:18px;padding:0 8px;border-radius:9px;margin:1px 3px 1px 0;
 border:1px solid #c5c5c5;background:#fff;color:#333;white-space:nowrap}
.lbl{display:inline-block;font-size:11px;line-height:18px;padding:0 8px;border-radius:3px;color:#fff;margin-right:4px}
.tagp{display:inline-block;font-size:12px;padding:0 6px;border:1px solid #bcd7e5;background:#e8f4fa;color:#00567a;
 border-radius:3px;margin:1px 4px 1px 0;font-family:Menlo,Consolas,monospace}
.cards{display:flex;gap:16px;flex-wrap:wrap;margin:10px 0 22px}
.card{background:#fff;border:1px solid var(--line);border-radius:3px;padding:14px 20px;min-width:220px}
.card .t{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#777;margin-bottom:8px}
.card .row{display:flex;gap:22px}.card .n{font-size:24px;font-weight:300;color:#000}
.card .k{font-size:11px;color:#777}
.kv{display:grid;grid-template-columns:200px 1fr;gap:8px 18px;background:#fff;border:1px solid var(--line);
 border-radius:3px;padding:16px 20px;font-size:13px}
.kv .k{color:#777}.kv .v{color:#222;word-break:break-all}
.bar{height:8px;background:#e8e8e8;border-radius:4px;overflow:hidden;display:flex;min-width:120px}
.bar span{display:block;height:100%}
.sev{display:inline-flex;align-items:center;gap:6px;font-size:12px;white-space:nowrap}
.sev i{display:inline-block;width:12px;height:12px;border-radius:2px}
.s-Critical{background:#a31300}.s-High{background:#e62700}.s-Medium{background:#ff8400}
.s-Low{background:#f8d600}.s-None{background:#2ec0ff}.s-Unknown{background:#8c8c8c}
.box{background:#fff;border:1px solid var(--line);border-radius:3px;padding:16px 20px;margin-bottom:16px}
.alert{border:1px solid #f0c000;background:#fef8e0;padding:10px 14px;border-radius:3px;margin:10px 0;font-size:13px;color:#333}
.alert.err{border-color:#e62700;background:#fdeeea}
.alert.info{border-color:#49afd9;background:#e1f1f6}
pre.cmd{background:#f4f4f4;border:1px solid #e0e0e0;border-radius:3px;padding:10px 12px;font-size:12px;
 white-space:pre-wrap;word-break:break-all;margin:6px 0}
details.d summary{cursor:pointer;color:var(--blue)}
.copy{border:0;background:none;cursor:pointer;color:var(--blue);padding:0 4px;font-size:13px}
.muted{color:#999}
.chk{width:14px;height:14px;border:1px solid #999;border-radius:2px;display:inline-block;vertical-align:middle;background:#fff}
@media (max-width:900px){nav{display:none}main{margin-left:0;padding:18px 14px}header form{display:none}
 .kv{grid-template-columns:1fr}}
"""

_LOGO = ("<svg width='34' height='34' viewBox='0 0 64 64' aria-hidden='true'><circle cx='32' cy='32' r='30' "
         "fill='#60b932'/><path d='M14 40h36l-4 9H18z' fill='#fff'/><path d='M22 38V20h4v18zm8 0V12h4v26zm8 0V24h4v14z'"
         " fill='#fff'/><path d='M33 12l9 12h-9z' fill='#d5f0c4'/></svg>")

_ICONS = {
    "proj": "<svg width='16' height='16' viewBox='0 0 16 16'><path d='M2 4h5l1 1.5h6V13H2z' fill='none' stroke='#555'"
            " stroke-width='1.3'/></svg>",
    "log": "<svg width='16' height='16' viewBox='0 0 16 16'><path d='M3 2h10v12H3zM5 5h6M5 8h6M5 11h4' fill='none'"
           " stroke='#555' stroke-width='1.3'/></svg>",
    "admin": "<svg width='16' height='16' viewBox='0 0 16 16'><circle cx='8' cy='8' r='2.5' fill='none' stroke='#555'"
             " stroke-width='1.3'/><path d='M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4"
             " 12.6l1.4-1.4M11.2 4.8l1.4-1.4' stroke='#555' stroke-width='1.3'/></svg>",
}

_JS = """
document.addEventListener('click',function(e){var b=e.target.closest('[data-copy]');if(!b)return;
var t=b.getAttribute('data-copy');try{navigator.clipboard.writeText(t);}catch(x){}
var o=b.textContent;b.textContent='\\u2713';setTimeout(function(){b.textContent=o},1200);});
"""


def _nav(active, user):
    items = [("/harbor/projects", "Projects", "proj", "projects"),
             ("/harbor/logs", "Logs", "log", "logs")]
    html = "".join(f"<a href='{u}' class='{'on' if active == k else ''}'>{_ICONS[i]}{t}</a>"
                   for u, t, i, k in items)
    if is_admin(user):
        html += f"<div class='grp'>{_ICONS['admin']} Administration</div>"
        for u, t, k in [("/harbor/users", "Users", "users"),
                        ("/harbor/robot-accounts", "Robot Accounts", "robots"),
                        ("/harbor/registries", "Registries", "registries"),
                        ("/harbor/replications", "Replications", "replications"),
                        ("/harbor/labels", "Labels", "labels"),
                        ("/harbor/project-quotas", "Project Quotas", "quotas"),
                        ("/harbor/interrogation-services", "Interrogation Services", "scanners"),
                        ("/harbor/clearing-job", "Clean Up", "gc"),
                        ("/harbor/configs", "Configuration", "configs")]:
            html += f"<a class='sub {'on' if active == k else ''}' href='{u}'>{t}</a>"
    return f"<nav>{html}</nav>"


def page(title, body, active="projects", status=200):
    user = current_user()
    if user:
        right = ("<details><summary>&#9881;&ensp;" + escape(user) + " &#9662;</summary><div class='menu'>"
                 "<a href='/harbor/user-profile'>User Profile</a>"
                 "<a href='/devcenter-api-2.0'>API Explorer</a>"
                 "<a href='/harbor/about'>About</a>"
                 "<a href='/c/log_out'>Log Out</a></div></details>")
    else:
        nxt = quote(request.full_path.rstrip("?"), safe="")
        right = (f"<a href='/devcenter-api-2.0'>API Explorer</a><a href='/harbor/about'>About</a>"
                 f"<a href='/account/sign-in?redirect_url={nxt}'>LOG IN</a>")
    q = escape(request.args.get("q", "")) if request.path == "/harbor/search" else ""
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title><style>{_CSS}</style></head><body>"
        f"<header><a class='brand' href='/harbor/projects'>{_LOGO}<span>Harbor</span></a>"
        "<form action='/harbor/search' method='get'><input name='q' value='" + q +
        "' placeholder='Search Harbor...' autocomplete='off'></form>"
        f"<div class='right'><span>English</span>{right}</div></header>"
        f"{_nav(active, user)}<main>{body}</main><script>{_JS}</script></body></html>"
    )
    return Response(html, status=status, mimetype="text/html")


def _need_login(next_path=None):
    nxt = quote(next_path or request.full_path.rstrip("?"), safe="")
    return redirect(f"/account/sign-in?redirect_url={nxt}")


def _forbidden_page(what="this page"):
    body = ("<h1>Access denied</h1><div class='alert err'>You do not have permission to view "
            f"{escape(what)}. Contact your Harbor system administrator.</div>")
    return page("Access denied - Harbor", body, status=403)


@app.errorhandler(404)
def _404(_e):
    if request.path.startswith(("/api/", "/v2/", "/image/")):
        return jsonify(errors=[{"code": "NOT_FOUND", "message": "not found"}]), 404
    body = ("<h1>Page not found</h1><div class='sub-h'>The page you requested does not exist. "
            "<a href='/harbor/projects'>Back to Projects</a></div>")
    return page("Not found - Harbor", body, status=404)


def _proj_url(p, tab="repositories"):
    return f"/harbor/projects/{p['id']}/{tab}"


def _repo_url(r):
    r = REPOS[r] if isinstance(r, str) else r
    return f"/harbor/projects/{r['project']['id']}/repositories/{quote(r['short'], safe='')}"


def _art_url(art, tab=None):
    u = f"{_repo_url(art['repo'])}/artifacts-tab/artifacts/{art['digest']}"
    return u + (f"?tab={tab}" if tab else "")


def _vuln_cell(art, link=True):
    s = _scan_summary(art)
    if s is None:
        return "<span class='muted'>Not Scanned</span>"
    if s["total"] == 0:
        return "<span class='sev'><i class='s-None'></i>No vulnerability</span>"
    txt = (f"<span class='sev'><i class='s-{s['severity']}'></i>{s['total']} Total &middot; "
           f"{s['fixable']} Fixable</span>")
    return f"<a href='{_art_url(art, 'vulnerabilities')}'>{txt}</a>" if link else txt


def _label_pills(names, proj=None):
    colors = {n: c for n, c, _ in D.GLOBAL_LABELS}
    if proj:
        colors.update({n: c for n, c, _ in proj["labels"]})
    return "".join(f"<span class='lbl' style='background:{colors.get(n, '#565656')}'>{escape(n)}</span>"
                   for n in names)


# ---------------------------------------------------------------------------
# Sign in / out
# ---------------------------------------------------------------------------
def _signin_page(err="", redirect_url="", status=200):
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'><title>Harbor</title>"
        f"<style>{_CSS}"
        "body{background:#25333d;display:flex;min-height:100%;align-items:center;justify-content:center}"
        ".login{background:#fff;width:440px;max-width:94vw;padding:44px 48px 36px;border-radius:4px;"
        "box-shadow:0 4px 24px rgba(0,0,0,.35)}"
        ".login h1{font-size:30px;margin:12px 0 2px}.login .ver{font-size:12px;color:#888;margin-bottom:26px}"
        ".login input.f{width:100%;margin-bottom:18px;height:36px;font-size:14px}"
        ".login .btn{width:100%;justify-content:center;height:38px;margin-top:8px}"
        ".login label.r{font-size:13px;display:flex;gap:6px;align-items:center;margin-bottom:6px}"
        ".login .more{margin-top:26px;font-size:12px;color:#888;display:flex;justify-content:space-between}"
        "</style></head><body><form class='login' method='post' action='/c/login'>"
        f"{_LOGO.replace('34', '52')}<h1>Harbor</h1><div class='ver'>{D.HARBOR_VERSION.split('-')[0]}"
        f" &middot; {D.REGISTRY_HOST}</div>"
        + (f"<div class='alert err'>{escape(err)}</div>" if err else "") +
        "<input class='f' name='principal' placeholder='Username' autofocus autocomplete='username'>"
        "<input class='f' name='password' type='password' placeholder='Password' autocomplete='current-password'>"
        f"<input type='hidden' name='redirect_url' value='{escape(redirect_url)}'>"
        "<input type='hidden' name='ui' value='1'>"
        "<label class='r'><input type='checkbox' name='remember'> Remember me</label>"
        "<button class='btn primary' type='submit'>Log In</button>"
        "<div class='more'><a href='/harbor/projects'>Browse public projects</a>"
        "<span>Forgot password? Contact devops@atbmarket.com</span></div>"
        "</form></body></html>")
    return Response(html, status=status, mimetype="text/html")


@app.get("/account/sign-in")
@app.get("/harbor/sign-in")
def sign_in():
    return _signin_page(redirect_url=request.args.get("redirect_url", ""))


@app.post("/c/login")
def c_login():
    ip = atblog.client_ip(request)
    user = (request.form.get("principal") or "").strip()
    pw = request.form.get("password") or ""
    ui = request.form.get("ui") == "1"
    if _check_pw(user, pw):
        session["u"] = user
        atblog.log("harbor.login", ip, user=user, admin=is_admin(user))
        if ui:
            nxt = request.form.get("redirect_url") or "/harbor/projects"
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = "/harbor/projects"
            return redirect(nxt)
        return Response("", status=200)
    atblog.log("harbor.login_fail", ip, user=user, via="form")
    if ui:
        return _signin_page("Invalid user name or password.", request.form.get("redirect_url", ""), 401)
    return Response("", status=401)


@app.get("/c/log_out")
def log_out():
    session.pop("u", None)
    return redirect("/account/sign-in")


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
@app.get("/")
@app.get("/harbor")
@app.get("/harbor/")
def root():
    return redirect("/harbor/projects")


@app.get("/harbor/projects")
def projects_page():
    ip = atblog.client_ip(request)
    user = current_user()
    atblog.log("harbor.catalog", ip, user=user or "anonymous", msg="project list")
    projs = visible_projects(user)
    q = request.args.get("name", "").strip().lower()
    acc = request.args.get("access", "")
    shown = [p for p in projs if (not q or q in p["name"]) and
             (acc not in ("public", "private") or p["public"] == (acc == "public"))]
    pub = [p for p in projs if p["public"]]
    priv = [p for p in projs if not p["public"]]
    rpub = sum(len(project_repos(p)) for p in pub)
    rpriv = sum(len(project_repos(p)) for p in priv)
    cards = (
        "<div class='cards'>"
        f"<div class='card'><div class='t'>Projects</div><div class='row'><div><div class='n'>{len(priv)}</div>"
        f"<div class='k'>Private</div></div><div><div class='n'>{len(pub)}</div><div class='k'>Public</div></div>"
        f"<div><div class='n'>{len(projs)}</div><div class='k'>Total</div></div></div></div>"
        f"<div class='card'><div class='t'>Repositories</div><div class='row'><div><div class='n'>{rpriv}</div>"
        f"<div class='k'>Private</div></div><div><div class='n'>{rpub}</div><div class='k'>Public</div></div>"
        f"<div><div class='n'>{rpub + rpriv}</div><div class='k'>Total</div></div></div></div>")
    if is_admin(user):
        used = sum(_proj_usage(p) for p in D.PROJECTS)
        cards += (f"<div class='card'><div class='t'>Quota used</div><div class='n'>{_fmt_size(used)}</div>"
                  "<div class='k'>of unlimited</div></div>")
    cards += "</div>"
    rows = ""
    for p in shown:
        role = role_in(user, p)
        rows += (
            f"<tr><td><span class='chk'></span></td><td><a href='{_proj_url(p)}'>{escape(p['name'])}</a></td>"
            f"<td>{'Public' if p['public'] else 'Private'}</td>"
            + (f"<td>{escape(role or '')}</td>" if user else "") +
            f"<td>{'Proxy Cache' if p['registry'] else 'Project'}</td>"
            f"<td>{len(project_repos(p))}</td>"
            f"<td>{_ui_time(REF - timedelta(days=p['created'], hours=_hn(p['name']) % 9))}</td></tr>")
    if not rows:
        rows = "<tr><td colspan='7' class='muted'>We couldn't find any projects!</td></tr>"
    body = (
        "<h1>Projects</h1>" + cards +
        "<div class='toolbar'>"
        f"<button class='btn {'primary' if is_admin(user) else 'dis'}' {'disabled' if not is_admin(user) else ''}>"
        "+ New Project</button><button class='btn dis' disabled>Action &#9662;</button>"
        "<form class='flt' method='get'><select class='f' name='access' onchange='this.form.submit()' "
        "style='min-width:130px'>"
        + "".join(f"<option value='{v}' {'selected' if acc == v else ''}>{t}</option>"
                  for v, t in (("", "All Projects"), ("private", "Private Projects"), ("public", "Public Projects")))
        + f"</select> <input class='f' name='name' value='{escape(q)}' placeholder='Filter projects'></form></div>"
        "<div class='grid'><table><thead><tr><th style='width:30px'></th><th>Project Name</th><th>Access Level</th>"
        + ("<th>Role</th>" if user else "") +
        "<th>Type</th><th>Repositories Count</th><th>Creation Time</th></tr></thead>"
        f"<tbody>{rows}</tbody></table><div class='foot'>1 - {len(shown)} of {len(shown)} items</div></div>")
    return page("Projects - Harbor", body)


def _project_or_redirect(pid):
    p = _proj_lookup(pid)
    if not p:
        abort(404)
    user = current_user()
    if not can_see(user, p):
        atblog.log("harbor.access_denied", atblog.client_ip(request), project=p["name"],
                   user=user or "anonymous", path=request.path)
        if not user:
            return None, _need_login()
        return None, _forbidden_page(f"project {p['name']}")
    return p, None


def _project_header(p, tab, user):
    role = role_in(user, p)
    tabs = [("summary", "Summary"), ("repositories", "Repositories"), ("members", "Members"),
            ("labels", "Labels"), ("robot-account", "Robot Accounts"), ("logs", "Logs"),
            ("configs", "Configuration")]
    t = "".join(f"<a href='{_proj_url(p, k)}' class='{'on' if k == tab else ''}'>{n}</a>" for k, n in tabs)
    meta = f"{'Public' if p['public'] else 'Private'}"
    if p["registry"]:
        meta += " &middot; Proxy Cache (Docker Hub)"
    if role:
        meta += f" &middot; Role: {escape(role)}"
    return (f"<div class='crumbs'><a href='/harbor/projects'>&lsaquo; Projects</a></div>"
            f"<h1>{escape(p['name'])}<small>{meta}</small></h1><div class='tabs'>{t}</div>")


@app.get("/harbor/projects/<pid>")
def project_root(pid):
    p = _proj_lookup(pid)
    if not p:
        abort(404)
    return redirect(_proj_url(p))


@app.get("/harbor/projects/<pid>/<tab>")
def project_tab(pid, tab):
    p, resp = _project_or_redirect(pid)
    if resp:
        return resp
    ip = atblog.client_ip(request)
    user = current_user()
    role = role_in(user, p)
    if tab not in ("summary", "repositories", "members", "labels", "robot-account", "logs", "configs"):
        abort(404)
    head = _project_header(p, tab, user)
    if tab == "summary":
        repos = project_repos(p)
        used = _proj_usage(p)
        lim = p["quota"]
        pct = 0 if lim < 0 else min(100, used * 100 / (lim * (1 << 30)))
        members = ""
        if role:
            cnt = {}
            for _, r in p["members"]:
                cnt[r] = cnt.get(r, 0) + 1
            members = ("<div class='card'><div class='t'>Members</div><div class='row'>" +
                       "".join(f"<div><div class='n'>{c}</div><div class='k'>{escape(r)}</div></div>"
                               for r, c in cnt.items()) + "</div></div>")
        body = (head + "<div class='cards'>"
                f"<div class='card'><div class='t'>Access level</div><div class='n'>"
                f"{'Public' if p['public'] else 'Private'}</div></div>"
                f"<div class='card'><div class='t'>Repositories</div><div class='n'>{len(repos)}</div>"
                f"<div class='k'>{sum(len(ARTIFACTS[r['name']]) for r in repos)} artifacts</div></div>"
                f"<div class='card' style='min-width:300px'><div class='t'>Quota</div>"
                f"<div class='k' style='margin-bottom:6px'>Storage: {_fmt_size(used)} of "
                f"{'unlimited' if lim < 0 else str(lim) + 'GiB'}</div>"
                f"<div class='bar'><span style='width:{pct:.1f}%;background:#0072a3'></span></div></div>"
                f"{members}</div>")
        if p["registry"]:
            body += ("<div class='box'><h3 style='margin-top:0'>Proxy Cache</h3>Endpoint: "
                     "<span class='mono'>https://hub.docker.com</span> &middot; registry <b>docker-hub</b>. "
                     f"Pull through with <span class='mono'>{D.REGISTRY_HOST}/{p['name']}/library/&lt;image&gt;:"
                     "&lt;tag&gt;</span>.</div>")
        return page(f"{p['name']} - Harbor", body)
    if tab == "repositories":
        atblog.log("harbor.catalog", ip, project=p["name"], user=user or "anonymous",
                   msg="project repositories browse")
        q = request.args.get("q", "").strip().lower()
        rows = ""
        repos = sorted(project_repos(p), key=lambda r: -ARTIFACTS[r["name"]][0]["push"].timestamp())
        for r in repos:
            if q and q not in r["name"].lower():
                continue
            arts = ARTIFACTS[r["name"]]
            rows += (f"<tr><td><span class='chk'></span></td><td><a href='{_repo_url(r)}'>{escape(r['name'])}</a></td>"
                     f"<td>{len(arts)}</td><td>{r['pulls']}</td>"
                     f"<td>{_ui_time(arts[0]['push'])}</td></tr>")
        push = (f"docker tag SOURCE_IMAGE[:TAG] {D.REGISTRY_HOST}/{p['name']}/REPOSITORY[:TAG]\n"
                f"docker push {D.REGISTRY_HOST}/{p['name']}/REPOSITORY[:TAG]")
        body = (head +
                "<div class='toolbar'><details class='d'><summary class='btn'>Push Command &#9662;</summary>"
                f"<div class='box' style='margin-top:8px;width:640px;max-width:90vw'>"
                f"<b>Docker</b> - Tag an image for this project:<pre class='cmd'>{escape(push)}</pre>"
                f"<b>Podman</b><pre class='cmd'>podman push IMAGE_ID {D.REGISTRY_HOST}/{p['name']}/"
                "REPOSITORY[:TAG]</pre></div></details>"
                f"<button class='btn dis' disabled>Delete</button>"
                f"<form class='flt'><input class='f' name='q' value='{escape(q)}' placeholder='Filter repositories'>"
                "</form></div><div class='grid'><table><thead><tr><th style='width:30px'></th><th>Name</th>"
                "<th>Artifacts</th><th>Pulls</th><th>Last Modified Time</th></tr></thead>"
                f"<tbody>{rows or '<tr><td colspan=5 class=muted>No repositories found</td></tr>'}</tbody></table>"
                f"<div class='foot'>1 - {len(repos)} of {len(repos)} items</div></div>")
        return page(f"{p['name']} - Harbor", body)
    if tab == "members":
        if not role:
            if not user:
                return _need_login()
            body = head + "<div class='alert'>Only project members can view the member list.</div>"
            return page(f"{p['name']} - Members - Harbor", body)
        rows = ""
        for name, r in p["members"]:
            rows += (f"<tr><td><span class='chk'></span></td><td>{escape(name)}</td><td>User</td>"
                     f"<td>{escape(r)}</td></tr>")
        body = (head + "<div class='toolbar'><button class='btn dis' disabled>+ User</button>"
                "<button class='btn dis' disabled>+ Group</button><button class='btn dis' disabled>Action "
                "&#9662;</button></div><div class='grid'><table><thead><tr><th style='width:30px'></th>"
                f"<th>Name</th><th>Member Type</th><th>Role</th></tr></thead><tbody>{rows}</tbody></table>"
                f"<div class='foot'>1 - {len(p['members'])} of {len(p['members'])} items</div></div>")
        return page(f"{p['name']} - Members - Harbor", body)
    if tab == "labels":
        rows = "".join(f"<tr><td>{_label_pills([n], p)}</td><td>{escape(d)}</td>"
                       f"<td>{_ui_time(REF - timedelta(days=200 + _hn(n) % 300))}</td></tr>"
                       for n, c, d in p["labels"])
        body = (head + "<div class='toolbar'><button class='btn dis' disabled>+ New Label</button></div>"
                "<div class='grid'><table><thead><tr><th>Label</th><th>Description</th><th>Creation Time</th></tr>"
                f"</thead><tbody>{rows or '<tr><td colspan=3 class=muted>No project labels. Global labels (prod, staging, deprecated, ...) are managed by system administrators.</td></tr>'}"
                "</tbody></table></div>")
        return page(f"{p['name']} - Labels - Harbor", body)
    if tab == "robot-account":
        if not user:
            return _need_login()
        if role != "Project Admin":
            return page(f"{p['name']} - Harbor", head + "<div class='alert'>Robot accounts are visible to "
                                                         "project administrators only.</div>")
        rows = ""
        for name, lvl, proj, desc, created, exp, perms in D.ROBOTS:
            if proj == p["name"]:
                rows += (f"<tr><td class='mono'>{escape(name)}</td><td>Enabled</td><td>{escape(perms)}</td>"
                         f"<td>{_ui_time(REF - timedelta(days=created))}</td>"
                         f"<td>{'Never Expired' if exp < 0 else f'{exp} days'}</td><td>{escape(desc)}</td></tr>")
        body = (head + "<div class='grid'><table><thead><tr><th>Name</th><th>Status</th><th>Permissions</th>"
                "<th>Creation Time</th><th>Expires in</th><th>Description</th></tr></thead>"
                f"<tbody>{rows or '<tr><td colspan=6 class=muted>No robot accounts</td></tr>'}</tbody></table></div>")
        return page(f"{p['name']} - Robot Accounts - Harbor", body)
    if tab == "logs":
        if not user:
            return _need_login()
        if not role:
            return page(f"{p['name']} - Harbor", head + "<div class='alert'>Only project members can view "
                                                         "project logs.</div>")
        return page(f"{p['name']} - Logs - Harbor", head + _logs_table(_audit_logs([p]), request.args))
    # configs
    sev = p["severity"]
    chk = lambda on: "&#9745;" if on else "&#9744;"  # noqa: E731
    body = (head + "<div class='kv'>"
            f"<div class='k'>Project registry</div><div class='v'>{chk(p['public'])} Public "
            "<span class='muted'>&mdash; all users can pull images from a public project</span></div>"
            "<div class='k'>Proxy Cache</div><div class='v'>"
            + (f"{chk(True)} docker-hub (https://hub.docker.com)" if p["registry"] else f"{chk(False)} Disabled") +
            "</div><div class='k'>Deployment security</div><div class='v'>"
            f"{chk(False)} Cosign &ensp; {chk(False)} Notation &mdash; only signed images may be deployed<br>"
            f"{chk(bool(sev))} Prevent vulnerable images from running"
            + (f" (severity <b>{escape(sev)}</b> and above)" if sev else "") + "</div>"
            f"<div class='k'>Vulnerability scanning</div><div class='v'>{chk(p['auto_scan'])} "
            "Automatically scan images on push</div>"
            f"<div class='k'>SBOM generation</div><div class='v'>{chk(False)} Automatically generate SBOM on push</div>"
            "<div class='k'>CVE allowlist</div><div class='v'>System allowlist (empty)</div>"
            "</div>"
            + ("<div class='toolbar' style='margin-top:12px'><button class='btn dis' disabled>Save</button></div>"
               if role == "Project Admin" else ""))
    return page(f"{p['name']} - Configuration - Harbor", body)


# ---------------------------------------------------------------------------
# Repository / artifacts
# ---------------------------------------------------------------------------
@app.get("/harbor/projects/<pid>/repositories/<path:rest>")
def repo_router(pid, rest):
    p, resp = _project_or_redirect(pid)
    if resp:
        return resp
    rest = unquote(rest)
    if "/artifacts-tab/artifacts/" in rest:
        short, ref = rest.split("/artifacts-tab/artifacts/", 1)
        return artifact_page(p, short.strip("/"), ref.strip("/"))
    short = rest.strip("/")
    if short.endswith("/artifacts-tab"):
        short = short[: -len("/artifacts-tab")]
    if short.endswith("/info-tab"):
        return repo_page(p, short[: -len("/info-tab")], "info")
    return repo_page(p, short, request.args.get("tab", "artifacts"))


def repo_page(p, short, tab):
    name = f"{p['name']}/{short}"
    r = REPOS.get(name)
    if not r:
        abort(404)
    ip = atblog.client_ip(request)
    user = current_user()
    atblog.log("harbor.tags_list", ip, repo=name, user=user or "anonymous", msg="repository browse")
    arts = ARTIFACTS[name]
    tabs = (f"<div class='tabs'><a href='{_repo_url(r)}?tab=info' class='{'on' if tab == 'info' else ''}'>Info</a>"
            f"<a href='{_repo_url(r)}' class='{'on' if tab != 'info' else ''}'>Artifacts</a></div>")
    head = (f"<div class='crumbs'><a href='/harbor/projects'>Projects</a> &lsaquo; "
            f"<a href='{_proj_url(p)}'>{escape(p['name'])}</a></div><h1>{escape(name)}</h1>{tabs}")
    if tab == "info":
        desc = r["desc"] or "No description for this repo. You can add it to this repository."
        body = (head + "<div class='box' style='white-space:pre-wrap;line-height:1.6'>" + escape(desc) +
                "</div><div class='toolbar'><button class='btn dis' disabled>Edit</button></div>")
        return page(f"{name} - Harbor", body)
    q = request.args.get("q", "").strip()
    rows = ""
    for a in arts:
        if q and not any(q in t for t in a["tags"]) and q not in a["digest"]:
            continue
        pull = f"docker pull {D.REGISTRY_HOST}/{name}@{a['digest']}"
        tags = "".join(f"<span class='tagp'>{escape(t)}</span>" for t in a["tags"][:3]) or \
            "<span class='muted'>-</span>"
        if len(a["tags"]) > 3:
            tags += f"<span class='muted'>+{len(a['tags']) - 3}</span>"
        rows += (
            f"<tr><td><span class='chk'></span></td>"
            f"<td><a class='mono' href='{_art_url(a)}'>{a['digest'][:15]}</a></td>"
            f"<td><button class='copy' title='{escape(pull)}' data-copy='{escape(pull)}'>&#10697;</button></td>"
            f"<td>{tags}</td><td>{_fmt_size(a['size'])}</td><td>{_vuln_cell(a)}</td>"
            f"<td><span class='muted'>-</span></td><td>{_label_pills(a['labels'], p)}</td>"
            f"<td>{_ui_time(a['push'])}</td><td>{_ui_time(_pull_time(a))}</td></tr>")
    body = (head +
            "<div class='toolbar'><button class='btn dis' disabled>Scan</button>"
            "<button class='btn dis' disabled>Stop Scan</button>"
            "<button class='btn dis' disabled>Actions &#9662;</button>"
            f"<form class='flt'><input class='f' name='q' value='{escape(q)}' placeholder='Filter by tag or digest'>"
            "</form></div><div class='grid'><table><thead><tr><th style='width:30px'></th><th>Artifacts</th>"
            "<th>Pull Command</th><th>Tags</th><th>Size</th><th>Vulnerabilities</th><th>Annotations</th>"
            "<th>Labels</th><th>Push Time</th><th>Pull Time</th></tr></thead>"
            f"<tbody>{rows or '<tr><td colspan=10 class=muted>No artifacts found</td></tr>'}</tbody></table>"
            f"<div class='foot'>1 - {len(arts)} of {len(arts)} items</div></div>")
    return page(f"{name} - Harbor", body)


def artifact_page(p, short, ref):
    name = f"{p['name']}/{short}"
    if name not in REPOS:
        abort(404)
    a = _find_art(name, ref)
    if not a:
        abort(404)
    ip = atblog.client_ip(request)
    tab = request.args.get("tab", "overview")
    r = REPOS[name]
    tabs = [("overview", "Overview"), ("history", "Build History"), ("vulnerabilities", "Vulnerabilities"),
            ("tags", "Tags"), ("sbom", "SBOM")]
    t = "".join(f"<a href='{_art_url(a, k)}' class='{'on' if k == tab else ''}'>{n}</a>" for k, n in tabs)
    head = (f"<div class='crumbs'><a href='/harbor/projects'>Projects</a> &lsaquo; "
            f"<a href='{_proj_url(p)}'>{escape(p['name'])}</a> &lsaquo; "
            f"<a href='{_repo_url(r)}'>{escape(short)}</a></div>"
            f"<h1>{escape(short)}@{a['digest'][:15]}</h1>"
            "<div class='sub-h'>" + ("".join(f"<span class='tagp'>{escape(x)}</span>" for x in a["tags"]) or
                                     "<span class='muted'>untagged</span>") + "</div>"
            f"<div class='tabs'>{t}</div>")
    cfg = a["config"]
    if tab == "history":
        _log_pull("harbor.manifest_pull", name, ip, a["env"], digest=a["digest"], via="ui_build_history")
        rows = ""
        for h in cfg["history"]:
            dt = datetime.strptime(h["created"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            rows += (f"<tr><td style='white-space:nowrap'>{_ui_time(dt)}</td>"
                     f"<td class='mono' style='word-break:break-all'>{escape(h['created_by'])}</td></tr>")
        body = (head + "<div class='grid'><table><thead><tr><th style='width:150px'>Created</th><th>Command</th>"
                f"</tr></thead><tbody>{rows}</tbody></table></div>")
        return page(f"{name} - Build History - Harbor", body)
    if tab == "vulnerabilities":
        atblog.log("harbor.vuln_report", ip, repo=name, digest=a["digest"])
        s = _scan_summary(a)
        if s is None:
            body = head + ("<div class='alert info'>This artifact has not been scanned yet."
                           + (" Proxy-cache artifacts are scanned on demand." if p["registry"] else "") +
                           "</div><button class='btn dis' disabled>Scan vulnerability</button>")
            return page(f"{name} - Vulnerabilities - Harbor", body)
        fsev = request.args.get("severity", "")
        bar = "".join(f"<span class='s-{k}' style='width:{s['counts'][k] * 100 / max(s['total'], 1):.1f}%'></span>"
                      for k in SEVS if s["counts"].get(k))
        legend = " &ensp; ".join(f"<a href='{_art_url(a, 'vulnerabilities')}&severity={k}' class='sev'>"
                                 f"<i class='s-{k}'></i>{s['counts'][k]} {k}</a>"
                                 for k in SEVS if s["counts"].get(k))
        rows = ""
        for v in a["vulns"]:
            if fsev and v["severity"] != fsev:
                continue
            link = f"https://avd.aquasec.com/nvd/{v['id'].lower()}"
            rows += (f"<tr><td><a href='{link}' target='_blank' rel='noopener'>{v['id']}</a></td>"
                     f"<td><span class='sev'><i class='s-{v['severity']}'></i>{v['severity']}</span></td>"
                     f"<td>{v['score'] or ''}</td><td class='mono'>{escape(v['package'])}</td>"
                     f"<td class='mono'>{escape(v['version'])}</td>"
                     f"<td class='mono'>{escape(v['fix_version']) or '<span class=muted>-</span>'}</td>"
                     f"<td>No</td><td><details class='d'><summary>{escape(v['description'][:60])}"
                     f"{'...' if len(v['description']) > 60 else ''}</summary>{escape(v['description'])}"
                     f"<br><span class='muted'>{escape(v['cwe'])}</span></details></td></tr>")
        body = (head +
                "<div class='box'><div style='display:flex;gap:30px;flex-wrap:wrap;align-items:center'>"
                f"<div><div class='k muted'>Total</div><div style='font-size:26px;font-weight:300;color:#000'>"
                f"{s['total']}</div><div class='muted' style='font-size:12px'>{s['fixable']} fixable</div></div>"
                f"<div style='flex:1;min-width:240px'><div class='bar' style='height:14px'>{bar}</div>"
                f"<div style='margin-top:8px'>{legend}</div></div>"
                f"<div style='font-size:12px'>Scanned by: <b>Trivy</b> {D.TRIVY_VERSION} (Aqua Security)<br>"
                f"Scan completed: {_ui_time(a['scan_end'])}<br>Duration: {12 + _hn(a['digest']) % 50}s</div>"
                "</div></div>"
                "<div class='toolbar'><button class='btn dis' disabled>Scan vulnerability</button>"
                "<button class='btn dis' disabled>Add to CVE allowlist</button>"
                f"<span class='flt'>{('Filter: <b>' + escape(fsev) + '</b> &middot; <a href=' + chr(39) + _art_url(a, 'vulnerabilities') + chr(39) + '>clear</a>') if fsev else ''}</span></div>"
                "<div class='grid'><table><thead><tr><th>Vulnerability</th><th>Severity</th><th>CVSS3</th>"
                "<th>Package</th><th>Current version</th><th>Fixed in version</th><th>Listed In CVE Allowlist</th>"
                f"<th>Description</th></tr></thead><tbody>{rows}</tbody></table>"
                f"<div class='foot'>{s['total']} items</div></div>")
        return page(f"{name} - Vulnerabilities - Harbor", body)
    if tab == "tags":
        rows = ""
        for i, tg in enumerate(a["tags"]):
            rows += (f"<tr><td><span class='chk'></span></td><td class='mono'>{escape(tg)}</td>"
                     f"<td>{'No'}</td><td>{_ui_time(_pull_time(a))}</td>"
                     f"<td>{_ui_time(a['push'] + timedelta(seconds=i))}</td></tr>")
        body = (head + "<div class='toolbar'><button class='btn dis' disabled>Add Tag</button>"
                "<button class='btn dis' disabled>Remove Tag</button></div>"
                "<div class='grid'><table><thead><tr><th style='width:30px'></th><th>Name</th><th>Immutable</th>"
                "<th>Pull Time</th><th>Push Time</th></tr></thead>"
                f"<tbody>{rows or '<tr><td colspan=5 class=muted>No tags</td></tr>'}</tbody></table></div>")
        return page(f"{name} - Tags - Harbor", body)
    if tab == "sbom":
        pk = _sbom_packages(a)
        if pk is None:
            body = head + ("<div class='alert info'>No SBOM. SBOM is generated by the interrogation service "
                           "together with the vulnerability scan.</div>")
            return page(f"{name} - SBOM - Harbor", body)
        rows = "".join(f"<tr><td class='mono'>{escape(n)}</td><td class='mono'>{escape(v)}</td>"
                       f"<td>{escape(t)}</td><td>{escape(lic)}</td></tr>" for n, v, t, lic in pk)
        api = (f"/api/v2.0/projects/{p['name']}/repositories/{quote(quote(short, safe=''), safe='')}"
               f"/artifacts/{a['digest']}/additions/sbom")
        body = (head + f"<div class='toolbar'><span>Format: SPDX 2.3 &middot; generated by Trivy {D.TRIVY_VERSION}"
                f"</span><a class='btn flt' href='{api}'>Download</a></div>"
                "<div class='grid'><table><thead><tr><th>Package</th><th>Version</th><th>Type</th><th>License</th>"
                f"</tr></thead><tbody>{rows}</tbody></table><div class='foot'>{len(pk)} packages</div></div>")
        return page(f"{name} - SBOM - Harbor", body)
    # overview
    ci = cfg["config"]
    pull = f"docker pull {D.REGISTRY_HOST}/{name}@{a['digest']}"
    s = _scan_summary(a)
    info = [
        ("Type", "IMAGE"), ("Media type", MANIFEST_MT), ("Digest", f"<span class='mono'>{a['digest']}</span>"),
        ("Size", _fmt_size(a["size"])), ("Push time", _ui_time(a["push"])),
        ("Pull time", _ui_time(_pull_time(a)) or "-"), ("Created", _ui_time(a["created"])),
        ("Architecture", "amd64"), ("OS", "linux"),
        ("Base", escape(D.BASES[r["spec"]["base"]]["image"]) if not r["spec"].get("base_only") else "-"),
        ("Author", "-"),
        ("Pull command", f"<span class='mono'>{escape(pull)}</span> <button class='copy' "
                         f"data-copy='{escape(pull)}'>&#10697;</button>"),
        ("Vulnerabilities", _vuln_cell(a) if s else "<span class='muted'>Not Scanned</span>"),
        ("Labels", _label_pills(a["labels"], p) or "-"),
    ]
    kv = "".join(f"<div class='k'>{k}</div><div class='v'>{v}</div>" for k, v in info)
    oci = ci.get("Labels") or {}
    lab = "".join(f"<div class='k mono'>{escape(k)}</div><div class='v mono'>{escape(v)}</div>"
                  for k, v in oci.items())
    adds = (f"<ul><li><a href='{_art_url(a, 'history')}'>Build History</a></li>"
            f"<li><a href='{_art_url(a, 'vulnerabilities')}'>Vulnerabilities</a></li>"
            f"<li><a href='{_art_url(a, 'sbom')}'>SBOM</a></li></ul>")
    body = (head + f"<h3>Artifact Info</h3><div class='kv'>{kv}</div>"
            + (f"<h3>Annotations / OCI labels</h3><div class='kv'>{lab}</div>" if lab else "")
            + f"<h3>Additions</h3><div class='box'>{adds}</div>")
    return page(f"{name} - Harbor", body)


def _sbom_packages(a):
    if a["vulns"] is None:
        return None
    r = REPOS[a["repo"]]
    base = D.BASES[r["spec"]["base"]]
    pools = base["pools"][:1] if r["spec"].get("base_only") else base["pools"]
    seen, out = set(), []
    for pool in pools:
        for n, v, t, lic in D.SBOM_EXTRA.get(pool, []):
            if n not in seen:
                seen.add(n)
                out.append((n, v, t, lic))
    typ = {"alpine": "apk", "debian": "deb", "ubuntu": "deb", "node": "npm", "python": "python-pkg",
           "dotnet": "nuget", "php": "binary", "go": "gobinary", "java": "jar"}
    for vid, (pool, pkg, ver, *_r) in D.VULNS.items():
        if pool in pools and pkg not in seen:
            seen.add(pkg)
            out.append((pkg, ver, typ[pool], ""))
    return sorted(out, key=lambda x: (x[2], x[0].lower()))


# Legacy URLs from the old UI (kept working).
@app.get("/harbor/repo/<path:repo>")
def legacy_repo(repo):
    if repo not in REPOS:
        abort(404)
    return redirect(_art_url(ARTIFACTS[repo][0], "history"))


# ---------------------------------------------------------------------------
# Search, logs, misc pages
# ---------------------------------------------------------------------------
@app.get("/harbor/search")
def search_page():
    ip = atblog.client_ip(request)
    user = current_user()
    q = request.args.get("q", "").strip()
    atblog.log("harbor.search", ip, q=q, user=user or "anonymous")
    ql = q.lower()
    projs = [p for p in visible_projects(user) if ql and ql in p["name"]]
    repos = [r for r in REPOS.values() if ql and ql in r["name"].lower() and can_see(user, r["project"])]
    prow = "".join(f"<tr><td><a href='{_proj_url(p)}'>{escape(p['name'])}</a></td>"
                   f"<td>{'Public' if p['public'] else 'Private'}</td><td>{len(project_repos(p))}</td></tr>"
                   for p in projs)
    rrow = "".join(f"<tr><td><a href='{_repo_url(r)}'>{escape(r['name'])}</a></td><td>{len(ARTIFACTS[r['name']])}</td>"
                   f"<td>{r['pulls']}</td></tr>" for r in repos)
    body = (f"<h1>Search results for &ldquo;{escape(q)}&rdquo;</h1>"
            f"<h2>Projects ({len(projs)})</h2><div class='grid'><table><thead><tr><th>Project Name</th>"
            f"<th>Access Level</th><th>Repositories Count</th></tr></thead><tbody>"
            f"{prow or '<tr><td colspan=3 class=muted>No projects found</td></tr>'}</tbody></table></div>"
            f"<h2>Repositories ({len(repos)})</h2><div class='grid'><table><thead><tr><th>Name</th>"
            f"<th>Artifacts</th><th>Pulls</th></tr></thead><tbody>"
            f"{rrow or '<tr><td colspan=3 class=muted>No repositories found</td></tr>'}</tbody></table></div>")
    return page("Search - Harbor", body)


def _audit_logs(projs):
    now = datetime.now(timezone.utc)
    out = []
    lid = 0
    for p in projs:
        pusher = D.PUSHERS.get(p["name"], "admin")
        pullers = D.PULLERS.get(p["name"], D.DEFAULT_PULLERS)
        for r in project_repos(p):
            for a in ARTIFACTS[r["name"]]:
                res = f"{r['name']}:{a['tags'][0]}" if a["tags"] else f"{r['name']}@{a['digest'][:15]}"
                out.append((a["push"], pusher, res, "artifact", "create"))
                for i, t in enumerate(a["tags"][1:]):
                    out.append((a["push"] + timedelta(seconds=2 + i), pusher, f"{r['name']}:{t}", "tag", "create"))
                if a["pull_age"]:
                    for k in range(1 + _hn(a["digest"], "n") % 4):
                        when = now - a["pull_age"] - timedelta(hours=k * (5 + _hn(a["digest"], k) % 30))
                        if when > a["push"]:
                            out.append((when, pullers[(k + _hn(r["name"])) % len(pullers)],
                                        f"{r['name']}@{a['digest'][:15]}", "artifact", "pull"))
                if a["idx"] == 3:
                    out.append((a["push"] + timedelta(days=4, hours=3), p["owner"],
                                f"{r['name']}:rc-{_hn(a['digest']) % 9}", "tag", "delete"))
    out.sort(key=lambda x: x[0], reverse=True)
    res = []
    for when, who, resource, rtype, op in out:
        lid += 1
        res.append({"id": 90000 - lid, "username": who, "resource": resource, "resource_type": rtype,
                    "operation": op, "op_time": when})
    return res


def _logs_table(logs, args):
    q = args.get("q", "").strip()
    op = args.get("op", "")
    logs = [l for l in logs if (not q or q in l["resource"] or q in l["username"]) and (not op or l["operation"] == op)]
    try:
        pg = max(1, int(args.get("page", "1")))
    except ValueError:
        pg = 1
    per = 25
    total = len(logs)
    chunk = logs[(pg - 1) * per: pg * per]
    rows = "".join(f"<tr><td>{escape(l['username'])}</td><td class='mono'>{escape(l['resource'])}</td>"
                   f"<td>{l['resource_type']}</td><td>{l['operation']}</td><td>{_ui_time(l['op_time'])}</td></tr>"
                   for l in chunk)
    base = request.path + "?" + "&".join(f"{k}={quote(v)}" for k, v in (("q", q), ("op", op)) if v)
    nav = ""
    if pg > 1:
        nav += f"<a href='{base}&page={pg - 1}'>&lsaquo; prev</a> &ensp;"
    if pg * per < total:
        nav += f"<a href='{base}&page={pg + 1}'>next &rsaquo;</a>"
    return ("<div class='toolbar'><form class='flt' method='get'><select class='f' name='op' style='min-width:120px'>"
            + "".join(f"<option value='{v}' {'selected' if v == op else ''}>{t}</option>"
                      for v, t in (("", "All operations"), ("create", "Create"), ("pull", "Pull"), ("delete", "Delete")))
            + f"</select> <input class='f' name='q' value='{escape(q)}' placeholder='Filter by user or resource'>"
            " <button class='btn'>Filter</button></form></div>"
            "<div class='grid'><table><thead><tr><th>Username</th><th>Resource</th><th>Resource Type</th>"
            f"<th>Operation</th><th>Timestamp</th></tr></thead><tbody>"
            f"{rows or '<tr><td colspan=5 class=muted>No logs</td></tr>'}</tbody></table>"
            f"<div class='foot'>{nav} &ensp; {(pg - 1) * per + 1 if total else 0} - {min(pg * per, total)} of {total} items"
            "</div></div>")


@app.get("/harbor/logs")
def logs_page():
    user = current_user()
    if not user:
        return _need_login()
    projs = D.PROJECTS if is_admin(user) else [p for p in D.PROJECTS if role_in(user, p)]
    atblog.log("harbor.audit_log_view", atblog.client_ip(request), user=user)
    return page("Logs - Harbor", "<h1>Logs</h1>" + _logs_table(_audit_logs(projs), request.args), active="logs")


@app.get("/harbor/about")
def about_page():
    body = ("<h1>About Harbor</h1><div class='kv'>"
            f"<div class='k'>Version</div><div class='v'>{D.HARBOR_VERSION}</div>"
            f"<div class='k'>Registry</div><div class='v'>{D.REGISTRY_HOST}</div>"
            "<div class='k'>Host</div><div class='v'>sh-harb-p01</div>"
            f"<div class='k'>Interrogation service</div><div class='v'>Trivy {D.TRIVY_VERSION} (default)</div>"
            "<div class='k'>Support</div><div class='v'>DevOps team &middot; devops@atbmarket.com</div>"
            "</div><p class='muted' style='font-size:12px;margin-top:18px'>Harbor&trade; is an open source trusted "
            "cloud native registry project that stores, signs, and scans content. Licensed under the Apache "
            "License, Version 2.0.</p>")
    return page("About - Harbor", body, active="")


@app.get("/harbor/user-profile")
def profile_page():
    user = current_user()
    if not user:
        return _need_login()
    u = D.USERS[user]
    body = ("<h1>User Profile</h1><div class='kv'>"
            f"<div class='k'>Username</div><div class='v'>{escape(user)}</div>"
            f"<div class='k'>Email</div><div class='v'>{escape(u['email'])}</div>"
            f"<div class='k'>First and last name</div><div class='v'>{escape(u['realname'])}</div>"
            f"<div class='k'>Comments</div><div class='v'>-</div>"
            f"<div class='k'>System admin</div><div class='v'>{'Yes' if u['admin'] else 'No'}</div></div>"
            "<div class='toolbar' style='margin-top:12px'><button class='btn dis' disabled>Change Password</button>"
            "<button class='btn dis' disabled>Generate CLI secret</button></div>")
    return page("User Profile - Harbor", body, active="")


@app.get("/devcenter-api-2.0")
def api_explorer():
    eps = [
        ("GET", "/api/v2.0/health", "Check the status of Harbor components"),
        ("GET", "/api/v2.0/systeminfo", "Get general system info"),
        ("GET", "/api/v2.0/projects", "List projects"),
        ("GET", "/api/v2.0/projects/{project_name_or_id}", "Return specific project detail information"),
        ("GET", "/api/v2.0/projects/{project_name_or_id}/summary", "Get summary of the project"),
        ("GET", "/api/v2.0/projects/{project_name_or_id}/members", "Get all project member information"),
        ("GET", "/api/v2.0/projects/{project_name}/logs", "Get recent logs of the projects"),
        ("GET", "/api/v2.0/projects/{project_name}/repositories", "List repositories"),
        ("GET", "/api/v2.0/projects/{project_name}/repositories/{repository_name}", "Get repository"),
        ("GET", "/api/v2.0/projects/{project_name}/repositories/{repository_name}/artifacts", "List artifacts"),
        ("GET", "/api/v2.0/projects/{project_name}/repositories/{repository_name}/artifacts/{reference}",
         "Get the specific artifact"),
        ("GET", ".../artifacts/{reference}/tags", "List tags"),
        ("GET", ".../artifacts/{reference}/additions/{addition}",
         "Get the addition of the artifact (build_history, vulnerabilities)"),
        ("GET", "/api/v2.0/repositories", "List all authorized repositories"),
        ("GET", "/api/v2.0/search?q=", "Search for projects and repositories"),
        ("GET", "/api/v2.0/labels?scope=g", "List labels"),
        ("GET", "/api/v2.0/audit-logs", "Get recent logs of the projects which the user is a member of"),
        ("GET", "/api/v2.0/statistics", "Get the statistic information about the projects and repositories"),
        ("GET", "/api/v2.0/users/current", "Get current user info"),
        ("GET", "/api/v2.0/users", "List users (system admin)"),
        ("GET", "/api/v2.0/robots", "Get robot account list (system admin)"),
        ("GET", "/api/v2.0/quotas", "List quotas (system admin)"),
        ("GET", "/api/v2.0/scanners", "List scanner registrations (system admin)"),
        ("GET", "/api/v2.0/registries", "List the registries (system admin)"),
    ]
    rows = "".join(f"<tr><td><span class='pill' style='background:#e1f1f6;border-color:#49afd9'>{m}</span></td>"
                   f"<td class='mono'>{escape(u)}</td><td>{escape(d)}</td></tr>" for m, u, d in eps)
    body = ("<h1>Harbor API V2.0</h1><div class='sub-h'>Base URL: <span class='mono'>/api/v2.0</span> &middot; "
            "Authentication: HTTP Basic (user or robot account) or session cookie. Docker Registry HTTP API V2 is "
            "served under <span class='mono'>/v2/</span>.</div>"
            "<div class='grid'><table><thead><tr><th>Method</th><th>Path</th><th>Description</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")
    return page("Harbor API", body, active="")


# --- system admin pages ------------------------------------------------------
def _admin_guard():
    user = current_user()
    if not user:
        return _need_login()
    if not is_admin(user):
        atblog.log("harbor.access_denied", atblog.client_ip(request), user=user, path=request.path)
        return _forbidden_page("system administration")
    return None


@app.get("/harbor/users")
def admin_users():
    g = _admin_guard()
    if g:
        return g
    rows = "".join(f"<tr><td>{escape(n)}</td><td>{'Yes' if u['admin'] else 'No'}</td><td>{escape(u['email'])}</td>"
                   f"<td>{_ui_time(REF - timedelta(days=u['created']))}</td></tr>"
                   for n, u in sorted(D.USERS.items(), key=lambda x: x[1]["id"]))
    body = ("<h1>Users</h1><div class='toolbar'><button class='btn primary'>+ New User</button>"
            "<button class='btn'>Set as Administrator</button></div><div class='grid'><table><thead><tr><th>Name</th>"
            f"<th>Administrator</th><th>Email</th><th>Registration Time</th></tr></thead><tbody>{rows}</tbody>"
            "</table></div>")
    return page("Users - Harbor", body, active="users")


@app.get("/harbor/robot-accounts")
def admin_robots():
    g = _admin_guard()
    if g:
        return g
    rows = "".join(f"<tr><td class='mono'>{escape(n)}</td><td>{lvl}</td><td>{escape(pr)}</td><td>{escape(pe)}</td>"
                   f"<td>{_ui_time(REF - timedelta(days=c))}</td><td>{'Never Expired' if e < 0 else f'{e} days'}</td>"
                   f"<td>{escape(d)}</td></tr>" for n, lvl, pr, d, c, e, pe in D.ROBOTS)
    body = ("<h1>Robot Accounts</h1><div class='grid'><table><thead><tr><th>Name</th><th>Level</th><th>Projects</th>"
            "<th>Permissions</th><th>Creation Time</th><th>Expires in</th><th>Description</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")
    return page("Robot Accounts - Harbor", body, active="robots")


@app.get("/harbor/registries")
def admin_registries():
    g = _admin_guard()
    if g:
        return g
    rows = "".join(f"<tr><td>{escape(n)}</td><td>{escape(u)}</td><td>{s}</td><td>{escape(t)}</td>"
                   f"<td>{_ui_time(REF - timedelta(days=c))}</td></tr>" for n, t, u, s, c in D.REGISTRIES)
    body = ("<h1>Registries</h1><div class='grid'><table><thead><tr><th>Name</th><th>Endpoint URL</th><th>Status</th>"
            f"<th>Provider</th><th>Creation Time</th></tr></thead><tbody>{rows}</tbody></table></div>")
    return page("Registries - Harbor", body, active="registries")


@app.get("/harbor/replications")
def admin_replications():
    g = _admin_guard()
    if g:
        return g
    body = ("<h1>Replications</h1><div class='grid'><table><thead><tr><th>Name</th><th>Status</th><th>Source</th>"
            "<th>Mode</th><th>Destination</th><th>Trigger</th></tr></thead><tbody><tr><td>gitlab-mirror</td>"
            "<td>Disabled</td><td>gitlab-registry</td><td>Pull-based</td><td>mobapp</td><td>Manual</td></tr>"
            "</tbody></table></div>")
    return page("Replications - Harbor", body, active="replications")


@app.get("/harbor/labels")
def admin_labels():
    g = _admin_guard()
    if g:
        return g
    rows = "".join(f"<tr><td>{_label_pills([n])}</td><td>{escape(d)}</td></tr>" for n, c, d in D.GLOBAL_LABELS)
    return page("Labels - Harbor", "<h1>Labels</h1><div class='grid'><table><thead><tr><th>Label</th>"
                f"<th>Description</th></tr></thead><tbody>{rows}</tbody></table></div>", active="labels")


@app.get("/harbor/project-quotas")
def admin_quotas():
    g = _admin_guard()
    if g:
        return g
    rows = "".join(f"<tr><td>{escape(p['name'])}</td><td>{escape(p['owner'])}</td>"
                   f"<td>{_fmt_size(_proj_usage(p))} of {'unlimited' if p['quota'] < 0 else str(p['quota']) + 'GiB'}"
                   "</td></tr>" for p in D.PROJECTS)
    return page("Project Quotas - Harbor", "<h1>Project Quotas</h1><div class='kv' style='margin-bottom:14px'>"
                "<div class='k'>Default quota space per project</div><div class='v'>unlimited</div></div>"
                "<div class='grid'><table><thead><tr><th>Project</th><th>Owner</th><th>Storage</th></tr></thead>"
                f"<tbody>{rows}</tbody></table></div>", active="quotas")


@app.get("/harbor/interrogation-services")
def admin_scanners():
    g = _admin_guard()
    if g:
        return g
    return page("Interrogation Services - Harbor",
                "<h1>Interrogation Services</h1><div class='grid'><table><thead><tr><th>Name</th><th>Endpoint</th>"
                "<th>Health</th><th>Enabled</th><th>Authorization</th></tr></thead><tbody><tr><td>Trivy "
                "<span class='pill'>Default</span></td><td class='mono'>http://trivy-adapter:8080</td>"
                "<td>Healthy</td><td>true</td><td>None</td></tr></tbody></table></div>"
                "<h2>Vulnerability database</h2><div class='kv'><div class='k'>Scanner</div>"
                f"<div class='v'>Trivy {D.TRIVY_VERSION}</div><div class='k'>Schedule</div>"
                "<div class='v'>Daily at 02:00</div><div class='k'>Last updated</div>"
                f"<div class='v'>{_ui_time(REF - timedelta(hours=7))}</div></div>", active="scanners")


@app.get("/harbor/clearing-job")
def admin_gc():
    g = _admin_guard()
    if g:
        return g
    return page("Clean Up - Harbor", "<h1>Clean Up</h1><div class='kv'><div class='k'>Garbage collection schedule</div>"
                "<div class='v'>Weekly (Sun 03:00)</div><div class='k'>Last run</div>"
                f"<div class='v'>{_ui_time(REF - timedelta(days=4, hours=6))} &middot; Success &middot; "
                "freed 3.71GiB</div></div>", active="gc")


@app.get("/harbor/configs")
def admin_configs():
    g = _admin_guard()
    if g:
        return g
    return page("Configuration - Harbor", "<h1>Configuration</h1><div class='kv'>"
                "<div class='k'>Auth mode</div><div class='v'>Database</div>"
                "<div class='k'>Primary auth mode</div><div class='v'>false</div>"
                "<div class='k'>Project creation</div><div class='v'>Admin only</div>"
                "<div class='k'>Allow self-registration</div><div class='v'>false</div>"
                "<div class='k'>Email server</div><div class='v'>mail.atbmarket.com:25 (no auth)</div>"
                "<div class='k'>Repository read only</div><div class='v'>false</div>"
                "<div class='k'>Robot token expiration</div><div class='v'>30 days</div></div>", active="configs")


# ---------------------------------------------------------------------------
# Harbor API v2.0
# ---------------------------------------------------------------------------
def _err(code, msg, status):
    return jsonify(errors=[{"code": code, "message": msg}]), status


def _api_auth_err(user):
    return _err("UNAUTHORIZED", "unauthorized", 401) if not user else _err("FORBIDDEN", "forbidden", 403)


def _paged(items):
    try:
        pg = max(1, int(request.args.get("page", 1)))
        size = min(100, max(1, int(request.args.get("page_size", 10))))
    except ValueError:
        return _err("BAD_REQUEST", "invalid page parameters", 400)
    chunk = items[(pg - 1) * size: pg * size]
    resp = jsonify(chunk)
    resp.headers["X-Total-Count"] = str(len(items))
    if pg * size < len(items):
        args = dict(request.args)
        args["page"] = str(pg + 1)
        resp.headers["Link"] = f'<{request.path}?' + "&".join(f"{k}={quote(v)}" for k, v in args.items()) + \
            '>; rel="next"'
    return resp


def _q_name():
    """Supports ?name=X and Harbor's ?q=name=~X / name=X query syntax."""
    name = request.args.get("name", "")
    q = request.args.get("q", "")
    for part in q.split(","):
        k, sep, v = part.partition("=")
        if k.strip() == "name" and sep:
            name = v.lstrip("~")
    return name.strip()


def _proj_json(p, user):
    repos = project_repos(p)
    out = {"project_id": p["id"], "owner_id": D.USERS.get(p["owner"], {}).get("id", 1), "name": p["name"],
           "owner_name": p["owner"], "registry_id": 1 if p["registry"] else None,
           "creation_time": _iso(REF - timedelta(days=p["created"])),
           "update_time": _iso(REF - timedelta(days=p["created"] // 3)), "deleted": False,
           "repo_count": len(repos), "chart_count": 0,
           "metadata": {"public": str(p["public"]).lower(), "auto_scan": str(p["auto_scan"]).lower(),
                        "enable_content_trust": "false", "prevent_vul": str(bool(p["severity"])).lower(),
                        "severity": p["severity"] or "low", "reuse_sys_cve_allowlist": "true"},
           "cve_allowlist": {"id": p["id"], "project_id": p["id"], "items": [], "expires_at": None,
                             "creation_time": "0001-01-01T00:00:00.000Z", "update_time": "0001-01-01T00:00:00.000Z"}}
    role = role_in(user, p)
    if role:
        out["current_user_role_id"] = {"Project Admin": 1, "Developer": 2, "Guest": 3, "Maintainer": 4,
                                       "Limited Guest": 5}[role]
        out["current_user_role_ids"] = [out["current_user_role_id"]]
    return out


def _repo_json(r):
    arts = ARTIFACTS[r["name"]]
    return {"id": r["id"], "project_id": r["project"]["id"], "name": r["name"], "description": r["desc"],
            "artifact_count": len(arts), "pull_count": r["pulls"],
            "creation_time": _iso(arts[-1]["push"]), "update_time": _iso(arts[0]["push"])}


def _scan_overview(a):
    s = _scan_summary(a)
    if s is None:
        return None
    return {REPORT_MT: {
        "report_id": _h(a["digest"], "report")[:8] + "-" + _h(a["digest"], "report")[8:12] + "-4" +
                     _h(a["digest"], "report")[13:16] + "-a" + _h(a["digest"], "report")[17:20] + "-" +
                     _h(a["digest"], "report")[20:32],
        "scan_status": "Success", "severity": s["severity"], "duration": 12 + _hn(a["digest"]) % 50,
        "summary": {"total": s["total"], "fixable": s["fixable"], "summary": s["counts"]},
        "start_time": _iso(a["scan_end"] - timedelta(seconds=12 + _hn(a["digest"]) % 50)),
        "end_time": _iso(a["scan_end"]),
        "scanner": {"name": "Trivy", "vendor": "Aqua Security", "version": D.TRIVY_VERSION},
        "complete_percent": 100}}


def _art_json(a, p, short):
    enc = quote(quote(short, safe=""), safe="")
    base = f"/api/v2.0/projects/{p['name']}/repositories/{enc}/artifacts/{a['digest']}/additions"
    pt = _pull_time(a)
    r = REPOS[a["repo"]]
    colors = {n: c for n, c, _ in D.GLOBAL_LABELS + p["labels"]}
    out = {
        "id": a["id"], "type": "IMAGE", "media_type": CONFIG_MT, "manifest_media_type": MANIFEST_MT,
        "project_id": p["id"], "repository_id": r["id"], "digest": a["digest"], "size": a["size"],
        "icon": ICON, "push_time": _iso(a["push"]), "pull_time": _iso(pt) if pt else "0001-01-01T00:00:00.000Z",
        "extra_attrs": {"architecture": "amd64", "author": "", "config": a["config"]["config"],
                        "created": a["config"]["created"], "os": "linux"},
        "annotations": None, "references": None,
        "tags": [{"id": a["id"] * 10 + i, "repository_id": r["id"], "artifact_id": a["id"], "name": t,
                  "push_time": _iso(a["push"] + timedelta(seconds=i)),
                  "pull_time": _iso(pt) if pt else "0001-01-01T00:00:00.000Z",
                  "immutable": False} for i, t in enumerate(a["tags"])] or None,
        "addition_links": {"build_history": {"href": f"{base}/build_history", "absolute": False},
                           "vulnerabilities": {"href": f"{base}/vulnerabilities", "absolute": False}},
        "labels": [{"id": 10 + _hn(n) % 90, "name": n, "color": colors.get(n, "#565656"),
                    "scope": "g" if n in dict((x[0], 1) for x in D.GLOBAL_LABELS) else "p"}
                   for n in a["labels"]] or None,
    }
    so = _scan_overview(a)
    if so and request.args.get("with_scan_overview", "false").lower() == "true":
        out["scan_overview"] = so
    return out


@app.get("/api/v2.0/ping")
def api_ping():
    return Response("Pong", mimetype="text/plain")


@app.get("/api/v2.0/health")
def api_health():
    comps = ["core", "database", "jobservice", "portal", "redis", "registry", "registryctl", "trivy"]
    return jsonify(status="healthy", components=[{"name": c, "status": "healthy"} for c in comps])


@app.get("/api/v2.0/systeminfo")
def api_systeminfo():
    user = current_user()
    info = {"auth_mode": "db_auth", "banner_message": "", "current_time": _iso(datetime.now(timezone.utc)),
            "harbor_version": D.HARBOR_VERSION, "oidc_provider_name": "", "primary_auth_mode": False,
            "self_registration": False}
    if user:
        info.update({"external_url": f"https://{D.REGISTRY_HOST}", "has_ca_root": False,
                     "notification_enable": True, "project_creation_restriction": "adminonly",
                     "read_only": False, "registry_storage_provider_name": "filesystem",
                     "registry_url": D.REGISTRY_HOST, "with_chartmuseum": False, "with_notary": False})
    return jsonify(info)


@app.get("/api/v2.0/systeminfo/volumes")
def api_volumes():
    user = current_user()
    if not is_admin(user):
        return _api_auth_err(user)
    return jsonify(storage=[{"total": 2147483648000, "free": 1328926552064}])


@app.get("/api/v2.0/statistics")
def api_stats():
    user = current_user()
    if not user:
        return _api_auth_err(user)
    projs = visible_projects(user)
    pub = [p for p in projs if p["public"]]
    priv = [p for p in projs if not p["public"]]
    out = {"private_project_count": len(priv), "private_repo_count": sum(len(project_repos(p)) for p in priv),
           "public_project_count": len(pub), "public_repo_count": sum(len(project_repos(p)) for p in pub),
           "total_project_count": len(projs),
           "total_repo_count": sum(len(project_repos(p)) for p in projs)}
    if is_admin(user):
        out["total_storage_consumption"] = sum(_proj_usage(p) for p in D.PROJECTS)
    return jsonify(out)


@app.get("/api/v2.0/users/current")
def api_user_current():
    user = current_user()
    if not user:
        return _api_auth_err(user)
    u = D.USERS[user]
    return jsonify(user_id=u["id"], username=user, email=u["email"], realname=u["realname"], comment="",
                   sysadmin_flag=u["admin"], admin_role_in_auth=False, oidc_user_meta=None,
                   creation_time=_iso(REF - timedelta(days=u["created"])),
                   update_time=_iso(REF - timedelta(days=u["created"] // 2)))


@app.get("/api/v2.0/users")
def api_users():
    user = current_user()
    if not is_admin(user):
        return _api_auth_err(user)
    return _paged([{"user_id": u["id"], "username": n, "email": u["email"], "realname": u["realname"],
                    "sysadmin_flag": u["admin"], "creation_time": _iso(REF - timedelta(days=u["created"]))}
                   for n, u in sorted(D.USERS.items(), key=lambda x: x[1]["id"])])


@app.get("/api/v2.0/robots")
def api_robots():
    user = current_user()
    if not is_admin(user):
        return _api_auth_err(user)
    return _paged([{"id": i + 1, "name": n, "level": lvl, "description": d, "disable": False,
                    "duration": e, "editable": True,
                    "creation_time": _iso(REF - timedelta(days=c)),
                    "permissions": [{"kind": "project", "namespace": pr,
                                     "access": [{"resource": "repository", "action": x.strip()} for x in pe.split(",")]}]}
                   for i, (n, lvl, pr, d, c, e, pe) in enumerate(D.ROBOTS)])


@app.get("/api/v2.0/quotas")
def api_quotas():
    user = current_user()
    if not is_admin(user):
        return _api_auth_err(user)
    return _paged([{"id": p["id"], "ref": {"id": p["id"], "name": p["name"], "owner_name": p["owner"]},
                    "hard": {"storage": -1 if p["quota"] < 0 else p["quota"] << 30},
                    "used": {"storage": _proj_usage(p)}} for p in D.PROJECTS])


@app.get("/api/v2.0/scanners")
def api_scanners():
    user = current_user()
    if not is_admin(user):
        return _api_auth_err(user)
    return jsonify([{"uuid": "6f3a2bd4-2a7e-11ee-9a2c-0242ac120007", "name": "Trivy", "description":
                     "The Trivy scanner adapter", "url": "http://trivy-adapter:8080", "disabled": False,
                     "is_default": True, "auth": "", "skip_certVerify": False, "use_internal_addr": True,
                     "vendor": "Aqua Security", "version": D.TRIVY_VERSION, "health": "healthy"}])


@app.get("/api/v2.0/registries")
def api_registries():
    user = current_user()
    if not is_admin(user):
        return _api_auth_err(user)
    return jsonify([{"id": i + 1, "name": n, "type": "docker-hub" if "Hub" in t else "docker-registry",
                     "url": u, "status": s.lower(), "insecure": False,
                     "creation_time": _iso(REF - timedelta(days=c))} for i, (n, t, u, s, c) in enumerate(D.REGISTRIES)])


@app.get("/api/v2.0/configurations")
def api_configs():
    user = current_user()
    if not is_admin(user):
        return _api_auth_err(user)
    return jsonify({"auth_mode": {"value": "db_auth", "editable": False},
                    "project_creation_restriction": {"value": "adminonly", "editable": True},
                    "self_registration": {"value": False, "editable": True},
                    "read_only": {"value": False, "editable": True},
                    "email_host": {"value": "mail.atbmarket.com", "editable": True},
                    "email_port": {"value": 25, "editable": True},
                    "robot_token_duration": {"value": 30, "editable": True}})


@app.get("/api/v2.0/labels")
def api_labels():
    scope = request.args.get("scope", "g")
    if scope == "p":
        p = _proj_lookup(request.args.get("project_id", ""))
        if not p or not can_see(current_user(), p):
            return _err("NOT_FOUND", "project not found", 404)
        items = [(n, c, d, "p", p["id"]) for n, c, d in p["labels"]]
    else:
        items = [(n, c, d, "g", 0) for n, c, d in D.GLOBAL_LABELS]
    return _paged([{"id": 10 + _hn(n) % 90, "name": n, "color": c, "description": d, "scope": s,
                    "project_id": pid, "deleted": False} for n, c, d, s, pid in items])


@app.get("/api/v2.0/search")
def api_search():
    user = current_user()
    q = request.args.get("q", "").strip().lower()
    atblog.log("harbor.search", atblog.client_ip(request), q=q, user=user or "anonymous", via="api")
    projs = [_proj_json(p, user) for p in visible_projects(user) if q and q in p["name"]]
    repos = [{"project_id": r["project"]["id"], "project_name": r["project"]["name"],
              "project_public": r["project"]["public"], "repository_name": r["name"],
              "pull_count": r["pulls"], "artifact_count": len(ARTIFACTS[r["name"]])}
             for r in REPOS.values() if q and q in r["name"].lower() and can_see(user, r["project"])]
    return jsonify(project=projs, repository=repos)


@app.get("/api/v2.0/projects")
def api_projects():
    user = current_user()
    atblog.log("harbor.catalog", atblog.client_ip(request), user=user or "anonymous", via="api")
    name = _q_name().lower()
    pub = request.args.get("public")
    projs = [p for p in visible_projects(user) if (not name or name in p["name"]) and
             (pub is None or str(p["public"]).lower() == pub.lower())]
    return _paged([_proj_json(p, user) for p in projs])


@app.route("/api/v2.0/projects", methods=["HEAD"])
def api_project_head():
    p = PROJECTS.get(request.args.get("project_name", ""))
    return Response(status=200 if p else 404)


def _api_proj(key):
    p = _proj_lookup(key)
    user = current_user()
    if not p:
        return None, user, _err("NOT_FOUND", f"project {key} not found", 404)
    if not can_see(user, p):
        atblog.log("harbor.access_denied", atblog.client_ip(request), project=p["name"],
                   user=user or "anonymous", path=request.path)
        return None, user, _api_auth_err(user)
    return p, user, None


@app.get("/api/v2.0/projects/<key>")
def api_project(key):
    p, user, err = _api_proj(key)
    return err or jsonify(_proj_json(p, user))


@app.get("/api/v2.0/projects/<key>/summary")
def api_project_summary(key):
    p, user, err = _api_proj(key)
    if err:
        return err
    out = {"repo_count": len(project_repos(p)),
           "quota": {"hard": {"storage": -1 if p["quota"] < 0 else p["quota"] << 30},
                     "used": {"storage": _proj_usage(p)}}}
    if role_in(user, p):
        cnt = {"project_admin_count": 0, "maintainer_count": 0, "developer_count": 0, "guest_count": 0,
               "limited_guest_count": 0}
        for _, r in p["members"]:
            cnt[r.lower().replace(" ", "_") + "_count"] += 1
        out.update(cnt)
    if p["registry"]:
        out["registry"] = {"id": 1, "name": "docker-hub", "url": "https://hub.docker.com", "type": "docker-hub",
                           "status": "healthy"}
    return jsonify(out)


@app.get("/api/v2.0/projects/<key>/members")
def api_project_members(key):
    p, user, err = _api_proj(key)
    if err:
        return err
    if not role_in(user, p):
        return _api_auth_err(user)
    rid = {"Project Admin": 1, "Developer": 2, "Guest": 3, "Maintainer": 4, "Limited Guest": 5}
    return _paged([{"id": p["id"] * 100 + i, "project_id": p["id"], "entity_name": n, "entity_type": "u",
                    "entity_id": D.USERS.get(n, {}).get("id", 0), "role_name": r.lower().replace(" ", ""),
                    "role_id": rid[r]} for i, (n, r) in enumerate(p["members"])])


@app.get("/api/v2.0/projects/<key>/logs")
def api_project_logs(key):
    p, user, err = _api_proj(key)
    if err:
        return err
    if not role_in(user, p):
        return _api_auth_err(user)
    return _paged([dict(l, op_time=_iso(l["op_time"])) for l in _audit_logs([p])])


@app.get("/api/v2.0/audit-logs")
def api_audit_logs():
    user = current_user()
    if not user:
        return _api_auth_err(user)
    projs = D.PROJECTS if is_admin(user) else [p for p in D.PROJECTS if role_in(user, p)]
    return _paged([dict(l, op_time=_iso(l["op_time"])) for l in _audit_logs(projs)])


@app.get("/api/v2.0/repositories")
def api_all_repos():
    user = current_user()
    name = _q_name().lower()
    items = [_repo_json(r) for r in REPOS.values() if can_see(user, r["project"]) and
             (not name or name in r["name"].lower())]
    return _paged(items)


@app.get("/api/v2.0/projects/<key>/repositories")
def api_repos(key):
    p, user, err = _api_proj(key)
    if err:
        return err
    atblog.log("harbor.catalog", atblog.client_ip(request), project=p["name"], user=user or "anonymous", via="api")
    name = _q_name().lower()
    return _paged([_repo_json(r) for r in project_repos(p) if not name or name in r["name"].lower()])


@app.get("/api/v2.0/projects/<key>/repositories/<path:rest>")
def api_repo_router(key, rest):
    p, user, err = _api_proj(key)
    if err:
        return err
    ip = atblog.client_ip(request)
    rest = unquote(unquote(rest))
    if "/artifacts" in rest:
        short, _, tail = rest.partition("/artifacts")
    else:
        short, tail = rest, None
    short = short.strip("/")
    name = f"{p['name']}/{short}"
    if name not in REPOS:
        return _err("NOT_FOUND", f"repository {name} not found", 404)
    r = REPOS[name]
    if tail is None:
        return jsonify(_repo_json(r))
    tail = tail.strip("/")
    if not tail:
        atblog.log("harbor.tags_list", ip, repo=name, via="api")
        _log_pull("harbor.manifest_pull", name, ip, via="api_artifacts")
        return _paged([_art_json(a, p, short) for a in ARTIFACTS[name]])
    parts = tail.split("/")
    a = _find_art(name, parts[0])
    if not a:
        return _err("NOT_FOUND", f"artifact {name}@{parts[0]} not found", 404)
    if len(parts) == 1:
        _log_pull("harbor.manifest_pull", name, ip, a["env"], digest=a["digest"], via="api_artifact")
        return jsonify(_art_json(a, p, short))
    if parts[1] == "tags" and len(parts) == 2:
        return _paged(_art_json(a, p, short)["tags"] or [])
    if parts[1] == "additions" and len(parts) == 3:
        add = parts[2]
        if add == "build_history":
            _log_pull("harbor.manifest_pull", name, ip, a["env"], digest=a["digest"], via="api_build_history")
            return jsonify([{k: v for k, v in h.items() if k != "comment"} for h in a["config"]["history"]])
        if add == "vulnerabilities":
            atblog.log("harbor.vuln_report", ip, repo=name, digest=a["digest"], via="api")
            if a["vulns"] is None:
                return jsonify({})
            s = _scan_summary(a)
            return jsonify({REPORT_MT: {
                "generated_at": _iso(a["scan_end"]),
                "artifact": {"repository": name, "digest": a["digest"], "mime_type": MANIFEST_MT},
                "scanner": {"name": "Trivy", "vendor": "Aqua Security", "version": D.TRIVY_VERSION},
                "severity": s["severity"],
                "vulnerabilities": [{
                    "id": v["id"], "package": v["package"], "version": v["version"],
                    "fix_version": v["fix_version"], "severity": v["severity"], "description": v["description"],
                    "links": [f"https://avd.aquasec.com/nvd/{v['id'].lower()}"],
                    "preferred_cvss": {"score_v3": v["score"] or None, "score_v2": None},
                    "cwe_ids": [v["cwe"]] if v["cwe"] else [], "vendor_attributes": None}
                    for v in a["vulns"]]}})
        if add == "sbom":
            pk = _sbom_packages(a)
            if pk is None:
                return _err("NOT_FOUND", "sbom not found", 404)
            return jsonify({"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
                            "name": f"{D.REGISTRY_HOST}/{name}@{a['digest']}",
                            "creationInfo": {"creators": ["Organization: aquasecurity",
                                                          f"Tool: trivy-{D.TRIVY_VERSION.lstrip('v')}"],
                                             "created": _iso(a["scan_end"])},
                            "packages": [{"name": n, "SPDXID": f"SPDXRef-Package-{_h(n, v)[:16]}",
                                          "versionInfo": v, "licenseConcluded": lic or "NOASSERTION",
                                          "primaryPackagePurpose": "LIBRARY",
                                          "annotations": [{"comment": f"PkgType: {t}"}]} for n, v, t, lic in pk]})
        return _err("NOT_FOUND", f"addition {add} not found", 404)
    return _err("NOT_FOUND", "not found", 404)


@app.route("/api/<path:_rest>", methods=["POST", "PUT", "PATCH", "DELETE"])
def api_write(_rest):
    user = current_user()
    atblog.log("harbor.write_denied", atblog.client_ip(request), user=user or "anonymous",
               method=request.method, path=request.path)
    if not user:
        return _api_auth_err(user)
    return _err("FORBIDDEN", "forbidden", 403)


@app.get("/api/<path:_rest>")
def api_unknown(_rest):
    return _err("NOT_FOUND", "not found", 404)


# ---------------------------------------------------------------------------
# Docker Registry HTTP API v2
# ---------------------------------------------------------------------------
def _v2_err(code, msg, status, detail=None, auth=False):
    resp = jsonify(errors=[{"code": code, "message": msg, "detail": detail}])
    resp.status_code = status
    resp.headers["Docker-Distribution-API-Version"] = "registry/2.0"
    if auth:
        resp.headers["WWW-Authenticate"] = f'Basic realm="{D.REGISTRY_HOST}"'
    return resp


def _v2_repo(repo):
    """Return (repo, error_response)."""
    if repo not in REPOS:
        return None, _v2_err("NAME_UNKNOWN", "repository name not known to registry", 404, {"name": repo})
    user = current_user()
    if not can_see(user, REPOS[repo]["project"]):
        atblog.log("harbor.access_denied", atblog.client_ip(request), repo=repo, user=user or "anonymous",
                   path=request.path)
        if not user:
            return None, _v2_err("UNAUTHORIZED", "unauthorized to access repository", 401,
                                 [{"Type": "repository", "Class": "", "Name": repo, "Action": "pull"}], auth=True)
        return None, _v2_err("DENIED", "requested access to the resource is denied", 403)
    return repo, None


@app.get("/v2/")
@app.get("/v2")
def registry_ping():
    ip = atblog.client_ip(request)
    atblog.log("harbor.ping", ip)
    resp = jsonify({})
    resp.headers["Docker-Distribution-API-Version"] = "registry/2.0"
    return resp, 200


@app.get("/v2/_catalog")
def catalog():
    ip = atblog.client_ip(request)
    user = current_user()
    atblog.log("harbor.catalog", ip, user=user or "anonymous", msg="registry catalog listing")
    names = sorted(r for r in REPOS if can_see(user, REPOS[r]["project"]))
    last = request.args.get("last")
    if last:
        names = [n for n in names if n > last]
    try:
        n = int(request.args.get("n", 0))
    except ValueError:
        n = 0
    resp = jsonify(repositories=names[:n] if n > 0 else names)
    if 0 < n < len(names):
        resp.headers["Link"] = f'</v2/_catalog?last={quote(names[n - 1], safe="")}&n={n}>; rel="next"'
    return resp, 200


@app.get("/v2/<path:repo>/tags/list")
def tags_list(repo):
    ip = atblog.client_ip(request)
    atblog.log("harbor.tags_list", ip, repo=repo)
    _, err = _v2_repo(repo)
    if err:
        return err
    tags = sorted({t for a in ARTIFACTS[repo] for t in a["tags"]})
    return jsonify(name=repo, tags=tags), 200


@app.route("/v2/<path:repo>/manifests/<ref>", methods=["GET", "HEAD"])
def manifest_pull(repo, ref):
    ip = atblog.client_ip(request)
    if repo not in REPOS:
        atblog.log("harbor.manifest_pull", ip, repo=repo, tag=ref, msg="unknown repository")
        return _v2_err("MANIFEST_UNKNOWN", "manifest unknown", 404, repo)
    _, err = _v2_repo(repo)
    if err:
        return err
    a = _find_art(repo, ref)
    if not a:
        atblog.log("harbor.manifest_pull", ip, repo=repo, tag=ref, msg="unknown tag")
        return _v2_err("MANIFEST_UNKNOWN", "manifest unknown", 404, {"Tag": ref})
    if request.method == "GET":
        _log_pull("harbor.manifest_pull", repo, ip, a["env"], tag=ref)
    resp = Response(a["manifest_b"] if request.method == "GET" else b"", mimetype=MANIFEST_MT)
    resp.headers["Docker-Content-Digest"] = a["digest"]
    resp.headers["Docker-Distribution-API-Version"] = "registry/2.0"
    resp.headers["Content-Length"] = str(len(a["manifest_b"]))
    resp.headers["Etag"] = f'"{a["digest"]}"'
    return resp


@app.route("/v2/<path:repo>/blobs/<digest>", methods=["GET", "HEAD"])
def blob_pull(repo, digest):
    ip = atblog.client_ip(request)
    _, err = _v2_repo(repo)
    if err:
        return err
    owned = False
    for a in ARTIFACTS[repo]:
        if a["config_digest"] == digest or digest in [l["digest"] for l in json.loads(a["manifest_b"])["layers"]]:
            owned = a
            break
    if not owned or digest not in BLOBS:
        return _v2_err("BLOB_UNKNOWN", "blob unknown to registry", 404, digest)
    data, mt = BLOBS[digest]
    if mt == CONFIG_MT and request.method == "GET":
        _log_pull("harbor.manifest_pull", repo, ip, owned["env"], blob=digest, via="config_blob")
    resp = Response(data if request.method == "GET" else b"", mimetype="application/octet-stream")
    resp.headers["Docker-Content-Digest"] = digest
    resp.headers["Content-Length"] = str(len(data))
    resp.headers["Docker-Distribution-API-Version"] = "registry/2.0"
    return resp


@app.route("/v2/<path:_rest>", methods=["POST", "PUT", "PATCH", "DELETE"])
def registry_write(_rest):
    user = current_user()
    atblog.log("harbor.write_denied", atblog.client_ip(request), user=user or "anonymous",
               method=request.method, path=request.path)
    if not user:
        return _v2_err("UNAUTHORIZED", "authentication required", 401, auth=True)
    return _v2_err("DENIED", "requested access to the resource is denied", 403)


@app.get("/service/token")
def service_token():
    user = current_user()
    tok = base64.urlsafe_b64encode(json.dumps({"sub": user or "", "iss": "harbor-token-issuer",
                                                "scope": request.args.get("scope", "")}).encode()).decode()
    return jsonify(token=tok, access_token=tok, expires_in=1800, issued_at=_iso(datetime.now(timezone.utc)))


# ---------------------------------------------------------------------------
# Convenience endpoint used by the ops runbooks: image config ENV as JSON.
# ---------------------------------------------------------------------------
@app.get("/image/<path:repo>/env")
def image_env(repo):
    ip = atblog.client_ip(request)
    tag = request.args.get("tag", "latest")
    if repo not in REPOS:
        atblog.log("harbor.manifest_pull", ip, repo=repo, msg="unknown repository")
        return jsonify(errors=[{"code": "NAME_UNKNOWN", "message": "repository name not known",
                                "detail": repo}]), 404
    _, err = _v2_repo(repo)
    if err:
        return err
    a = _find_art(repo, tag) or ARTIFACTS[repo][0]
    _log_pull("harbor.manifest_pull", repo, ip, a["env"])
    return jsonify(a["env"]), 200


@app.get("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80, threaded=True)
