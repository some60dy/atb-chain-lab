"""Step 8 - sh-harb-p01 Harbor container registry (Docker Registry v2-ish).

Mocks a private Harbor registry whose images bake DB credentials into their
image config ENV. Pulling a manifest (or hitting the convenience /image/.../env
endpoint) leaks hard-coded DSNs that were committed into the layers.
"""
from flask import Flask, request, jsonify
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


@app.get("/")
def index():
    return "<html><body><h1>Harbor (sh-harb-p01)</h1></body></html>", 200


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
