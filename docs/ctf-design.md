# CTF design (organizers only — spoilers)

The lab is a CTF: players get only the perimeter and must reach everything else
by taking a shell and pivoting. No flags, no scoreboard — objectives are the 10
steps of the original kill-chain. Every web service must be fully usable by
clicking in a browser; non-HTTP steps (ZBXD, SSH, Oracle, DBs) are done from a
shell the player has obtained, using the tools that box already has.

## Topology

| Zone | Services | Reachable from |
|------|----------|----------------|
| Perimeter (host ports) | www :8080, mobapp :8081, education :8082, supplier :8083, exchange OWA :8444, splunk :8000 | player's browser |
| Internal (no host ports) | grafana :3000, zabbix :80, zabbix-db :3306, harbor :80, jenkins ZBXD :10050, ad-ldap :80, oracle-mocks 1581/1521/1251, bastion :22, gitlab :22, squid :3128, ishop-db, supplier-db, education-db, storeplus-db | a shell inside the `atb` network |

Splunk on :8000 with `admin:changeme` is intentional — that's how it was in the
original infra. It is a joke/bonus, not a step.

`docker-compose.dev.yml` re-exposes internal services on the old host ports for
organizers (`make up-dev`). Players never get it.

## Chain and breadcrumbs (in-world only — no "CTF hint" text anywhere)

1. **Recon.** www footer links to the mobile app page (mobapp), the staff LMS
   (education), the supplier portal and webmail. mobapp `/` offers
   `atb-market.apk` (a zip built at image build time) whose
   `assets/index.android.bundle` contains the API base URL and the Basic creds
   `reg_user:basic*88password!prod99`. education's front page JS calls
   `/md/blocks/moco_news/ajax.php` with `procedure=getNews`; `procedure=getPosts`
   leaks config: `education@atbmarket.com:Edu003868$`, Moodle DB creds, salt.
2. **SQLi.** www catalog filter checkboxes produce `filter[8][490]=1`; the array
   key is injectable (boolean 200/500). Dumps `ishop.users`.
3. **Supplier portal.** Self-registration; "Forgot password" form has hidden
   `link=0` — set to `1` and the response returns the reset GUID.
4. **LFI.** After login: Import wizard → mapping refresh posts `importFile`.
   Reads `config.php` (supplier-db creds), `config_override.php` (3 Oracle DSNs +
   Blowfish mailbox password), `/etc/zabbix/zabbix_agentd.conf`
   (`Server=zb-app-p01`, comment pointing to `http://grafana.atbmarket.com:3000`).
5. **Web-shell.** Upload a phar/PNG polyglot padded past 180 KB (WAF window),
   trigger `phar://` via importFile → `/upload/shell.php` (uid 993 nginx on
   sp-web-p01). The shell has a browser UI (command box, upload, download) and
   still accepts `?z=<base64 cmd>`. Box has python3, `sqlplus` (client for the
   oracle mocks) and `zabbix_get`-less agent config. Player pivots from here
   (chisel/ligolo/python SOCKS/etc.) to browse internal web UIs.
6. **Grafana → Zabbix.** Grafana (internal :3000) accepts the reused
   `education@atbmarket.com:Edu003868$`. Data source "Zabbix DB" (MySQL
   `zabbix-db`, user `grafana`) is over-privileged (INSERT/UPDATE on zabbix.*).
   In Explore the player runs `SELECT session_key FROM config`, then
   `INSERT INTO sessions (sessionid,userid,lastaccess,status,secret) VALUES (...)`
   for userid 1 (Admin). Forged cookie (Zabbix 6.0 CEncryptedCookieSession):
   `zbx_session = base64(json)` where json = `{"sessionid":"<sid>","sign":"<hex>"}`
   and `sign = HMAC-SHA256(session_key, '{"sessionid":"<sid>"}')` (compact JSON of
   the payload without `sign`; extra keys like serverCheckResult are allowed and
   are included in the signed JSON in their given order). Zabbix UI as Admin →
   Administration → Scripts → create → Monitoring → Hosts → host menu → run
   script → output as **root** on zb-app-p01.
7. **Keys.** Zabbix Hosts list shows `jenkins.atbmarket.com` (agent 10050) and
   `bkp-atman`. Jenkins' agent accepts only `Server=zb-app-p01` (peer IP must be
   the zabbix container), so the player runs `zabbix_get -s jenkins.atbmarket.com
   -k 'system.run[...]'` from zabbix RCE. `/mnt/BACKUP/root.tar.gz` →
   `root/.ssh/id_rsa_root` → `ssh root@bastion-main-p01` (zabbix has
   openssh-client).
8. **Databases.** bastion root `.bash_history` points at harbor, gitlab, DB hosts;
   bastion has mysql/psql clients. Harbor UI (internal) lets anonymous users
   browse public project `ishop`; image Build History shows `ENV` with ishop
   MySQL and store-plus Postgres creds. Oracle creds from step 4 work with
   `sqlplus` on sp-web-p01. AD bind with reused edu creds against ad-ldap.
9. **Mail.** Blowfish value in `config_override.php` + key in
   `custom/blowfish/` (readable via LFI/shell) → `supplier@atbmarket.com:
   supplier123569` → OWA (perimeter :8444): inbox with 15 907 items, reset GUIDs.
10. **Source.** `ssh root@gitlab-p01` with the same key (from bastion) → 524 repos.

## Fixed values

| What | Value |
|------|-------|
| zabbix-db | db `zabbix`; app user `zabbix:Zbx_Srv_2026!`; grafana user `grafana:Gr4f4na_DS_ro` (SELECT, INSERT, UPDATE, DELETE on zabbix.*) ; root uses `MYSQL_ROOT_PASSWORD` |
| Zabbix session_key | `713a5c3bc0688c7106abfdd90bfcd0d1` (in `config.session_key`) |
| Zabbix Admin | userid 1, username `Admin`, password `Zbx!Adm_n0t-guessable_7731` (not meant to be cracked) |
| Grafana login | `education@atbmarket.com : Edu003868$` |
| Webshell contract | `GET /upload/shell.php?z=<base64 cmd>` → `text/plain` output (used by `attack/solve.py`) |
