"""SuiteCRM 7.10.25 schema + reference data for the ATB supplier portal (pp_web1).

Deterministic: same ids/values every run, so the MySQL init dump
(seed/mysql-supplier/01-init.sql) and the app's own first-boot install agree.

    python3 suitecrm_seed.py > ../../seed/mysql-supplier/01-init.sql
"""
import datetime as dt
import hashlib
import random
import uuid

SEED_VERSION = "7.10.25-atb.3"
_NS = uuid.UUID("6f1c1d5e-7a1b-4c1e-9e55-2a7d0c0ffee0")
TODAY = dt.date(2026, 10, 9)


def uid(kind, i):
    return str(uuid.uuid5(_NS, f"{kind}:{i}"))


_COMMON = """
  date_entered DATETIME NULL,
  date_modified DATETIME NULL,
  modified_user_id CHAR(36) NULL,
  created_by CHAR(36) NULL,
  assigned_user_id CHAR(36) NULL,
  description TEXT NULL,
  deleted TINYINT(1) NOT NULL DEFAULT 0"""

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS config (
  category VARCHAR(32) NOT NULL, name VARCHAR(32) NOT NULL, value TEXT,
  PRIMARY KEY (category, name)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    f"""CREATE TABLE IF NOT EXISTS users (
  id CHAR(36) NOT NULL PRIMARY KEY,
  user_name VARCHAR(190) NOT NULL, user_hash VARCHAR(255) NULL,
  first_name VARCHAR(100), last_name VARCHAR(100), title VARCHAR(100),
  department VARCHAR(100), email1 VARCHAR(190), phone_work VARCHAR(50),
  phone_mobile VARCHAR(50), address_city VARCHAR(100),
  status VARCHAR(20) DEFAULT 'Active', user_type VARCHAR(20) DEFAULT 'Staff',
  is_admin TINYINT(1) DEFAULT 0, portal_account_id CHAR(36) NULL,
  last_login DATETIME NULL,{_COMMON},
  UNIQUE KEY idx_user_name (user_name)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    f"""CREATE TABLE IF NOT EXISTS accounts (
  id CHAR(36) NOT NULL PRIMARY KEY,
  name VARCHAR(190), account_type VARCHAR(50), industry VARCHAR(50),
  edrpou VARCHAR(20), vat_number VARCHAR(20), iban VARCHAR(40), bank_name VARCHAR(100),
  payment_terms VARCHAR(30), supplier_rating VARCHAR(10),
  phone_office VARCHAR(50), email1 VARCHAR(190), website VARCHAR(190),
  billing_address_street VARCHAR(190), billing_address_city VARCHAR(100),
  billing_address_postalcode VARCHAR(20), billing_address_country VARCHAR(60),
  annual_revenue VARCHAR(60), employees VARCHAR(20),{_COMMON},
  KEY idx_acc_name (name)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    f"""CREATE TABLE IF NOT EXISTS contacts (
  id CHAR(36) NOT NULL PRIMARY KEY,
  salutation VARCHAR(20), first_name VARCHAR(100), last_name VARCHAR(100),
  title VARCHAR(100), department VARCHAR(100), account_id CHAR(36),
  email1 VARCHAR(190), phone_work VARCHAR(50), phone_mobile VARCHAR(50),
  primary_address_city VARCHAR(100), lead_source VARCHAR(50),
  do_not_call TINYINT(1) DEFAULT 0,{_COMMON},
  KEY idx_cont_acc (account_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    f"""CREATE TABLE IF NOT EXISTS opportunities (
  id CHAR(36) NOT NULL PRIMARY KEY,
  name VARCHAR(190), account_id CHAR(36), opportunity_type VARCHAR(50),
  amount DECIMAL(14,2), currency_id VARCHAR(3) DEFAULT 'UAH',
  sales_stage VARCHAR(40), probability INT, date_closed DATE,
  lead_source VARCHAR(50), next_step VARCHAR(190),{_COMMON},
  KEY idx_opp_acc (account_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    f"""CREATE TABLE IF NOT EXISTS aos_products (
  id CHAR(36) NOT NULL PRIMARY KEY,
  name VARCHAR(190), part_number VARCHAR(40), supplier_sku VARCHAR(40),
  ean VARCHAR(13), category VARCHAR(50), unit VARCHAR(10),
  cost DECIMAL(12,2), price DECIMAL(12,2), vat_rate VARCHAR(5) DEFAULT '20',
  shelf_life_days INT, min_order_qty INT, status VARCHAR(30),
  account_id CHAR(36),{_COMMON},
  KEY idx_prod_acc (account_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    f"""CREATE TABLE IF NOT EXISTS atb_pricelists (
  id CHAR(36) NOT NULL PRIMARY KEY,
  name VARCHAR(190), plist_number VARCHAR(30), account_id CHAR(36),
  status VARCHAR(30), valid_from DATE, valid_to DATE, currency VARCHAR(3) DEFAULT 'UAH',
  avg_change DECIMAL(6,2), reviewer_id CHAR(36),{_COMMON},
  KEY idx_pl_acc (account_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS atb_pricelist_items (
  id CHAR(36) NOT NULL PRIMARY KEY, pricelist_id CHAR(36), product_id CHAR(36),
  price_old DECIMAL(12,2), price_new DECIMAL(12,2), date_entered DATETIME NULL,
  deleted TINYINT(1) NOT NULL DEFAULT 0,
  KEY idx_pli_pl (pricelist_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    f"""CREATE TABLE IF NOT EXISTS atb_purchaseorders (
  id CHAR(36) NOT NULL PRIMARY KEY,
  name VARCHAR(40), account_id CHAR(36), status VARCHAR(30),
  order_date DATE, delivery_date DATE, warehouse VARCHAR(80),
  payment_terms VARCHAR(30), ttn_number VARCHAR(40),
  total_net DECIMAL(14,2) DEFAULT 0, total_vat DECIMAL(14,2) DEFAULT 0,
  total_amount DECIMAL(14,2) DEFAULT 0, currency VARCHAR(3) DEFAULT 'UAH',{_COMMON},
  KEY idx_po_acc (account_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS atb_po_lines (
  id CHAR(36) NOT NULL PRIMARY KEY, po_id CHAR(36), product_id CHAR(36),
  qty DECIMAL(12,3), unit_price DECIMAL(12,2), vat_rate DECIMAL(5,2),
  line_net DECIMAL(14,2), date_entered DATETIME NULL,
  deleted TINYINT(1) NOT NULL DEFAULT 0,
  KEY idx_pol_po (po_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    f"""CREATE TABLE IF NOT EXISTS aos_invoices (
  id CHAR(36) NOT NULL PRIMARY KEY,
  name VARCHAR(40), account_id CHAR(36), po_id CHAR(36),
  invoice_date DATE, due_date DATE, total_net DECIMAL(14,2), total_vat DECIMAL(14,2),
  total_amount DECIMAL(14,2), amount_paid DECIMAL(14,2), status VARCHAR(30),
  tax_invoice_number VARCHAR(40), erpn_status VARCHAR(30),{_COMMON},
  KEY idx_inv_acc (account_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    f"""CREATE TABLE IF NOT EXISTS documents (
  id CHAR(36) NOT NULL PRIMARY KEY,
  document_name VARCHAR(190), filename VARCHAR(190), file_mime_type VARCHAR(100),
  file_size INT, category_id VARCHAR(50), status_id VARCHAR(30), revision VARCHAR(20),
  active_date DATE, exp_date DATE, account_id CHAR(36),{_COMMON},
  KEY idx_doc_acc (account_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    f"""CREATE TABLE IF NOT EXISTS cases (
  id CHAR(36) NOT NULL PRIMARY KEY,
  case_number INT NOT NULL AUTO_INCREMENT, name VARCHAR(190),
  account_id CHAR(36), contact_id CHAR(36), status VARCHAR(30), priority VARCHAR(20),
  type VARCHAR(40), resolution TEXT,{_COMMON},
  UNIQUE KEY idx_case_number (case_number)) ENGINE=InnoDB AUTO_INCREMENT=1001 DEFAULT CHARSET=utf8mb4""",
    f"""CREATE TABLE IF NOT EXISTS calls (
  id CHAR(36) NOT NULL PRIMARY KEY,
  name VARCHAR(190), status VARCHAR(20), direction VARCHAR(20),
  date_start DATETIME, duration_minutes INT, account_id CHAR(36), contact_id CHAR(36),{_COMMON}
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    f"""CREATE TABLE IF NOT EXISTS meetings (
  id CHAR(36) NOT NULL PRIMARY KEY,
  name VARCHAR(190), status VARCHAR(20), location VARCHAR(190),
  date_start DATETIME, duration_minutes INT, account_id CHAR(36), contact_id CHAR(36),{_COMMON}
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS tracker (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, user_id CHAR(36), module_name VARCHAR(40),
  item_id CHAR(36), item_summary VARCHAR(255), date_modified DATETIME,
  KEY idx_tracker_user (user_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS users_last_import (
  id CHAR(36) NOT NULL PRIMARY KEY, assigned_user_id CHAR(36), import_module VARCHAR(40),
  bean_type VARCHAR(40), bean_id CHAR(36), date_entered DATETIME,
  deleted TINYINT(1) NOT NULL DEFAULT 0) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]

TABLES = ["config", "users", "accounts", "contacts", "opportunities", "aos_products",
          "atb_pricelists", "atb_pricelist_items", "atb_purchaseorders", "atb_po_lines",
          "aos_invoices", "documents", "cases", "calls", "meetings", "tracker",
          "users_last_import"]

# ------------------------------------------------------------------ reference
STAFF = [
    # user_name, first, last, title, department, phone, admin
    ("admin", "", "Administrator", "System Administrator", "IT", "+380 56 790-10-01", 1),
    ("o.kovalenko", "Олена", "Коваленко", "Category Manager — Dairy & Cheese", "Procurement", "+380 56 790-12-14", 0),
    ("a.shevchuk", "Андрій", "Шевчук", "Category Manager — Grocery", "Procurement", "+380 56 790-12-27", 0),
    ("m.tkachenko", "Марина", "Ткаченко", "Category Manager — Fresh", "Procurement", "+380 56 790-12-31", 0),
    ("i.melnyk", "Ірина", "Мельник", "Supplier Quality Specialist", "Quality Assurance", "+380 56 790-15-02", 0),
    ("d.bondarenko", "Дмитро", "Бондаренко", "Logistics Coordinator, DC Dnipro", "Logistics", "+380 56 790-17-45", 0),
    ("t.lysenko", "Тетяна", "Лисенко", "Accounts Payable Specialist", "Finance", "+380 56 790-19-08", 0),
    ("v.hnatiuk", "Віктор", "Гнатюк", "Head of Supplier Relations", "Procurement", "+380 56 790-12-01", 0),
    ("portal.sync", "", "Portal Sync", "Service account (EDI / MEDoc sync)", "IT", "", 0),
]


def staff_id(i):
    return "1" if i == 0 else uid("user", STAFF[i][0])


CATALOG = {
    "Dairy": [("Молоко 2,5% 900 г, плівка", "pcs", 32.40, 7), ("Кефір 1% 900 г", "pcs", 34.90, 10),
              ("Сметана 15% 350 г", "pcs", 38.50, 21), ("Сир кисломолочний 5% 350 г", "pcs", 64.90, 14),
              ("Йогурт питний полуниця 1,5% 500 г", "pcs", 37.20, 21), ("Масло вершкове 72,5% 180 г", "pcs", 78.90, 60),
              ("Ряжанка 2,5% 400 г", "pcs", 29.50, 10)],
    "Bakery": [("Хліб «Український» нарізний 650 г", "pcs", 24.90, 3), ("Батон нарізний 450 г", "pcs", 19.80, 3),
               ("Багет пшеничний 250 г", "pcs", 16.50, 2), ("Хліб житньо-пшеничний 700 г", "pcs", 27.30, 4),
               ("Булочка з маком 100 г", "pcs", 9.90, 3), ("Лаваш тонкий 300 г", "pcs", 22.00, 10)],
    "Meat": [("Ковбаса варена «Лікарська» в/г", "kg", 189.00, 20), ("Сосиски «Молочні» в/г", "kg", 172.50, 20),
             ("Ковбаса с/к «Салямі» 300 г", "pcs", 129.90, 90), ("Шинка варена «Домашня»", "kg", 219.00, 25),
             ("Сардельки «Свинячі»", "kg", 164.00, 15), ("Паштет печінковий 150 г", "pcs", 32.90, 30)],
    "Beverages": [("Вода мінеральна газована 1,5 л", "pcs", 17.90, 365), ("Вода негазована 0,5 л", "pcs", 11.20, 365),
                  ("Вода питна негазована 6 л", "pcs", 49.00, 365), ("Напій «Лимонад» 1 л", "pcs", 24.50, 180),
                  ("Сік яблучний прямого віджиму 1 л", "pcs", 39.90, 270)],
    "Grocery": [("Крупа гречана ядриця 1 кг", "pcs", 54.90, 365), ("Рис довгозернистий 1 кг", "pcs", 49.50, 540),
                ("Пшоно шліфоване 1 кг", "pcs", 28.40, 270), ("Борошно пшеничне в/г 2 кг", "pcs", 42.80, 365),
                ("Макарони «Ріжки» 800 г", "pcs", 33.90, 720), ("Пластівці вівсяні 800 г", "pcs", 36.50, 365)],
    "Produce": [("Картопля молода", "kg", 21.90, 30), ("Морква мита", "kg", 17.50, 30),
                ("Цибуля ріпчаста", "kg", 14.90, 60), ("Капуста білоголова", "kg", 12.40, 45),
                ("Огірки тепличні", "kg", 64.00, 10), ("Помідори рожеві", "kg", 79.00, 10),
                ("Яблука «Голден»", "kg", 32.50, 90)],
    "Household": [("Засіб для миття посуду, лимон 500 мл", "pcs", 34.90, 1095), ("Пральний порошок автомат 3 кг", "pcs", 189.00, 1095),
                  ("Відбілювач 1 л", "pcs", 27.50, 730), ("Мило рідке 500 мл", "pcs", 31.20, 730),
                  ("Засіб для миття скла 500 мл", "pcs", 44.90, 1095)],
    "Packaging": [("Пакет-майка ПНД 38х60, уп. 100 шт", "pack", 89.00, 0), ("Стрейч-плівка 500 мм, 2 кг", "pcs", 165.00, 0),
                  ("Гофроящик 600х400х300", "pcs", 24.50, 0), ("Термоетикетка 58х40, рул. 1000 шт", "pcs", 38.00, 0)],
    "Oils & Sauces": [("Олія соняшникова рафінована 850 мл", "pcs", 61.90, 365), ("Олія соняшникова нерафінована 500 мл", "pcs", 49.90, 270),
                      ("Майонез «Провансаль» 67% 350 г", "pcs", 38.40, 120), ("Олія соняшникова рафінована 5 л", "pcs", 329.00, 365)],
    "Confectionery": [("Печиво «Марія» 155 г", "pcs", 21.50, 270), ("Цукерки «Ромашка», ваг.", "kg", 219.00, 180),
                      ("Вафлі «Артек» 200 г", "pcs", 29.90, 270), ("Шоколад молочний 90 г", "pcs", 39.90, 365),
                      ("Пряники з начинкою 400 г", "pcs", 44.50, 60)],
    "Fish": [("Оселедець слабосолений", "kg", 139.00, 30), ("Скумбрія х/к", "kg", 259.00, 20),
             ("Філе хека с/м 1 кг", "pcs", 229.00, 300), ("Шпроти в олії 160 г", "pcs", 54.90, 730),
             ("Крабові палички охолоджені 200 г", "pcs", 44.90, 30)],
    "Poultry": [("Філе куряче охолоджене", "kg", 179.00, 7), ("Гомілка куряча охолоджена", "kg", 109.00, 7),
                ("Крила курячі охолоджені", "kg", 99.00, 7), ("Яйця курячі С1, 10 шт", "pack", 54.90, 25),
                ("Тушка курчати-бройлера", "kg", 94.00, 7)],
    "Coffee & Tea": [("Кава мелена 250 г", "pcs", 149.00, 540), ("Кава в зернах 1 кг", "pcs", 589.00, 540),
                     ("Кава розчинна сублімована 100 г", "pcs", 139.00, 720), ("Чай чорний, 100 пак.", "pack", 99.00, 720)],
    "Canned": [("Горошок зелений 420 г", "pcs", 32.90, 1095), ("Кукурудза цукрова 340 г", "pcs", 34.50, 1095),
               ("Ікра кабачкова 480 г", "pcs", 39.90, 730), ("Томатна паста 25% 70 г", "pcs", 11.90, 730),
               ("Огірки мариновані 900 мл", "pcs", 59.90, 730)],
    "Frozen": [("Пельмені «Домашні» 800 г", "pcs", 109.00, 180), ("Вареники з картоплею 900 г", "pcs", 69.00, 180),
               ("Суміш овочева с/м 400 г", "pcs", 49.90, 365), ("Морозиво пломбір 70 г", "pcs", 19.90, 270)],
    "Cheese": [("Сир «Голландський» 45%", "kg", 389.00, 120), ("Сир «Російський» 50%", "kg", 369.00, 120),
               ("Сир плавлений 90 г", "pcs", 24.90, 90), ("Бринза 300 г", "pcs", 99.00, 60)],
}
CAT_CODE = {"Dairy": "DAI", "Bakery": "BAK", "Meat": "MEA", "Beverages": "BEV", "Grocery": "GRO",
            "Produce": "FRV", "Household": "HHC", "Packaging": "PKG", "Oils & Sauces": "OIL",
            "Confectionery": "CON", "Fish": "FSH", "Poultry": "PLT", "Coffee & Tea": "COF",
            "Canned": "CAN", "Frozen": "FRZ", "Cheese": "CHE"}

# name, catalog key/industry, city, street, postcode, domain, staff idx, rating, terms
SUPPLIERS = [
    ("ТОВ «Дніпровський молокозавод»", "Dairy", "Дніпро", "вул. Молочна, 14", "49006", "dnipromoloko.com.ua", 1, "A", "Net 30"),
    ("ТОВ «Полтавська молочна ферма»", "Dairy", "Полтава", "вул. Зіньківська, 6", "36009", "pmferma.com.ua", 1, "B", "Net 30"),
    ("ПрАТ «Запорізький хлібокомбінат №7»", "Bakery", "Запоріжжя", "вул. Хлібна, 2", "69002", "zhk7.com.ua", 3, "A", "Net 14"),
    ("ТОВ «Агро-Хліб Поділля»", "Bakery", "Вінниця", "вул. Немирівське шосе, 48", "21034", "agrokhlib.vn.ua", 3, "B", "Net 14"),
    ("ТОВ «Слобожанські ковбаси»", "Meat", "Харків", "вул. Біологічна, 1", "61030", "slobkovbasy.com.ua", 3, "B", "Net 30"),
    ("ТОВ «М'ясна гільдія Галичини»", "Meat", "Львів", "вул. Городоцька, 289", "79040", "myasnagildia.lviv.ua", 3, "A", "Net 30"),
    ("ПП «Карпатське джерело»", "Beverages", "Свалява", "вул. Визволення, 37", "89300", "karpdzherelo.com.ua", 2, "A", "Net 45"),
    ("ТОВ «Полтавські крупи»", "Grocery", "Кременчук", "вул. Київська, 74", "39600", "poltavkrupy.com.ua", 2, "A", "Net 45"),
    ("ТОВ «Південна овочева база»", "Produce", "Миколаїв", "вул. Херсонське шосе, 52", "54025", "pivdenovoch.com.ua", 3, "C", "Net 14"),
    ("ТОВ «Укрпобутхім-Трейд»", "Household", "Київ", "вул. Пирогівський шлях, 135", "03187", "upbh-trade.com.ua", 2, "B", "Net 60"),
    ("ТОВ «ЕкоПак Україна»", "Packaging", "Біла Церква", "вул. Сквирське шосе, 202", "09108", "ecopak.ua", 5, "B", "Net 45"),
    ("ТОВ «Сонячна олія Слобожанщини»", "Oils & Sauces", "Харків", "просп. Героїв Харкова, 270", "61046", "sonoliya.com.ua", 2, "A", "Net 30"),
    ("ПрАТ «Кондитерська фабрика «Світанок»", "Confectionery", "Київ", "вул. Електриків, 29", "04176", "svitanok-kf.com.ua", 2, "A", "Net 45"),
    ("ТОВ «Чорноморська риба»", "Fish", "Одеса", "вул. Отамана Головатого, 1", "65031", "chornoryba.od.ua", 3, "B", "Net 30"),
    ("ТОВ «Птахофабрика «Золоте крило»", "Poultry", "Черкаси", "вул. Смілянська, 165", "18030", "zolotekrylo.com.ua", 3, "A", "Net 14"),
    ("ТОВ «Одеська кавова компанія»", "Coffee & Tea", "Одеса", "вул. Мельницька, 26", "65005", "okk.com.ua", 2, "A", "Net 60"),
    ("ТОВ «Житомирські консерви»", "Canned", "Житомир", "вул. Промислова, 7", "10025", "zhytkonserv.com.ua", 2, "B", "Net 45"),
    ("ТОВ «Морозко-Київ»", "Frozen", "Бориспіль", "вул. Запорізька, 13", "08301", "morozko-kyiv.com.ua", 3, "C", "Net 30"),
    ("ТОВ «Буковинський сир»", "Cheese", "Чернівці", "вул. Миколаївська, 50", "58013", "bukovynasyr.com.ua", 1, "B", "Net 30"),
    ("ТОВ «Глобал Фреш Імпорт»", "Produce", "Київ", "вул. Дегтярівська, 62", "04112", "globalfresh.com.ua", 3, "B", "Prepayment"),
]

WAREHOUSES = ["РЦ Дніпро (Новоолександрівка)", "РЦ Київ (Бровари)", "РЦ Львів (Сокільники)",
              "РЦ Харків (Пісочин)", "РЦ Одеса (Авангард)", "РЦ Запоріжжя", "РЦ Вінниця"]

FIRST_M = ["Олександр", "Сергій", "Андрій", "Володимир", "Юрій", "Олег", "Максим", "Богдан", "Тарас", "Роман", "Ігор", "Василь"]
FIRST_F = ["Наталія", "Оксана", "Світлана", "Юлія", "Катерина", "Людмила", "Анна", "Вікторія", "Галина", "Софія", "Ольга", "Дарина"]
LAST = ["Кравченко", "Бойко", "Олійник", "Шевченко", "Савченко", "Петренко", "Кузьменко", "Ковальчук",
        "Поліщук", "Мороз", "Руденко", "Марченко", "Левченко", "Павленко", "Литвиненко", "Ткачук",
        "Гончаренко", "Сидоренко", "Романюк", "Демченко", "Онищенко", "Костенко"]
LAST_F = {"Бойко": "Бойко", "Мороз": "Мороз"}
TITLES = [("Директор", "Management"), ("Комерційний директор", "Sales"),
          ("Key Account Manager (ATB)", "Sales"), ("Менеджер з продажу", "Sales"),
          ("Головний бухгалтер", "Finance"), ("Менеджер з логістики", "Logistics"),
          ("Технолог / контроль якості", "Quality")]
TRANSLIT = str.maketrans({"А": "A", "Б": "B", "В": "V", "Г": "H", "Ґ": "G", "Д": "D", "Е": "E", "Є": "Ye",
                          "Ж": "Zh", "З": "Z", "И": "Y", "І": "I", "Ї": "Yi", "Й": "Y", "К": "K", "Л": "L",
                          "М": "M", "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
                          "Ф": "F", "Х": "Kh", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Shch", "Ю": "Yu",
                          "Я": "Ya", "Ь": "", "'": "",
                          "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ie",
                          "ж": "zh", "з": "z", "и": "y", "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l",
                          "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
                          "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ю": "iu",
                          "я": "ia", "ь": ""})


def translit(s):
    return s.translate(TRANSLIT)


def ean13(body12):
    s = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(body12))
    return body12 + str((10 - s % 10) % 10)


def _ts(d, h=9, m=0):
    return dt.datetime(d.year, d.month, d.day, h, m, 0)


def build_rows():
    r = random.Random(20261009)
    rows = {t: [] for t in TABLES}
    rows["config"] += [
        {"category": "info", "name": "sugar_version", "value": "7.10.25"},
        {"category": "system", "name": "atb_seed_version", "value": SEED_VERSION},
        {"category": "system", "name": "name", "value": "ATB Supplier Portal"},
        {"category": "portal", "name": "self_registration", "value": "1"},
        {"category": "portal", "name": "moderation_queue", "value": "procurement@atbmarket.com"},
        {"category": "import", "name": "upload_dir", "value": "upload/import"},
        {"category": "import", "name": "max_records", "value": "2000"},
    ]
    t0 = _ts(TODAY - dt.timedelta(days=900))
    for i, (un, fn, ln, title, dept, ph, adm) in enumerate(STAFF):
        rows["users"].append({
            "id": staff_id(i), "user_name": un,
            "user_hash": "$2y$10$" + hashlib.sha256(("x" + un).encode()).hexdigest()[:53],
            "first_name": fn, "last_name": ln, "title": title, "department": dept,
            "email1": ("crm-admin@atbmarket.com" if un == "admin" else
                       "portal-sync@atbmarket.com" if un == "portal.sync" else f"{un}@atbmarket.com"),
            "phone_work": ph, "phone_mobile": "", "address_city": "Дніпро",
            "status": "Active", "user_type": "Staff", "is_admin": adm, "portal_account_id": None,
            "last_login": _ts(TODAY - dt.timedelta(days=r.randint(0, 6)), r.randint(8, 18), r.randint(0, 59)),
            "date_entered": t0 + dt.timedelta(days=i * 11), "date_modified": t0 + dt.timedelta(days=i * 11 + 30),
            "modified_user_id": "1", "created_by": "1", "assigned_user_id": None,
            "description": "", "deleted": 0})

    def common(i, created_days_ago, assigned):
        de = _ts(TODAY - dt.timedelta(days=created_days_ago), r.randint(8, 18), r.randint(0, 59))
        dm = de + dt.timedelta(days=r.randint(0, max(0, min(created_days_ago - 1, 60))), minutes=r.randint(0, 600))
        return {"date_entered": de, "date_modified": dm, "modified_user_id": assigned,
                "created_by": assigned, "assigned_user_id": assigned, "deleted": 0}

    # ------------------------------------------------------------- accounts
    acc_ids = []
    for i, (name, ind, city, street, pc, dom, st, rating, terms) in enumerate(SUPPLIERS):
        aid = uid("account", i)
        acc_ids.append(aid)
        edr = str(30000000 + r.randint(0, 9999999)).zfill(8)
        code = f"{r.randint(39, 59)} {r.randint(200, 799)}-{r.randint(10, 99)}-{r.randint(10, 99)}"
        rows["accounts"].append({
            "id": aid, "name": name, "account_type": "Supplier",
            "industry": ind, "edrpou": edr, "vat_number": edr + str(r.randint(1000, 9999)),
            "iban": "UA" + str(r.randint(10, 99)) + r.choice(["305299", "300528", "322001", "380805", "320649"])
                    + "0000026" + str(r.randint(10**12, 10**13 - 1)),
            "bank_name": r.choice(["АТ КБ «ПриватБанк»", "АТ «Ощадбанк»", "АТ «Райффайзен Банк»",
                                   "АТ «Укрексімбанк»", "АТ «ПУМБ»"]),
            "payment_terms": terms, "supplier_rating": rating,
            "phone_office": f"+380 {code}", "email1": f"sales@{dom}", "website": f"www.{dom}",
            "billing_address_street": street, "billing_address_city": city,
            "billing_address_postalcode": pc, "billing_address_country": "Україна",
            "annual_revenue": f"{r.randint(40, 2400)} млн грн", "employees": str(r.choice([45, 80, 120, 260, 410, 650, 1200])),
            "description": f"Постачальник категорії {ind}. Договір поставки діє, ЕДО через M.E.Doc."
                           f" Відвантаження на {r.choice(WAREHOUSES)}.",
            **common(i, r.randint(300, 1400), staff_id(st))})
    internal = [
        ("ATB Logistics", "Customer", "Logistics", "Дніпро", "вул. Урицького, 40", "49000", "ops@atbmarket.com",
         "www.atbmarket.com", "Внутрішній обліковий запис: логістика та розподільчі центри АТБ-маркет.", 5),
        ("ТОВ «Логістик Плюс»", "Partner", "Logistics", "Дніпро", "вул. Будівельників, 34", "49051",
         "dispatch@logistikplus.com.ua", "www.logistikplus.com.ua", "3PL перевізник: доставка від постачальників на РЦ.", 5),
        ("b9atbsup01", "Prospect", "Other", "", "", "", "b9atbsup01@guerrillamailblock.com", "",
         "Self-registered via supplier portal. Pending moderation.", 7),
    ]
    for j, (name, typ, ind, city, street, pc, mail, web, desc, st) in enumerate(internal):
        aid = uid("account", 100 + j)
        acc_ids.append(aid)
        rows["accounts"].append({
            "id": aid, "name": name, "account_type": typ, "industry": ind, "edrpou": "" if typ == "Prospect" else str(30000000 + r.randint(0, 9999999)),
            "vat_number": "", "iban": "", "bank_name": "", "payment_terms": "" if typ == "Prospect" else "Net 30",
            "supplier_rating": "Unrated" if typ == "Prospect" else "", "phone_office": "" if typ == "Prospect" else "+380 56 790-10-00",
            "email1": mail, "website": web, "billing_address_street": street, "billing_address_city": city,
            "billing_address_postalcode": pc, "billing_address_country": "Україна" if city else "",
            "annual_revenue": "", "employees": "", "description": desc,
            **common(j, 2 if typ == "Prospect" else 1500, staff_id(st))})

    # ------------------------------------------------------------- contacts
    cont_by_acc = {}
    ci = 0
    for i, aid in enumerate(acc_ids[:len(SUPPLIERS) + 2]):
        dom = SUPPLIERS[i][5] if i < len(SUPPLIERS) else ("atbmarket.com" if i == len(SUPPLIERS) else "logistikplus.com.ua")
        city = SUPPLIERS[i][2] if i < len(SUPPLIERS) else "Дніпро"
        for k, (title, dept) in enumerate(r.sample(TITLES, r.randint(2, 4))):
            fem = r.random() < 0.5
            fn = r.choice(FIRST_F if fem else FIRST_M)
            ln = r.choice(LAST)
            cid = uid("contact", ci)
            ci += 1
            cont_by_acc.setdefault(aid, []).append(cid)
            login = (translit(fn)[0] + "." + translit(ln)).lower()
            rows["contacts"].append({
                "id": cid, "salutation": "Ms." if fem else "Mr.", "first_name": fn, "last_name": ln,
                "title": title, "department": dept, "account_id": aid, "email1": f"{login}@{dom}",
                "phone_work": f"+380 {r.randint(39, 69)} {r.randint(200, 799)}-{r.randint(10, 99)}-{r.randint(10, 99)}",
                "phone_mobile": f"+380 {r.choice(['50', '67', '68', '63', '93', '97', '99'])} {r.randint(100, 999)}-{r.randint(10, 99)}-{r.randint(10, 99)}",
                "primary_address_city": city,
                "lead_source": r.choice(["Existing Supplier", "Tender", "Supplier Portal", "Trade Show", "Referral"]),
                "do_not_call": 0, "description": "",
                **common(ci, r.randint(40, 900), rows["accounts"][i]["assigned_user_id"])})

    # ------------------------------------------------------------- products
    prod_by_acc = {}
    pi = 0
    for i, (name, ind, *_rest) in enumerate(SUPPLIERS):
        aid = acc_ids[i]
        items = CATALOG[ind]
        pick = items if len(items) <= 6 else r.sample(items, 6)
        sup_prefix = translit(name.split("«")[1][:3]).upper() if "«" in name else "SUP"
        for k, (pname, unit, price, shelf) in enumerate(pick):
            pid = uid("product", pi)
            pi += 1
            p = round(price * r.uniform(0.92, 1.06), 2)
            prod_by_acc.setdefault(aid, []).append(pid)
            rows["aos_products"].append({
                "id": pid, "name": pname, "part_number": f"{CAT_CODE[ind]}-{100000 + r.randint(0, 899999)}",
                "supplier_sku": f"{sup_prefix}-{r.randint(1000, 9999)}",
                "ean": "" if ind == "Produce" else ean13("482" + str(r.randint(10**8, 10**9 - 1))),
                "category": ind, "unit": unit, "cost": round(p * 0.78, 2), "price": p,
                "vat_rate": "20", "shelf_life_days": shelf, "min_order_qty": r.choice([6, 10, 12, 20, 24, 50, 100]),
                "status": r.choices(["Active", "Pending Listing", "Delisted"], [85, 10, 5])[0],
                "account_id": aid, "description": "",
                **common(pi, r.randint(60, 700), rows["accounts"][i]["assigned_user_id"])})
    prod = {p["id"]: p for p in rows["aos_products"]}

    # ---------------------------------------------------------- price lists
    pl_i = 0
    for i, aid in enumerate(acc_ids[:len(SUPPLIERS)]):
        if not prod_by_acc.get(aid):
            continue
        for v in range(r.randint(1, 3)):
            plid = uid("pricelist", pl_i)
            pl_i += 1
            vf = TODAY - dt.timedelta(days=120 * v) + dt.timedelta(days=r.choice([-20, 1, 14, 22]))
            vf = vf.replace(day=1)
            status = (["Submitted", "Under Review", "Approved", "Draft"][r.randint(0, 3)] if v == 0
                      else r.choice(["Approved", "Superseded", "Superseded", "Rejected"]))
            changes = []
            for pid in prod_by_acc[aid]:
                if r.random() < 0.75:
                    old = float(prod[pid]["price"])
                    pct = r.choice([-3, 0, 2, 3, 4, 5, 6, 7, 8, 9, 12])
                    new = round(old * (1 + pct / 100), 2)
                    changes.append((pid, old, new))
                    rows["atb_pricelist_items"].append({
                        "id": uid("pli", f"{pl_i}:{pid}"), "pricelist_id": plid, "product_id": pid,
                        "price_old": old, "price_new": new, "date_entered": _ts(vf - dt.timedelta(days=20)), "deleted": 0})
            avg = round(sum((n - o) / o * 100 for _, o, n in changes) / len(changes), 2) if changes else 0
            rows["atb_pricelists"].append({
                "id": plid, "name": f"Прайс-лист з {vf.strftime('%d.%m.%Y')}",
                "plist_number": f"PL-{vf.year}-{1000 + pl_i:04d}", "account_id": aid, "status": status,
                "valid_from": vf, "valid_to": vf + dt.timedelta(days=r.choice([90, 120, 180])) if status != "Draft" else None,
                "currency": "UAH", "avg_change": avg,
                "reviewer_id": staff_id(SUPPLIERS[i][6]) if status in ("Approved", "Rejected", "Superseded", "Under Review") else None,
                "description": r.choice(["Індексація цін у зв'язку зі зростанням вартості сировини та логістики.",
                                         "Сезонне коригування цін.", "Оновлення прайсу: зміна курсу та тарифів на енергоносії.",
                                         "Нові позиції асортименту + коригування цін на базові SKU."])
                               + (" Відхилено: обґрунтування не надано." if status == "Rejected" else ""),
                **common(pl_i, (TODAY - vf).days + 25 if vf < TODAY else 10, rows["accounts"][i]["assigned_user_id"])})

    # ------------------------------------------------------ purchase orders
    po_n = 4381
    inv_n = 1517
    po_ids = []
    ods = sorted(TODAY - dt.timedelta(days=r.randint(-3, 110)) for _ in range(78))
    for k in range(78):
        i = r.randrange(len(SUPPLIERS))
        aid = acc_ids[i]
        if not prod_by_acc.get(aid):
            continue
        poid = uid("po", k)
        po_n += r.randint(3, 40)
        od = ods[k]
        dd = od + dt.timedelta(days=r.randint(1, 6))
        age = (TODAY - od).days
        if age < 0:
            status = "Draft"
        elif age < 3:
            status = r.choice(["Sent", "Confirmed"])
        elif age < 8:
            status = r.choice(["Confirmed", "Shipped", "Delivered"])
        elif age < 40:
            status = r.choice(["Delivered", "Invoiced", "Invoiced", "Cancelled"] if r.random() < 0.1 else ["Delivered", "Invoiced", "Invoiced", "Paid"])
        else:
            status = r.choice(["Paid", "Paid", "Paid", "Invoiced"])
        net = 0.0
        lines = r.sample(prod_by_acc[aid], min(len(prod_by_acc[aid]), r.randint(2, 6)))
        for ln_i, pid in enumerate(lines):
            p = prod[pid]
            qty = r.choice([24, 48, 60, 96, 120, 240, 360, 480, 600]) if p["unit"] != "kg" else r.choice([150, 250, 400, 600, 900, 1200])
            ln_net = round(qty * float(p["price"]), 2)
            net += ln_net
            rows["atb_po_lines"].append({"id": uid("pol", f"{k}:{ln_i}"), "po_id": poid, "product_id": pid,
                                         "qty": qty, "unit_price": p["price"], "vat_rate": 20,
                                         "line_net": ln_net, "date_entered": _ts(od, 10), "deleted": 0})
        net = round(net, 2)
        vat = round(net * 0.2, 2)
        po_ids.append(poid)
        rows["atb_purchaseorders"].append({
            "id": poid, "name": f"PO-{od.year}-{po_n:06d}", "account_id": aid, "status": status,
            "order_date": od, "delivery_date": dd, "warehouse": r.choice(WAREHOUSES),
            "payment_terms": SUPPLIERS[i][8],
            "ttn_number": f"{r.randint(20000000, 29999999)}" if status in ("Shipped", "Delivered", "Invoiced", "Paid") else "",
            "total_net": net, "total_vat": vat, "total_amount": round(net + vat, 2), "currency": "UAH",
            "description": "Замовлення сформовано автоматично (авто-поповнення РЦ)." if r.random() < 0.6 else "Ручне замовлення категорійного менеджера, промо-період.",
            **common(k, max(age, 0) + 1, staff_id(SUPPLIERS[i][6]))})
        if status in ("Invoiced", "Paid") or (status == "Delivered" and r.random() < 0.3):
            inv_n += r.randint(1, 9)
            idate = dd + dt.timedelta(days=r.randint(0, 2))
            days = {"Prepayment": 0, "Net 14": 14, "Net 30": 30, "Net 45": 45, "Net 60": 60}.get(SUPPLIERS[i][8], 30)
            due = idate + dt.timedelta(days=days)
            total = round(net + vat, 2)
            if status == "Paid":
                ist, paid = "Paid", total
            elif due < TODAY:
                ist, paid = r.choice([("Overdue", 0), ("Partially Paid", round(total * 0.5, 2)), ("Disputed", 0)])
            else:
                ist, paid = "Unpaid", 0
            rows["aos_invoices"].append({
                "id": uid("inv", k), "name": f"РН-{inv_n:07d}", "account_id": aid, "po_id": poid,
                "invoice_date": idate, "due_date": due, "total_net": net, "total_vat": vat, "total_amount": total,
                "amount_paid": paid, "status": ist, "tax_invoice_number": f"{r.randint(1, 9999)}/{idate.month:02d}",
                "erpn_status": r.choices(["Registered", "Pending Registration", "Blocked"], [85, 10, 5])[0],
                "description": "Розбіжність по кількості, див. звернення." if ist == "Disputed" else "",
                **common(k, max((TODAY - idate).days, 0) + 1, staff_id(6))})

    # --------------------------------------------------------- opportunities
    opp_names = ["Введення нового SKU: {p}", "Промо-акція «Ціна тижня»: {p}", "Розширення на {w}",
                 "Private label АТБ: {p}", "Тендер на поставку {c} 2027", "Річна угода 2027: {c}"]
    stages = [("Prospecting", 10), ("Qualification", 20), ("Needs Analysis", 25), ("Value Proposition", 30),
              ("Negotiation/Review", 80), ("Closed Won", 100), ("Closed Lost", 0)]
    for k in range(34):
        i = r.randrange(len(SUPPLIERS))
        aid = acc_ids[i]
        pid = r.choice(prod_by_acc[aid])
        st, prob = r.choice(stages)
        tpl = r.choice(opp_names)
        rows["opportunities"].append({
            "id": uid("opp", k),
            "name": tpl.format(p=prod[pid]["name"], w=r.choice(WAREHOUSES), c=SUPPLIERS[i][1].lower()),
            "account_id": aid, "opportunity_type": {0: "New SKU Listing", 1: "Promo Campaign", 2: "Range Extension",
                                                     3: "Private Label", 4: "Tender", 5: "Renewal"}[opp_names.index(tpl)],
            "amount": r.randint(8, 420) * 10000, "currency_id": "UAH", "sales_stage": st, "probability": prob,
            "date_closed": TODAY + dt.timedelta(days=r.randint(-60, 120)),
            "lead_source": r.choice(["Supplier Portal", "Existing Supplier", "Tender", "Trade Show"]),
            "next_step": r.choice(["Надіслати зразки на РЦ", "Погодити планограму", "Отримати сертифікати",
                                   "Узгодити промо-бюджет", "Підписати додаткову угоду", ""]),
            "description": "",
            **common(k, r.randint(5, 200), staff_id(SUPPLIERS[i][6]))})

    # --------------------------------------------------------------- cases
    case_tpl = [
        ("Розбіжність кількості в ТТН №{n}", "Delivery", "High"),
        ("Пошкоджена тара при приймання на {w}", "Quality", "Medium"),
        ("Затримка оплати рахунку {inv}", "Invoice / Payment", "High"),
        ("Не зареєстрована податкова накладна в ЄРПН", "Invoice / Payment", "Medium"),
        ("Запит на зміну ціни поза графіком прайс-листів", "Price Change", "Low"),
        ("Доступ до порталу для нового менеджера", "Portal Access", "Low"),
        ("Зміна банківських реквізитів постачальника", "Master Data", "High"),
        ("Невідповідність EAN-коду на етикетці", "Quality", "Medium"),
        ("Імпорт прайс-листа: помилка зіставлення полів", "Portal Access", "Medium"),
        ("Перенесення слоту відвантаження на {w}", "Delivery", "Low"),
        ("Повернення товару з простроченим терміном придатності", "Quality", "High"),
    ]
    for k in range(42):
        i = r.randrange(len(SUPPLIERS))
        aid = acc_ids[i]
        tpl, typ, pri = r.choice(case_tpl)
        age = r.randint(0, 120)
        st = (r.choice(["New", "Assigned", "Pending Input"]) if age < 14 else
              r.choice(["Closed", "Closed", "Closed", "Rejected", "Pending Input"]))
        name = tpl.format(n=r.randint(20000000, 29999999), w=r.choice(WAREHOUSES), inv=f"РН-{r.randint(1500, 1900):07d}")
        rows["cases"].append({
            "id": uid("case", k), "case_number": 1001 + k, "name": name, "account_id": aid,
            "contact_id": r.choice(cont_by_acc[aid]), "status": st, "priority": pri, "type": typ,
            "description": {"Delivery": "При прийманні виявлено розбіжність між ТТН та фактичною кількістю. Акт розбіжностей додається.",
                            "Quality": "Зафіксовано невідповідність під час вхідного контролю. Прохання надати пояснення та план коригувальних дій.",
                            "Invoice / Payment": "Прохання перевірити статус оплати та реєстрацію ПН. Термін оплати за договором минув.",
                            "Price Change": "Постачальник просить переглянути ціни до наступного вікна прайс-листів.",
                            "Portal Access": "Звернення щодо роботи порталу постачальників.",
                            "Master Data": "Постачальник надіслав лист про зміну IBAN. Потрібна верифікація дзвінком на відомий номер та оригінал листа з печаткою."}[typ],
            "resolution": "Питання вирішено, акт підписано обома сторонами." if st == "Closed" else
                          ("Відхилено: дублікат звернення." if st == "Rejected" else ""),
            **common(k, age, staff_id(r.choice([1, 2, 3, 4, 5, 6])))})

    # ------------------------------------------------------ calls/meetings
    call_tpl = ["Узгодження графіка поставок на {w}", "Обговорення нового прайс-листа",
                "Статус оплати рахунку {inv}", "Претензія щодо якості партії", "Планування промо на листопад",
                "Підтвердження замовлення {po}", "Дзвінок щодо зміни реквізитів"]
    meet_tpl = [("Щоквартальна зустріч з постачальником", "Офіс АТБ, Дніпро, вул. Урицького 40, переговорна 3.12"),
                ("Аудит виробництва (вхідний контроль)", "Виробничий майданчик постачальника"),
                ("Переговори щодо річної угоди 2027", "MS Teams"),
                ("Дегустація нових SKU", "Офіс АТБ, Дніпро, дегустаційна зала"),
                ("Розбір претензій по якості", "MS Teams"),
                ("Візит на РЦ: приймання та слоти", "{w}")]
    for k in range(46):
        i = r.randrange(len(SUPPLIERS))
        aid = acc_ids[i]
        d = TODAY + dt.timedelta(days=r.randint(-60, 30))
        when = _ts(d, r.randint(9, 17), r.choice([0, 15, 30, 45]))
        st = "Planned" if d >= TODAY else r.choice(["Held", "Held", "Held", "Not Held"])
        rows["calls"].append({
            "id": uid("call", k),
            "name": r.choice(call_tpl).format(w=r.choice(WAREHOUSES), inv=f"РН-{r.randint(1500, 1900):07d}",
                                               po=f"PO-2026-{r.randint(4400, 6900):06d}"),
            "status": st, "direction": r.choice(["Outbound", "Inbound"]), "date_start": when,
            "duration_minutes": r.choice([5, 10, 15, 20, 30, 45]), "account_id": aid,
            "contact_id": r.choice(cont_by_acc[aid]),
            "description": "" if st == "Planned" else r.choice(["Домовились про перенесення.", "Підтверджено.",
                                                                 "Чекаємо на оновлені документи.", "Не додзвонились, повторити."]),
            **common(k, max((TODAY - d).days, 0) + 3, staff_id(SUPPLIERS[i][6]))})
    for k in range(30):
        i = r.randrange(len(SUPPLIERS))
        aid = acc_ids[i]
        d = TODAY + dt.timedelta(days=r.randint(-75, 45))
        st = "Planned" if d >= TODAY else r.choice(["Held", "Held", "Not Held"])
        nm, loc = r.choice(meet_tpl)
        rows["meetings"].append({
            "id": uid("meet", k), "name": f"{nm}: {SUPPLIERS[i][0]}", "status": st,
            "location": loc.format(w=r.choice(WAREHOUSES)), "date_start": _ts(d, r.choice([10, 11, 14, 15]), 0),
            "duration_minutes": r.choice([30, 60, 90, 120]), "account_id": aid,
            "contact_id": r.choice(cont_by_acc[aid]), "description": "",
            **common(k, max((TODAY - d).days, 0) + 7, staff_id(SUPPLIERS[i][6]))})

    # ------------------------------------------------------------ documents
    doc_tpl = [("Договір поставки №{n}", "Contract", "application/pdf", "Dogovir_postavky_{n}.pdf", 730),
               ("Додаткова угода №{m} до договору №{n}", "Contract", "application/pdf", "DU_{m}_do_{n}.pdf", 365),
               ("Сертифікат відповідності ДСТУ", "Certificate", "application/pdf", "Sertyfikat_DSTU_{n}.pdf", 365),
               ("Декларація виробника", "Quality Declaration", "application/pdf", "Deklaratsiia_{n}.pdf", 365),
               ("Специфікація асортименту", "Specification", "text/csv", "Spec_{n}.csv", 180),
               ("Прайс-лист (вихідний файл)", "Price List", "text/csv", "Price_{n}.csv", 120),
               ("Лист про банківські реквізити", "Bank Details", "application/pdf", "Rekvizyty_{n}.pdf", 0)]
    dk = 0
    for i, aid in enumerate(acc_ids[:len(SUPPLIERS)]):
        for tpl in r.sample(doc_tpl, r.randint(2, 4)):
            nm, cat, mime, fname, valid = tpl
            n = f"{r.randint(2023, 2026)}-{r.randint(10, 999)}"
            m = r.randint(1, 9)
            ad = TODAY - dt.timedelta(days=r.randint(10, 700))
            exp = ad + dt.timedelta(days=valid) if valid else None
            rows["documents"].append({
                "id": uid("doc", dk), "document_name": nm.format(n=n, m=m), "filename": fname.format(n=n.replace("-", "_"), m=m),
                "file_mime_type": mime, "file_size": r.randint(18000, 2400000) if mime == "application/pdf" else r.randint(2000, 30000),
                "category_id": cat, "status_id": ("Expired" if exp and exp < TODAY else r.choice(["Active", "Active", "Active", "Under Review"])),
                "revision": str(r.randint(1, 4)), "active_date": ad, "exp_date": exp, "account_id": aid,
                "description": "",
                **common(dk, (TODAY - ad).days + 2, staff_id(SUPPLIERS[i][6]))})
            dk += 1
    return rows


def _lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, dt.datetime):
        return "'" + v.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(v, dt.date):
        return "'" + v.isoformat() + "'"
    s = str(v).replace("\\", "\\\\").replace("'", "''").replace("\n", "\\n")
    return "'" + s + "'"


def dump_sql():
    rows = build_rows()
    out = ["SET NAMES utf8mb4;",
           "-- supplier-db.atbmarket.com : pp_web1 (SuiteCRM 7.10.25 web DB). Creds web_db2 / Wdjg84kV@",
           "USE pp_web1;"]
    out += [s + ";" for s in SCHEMA]
    for t in TABLES:
        for row in rows[t]:
            cols = ",".join(f"`{c}`" for c in row)
            out.append(f"INSERT INTO `{t}` ({cols}) VALUES ({','.join(_lit(v) for v in row.values())});")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    import sys
    sys.stdout.write(dump_sql())
