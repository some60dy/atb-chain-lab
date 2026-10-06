# ATB Market — Asset Inventory

> Reconstructed from the red-team write-up (`81e06c1c-….pdf`). This is the
> authoritative map of every host, credential, and database referenced in the
> kill-chain. Everything below is **fictional lab data** — the passwords are the
> ones from the scenario and exist only inside the isolated Docker network.

## 1. Hosts & services

| # | Hostname | Lab IP | Role / software | Exposed | Vuln / purpose |
|---|----------|--------|-----------------|---------|----------------|
| 1 | `mobapp.atbmarket.com` | 10.0.7.60 | Mobile registration API | 8081 | Hard-coded Basic creds in APK |
| 2 | `education.atbmarket.com` | 10.0.7.61 | Moodle (employee LMS) | 8082 | Unauth config disclosure |
| 3 | `www.atbmarket.com` | 10.0.7.62 | Yii2 e-shop | 8080 | Boolean SQLi in catalog filter key |
| 4 | `supplier.atbmarket.com` / `sp-web-p01` | 172.16.70.40 | SuiteCRM 7.10.25 (nginx/php-fpm) | 8083 | Open reg → LFI → phar deserialization RCE |
| 5 | `grafana.atbmarket.com` | 172.16.70.38 | Grafana (writes to Zabbix DB) | 3000 | Reused creds → SQL write to Zabbix |
| 6 | `zb-app-p01` | 172.16.70.37 | Zabbix server (runs as root) | 8084 | Forged session → `script.create` RCE |
| 7 | `squid-proxy` | 172.16.70.41 | Squid, trusted /28 | 8088→3128 | Firewall-bypass pivot |
| 8 | `jenkins.atbmarket.com` | 10.0.7.55 | Jenkins (user `zabbix`) | 8087 | ZBXD `system.run`; CIFS backup mount |
| 9 | `gitlab-p01.atbmarket.com` | 172.16.68.194 | GitLab CE (524 repos) | 8086 / ssh 2222 | root via stolen SSH key |
| 10 | `sh-harb-p01` | 10.0.6.198 | Harbor registry | 8085 | DB creds baked into images |
| 11 | `bastion-main-p01` | 172.16.70.10 | Bastion host | ssh 2210 | Holds `id_rsa_root` in backup |
| 12 | `bkp-atman.atbmarket.com` | 172.16.70.50 | CIFS backup share (`//…/BACKUP`) | 445 | `root.tar.gz` → `id_rsa_root` |
| 13 | `DC-MAIN-01.atbmarket.com` | 172.16.68.10 | Active Directory / LDAP | 389 | Bind with reused edu creds |
| 14 | `ex.atbmarket.com` | 172.16.68.20 | Exchange EWS | 8444 | Basic auth → 15 907 mails |
| 15 | `splunk` | 172.16.70.200 | Splunk (SIEM) | 8000 / HEC 8088 | Default `admin:changeme` |

### Database servers

| Host | Lab IP | Engine | Lab port |
|------|--------|--------|----------|
| `10.0.7.118` / `api.zakaz.atbmarket.com` | 10.0.7.118 | MySQL 8.4 (Percona) `ishop` | 3306 |
| `education-db` | 10.0.7.63 | MySQL (Moodle) | 3307 |
| `supplier-db.atbmarket.com` | 172.16.70.42 | MySQL `pp_web1` | 3308 |
| `pgsql-dev.store-plus.atbmarket.com` | 10.0.7.70 | PostgreSQL `asu` | 5432 |
| `erpdb` (Oracle EBS PROD) | 10.0.6.80 | Oracle mock | 1581 |
| `retaildb` (Oracle RMS `retekdb`) | 10.0.6.81 | Oracle mock | 1521 |
| `ISMEDOC-DB` (Oracle MEDOC `ZVITZAKUP`) | 10.0.6.82 | Oracle mock | 1251 |

## 2. Credentials harvested along the chain

| Secret | Value | Source step | Unlocks |
|--------|-------|-------------|---------|
| mobile API Basic | `reg_user : basic*88password!prod99` | 1 (APK/jadx) | `/register/login` |
| Moodle DB | `tmx : DGGS845k45lkk340` | 1 (Moodle leak) | education-db |
| corp SMTP / edu acct | `education@atbmarket.com : Edu003868$` | 1 (Moodle leak) | Grafana, AD bind |
| password salt | `4STvnJrt33TTbdIY4Qt` | 1 | hash cracking |
| supplier portal acct | `b9atbsup01@… : AtbB9Sup2026x!` | 3 (self-reg) | SuiteCRM login |
| supplier web DB | `web_db2 : Wdjg84kV@` → `pp_web1` | 4 (LFI config.php) | supplier-db |
| Oracle EBS | `XX_SUP_PORTAL_RO : S0h6jWot2fTLSMm` @ erpdb:1581/PROD | 4 (LFI override) | EBS |
| Oracle RMS | `SUPP_PORT_READER : C3KPgME{p=VyYmeTD6BqaIjN2` @ retaildb:1521/retekdb | 4 | RMS |
| Oracle MEDOC | `MEDOC : HIr3t4G8Zso7` @ ISMEDOC-DB:1251/ZVITZAKUP | 4 | MEDOC |
| Zabbix session_key | `713a5c3bc0688c7106abfdd90bfcd0d1` | 6 (Grafana→Zabbix cfg) | HMAC cookie forge |
| MySQL ishop (direct) | `ishop : rEQaZ55o7x_E53oC` @ 10.0.7.118 | 8 (Harbor image) | 7.8M users |
| PostgreSQL store-plus | `asu : Qw123456` (SUPERUSER) | 8 (Harbor image) | 127k employees |
| Exchange / supplier mail | `supplier@atbmarket.com : supplier123569` | 9 (Blowfish via LFI) | EWS |
| bastion root key | `root/.ssh/id_rsa_root` | 7 (CIFS backup) | GitLab/Jenkins/Harbor/CICD root |

## 3. Impact figures (from the report)

- `ishop.users` ≈ **7 876 935** rows (bcrypt, auth_key, phone, email)
- PostgreSQL: **127 265** employees w/ passport data
- Active Directory: **68 250** accounts
- Exchange: **15 907** inbox items, 27 with live password-reset GUIDs
- GitLab: **524** repos / 4.77 GB / 232 projects / 121 dev accounts

See [`attack-chain.md`](./attack-chain.md) for how each asset is reached, and
[`network.md`](./network.md) for segmentation.
