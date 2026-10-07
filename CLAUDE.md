# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A deliberately vulnerable Docker **CTF** that reproduces the 10-step "ATB Market" red-team kill-chain (source write-up: `../81e06c1c-….pdf`), with Splunk ingesting telemetry from every stage. All hosts, credentials and vulns are fictional and intentionally insecure — the hard-coded passwords in `.env`, `attack/` and `services/` are scenario data, not leaks to "fix". Exploitability of each step is the product; don't harden services unless asked.

It's framed as a CTF: players get only the **perimeter** (www, mobapp, education, supplier, exchange/OWA, Splunk) and must take a shell (the step-5 phar web-shell on the supplier box) and pivot across the flat `atb` network to reach everything else. Every web service is a real, clickable browser UI. Non-HTTP steps (ZBXD, SSH, Oracle, raw DBs) are run from the pivot shell, which ships DB/SSH/`nc`/python clients. See `docs/ctf-design.md` and `SOLUTIONS.md` (both spoilers). The Splunk `admin:changeme` default is an intentional in-joke, not a step.

## Commands

```bash
make up        # bootstrap.sh (ssh key + leaked backup) -> build atb-base -> docker compose up -d  (PERIMETER ONLY)
make up-dev    # ALSO expose internal services on host ports (organizers; docker-compose.dev.yml)
make ps        # wait ~60-90 s after up for DB seed + Splunk
make solve     # attack/solve.py reference solver, all 10 steps PASS/FAIL — REQUIRES `make up-dev`
make logs      # follow container logs
make down      # stop;  make reset = down -v + wipe logs/*.json;  make clean = also drop atb-base image
```

`make solve`/`solve.py` are stdlib-only and target the dev-exposed host ports, so they need `make up-dev`. The authentic player path instead pivots from the web-shell; the reference solver is just an organizer smoke test.

Iterating on one service: `docker compose up -d --build <service>` (the base image must already exist; rebuild it with `make base` after changing `services/_base/Dockerfile` or `services/_lib/atblog.py`, then rebuild dependents).

There is no unit-test suite. Verify a change with `make up-dev && make solve` (the reference solver, all 10 steps PASS/FAIL), or by running a step's commands from `SOLUTIONS.md` (URLs with `filter[...]` need `curl -g`), then checking the event in Splunk (http://localhost:8000, admin/changeme): `index=atb event=<service>.<name>`. Every service also has `/healthz`, and events are echoed to `docker logs <service>`.

## Architecture

- **One flat bridge network `atb`** (`172.31.0.0/16`). Scenario hostnames/IPs from the report (e.g. `sp-web-p01`, `zb-app-p01`, `erpdb`, `DC-MAIN-01.atbmarket.com`) are network aliases in `docker-compose.yml`, so in-container code uses those names. **Only perimeter services publish host ports** in the base compose; internal services have no `ports:` and are reached by alias on the `atb` network. `docker-compose.dev.yml` (merged by `make up-dev`) re-adds host ports for every internal service — organizer-only.
- **Step-6 couples three pieces**: `grafana` and `zabbix` both talk to the new `zabbix-db` (seed in `seed/mysql-zabbix/`). Grafana's Explore SQL console runs arbitrary SQL as the over-privileged `grafana` DB user (reads `config.session_key`, INSERTs a forged row into `sessions`); Zabbix verifies the `zbx_session` cookie against that same DB. The cookie contract (base64 JSON + HMAC-SHA256 over `{"sessionid":"…"}` with the session key) must stay identical in both services and in `attack/solve.py`. Note: `passwd` in the zabbix `users` seed must be ≤60 chars (MySQL 8 strict mode aborts the whole seed otherwise).
- **Python services share `atb-base`** (`services/_base/Dockerfile`: python 3.12 + flask, pymysql, psycopg2, cryptography, requests). Each `services/<name>/Dockerfile` is `FROM atb-base:latest`, copies a single `app.py`, and sets `ATB_SERVICE` / `ATB_HOSTNAME`. Build context is the repo root for every service, so Dockerfiles `COPY services/...` and `keys/...` paths.
- **Real vs mocked**: www (SQLi against the real `ishop-db` MySQL), supplier (LFI + phar webshell + 180KB WAF bypass, runs as `nginx` uid 993), grafana→zabbix (forged HMAC session → root RCE), jenkins (ZBXD `system.run` on tcp/10050, mounts `backup-seed/` as `/mnt/BACKUP`), bastion + gitlab (real sshd on Debian, trust `keys/id_rsa_root.pub`) are working implementations. oracle-mocks (3 TCP listeners), exchange (EWS), ad-ldap (HTTP), harbor are protocol-shaped mocks. Squid only represents the "trusted /28" hop.
- **Key leak chain**: `bootstrap.sh` generates `keys/id_rsa_root` and packs it into `backup-seed/root.tar.gz`; step 7 exfiltrates that via ZBXD and uses it for steps 7/10 SSH. Bastion/gitlab images bake in the pubkey at build time, so regenerating keys requires rebuilding them. `keys/`, `backup-seed/`, `logs/` are git-ignored and excluded from the distributed tarball.
- **Seeds**: `seed/mysql-*`, `seed/postgres` are mounted into `/docker-entrypoint-initdb.d` and only run on an empty volume — use `make reset` after editing them.

## Telemetry contract

`services/_lib/atblog.py` is the detection schema: `log(event, src_ip, **fields)` appends one JSON line to `/var/log/atb/<ATB_SERVICE>.json` with fields `time, host, service, src_ip, event` + extras. `./logs` is bind-mounted into every service and read-only into Splunk, where app `splunk/apps/atb_inputs` monitors it as `index=atb sourcetype=atb:json`. Event names (`<service>.<action>`, e.g. `supplier.lfi_read`, `jenkins.zbxd_system_run`) are referenced by `splunk/apps/atb_inputs/local/savedsearches.conf` and `splunk/detections.md` — keep them stable, and update both when adding or renaming an event. The bastion/gitlab sshd containers log via `sshrc` instead of atblog.

## Known simplifications (intentional)

jenkins runs as root (report: zabbix uid 994); ishop has ~4k seeded users (report: 7.8M); Splunk REST login is disabled under the default password, so use the web UI. The step-1 mobile credential really comes from decompiling the APK — see `docs/apk-recon.md`.

## Docs

`docs/attack-chain.md` (each step in detail), `docs/asset-inventory.md` (hosts/creds/DBs), `docs/network.md` (pivot path), `splunk/detections.md` (SPL per stage), `DEPLOY.md` (port/subnet collision fixes).
