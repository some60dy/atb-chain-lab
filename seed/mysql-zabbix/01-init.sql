-- zabbix-db.atbmarket.com : Zabbix 6.0 frontend DB.
-- The `grafana` datasource user (created by docker-entrypoint from MYSQL_USER)
-- gets full rights on this schema — that over-privilege is the step-6 vuln:
-- it can read config.session_key and INSERT a forged admin row into `sessions`.
SET NAMES utf8mb4;
USE zabbix;

-- --- frontend config: holds the session-signing key (recovered from zabbix.conf.php)
CREATE TABLE IF NOT EXISTS config (
  configid     BIGINT UNSIGNED NOT NULL PRIMARY KEY,
  session_key  VARCHAR(32)  NOT NULL DEFAULT '',
  default_lang VARCHAR(5)   NOT NULL DEFAULT 'en_GB',
  server_check_interval INT NOT NULL DEFAULT 10
) ENGINE=InnoDB;
INSERT INTO config (configid, session_key) VALUES
  (1, '713a5c3bc0688c7106abfdd90bfcd0d1');

-- --- users: Admin is userid 1 (Super admin role). Password is a bcrypt hash and
-- is NOT meant to be cracked — the intended path is forging a session, not login.
CREATE TABLE IF NOT EXISTS users (
  userid   BIGINT UNSIGNED NOT NULL PRIMARY KEY,
  username VARCHAR(100) NOT NULL,
  passwd   VARCHAR(60)  NOT NULL DEFAULT '',
  roleid   BIGINT UNSIGNED NOT NULL DEFAULT 1,
  name     VARCHAR(100) NOT NULL DEFAULT '',
  surname  VARCHAR(100) NOT NULL DEFAULT ''
) ENGINE=InnoDB;
-- passwd is a 60-char bcrypt hash (NOT meant to be cracked); forge a session instead.
INSERT INTO users (userid, username, passwd, roleid, name, surname) VALUES
  (1, 'Admin', '$2y$10$ZbXSuperAdminHashNotForCracking0000000000000000000000', 3, 'Zabbix', 'Administrator'),
  (2, 'guest', '', 4, '', ''),
  (3, 'monitoring', '$2y$10$MonitoringReadonlyRoleHash000000000000000000000000000', 1, 'NOC', 'Monitoring');

-- --- live sessions. Empty at boot; the attacker INSERTs a forged Admin row here
-- through Grafana's over-privileged datasource, then signs a matching cookie.
CREATE TABLE IF NOT EXISTS sessions (
  sessionid  VARCHAR(32) NOT NULL PRIMARY KEY,
  userid     BIGINT UNSIGNED NOT NULL,
  lastaccess INT UNSIGNED NOT NULL DEFAULT 0,
  status     INT NOT NULL DEFAULT 0,       -- 0 = active, 1 = disabled
  secret     VARCHAR(32) NOT NULL DEFAULT ''
) ENGINE=InnoDB;

-- --- a couple of monitored hosts so the step-7 targets are discoverable in the UI
CREATE TABLE IF NOT EXISTS hosts (
  hostid BIGINT UNSIGNED NOT NULL PRIMARY KEY,
  host   VARCHAR(128) NOT NULL,
  name   VARCHAR(128) NOT NULL,
  agent_ip VARCHAR(64) NOT NULL DEFAULT '',
  agent_port INT NOT NULL DEFAULT 10050
) ENGINE=InnoDB;
INSERT INTO hosts (hostid, host, name, agent_ip, agent_port) VALUES
  (10001, 'zb-app-p01',             'Zabbix server',   '127.0.0.1',             10050),
  (10002, 'jenkins.atbmarket.com',  'CI / Jenkins',    'jenkins.atbmarket.com', 10050),
  (10003, 'bkp-atman',              'Backup (CIFS)',   'bkp-atman',             10050);
