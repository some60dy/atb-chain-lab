"""Step 8 - sh-harb-p01 Harbor container registry (Docker Registry v2-ish).

Mocks a private Harbor registry whose images bake DB credentials into their
image config ENV. Pulling a manifest (or hitting the convenience /image/.../env
endpoint) leaks hard-coded DSNs that were committed into the layers.
"""
from flask import Flask, request, jsonify, Response, abort
from html import escape
import atblog

app = Flask(__name__)

# In-memory catalog: repo name -> image config env (list of "KEY=VALUE" strings).
CATALOG = {
    "storeplus/excise.api": [
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "ASPNETCORE_URLS=http://+:80",
        'PG_DSN=postgresql://asu:Qw123456@pgsql-dev.store-plus.atbmarket.com:5432/asu',
    ],
    "ishop/api": [
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "NODE_ENV=production",
        'MYSQL_DSN=mysql://ishop:rEQaZ55o7x_E53oC@10.0.7.118:3306/ishop',
    ],
    "mobapp/cicd": [
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "CI=true",
        'REG_BASIC=reg_user:basic*88password!prod99',
    ],
}

# Substrings that mark an env value as a leaked secret/DSN.
_SECRET_KEYS = ("PG_DSN", "MYSQL_DSN", "REG_BASIC")


def _leaked_secrets(env):
    """Return the list of env values that carry hard-coded credentials."""
    out = []
    for item in env:
        key, _, val = item.partition("=")
        if key in _SECRET_KEYS:
            out.append(val)
    return out


def _log_pull(event, repo, ip):
    """Common logging for a manifest/env pull of a known repo."""
    atblog.log(event, ip, repo=repo)
    for secret in _leaked_secrets(CATALOG[repo]):
        atblog.log("harbor.creds_in_layer", ip, repo=repo, secret=secret,
                   msg="hard-coded DB credentials found in image config")


def _projects():
    """Top-level project name (part before first '/') -> sorted list of repos."""
    projects = {}
    for repo in CATALOG:
        proj = repo.split("/", 1)[0]
        projects.setdefault(proj, []).append(repo)
    for repos in projects.values():
        repos.sort()
    return projects


# ---------------------------------------------------------------------------
# Harbor-style browser UI (inline CSS, self-contained, anonymous browsing).
# ---------------------------------------------------------------------------
_CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,
 Helvetica,Arial,sans-serif;background:#0d1b2a;color:#e4ecf3;line-height:1.5}
a{color:#4fd1c5;text-decoration:none}
a:hover{text-decoration:underline}
header{background:#13293d;border-bottom:3px solid #1b998b;padding:14px 20px;
 display:flex;align-items:center;gap:12px}
header .logo{width:30px;height:30px;border-radius:6px;background:#1b998b;
 display:flex;align-items:center;justify-content:center;font-weight:700;color:#0d1b2a}
header h1{font-size:18px;margin:0;font-weight:600;letter-spacing:.3px}
header .host{margin-left:auto;font-size:12px;color:#7fb2c9;font-family:monospace}
.wrap{max-width:960px;margin:0 auto;padding:22px 16px}
.crumbs{font-size:13px;color:#8aa6b8;margin-bottom:18px}
.crumbs a{color:#8aa6b8}
h2{font-size:16px;font-weight:600;color:#bfe3dc;margin:0 0 14px;
 border-bottom:1px solid #22384a;padding-bottom:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}
.card{background:#13293d;border:1px solid #22384a;border-radius:8px;padding:16px;
 transition:border-color .15s,transform .15s;display:block}
.card:hover{border-color:#1b998b;transform:translateY(-2px);text-decoration:none}
.card .name{font-size:15px;font-weight:600;color:#e4ecf3;word-break:break-all}
.card .meta{font-size:12px;color:#7fb2c9;margin-top:6px}
.badge{display:inline-block;font-size:11px;background:#1b998b;color:#0d1b2a;
 border-radius:10px;padding:1px 8px;font-weight:600;margin-left:6px}
.panel{background:#13293d;border:1px solid #22384a;border-radius:8px;
 padding:0;margin-bottom:18px;overflow:hidden}
.panel .ptitle{background:#17324a;padding:10px 16px;font-size:13px;font-weight:600;
 color:#bfe3dc;border-bottom:1px solid #22384a}
.panel .pbody{padding:14px 16px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #22384a;
 word-break:break-all;vertical-align:top}
th{color:#7fb2c9;font-weight:600;text-transform:uppercase;font-size:11px;
 letter-spacing:.5px}
td.k{font-family:monospace;color:#9fd8cd;white-space:nowrap}
td.v{font-family:monospace;color:#e4ecf3}
.tag{display:inline-block;font-family:monospace;font-size:12px;background:#0d1b2a;
 border:1px solid #22384a;border-radius:4px;padding:2px 8px;margin-right:6px}
footer{color:#5c7488;font-size:11px;text-align:center;padding:24px 0}
"""


def _page(title, body):
    return Response(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title><style>{_CSS}</style></head><body>"
        "<header><div class='logo'>H</div>"
        "<h1>Harbor</h1><span class='host'>sh-harb-p01</span></header>"
        f"<div class='wrap'>{body}</div>"
        "<footer>Harbor &middot; private container registry &middot; sh-harb-p01"
        "</footer></body></html>",
        mimetype="text/html",
    )


@app.get("/")
def index():
    ip = atblog.client_ip(request)
    atblog.log("harbor.catalog", ip, msg="anonymous catalog listing")
    projects = _projects()
    cards = ""
    for proj in sorted(projects):
        n = len(projects[proj])
        cards += (
            f"<a class='card' href='/harbor/projects/{escape(proj)}'>"
            f"<div class='name'>{escape(proj)}</div>"
            f"<div class='meta'>{n} repositor{'y' if n == 1 else 'ies'}"
            "<span class='badge'>Public</span></div></a>"
        )
    body = (
        "<div class='crumbs'>Projects</div>"
        "<h2>Projects</h2>"
        f"<div class='grid'>{cards}</div>"
    )
    return _page("Projects - Harbor", body)


@app.get("/harbor/projects/<project>")
def project_repos(project):
    ip = atblog.client_ip(request)
    projects = _projects()
    if project not in projects:
        abort(404)
    atblog.log("harbor.tags_list", ip, repo=project,
               msg="anonymous project browse")
    cards = ""
    for repo in projects[project]:
        cards += (
            f"<a class='card' href='/harbor/repo/{escape(repo)}'>"
            f"<div class='name'>{escape(repo)}</div>"
            "<div class='meta'>tag: latest</div></a>"
        )
    body = (
        "<div class='crumbs'><a href='/'>Projects</a> / "
        f"{escape(project)}</div>"
        f"<h2>Repositories in {escape(project)}</h2>"
        f"<div class='grid'>{cards}</div>"
    )
    return _page(f"{project} - Harbor", body)


@app.get("/harbor/repo/<path:repo>")
def repo_detail(repo):
    ip = atblog.client_ip(request)
    if repo not in CATALOG:
        abort(404)
    # Same code path as a manifest/env pull so detections fire on a human click.
    _log_pull("harbor.manifest_pull", repo, ip)
    env = CATALOG[repo]
    rows = ""
    for item in env:
        key, _, val = item.partition("=")
        rows += (
            f"<tr><td class='k'>{escape(key)}</td>"
            f"<td class='v'>{escape(val)}</td></tr>"
        )
    project = repo.split("/", 1)[0]
    body = (
        "<div class='crumbs'><a href='/'>Projects</a> / "
        f"<a href='/harbor/projects/{escape(project)}'>{escape(project)}</a>"
        f" / {escape(repo)}</div>"
        f"<h2>{escape(repo)}</h2>"
        "<div class='panel'><div class='ptitle'>Artifacts</div>"
        "<div class='pbody'><span class='tag'>latest</span>"
        "<span class='tag'>linux/amd64</span></div></div>"
        "<div class='panel'><div class='ptitle'>Image config &middot; "
        "Build History (ENV)</div><div class='pbody'>"
        "<table><thead><tr><th>Key</th><th>Value</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></div>"
    )
    return _page(f"{repo} - Harbor", body)


@app.get("/v2/")
def registry_ping():
    ip = atblog.client_ip(request)
    atblog.log("harbor.ping", ip)
    return jsonify({}), 200


@app.get("/v2/_catalog")
def catalog():
    ip = atblog.client_ip(request)
    atblog.log("harbor.catalog", ip, msg="anonymous catalog listing")
    return jsonify(repositories=sorted(CATALOG.keys())), 200


@app.get("/v2/<path:repo>/tags/list")
def tags_list(repo):
    ip = atblog.client_ip(request)
    atblog.log("harbor.tags_list", ip, repo=repo)
    return jsonify(name=repo, tags=["latest"]), 200


@app.get("/v2/<path:repo>/manifests/<tag>")
def manifest_pull(repo, tag):
    ip = atblog.client_ip(request)
    if repo not in CATALOG:
        atblog.log("harbor.manifest_pull", ip, repo=repo, tag=tag,
                   msg="unknown repository")
        return jsonify(errors=[{"code": "MANIFEST_UNKNOWN",
                                "message": "manifest unknown",
                                "detail": repo}]), 404
    _log_pull("harbor.manifest_pull", repo, ip)
    env = CATALOG[repo]
    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "name": repo,
        "tag": tag,
        "config": {
            "mediaType": "application/vnd.docker.container.image.v1+json",
            "Env": env,
            "Cmd": ["dotnet", "app.dll"],
        },
        "layers": [
            {"mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip",
             "size": 2819413,
             "digest": "sha256:deadbeefcafebabe0000000000000000000000000000000000000000000000ab"},
        ],
    }
    return jsonify(manifest), 200


@app.get("/image/<path:repo>/env")
def image_env(repo):
    ip = atblog.client_ip(request)
    if repo not in CATALOG:
        atblog.log("harbor.manifest_pull", ip, repo=repo,
                   msg="unknown repository")
        return jsonify(errors=[{"code": "NAME_UNKNOWN",
                                "message": "repository name not known",
                                "detail": repo}]), 404
    _log_pull("harbor.manifest_pull", repo, ip)
    return jsonify(CATALOG[repo]), 200


@app.get("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80)
