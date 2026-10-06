SET NAMES utf8mb4;
USE ishop;

INSERT INTO products (name, price) VALUES
  ('Молоко Яготинське 2.6%', 38.90),
  ('Хліб Київський',          21.50),
  ('Кава Jacobs Monarch 230г',289.00),
  ('Вода Моршинська 1.5л',    19.90),
  ('Сир Комо 50%',           129.00);

-- baseline filter[8][490]=1 must resolve to valid SQL (-> HTTP 200)
INSERT INTO product_attr (product_id, group_id, attr_id, value) VALUES
  (1, 8, 490, '1'),
  (2, 8, 490, '1'),
  (3, 8, 491, '2'),
  (4, 8, 492, '1'),
  (5, 8, 490, '3');

-- sample of the user table (production ~7.88M rows; lab seeds a representative set).
-- password column = bcrypt of 'password123' for all demo rows.
INSERT INTO users (phone, email, password, auth_key) VALUES
  ('+380671112233','olena@example.ua','$2y$10$abcdefghijklmnopqrstuvQ8e6uFJ0nDq9wq8wz3bqkY9fWxT1J3K','AK0000000001'),
  ('+380502223344','petro@example.ua','$2y$10$abcdefghijklmnopqrstuvQ8e6uFJ0nDq9wq8wz3bqkY9fWxT1J3K','AK0000000002'),
  ('+380633334455','iryna@example.ua','$2y$10$abcdefghijklmnopqrstuvQ8e6uFJ0nDq9wq8wz3bqkY9fWxT1J3K','AK0000000003');

-- bulk-pad to a few thousand rows so COUNT(*) is non-trivial for the SQLi oracle
INSERT INTO users (phone, email, password, auth_key)
SELECT CONCAT('+38050', LPAD(n,7,'0')),
       CONCAT('user', n, '@atb.example'),
       '$2y$10$abcdefghijklmnopqrstuvQ8e6uFJ0nDq9wq8wz3bqkY9fWxT1J3K',
       CONCAT('AK', LPAD(n,10,'0'))
FROM (
  SELECT a.N + b.N*10 + c.N*100 + d.N*1000 AS n
  FROM (SELECT 0 N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
        UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) a,
       (SELECT 0 N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
        UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) b,
       (SELECT 0 N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
        UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) c,
       (SELECT 0 N UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
        UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9) d
) nums
WHERE n BETWEEN 1 AND 4000;
