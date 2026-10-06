-- store-plus PostgreSQL: 127k employees w/ passport data (seeded small for the lab).
CREATE TABLE IF NOT EXISTS employees (
    id          SERIAL PRIMARY KEY,
    full_name   TEXT NOT NULL,
    position    TEXT,
    store       TEXT,
    passport    TEXT,          -- "АА123456"
    tax_id      TEXT,          -- ІПН
    salary      NUMERIC(10,2)
);

INSERT INTO employees (full_name, position, store, passport, tax_id, salary)
SELECT
    'Співробітник ' || g,
    (ARRAY['Касир','Менеджер','Вантажник','Товарознавець','Директор магазину'])[1 + (g % 5)],
    'ATB-' || lpad(((g % 1200) + 1)::text, 4, '0'),
    'АА' || lpad(((g * 7) % 999999)::text, 6, '0'),
    lpad(((g * 13) % 9999999999)::text, 10, '0'),
    18000 + (g % 20000)
FROM generate_series(1, 5000) AS g;

-- superuser note: the 'asu' role is created as POSTGRES_USER (superuser) by the image.
