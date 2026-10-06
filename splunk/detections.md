# Splunk detections — ATB kill-chain

All events share `index=atb sourcetype=atb:json`. Field schema (from
`services/_lib/atblog.py`): `time, host, service, src_ip, event` + per-event
extras. The ready-made correlation searches ship in
`splunk/apps/atb_inputs/local/savedsearches.conf` (prefixed `ATB …`). Copy any
SPL below into Search & Reporting.

| Step | Detection idea | SPL (core) |
|------|----------------|-----------|
| 1a | Hard-coded APK creds used | `index=atb event=mobapp.hardcoded_cred_used` |
| 1a | Mobile API brute force | `index=atb event=mobapp.auth_fail \| stats count by src_ip \| where count>10` |
| 1b | Moodle config disclosure | `index=atb event=education.config_disclosure` |
| 2  | SQLi error spike / probing | `index=atb (event=www.sqli_error OR event=www.sqli_probe_true) \| timechart span=1m count by event` |
| 3  | Supplier self-reg + reset abuse | `index=atb event=supplier.password_reset_link` |
| 4  | LFI of sensitive files | `index=atb event=supplier.lfi_read importFile IN ("*config*","/etc/*","/proc/*")` |
| 5  | WAF bypass / phar RCE / webshell | `index=atb event IN (supplier.waf_bypass,supplier.phar_deserialization_rce,supplier.webshell_exec)` |
| 6  | Reused creds Grafana→Zabbix DB | `index=atb event IN (grafana.login_reused_creds,grafana.zabbix_db_write)` |
| 6  | Forged Zabbix session → root RCE | `index=atb event=zabbix.script_create_rce \| table _time src_ip command output` |
| 7  | Zabbix agent system.run | `index=atb event=jenkins.zbxd_system_run \| table _time src_ip cmd` |
| 7  | Root SSH via backup key | `index=atb event=ssh.login_root_key` |
| 8  | Creds leaked in Harbor images | `index=atb event=harbor.creds_in_layer` |
| 8  | Oracle prod auth from portal | `index=atb event=oracle.auth_ok \| stats count by instance user src_ip` |
| 8  | AD bind w/ reused creds | `index=atb event=ad.bind_reused_creds` |
| 9  | Exchange EWS stolen mailbox | `index=atb event=exchange.ews_auth` |

### Whole-chain timeline (great for the report screenshot)
```spl
index=atb | sort 0 _time | table _time host service event src_ip msg
```

### Single-actor kill-chain rollup
```spl
index=atb
| stats min(_time) as first max(_time) as last values(event) as techniques dc(service) as services by src_ip
| eval dwell=tostring(last-first,"duration")
| sort -dc(services)
```

### Verify ingestion
```spl
| tstats count where index=atb by sourcetype        # should be > 0 after `make chain`
```

If Splunk shows nothing: confirm `./logs/*.json` is filling on the host
(`tail -f logs/*.json`), and that the `atb_inputs` app mounted
(`Settings → Data inputs → Files & directories`).
