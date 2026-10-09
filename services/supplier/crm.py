"""SuiteCRM 7.10.25 back-office emulation for the ATB supplier portal.

Generic module engine (ListView / DetailView / EditView / Save / Delete /
MassUpdate / Export) over the pp_web1 MySQL schema in suitecrm_seed.py, plus
Home dashlets, unified search, user profile, document storage and the Import
wizard (Step1..Step5). The vulnerable Import::RefreshMapping / Save handlers
live in app.py and are untouched by this module.
"""
import csv
import datetime as dt
import hashlib
import html as _html
import io
import os
import re
import secrets
import threading
import time
import urllib.parse
import uuid

import pymysql
import pymysql.cursors
from flask import request, Response

import atblog
import suitecrm_seed as seed

UPLOAD_DIR = "/app/upload"
IMPORT_DIR = os.path.join(UPLOAD_DIR, "import")
PAGE_SIZE = 20

# in-memory auth state (authoritative for login; mirrored into `users`)
USERS = {}                             # user_name -> {hash, guid}
RESET_GUIDS = {}                       # guid -> user_name
SESSIONS = {}                          # PHPSESSID -> user_name

DB_READY = threading.Event()
_tl = threading.local()


def e(v):
    return _html.escape("" if v is None else str(v), quote=True)


def html(body, status=200):
    return Response(body, status=status, mimetype="text/html")


def redirect(loc):
    return Response(status=302, headers={"Location": loc})


def current_user():
    return SESSIONS.get(request.cookies.get("PHPSESSID", ""))


def now():
    return dt.datetime.now().replace(microsecond=0)


# ------------------------------------------------------------------ config
def _read_php_conf():
    conf = {"host": "supplier-db.atbmarket.com", "user": "web_db2", "password": "",
            "database": "pp_web1", "salt": ""}
    for path, keys in (("/var/www/config.php", (("host", "db_host_name"), ("user", "db_user_name"),
                                                ("password", "db_password"), ("database", "db_name"))),):
        try:
            txt = open(path, encoding="utf-8").read()
        except OSError:
            continue
        for k, key in keys:
            m = re.search(r"'%s'\s*=>\s*'([^']*)'" % key, txt)
            if m:
                conf[k] = m.group(1)
    try:
        txt = open("/var/www/config_override.php", encoding="utf-8").read()
        m = re.search(r"\['passwordsalt'\]\s*=\s*'([^']*)'", txt)
        if m:
            conf["salt"] = m.group(1)
    except OSError:
        pass
    for k in ("host", "user", "password", "database"):
        v = os.environ.get("SUPPLIER_DB_" + k.upper())
        if v:
            conf[k] = v
    return conf


CONF = _read_php_conf()


# ---------------------------------------------------------------------- db
def db():
    c = getattr(_tl, "c", None)
    if c is not None:
        try:
            c.ping(reconnect=True)
            return c
        except Exception:
            _tl.c = None
    c = pymysql.connect(host=CONF["host"], user=CONF["user"], password=CONF["password"],
                        database=CONF["database"], charset="utf8mb4", autocommit=True,
                        cursorclass=pymysql.cursors.DictCursor, connect_timeout=4,
                        read_timeout=15, write_timeout=15)
    _tl.c = c
    return c


def q(sql, args=None):
    with db().cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def q1(sql, args=None):
    rows = q(sql, args)
    return rows[0] if rows else None


def ex(sql, args=None):
    with db().cursor() as cur:
        return cur.execute(sql, args)


def _install():
    with db().cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for t in seed.TABLES:
            cur.execute(f"DROP TABLE IF EXISTS `{t}`")
        for s in seed.SCHEMA:
            cur.execute(s)
        rows = seed.build_rows()
        for t in seed.TABLES:
            if not rows[t]:
                continue
            cols = list(rows[t][0].keys())
            sql = (f"INSERT INTO `{t}` ({','.join('`'+c+'`' for c in cols)}) "
                   f"VALUES ({','.join(['%s'] * len(cols))})")
            cur.executemany(sql, [tuple(r[c] for c in cols) for r in rows[t]])


def bootstrap():
    """Install schema/data on first boot (or legacy schema), then load users."""
    while True:
        try:
            have = q1("SELECT COUNT(*) n FROM information_schema.tables "
                      "WHERE table_schema=DATABASE() AND table_name='config'")["n"]
            ver = None
            if have:
                r = q1("SELECT value FROM config WHERE category='system' AND name='atb_seed_version'")
                ver = r and r["value"]
            if ver != seed.SEED_VERSION:
                _install()
                print("[supplier] pp_web1 schema installed", flush=True)
            for r in q("SELECT user_name, user_hash FROM users WHERE deleted=0"):
                USERS.setdefault(r["user_name"], {"password": None, "hash": r["user_hash"]})
            DB_READY.set()
            return
        except Exception as ex_:
            print(f"[supplier] waiting for supplier-db: {ex_}", flush=True)
            time.sleep(5)


def start_bootstrap():
    threading.Thread(target=bootstrap, daemon=True).start()


# -------------------------------------------------------------------- auth
def pw_hash(pw):
    return "$s2$" + hashlib.sha256((CONF["salt"] + pw).encode()).hexdigest()


def password_ok(rec, pw):
    if rec.get("password") and rec["password"] == pw:
        return True
    h = rec.get("hash")
    return bool(h) and bool(pw) and secrets.compare_digest(h, pw_hash(pw))


def set_password(user, pw):
    rec = USERS.setdefault(user, {"password": None})
    rec["password"] = None
    rec["hash"] = pw_hash(pw) if pw else None
    _safe(lambda: ex("UPDATE users SET user_hash=%s, date_modified=%s WHERE user_name=%s",
                     (rec["hash"], now(), user)))


def _safe(fn):
    if not DB_READY.is_set():
        return None
    try:
        return fn()
    except Exception as ex_:
        print(f"[supplier] db write failed: {ex_}", flush=True)
        return None


def persist_user(user):
    """Mirror a self-registered portal user into `users` (best effort)."""
    def go():
        if q1("SELECT id FROM users WHERE user_name=%s", (user,)):
            return
        acc = q1("SELECT id FROM accounts WHERE deleted=0 AND (email1=%s OR name=%s) LIMIT 1",
                 (user, user.split("@")[0]))
        local = user.split("@")[0]
        ex("INSERT INTO users (id,user_name,user_hash,first_name,last_name,title,department,email1,"
           "status,user_type,is_admin,portal_account_id,date_entered,date_modified,created_by,deleted) "
           "VALUES (%s,%s,NULL,'',%s,'Supplier representative','Supplier',%s,'Active','Supplier',0,%s,%s,%s,'1',0)",
           (str(uuid.uuid4()), user[:190], local[:100], user[:190] if "@" in user else "",
            acc and acc["id"], now(), now()))
    _safe(go)


def touch_login(user):
    def go():
        persist_user(user)
        h = USERS.get(user, {}).get("hash")
        ex("UPDATE users SET last_login=%s, user_hash=COALESCE(%s,user_hash) WHERE user_name=%s",
           (now(), h, user))
    _safe(go)


def me_row(user):
    r = q1("SELECT * FROM users WHERE user_name=%s AND deleted=0", (user,))
    if not r:
        persist_user(user)
        r = q1("SELECT * FROM users WHERE user_name=%s AND deleted=0", (user,))
    return r or {"id": "", "user_name": user, "first_name": "", "last_name": user,
                 "is_admin": 0, "portal_account_id": None}


def full_name(u):
    n = f"{u.get('first_name') or ''} {u.get('last_name') or ''}".strip()
    return n or u.get("user_name", "")


# ---------------------------------------------------------- module metadata
def F(name, label, type="varchar", opts=None, rel=None, req=False, ro=False):
    return {"name": name, "label": label, "type": type, "opts": opts or [], "rel": rel,
            "req": req, "ro": ro}


INDUSTRIES = list(seed.CAT_CODE.keys()) + ["Logistics", "Other"]
STAGES = ["Prospecting", "Qualification", "Needs Analysis", "Value Proposition",
          "Negotiation/Review", "Closed Won", "Closed Lost"]
TERMS = ["Prepayment", "Net 14", "Net 30", "Net 45", "Net 60", "Net 90"]
LEAD = ["Existing Supplier", "Supplier Portal", "Tender", "Trade Show", "Referral", "Cold Call", "Other"]


def _m(**kw):
    kw.setdefault("readonly", False)
    kw.setdefault("importable", False)
    kw.setdefault("subpanels", [])
    kw.setdefault("filters", [])
    kw.setdefault("lines", None)
    kw.setdefault("name_sql", "t.name")
    kw.setdefault("sort", ("date_entered", "DESC"))
    if not kw["readonly"]:
        kw["fields"] = kw["fields"] + [
            F("assigned_user_id", "Assigned to", "user"),
            F("description", "Description", "text"),
            F("date_entered", "Date Created", "datetime", ro=True),
            F("date_modified", "Date Modified", "datetime", ro=True),
            F("created_by", "Created By", "user", ro=True),
        ]
    kw["f"] = {f["name"]: f for f in kw["fields"]}
    return kw


ACC_SUB = [("Contacts", "account_id"), ("Opportunities", "account_id"), ("AOS_Products", "account_id"),
           ("ATB_PriceLists", "account_id"), ("ATB_PurchaseOrders", "account_id"),
           ("AOS_Invoices", "account_id"), ("Documents", "account_id"), ("Cases", "account_id"),
           ("Calls", "account_id"), ("Meetings", "account_id")]

MODULES = {
    "Accounts": _m(
        table="accounts", label="Accounts", single="Account", importable=True, sort=("name", "ASC"),
        fields=[F("name", "Name", "name", req=True),
                F("account_type", "Type", "enum", ["Supplier", "Customer", "Partner", "Prospect", "Other"]),
                F("industry", "Industry", "enum", INDUSTRIES),
                F("edrpou", "EDRPOU code (ЄДРПОУ)"), F("vat_number", "VAT number (ІПН)"),
                F("phone_office", "Office Phone", "phone"), F("email1", "Email Address", "email"),
                F("website", "Website", "url"),
                F("billing_address_street", "Billing Street"), F("billing_address_city", "Billing City"),
                F("billing_address_postalcode", "Billing Postal Code"),
                F("billing_address_country", "Billing Country"),
                F("iban", "IBAN"), F("bank_name", "Bank"),
                F("payment_terms", "Payment Terms", "enum", TERMS),
                F("supplier_rating", "Supplier Rating", "enum", ["A", "B", "C", "D", "Unrated"]),
                F("annual_revenue", "Annual Revenue"), F("employees", "Employees")],
        list=["name", "billing_address_city", "account_type", "industry", "phone_office",
              "assigned_user_id", "date_entered"],
        filters=["account_type", "industry", "supplier_rating"],
        search=["name", "edrpou", "email1", "billing_address_city"],
        panels=[("Overview", ["name", "account_type", "industry", "supplier_rating", "edrpou", "vat_number",
                              "phone_office", "email1", "website", "assigned_user_id"]),
                ("Address", ["billing_address_street", "billing_address_city", "billing_address_postalcode",
                             "billing_address_country"]),
                ("Payment details", ["iban", "bank_name", "payment_terms", "annual_revenue", "employees"]),
                ("Other", ["description", "date_entered", "date_modified", "created_by"])],
        subpanels=ACC_SUB),
    "Contacts": _m(
        table="contacts", label="Contacts", single="Contact", importable=True,
        name_sql="CONCAT_WS(' ',t.first_name,t.last_name)", sort=("last_name", "ASC"),
        fields=[F("salutation", "Salutation", "enum", ["", "Mr.", "Ms.", "Mrs.", "Dr."]),
                F("first_name", "First Name"), F("last_name", "Last Name", "name", req=True),
                F("title", "Title"), F("department", "Department"),
                F("account_id", "Account Name", "relate", rel="Accounts"),
                F("email1", "Email Address", "email"), F("phone_work", "Office Phone", "phone"),
                F("phone_mobile", "Mobile", "phone"), F("primary_address_city", "City"),
                F("lead_source", "Lead Source", "enum", LEAD), F("do_not_call", "Do Not Call", "bool")],
        list=["last_name", "title", "account_id", "email1", "phone_work", "assigned_user_id"],
        filters=["lead_source"], search=["first_name", "last_name", "email1", "title"],
        panels=[("Contact", ["salutation", "first_name", "last_name", "title", "department", "account_id",
                             "email1", "phone_work", "phone_mobile", "primary_address_city"]),
                ("More information", ["lead_source", "do_not_call", "assigned_user_id", "description",
                                      "date_entered", "date_modified", "created_by"])],
        subpanels=[("Calls", "contact_id"), ("Meetings", "contact_id"), ("Cases", "contact_id")]),
    "Opportunities": _m(
        table="opportunities", label="Opportunities", single="Opportunity", importable=True,
        fields=[F("name", "Opportunity Name", "name", req=True),
                F("account_id", "Account Name", "relate", rel="Accounts"),
                F("opportunity_type", "Type", "enum", ["New SKU Listing", "Promo Campaign", "Range Extension",
                                                       "Private Label", "Tender", "Renewal"]),
                F("amount", "Opportunity Amount", "currency"),
                F("sales_stage", "Sales Stage", "enum", STAGES), F("probability", "Probability (%)", "int"),
                F("date_closed", "Expected Close Date", "date"), F("lead_source", "Lead Source", "enum", LEAD),
                F("next_step", "Next Step")],
        list=["name", "account_id", "sales_stage", "amount", "date_closed", "assigned_user_id"],
        filters=["sales_stage", "opportunity_type"], search=["name", "next_step"],
        panels=[("Overview", ["name", "account_id", "opportunity_type", "amount", "sales_stage", "probability",
                              "date_closed", "lead_source", "next_step", "assigned_user_id"]),
                ("Other", ["description", "date_entered", "date_modified", "created_by"])]),
    "AOS_Products": _m(
        table="aos_products", label="Products", single="Product", importable=True, sort=("name", "ASC"),
        fields=[F("name", "Product Name", "name", req=True), F("part_number", "ATB SKU"),
                F("supplier_sku", "Supplier Code"), F("ean", "EAN-13"),
                F("category", "Category", "enum", list(seed.CAT_CODE.keys())),
                F("unit", "Unit", "enum", ["pcs", "kg", "l", "pack", "box"]),
                F("cost", "Cost", "currency"), F("price", "Price (excl. VAT)", "currency"),
                F("vat_rate", "VAT %", "enum", ["20", "14", "7", "0"]),
                F("shelf_life_days", "Shelf life (days)", "int"), F("min_order_qty", "Min. order qty", "int"),
                F("status", "Status", "enum", ["Active", "Pending Listing", "Delisted", "Blocked"]),
                F("account_id", "Supplier", "relate", rel="Accounts")],
        list=["name", "part_number", "account_id", "category", "unit", "price", "status"],
        filters=["category", "status", "account_id"], search=["name", "part_number", "supplier_sku", "ean"],
        panels=[("Product", ["name", "part_number", "supplier_sku", "ean", "category", "unit", "account_id",
                             "status"]),
                ("Pricing & logistics", ["cost", "price", "vat_rate", "min_order_qty", "shelf_life_days",
                                         "assigned_user_id"]),
                ("Other", ["description", "date_entered", "date_modified", "created_by"])]),
    "ATB_PriceLists": _m(
        table="atb_pricelists", label="Price Lists", single="Price List", lines="pl",
        fields=[F("plist_number", "Price List No.", "name", req=True), F("name", "Title"),
                F("account_id", "Supplier", "relate", rel="Accounts"),
                F("status", "Status", "enum", ["Draft", "Submitted", "Under Review", "Approved", "Rejected",
                                               "Superseded"]),
                F("valid_from", "Valid From", "date"), F("valid_to", "Valid To", "date"),
                F("currency", "Currency", "enum", ["UAH", "EUR", "USD"]),
                F("avg_change", "Avg. change %", "float", ro=True),
                F("reviewer_id", "Reviewed By", "user", ro=True)],
        list=["plist_number", "name", "account_id", "status", "valid_from", "avg_change"],
        filters=["status", "account_id"], search=["plist_number", "name"], name_sql="t.plist_number",
        panels=[("Price list", ["plist_number", "name", "account_id", "status", "valid_from", "valid_to",
                                "currency", "avg_change", "reviewer_id", "assigned_user_id"]),
                ("Other", ["description", "date_entered", "date_modified", "created_by"])]),
    "ATB_PurchaseOrders": _m(
        table="atb_purchaseorders", label="Purchase Orders", single="Purchase Order", lines="po",
        fields=[F("name", "PO Number", "name", req=True),
                F("account_id", "Supplier", "relate", rel="Accounts"),
                F("status", "Status", "enum", ["Draft", "Sent", "Confirmed", "Shipped", "Delivered",
                                               "Invoiced", "Paid", "Cancelled"]),
                F("order_date", "Order Date", "date"), F("delivery_date", "Delivery Date", "date"),
                F("warehouse", "Ship To (DC)", "enum", seed.WAREHOUSES),
                F("payment_terms", "Payment Terms", "enum", TERMS),
                F("ttn_number", "Waybill (ТТН) No."),
                F("total_net", "Total (excl. VAT)", "currency", ro=True),
                F("total_vat", "VAT", "currency", ro=True), F("total_amount", "Grand Total", "currency", ro=True),
                F("currency", "Currency", "enum", ["UAH", "EUR", "USD"])],
        list=["name", "account_id", "status", "order_date", "delivery_date", "warehouse", "total_amount"],
        filters=["status", "warehouse", "account_id"], search=["name", "ttn_number"],
        panels=[("Order", ["name", "account_id", "status", "order_date", "delivery_date", "warehouse",
                           "payment_terms", "ttn_number", "currency", "assigned_user_id"]),
                ("Totals", ["total_net", "total_vat", "total_amount"]),
                ("Other", ["description", "date_entered", "date_modified", "created_by"])],
        subpanels=[("AOS_Invoices", "po_id")]),
    "AOS_Invoices": _m(
        table="aos_invoices", label="Invoices", single="Invoice",
        fields=[F("name", "Invoice No.", "name", req=True),
                F("account_id", "Supplier", "relate", rel="Accounts"),
                F("po_id", "Purchase Order", "relate", rel="ATB_PurchaseOrders"),
                F("invoice_date", "Invoice Date", "date"), F("due_date", "Due Date", "date"),
                F("total_net", "Total (excl. VAT)", "currency"), F("total_vat", "VAT", "currency"),
                F("total_amount", "Grand Total", "currency"), F("amount_paid", "Amount Paid", "currency"),
                F("status", "Status", "enum", ["Unpaid", "Partially Paid", "Paid", "Overdue", "Disputed",
                                               "Cancelled"]),
                F("tax_invoice_number", "Tax invoice (ПН) No."),
                F("erpn_status", "ЄРПН status", "enum", ["Registered", "Pending Registration", "Blocked",
                                                         "Not Required"])],
        list=["name", "account_id", "po_id", "invoice_date", "due_date", "total_amount", "status"],
        filters=["status", "erpn_status", "account_id"], search=["name", "tax_invoice_number"],
        panels=[("Invoice", ["name", "account_id", "po_id", "invoice_date", "due_date", "status",
                             "tax_invoice_number", "erpn_status", "assigned_user_id"]),
                ("Amounts", ["total_net", "total_vat", "total_amount", "amount_paid"]),
                ("Other", ["description", "date_entered", "date_modified", "created_by"])]),
    "Documents": _m(
        table="documents", label="Documents", single="Document", name_sql="t.document_name",
        fields=[F("document_name", "Document Name", "name", req=True),
                F("filename", "File Name", "file", ro=True),
                F("category_id", "Category", "enum", ["Contract", "Certificate", "Price List", "Specification",
                                                      "Quality Declaration", "Bank Details", "Other"]),
                F("status_id", "Status", "enum", ["Active", "Draft", "Under Review", "Expired"]),
                F("revision", "Revision"), F("active_date", "Publish Date", "date"),
                F("exp_date", "Expiration Date", "date"),
                F("account_id", "Account", "relate", rel="Accounts"),
                F("file_mime_type", "Mime Type", ro=True), F("file_size", "File Size (bytes)", "int", ro=True)],
        list=["document_name", "category_id", "account_id", "status_id", "active_date", "exp_date"],
        filters=["category_id", "status_id", "account_id"], search=["document_name", "filename"],
        panels=[("Document", ["document_name", "filename", "category_id", "status_id", "revision", "account_id",
                              "active_date", "exp_date", "file_mime_type", "file_size", "assigned_user_id"]),
                ("Other", ["description", "date_entered", "date_modified", "created_by"])]),
    "Cases": _m(
        table="cases", label="Cases", single="Case", importable=True,
        fields=[F("case_number", "Number", "int", ro=True), F("name", "Subject", "name", req=True),
                F("account_id", "Account Name", "relate", rel="Accounts"),
                F("contact_id", "Contact", "relate", rel="Contacts"),
                F("status", "Status", "enum", ["New", "Assigned", "Pending Input", "Closed", "Rejected",
                                               "Duplicate"]),
                F("priority", "Priority", "enum", ["High", "Medium", "Low"]),
                F("type", "Type", "enum", ["Delivery", "Invoice / Payment", "Quality", "Price Change",
                                           "Portal Access", "Master Data", "Other"]),
                F("resolution", "Resolution", "text")],
        list=["case_number", "name", "account_id", "priority", "status", "assigned_user_id", "date_entered"],
        filters=["status", "priority", "type"], search=["name"],
        panels=[("Case", ["case_number", "name", "account_id", "contact_id", "status", "priority", "type",
                          "assigned_user_id"]),
                ("Details", ["description", "resolution"]),
                ("Other", ["date_entered", "date_modified", "created_by"])]),
    "Calls": _m(
        table="calls", label="Calls", single="Call", importable=True, sort=("date_start", "DESC"),
        fields=[F("name", "Subject", "name", req=True),
                F("direction", "Direction", "enum", ["Outbound", "Inbound"]),
                F("status", "Status", "enum", ["Planned", "Held", "Not Held"]),
                F("date_start", "Start Date", "datetime"), F("duration_minutes", "Duration (min)", "int"),
                F("account_id", "Related to (Account)", "relate", rel="Accounts"),
                F("contact_id", "Contact", "relate", rel="Contacts")],
        list=["name", "direction", "status", "account_id", "contact_id", "date_start", "assigned_user_id"],
        filters=["status", "direction"], search=["name"],
        panels=[("Call", ["name", "direction", "status", "date_start", "duration_minutes", "account_id",
                          "contact_id", "assigned_user_id"]),
                ("Other", ["description", "date_entered", "date_modified", "created_by"])]),
    "Meetings": _m(
        table="meetings", label="Meetings", single="Meeting", importable=True, sort=("date_start", "DESC"),
        fields=[F("name", "Subject", "name", req=True),
                F("status", "Status", "enum", ["Planned", "Held", "Not Held"]),
                F("location", "Location"), F("date_start", "Start Date", "datetime"),
                F("duration_minutes", "Duration (min)", "int"),
                F("account_id", "Related to (Account)", "relate", rel="Accounts"),
                F("contact_id", "Contact", "relate", rel="Contacts")],
        list=["name", "status", "location", "account_id", "date_start", "assigned_user_id"],
        filters=["status"], search=["name", "location"],
        panels=[("Meeting", ["name", "status", "location", "date_start", "duration_minutes", "account_id",
                             "contact_id", "assigned_user_id"]),
                ("Other", ["description", "date_entered", "date_modified", "created_by"])]),
    "Employees": _m(
        table="users", label="Employees", single="Employee", readonly=True, sort=("last_name", "ASC"),
        name_sql="COALESCE(NULLIF(CONCAT_WS(' ',t.first_name,t.last_name),''),t.user_name)",
        fields=[F("last_name", "Name", "name"), F("user_name", "User Name"), F("title", "Title"),
                F("department", "Department"), F("email1", "Email", "email"),
                F("phone_work", "Office Phone", "phone"), F("address_city", "City"),
                F("status", "Status", "enum", ["Active", "Inactive"]),
                F("user_type", "User Type", "enum", ["Staff", "Supplier"]),
                F("last_login", "Last Login", "datetime"), F("date_entered", "Date Created", "datetime")],
        list=["last_name", "user_name", "title", "department", "email1", "phone_work", "user_type"],
        filters=["user_type", "department"], search=["user_name", "first_name", "last_name", "email1"],
        panels=[("Employee", ["last_name", "user_name", "title", "department", "email1", "phone_work",
                              "address_city", "status", "user_type", "date_entered"])]),
}
MODULES["Employees"]["f"]["department"]["type"] = "varchar"
NAME_FIELD = {m: next(f["name"] for f in md["fields"] if f["type"] == "name") for m, md in MODULES.items()}

NAV = [("Sales", ["Accounts", "Contacts", "Opportunities"]),
       ("Supply", ["AOS_Products", "ATB_PriceLists", "ATB_PurchaseOrders", "AOS_Invoices"]),
       ("Support", ["Cases"]),
       ("Activities", ["Calls", "Meetings"]),
       ("Collaboration", ["Documents", "Employees"])]


def url(module=None, action=None, **kw):
    p = {}
    if module:
        p["module"] = module
    if action:
        p["action"] = action
    p.update({k: v for k, v in kw.items() if v not in (None, "")})
    return "/index.php?" + urllib.parse.urlencode(p)


# ---------------------------------------------------------------- formatting
def fmt_money(v, cur="₴"):
    if v in (None, ""):
        return ""
    try:
        return f"{cur}{float(v):,.2f}"
    except (TypeError, ValueError):
        return e(v)


def fmt_date(v):
    if not v:
        return ""
    if isinstance(v, dt.datetime):
        return v.strftime("%d.%m.%Y %H:%M")
    if isinstance(v, dt.date):
        return v.strftime("%d.%m.%Y")
    return str(v)


def names_for(module, ids):
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    md = MODULES[module]
    rows = q(f"SELECT t.id, {md['name_sql']} AS n FROM {md['table']} t WHERE t.id IN "
             f"({','.join(['%s'] * len(ids))})", ids)
    return {r["id"]: r["n"] for r in rows}


def resolve(module, rows, fields):
    """{field: {id: name}} for relate/user fields among `fields`."""
    md = MODULES[module]
    out = {}
    for fn in fields:
        f = md["f"].get(fn)
        if f and f["type"] in ("relate", "user"):
            rel = f["rel"] if f["type"] == "relate" else "Employees"
            out[fn] = names_for(rel, [r.get(fn) for r in rows])
    return out


BADGE = {"Paid": "ok", "Approved": "ok", "Closed Won": "ok", "Active": "ok", "Held": "ok", "Delivered": "ok",
         "Closed": "mute", "Superseded": "mute", "Cancelled": "mute", "Delisted": "mute", "Expired": "mute",
         "Overdue": "bad", "Disputed": "bad", "Rejected": "bad", "Closed Lost": "bad", "High": "bad",
         "Blocked": "bad", "Not Held": "mute", "New": "info", "Submitted": "info", "Under Review": "warn",
         "Pending Input": "warn", "Partially Paid": "warn", "Unpaid": "warn", "Pending Listing": "warn",
         "Sent": "info", "Confirmed": "info", "Shipped": "info", "Invoiced": "warn", "Planned": "info",
         "Draft": "mute", "Medium": "warn", "Low": "mute", "Pending Registration": "warn"}


def render_value(module, f, row, rel, link=True):
    v = row.get(f["name"])
    t = f["type"]
    if t == "name":
        label = row.get("_display") or v or "(no name)"
        if link:
            return f'<a href="{e(url(module, "DetailView", record=row["id"]))}">{e(label)}</a>'
        return e(label)
    if v in (None, ""):
        return ""
    if t in ("relate", "user"):
        rmod = f["rel"] if t == "relate" else "Employees"
        name = rel.get(f["name"], {}).get(v)
        if not name:
            return ""
        if t == "user":
            return e(name)
        return f'<a href="{e(url(rmod, "DetailView", record=v))}">{e(name)}</a>'
    if t == "currency":
        return fmt_money(v)
    if t in ("date", "datetime"):
        return fmt_date(v)
    if t == "bool":
        return "&#10003;" if str(v) in ("1", "True") else ""
    if t == "email":
        return f'<a href="mailto:{e(v)}">{e(v)}</a>'
    if t == "enum":
        cls = BADGE.get(str(v))
        return f'<span class="badge {cls}">{e(v)}</span>' if cls else e(v)
    if t == "text":
        return e(v).replace("\n", "<br>")
    if t == "file":
        return (f'<a href="{e("/index.php?entryPoint=download&type=Documents&id=" + row["id"])}">'
                f'&#128206; {e(v)}</a>')
    if t == "float":
        try:
            return f"{float(v):+.2f}%" if f["name"] == "avg_change" else f"{float(v):.2f}"
        except ValueError:
            return e(v)
    return e(v)


def with_display(module, rows):
    md = MODULES[module]
    if module == "Contacts":
        for r in rows:
            r["_display"] = f"{r.get('salutation') or ''} {r.get('first_name') or ''} {r.get('last_name') or ''}".strip()
    elif module == "Employees":
        for r in rows:
            r["_display"] = full_name(r)
    else:
        nf = NAME_FIELD[module]
        for r in rows:
            r["_display"] = r.get(nf)
    return rows


# ----------------------------------------------------------------- theme
THEME_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--nav:#2b333b;--nav2:#333c45;--acc:#f08377;--acc2:#e86f62;--line:#e1e6ea;--bg:#eef1f4;
      --ink:#2b2f33;--mute:#8a9199;--link:#d0574a}
html{-webkit-text-size-adjust:100%}
body{font-family:'Segoe UI',Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg);
     font-size:14px;-webkit-font-smoothing:antialiased}
a{color:var(--link);text-decoration:none}a:hover{text-decoration:underline}
.wm{font-size:22px;font-weight:700;letter-spacing:.5px;color:#fff}.wm span{color:var(--acc)}
/* navbar */
.navbar{background:var(--nav);color:#cfd6dd;display:flex;align-items:stretch;min-height:52px;
        position:sticky;top:0;z-index:50;box-shadow:0 2px 6px rgba(0,0,0,.25)}
.navbar .brand{display:flex;align-items:center;padding:0 22px;border-right:1px solid #3a434c}
.navbar .brand:hover{text-decoration:none}
.tabs{display:flex;align-items:stretch;flex:1;min-width:0}
.tab{position:relative;display:flex;align-items:center}
.tab>a,.tab>span{display:flex;align-items:center;height:100%;padding:0 16px;color:#cfd6dd;font-size:13px;
      font-weight:600;text-transform:uppercase;letter-spacing:.5px;cursor:pointer;border-bottom:3px solid transparent}
.tab>a:hover,.tab:hover>span{background:var(--nav2);text-decoration:none;color:#fff}
.tab.on>a,.tab.on>span{border-bottom-color:var(--acc);color:#fff}
.menu{display:none;position:absolute;top:100%;left:0;min-width:210px;background:#fff;border:1px solid var(--line);
      border-radius:0 0 4px 4px;box-shadow:0 6px 18px rgba(0,0,0,.18);padding:6px 0;z-index:60}
.tab:hover .menu,.tab:focus-within .menu{display:block}
.menu a{display:block;padding:9px 16px;color:var(--ink);font-size:13px}
.menu a:hover{background:#f6f7f9;text-decoration:none;color:var(--link)}
.navr{display:flex;align-items:center;gap:10px;padding:0 16px}
.navr form{display:flex}
.navr input{width:190px;padding:7px 10px;border-radius:3px;border:1px solid #46505a;background:#39424b;
      color:#fff;font-size:13px}
.navr input::placeholder{color:#99a2ab}
.navr .tab>span{text-transform:none;font-weight:600;letter-spacing:0}
.navr .menu{left:auto;right:0}
/* layout */
.page{display:flex;min-height:calc(100vh - 52px)}
.side{width:220px;flex-shrink:0;background:#fff;border-right:1px solid var(--line);padding:18px 0}
.side h4{font-size:11px;letter-spacing:.8px;color:var(--mute);text-transform:uppercase;padding:0 18px 8px}
.side a{display:block;padding:7px 18px;color:var(--ink);font-size:13px;white-space:nowrap;overflow:hidden;
        text-overflow:ellipsis}
.side a:hover{background:#f6f7f9;color:var(--link);text-decoration:none}
.side .sep{height:1px;background:var(--line);margin:14px 0}
.main{flex:1;min-width:0;padding:22px 26px 40px}
.mtitle{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.mtitle h1{font-size:20px;font-weight:600;color:#2b333b;text-transform:uppercase;letter-spacing:.6px}
.mtitle h1 small{display:block;text-transform:none;font-size:13px;color:var(--mute);letter-spacing:0;font-weight:400;margin-top:3px}
.crumb{font-size:12px;color:var(--mute);margin-bottom:6px}
/* buttons */
.btn,button.btn{display:inline-block;padding:8px 16px;border:none;border-radius:3px;background:var(--acc);
     color:#fff;font-size:13px;font-weight:600;cursor:pointer;line-height:1.3;font-family:inherit}
.btn:hover{background:var(--acc2);text-decoration:none}
.btn.sec{background:#fff;color:#2b333b;border:1px solid #cfd6dd}.btn.sec:hover{background:#f6f7f9}
.btn.dark{background:#2b333b}.btn.dark:hover{background:#3a444d}
.btn.sm{padding:5px 10px;font-size:12px}
.btn.danger{background:#c0392b}
.btns{display:flex;gap:8px;flex-wrap:wrap}
/* panels & tables */
.card{background:#fff;border:1px solid var(--line);border-radius:4px;margin-bottom:18px}
.card>.hd{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 16px;
     border-bottom:1px solid var(--line);font-size:12px;font-weight:700;text-transform:uppercase;
     letter-spacing:.6px;color:#4a525a;background:#fafbfc;border-radius:4px 4px 0 0}
.card>.hd a{text-transform:none;letter-spacing:0;font-weight:600}
.card>.bd{padding:16px}
.tw{overflow-x:auto}
table.list{width:100%;border-collapse:collapse;font-size:13px}
table.list th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#60666c;
     background:#f3f5f7;padding:9px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
table.list th a{color:#60666c}
table.list td{padding:9px 10px;border-bottom:1px solid #eef1f4;vertical-align:top}
table.list tr:hover td{background:#fbfbfc}
table.list td.num,table.list th.num{text-align:right;white-space:nowrap}
table.list tfoot td{font-weight:700;background:#fafbfc}
.empty{padding:22px;text-align:center;color:var(--mute)}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;background:#eef1f4;color:#4a525a;white-space:nowrap}
.badge.ok{background:#e3f5e8;color:#1e7b3a}.badge.bad{background:#fde8e6;color:#b03a2e}
.badge.warn{background:#fff3dc;color:#9a6200}.badge.info{background:#e6f0fb;color:#215d9c}
.badge.mute{background:#eceff1;color:#6b737a}
/* detail */
.dgrid{display:grid;grid-template-columns:1fr 1fr;gap:0 28px}
.dgrid .it{display:flex;padding:9px 0;border-bottom:1px solid #f0f2f4;min-width:0}
.dgrid .it.wide{grid-column:1/-1}
.dgrid .lb{width:42%;flex-shrink:0;color:#60666c;font-size:12px;font-weight:600;padding-right:10px}
.dgrid .vl{flex:1;min-width:0;word-wrap:break-word}
/* forms */
.fgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px 28px}
.fgrid .wide{grid-column:1/-1}
label.fl{display:block;font-size:12px;font-weight:600;color:#60666c;margin-bottom:5px}
label.fl .req{color:#c0392b}
input.in,select.in,textarea.in{width:100%;padding:8px 10px;border:1px solid #cfd6dd;border-radius:3px;
     font-size:13px;background:#fff;font-family:inherit;color:var(--ink)}
textarea.in{min-height:90px;resize:vertical}
input.in:focus,select.in:focus,textarea.in:focus{outline:none;border-color:var(--acc);box-shadow:0 0 0 2px rgba(240,131,119,.18)}
.filter{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;padding:12px 16px;border-bottom:1px solid var(--line)}
.filter .fi{min-width:150px;flex:0 1 190px}
.filter .fi.q{flex:1 1 220px}
.chk{display:flex;align-items:center;gap:6px;font-size:13px;white-space:nowrap}
.chk input{width:auto}
.lvbar{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:10px 16px}
.pag{display:flex;align-items:center;gap:6px;font-size:12px;color:#60666c}
.pag a,.pag span.dis{display:inline-block;min-width:30px;text-align:center;padding:4px 8px;border:1px solid #cfd6dd;
     border-radius:3px;color:#2b333b;background:#fff}
.pag span.dis{color:#c3c9cf}
.msg{padding:11px 16px;border-radius:4px;margin-bottom:16px;font-size:13px}
.msg.ok{background:#e3f5e8;color:#1e5a31;border:1px solid #bfe5ca}
.msg.err{background:#fde8e6;color:#8c2b20;border:1px solid #f5c6c0}
.msg.info{background:#e6f0fb;color:#1f4f82;border:1px solid #c5dbf2}
/* dashlets */
.dash{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
.dash .card{margin:0}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:18px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:4px;padding:14px 16px;border-top:3px solid var(--acc)}
.kpi .v{font-size:22px;font-weight:700;color:#2b333b;margin-top:4px}
.kpi .l{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--mute);font-weight:700}
.kpi .s{font-size:12px;color:var(--mute);margin-top:2px}
.bars .row{display:flex;align-items:center;gap:10px;margin:7px 0;font-size:12px}
.bars .lab{width:150px;flex-shrink:0;color:#4a525a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bars .trk{flex:1;background:#f0f2f4;border-radius:2px;height:14px;overflow:hidden}
.bars .fil{height:100%;background:var(--acc)}
.bars .val{width:110px;text-align:right;color:#4a525a;white-space:nowrap}
.steps{display:flex;gap:0;margin-bottom:18px;flex-wrap:wrap}
.steps div{flex:1;min-width:120px;padding:10px 12px;background:#fff;border:1px solid var(--line);font-size:12px;
     color:var(--mute);font-weight:600;text-transform:uppercase;letter-spacing:.4px}
.steps div.on{background:var(--nav);color:#fff;border-color:var(--nav)}
.steps div.done{color:#1e7b3a}
.foot{padding:14px 26px;color:#9aa1a8;font-size:12px;border-top:1px solid var(--line);background:#fff;
      display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
pre.raw{white-space:pre-wrap;font-size:12px;background:#f6f7f9;border:1px solid var(--line);padding:10px;border-radius:3px}
iframe.resp{width:100%;height:200px;border:1px solid var(--line);border-radius:3px;background:#fff}
.hamb{display:none}
@media(max-width:980px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.dash{grid-template-columns:minmax(0,1fr)}}
.dgrid .it.wide .lb{width:21%}
@media(max-width:760px){
  .navbar{flex-wrap:wrap}.navbar .brand{padding:12px 16px;border-right:none;flex:1}
  .hamb{display:flex;align-items:center;padding:0 16px;color:#fff;font-size:22px;cursor:pointer}
  .tabs{display:none;flex-basis:100%;flex-direction:column;border-top:1px solid #3a434c}
  #navtoggle:checked~.tabs{display:flex}
  .tab{flex-direction:column;align-items:stretch}.tab>a,.tab>span{padding:12px 16px}
  .menu{position:static;display:block;box-shadow:none;border:none;border-radius:0;background:var(--nav2);padding:0}
  .menu a{color:#cfd6dd;padding:9px 28px}
  .navr{display:none;flex-basis:100%;padding:8px 16px 12px;flex-wrap:wrap}#navtoggle:checked~.navr{display:flex}
  .navr .tab{flex-basis:100%}.navr form{flex:1}.navr input{width:100%}
  .page{flex-direction:column}.side{width:100%;border-right:none;border-bottom:1px solid var(--line);padding:10px 0}
  .side .recent{display:none}
  .main{padding:16px}
  .dgrid,.fgrid{grid-template-columns:minmax(0,1fr)}.dgrid .it.wide .lb{width:40%}.kpis{grid-template-columns:1fr 1fr}
  .dgrid .lb{width:40%}
}
"""

_LOGIN_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Helvetica,Arial,sans-serif;color:#2b2f33;
     background:#eef1f4;-webkit-font-smoothing:antialiased}
a{color:#f08377;text-decoration:none}a:hover{text-decoration:underline}
.wm{font-size:30px;font-weight:700;letter-spacing:.5px;color:#fff}
.wm span{color:#f08377}
.muted{color:#8a9199;font-size:13px}
input,select{width:100%;padding:11px 12px;border:1px solid #cfd6dd;border-radius:4px;
     font-size:14px;background:#fff;margin-top:6px}
input:focus,select:focus{outline:none;border-color:#f08377;
     box-shadow:0 0 0 2px rgba(240,131,119,.18)}
label{display:block;font-size:12px;font-weight:600;color:#60666c;
     text-transform:uppercase;letter-spacing:.4px;margin-top:16px}
.btn{display:inline-block;width:100%;margin-top:22px;padding:12px;border:none;
     border-radius:4px;background:#f08377;color:#fff;font-size:15px;font-weight:600;
     cursor:pointer}
.btn:hover{background:#e86f62}
body{display:flex;align-items:center;justify-content:center;min-height:100vh;
     background:linear-gradient(135deg,#232a31 0%,#2f3a44 100%);padding:16px}
.card{width:100%;max-width:380px;background:#fff;border-radius:8px;
     box-shadow:0 10px 40px rgba(0,0,0,.35);overflow:hidden}
.card.wide{max-width:460px}
.head{background:#2b333b;padding:28px 32px 24px;text-align:center}
.sub{color:#aeb6bd;font-size:13px;margin-top:6px}
.body{padding:26px 32px 30px}
.foot{text-align:center;padding:16px;border-top:1px solid #eef1f4;
     color:#9aa1a8;font-size:12px}
.reg{text-align:center;margin-top:18px;font-size:13px}
.note{color:#60666c;font-size:13px;line-height:1.5}
iframe{width:100%;height:110px;border:1px solid #e1e6ea;border-radius:4px;margin-top:16px}
"""


def login_page(error=""):
    err = (f'<div style="color:#c0392b;font-size:13px;margin-top:14px">{error}</div>'
           if error else "")
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SuiteCRM</title><style>{_LOGIN_CSS}</style></head><body>
<div class="card">
  <div class="head">
    <div class="wm">Suite<span>CRM</span></div>
    <div class="sub">ATB Supplier Portal</div>
  </div>
  <div class="body">
    <form method="post" action="/index.php?action=Login">
      <label>User Name</label>
      <input type="text" name="user_name" autocomplete="username" placeholder="user name">
      <label>Password</label>
      <input type="password" name="password" autocomplete="current-password" placeholder="password">
      <button class="btn" type="submit">Log In</button>
      {err}
    </form>
    <div class="reg">New supplier?
      <a href="/index.php?action=Signup">Register as a supplier</a>
    </div>
  </div>
  <div class="foot">SuiteCRM 7.10.25 &middot; &copy; 2026 ATB-Market</div>
</div>
</body></html>"""


def signup_page():
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SuiteCRM</title><style>{_LOGIN_CSS}</style></head><body>
<div class="card wide">
  <div class="head"><div class="wm">Suite<span>CRM</span></div>
    <div class="sub">Supplier Registration</div></div>
  <div class="body">
    <div class="note">Create a supplier account for the ATB-Market procurement portal.
      A password-reset link will be generated for you to set your password.</div>
    <form method="post" target="respframe"
          action="/index.php?entryPoint=GeneratePassword">
      <input type="hidden" name="link" value="0">
      <label>Email / User Name</label>
      <input type="text" name="user_name" placeholder="supplier@example.com" required>
      <button class="btn" type="submit">Register</button>
    </form>
    <iframe name="respframe" title="status"></iframe>
    <div class="reg">Already registered? <a href="/index.php?action=Login">Back to login</a></div>
  </div>
  <div class="foot">SuiteCRM 7.10.25</div>
</div></body></html>"""


def change_password_page(guid, msg=""):
    note = f'<div class="muted" style="margin-top:14px">{msg}</div>' if msg else ""
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SuiteCRM</title><style>{_LOGIN_CSS}</style></head><body>
<div class="card"><div class="head"><div class="wm">Suite<span>CRM</span></div>
<div class="sub">Set your password</div></div><div class="body">
<form method="post" action="/index.php?entryPoint=Changenewpassword&amp;guid={guid}">
  <label>New password</label><input type="password" name="password1" required>
  <label>Confirm password</label><input type="password" name="password2" required>
  <button class="btn" type="submit">Save</button>{note}
</form></div></div></body></html>"""


def layout(ctx, title, body, module=None, sub=None, crumb=None):
    me = ctx["me"]
    tabs = [f'<div class="tab{" on" if module == "Home" else ""}"><a href="{e(url("Home", "index"))}">Home</a></div>']
    for grp, mods in NAV:
        on = " on" if module in mods else ""
        items = "".join(f'<a href="{e(url(m, "index"))}">{e(MODULES[m]["label"])}</a>' for m in mods)
        tabs.append(f'<div class="tab{on}" tabindex="0"><span>{e(grp)} &#9662;</span>'
                    f'<div class="menu">{items}</div></div>')
    on = " on" if module == "Import" else ""
    tabs.append(f'<div class="tab{on}"><a href="{e(url("Import", "index"))}">Import</a></div>')
    side = ""
    if module in MODULES:
        md = MODULES[module]
        acts = ""
        if not md["readonly"]:
            acts += f'<a href="{e(url(module, "EditView"))}">+ Create {e(md["single"])}</a>'
        acts += f'<a href="{e(url(module, "index"))}">&#9776; View {e(md["label"])}</a>'
        if md["importable"]:
            acts += f'<a href="{e(url("Import", "index", import_module=module))}">&#8682; Import {e(md["label"])}</a>'
        side = f"<h4>Actions</h4>{acts}"
    elif module == "Home":
        side = ("<h4>Quick create</h4>"
                + "".join(f'<a href="{e(url(m, "EditView"))}">+ {e(MODULES[m]["single"])}</a>'
                          for m in ("Cases", "Calls", "Meetings", "Documents", "Contacts")))
    elif module in ("Import", "Users"):
        side = ("<h4>Actions</h4>" + f'<a href="{e(url("Import", "index"))}">&#8682; Import Data</a>'
                f'<a href="{e(url("Users", "DetailView", record=me.get("id")))}">&#9787; My Account</a>')
    recent = ""
    try:
        rv = q("SELECT module_name, item_id, MAX(item_summary) s, MAX(date_modified) d FROM tracker "
               "WHERE user_id=%s GROUP BY module_name, item_id ORDER BY d DESC LIMIT 8", (me.get("id"),))
        if rv:
            recent = ('<div class="recent"><div class="sep"></div><h4>Recently viewed</h4>'
                      + "".join(f'<a href="{e(url(r["module_name"], "DetailView", record=r["item_id"]))}" '
                                f'title="{e(r["s"])}">{e(r["s"])}</a>' for r in rv) + "</div>")
    except Exception:
        pass
    crumbs = f'<div class="crumb">{crumb}</div>' if crumb else ""
    subt = f"<small>{sub}</small>" if sub else ""
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} &raquo; SuiteCRM</title>
<link rel="stylesheet" href="/themes/SuiteP/css/style.css?v=7.10.25"></head><body>
<header class="navbar">
  <a class="brand" href="{e(url("Home", "index"))}"><span class="wm">Suite<span>CRM</span></span></a>
  <label class="hamb" for="navtoggle">&#9776;</label><input type="checkbox" id="navtoggle" hidden>
  <nav class="tabs">{"".join(tabs)}</nav>
  <div class="navr">
    <form method="get" action="/index.php"><input type="hidden" name="module" value="Home">
      <input type="hidden" name="action" value="UnifiedSearch">
      <input name="query_string" placeholder="Search..." value="{e(request.args.get('query_string', '') if module == 'Home' else '')}"></form>
    <div class="tab" tabindex="0"><span>&#9787; {e(full_name(me))} &#9662;</span><div class="menu">
      <a href="{e(url("Users", "DetailView", record=me.get("id")))}">My Account</a>
      <a href="{e(url("Users", "ChangePassword"))}">Change Password</a>
      <a href="{e(url("Employees", "index"))}">Employees</a>
      <a href="{e(url("Import", "index"))}">Import</a>
      <a href="/index.php?action=Logout">Log Out</a></div></div>
  </div>
</header>
<div class="page">
  <aside class="side">{side}{recent}</aside>
  <main class="main">{crumbs}<div class="mtitle"><h1>{e(title)}{subt}</h1></div>{body}</main>
</div>
<div class="foot"><span>&copy; Supercharged by SuiteCRM &middot; Powered by SugarCRM</span>
<span>SuiteCRM 7.10.25 &middot; ATB Supplier Portal &middot; Server time {now().strftime('%d.%m.%Y %H:%M')}</span></div>
<script>
document.querySelectorAll('form[data-confirm]').forEach(function(f){{f.addEventListener('submit',function(ev){{
 if(!confirm(f.getAttribute('data-confirm')))ev.preventDefault();}});}});
var ca=document.getElementById('checkall');if(ca)ca.addEventListener('change',function(){{
 document.querySelectorAll('input[name=mass]').forEach(function(c){{c.checked=ca.checked;}});}});
</script>
</body></html>"""


def page(ctx, title, body, module=None, **kw):
    return html(layout(ctx, title, body, module, **kw))


def db_error_page():
    return html("""<!doctype html><html><head><meta charset="utf-8"><title>SuiteCRM</title>
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Segoe UI,Arial,sans-serif;background:#eef1f4;padding:40px">
<div style="max-width:560px;margin:auto;background:#fff;border:1px solid #e1e6ea;border-radius:6px;padding:26px">
<h2 style="font-size:18px;margin-bottom:10px">Database failure</h2>
<p style="color:#60666c;font-size:14px">Database failure. Please refer to suitecrm.log for details.</p>
<p style="margin-top:16px"><a style="color:#d0574a" href="/index.php">Retry</a></p></div></body></html>""", 503)


def msg_box():
    m = request.args.get("msg", "")
    known = {"saved": ("ok", "Record saved."), "deleted": ("ok", "Record deleted."),
             "mass_deleted": ("ok", "Selected records deleted."), "line_added": ("ok", "Line item added."),
             "line_removed": ("ok", "Line item removed."), "pw_changed": ("ok", "Your password has been changed."),
             "profile": ("ok", "Profile updated."), "undone": ("ok", "Last import has been undone."),
             "nothing": ("info", "Please select at least one record.")}
    if m in known:
        cls, text = known[m]
        return f'<div class="msg {cls}">{e(text)}</div>'
    return ""


# ------------------------------------------------------------ dispatcher
def dispatch(module, action, user, ip):
    if not DB_READY.is_set():
        return db_error_page()
    try:
        ctx = {"user": user, "me": me_row(user), "ip": ip}
        if module == "Home":
            if action == "UnifiedSearch":
                return unified_search(ctx)
            return home(ctx)
        if module == "Users":
            return users_module(ctx, action)
        if module == "Import":
            return import_wizard(ctx, action)
        if module in MODULES:
            fn = {"index": list_view, "ListView": list_view, "DetailView": detail_view,
                  "EditView": edit_view, "Save": save_record, "Delete": delete_record,
                  "MassUpdate": mass_update, "Export": export_records, "AddLine": add_line,
                  "RemoveLine": remove_line}.get(action, list_view)
            return fn(ctx, module)
        return page(ctx, "Error", '<div class="msg err">The requested module is not available or you do not '
                                  'have access to it.</div>', None)
    except pymysql.err.Error as ex_:
        print(f"[supplier] db error: {ex_}", flush=True)
        return db_error_page()


# ---------------------------------------------------------------- list view
def _list_query(module, args, ctx):
    md = MODULES[module]
    where, params = ["t.deleted=0"], []
    qs = (args.get("query_string") or "").strip()
    if qs:
        where.append("(" + " OR ".join(f"t.{c} LIKE %s" for c in md["search"]) + ")")
        params += [f"%{qs}%"] * len(md["search"])
    for fn, f in md["f"].items():
        v = args.get("f_" + fn)
        if v and (fn in md["filters"] or f["type"] in ("relate", "user")):
            where.append(f"t.{fn}=%s")
            params.append(v)
    if args.get("my_items") and not md["readonly"]:
        where.append("t.assigned_user_id=%s")
        params.append(ctx["me"].get("id"))
    return " AND ".join(where), params


def _sort(module, args):
    md = MODULES[module]
    ob = args.get("orderBy", "")
    so = "ASC" if args.get("sortOrder", "").upper() == "ASC" else "DESC"
    if ob not in md["f"]:
        ob, so = md["sort"]
    return ob, so


def list_table(module, rows, cols, rel, mass=False, sort=None, base=None):
    md = MODULES[module]
    head = '<th style="width:28px"><input type="checkbox" id="checkall"></th>' if mass else ""
    for c in cols:
        f = md["f"][c]
        cls = ' class="num"' if f["type"] in ("currency", "float") else ""
        if sort is not None:
            ob, so = sort
            nso = "ASC" if (ob != c or so == "DESC") else "DESC"
            arrow = (" &#9650;" if so == "ASC" else " &#9660;") if ob == c else ""
            head += f'<th{cls}><a href="{e(base + "&" + urllib.parse.urlencode({"orderBy": c, "sortOrder": nso}))}">{e(f["label"])}{arrow}</a></th>'
        else:
            head += f"<th{cls}>{e(f['label'])}</th>"
    body = ""
    for r in rows:
        tds = f'<td><input type="checkbox" name="mass" value="{e(r["id"])}"></td>' if mass else ""
        for c in cols:
            f = md["f"][c]
            cls = ' class="num"' if f["type"] in ("currency", "float") else ""
            tds += f"<td{cls}>{render_value(module, f, r, rel)}</td>"
        body += f"<tr>{tds}</tr>"
    if not rows:
        body = f'<tr><td colspan="{len(cols) + (1 if mass else 0)}" class="empty">No data</td></tr>'
    return f'<div class="tw"><table class="list"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _rel_options(module, selected=None, where="", params=()):
    md = MODULES[module]
    rows = q(f"SELECT t.id, {md['name_sql']} AS n FROM {md['table']} t WHERE t.deleted=0 {where} "
             f"ORDER BY n LIMIT 500", params)
    return "".join(f'<option value="{e(r["id"])}"{" selected" if r["id"] == selected else ""}>{e(r["n"])}</option>'
                   for r in rows)


def list_view(ctx, module):
    md = MODULES[module]
    args = request.args
    where, params = _list_query(module, args, ctx)
    ob, so = _sort(module, args)
    try:
        offset = max(0, int(args.get("offset", 0)))
    except ValueError:
        offset = 0
    total = q1(f"SELECT COUNT(*) n FROM {md['table']} t WHERE {where}", params)["n"]
    rows = q(f"SELECT t.* FROM {md['table']} t WHERE {where} ORDER BY t.{ob} {so}, t.id LIMIT %s OFFSET %s",
             params + [PAGE_SIZE, offset])
    with_display(module, rows)
    rel = resolve(module, rows, md["list"])
    keep = {k: v for k, v in args.items() if (k.startswith("f_") or k in ("query_string", "my_items")) and v}
    base = url(module, "index", **keep)
    # filter bar
    fl = (f'<div class="fi q"><label class="fl">Filter</label><input class="in" name="query_string" '
          f'value="{e(args.get("query_string", ""))}" placeholder="{e(", ".join(md["f"][c]["label"] for c in md["search"] if c in md["f"]))}"></div>')
    for fn in md["filters"]:
        f = md["f"][fn]
        cur = args.get("f_" + fn, "")
        if f["type"] == "relate":
            opts = _rel_options(f["rel"], cur)
        elif fn == "department":
            opts = "".join(f'<option{" selected" if d["department"] == cur else ""}>{e(d["department"])}</option>'
                           for d in q("SELECT DISTINCT department FROM users WHERE deleted=0 AND department<>'' ORDER BY 1"))
        else:
            opts = "".join(f'<option{" selected" if o == cur else ""}>{e(o)}</option>' for o in f["opts"] if o)
        fl += (f'<div class="fi"><label class="fl">{e(f["label"])}</label><select class="in" name="f_{fn}">'
               f'<option value="">— any —</option>{opts}</select></div>')
    for k, v in keep.items():   # carry relate filters coming from subpanel "view all" links
        if k.startswith("f_") and k[2:] not in md["filters"]:
            fl += f'<input type="hidden" name="{e(k)}" value="{e(v)}">'
    if not md["readonly"]:
        fl += (f'<label class="chk"><input type="checkbox" name="my_items" value="1"'
               f'{" checked" if args.get("my_items") else ""}> My Items</label>')
    fl += (f'<div class="btns"><button class="btn" type="submit">Search</button>'
           f'<a class="btn sec" href="{e(url(module, "index"))}">Clear</a></div>')
    filt = (f'<form class="filter" method="get" action="/index.php"><input type="hidden" name="module" value="{e(module)}">'
            f'<input type="hidden" name="action" value="index">{fl}</form>')
    # pager
    last = max(0, (total - 1) // PAGE_SIZE * PAGE_SIZE)
    sortkv = {"orderBy": ob, "sortOrder": so}

    def pl(lbl, off, ok):
        if not ok:
            return f'<span class="dis">{lbl}</span>'
        return f'<a href="{e(base + "&" + urllib.parse.urlencode({**sortkv, "offset": off}))}">{lbl}</a>'
    shown = f"({offset + 1 if total else 0} - {min(offset + PAGE_SIZE, total)} of {total})"
    pager = (f'<div class="pag">{pl("&laquo;", 0, offset > 0)}{pl("&lsaquo;", max(0, offset - PAGE_SIZE), offset > 0)}'
             f'<span>{shown}</span>{pl("&rsaquo;", offset + PAGE_SIZE, offset + PAGE_SIZE < total)}'
             f'{pl("&raquo;", last, offset + PAGE_SIZE < total)}</div>')
    mass = not md["readonly"]
    acts = ""
    if mass:
        acts = ('<div class="btns"><button class="btn sm sec" name="do" value="export" formaction="'
                + e(url(module, "Export")) + '">Export</button>'
                '<button class="btn sm sec" name="do" value="delete" formaction="' + e(url(module, "MassUpdate"))
                + '" onclick="return confirm(\'Are you sure you want to delete the selected records?\')">Delete</button></div>')
    else:
        acts = "<div></div>"
    table = list_table(module, rows, md["list"], rel, mass=mass, sort=(ob, so), base=base)
    create = ("" if md["readonly"] else
              f'<a class="btn" href="{e(url(module, "EditView"))}">+ Create {e(md["single"])}</a>')
    body = (msg_box() + f'<div class="card">{filt}<form method="post">'
            f'<div class="lvbar">{acts}{pager}</div>{table}<div class="lvbar"><div></div>{pager}</div></form></div>')
    title = md["label"]
    return html(layout(ctx, title, body, module, sub=f"{total} records")
                .replace("</h1></div>", f"</h1>{create}</div>", 1))


# --------------------------------------------------------------- detail view
def fetch(module, record):
    md = MODULES[module]
    r = q1(f"SELECT t.* FROM {md['table']} t WHERE t.id=%s AND t.deleted=0", (record,))
    if r:
        with_display(module, [r])
    return r


def track(ctx, module, rec):
    try:
        ex("INSERT INTO tracker (user_id,module_name,item_id,item_summary,date_modified) VALUES (%s,%s,%s,%s,%s)",
           (ctx["me"].get("id"), module, rec["id"], (rec.get("_display") or "")[:250], now()))
    except Exception:
        pass


def not_found(ctx, module):
    return page(ctx, MODULES.get(module, {}).get("label", module),
                '<div class="msg err">Record not found or it has been deleted.</div>'
                f'<a class="btn sec" href="{e(url(module, "index"))}">Back to list</a>', module)


def panels_html(module, rec, rel):
    md = MODULES[module]
    out = ""
    for title, names in md["panels"]:
        items = ""
        for n in names:
            f = md["f"][n]
            wide = " wide" if f["type"] == "text" else ""
            items += (f'<div class="it{wide}"><div class="lb">{e(f["label"])}:</div>'
                      f'<div class="vl">{render_value(module, f, rec, rel, link=False)}</div></div>')
        out += f'<div class="card"><div class="hd">{e(title)}</div><div class="bd"><div class="dgrid">{items}</div></div></div>'
    return out


def subpanel(ctx, child, fk, parent_mod, rec):
    md = MODULES[child]
    total = q1(f"SELECT COUNT(*) n FROM {md['table']} t WHERE t.deleted=0 AND t.{fk}=%s", (rec["id"],))["n"]
    ob, so = md["sort"]
    rows = q(f"SELECT t.* FROM {md['table']} t WHERE t.deleted=0 AND t.{fk}=%s ORDER BY t.{ob} {so} LIMIT 10",
             (rec["id"],))
    with_display(child, rows)
    cols = [c for c in md["list"] if c != fk][:6]
    rel = resolve(child, rows, cols)
    links = f'<a href="{e(url(child, "EditView", **{fk: rec["id"]}))}">+ Create</a>'
    if total > 10:
        links += f' &nbsp;<a href="{e(url(child, "index", **{"f_" + fk: rec["id"]}))}">View all ({total})</a>'
    return (f'<div class="card"><div class="hd"><span>{e(md["label"])} ({total})</span><span>{links}</span></div>'
            f'{list_table(child, rows, cols, rel)}</div>')


def detail_view(ctx, module):
    md = MODULES[module]
    record = request.args.get("record", "")
    rec = fetch(module, record)
    if not rec:
        return not_found(ctx, module)
    track(ctx, module, rec)
    names = [n for _, ns in md["panels"] for n in ns]
    rel = resolve(module, [rec], names)
    btns = ""
    if not md["readonly"]:
        btns = (f'<a class="btn" href="{e(url(module, "EditView", record=rec["id"]))}">Edit</a>'
                f'<a class="btn sec" href="{e(url(module, "EditView", record=rec["id"], isDuplicate="true"))}">Duplicate</a>')
        if module == "Documents":
            btns += f'<a class="btn sec" href="{e("/index.php?entryPoint=download&type=Documents&id=" + rec["id"])}">Download</a>'
        if module == "ATB_PurchaseOrders":
            btns += (f'<a class="btn sec" href="{e(url("AOS_Invoices", "EditView", po_id=rec["id"], account_id=rec.get("account_id"), total_net=rec.get("total_net"), total_vat=rec.get("total_vat"), total_amount=rec.get("total_amount")))}">'
                     "Create Invoice</a>")
        btns += (f'<form method="post" action="{e(url(module, "Delete", record=rec["id"]))}" '
                 f'data-confirm="Are you sure you want to delete this record?" style="display:inline">'
                 f'<button class="btn sec" type="submit">Delete</button></form>')
    body = msg_box() + f'<div class="btns" style="margin-bottom:16px">{btns}</div>' + panels_html(module, rec, rel)
    if md["lines"] == "po":
        body += po_lines_html(rec)
    elif md["lines"] == "pl":
        body += pl_lines_html(rec)
    if module == "AOS_Products":
        body += product_history_html(rec)
    if module == "Employees":
        body += subpanel_assigned(ctx, rec)
    for child, fk in md["subpanels"]:
        body += subpanel(ctx, child, fk, module, rec)
    crumb = f'<a href="{e(url(module, "index"))}">{e(md["label"])}</a> &rsaquo; {e(rec.get("_display"))}'
    return page(ctx, f'{md["single"]}: {rec.get("_display") or ""}', body, module, crumb=crumb)


def subpanel_assigned(ctx, rec):
    out = ""
    for child in ("Cases", "ATB_PurchaseOrders"):
        md = MODULES[child]
        rows = q(f"SELECT t.* FROM {md['table']} t WHERE t.deleted=0 AND t.assigned_user_id=%s "
                 f"ORDER BY t.date_entered DESC LIMIT 8", (rec["id"],))
        with_display(child, rows)
        cols = [c for c in md["list"] if c != "assigned_user_id"][:5]
        out += (f'<div class="card"><div class="hd">Assigned {e(md["label"])}</div>'
                f'{list_table(child, rows, cols, resolve(child, rows, cols))}</div>')
    return out


# ------------------------------------------------------------- line items
def recalc_po(po_id):
    ex("UPDATE atb_purchaseorders p SET "
       "total_net=(SELECT COALESCE(SUM(line_net),0) FROM atb_po_lines WHERE po_id=p.id AND deleted=0),"
       "total_vat=(SELECT COALESCE(ROUND(SUM(line_net*vat_rate/100),2),0) FROM atb_po_lines WHERE po_id=p.id AND deleted=0),"
       "total_amount=total_net+total_vat, date_modified=%s WHERE id=%s", (now(), po_id))


def recalc_pl(pl_id):
    ex("UPDATE atb_pricelists p SET avg_change=(SELECT COALESCE(ROUND(AVG((price_new-price_old)/price_old*100),2),0) "
       "FROM atb_pricelist_items WHERE pricelist_id=p.id AND deleted=0 AND price_old>0), date_modified=%s WHERE id=%s",
       (now(), pl_id))


def _product_select(account_id, name="product_id"):
    where, params = ("AND t.account_id=%s", (account_id,)) if account_id else ("", ())
    rows = q(f"SELECT t.id, t.name, t.part_number, t.price, t.unit FROM aos_products t WHERE t.deleted=0 {where} "
             f"ORDER BY t.name LIMIT 500", params)
    opts = "".join(f'<option value="{e(r["id"])}">{e(r["part_number"])} — {e(r["name"])} '
                   f'({fmt_money(r["price"])}/{e(r["unit"])})</option>' for r in rows)
    return f'<select class="in" name="{name}" required>{opts}</select>'


def po_lines_html(rec):
    rows = q("SELECT l.*, p.name pname, p.part_number, p.unit, p.ean FROM atb_po_lines l "
             "LEFT JOIN aos_products p ON p.id=l.product_id WHERE l.po_id=%s AND l.deleted=0 "
             "ORDER BY l.date_entered, p.name", (rec["id"],))
    trs = ""
    for i, r in enumerate(rows, 1):
        net = float(r["line_net"] or 0)
        vat = round(net * float(r["vat_rate"] or 0) / 100, 2)
        trs += (f'<tr><td>{i}</td><td>{e(r["part_number"])}</td>'
                f'<td><a href="{e(url("AOS_Products", "DetailView", record=r["product_id"]))}">{e(r["pname"])}</a>'
                f'<div style="color:#8a9199;font-size:11px">EAN {e(r["ean"] or "—")}</div></td>'
                f'<td class="num">{float(r["qty"]):g} {e(r["unit"])}</td><td class="num">{fmt_money(r["unit_price"])}</td>'
                f'<td class="num">{float(r["vat_rate"]):g}%</td><td class="num">{fmt_money(net)}</td>'
                f'<td class="num">{fmt_money(net + vat)}</td>'
                f'<td><form method="post" action="{e(url("ATB_PurchaseOrders", "RemoveLine", record=rec["id"]))}" '
                f'data-confirm="Remove this line?"><input type="hidden" name="line_id" value="{e(r["id"])}">'
                f'<button class="btn sm sec" title="Remove">&times;</button></form></td></tr>')
    if not rows:
        trs = '<tr><td colspan="9" class="empty">No line items</td></tr>'
    foot = (f'<tfoot><tr><td colspan="6" class="num">Total</td><td class="num">{fmt_money(rec["total_net"])}</td>'
            f'<td class="num">{fmt_money(rec["total_amount"])}</td><td></td></tr></tfoot>')
    add = (f'<form class="filter" method="post" action="{e(url("ATB_PurchaseOrders", "AddLine", record=rec["id"]))}">'
           f'<div class="fi q"><label class="fl">Product</label>{_product_select(rec.get("account_id"))}</div>'
           f'<div class="fi" style="flex:0 1 110px"><label class="fl">Quantity</label><input class="in" type="number" step="0.001" min="0.001" name="qty" value="1" required></div>'
           f'<div class="fi" style="flex:0 1 140px"><label class="fl">Unit price (blank = list)</label><input class="in" type="number" step="0.01" min="0" name="unit_price"></div>'
           f'<div class="btns"><button class="btn" type="submit">Add line</button></div></form>')
    return (f'<div class="card"><div class="hd">Line items ({len(rows)})</div><div class="tw"><table class="list">'
            f'<thead><tr><th>#</th><th>SKU</th><th>Product</th><th class="num">Qty</th><th class="num">Unit price</th>'
            f'<th class="num">VAT</th><th class="num">Net</th><th class="num">Gross</th><th></th></tr></thead>'
            f'<tbody>{trs}</tbody>{foot}</table></div>{add}</div>')


def pl_lines_html(rec):
    rows = q("SELECT i.*, p.name pname, p.part_number, p.unit FROM atb_pricelist_items i "
             "LEFT JOIN aos_products p ON p.id=i.product_id WHERE i.pricelist_id=%s AND i.deleted=0 "
             "ORDER BY p.name", (rec["id"],))
    trs = ""
    for r in rows:
        old, new = float(r["price_old"] or 0), float(r["price_new"] or 0)
        ch = (new - old) / old * 100 if old else 0
        col = "#b03a2e" if ch > 5 else ("#1e7b3a" if ch < 0 else "#4a525a")
        trs += (f'<tr><td>{e(r["part_number"])}</td>'
                f'<td><a href="{e(url("AOS_Products", "DetailView", record=r["product_id"]))}">{e(r["pname"])}</a></td>'
                f'<td>{e(r["unit"])}</td><td class="num">{fmt_money(old)}</td><td class="num">{fmt_money(new)}</td>'
                f'<td class="num" style="color:{col};font-weight:600">{ch:+.2f}%</td>'
                f'<td><form method="post" action="{e(url("ATB_PriceLists", "RemoveLine", record=rec["id"]))}" '
                f'data-confirm="Remove this item?"><input type="hidden" name="line_id" value="{e(r["id"])}">'
                f'<button class="btn sm sec">&times;</button></form></td></tr>')
    if not rows:
        trs = '<tr><td colspan="7" class="empty">No items</td></tr>'
    add = (f'<form class="filter" method="post" action="{e(url("ATB_PriceLists", "AddLine", record=rec["id"]))}">'
           f'<div class="fi q"><label class="fl">Product</label>{_product_select(rec.get("account_id"))}</div>'
           f'<div class="fi" style="flex:0 1 160px"><label class="fl">New price (excl. VAT)</label>'
           f'<input class="in" type="number" step="0.01" min="0" name="price_new" required></div>'
           f'<div class="btns"><button class="btn" type="submit">Add item</button></div></form>')
    return (f'<div class="card"><div class="hd">Price list items ({len(rows)})</div><div class="tw"><table class="list">'
            f'<thead><tr><th>SKU</th><th>Product</th><th>Unit</th><th class="num">Current price</th>'
            f'<th class="num">New price</th><th class="num">Change</th><th></th></tr></thead><tbody>{trs}</tbody></table></div>'
            f'{add}</div>')


def product_history_html(rec):
    rows = q("SELECT i.price_old, i.price_new, pl.id, pl.plist_number, pl.status, pl.valid_from FROM atb_pricelist_items i "
             "JOIN atb_pricelists pl ON pl.id=i.pricelist_id AND pl.deleted=0 WHERE i.product_id=%s AND i.deleted=0 "
             "ORDER BY pl.valid_from DESC", (rec["id"],))
    trs = "".join(
        f'<tr><td><a href="{e(url("ATB_PriceLists", "DetailView", record=r["id"]))}">{e(r["plist_number"])}</a></td>'
        f'<td>{fmt_date(r["valid_from"])}</td><td>{render_value("ATB_PriceLists", MODULES["ATB_PriceLists"]["f"]["status"], r, {})}</td>'
        f'<td class="num">{fmt_money(r["price_old"])}</td><td class="num">{fmt_money(r["price_new"])}</td></tr>'
        for r in rows) or '<tr><td colspan="5" class="empty">No price changes</td></tr>'
    po = q("SELECT p.id, p.name, p.order_date, p.status, l.qty, l.unit_price FROM atb_po_lines l "
           "JOIN atb_purchaseorders p ON p.id=l.po_id AND p.deleted=0 WHERE l.product_id=%s AND l.deleted=0 "
           "ORDER BY p.order_date DESC LIMIT 10", (rec["id"],))
    trs2 = "".join(
        f'<tr><td><a href="{e(url("ATB_PurchaseOrders", "DetailView", record=r["id"]))}">{e(r["name"])}</a></td>'
        f'<td>{fmt_date(r["order_date"])}</td><td>{render_value("ATB_PurchaseOrders", MODULES["ATB_PurchaseOrders"]["f"]["status"], r, {})}</td>'
        f'<td class="num">{float(r["qty"]):g}</td><td class="num">{fmt_money(r["unit_price"])}</td></tr>'
        for r in po) or '<tr><td colspan="5" class="empty">No orders</td></tr>'
    return (f'<div class="card"><div class="hd">Price history</div><div class="tw"><table class="list"><thead><tr>'
            f'<th>Price list</th><th>Valid from</th><th>Status</th><th class="num">Old price</th><th class="num">New price</th>'
            f'</tr></thead><tbody>{trs}</tbody></table></div></div>'
            f'<div class="card"><div class="hd">Recent purchase orders</div><div class="tw"><table class="list"><thead><tr>'
            f'<th>PO</th><th>Order date</th><th>Status</th><th class="num">Qty</th><th class="num">Unit price</th>'
            f'</tr></thead><tbody>{trs2}</tbody></table></div></div>')


def _num(v, default=None):
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return default


def add_line(ctx, module):
    record = request.args.get("record", "")
    rec = fetch(module, record)
    if not rec or request.method != "POST":
        return redirect(url(module, "DetailView", record=record))
    pid = request.form.get("product_id", "")
    prod = q1("SELECT * FROM aos_products WHERE id=%s AND deleted=0", (pid,))
    if not prod:
        return redirect(url(module, "DetailView", record=record))
    if module == "ATB_PurchaseOrders":
        qty = _num(request.form.get("qty"), 1) or 1
        price = _num(request.form.get("unit_price"))
        price = float(prod["price"] or 0) if price is None else price
        ex("INSERT INTO atb_po_lines (id,po_id,product_id,qty,unit_price,vat_rate,line_net,date_entered,deleted) "
           "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0)",
           (str(uuid.uuid4()), record, pid, qty, price, _num(prod["vat_rate"], 20), round(qty * price, 2), now()))
        recalc_po(record)
    elif module == "ATB_PriceLists":
        new = _num(request.form.get("price_new"))
        if new is None:
            return redirect(url(module, "DetailView", record=record))
        ex("INSERT INTO atb_pricelist_items (id,pricelist_id,product_id,price_old,price_new,date_entered,deleted) "
           "VALUES (%s,%s,%s,%s,%s,%s,0)", (str(uuid.uuid4()), record, pid, prod["price"], new, now()))
        recalc_pl(record)
    atblog.log("supplier.record_update", ctx["ip"], user=ctx["user"], module=module, record=record,
               change="line_added", product=prod["part_number"])
    return redirect(url(module, "DetailView", record=record, msg="line_added"))


def remove_line(ctx, module):
    record = request.args.get("record", "")
    lid = request.form.get("line_id", "")
    if request.method == "POST":
        if module == "ATB_PurchaseOrders":
            ex("UPDATE atb_po_lines SET deleted=1 WHERE id=%s AND po_id=%s", (lid, record))
            recalc_po(record)
        elif module == "ATB_PriceLists":
            ex("UPDATE atb_pricelist_items SET deleted=1 WHERE id=%s AND pricelist_id=%s", (lid, record))
            recalc_pl(record)
        atblog.log("supplier.record_update", ctx["ip"], user=ctx["user"], module=module, record=record,
                   change="line_removed")
    return redirect(url(module, "DetailView", record=record, msg="line_removed"))


# ---------------------------------------------------------------- edit view
def _input(module, f, val):
    n, t = f["name"], f["type"]
    v = "" if val is None else val
    req = " required" if f["req"] else ""
    if t == "text":
        return f'<textarea class="in" name="{n}">{e(v)}</textarea>'
    if t == "enum":
        opts = f["opts"] if v in f["opts"] or v == "" else f["opts"] + [v]
        return (f'<select class="in" name="{n}">' + "".join(
            f'<option value="{e(o)}"{" selected" if str(o) == str(v) else ""}>{e(o) or "&nbsp;"}</option>' for o in opts)
            + "</select>")
    if t == "relate":
        return (f'<select class="in" name="{n}"><option value=""></option>'
                f'{_rel_options(f["rel"], v)}</select>')
    if t == "user":
        users = q("SELECT id, user_name, first_name, last_name FROM users WHERE deleted=0 AND status='Active' "
                  "AND (user_type='Staff' OR id=%s OR id=%s) ORDER BY last_name", (v, request.environ.get("atb.me", "")))
        return (f'<select class="in" name="{n}"><option value=""></option>' + "".join(
            f'<option value="{e(u["id"])}"{" selected" if u["id"] == v else ""}>{e(full_name(u))}</option>' for u in users)
            + "</select>")
    if t == "date":
        return f'<input class="in" type="date" name="{n}" value="{e(v.isoformat() if hasattr(v, "isoformat") else v)}"{req}>'
    if t == "datetime":
        s = v.strftime("%Y-%m-%dT%H:%M") if hasattr(v, "strftime") else str(v).replace(" ", "T")[:16]
        return f'<input class="in" type="datetime-local" name="{n}" value="{e(s)}"{req}>'
    if t in ("currency", "float"):
        return f'<input class="in" type="number" step="0.01" name="{n}" value="{e(v)}"{req}>'
    if t == "int":
        return f'<input class="in" type="number" step="1" name="{n}" value="{e(v)}"{req}>'
    if t == "bool":
        return (f'<label class="chk"><input type="checkbox" name="{n}" value="1"'
                f'{" checked" if str(v) in ("1", "True") else ""}> Yes</label>')
    typ = {"email": "email", "phone": "tel"}.get(t, "text")
    return f'<input class="in" type="{typ}" name="{n}" value="{e(v)}"{req} maxlength="190">'


def edit_view(ctx, module, rec=None, error=""):
    md = MODULES[module]
    if md["readonly"]:
        return redirect(url(module, "index"))
    record = request.args.get("record", "")
    dup = request.args.get("isDuplicate") == "true"
    if rec is None:
        rec = {}
        if record:
            rec = fetch(module, record)
            if not rec:
                return not_found(ctx, module)
        else:
            rec = {k: v for k, v in request.args.items() if k in md["f"]}
            rec.setdefault("assigned_user_id", ctx["me"].get("id"))
            if module == "ATB_PurchaseOrders":
                nxt = q1("SELECT COUNT(*) n FROM atb_purchaseorders")["n"]
                rec.setdefault("name", f"PO-{now().year}-{6100 + nxt:06d}")
                rec.setdefault("status", "Draft")
                rec.setdefault("order_date", dt.date.today())
            if module == "ATB_PriceLists":
                nxt = q1("SELECT COUNT(*) n FROM atb_pricelists")["n"]
                rec.setdefault("plist_number", f"PL-{now().year}-{1100 + nxt:04d}")
                rec.setdefault("status", "Draft")
                rec.setdefault("currency", "UAH")
            if module == "Cases":
                rec.setdefault("status", "New")
                rec.setdefault("priority", "Medium")
    request.environ["atb.me"] = ctx["me"].get("id")
    sections = ""
    for title, names in md["panels"]:
        cells = ""
        for n in names:
            f = md["f"][n]
            if f["ro"]:
                continue
            wide = ' class="wide"' if f["type"] == "text" else ""
            star = ' <span class="req">*</span>' if f["req"] else ""
            cells += f'<div{wide}><label class="fl">{e(f["label"])}{star}</label>{_input(module, f, rec.get(n))}</div>'
        if module == "Documents" and title == "Document":
            cur = f' (current: {e(rec.get("filename"))})' if rec.get("filename") and not dup else ""
            cells = (f'<div class="wide"><label class="fl">File{cur}</label>'
                     f'<input class="in" type="file" name="uploadfile"></div>') + cells
        if cells:
            sections += f'<div class="card"><div class="hd">{e(title)}</div><div class="bd"><div class="fgrid">{cells}</div></div></div>'
    rid = "" if dup else (rec.get("id") or "")
    err = f'<div class="msg err">{e(error)}</div>' if error else ""
    cancel = url(module, "DetailView", record=rid) if rid else url(module, "index")
    enc = ' enctype="multipart/form-data"' if module == "Documents" else ""
    body = (f'{err}<form method="post" action="{e(url(module, "Save"))}"{enc}>'
            f'<input type="hidden" name="record" value="{e(rid)}">'
            f'<div class="btns" style="margin-bottom:16px"><button class="btn" type="submit">Save</button>'
            f'<a class="btn sec" href="{e(cancel)}">Cancel</a></div>{sections}'
            f'<div class="btns"><button class="btn" type="submit">Save</button>'
            f'<a class="btn sec" href="{e(cancel)}">Cancel</a></div></form>')
    title = f'{md["single"]}: {rec.get("_display") or ""}' if rid else f'Create {md["single"]}'
    return page(ctx, title, body, module,
                crumb=f'<a href="{e(url(module, "index"))}">{e(md["label"])}</a> &rsaquo; {"Edit" if rid else "Create"}')


def _parse(f, raw):
    t = f["type"]
    raw = (raw or "").strip()
    if t == "bool":
        return 1 if raw in ("1", "on", "yes", "true", "Yes", "True") else 0
    if raw == "":
        return None if t in ("date", "datetime", "currency", "float", "int", "relate", "user") else ""
    if t in ("currency", "float"):
        v = _num(raw)
        if v is None:
            raise ValueError(f"{f['label']}: invalid number")
        return round(v, 2)
    if t == "int":
        v = _num(raw)
        if v is None:
            raise ValueError(f"{f['label']}: invalid number")
        return int(v)
    if t == "date":
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return dt.datetime.strptime(raw, fmt).date()
            except ValueError:
                pass
        raise ValueError(f"{f['label']}: invalid date")
    if t == "datetime":
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d", "%d.%m.%Y"):
            try:
                return dt.datetime.strptime(raw, fmt)
            except ValueError:
                pass
        raise ValueError(f"{f['label']}: invalid date/time")
    if t == "text":
        return raw[:20000]
    return raw[:190]


def save_record(ctx, module):
    md = MODULES[module]
    if md["readonly"] or request.method != "POST":
        return redirect(url(module, "index"))
    form = request.form
    record = form.get("record", "")
    old = fetch(module, record) if record else None
    if record and not old:
        return not_found(ctx, module)
    vals, err = {}, ""
    for f in md["fields"]:
        if f["ro"]:
            continue
        if f["type"] != "bool" and f["name"] not in form:
            continue
        try:
            vals[f["name"]] = _parse(f, form.get(f["name"]))
        except ValueError as ex_:
            err = str(ex_)
        if f["req"] and not vals.get(f["name"]):
            err = f'Missing required field: {f["label"]}'
    if err:
        rec = dict(old or {})
        rec.update({k: form.get(k) for k in form})
        rec["id"] = record
        return edit_view(ctx, module, rec, err)
    ts = now()
    vals["date_modified"] = ts
    vals["modified_user_id"] = ctx["me"].get("id")
    up = request.files.get("uploadfile") if module == "Documents" else None
    if record:
        sets = ",".join(f"`{k}`=%s" for k in vals)
        ex(f"UPDATE {md['table']} SET {sets} WHERE id=%s", list(vals.values()) + [record])
        ev = "supplier.record_update"
    else:
        record = str(uuid.uuid4())
        vals.update({"id": record, "date_entered": ts, "created_by": ctx["me"].get("id"), "deleted": 0})
        cols = ",".join(f"`{k}`" for k in vals)
        ex(f"INSERT INTO {md['table']} ({cols}) VALUES ({','.join(['%s'] * len(vals))})", list(vals.values()))
        ev = "supplier.record_create"
    if up and up.filename:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        dest = os.path.join(UPLOAD_DIR, record)        # SuiteCRM stores upload://<document id>
        up.save(dest)
        ex("UPDATE documents SET filename=%s, file_mime_type=%s, file_size=%s WHERE id=%s",
           (os.path.basename(up.filename)[:190], (up.mimetype or "application/octet-stream")[:100],
            os.path.getsize(dest), record))
        atblog.log("supplier.document_upload", ctx["ip"], user=ctx["user"], record=record,
                   filename=os.path.basename(up.filename), size=os.path.getsize(dest))
    if module == "ATB_PriceLists" and vals.get("status") == "Approved" and (not old or old.get("status") != "Approved"):
        ex("UPDATE aos_products p JOIN atb_pricelist_items i ON i.product_id=p.id AND i.deleted=0 "
           "SET p.price=i.price_new, p.date_modified=%s WHERE i.pricelist_id=%s", (ts, record))
        ex("UPDATE atb_pricelists SET reviewer_id=%s WHERE id=%s", (ctx["me"].get("id"), record))
        atblog.log("supplier.pricelist_approved", ctx["ip"], user=ctx["user"], record=record)
    if module == "ATB_PurchaseOrders":
        recalc_po(record)
    atblog.log(ev, ctx["ip"], user=ctx["user"], module=module, record=record)
    return redirect(url(module, "DetailView", record=record, msg="saved"))


def delete_record(ctx, module):
    md = MODULES[module]
    record = request.args.get("record", "") or request.form.get("record", "")
    if md["readonly"] or request.method != "POST":
        return redirect(url(module, "DetailView", record=record))
    ex(f"UPDATE {md['table']} SET deleted=1, date_modified=%s, modified_user_id=%s WHERE id=%s",
       (now(), ctx["me"].get("id"), record))
    atblog.log("supplier.record_delete", ctx["ip"], user=ctx["user"], module=module, record=record)
    return redirect(url(module, "index", msg="deleted"))


def mass_update(ctx, module):
    md = MODULES[module]
    ids = request.form.getlist("mass")
    if md["readonly"] or request.method != "POST":
        return redirect(url(module, "index"))
    if not ids:
        return redirect(url(module, "index", msg="nothing"))
    ex(f"UPDATE {md['table']} SET deleted=1, date_modified=%s WHERE id IN ({','.join(['%s'] * len(ids))})",
       [now()] + ids)
    atblog.log("supplier.record_delete", ctx["ip"], user=ctx["user"], module=module, count=len(ids))
    return redirect(url(module, "index", msg="mass_deleted"))


def export_records(ctx, module):
    md = MODULES[module]
    ids = request.form.getlist("mass")
    if ids:
        rows = q(f"SELECT t.* FROM {md['table']} t WHERE t.deleted=0 AND t.id IN ({','.join(['%s'] * len(ids))})", ids)
    else:
        where, params = _list_query(module, request.args, ctx)
        rows = q(f"SELECT t.* FROM {md['table']} t WHERE {where} LIMIT 5000", params)
    fields = [f for f in md["fields"] if f["type"] != "file" or True]
    rel = resolve(module, rows, [f["name"] for f in fields])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id"] + [f["label"] for f in fields])
    for r in rows:
        line = [r["id"]]
        for f in fields:
            v = r.get(f["name"])
            if f["type"] in ("relate", "user"):
                v = rel.get(f["name"], {}).get(v, "")
            line.append("" if v is None else (fmt_date(v) if isinstance(v, (dt.date, dt.datetime)) else v))
        w.writerow(line)
    atblog.log("supplier.export", ctx["ip"], user=ctx["user"], module=module, rows=len(rows))
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{module}.csv"'})


# ------------------------------------------------------------------- home
def home(ctx):
    me = ctx["me"]
    k = q1("SELECT "
           "(SELECT COUNT(*) FROM atb_purchaseorders WHERE deleted=0 AND status IN ('Sent','Confirmed','Shipped')) open_po,"
           "(SELECT COALESCE(SUM(total_amount),0) FROM atb_purchaseorders WHERE deleted=0 AND status IN ('Sent','Confirmed','Shipped')) open_po_amt,"
           "(SELECT COUNT(*) FROM aos_invoices WHERE deleted=0 AND status IN ('Unpaid','Overdue','Partially Paid','Disputed')) inv_open,"
           "(SELECT COALESCE(SUM(total_amount-amount_paid),0) FROM aos_invoices WHERE deleted=0 AND status IN ('Unpaid','Overdue','Partially Paid','Disputed')) inv_amt,"
           "(SELECT COUNT(*) FROM cases WHERE deleted=0 AND status IN ('New','Assigned','Pending Input')) cases_open,"
           "(SELECT COUNT(*) FROM cases WHERE deleted=0 AND status IN ('New','Assigned','Pending Input') AND priority='High') cases_high,"
           "(SELECT COUNT(*) FROM atb_pricelists WHERE deleted=0 AND status IN ('Submitted','Under Review')) pl_pending,"
           "(SELECT COUNT(*) FROM aos_products WHERE deleted=0 AND status='Active') sku")
    kpis = (f'<div class="kpis">'
            f'<div class="kpi"><div class="l">Open purchase orders</div><div class="v">{k["open_po"]}</div><div class="s">{fmt_money(k["open_po_amt"])} incl. VAT</div></div>'
            f'<div class="kpi"><div class="l">Invoices outstanding</div><div class="v">{k["inv_open"]}</div><div class="s">{fmt_money(k["inv_amt"])} to pay</div></div>'
            f'<div class="kpi"><div class="l">Open cases</div><div class="v">{k["cases_open"]}</div><div class="s">{k["cases_high"]} high priority</div></div>'
            f'<div class="kpi"><div class="l">Price lists in review</div><div class="v">{k["pl_pending"]}</div><div class="s">{k["sku"]} active SKUs</div></div></div>')

    def dashlet(title, module, rows, cols, more):
        with_display(module, rows)
        return (f'<div class="card"><div class="hd"><span>{e(title)}</span><a href="{e(more)}">View all</a></div>'
                f'{list_table(module, rows, cols, resolve(module, rows, cols))}</div>')
    po = q("SELECT * FROM atb_purchaseorders WHERE deleted=0 AND status IN ('Sent','Confirmed','Shipped') "
           "ORDER BY delivery_date LIMIT 7")
    inv = q("SELECT * FROM aos_invoices WHERE deleted=0 AND status IN ('Overdue','Unpaid','Partially Paid','Disputed') "
            "ORDER BY due_date LIMIT 7")
    cs = q("SELECT * FROM cases WHERE deleted=0 AND status IN ('New','Assigned','Pending Input') "
           "ORDER BY FIELD(priority,'High','Medium','Low'), date_entered DESC LIMIT 7")
    calls = q("SELECT * FROM calls WHERE deleted=0 AND status='Planned' ORDER BY date_start LIMIT 6")
    meets = q("SELECT * FROM meetings WHERE deleted=0 AND status='Planned' ORDER BY date_start LIMIT 6")
    pls = q("SELECT * FROM atb_pricelists WHERE deleted=0 ORDER BY date_modified DESC LIMIT 6")
    stage = q("SELECT sales_stage s, COUNT(*) n, COALESCE(SUM(amount),0) a FROM opportunities WHERE deleted=0 "
              "GROUP BY sales_stage")
    sm = {r["s"]: r for r in stage}
    mx = max([float(r["a"]) for r in stage] + [1])
    bars = "".join(
        f'<div class="row"><div class="lab">{e(s)}</div><div class="trk"><div class="fil" style="width:{float(sm[s]["a"]) / mx * 100:.1f}%"></div></div>'
        f'<div class="val">{fmt_money(sm[s]["a"])}</div></div>' for s in STAGES if s in sm)
    months = q("SELECT DATE_FORMAT(order_date,'%%Y-%%m') m, COALESCE(SUM(total_amount),0) a, COUNT(*) n "
               "FROM atb_purchaseorders WHERE deleted=0 AND status<>'Cancelled' GROUP BY m ORDER BY m DESC LIMIT 6")
    mx2 = max([float(r["a"]) for r in months] + [1])
    bars2 = "".join(
        f'<div class="row"><div class="lab">{e(r["m"])} ({r["n"]} PO)</div><div class="trk"><div class="fil" style="width:{float(r["a"]) / mx2 * 100:.1f}%;background:#5b8fc7"></div></div>'
        f'<div class="val">{fmt_money(r["a"])}</div></div>' for r in reversed(months))
    company = ""
    if me.get("portal_account_id"):
        acc = q1("SELECT id, name, account_type FROM accounts WHERE id=%s AND deleted=0", (me["portal_account_id"],))
        if acc:
            company = (f'<div class="msg info">Your company: <a href="{e(url("Accounts", "DetailView", record=acc["id"]))}">'
                       f'{e(acc["name"])}</a> ({e(acc["account_type"])}). New supplier accounts are reviewed by the '
                       f'ATB procurement team.</div>')
    dash = (f'<div class="dash">'
            + dashlet("Purchase orders awaiting delivery", "ATB_PurchaseOrders", po,
                      ["name", "account_id", "status", "delivery_date", "total_amount"], url("ATB_PurchaseOrders", "index"))
            + dashlet("Invoices to be paid", "AOS_Invoices", inv, ["name", "account_id", "due_date", "total_amount", "status"],
                      url("AOS_Invoices", "index"))
            + dashlet("Open cases", "Cases", cs, ["case_number", "name", "priority", "status"], url("Cases", "index"))
            + dashlet("Price list submissions", "ATB_PriceLists", pls, ["plist_number", "account_id", "status", "avg_change"],
                      url("ATB_PriceLists", "index"))
            + dashlet("My upcoming calls", "Calls", calls, ["name", "account_id", "date_start"], url("Calls", "index"))
            + dashlet("My upcoming meetings", "Meetings", meets, ["name", "location", "date_start"], url("Meetings", "index"))
            + f'<div class="card"><div class="hd"><span>Pipeline by sales stage</span><a href="{e(url("Opportunities", "index"))}">View all</a></div><div class="bd bars">{bars}</div></div>'
            + f'<div class="card"><div class="hd"><span>Purchase volume by month</span><a href="{e(url("ATB_PurchaseOrders", "index"))}">View all</a></div><div class="bd bars">{bars2}</div></div>'
            + "</div>")
    return page(ctx, "Suite CRM Dashboard", company + kpis + dash, "Home",
                sub=f"Welcome, {e(full_name(me))}")


# ------------------------------------------------------------ unified search
def unified_search(ctx):
    qs = (request.args.get("query_string") or "").strip()
    body = (f'<div class="card"><form class="filter" method="get" action="/index.php">'
            f'<input type="hidden" name="module" value="Home"><input type="hidden" name="action" value="UnifiedSearch">'
            f'<div class="fi q"><label class="fl">Search all modules</label><input class="in" name="query_string" value="{e(qs)}" autofocus></div>'
            f'<div class="btns"><button class="btn">Search</button></div></form></div>')
    if len(qs) >= 2:
        atblog.log("supplier.search", ctx["ip"], user=ctx["user"], query=qs[:200])
        found = 0
        for module, md in MODULES.items():
            where = " OR ".join(f"t.{c} LIKE %s" for c in md["search"])
            rows = q(f"SELECT t.* FROM {md['table']} t WHERE t.deleted=0 AND ({where}) LIMIT 10",
                     [f"%{qs}%"] * len(md["search"]))
            if not rows:
                continue
            found += len(rows)
            with_display(module, rows)
            cols = md["list"][:5]
            body += (f'<div class="card"><div class="hd"><span>{e(md["label"])} ({len(rows)}{"+" if len(rows) == 10 else ""})</span>'
                     f'<a href="{e(url(module, "index", query_string=qs))}">View in list</a></div>'
                     f'{list_table(module, rows, cols, resolve(module, rows, cols))}</div>')
        if not found:
            body += '<div class="msg info">No results found.</div>'
    return page(ctx, "Search", body, "Home", sub=f'Results for "{e(qs)}"' if qs else None)


# ------------------------------------------------------------ users/profile
def users_module(ctx, action):
    me = ctx["me"]
    if action == "ChangePassword":
        err = ""
        if request.method == "POST":
            old, p1, p2 = (request.form.get(k, "") for k in ("old_password", "new_password", "confirm_password"))
            rec = USERS.get(ctx["user"], {})
            if not password_ok(rec, old):
                err = "The old password is incorrect."
            elif len(p1) < 8:
                err = "The new password must be at least 8 characters long."
            elif p1 != p2:
                err = "The passwords do not match."
            else:
                set_password(ctx["user"], p1)
                atblog.log("supplier.user_password_change", ctx["ip"], user=ctx["user"])
                return redirect(url("Users", "DetailView", record=me.get("id"), msg="pw_changed"))
        body = ((f'<div class="msg err">{e(err)}</div>' if err else "")
                + f'<div class="card" style="max-width:520px"><div class="hd">Change password</div><div class="bd">'
                  f'<form method="post" action="{e(url("Users", "ChangePassword"))}">'
                  f'<label class="fl">Current password</label><input class="in" type="password" name="old_password" required>'
                  f'<label class="fl" style="margin-top:12px">New password</label><input class="in" type="password" name="new_password" required>'
                  f'<label class="fl" style="margin-top:12px">Confirm new password</label><input class="in" type="password" name="confirm_password" required>'
                  f'<div class="btns" style="margin-top:16px"><button class="btn">Save</button>'
                  f'<a class="btn sec" href="{e(url("Users", "DetailView", record=me.get("id")))}">Cancel</a></div></form></div></div>')
        return page(ctx, "Change Password", body, "Users")
    editable = [("first_name", "First Name"), ("last_name", "Last Name"), ("title", "Title"),
                ("department", "Department"), ("email1", "Email Address"), ("phone_work", "Office Phone"),
                ("phone_mobile", "Mobile"), ("address_city", "City")]
    if action == "Save" and request.method == "POST":
        vals = {k: (request.form.get(k) or "").strip()[:100] for k, _ in editable}
        if not vals["last_name"]:
            vals["last_name"] = ctx["user"].split("@")[0]
        ex("UPDATE users SET " + ",".join(f"{k}=%s" for k in vals) + ", date_modified=%s WHERE id=%s",
           list(vals.values()) + [now(), me.get("id")])
        atblog.log("supplier.profile_update", ctx["ip"], user=ctx["user"])
        return redirect(url("Users", "DetailView", record=me.get("id"), msg="profile"))
    if action == "EditView":
        cells = "".join(f'<div><label class="fl">{e(lbl)}</label><input class="in" name="{k}" value="{e(me.get(k))}"></div>'
                        for k, lbl in editable)
        body = (f'<form method="post" action="{e(url("Users", "Save"))}"><div class="card"><div class="hd">User profile</div>'
                f'<div class="bd"><div class="fgrid">{cells}</div></div></div><div class="btns"><button class="btn">Save</button>'
                f'<a class="btn sec" href="{e(url("Users", "DetailView", record=me.get("id")))}">Cancel</a></div></form>')
        return page(ctx, "My Account", body, "Users")
    # DetailView (own profile; other users are viewed through Employees)
    rec = request.args.get("record")
    if rec and rec != me.get("id"):
        return redirect(url("Employees", "DetailView", record=rec))
    acc = (q1("SELECT id,name FROM accounts WHERE id=%s", (me.get("portal_account_id"),))
           if me.get("portal_account_id") else None)
    rows = [("User Name", e(me.get("user_name"))), ("Full name", e(full_name(me)))] + \
           [(lbl, e(me.get(k))) for k, lbl in editable[2:]] + [
           ("User Type", e(me.get("user_type") or "Supplier")), ("Status", e(me.get("status") or "Active")),
           ("Company", f'<a href="{e(url("Accounts", "DetailView", record=acc["id"]))}">{e(acc["name"])}</a>' if acc else ""),
           ("Last login", fmt_date(me.get("last_login"))), ("Date Created", fmt_date(me.get("date_entered")))]
    items = "".join(f'<div class="it"><div class="lb">{lbl}:</div><div class="vl">{v}</div></div>' for lbl, v in rows)
    prefs = ('<div class="card"><div class="hd">Advanced</div><div class="bd"><div class="dgrid">'
             '<div class="it"><div class="lb">Date format:</div><div class="vl">dd.mm.yyyy</div></div>'
             '<div class="it"><div class="lb">Time zone:</div><div class="vl">Europe/Kyiv (UTC+03:00)</div></div>'
             '<div class="it"><div class="lb">Currency:</div><div class="vl">Hryvnia (₴)</div></div>'
             '<div class="it"><div class="lb">Language:</div><div class="vl">English (US)</div></div>'
             '</div></div></div>')
    body = (msg_box() + f'<div class="btns" style="margin-bottom:16px"><a class="btn" href="{e(url("Users", "EditView"))}">Edit</a>'
            f'<a class="btn sec" href="{e(url("Users", "ChangePassword"))}">Change Password</a></div>'
            f'<div class="card"><div class="hd">User profile</div><div class="bd"><div class="dgrid">{items}</div></div></div>{prefs}')
    return page(ctx, "My Account", body, "Users", sub=e(me.get("user_name")))


# --------------------------------------------------------------- documents
def _mini_pdf(lines):
    lines = [seed.translit(ln).replace("\u2116", "No.").encode("latin-1", "replace").decode("latin-1") for ln in lines]
    text = "BT /F1 11 Tf 56 780 Td 15 TL " + " ".join(
        "(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") '" for ln in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            f"<< /Length {len(text)} >>\nstream\n{text}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out.encode("latin-1")))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    x = len(out.encode("latin-1"))
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n"
    return out.encode("latin-1", "replace")


def download(user, ip):
    if not DB_READY.is_set():
        return db_error_page()
    did = request.args.get("id", "")
    doc = q1("SELECT * FROM documents WHERE id=%s AND deleted=0", (did,))
    if not doc:
        return html("File not found", 404)
    atblog.log("supplier.document_download", ip, user=user, record=did, filename=doc["filename"])
    fname = doc["filename"] or "document"
    path = os.path.join(UPLOAD_DIR, did)
    disp = {"Content-Disposition": f"attachment; filename=\"{seed.translit(fname).encode('ascii', 'replace').decode()}\""}
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            return Response(fh.read(), mimetype=doc["file_mime_type"] or "application/octet-stream", headers=disp)
    acc = q1("SELECT * FROM accounts WHERE id=%s", (doc["account_id"],)) or {}
    if (doc["file_mime_type"] or "").startswith("text/csv"):
        rows = q("SELECT part_number, supplier_sku, ean, name, unit, price, vat_rate FROM aos_products "
                 "WHERE account_id=%s AND deleted=0 ORDER BY name", (doc["account_id"],))
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["ATB SKU", "Supplier code", "EAN", "Name", "Unit", "Price excl. VAT", "VAT %"])
        for r in rows:
            w.writerow([r["part_number"], r["supplier_sku"], r["ean"], r["name"], r["unit"],
                        f'{float(r["price"]):.2f}'.replace(".", ","), r["vat_rate"]])
        return Response("﻿" + buf.getvalue(), mimetype="text/csv", headers=disp)
    lines = [seed.translit(doc["document_name"] or ""), "",
             f"Supplier: {seed.translit(acc.get('name') or '')}",
             f"EDRPOU: {acc.get('edrpou') or ''}    VAT: {acc.get('vat_number') or ''}",
             f"Address: {seed.translit(acc.get('billing_address_street') or '')}, {seed.translit(acc.get('billing_address_city') or '')}",
             "", "Buyer: TOV \"ATB-market\", EDRPOU 30487219, Dnipro, vul. Urytskoho 40", "",
             f"Category: {doc['category_id']}    Revision: {doc['revision']}",
             f"Valid from: {fmt_date(doc['active_date'])}    Valid to: {fmt_date(doc['exp_date']) or 'indefinite'}", "",
             "This document was signed with a qualified electronic signature (KEP)",
             "and delivered via M.E.Doc electronic document exchange.", "",
             f"Document ID: {doc['id']}"]
    if doc["category_id"] == "Bank Details":
        lines[10:10] = [f"Beneficiary account (IBAN): {acc.get('iban') or ''}",
                        f"Bank: {seed.translit(acc.get('bank_name') or '')}", ""]
    return Response(_mini_pdf(lines), mimetype="application/pdf", headers=disp)


# ------------------------------------------------------------- import wizard
IMPORT_MODULES = [m for m, md in MODULES.items() if md["importable"]]
SYNONYMS = {"sku": "part_number", "atbsku": "part_number", "artikul": "part_number", "артикул": "part_number",
            "barcode": "ean", "ean13": "ean", "штрихкод": "ean", "назва": "name", "найменування": "name",
            "productname": "name", "company": "name", "companyname": "name", "accountname": "account_id",
            "supplier": "account_id", "постачальник": "account_id", "email": "email1", "mail": "email1",
            "phone": "phone_work", "телефон": "phone_work", "city": "billing_address_city", "місто": "billing_address_city",
            "ціна": "price", "цінабезпдв": "price", "price": "price", "unitprice": "price", "edrpou": "edrpou",
            "єдрпоу": "edrpou", "subject": "name", "тема": "name", "contact": "contact_id", "mobile": "phone_mobile",
            "firstname": "first_name", "lastname": "last_name", "ім'я": "first_name", "прізвище": "last_name"}


def _norm(s):
    return re.sub(r"[^0-9a-zа-яіїєґ']", "", (s or "").lower())


def _import_fields(module):
    md = MODULES[module]
    return [f for f in md["fields"] if not f["ro"] and f["type"] not in ("file",)]


def _guess(module, header):
    n = _norm(header)
    fields = _import_fields(module)
    for f in fields:
        if n in (_norm(f["name"]), _norm(f["label"])):
            return f["name"]
    s = SYNONYMS.get(n)
    if s and s in MODULES[module]["f"]:
        return s
    if module == "Contacts" and s == "account_id":
        return "account_id"
    return ""


def _safe_import_path(p):
    rp = os.path.realpath(p or "")
    return rp if rp.startswith(IMPORT_DIR + os.sep) and os.path.isfile(rp) else None


def _read_csv(path, delim, encl, enc, limit=None):
    with open(path, "rb") as fh:
        raw = fh.read(5 * 1024 * 1024)
    text = raw.decode("cp1251" if enc == "cp1251" else "utf-8-sig", "replace")
    d = {"comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|"}.get(delim, ",")
    rdr = csv.reader(io.StringIO(text), delimiter=d, quotechar=encl if encl in ('"', "'") else '"')
    rows = []
    for r in rdr:
        if any(c.strip() for c in r):
            rows.append([c.strip() for c in r])
        if limit and len(rows) >= limit:
            break
    return rows


def _steps(n):
    names = ["1. Upload file", "2. File properties", "3. Field mapping", "4. Confirm", "5. Results"]
    return '<div class="steps">' + "".join(
        f'<div class="{"on" if i + 1 == n else ("done" if i + 1 < n else "")}">{s}</div>' for i, s in enumerate(names)) + "</div>"


def _hidden(**kw):
    return "".join(f'<input type="hidden" name="{e(k)}" value="{e(v)}">' for k, v in kw.items())


def import_wizard(ctx, action):
    form = request.form
    if action in ("Step2",) and request.method == "POST":
        return import_step2(ctx)
    if action == "Step3" and request.method == "POST":
        return import_step3(ctx)
    if action == "Step4" and request.method == "POST":
        return import_step4(ctx)
    if action == "Step5" and request.method == "POST":
        return import_step5(ctx)
    if action == "Undo" and request.method == "POST":
        rows = q("SELECT bean_type, bean_id FROM users_last_import WHERE assigned_user_id=%s AND deleted=0",
                 (ctx["me"].get("id"),))
        for r in rows:
            md = MODULES.get(r["bean_type"])
            if md:
                ex(f"UPDATE {md['table']} SET deleted=1 WHERE id=%s", (r["bean_id"],))
        ex("UPDATE users_last_import SET deleted=1 WHERE assigned_user_id=%s", (ctx["me"].get("id"),))
        atblog.log("supplier.import_undo", ctx["ip"], user=ctx["user"], count=len(rows))
        return redirect(url("Import", "index", msg="undone"))
    return import_step1(ctx)


def import_step1(ctx, error=""):
    mod = request.args.get("import_module", "")
    err = f'<div class="msg err">{e(error)}</div>' if error else ""
    opts = "".join(f'<option value="{m}"{" selected" if m == mod else ""}>{e(MODULES[m]["label"])}</option>'
                   for m in IMPORT_MODULES)
    sample = ("ATB SKU;Supplier code;EAN;Name;Unit;Price excl. VAT;VAT %\n"
              "DAI-118204;DNI-4471;4820000000017;Молоко 2,5% 900 г;pcs;32,40;20")
    body = (msg_box() + err + _steps(1) +
            f'<div class="card"><div class="hd">Upload import file</div><div class="bd">'
            f'<p style="color:#60666c;margin-bottom:12px">Select a comma- or semicolon-separated (.csv) file exported '
            f'from your ERP / 1C / M.E.Doc. The first row should contain column headers. Maximum 2000 records per file.</p>'
            f'<form method="post" enctype="multipart/form-data" action="{e(url("Import", "Step2"))}">'
            f'<div class="fgrid"><div><label class="fl">File <span class="req">*</span></label>'
            f'<input class="in" type="file" name="userfile" accept=".csv,.txt,text/csv" required></div>'
            f'<div><label class="fl">Import into</label><select class="in" name="import_module">{opts}</select></div></div>'
            f'<div class="btns" style="margin-top:16px"><button class="btn" type="submit">Next &rsaquo;</button></div></form>'
            f'<p style="color:#8a9199;font-size:12px;margin:16px 0 6px">Example price list layout:</p><pre class="raw">{e(sample)}</pre>'
            f'</div></div>'
            # saved mapping / attachment refresh (Import::RefreshMapping)
            f'<div class="card"><div class="hd">Saved import mapping</div><div class="bd">'
            f'<p style="color:#60666c;margin-bottom:12px">Re-run the field mapping for a previously uploaded import file, '
            f'or attach a source file to refresh it.</p>'
            f'<form method="post" target="respframe" action="/index.php?module=Import&amp;action=RefreshMapping" '
            f'enctype="multipart/form-data"><div class="fgrid">'
            f'<div><label class="fl">Import file / mapping source</label>'
            f'<input class="in" type="text" name="importFile" placeholder="upload/import/..."></div>'
            f'<div><label class="fl">Attachment</label><input class="in" type="file" name="file"></div></div>'
            f'<div class="btns" style="margin-top:16px"><button class="btn sec" type="submit">Refresh mapping</button></div></form>'
            f'<label class="fl" style="margin-top:16px">Server response</label>'
            f'<iframe class="resp" name="respframe" title="server response"></iframe></div></div>')
    last = q("SELECT import_module, COUNT(*) n, MAX(date_entered) d FROM users_last_import WHERE assigned_user_id=%s "
             "AND deleted=0 GROUP BY import_module", (ctx["me"].get("id"),))
    if last:
        body += (f'<div class="card"><div class="hd">Last import</div><div class="bd">'
                 + "".join(f'<div>{r["n"]} {e(MODULES.get(r["import_module"], {}).get("label", r["import_module"]))} '
                           f'record(s) imported {fmt_date(r["d"])}</div>' for r in last)
                 + f'<form method="post" action="{e(url("Import", "Undo"))}" data-confirm="Delete all records created by your last import?" '
                   f'style="margin-top:12px"><button class="btn sec">Undo Import</button></form></div></div>')
    return page(ctx, "Import", body, "Import", sub="Step 1: Upload import file")


def import_step2(ctx):
    up = request.files.get("userfile")
    mod = request.form.get("import_module", "")
    if not up or not up.filename:
        return import_step1(ctx, "Please select a file to import.")
    os.makedirs(IMPORT_DIR, exist_ok=True)
    stored = os.path.join(IMPORT_DIR, f"{(ctx['me'].get('id') or 'x')[:8]}_{secrets.token_hex(6)}.csv")
    up.save(stored)
    size = os.path.getsize(stored)
    with open(stored, "rb") as fh:
        head = fh.read(65536)
    text = head.decode("utf-8", "replace")
    lines = text.count("\n") + (0 if text.endswith("\n") else 1)
    first = text.splitlines()[0] if text else ""
    guess = max(("comma", "semicolon", "tab", "pipe"),
                key=lambda d: first.count({"comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|"}[d]))
    try:
        head.decode("utf-8")
        enc_guess = "utf-8"
    except UnicodeDecodeError:
        enc_guess = "cp1251"
    atblog.log("supplier.import_upload", ctx["ip"], user=ctx["user"], filename=os.path.basename(up.filename),
               stored=stored, size=size)
    opts = "".join(f'<option value="{m}"{" selected" if m == mod else ""}>{e(MODULES[m]["label"])}</option>'
                   for m in IMPORT_MODULES)

    def radio(name, val, lbl, cur):
        return (f'<label class="chk"><input type="radio" name="{name}" value="{val}"'
                f'{" checked" if val == cur else ""}> {lbl}</label>')
    body = (_steps(2) +
            f'<form method="post" action="{e(url("Import", "Step3"))}">{_hidden(importFile=stored, source_name=os.path.basename(up.filename))}'
            f'<div class="card"><div class="hd">Uploaded file</div><div class="bd"><div class="dgrid">'
            f'<div class="it"><div class="lb">File name:</div><div class="vl">{e(os.path.basename(up.filename))}</div></div>'
            f'<div class="it"><div class="lb">Size:</div><div class="vl">{size:,} bytes</div></div>'
            f'<div class="it"><div class="lb">Lines (approx.):</div><div class="vl">{lines}</div></div>'
            f'<div class="it"><div class="lb">Detected encoding:</div><div class="vl">{e(enc_guess)}</div></div>'
            f'</div><pre class="raw" style="margin-top:12px">{e(chr(10).join(text.splitlines()[:4]))}</pre></div></div>'
            f'<div class="card"><div class="hd">File properties</div><div class="bd"><div class="fgrid">'
            f'<div><label class="fl">Import into module</label><select class="in" name="import_module">{opts}</select></div>'
            f'<div><label class="fl">Character encoding</label><select class="in" name="encoding">'
            f'<option value="utf-8"{" selected" if enc_guess == "utf-8" else ""}>UTF-8</option>'
            f'<option value="cp1251"{" selected" if enc_guess == "cp1251" else ""}>Windows-1251 (Cyrillic)</option></select></div>'
            f'<div><label class="fl">Field delimiter</label><div class="btns">'
            f'{radio("delimiter", "comma", "Comma ( , )", guess)}{radio("delimiter", "semicolon", "Semicolon ( ; )", guess)}'
            f'{radio("delimiter", "tab", "Tab", guess)}{radio("delimiter", "pipe", "Pipe ( | )", guess)}</div></div>'
            f'<div><label class="fl">Field qualifier</label><select class="in" name="enclosure">'
            f'<option value="&quot;">Double quote (&quot;)</option><option value="\'">Single quote (\')</option>'
            f'<option value="">None</option></select></div>'
            f'<div><label class="chk"><input type="checkbox" name="has_header" value="1" checked> First row contains column headers</label></div>'
            f'</div></div></div>'
            f'<div class="btns"><a class="btn sec" href="{e(url("Import", "index"))}">&lsaquo; Back</a>'
            f'<button class="btn">Next &rsaquo;</button></div></form>')
    return page(ctx, "Import", body, "Import", sub="Step 2: Confirm file properties")


def _wiz_state():
    f = request.form
    st = {k: f.get(k, "") for k in ("importFile", "source_name", "import_module", "encoding", "delimiter",
                                    "enclosure", "has_header", "dup_check")}
    if st["import_module"] not in IMPORT_MODULES:
        st["import_module"] = IMPORT_MODULES[0]
    return st


def import_step3(ctx):
    st = _wiz_state()
    path = _safe_import_path(st["importFile"])
    if not path:
        return import_step1(ctx, "The import file could not be found. Please upload it again.")
    rows = _read_csv(path, st["delimiter"], st["enclosure"], st["encoding"], limit=4)
    if not rows:
        return import_step1(ctx, "The file is empty or could not be parsed.")
    module = st["import_module"]
    hdr = rows[0] if st["has_header"] else [f"Column {i + 1}" for i in range(len(rows[0]))]
    samples = rows[1:3] if st["has_header"] else rows[:2]
    ncol = max(len(r) for r in rows)
    fields = _import_fields(module)
    trs = ""
    used = set()
    for i in range(ncol):
        h = hdr[i] if i < len(hdr) else f"Column {i + 1}"
        g = _guess(module, h) if st["has_header"] else ""
        if g in used:
            g = ""
        used.add(g)
        opts = '<option value="">-- Do not map this field --</option>' + "".join(
            f'<option value="{f["name"]}"{" selected" if f["name"] == g else ""}>{e(f["label"])}'
            f'{" *" if f["req"] else ""}</option>' for f in fields)
        s1 = samples[0][i] if samples and i < len(samples[0]) else ""
        s2 = samples[1][i] if len(samples) > 1 and i < len(samples[1]) else ""
        trs += (f'<tr><td><b>{e(h)}</b></td><td><select class="in" name="map_{i}">{opts}</select></td>'
                f'<td>{e(s1)}</td><td>{e(s2)}</td></tr>')
    req = ", ".join(f["label"] for f in fields if f["req"])
    body = (_steps(3) +
            f'<form method="post" action="{e(url("Import", "Step4"))}">{_hidden(**st, ncol=ncol)}'
            f'<div class="card"><div class="hd"><span>Map fields — {e(MODULES[module]["label"])}</span>'
            f'<span style="font-weight:400;text-transform:none">Required: {e(req)}</span></div><div class="tw"><table class="list">'
            f'<thead><tr><th>Header row</th><th style="min-width:220px">{e(MODULES[module]["single"])} field</th>'
            f'<th>Row 1</th><th>Row 2</th></tr></thead><tbody>{trs}</tbody></table></div>'
            f'<div class="bd"><label class="chk"><input type="checkbox" name="dup_check" value="1" checked> '
            f'Skip records whose name already exists (duplicate check)</label></div></div>'
            f'<div class="btns"><a class="btn sec" href="{e(url("Import", "index"))}">&lsaquo; Start over</a>'
            f'<button class="btn">Next &rsaquo;</button></div></form>'
            # live mapping refresh, as on SuiteCRM's Step 3 (AJAX RefreshMapping)
            f'<div class="card" style="margin-top:18px"><div class="hd"><span>Source file preview</span>'
            f'<form method="post" target="mapframe" action="/index.php?module=Import&amp;action=RefreshMapping" style="display:inline">'
            f'<input type="hidden" name="importFile" value="{e(st["importFile"])}">'
            f'<button class="btn sm sec" type="submit">Refresh mapping</button></form></div>'
            f'<div class="bd"><iframe class="resp" name="mapframe" title="mapping preview"></iframe></div></div>')
    return page(ctx, "Import", body, "Import", sub=f"Step 3: Map fields ({e(st['source_name'])})")


def _mapping():
    try:
        ncol = min(200, int(request.form.get("ncol", "0")))
    except ValueError:
        ncol = 0
    return {i: request.form.get(f"map_{i}", "") for i in range(ncol) if request.form.get(f"map_{i}")}


def _build_records(module, st, mapping):
    path = _safe_import_path(st["importFile"])
    if not path:
        return None, None
    rows = _read_csv(path, st["delimiter"], st["enclosure"], st["encoding"], limit=2001)
    if st["has_header"]:
        rows = rows[1:]
    md = MODULES[module]
    recs, errs = [], []
    lookups = {}
    for n, r in enumerate(rows[:2000], 1):
        vals, bad = {}, ""
        for i, fname in mapping.items():
            f = md["f"].get(fname)
            if not f or f["ro"]:
                continue
            raw = r[i] if i < len(r) else ""
            if f["type"] == "relate" and raw:
                key = (f["rel"], raw)
                if key not in lookups:
                    rmd = MODULES[f["rel"]]
                    hit = q1(f"SELECT t.id FROM {rmd['table']} t WHERE t.deleted=0 AND (t.id=%s OR {rmd['name_sql']}=%s) LIMIT 1",
                             (raw, raw))
                    lookups[key] = hit and hit["id"]
                vals[fname] = lookups[key]
                if not lookups[key]:
                    vals["_warn"] = f'{f["label"]} "{raw}" not found'
                continue
            if f["type"] == "enum" and raw:
                m = next((o for o in f["opts"] if o.lower() == raw.lower()), None)
                vals[fname] = m or raw[:50]
                continue
            try:
                vals[fname] = _parse(f, raw)
            except ValueError as ex_:
                bad = str(ex_)
        nf = NAME_FIELD[module]
        if not bad and not vals.get(nf):
            bad = f'Missing required field: {md["f"][nf]["label"]}'
        if bad:
            errs.append((n, bad))
        else:
            recs.append((n, vals))
    return recs, errs


def import_step4(ctx):
    st = _wiz_state()
    module = st["import_module"]
    mapping = _mapping()
    recs, errs = _build_records(module, st, mapping)
    if recs is None:
        return import_step1(ctx, "The import file could not be found. Please upload it again.")
    md = MODULES[module]
    cols = list(dict.fromkeys(mapping.values()))
    trs = ""
    for n, v in recs[:10]:
        tds = "".join(f'<td>{e(fmt_date(v.get(c)) if isinstance(v.get(c), (dt.date, dt.datetime)) else v.get(c))}</td>' for c in cols)
        warn = f' <span class="badge warn">{e(v["_warn"])}</span>' if v.get("_warn") else ""
        trs += f"<tr><td>{n}{warn}</td>{tds}</tr>"
    errhtml = ""
    if errs:
        errhtml = ('<div class="card"><div class="hd">Rows with errors (will be skipped)</div><div class="tw"><table class="list">'
                   '<thead><tr><th>Row</th><th>Error</th></tr></thead><tbody>'
                   + "".join(f"<tr><td>{n}</td><td>{e(m)}</td></tr>" for n, m in errs[:50]) + "</tbody></table></div></div>")
    maps = "".join(f'<input type="hidden" name="map_{i}" value="{e(v)}">' for i, v in mapping.items())
    head = "".join(f"<th>{e(md['f'][c]['label'])}</th>" for c in cols)
    body = (_steps(4) +
            f'<div class="msg info">{len(recs)} record(s) ready to import into {e(md["label"])}'
            f'{f", {len(errs)} row(s) with errors" if errs else ""}.</div>'
            f'<div class="card"><div class="hd">Preview (first 10 records)</div><div class="tw"><table class="list">'
            f'<thead><tr><th>Row</th>{head}</tr></thead><tbody>{trs or "<tr><td class=empty colspan=99>Nothing to import</td></tr>"}</tbody></table></div></div>'
            f'{errhtml}<form method="post" action="{e(url("Import", "Step5"))}">{_hidden(**st, ncol=request.form.get("ncol", "0"))}{maps}'
            f'<div class="btns"><a class="btn sec" href="{e(url("Import", "index"))}">&lsaquo; Start over</a>'
            f'<button class="btn"{" disabled" if not recs else ""}>Import Now</button></div></form>')
    return page(ctx, "Import", body, "Import", sub="Step 4: Confirm import")


def import_step5(ctx):
    st = _wiz_state()
    module = st["import_module"]
    md = MODULES[module]
    recs, errs = _build_records(module, st, _mapping())
    if recs is None:
        return import_step1(ctx, "The import file could not be found. Please upload it again.")
    me_id = ctx["me"].get("id")
    ex("UPDATE users_last_import SET deleted=1 WHERE assigned_user_id=%s", (me_id,))
    created, dups = [], []
    nf = NAME_FIELD[module]
    for n, vals in recs:
        vals.pop("_warn", None)
        if st["dup_check"] and q1(f"SELECT id FROM {md['table']} WHERE deleted=0 AND {nf}=%s LIMIT 1", (vals[nf],)):
            dups.append((n, vals[nf]))
            continue
        rid = str(uuid.uuid4())
        vals.update({"id": rid, "date_entered": now(), "date_modified": now(), "created_by": me_id,
                     "modified_user_id": me_id, "deleted": 0})
        vals.setdefault("assigned_user_id", me_id)
        cols = ",".join(f"`{k}`" for k in vals)
        ex(f"INSERT INTO {md['table']} ({cols}) VALUES ({','.join(['%s'] * len(vals))})", list(vals.values()))
        ex("INSERT INTO users_last_import (id,assigned_user_id,import_module,bean_type,bean_id,date_entered,deleted) "
           "VALUES (%s,%s,%s,%s,%s,%s,0)", (str(uuid.uuid4()), me_id, module, module, rid, now()))
        created.append(rid)
    atblog.log("supplier.import_commit", ctx["ip"], user=ctx["user"], module=module, created=len(created),
               errors=len(errs), duplicates=len(dups), source=st["source_name"])
    rows = q(f"SELECT t.* FROM {md['table']} t WHERE t.id IN ({','.join(['%s'] * len(created))})", created) if created else []
    with_display(module, rows)
    cols = md["list"][:6]
    body = (_steps(5) +
            f'<div class="msg ok">{len(created)} record(s) were created.'
            f'{f" {len(dups)} duplicate(s) skipped." if dups else ""}{f" {len(errs)} row(s) had errors." if errs else ""}</div>'
            f'<div class="card"><div class="hd">Created records</div>{list_table(module, rows[:50], cols, resolve(module, rows, cols))}</div>'
            + ((f'<div class="card"><div class="hd">Skipped</div><div class="tw"><table class="list"><thead><tr><th>Row</th><th>Reason</th></tr></thead><tbody>'
                + "".join(f"<tr><td>{n}</td><td>Duplicate: {e(v)}</td></tr>" for n, v in dups[:50])
                + "".join(f"<tr><td>{n}</td><td>{e(m)}</td></tr>" for n, m in errs[:50])
                + "</tbody></table></div></div>") if (dups or errs) else "")
            + f'<div class="btns"><form method="post" action="{e(url("Import", "Undo"))}" data-confirm="Delete all records created by this import?">'
              f'<button class="btn sec">Undo Import</button></form>'
              f'<a class="btn sec" href="{e(url("Import", "index", import_module=module))}">Import Again</a>'
              f'<a class="btn" href="{e(url(module, "index"))}">View {e(md["label"])}</a></div>')
    return page(ctx, "Import", body, "Import", sub="Step 5: Results")
