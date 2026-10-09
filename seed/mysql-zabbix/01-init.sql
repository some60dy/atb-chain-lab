-- zabbix-db.atbmarket.com : Zabbix 6.0 database server.
-- The schema itself is created by zabbix-server on first start (it checks for
-- `dbversion`), so this file only prepares the database and the accounts.
-- The `grafana` account backs Grafana's "Zabbix DB" data source. It was meant
-- to be read-only but was granted write access too — that's the step-6 vuln.
CREATE DATABASE IF NOT EXISTS zabbix CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER IF NOT EXISTS 'zabbix'@'%' IDENTIFIED BY 'Zbx_Srv_2026!';
GRANT ALL PRIVILEGES ON zabbix.* TO 'zabbix'@'%';
CREATE USER IF NOT EXISTS 'grafana'@'%' IDENTIFIED BY 'Gr4f4na_DS_ro';
GRANT SELECT, INSERT, UPDATE, DELETE ON zabbix.* TO 'grafana'@'%';
FLUSH PRIVILEGES;
