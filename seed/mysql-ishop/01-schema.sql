SET NAMES utf8mb4;
-- ishop schema: products + product_attr feed the catalog filter (SQLi target),
-- users is the 7.8M-row table from the report (seeded small for the lab).
USE ishop;

CREATE TABLE IF NOT EXISTS categories (
  id      INT PRIMARY KEY,
  slug    VARCHAR(64) NOT NULL UNIQUE,
  name    VARCHAR(100) NOT NULL,
  attr_id INT NOT NULL,          -- group 8 ("Розділ") attribute for this section
  icon    VARCHAR(16),
  bg      VARCHAR(16),
  sort    INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS products (
  id   INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(200) NOT NULL,
  price DECIMAL(10,2) NOT NULL DEFAULT 0,
  category_id INT,
  brand       VARCHAR(80),
  pack        VARCHAR(40),
  unit        VARCHAR(8) NOT NULL DEFAULT 'шт',
  old_price   DECIMAL(10,2) NULL,
  country     VARCHAR(40),
  is_own      TINYINT NOT NULL DEFAULT 0,
  is_new      TINYINT NOT NULL DEFAULT 0,
  icon        VARCHAR(16),
  description TEXT,
  composition TEXT,
  storage     VARCHAR(255),
  sku         VARCHAR(20),
  stock       INT NOT NULL DEFAULT 0,
  rating      DECIMAL(2,1) NOT NULL DEFAULT 0,
  reviews_cnt INT NOT NULL DEFAULT 0,
  popularity  INT NOT NULL DEFAULT 0,
  KEY idx_cat (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS attr_groups (
  id   INT PRIMARY KEY,
  name VARCHAR(64) NOT NULL,
  sort INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS attributes (
  group_id INT NOT NULL,
  attr_id  INT NOT NULL,
  name     VARCHAR(100) NOT NULL,
  PRIMARY KEY (group_id, attr_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS product_attr (
  id         INT PRIMARY KEY AUTO_INCREMENT,
  product_id INT NOT NULL,
  group_id   INT NOT NULL,   -- the [8] in filter[8][490]
  attr_id    INT NOT NULL,   -- the [490] -> injected key
  value      VARCHAR(64) NOT NULL,
  KEY idx_ga (group_id, attr_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS reviews (
  id         INT PRIMARY KEY AUTO_INCREMENT,
  product_id INT NOT NULL,
  user_id    INT NULL,
  author     VARCHAR(80) NOT NULL,
  rating     TINYINT NOT NULL,
  body       TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_p (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS stores (
  id      INT PRIMARY KEY AUTO_INCREMENT,
  city    VARCHAR(64) NOT NULL,
  address VARCHAR(160) NOT NULL,
  hours   VARCHAR(32) NOT NULL,
  phone   VARCHAR(20)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS users (
  id        INT PRIMARY KEY AUTO_INCREMENT,
  phone     VARCHAR(20),
  email     VARCHAR(190),
  password  VARCHAR(100),   -- bcrypt
  auth_key  VARCHAR(64),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  first_name VARCHAR(64),
  last_name  VARCHAR(64),
  bonus_card VARCHAR(20),
  status     SMALLINT NOT NULL DEFAULT 10,
  last_login DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS orders (
  id            INT PRIMARY KEY AUTO_INCREMENT,
  order_no      VARCHAR(20) NOT NULL,
  user_id       INT NULL,
  customer_name VARCHAR(130),
  phone         VARCHAR(20),
  email         VARCHAR(190),
  delivery_type VARCHAR(16) NOT NULL,   -- courier | pickup
  address       VARCHAR(255),
  store_id      INT NULL,
  slot          VARCHAR(40),
  payment       VARCHAR(16),
  comment       VARCHAR(500),
  subtotal      DECIMAL(10,2) NOT NULL DEFAULT 0,
  delivery_fee  DECIMAL(10,2) NOT NULL DEFAULT 0,
  status        VARCHAR(16) NOT NULL DEFAULT 'new',
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_u (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS order_items (
  id         INT PRIMARY KEY AUTO_INCREMENT,
  order_id   INT NOT NULL,
  product_id INT NOT NULL,
  name       VARCHAR(200) NOT NULL,
  price      DECIMAL(10,2) NOT NULL,
  qty        DECIMAL(10,3) NOT NULL,
  KEY idx_o (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- the ishop app account (MYSQL_USER) already owns ishop.*; it needs SELECT for the
-- catalogue and INSERT/UPDATE for sign-up, orders and reviews from the storefront.
GRANT SELECT, INSERT, UPDATE ON ishop.* TO 'ishop'@'%';
FLUSH PRIVILEGES;
