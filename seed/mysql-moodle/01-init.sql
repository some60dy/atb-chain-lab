SET NAMES utf8mb4;
-- education-db : Moodle DB. Creds tmx / DGGS845k45lkk340
USE moodle;
CREATE TABLE IF NOT EXISTS mdl_user (
  id INT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(100),
  email VARCHAR(190),
  password CHAR(60)
) ENGINE=InnoDB;
INSERT INTO mdl_user (username,email,password) VALUES
  ('admin','education@atbmarket.com','$2y$10$abcdefghijklmnopqrstuvQ8e6uFJ0nDq9wq8wz3bqkY9fWxT1J3K');
