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

Everything else (Grafana, Zabbix, Harbor `sh-harb-p01`, Jenkins ZBXD, Oracle,
MySQL/Postgres, the bastion and GitLab) is **internal** — no host port. You reach
it by name (`grafana.atbmarket.com`, `zb-app-p01`, `harbor.atbmarket.com`,
`jenkins.atbmarket.com`, `bastion-main-p01`, `gitlab-p01`, …) once you're inside.

## The 10 objectives

1. **Recon.** Pull the mobile app from the API host and recover the hard-coded API
   credentials baked into its JS bundle. Separately, find the staff LMS endpoint
   that leaks its configuration (DB creds, a reused service account, the salt).
2. **SQL injection.** The shop's catalog filter has an injectable array **key**
   (`filter[8][<here>]`) — a boolean 200/500 oracle. Dump the customer DB.
3. **Supplier foothold.** Self-register on the supplier portal and abuse its
   password-reset to take over an account.
4. **LFI.** As a supplier user, read arbitrary server files through the Import
   mapping feature — pull the portal's config and the secrets inside it.
5. **Web-shell.** Upload a phar/PNG polyglot that slips past the WAF's 180 KB scan
   window and get code execution. **This is your foothold on the internal
   network** — pivot from here (the box has DB/SSH/`nc`/python clients).
6. **Escalate: Grafana → Zabbix → root.** Reuse a looted credential to log into
   Grafana, run SQL through its over-privileged data source to forge an admin
   session in the Zabbix DB, then use the Zabbix UI to run a script — as **root**.
7. **Keys to everything.** From Zabbix, reach the Jenkins host's monitoring agent
   (ZBXD `system.run`), read the CIFS backup it can see, recover `id_rsa_root` and
   SSH into the bastion as root.
8. **Databases.** With the keys and creds you've gathered, hit the Oracle
   instances, the Harbor registry (creds baked into image layers), Active
   Directory and the raw MySQL/Postgres.
9. **Mail.** Decrypt the supplier mailbox password and read corporate webmail —
   the inbox is full of live password-reset links.
10. **Source.** SSH into GitLab as root and confirm you own all 524 repositories.

Hints live *in the world*: footers, config comments, the Zabbix host list, the
bastion's shell history. Follow them.

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
- `make solve` runs [`attack/solve.py`](attack/solve.py), the reference solver that
  drives all 10 steps and prints PASS/FAIL. It requires `make up-dev`.
- Full walk-through and exact values: [`docs/ctf-design.md`](docs/ctf-design.md)
  and [`SOLUTIONS.md`](SOLUTIONS.md) (spoilers).

## Docs

- [docs/ctf-design.md](docs/ctf-design.md) — topology, breadcrumbs, fixed values (spoilers)
- [docs/attack-chain.md](docs/attack-chain.md) — each step in detail
- [docs/asset-inventory.md](docs/asset-inventory.md) — hosts, credentials, databases
- [docs/apk-recon.md](docs/apk-recon.md) — extracting step 1's credential from the APK
- [docs/network.md](docs/network.md) — network notes
- [splunk/detections.md](splunk/detections.md) — SPL per stage
- [DEPLOY.md](DEPLOY.md) — deployment / troubleshooting
