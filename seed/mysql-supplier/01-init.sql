SET NAMES utf8mb4;
-- supplier-db.atbmarket.com : pp_web1 (SuiteCRM web DB). Creds web_db2 / Wdjg84kV@
USE pp_web1;
CREATE TABLE IF NOT EXISTS accounts (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(190),
  email VARCHAR(190),
  created DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
INSERT INTO accounts (name,email) VALUES
  ('ATB Logistics','ops@atbmarket.com'),
  ('b9atbsup01','b9atbsup01@guerrillamailblock.com');
