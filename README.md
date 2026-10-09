# ATB Market — CTF

A self-contained Docker CTF that reproduces a 10-step red-team kill-chain against
a fictional retailer, "ATB Market". You start at the **perimeter** — a handful of
public web apps — and have to work inward: pop a shell, pivot across the internal
network, loot credentials and escalate until you reach source control. A Splunk
instance watches every host, so the same lab doubles as a blue-team exercise.

**Lab only.** Every host, credential and vulnerability here is fictional and
deliberately insecure. Run it on an isolated machine and never expose the ports.

## Rules of the game

- **You only get the perimeter.** With a normal start, the only things published
  on your host are the public web apps and Splunk (see table below). Everything
  else — Grafana, Zabbix, Harbor, Jenkins, the databases, the SSH hosts — lives
  on an internal Docker network. To touch them you must first get a foothold and
  pivot from inside, exactly like the real engagement.
- **The web is clickable.** Every web app is a real, navigable site — log in,
  click around, follow the links. You drive the HTTP/SQLi/LFI steps from your
  browser or your tooling; the non-web steps (ZBXD, SSH, Oracle, raw DBs) you run
  from the shell you land after the web-shell step.
- **Objectives = the 10 steps** below. There are no flag strings; you've done a
  step when you've achieved the described access.

## Requirements

Linux / WSL2 / macOS with Docker Engine ≥ 24 and compose v2, ~8 GB RAM
(Splunk wants ~2 GB), ~6 GB disk, `make` / `bash` / `curl` / `ssh`.

## Start it

```bash
make up        # bootstrap keys -> build -> start the lab (first run pulls Splunk ~2.5 GB)
make ps        # wait until everything is "running" (~60-90 s for DB seed + Splunk)
make down      # stop         make reset = stop + wipe volumes & logs
```

Port already taken on your host (e.g. Burp on 8080)? Override any perimeter
port: `WWW_PORT=18080 MOBAPP_PORT=18081 make up` (also `EDU_PORT`,
`SUPPLIER_PORT`, `OWA_PORT`, `SPLUNK_PORT`; defaults in `.env`).

## Your entry points (perimeter)

| Service | URL | What it is |
|---|---|---|
| ATB shop (Yii2) | http://localhost:8080 | online supermarket |
| Mobile app API | http://localhost:8081 | registration API + APK download |
| Staff LMS (Moodle) | http://localhost:8082 | employee e-learning |
| Supplier portal (SuiteCRM) | http://localhost:8083 | B2B supplier CRM |
| Corporate webmail (OWA) | http://localhost:8444 | Exchange / Outlook Web |
| Splunk (blue team) | http://localhost:8000 | SIEM — `admin` / `changeme` |

Yes, Splunk really is `admin:changeme`. That's not a challenge step — it's a wink
at the original infrastructure, where it was exactly that. Use it to watch
yourself (and to build detections): index `atb`.

Everything else is **internal** — no host port, and not listed here. Finding out
what exists inside, and how to reach it, is part of the game.

## The 10 objectives

1. **Recon.** The public apps leak more than they should. Get the mobile app's
   API credential, and find the staff portal endpoint that discloses its config.
2. **SQL injection.** Something in the shop's catalogue reaches the database
   unsanitised. Prove it and dump customers.
3. **Supplier foothold.** Get a logged-in account on the supplier portal without
   a moderator ever approving you.
4. **File read.** As a supplier, read files on the portal server. Its config
   holds secrets for half the company.
5. **Web-shell.** Turn the portal into code execution despite the WAF in front
   of it. This is your foothold inside — everything after this is a pivot.
6. **Monitoring.** Work out what monitors the portal box, get into it with what
   you already have, and become root on the monitoring server.
7. **Keys to everything.** The monitoring server can talk to things you can't.
   Find the backups, find the key, reach the jump host.
8. **Databases.** Loot the credentials scattered across registries, configs and
   shell history, and dump the retail and HR databases. Bind to the directory.
9. **Mail.** Recover the supplier group mailbox password and read its inbox.
10. **Source.** Own the source-control server — it only trusts the jump host.

Hints live *in the world*: page source, config comments, file-system notes, the
monitoring host list, shell history and SSH configs. Follow them.

## Blue team (Splunk)

Every container ships structured JSON to Splunk (index `atb`). Whole-chain view:

```spl
index=atb | sort 0 _time | table _time host service event src_ip msg
```

Per-stage correlation searches ship in the `atb_inputs` app (`ATB …`); the SPL for
each step is in [`splunk/detections.md`](splunk/detections.md).

## For organizers

- `make up-dev` additionally exposes every internal service on a host port (for
  debugging / building detections) — see [`docker-compose.dev.yml`](docker-compose.dev.yml).
  **Never give players this.**
- `make solve` (pass the same `*_PORT=` overrides) runs [`attack/solve.py`](attack/solve.py), the reference solver that
  drives all 10 steps and prints PASS/FAIL. It requires `make up-dev`.
- Full walk-through and exact values: [`docs/ctf-design.md`](docs/ctf-design.md)
  and [`SOLUTIONS.md`](SOLUTIONS.md) (spoilers).
- [`docs/attack-chain.md`](docs/attack-chain.md) has a copy-paste command block
  for every step. All 10 steps are verified working with `make solve`.

## Docs

- [docs/ctf-design.md](docs/ctf-design.md) — topology, breadcrumbs, fixed values (spoilers)
- [docs/attack-chain.md](docs/attack-chain.md) — each step in detail
- [docs/asset-inventory.md](docs/asset-inventory.md) — hosts, credentials, databases
- [docs/apk-recon.md](docs/apk-recon.md) — extracting step 1's credential from the APK
- [docs/network.md](docs/network.md) — network notes
- [splunk/detections.md](splunk/detections.md) — SPL per stage
- [DEPLOY.md](DEPLOY.md) — deployment / troubleshooting
