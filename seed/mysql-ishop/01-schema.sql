SET NAMES utf8mb4;
-- ishop schema: products + product_attr feed the catalog filter (SQLi target),
-- users is the 7.8M-row table from the report (seeded small for the lab).
USE ishop;

CREATE TABLE IF NOT EXISTS products (
  id   INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(200) NOT NULL,
  price DECIMAL(10,2) NOT NULL DEFAULT 0
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS product_attr (
  id         INT PRIMARY KEY AUTO_INCREMENT,
  product_id INT NOT NULL,
  group_id   INT NOT NULL,   -- the [8] in filter[8][490]
  attr_id    INT NOT NULL,   -- the [490] -> injected key
  value      VARCHAR(64) NOT NULL,
  KEY idx_ga (group_id, attr_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS users (
  id        INT PRIMARY KEY AUTO_INCREMENT,
  phone     VARCHAR(20),
  email     VARCHAR(190),
  password  VARCHAR(100),   -- bcrypt
  auth_key  VARCHAR(64),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- extra grant so user() / version() probing works from the www service host
GRANT SELECT ON ishop.* TO 'ishop'@'%';
FLUSH PRIVILEGES;
