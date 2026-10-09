# CTF design (organizers only — spoilers)

The lab is a CTF: players get only the perimeter and must reach everything else
by taking a shell and pivoting. No flags, no scoreboard — objectives are the 10
steps of the original kill-chain. Every web service must be fully usable by
clicking in a browser; non-HTTP steps (ZBXD, SSH, Oracle, DBs) are done from a
shell the player has obtained, using the tools that box already has.

## Topology

| Zone | Services | Reachable from |
|------|----------|----------------|
| Perimeter (host ports, overridable via `*_PORT`) | www :8080, mobapp :8081, education :8082, supplier :8083, exchange OWA :8444, splunk :8000 | player's browser |
| Internal (no host ports) | grafana :3000, zabbix :80, zabbix-db :3306, harbor :80, jenkins ZBXD :10050, ad-ldap :80, oracle-mocks 1581/1521/1251, bastion :22, gitlab :22, squid :3128, ishop-db, supplier-db, education-db, storeplus-db | a shell inside the `atb` network |

Splunk on :8000 with `admin:changeme` is intentional — that's how it was in the
original infra. It is a joke/bonus, not a step.

`docker-compose.dev.yml` re-exposes internal services on the old host ports for
organizers (`make up-dev`). Players never get it.

## Chain and breadcrumbs (in-world only — no "CTF hint" text anywhere)

1. **Recon.** www footer links to mobapp, education, supplier and OWA. mobapp `/`
   offers `atb-market.apk` (zip) whose `assets/index.android.bundle` holds
   `reg_user:basic*88password!prod99`. education's page JS calls
   `/md/blocks/moco_news/ajax.php` with `procedure=getNews`; a JS comment names
   the legacy `getPosts`, which leaks `education@atbmarket.com:Edu003868$`,
   Moodle DB creds and the salt. Unknown procedures return a 400 JSON error.
2. **SQLi.** Category tiles link to `filter[8][<attr>]=1` and the page echoes the
   active filter; the array key is injectable (boolean 200/500).
3. **Supplier portal.** Sign-up form carries hidden `link=0` → "link e-mailed,
   wait for moderator". With `link=1` the response contains the
   `Changenewpassword&guid=…` link, which renders a set-password form. Then log
   in (`/index.php?action=Login`, `PHPSESSID` cookie). Import is **401 without a
   session**.
4. **LFI** (Import → `importFile`, logged in). Paths are discoverable:
   `config.php` (relative, comment names `/var/www/config.php`) →
   `config_override.php` (SuiteCRM convention; also readable relative) — Oracle
   DSNs, LDAP host `DC-MAIN-01.atbmarket.com` + bind user, and the inbound mailbox
   password as `blowfishEncode(blowfishGetKey('InboundEmail'), …)`. The key is the
   SuiteCRM-standard `/var/www/custom/blowfish/InboundEmail.php`.
   `/var/www/README.ops` maps the box (webroot, upload dir, zabbix agent conf,
   bastion). `/etc/zabbix/zabbix_agentd.conf`: `Server=zb-app-p01`,
   `AllowKey=system.run[*]` ("same template on every prod host"), and the Grafana
   URL `http://grafana.atbmarket.com:3000` ("login = your corporate e-mail").
5. **Web-shell.** Unchanged mechanics (phar trigger padded past the 180 KB WAF
   window → `/upload/shell.php?z=<b64>`). Open item: nothing in-world yet hints
   at the WAF window or the shell location — organizers decide how much to give.
6. **Grafana → Zabbix.** Grafana (internal :3000, Grafana 10 emulation with
   live dashboards) takes the reused edu creds. Its "Zabbix DB" data source
   (Connections → Data sources) is MySQL user `grafana` on `zabbix-db`, granted
   SELECT/INSERT/UPDATE/DELETE on `zabbix.*`. Example queries are neutral.
   **Zabbix is the real 6.0.48** (official images): server `zb-app-p01`,
   frontend `http://zabbix.atbmarket.com:8080` (named in the supplier box's agent
   conf). Admin's password is random, so the player needs real Zabbix 6.0
   knowledge: `config.session_key` signs the `zbx_session` cookie
   (`CEncryptedCookieSession`: base64 JSON, `sign = hash_hmac('sha256',
   json_encode(data without sign), session_key)`), and sessions live in the
   `sessions` table (no `secret` column in 6.0). INSERT an active session for
   userid 1, forge the cookie → frontend as Admin. Also valid: the inserted
   sessionid works directly as a JSON-RPC `auth` token. Administration → Scripts
   → a global script with "Execute on: Zabbix server" → runs as **root**
   (`AllowRoot=1`).
7. **Keys.** Zabbix lists jenkins.atbmarket.com and `bkp-atman (Backup CIFS)`;
   jenkins has an item "Backup share //bkp-atman/BACKUP: usage" =
   `system.run[df -h /mnt/BACKUP | tail -1]` (Latest data shows the mount).
   Jenkins' agent **drops any peer that is not zb-app-p01**, so the player runs
   `zabbix_get` (ships with the server image) from a Zabbix script. On jenkins
   `/etc/fstab` shows `//bkp-atman/BACKUP /mnt/BACKUP`. `root.tar.gz` holds
   `id_rsa_root`, `.ssh/config` (bastion = `bastion-main-p01`; gitlab =
   `gitlab-p01` with `ProxyJump bastion`) and a `.bash_history`. zabbix has `ssh`;
   so does the supplier box.
8. **Databases.** bastion `/root/.bash_history` points at harbor (`/v2/_catalog`),
   `db-ishop-p01` ("moved off 10.0.7.118" — the IP in the harbor DSN), store-plus
   Postgres, the AD `/bind` endpoint and gitlab. bastion has mysql/psql/curl.
   Harbor image env leaks ishop MySQL + store-plus Postgres creds. Oracle creds
   from step 4 work with `/usr/local/bin/oracle_probe.py` on sp-web-p01.
9. **Mail.** Decrypt the Blowfish value (ECB, null-padded, key from step 4) →
   `supplier123569` → OWA (perimeter) inbox with reset GUIDs.
10. **Source.** gitlab sshd has `AllowUsers root@172.31.0.10` (bastion's pinned
    IP), so root must come *through* the bastion (ProxyJump / copy the key there).
    → 524 repos.

## Fixed values

| What | Value |
|------|-------|
| zabbix-db | db `zabbix` (utf8mb4_bin, real 6.0 schema created by the server); server/frontend user `zabbix:Zbx_Srv_2026!`; grafana user `grafana:Gr4f4na_DS_ro` (SELECT, INSERT, UPDATE, DELETE on zabbix.*) |
| Zabbix session_key | generated by the frontend on first login (`zabbix-init`) — differs per install; read it from `config` |
| Zabbix Admin | userid 1, `Admin`; `zabbix-init` rotates the default password to a random one nobody knows. Other users (o.kravets, noc, svc.reports) also random |
| Grafana login | `education@atbmarket.com : Edu003868$` (port 3000) |
| Blowfish key (InboundEmail) | `9b4f2c7e-31d8-4a6e-b0c5-7d2e8f1a6c39`; ciphertext `48HBtlcz5PGpXdkX6RkJqw==` |
| bastion IP (pinned) | `172.31.0.10`; dynamic IPs come from `172.31.128.0/17` |
| Webshell contract | `GET /upload/shell.php?z=<base64 cmd>` → `text/plain` output (used by `attack/solve.py`) |

## Side findings (not on the main chain — for exploration)

Every web app is a working product emulation with realistic data. Things a
player may find that don't skip any step:

- **www**: register/login/cart/checkout/orders. `ishop.users` (4000 rows) holds
  real bcrypt hashes, ~35% weak — the SQLi dump is crackable (e.g.
  `petro@example.ua:qwerty123`) and those logins work in "Мій кабінет".
- **mobapp**: `/api/docs` + OpenAPI; registration leaks the OTP in an
  `X-Debug-OTP` header; `/api/v1/loyalty/card/<13 digits>` is an IDOR.
- **education**: real Moodle-style login; ten staff use weak passwords stored as
  `md5(password . passwordsaltmain)` — the salt from the step-1 leak makes them
  crackable once the Moodle DB is reached (creds also in the leak).
  `education@atbmarket.com` is not a working LMS login.
- **supplier**: full SuiteCRM back-office on pp_web1. The `link=1` reset also
  takes over seeded staff accounts (e.g. `admin`) — no extra privileges.
- **exchange**: full OWA (folders, attachments, send between mailboxes, calendar,
  GAL). Only the supplier mailbox is reachable; password change is refused.
- **harbor**: Harbor 2 UI + API v2.0, Trivy CVEs, SBOM. `reg_user` (mobile cred)
  logs in as Developer on `mobapp` / Guest on private `loyalty`; a decoy
  RabbitMQ DSN in `loyalty/bonus-api`.
- **ad-ldap**: directory portal + LDAP-ish JSON API (filters, paging, rootDSE),
  831 office objects + generated store staff (68 250 total).
