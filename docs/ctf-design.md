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
6. **Grafana → Zabbix.** Grafana (internal :3000) takes the reused edu creds.
   Explore's default/example queries are neutral (`hosts`, `sessions`); the player
   must know Zabbix keeps `config.session_key` and that the frontend cookie is
   HMAC-signed (the Zabbix 401 page says the cookie is "signed with the frontend
   session key"; footer shows 6.0.18). INSERT a session for userid 1 (Admin is
   discoverable via `SELECT * FROM users`), forge the cookie, Scripts → root.
7. **Keys.** Zabbix Hosts lists `jenkins.atbmarket.com:10050` and `bkp-atman
   (Backup CIFS)`. Jenkins' agent **drops any peer that is not zb-app-p01**, so
   the web-shell can't reach it — the player uses `zabbix_get` (installed on
   zb-app-p01) from a Zabbix script. On jenkins `/etc/fstab` shows
   `//bkp-atman/BACKUP /mnt/BACKUP`. `root.tar.gz` holds `id_rsa_root`,
   `.ssh/config` (bastion = `bastion-main-p01`; gitlab = `gitlab-p01` with
   `ProxyJump bastion`) and a `.bash_history`. zabbix has `ssh`; so does the
   supplier box.
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
| zabbix-db | db `zabbix`; app user `zabbix:Zbx_Srv_2026!`; grafana user `grafana:Gr4f4na_DS_ro` (SELECT, INSERT, UPDATE, DELETE on zabbix.*) ; root uses `MYSQL_ROOT_PASSWORD` |
| Zabbix session_key | `713a5c3bc0688c7106abfdd90bfcd0d1` (in `config.session_key`) |
| Zabbix Admin | userid 1, username `Admin`, password `Zbx!Adm_n0t-guessable_7731` (not meant to be cracked) |
| Grafana login | `education@atbmarket.com : Edu003868$` (port 3000) |
| Blowfish key (InboundEmail) | `9b4f2c7e-31d8-4a6e-b0c5-7d2e8f1a6c39`; ciphertext `48HBtlcz5PGpXdkX6RkJqw==` |
| bastion IP (pinned) | `172.31.0.10`; dynamic IPs come from `172.31.128.0/17` |
| Webshell contract | `GET /upload/shell.php?z=<base64 cmd>` → `text/plain` output (used by `attack/solve.py`) |
