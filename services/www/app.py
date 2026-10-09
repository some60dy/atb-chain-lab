"""Step 2 - www.atbmarket.com Yii2 e-shop with a boolean-blind SQL injection.

The catalog filter is passed as filter[<group>][<attr>]=<value>. Yii2 PARAMETRISES
the value, but the array KEY (<attr>) is concatenated straight into the WHERE
clause (classic Yii2 key-injection). So:

    /shop/catalog/novetly?filter[8][490]=1          -> valid SQL   -> 200
    /shop/catalog/novetly?filter[8][490']=1         -> broken SQL  -> 500 (#42000)
    /shop/catalog/novetly?filter[8][490 AND 1=1]=1  -> valid SQL   -> 200

That 200/500 split is a real boolean oracle: any subquery/comparison placed in the
key either keeps the SQL valid (200) or breaks it (500), letting an attacker read
version()/database()/user()/COUNT(*) char-by-char. Backed by the real `ishop`
MySQL, so extraction returns genuine values (users.password = real bcrypt).

Everything else (catalogue listing, search, cart, checkout, customer accounts,
stores, static pages) is a working storefront built on parametrised queries.
"""
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from html import escape
from urllib.parse import urlencode

import bcrypt
import pymysql
import pymysql.cursors
from flask import Flask, request, Response, session, redirect, flash, get_flashed_messages
import atblog

app = Flask(__name__)
app.secret_key = os.environ.get("WWW_SECRET", "yii2-frontend-cookieValidationKey-8f3a1c9e77d24b0a")
app.config.update(SESSION_COOKIE_NAME="advanced-frontend", SESSION_COOKIE_HTTPONLY=True,
                  PERMANENT_SESSION_LIFETIME=timedelta(days=30))

DB = dict(
    host=os.environ.get("ISHOP_DB_HOST", "ishop-db"),
    port=int(os.environ.get("ISHOP_DB_PORT", "3306")),
    user=os.environ.get("ISHOP_DB_USER", "ishop"),
    password=os.environ.get("ISHOP_DB_PASS", "rEQaZ55o7x_E53oC"),
    database=os.environ.get("ISHOP_DB_NAME", "ishop"),
    connect_timeout=5,
    charset="utf8mb4",
)

# crude signal that this request is probing the injection, for detection logging
INJECT_SIGNS = re.compile(r"(select|union|sleep|\bor\b|\band\b|--|#|'|\"|=|<|>|ascii|substr|version|database|\buser\b)", re.I)

PER_PAGE = 12
FREE_DELIVERY_FROM = 1000
DELIVERY_FEE = 49
MIN_COURIER_ORDER = 200


def _conn():
    return pymysql.connect(**DB)


def run_filter(group, attr, value):
    """group,value are parametrised; attr (the array key) is concatenated = the bug."""
    sql = (
        "SELECT p.id FROM products p "
        "JOIN product_attr a ON a.product_id = p.id "
        f"WHERE a.group_id = %s AND a.attr_id = {attr} AND a.value = %s LIMIT 1"
    )
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (group, value))
            cur.fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Safe data access (everything below is parametrised)
# ---------------------------------------------------------------------------

def q(sql, args=()):
    conn = pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **DB)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())
    finally:
        conn.close()


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def ex(sql, args=()):
    conn = pymysql.connect(autocommit=True, **DB)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.lastrowid
    finally:
        conn.close()


_CACHE = {}


def cached(key, fn, ttl=60):
    hit = _CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    val = fn()
    _CACHE[key] = (time.time() + ttl, val)
    return val


def categories():
    try:
        return cached("cats", lambda: q("SELECT * FROM categories ORDER BY sort"))
    except Exception:
        return []


def attr_names():
    def load():
        out = {}
        for r in q("SELECT group_id, attr_id, name FROM attributes"):
            out[(r["group_id"], r["attr_id"])] = r["name"]
        return out
    try:
        return cached("attrs", load)
    except Exception:
        return {}


def group_names():
    try:
        return cached("groups", lambda: {r["id"]: r["name"] for r in
                                         q("SELECT id, name FROM attr_groups ORDER BY sort")})
    except Exception:
        return {}


def stores():
    try:
        return cached("stores", lambda: q("SELECT * FROM stores ORDER BY id"))
    except Exception:
        return []


def store_by_id(sid):
    for s in stores():
        if str(s["id"]) == str(sid):
            return s
    return None


SPECIAL = {
    "novetly": ("Новинки", "p.is_new = 1"),
    "economy": ("Акція «Економія»", "p.old_price IS NOT NULL"),
    "own-brands": ("Товари власних брендів", "p.is_own = 1"),
    "all": ("Усі товари", "1=1"),
}

SORTS = [
    ("popular", "За популярністю", "p.popularity DESC, p.id"),
    ("price", "Від дешевих до дорогих", "p.price ASC, p.id"),
    ("-price", "Від дорогих до дешевих", "p.price DESC, p.id"),
    ("name", "За назвою", "p.name ASC"),
    ("rating", "За рейтингом", "p.rating DESC, p.reviews_cnt DESC"),
    ("discount", "За розміром знижки", "(p.old_price - p.price) / p.old_price DESC, p.id"),
]


def products_by_ids(ids):
    ids = [int(i) for i in ids if str(i).isdigit()]
    if not ids:
        return {}
    rows = q("SELECT * FROM products WHERE id IN (%s)" % ",".join(["%s"] * len(ids)), ids)
    return {r["id"]: r for r in rows}


# ---------------------------------------------------------------------------
# Session helpers: cart, wishlist, user, csrf
# ---------------------------------------------------------------------------

def cart():
    return session.setdefault("cart", {})


def cart_lines():
    c = session.get("cart") or {}
    if not c:
        return [], 0.0
    try:
        prods = products_by_ids(c.keys())
    except Exception:
        return [], 0.0
    lines, total = [], 0.0
    for pid, qty in c.items():
        p = prods.get(int(pid))
        if not p:
            continue
        s = float(p["price"]) * qty
        total += s
        lines.append((p, qty, s))
    return lines, round(total, 2)


def wishlist():
    return session.setdefault("wish", [])


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    try:
        return q1("SELECT * FROM users WHERE id=%s AND status=10", (uid,))
    except Exception:
        return None


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(24)
    return session["_csrf"]


def csrf_field():
    return '<input type="hidden" name="_csrf-frontend" value="%s">' % csrf_token()


@app.before_request
def _check_csrf():
    session.permanent = True
    if request.method == "POST":
        tok = request.form.get("_csrf-frontend", "")
        if not tok or tok != session.get("_csrf"):
            return _page("Bad Request (#400)", _errbox(
                "Bad Request (#400)",
                "Не вдалося перевірити дані форми. Оновіть сторінку та спробуйте ще раз."),
                status=400)
    return None


def safe_next(default="/"):
    nxt = request.form.get("return") or request.args.get("return") or ""
    if nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return default


def norm_phone(s):
    d = re.sub(r"\D", "", s or "")
    if len(d) == 10 and d.startswith("0"):
        d = "38" + d
    if len(d) == 12 and d.startswith("380"):
        return "+" + d
    return None


def hash_pw(pw):
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(10)).decode().replace("$2b$", "$2y$", 1)


def check_pw(pw, h):
    if not h or not h.startswith("$2"):
        return False
    try:
        return bcrypt.checkpw(pw.encode(), h.replace("$2y$", "$2b$", 1).encode())
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

STYLE = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  background:#f2f2f2;color:#333;line-height:1.4;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
.wrap{max-width:1240px;margin:0 auto;padding:0 16px}
.hdr{background:#2d2d2d;color:#fff;position:relative;z-index:20}
.hdr .wrap{display:flex;align-items:center;gap:14px;padding:12px 16px}
.brand{font-weight:900;font-size:30px;color:#E2001A;letter-spacing:1px}
.catmenu{position:relative}
.catmenu summary{list-style:none}.catmenu summary::-webkit-details-marker{display:none}
.catbtn{background:#E2001A;color:#fff;border:0;border-radius:22px;padding:11px 18px;
  font-weight:700;font-size:14px;white-space:nowrap;cursor:pointer;display:inline-flex;
  align-items:center;gap:8px}
.catmenu .menu{position:absolute;top:48px;left:0;background:#fff;color:#333;border-radius:12px;
  box-shadow:0 12px 30px rgba(0,0,0,.2);padding:8px;min-width:280px}
.catmenu .menu a{display:flex;gap:10px;align-items:center;padding:9px 12px;border-radius:8px;font-size:14px}
.catmenu .menu a:hover{background:#fdeeee;color:#E2001A}
.catmenu .menu hr{border:0;border-top:1px solid #eee;margin:6px 0}
.hsearch{flex:1;min-width:120px;display:flex;background:#fff;border-radius:22px;
  align-items:center;padding:0 6px 0 16px}
.hsearch input{flex:1;border:0;outline:0;padding:11px 8px;font-size:14px;color:#333;background:transparent}
.hsearch button{border:0;background:none;color:#E2001A;font-size:16px;cursor:pointer;padding:6px 10px}
.lang{display:flex;align-items:center;gap:6px;font-size:13px;white-space:nowrap}
.lang .tog{width:30px;height:16px;background:#E2001A;border-radius:10px;position:relative}
.lang .tog::after{content:"";position:absolute;right:2px;top:2px;width:12px;height:12px;
  background:#fff;border-radius:50%}
.addr{font-size:11px;line-height:1.25;white-space:nowrap;opacity:.9}
.addr b{color:#fff;font-weight:600}
.addr:hover b{text-decoration:underline}
.acct{font-size:12px;white-space:nowrap;text-align:center}
.acct:hover,.wish:hover{color:#ffb3bc}
.wish{font-size:13px;white-space:nowrap}
.cart{background:#E2001A;color:#fff;border-radius:22px;padding:9px 16px;font-weight:700;
  font-size:13px;white-space:nowrap;display:inline-flex;align-items:center;gap:8px}
.snav{background:#fff;border-bottom:1px solid #e6e6e6}
.snav .wrap{display:flex;align-items:center;gap:20px;padding:11px 16px;flex-wrap:wrap}
.snav a{font-size:13px;color:#333;white-space:nowrap}
.snav a.promo{color:#E2001A;font-weight:700}
.snav a.active{color:#E2001A;text-decoration:underline;text-underline-offset:4px}
.snav a:hover{color:#E2001A}
.snav .phone{margin-left:auto;color:#E2001A;font-weight:700;font-size:13px}
.flash{margin:14px 0 0;padding:12px 16px;border-radius:10px;font-size:14px}
.flash.success{background:#eef8e4;border:1px solid #cfe9b5;color:#3d6b12}
.flash.error{background:#fdecee;border:1px solid #f6c3ca;color:#a0101f}
.flash.info{background:#eef6fb;border:1px solid #c8e2f2;color:#1f5c80}
.hero{display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-top:20px}
.hero .big{border-radius:16px;padding:34px;color:#fff;min-height:220px;
  background:linear-gradient(120deg,#E2001A 0%,#ff4d5e 60%,#ff8a5b 100%);position:relative;overflow:hidden}
.hero .big h1{font-size:34px;line-height:1.1;margin-bottom:10px;max-width:440px}
.hero .big p{max-width:420px;opacity:.95;margin-bottom:18px}
.hero .big .deco{position:absolute;right:30px;bottom:10px;font-size:120px;opacity:.9}
.hero .hside{display:grid;gap:14px}
.hero .sm{border-radius:16px;padding:20px;color:#2d2d2d;background:#fff;display:flex;gap:14px;align-items:center;
  box-shadow:0 1px 3px rgba(0,0,0,.06)}
.hero .sm .i{font-size:44px}
.hero .sm b{display:block;font-size:16px;margin-bottom:4px}
.hero .sm span{font-size:13px;color:#777}
.btn{display:inline-block;border:0;border-radius:22px;padding:11px 22px;font-weight:700;font-size:14px;
  cursor:pointer;background:#E2001A;color:#fff;text-align:center}
.btn:hover{filter:brightness(1.07)}
.btn.white{background:#fff;color:#E2001A}
.btn.green{background:#78BE20}
.btn.ghost{background:#fff;color:#333;border:1px solid #ddd}
.btn.sm{padding:7px 14px;font-size:13px}
.btn.block{display:block;width:100%}
.tiles{display:grid;grid-template-columns:repeat(8,1fr);gap:12px;margin:20px 0}
.tile{background:#fff;border-radius:12px;padding:16px 8px;text-align:center;
  display:flex;flex-direction:column;align-items:center;gap:8px;box-shadow:0 1px 3px rgba(0,0,0,.06);
  transition:box-shadow .15s,transform .15s}
.tile:hover{box-shadow:0 6px 16px rgba(0,0,0,.12);transform:translateY(-2px)}
.tile .ic{width:58px;height:58px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:30px}
.tile .lb{font-size:12px;color:#333;line-height:1.25;min-height:30px}
.section{background:#fff;border-radius:12px;padding:18px 18px 24px;margin:20px 0;
  box-shadow:0 1px 3px rgba(0,0,0,.06)}
.sechead{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;gap:10px;flex-wrap:wrap}
.sechead h2,.pghead{font-size:22px;font-weight:800;color:#2d2d2d}
.pghead{font-size:28px;margin:6px 0 14px}
.sechead .showall{color:#E2001A;font-weight:600;font-size:14px}
.crumbs{font-size:13px;color:#9a9a9a;margin:16px 0 4px}
.crumbs a:hover{color:#E2001A}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 14px;align-items:center}
.chip{background:#fff6ed;border:1px solid #ffd9b0;color:#8a4b00;border-radius:16px;
  padding:5px 12px;font-size:13px;display:inline-flex;gap:8px;align-items:center}
.chip code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px}
.chip a{color:#b06000;font-weight:700}
.chips .reset{font-size:13px;color:#E2001A}
.catlayout{display:grid;grid-template-columns:250px 1fr;gap:18px;align-items:start}
.side{background:#fff;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.side h4{font-size:14px;margin:14px 0 8px;color:#2d2d2d}
.side h4:first-child{margin-top:0}
.side a.opt{display:flex;align-items:center;gap:8px;font-size:13px;padding:4px 0;color:#444}
.side a.opt:hover{color:#E2001A}
.side a.opt .bx{width:16px;height:16px;border:1.5px solid #bbb;border-radius:4px;display:inline-flex;
  align-items:center;justify-content:center;font-size:11px;flex:0 0 auto}
.side a.opt.on .bx{background:#E2001A;border-color:#E2001A;color:#fff}
.side a.opt .n{margin-left:auto;color:#aaa;font-size:12px}
.side .scroll{max-height:220px;overflow:auto}
.side form.price{display:flex;gap:6px;align-items:center}
.side form.price input{width:70px;padding:6px 8px;border:1px solid #ddd;border-radius:8px}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;font-size:13px;color:#777;gap:10px;flex-wrap:wrap}
.toolbar select{padding:7px 10px;border:1px solid #ddd;border-radius:8px;background:#fff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(205px,1fr));gap:14px}
.card{position:relative;background:#fff;border:1px solid #efefef;border-radius:12px;
  padding:14px;display:flex;flex-direction:column;transition:box-shadow .15s}
.card:hover{box-shadow:0 8px 22px rgba(20,20,30,.10)}
.card .toprow{display:flex;align-items:center;justify-content:space-between;font-size:12px}
.stars{color:#f5a623;letter-spacing:1px}
.stars .off{color:#e0e0e0}
.reviews{color:#9a9a9a;margin-left:5px;letter-spacing:0}
.heartf{display:inline}
.heart{color:#c9c9c9;font-size:18px;cursor:pointer;background:none;border:0}
.heart.on{color:#E2001A}
.badges{position:absolute;top:40px;left:14px;display:flex;flex-direction:column;gap:5px;z-index:2}
.badge{font-size:11px;font-weight:700;color:#fff;border-radius:6px;padding:2px 7px;width:max-content}
.badge.disc{background:#E2001A}
.badge.nov{background:#8bc34a}
.badge.own{background:#ff9800}
.thumb{height:130px;display:flex;align-items:center;justify-content:center;font-size:62px;margin:6px 0 10px}
.card .nm{font-size:14px;color:#2d2d2d;min-height:38px;line-height:1.35}
.card .nm:hover{color:#E2001A}
.card .meta{font-size:12px;color:#aaa;margin-top:4px}
.priceblk{display:flex;align-items:flex-end;justify-content:space-between;margin-top:auto;padding-top:10px}
.oldp{font-size:13px;color:#9a9a9a;text-decoration:line-through}
.newp{color:#E2001A;font-weight:900;font-size:26px;line-height:1}
.newp sup{font-size:13px;font-weight:800;vertical-align:super}
.newp .u{display:block;font-size:11px;font-weight:600;color:#9a9a9a}
.addbtn{border:0;background:#78BE20;color:#fff;width:42px;height:42px;border-radius:50%;
  font-size:18px;cursor:pointer;flex:0 0 auto;align-self:flex-end}
.addbtn:hover{filter:brightness(1.05)}
.notice{background:#fff;border:1px dashed #e0e0e0;border-radius:12px;padding:28px;text-align:center;color:#9a9a9a}
.pager{display:flex;gap:6px;justify-content:center;margin-top:20px;flex-wrap:wrap}
.pager a,.pager span{min-width:36px;height:36px;padding:0 10px;border-radius:18px;display:inline-flex;align-items:center;
  justify-content:center;background:#fff;border:1px solid #e3e3e3;font-size:14px}
.pager .cur{background:#E2001A;border-color:#E2001A;color:#fff;font-weight:700}
.pager a:hover{border-color:#E2001A;color:#E2001A}
.pd{display:grid;grid-template-columns:1fr 1fr;gap:24px;background:#fff;border-radius:12px;padding:24px;
  box-shadow:0 1px 3px rgba(0,0,0,.06);position:relative}
.pd .img{background:#fafafa;border-radius:12px;display:flex;align-items:center;justify-content:center;
  font-size:180px;min-height:340px;position:relative}
.pd h1{font-size:24px;line-height:1.25;margin-bottom:8px}
.pd .sku{font-size:12px;color:#999;margin:6px 0 16px}
.pd .buy{display:flex;align-items:center;gap:14px;margin:18px 0;flex-wrap:wrap}
.pd .avail{font-size:13px;color:#3d6b12;margin:8px 0}
.pd .avail.no{color:#a0101f}
.qty{display:inline-flex;align-items:center;border:1px solid #ddd;border-radius:22px;overflow:hidden;background:#fff}
.qty button{border:0;background:#fff;width:34px;height:38px;font-size:18px;cursor:pointer;color:#555}
.qty input{width:46px;border:0;text-align:center;font-size:15px;height:38px;outline:0}
.specs{width:100%;border-collapse:collapse;font-size:14px}
.specs td{padding:9px 0;border-bottom:1px dashed #e6e6e6;vertical-align:top}
.specs td:first-child{color:#888;width:42%}
.tabs h3{font-size:18px;margin:22px 0 10px}
.rev{border-top:1px solid #f0f0f0;padding:12px 0}
.rev b{font-size:14px}.rev small{color:#aaa;margin-left:8px}
.rev p{font-size:14px;margin-top:4px;color:#444}
.box{background:#fff;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin:16px 0}
.box h2{font-size:20px;margin-bottom:12px}
.box h3{font-size:16px;margin:18px 0 8px}
.box p,.box li{font-size:14px;color:#444;margin-bottom:8px;line-height:1.55}
.box ul{padding-left:20px}
.form{max-width:460px}
.form label{display:block;font-size:13px;color:#666;margin:12px 0 5px}
.form input[type=text],.form input[type=email],.form input[type=password],.form input[type=tel],
.form select,.form textarea{width:100%;padding:11px 13px;border:1px solid #ddd;border-radius:10px;font-size:14px;
  background:#fff;font-family:inherit}
.form input:focus,.form select:focus,.form textarea:focus{outline:0;border-color:#E2001A}
.form .err{color:#c0001a;font-size:12px;margin-top:4px}
.form .chk{display:flex;gap:8px;align-items:flex-start;font-size:13px;color:#555;margin:14px 0}
.form .row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.form .hint{font-size:12px;color:#999;margin-top:4px}
.radios label{display:flex;gap:10px;align-items:flex-start;border:1px solid #e3e3e3;border-radius:10px;padding:12px;
  margin:8px 0;cursor:pointer;color:#333;font-size:14px}
.radios label small{display:block;color:#888;font-size:12px}
.twocol{display:grid;grid-template-columns:1fr 360px;gap:18px;align-items:start}
.summary{background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.06);position:sticky;top:12px}
.summary .ln{display:flex;justify-content:space-between;font-size:14px;margin:8px 0;gap:10px}
.summary .tot{font-size:20px;font-weight:800;border-top:1px solid #eee;padding-top:12px;margin-top:12px}
.summary .note{font-size:12px;color:#888;margin:10px 0}
.progress{height:6px;background:#eee;border-radius:3px;overflow:hidden;margin:6px 0}
.progress i{display:block;height:100%;background:#78BE20}
table.cart{width:100%;border-collapse:collapse;background:#fff}
table.cart td,table.cart th{padding:12px 8px;border-bottom:1px solid #f0f0f0;font-size:14px;text-align:left;vertical-align:middle}
table.cart th{font-size:12px;color:#999;font-weight:600;text-transform:uppercase}
table.cart .ico{font-size:38px;width:56px}
table.cart .x{background:none;border:0;color:#bbb;font-size:20px;cursor:pointer}
table.cart .x:hover{color:#E2001A}
table.list{width:100%;border-collapse:collapse;font-size:14px}
table.list td,table.list th{padding:10px 8px;border-bottom:1px solid #f0f0f0;text-align:left}
table.list th{color:#999;font-size:12px;font-weight:600}
.status{border-radius:10px;padding:2px 10px;font-size:12px;font-weight:600}
.status.delivered{background:#eef8e4;color:#3d6b12}.status.new{background:#eef6fb;color:#1f5c80}
.status.cancelled{background:#f4f4f4;color:#888}
.acctgrid{display:grid;grid-template-columns:240px 1fr;gap:18px;align-items:start}
.acctnav{background:#fff;border-radius:12px;padding:10px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.acctnav a,.acctnav button{display:block;width:100%;text-align:left;padding:10px 12px;border-radius:8px;font-size:14px;
  background:none;border:0;cursor:pointer;color:#333;font-family:inherit}
.acctnav a:hover,.acctnav button:hover,.acctnav a.on{background:#fdeeee;color:#E2001A}
.bonus{background:linear-gradient(120deg,#2d2d2d,#555);color:#fff;border-radius:14px;padding:18px;margin-bottom:14px}
.bonus b{font-size:22px;letter-spacing:2px;display:block;margin-top:6px}
.storegrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:12px}
.store{background:#fff;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.06);display:flex;
  flex-direction:column;gap:6px;font-size:14px}
.store .c{font-size:12px;color:#999;text-transform:uppercase;font-weight:700}
.store .open{color:#3d6b12;font-size:13px}
.store.sel{outline:2px solid #E2001A}
.cities{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 16px}
.cities a{background:#fff;border:1px solid #e3e3e3;border-radius:16px;padding:6px 14px;font-size:13px}
.cities a.on{background:#E2001A;border-color:#E2001A;color:#fff}
.vac{border:1px solid #eee;border-radius:12px;padding:16px;margin:10px 0}
.vac h3{margin:0 0 4px!important}
.vac .sal{color:#3d6b12;font-weight:700}
.feat{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}
.feat div{background:#fff;border-radius:12px;padding:16px;font-size:13px;color:#555;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.feat b{display:block;font-size:22px;color:#E2001A}
.errpage{max-width:760px;margin:40px auto}
.errcard{background:#fff;border:1px solid #efefef;border-top:5px solid #E2001A;border-radius:12px;padding:28px}
.errcard h1{font-size:22px;margin-bottom:6px;color:#E2001A}
.errcard p{color:#9a9a9a;margin-bottom:14px}
.errcard pre{background:#2d2d2d;color:#ff9f9f;border-radius:10px;padding:16px;overflow:auto;
  font-size:13px;font-family:ui-monospace,Menlo,Consolas,monospace}
.foot{color:#9a9a9a;font-size:13px;border-top:1px solid #e6e6e6;margin-top:24px;background:#fff}
.foot .wrap{padding:28px 16px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:18px}
.foot .fcol{display:flex;flex-direction:column;gap:6px}
.foot .fcol b{color:#555;margin-bottom:2px}
.foot .fcol a{color:#666}.foot .fcol a:hover{color:#E2001A}
.foot .fcol.portals a{color:#e30613}.foot .fcol.portals a:hover{text-decoration:underline}
.foot .copy{border-top:1px solid #eee;padding:14px 16px;text-align:center;font-size:12px}
@media(max-width:1000px){.tiles{grid-template-columns:repeat(4,1fr)}.catlayout,.twocol,.acctgrid,.pd,.hero{grid-template-columns:1fr}
  .feat{grid-template-columns:repeat(2,1fr)}}
@media(max-width:760px){
  .hdr .wrap{flex-wrap:wrap}
  .hsearch{order:5;flex-basis:100%}
  .addr,.acct,.wish,.lang{display:none}
  .hero .big .deco{display:none}
  .tiles{grid-template-columns:repeat(2,1fr)}
  .form .row{grid-template-columns:1fr}
}
"""

SCRIPT = """
document.addEventListener('click',function(e){
  var b=e.target.closest('[data-step]');if(!b)return;e.preventDefault();
  var i=b.parentNode.querySelector('input');var v=parseInt(i.value||'1',10)+parseInt(b.dataset.step,10);
  if(v<1)v=1;if(v>99)v=99;i.value=v;
  if(b.dataset.submit){b.form.submit();}
});
document.addEventListener('change',function(e){if(e.target.matches('[data-autosubmit]'))e.target.form.submit();});
document.addEventListener('click',function(e){var d=document.querySelector('details.catmenu[open]');
  if(d&&!d.contains(e.target))d.removeAttribute('open');});
"""

SNAV = [
    ("\U0001F4CD Акції", "/shop/catalog/economy", "promo"),
    ("Партнерам", "/partners", ""),
    ("Про нас", "/about", ""),
    ("Картка АТБ від Райфу", "/card", ""),
    ("Товари власних брендів", "/shop/catalog/own-brands", ""),
    ("Кар'єра", "/career", ""),
    ("Магазини", "/stores", ""),
    ("Оплата та доставка", "/delivery", ""),
]

h = escape


def money(v):
    return "%.2f" % float(v)


def _fmt_int_dec(price):
    try:
        f = float(price)
    except (TypeError, ValueError):
        return h(str(price)), "00"
    s = "%.2f" % f
    i, d = s.split(".")
    return i, d


def _header():
    lines, total = cart_lines()
    cnt = sum(int(qty) for _, qty, _ in lines)
    user = current_user()
    st = store_by_id(session.get("store_id", 1))
    addr = ("%s, %s" % (st["city"], st["address"])) if st else "Оберіть магазин"
    menu = "".join('<a href="/shop/catalog/%s"><span>%s</span>%s</a>' % (h(c["slug"]), c["icon"], h(c["name"]))
                   for c in categories())
    menu += ('<hr><a href="/shop/catalog/novetly">\U0001F195 Новинки</a>'
             '<a href="/shop/catalog/economy">\U0001F3F7 Акція «Економія»</a>'
             '<a href="/shop/catalog/own-brands">⭐ Власні бренди АТБ</a>'
             '<a href="/shop/catalog/all">\U0001F4CB Усі товари</a>')
    who = h(user["first_name"] or "Мій кабінет") if user else "Мій кабінет"
    return (
        '<header class="hdr"><div class="wrap">'
        '<a class="brand" href="/">АТБ</a>'
        '<details class="catmenu"><summary class="catbtn">▦ Каталог товарів ⌄</summary>'
        '<div class="menu">%s</div></details>'
        '<form class="hsearch" action="/search" method="get">'
        '<input name="q" placeholder="Я шукаю…" aria-label="Пошук" value="%s">'
        '<button type="submit" aria-label="Знайти">\U0001F50D</button>'
        '</form>'
        '<div class="lang"><span class="tog"></span>Рус</div>'
        '<a class="addr" href="/stores">\U0001F4CD Змінити адресу/магазин<br><b>%s</b></a>'
        '<a class="acct" href="/account">\U0001F464<br>%s</a>'
        '<a class="wish" href="/wishlist">♡ %d</a>'
        '<a class="cart" href="/cart">\U0001F6D2 %d &middot; %s грн</a>'
        '</div></header>'
        % (menu, h(request.args.get("q", "")) if request.path == "/search" else "",
           h(addr), who, len(session.get("wish") or []), cnt, money(total))
    )


def _snav():
    items = []
    for label, href, cls in SNAV:
        c = cls
        if request.path == href:
            c = (c + " active").strip()
        items.append('<a href="%s"%s>%s</a>' % (href, (' class="%s"' % c) if c else "", h(label)))
    items.append('<span class="phone">\U0001F4DE 0-800-500-415 (8:00-22:00)</span>')
    return '<nav class="snav"><div class="wrap">%s</div></nav>' % "".join(items)


def _flashes():
    out = []
    for cat, msg in get_flashed_messages(with_categories=True):
        out.append('<div class="flash %s">%s</div>' % (h(cat if cat != "message" else "info"), h(msg)))
    return '<div class="wrap">%s</div>' % "".join(out) if out else ""


def _footer():
    # Public ATB portals the player can reach directly (perimeter). The internal
    # systems (grafana/zabbix/harbor/…) are intentionally NOT linked — they are
    # found by pivoting. Links use the host-mapped ports documented in README.
    mob, edu, sup, owa = (os.environ.get("PORTAL_PORTS", "8081,8082,8083,8444")
                          .split(",") + ["", "", "", ""])[:4]
    host = (request.host or "localhost").split(":")[0]
    portals = (
        f'<a href="http://{host}:{mob}/">Мобільний застосунок</a>'
        f'<a href="http://{host}:{edu}/">Навчальний портал</a>'
        f'<a href="http://{host}:{sup}/">Портал постачальника</a>'
        f'<a href="http://{host}:{owa}/">Корпоративна пошта</a>'
    )
    return ('<footer class="foot">'
            '<div class="wrap">'
            '<div class="fcol"><b>Покупцям</b><a href="/delivery">Оплата та доставка</a>'
            '<a href="/stores">Адреси магазинів</a><a href="/card">Картка АТБ від Райфу</a>'
            '<a href="/faq">Питання та відповіді</a><a href="/account">Мій кабінет</a></div>'
            '<div class="fcol"><b>Компанія</b><a href="/about">Про нас</a><a href="/career">Кар\'єра</a>'
            '<a href="/partners">Партнерам</a><a href="/shop/catalog/own-brands">Власні бренди</a></div>'
            '<div class="fcol portals"><b>АТБ онлайн</b>%s</div>'
            '<div class="fcol"><b>Контакти</b><span>Гаряча лінія: 0-800-500-415</span>'
            '<span>Щодня з 8:00 до 22:00</span><span>info@atbmarket.com</span></div>'
            '</div><div class="copy">&copy; 2026 АТБ-Маркет &middot; www.atbmarket.com &middot; '
            'Ціни на сайті можуть відрізнятися від цін у магазинах</div></footer>' % portals)


def _page(title, body, status=200):
    html = (
        '<!doctype html><html lang="uk"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="csrf-param" content="_csrf-frontend"><meta name="csrf-token" content="%s">'
        '<title>%s</title><style>%s</style></head><body>%s%s%s%s%s'
        '<script>%s</script></body></html>'
        % (csrf_token(), h(title), STYLE, _header(), _snav(), _flashes(), body, _footer(), SCRIPT)
    )
    return Response(html, status=status, mimetype="text/html")


def _crumbs(*items):
    parts = ['<a href="/">Головна</a>']
    for label, href in items:
        parts.append('<a href="%s">%s</a>' % (h(href), h(label)) if href else h(label))
    return '<div class="crumbs">%s</div>' % " / ".join(parts)


def _errbox(title, msg):
    return ('<div class="wrap"><div class="errpage"><div class="errcard"><h1>%s</h1><p>%s</p>'
            '<a class="btn" href="/">На головну</a></div></div></div>' % (h(title), h(msg)))


def _stars(rating, cnt):
    filled = int(round(float(rating or 0)))
    s = "".join("★" if i < filled else '<span class="off">★</span>' for i in range(5))
    return '<span class="stars">%s<span class="reviews">(%d)</span></span>' % (s, int(cnt or 0))


def _disc(p):
    if p.get("old_price"):
        try:
            return int(round((1 - float(p["price"]) / float(p["old_price"])) * 100))
        except (TypeError, ZeroDivisionError):
            return 0
    return 0


def _badges(p):
    out = []
    d = _disc(p)
    if d:
        out.append('<span class="badge disc">-%d%%</span>' % d)
    if p.get("is_new"):
        out.append('<span class="badge nov">новинка</span>')
    if p.get("is_own"):
        out.append('<span class="badge own">▰ власна марка АТБ</span>')
    return '<div class="badges">%s</div>' % "".join(out)


def _heart(pid):
    on = int(pid) in (session.get("wish") or [])
    return ('<form class="heartf" method="post" action="/wishlist/toggle">%s'
            '<input type="hidden" name="product_id" value="%d"><input type="hidden" name="return" value="%s">'
            '<button class="heart%s" title="%s">%s</button></form>'
            % (csrf_field(), int(pid), h(request.full_path.rstrip("?")), " on" if on else "",
               "Прибрати з обраного" if on else "В обране", "♥" if on else "♡"))


def _card(p):
    intp, decp = _fmt_int_dec(p["price"])
    oldhtml = ('<span class="oldp">%s грн</span>' % money(p["old_price"])) if p.get("old_price") else ""
    return (
        '<div class="card">'
        '<div class="toprow">%s%s</div>%s'
        '<a class="thumb" href="/shop/product/%d">%s</a>'
        '<a class="nm" href="/shop/product/%d">%s</a>'
        '<div class="meta">%s</div>'
        '<div style="margin-top:6px;min-height:18px">%s</div>'
        '<div class="priceblk"><div>'
        '<span class="newp">%s<sup>.%s</sup><span class="u">грн/%s</span></span></div>'
        '<form method="post" action="/cart/add">%s<input type="hidden" name="product_id" value="%d">'
        '<input type="hidden" name="return" value="%s">'
        '<button class="addbtn" type="submit" title="До кошика">\U0001F6D2</button></form>'
        '</div></div>'
        % (_stars(p.get("rating"), p.get("reviews_cnt")), _heart(p["id"]), _badges(p),
           p["id"], p.get("icon") or "\U0001F6D2", p["id"], h(p["name"]),
           h(p.get("pack") or ""), oldhtml, intp, decp, h(p.get("unit") or "шт"),
           csrf_field(), p["id"], h(request.full_path.rstrip("?")))
    )


def _grid(products):
    if products is None:
        return '<div class="notice">\U0001F6D2 Каталог тимчасово недоступний.</div>'
    if not products:
        return '<div class="notice">Товарів не знайдено. Спробуйте змінити параметри фільтра.</div>'
    return '<div class="grid">%s</div>' % "".join(_card(r) for r in products)


def _section(title, products, more=None):
    return (
        '<div class="wrap"><div class="section">'
        '<div class="sechead"><h2>%s</h2>%s</div>%s</div></div>'
        % (h(title), ('<a class="showall" href="%s">Показати всі →</a>' % more) if more else "",
           _grid(products)))


def _tiles():
    out = []
    for c in categories():
        href = "/shop/catalog/%s?filter[8][%s]=1" % (h(c["slug"]), c["attr_id"])
        out.append(
            '<a class="tile" href="%s"><span class="ic" style="background:%s">%s</span>'
            '<span class="lb">%s</span></a>' % (href, h(c["bg"] or "#f3f3f3"), c["icon"], h(c["name"])))
    if not out:
        return ""
    return '<div class="wrap"><div class="tiles">%s</div></div>' % "".join(out)


def _error_page(sqlstate_line):
    body = (
        '<div class="wrap"><div class="errpage"><div class="errcard">'
        '<h1>Database Exception</h1>'
        '<p>Під час обробки фільтра каталогу сталася помилка бази даних.</p>'
        '<pre>%s\n  in /var/www/ishop/vendor/yiisoft/yii2/db/Command.php:1304</pre>'
        '</div></div></div>' % sqlstate_line
    )
    return body


def _pager(page, pages):
    if pages <= 1:
        return ""

    def link(n, label=None):
        args = [(k, v) for k, v in request.args.items(multi=True) if k != "page"]
        if n > 1:
            args.append(("page", str(n)))
        qs = urlencode(args, safe="[]")
        return '<a href="%s%s">%s</a>' % (h(request.path), ("?" + h(qs)) if qs else "", label or n)
    out = []
    if page > 1:
        out.append(link(page - 1, "‹"))
    for n in range(1, pages + 1):
        out.append('<span class="cur">%d</span>' % n if n == page else link(n))
    if page < pages:
        out.append(link(page + 1, "›"))
    return '<div class="pager">%s</div>' % "".join(out)


def _sort_select():
    cur = request.args.get("sort", "popular")
    hidden = "".join('<input type="hidden" name="%s" value="%s">' % (h(k), h(v))
                     for k, v in request.args.items(multi=True) if k not in ("sort", "page"))
    opts = "".join('<option value="%s"%s>%s</option>' % (k, " selected" if k == cur else "", h(lbl))
                   for k, lbl, _ in SORTS)
    return ('<form method="get" action="%s">%s<label>Сортувати: <select name="sort" data-autosubmit>%s'
            '</select></label><noscript><button>OK</button></noscript></form>'
            % (h(request.path), hidden, opts))


def _order_sql():
    key = request.args.get("sort", "popular")
    for k, _, sql in SORTS:
        if k == key:
            if k == "discount":
                return "p.old_price IS NULL, " + sql
            return sql
    return SORTS[0][2]


def _page_no():
    try:
        return max(1, int(request.args.get("page", "1")))
    except ValueError:
        return 1


def paged_products(where, args):
    total = q1("SELECT COUNT(*) AS n FROM products p WHERE " + where, args)["n"]
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(_page_no(), pages)
    rows = q("SELECT p.* FROM products p WHERE %s ORDER BY %s LIMIT %d OFFSET %d"
             % (where, _order_sql(), PER_PAGE, (page - 1) * PER_PAGE), args)
    return rows, total, page, pages


# ---------------------------------------------------------------------------
# Routes: home, catalogue, product, search
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    try:
        econ = q("SELECT * FROM products WHERE old_price IS NOT NULL ORDER BY popularity DESC LIMIT 10")
        new = q("SELECT * FROM products WHERE is_new=1 ORDER BY popularity DESC LIMIT 5")
        own = q("SELECT * FROM products WHERE is_own=1 ORDER BY popularity DESC LIMIT 5")
    except Exception:
        econ = new = own = None
    hero = (
        '<div class="wrap"><div class="hero">'
        '<div class="big"><h1>Економія щодня — ціни нижчі, ніж учора</h1>'
        '<p>Понад 1300 магазинів по всій Україні. Замовляйте онлайн з доставкою додому '
        'або забирайте в найближчому АТБ.</p>'
        '<a class="btn white" href="/shop/catalog/economy">Дивитись акції</a>'
        '<span class="deco">\U0001F6D2</span></div>'
        '<div class="hside">'
        '<a class="sm" href="/delivery"><span class="i">\U0001F69A</span><div><b>Доставка від 2 годин</b>'
        '<span>Безкоштовно від %d грн</span></div></a>'
        '<a class="sm" href="/card"><span class="i">\U0001F4B3</span><div><b>Картка АТБ від Райфу</b>'
        '<span>Кешбек до 5%% на покупки в АТБ</span></div></a>'
        '</div></div></div>' % FREE_DELIVERY_FROM)
    body = (hero + _tiles()
            + _section("Акція «Економія»", econ, "/shop/catalog/economy")
            + _section("Новинки", new, "/shop/catalog/novetly")
            + _section("Товари власних брендів", own, "/shop/catalog/own-brands")
            + '<div class="wrap"><div class="feat">'
              '<div><b>1300+</b>магазинів у 300+ населених пунктах</div>'
              '<div><b>45 000+</b>працівників у команді АТБ</div>'
              '<div><b>№1</b>за кількістю покупців серед роздрібних мереж</div>'
              '<div><b>1993</b>рік заснування компанії</div></div></div>')
    return _page("ATB Market — онлайн-супермаркет", body)


def _filter_link(group, attr, active_keys):
    key = "filter[%s][%s]" % (group, attr)
    args = [(k, v) for k, v in request.args.items(multi=True) if k != "page"]
    if key in active_keys:
        args = [(k, v) for k, v in args if k != key]
    else:
        args.append((key, "1"))
    qs = urlencode(args, safe="[]")
    return "%s%s" % (request.path, ("?" + qs) if qs else "")


def _render_catalog(category, filters):
    cats = {c["slug"]: c for c in categories()}
    cat = cats.get(category)
    if cat:
        title = cat["name"]
        where, args = ["p.category_id = %s"], [cat["id"]]
    elif category in SPECIAL:
        title, cond = SPECIAL[category]
        where, args = [cond], []
    else:
        return _page("Not Found (#404)", _errbox("Not Found (#404)", "Сторінку не знайдено."), status=404)
    base_where, base_args = list(where), list(args)

    # display filtering: only well-formed numeric keys narrow the listing
    by_group = {}
    for g, a, v in filters:
        if str(g).isdigit() and str(a).isdigit():
            by_group.setdefault(int(g), []).append((int(a), v))
    for g, items in by_group.items():
        ors = []
        for a, v in items:
            ors.append("(group_id=%s AND attr_id=%s AND value=%s)")
            args += [g, a, v]
        where.append("p.id IN (SELECT product_id FROM product_attr WHERE %s)" % " OR ".join(ors))
    try:
        pf, pt = request.args.get("price_from", ""), request.args.get("price_to", "")
        if pf:
            where.append("p.price >= %s"); args.append(float(pf))
        if pt:
            where.append("p.price <= %s"); args.append(float(pt))
    except ValueError:
        pass
    try:
        rows, total, page, pages = paged_products(" AND ".join(where), args)
        facets = q("SELECT a.group_id, a.attr_id, COUNT(DISTINCT a.product_id) AS n FROM product_attr a "
                   "JOIN products p ON p.id = a.product_id WHERE %s GROUP BY a.group_id, a.attr_id"
                   % " AND ".join(base_where), base_args)
    except Exception:
        rows, total, page, pages, facets = None, 0, 1, 1, []

    names, groups = attr_names(), group_names()
    active_keys = {"filter[%s][%s]" % (g, a) for g, a, _ in filters}
    # chips (echo of the active filter, as Yii's ActiveForm summary does)
    chips = []
    for g, a, v in filters:
        nm = None
        if str(g).isdigit() and str(a).isdigit():
            nm = names.get((int(g), int(a)))
        if nm:
            label = '%s: %s' % (h(groups.get(int(g), "Фільтр")), h(nm))
        else:
            label = '<code>filter[%s][%s]=%s</code>' % (h(str(g)), h(str(a)), h(str(v)))
        chips.append('<span class="chip">%s <a href="%s" title="Прибрати">×</a></span>'
                     % (label, h(_filter_link(g, a, active_keys))))
    chiphtml = ""
    if chips:
        chiphtml = ('<div class="chips"><span style="font-size:13px;color:#888">Обрані фільтри:</span>%s'
                    '<a class="reset" href="%s">Скинути все</a></div>' % ("".join(chips), h(request.path)))

    # sidebar facets
    fac = {}
    for r in facets:
        fac.setdefault(r["group_id"], []).append((r["attr_id"], r["n"]))
    side = []
    for gid in sorted(groups, key=lambda x: [8, 9, 12, 14].index(x) if x in (8, 9, 12, 14) else 99):
        if gid not in fac:
            continue
        opts = []
        for aid, n in sorted(fac[gid], key=lambda t: names.get((gid, t[0]), "")):
            key = "filter[%s][%s]" % (gid, aid)
            on = key in active_keys
            opts.append('<a class="opt%s" href="%s"><span class="bx">%s</span>%s<span class="n">%d</span></a>'
                        % (" on" if on else "", h(_filter_link(gid, aid, active_keys)), "✓" if on else "",
                           h(names.get((gid, aid), str(aid))), n))
        side.append('<h4>%s</h4><div class="scroll">%s</div>' % (h(groups[gid]), "".join(opts)))
    hidden = "".join('<input type="hidden" name="%s" value="%s">' % (h(k), h(v))
                     for k, v in request.args.items(multi=True) if k not in ("price_from", "price_to", "page"))
    side.append('<h4>Ціна, грн</h4><form class="price" method="get">%s<input name="price_from" placeholder="від" '
                'value="%s"> – <input name="price_to" placeholder="до" value="%s"><button class="btn sm">OK</button>'
                '</form>' % (hidden, h(request.args.get("price_from", "")), h(request.args.get("price_to", ""))))
    other = "".join('<a class="opt" href="/shop/catalog/%s"><span>%s</span>%s</a>' % (h(c["slug"]), c["icon"], h(c["name"]))
                    for c in categories() if c["slug"] != category)
    side.append('<h4>Інші розділи</h4>%s' % other)

    body = ('<div class="wrap">%s<h1 class="pghead">%s</h1>%s'
            '<div class="catlayout"><aside class="side">%s</aside><div>'
            '<div class="toolbar"><span>Знайдено товарів: <b>%d</b></span>%s</div>%s%s</div></div></div>'
            % (_crumbs(("Каталог", "/shop/catalog/all"), (title, None)), h(title), chiphtml,
               "".join(side), total, _sort_select(), _grid(rows), _pager(page, pages)))
    return _page("%s — купити в АТБ онлайн" % title, body)


@app.get("/shop/catalog/<category>")
def catalog(category):
    ip = atblog.client_ip(request)
    # Flask parses filter[8][490]=1 into request.args as 'filter[8][490]'
    filters = []
    for k in request.args:
        m = re.match(r"^filter\[(?P<g>[^\]]+)\]\[(?P<a>.+)\]$", k)
        if m:
            filters.append((m.group("g"), m.group("a"), request.args.get(k)))
    for group, attr, value in filters:
        suspicious = bool(INJECT_SIGNS.search(attr))
        try:
            run_filter(group, attr, value)
            if suspicious:
                atblog.log("www.sqli_probe_true", ip, category=category,
                           filter_key=attr, qs=request.query_string.decode("latin1"),
                           status=200, msg="injected key evaluated TRUE (boolean oracle)")
        except pymysql.err.ProgrammingError as e:
            code = e.args[0] if e.args else 0
            atblog.log("www.sqli_error", ip, category=category, filter_key=attr,
                       qs=request.query_string.decode("latin1"), status=500,
                       sqlstate="42000", err=str(e)[:200],
                       msg="SQL syntax error from injected key (#42000)")
            line = ("PDOException: SQLSTATE[42000]: Syntax error or access "
                    "violation: %s" % escape(str(code)))
            return _page("ATB Market — помилка", _error_page(line), status=500)
        except pymysql.err.OperationalError as e:
            # false branch of boolean subqueries can surface as operational errors too
            atblog.log("www.sqli_error", ip, category=category, filter_key=attr,
                       qs=request.query_string.decode("latin1"), status=500,
                       err=str(e)[:200])
            return _page("ATB Market — помилка",
                         _error_page("PDOException: SQLSTATE[HY000]: General error"),
                         status=500)
        except Exception as e:  # DB not ready etc.
            atblog.log("www.error", ip, err=str(e)[:200])
            return Response("temporary error", status=502)
    return _render_catalog(category, filters)


@app.get("/shop/product/<int:pid>")
def product(pid):
    try:
        p = q1("SELECT * FROM products WHERE id=%s", (pid,))
    except Exception:
        p = None
    if not p:
        return _page("Not Found (#404)", _errbox("Not Found (#404)", "Товар не знайдено або знято з продажу."),
                     status=404)
    cat = next((c for c in categories() if c["id"] == p["category_id"]), None)
    revs = q("SELECT * FROM reviews WHERE product_id=%s ORDER BY created_at DESC", (pid,))
    related = q("SELECT * FROM products WHERE category_id=%s AND id<>%s ORDER BY popularity DESC LIMIT 5",
                (p["category_id"], pid))
    intp, decp = _fmt_int_dec(p["price"])
    st = store_by_id(session.get("store_id", 1))
    in_cart = (session.get("cart") or {}).get(str(pid))
    specs = [("Торгова марка", p["brand"] or "—"), ("Країна виробництва", p["country"]),
             ("Фасування", p["pack"]), ("Одиниця продажу", p["unit"]),
             ("Склад", p["composition"]), ("Умови зберігання", p["storage"]),
             ("Розділ", cat["name"] if cat else "—")]
    spec_html = "".join("<tr><td>%s</td><td>%s</td></tr>" % (h(k), h(str(v or "—"))) for k, v in specs)
    rev_html = "".join('<div class="rev">%s <b>%s</b><small>%s</small><p>%s</p></div>'
                       % (_stars(r["rating"], 0).replace('<span class="reviews">(0)</span>', ""),
                          h(r["author"]), r["created_at"].strftime("%d.%m.%Y"), h(r["body"] or ""))
                       for r in revs) or '<p style="color:#999;font-size:14px">Відгуків ще немає. Будьте першим!</p>'
    if current_user():
        rev_form = ('<form class="form" method="post" action="/shop/product/%d/review" style="max-width:600px">%s'
                    '<label>Ваша оцінка</label><select name="rating">'
                    '<option value="5">★★★★★ Відмінно</option><option value="4">★★★★ Добре</option>'
                    '<option value="3">★★★ Нормально</option><option value="2">★★ Погано</option>'
                    '<option value="1">★ Жахливо</option></select>'
                    '<label>Відгук</label><textarea name="body" rows="3" maxlength="1000" required></textarea>'
                    '<div style="margin-top:10px"><button class="btn sm">Надіслати відгук</button></div></form>'
                    % (pid, csrf_field()))
    else:
        rev_form = ('<p style="font-size:14px;margin-top:10px"><a style="color:#E2001A" href="/login?return=/shop/product/%d">'
                    'Увійдіть</a>, щоб залишити відгук.</p>' % pid)
    avail = ('<div class="avail">✓ В наявності — %s, %s</div>' % (h(st["city"]), h(st["address"]))
             if p["stock"] > 0 and st else '<div class="avail no">✕ Немає в наявності в обраному магазині</div>')
    body = (
        '<div class="wrap">%s<div class="pd"><div class="img">%s%s</div><div>'
        '<h1>%s</h1>%s<div class="sku">Артикул: %s · %s</div>'
        '%s<div><span class="newp" style="font-size:36px">%s<sup>.%s</sup><span class="u">грн/%s</span></span></div>'
        '%s'
        '<form class="buy" method="post" action="/cart/add">%s<input type="hidden" name="product_id" value="%d">'
        '<span class="qty"><button data-step="-1">−</button><input name="qty" value="1" inputmode="numeric">'
        '<button data-step="1">+</button></span>'
        '<button class="btn green" type="submit">\U0001F6D2 Додати до кошика</button></form>%s'
        '<div style="margin-top:6px">%s</div>'
        '<p style="font-size:14px;color:#555;margin-top:16px">%s</p>'
        '</div></div>'
        '<div class="box tabs"><h3 style="margin-top:0">Характеристики</h3><table class="specs">%s</table>'
        '<h3>Відгуки (%d)</h3>%s%s</div>'
        '%s</div>'
        % (_crumbs(("Каталог", "/shop/catalog/all"),
                   (cat["name"], "/shop/catalog/" + cat["slug"]) if cat else ("Каталог", None), (p["name"], None)),
           _badges(p), p["icon"] or "\U0001F6D2", h(p["name"]), _stars(p["rating"], p["reviews_cnt"]),
           h(p["sku"] or ""), h(p["pack"] or ""),
           ('<div class="oldp">%s грн</div>' % money(p["old_price"])) if p["old_price"] else "",
           intp, decp, h(p["unit"]), avail, csrf_field(), pid,
           ('<div style="font-size:13px;color:#3d6b12">У кошику: %s %s · <a href="/cart" style="color:#E2001A">'
            'перейти до кошика</a></div>' % (in_cart, h(p["unit"]))) if in_cart else "",
           _heart(pid), h(p["description"] or ""), spec_html, len(revs), rev_html, rev_form,
           _section("Схожі товари", related, "/shop/catalog/" + cat["slug"] if cat else None)
           .replace('<div class="wrap">', '<div>', 1)))
    return _page("%s — АТБ" % p["name"], body)


@app.post("/shop/product/<int:pid>/review")
def product_review(pid):
    user = current_user()
    if not user:
        return redirect("/login?return=/shop/product/%d" % pid)
    body = (request.form.get("body") or "").strip()[:1000]
    try:
        rating = min(5, max(1, int(request.form.get("rating", "5"))))
    except ValueError:
        rating = 5
    if not body:
        flash("Напишіть текст відгуку.", "error")
        return redirect("/shop/product/%d" % pid)
    author = ("%s %s." % (user["first_name"] or "Покупець", (user["last_name"] or " ")[0])).strip()
    ex("INSERT INTO reviews (product_id, user_id, author, rating, body) VALUES (%s,%s,%s,%s,%s)",
       (pid, user["id"], author, rating, body))
    ex("UPDATE products SET reviews_cnt=(SELECT COUNT(*) FROM reviews WHERE product_id=%s), "
       "rating=(SELECT ROUND(AVG(rating),1) FROM reviews WHERE product_id=%s) WHERE id=%s", (pid, pid, pid))
    atblog.log("www.review_posted", atblog.client_ip(request), user_id=user["id"], product_id=pid, rating=rating)
    flash("Дякуємо! Ваш відгук опубліковано.", "success")
    return redirect("/shop/product/%d" % pid)


@app.get("/search")
def search():
    term = (request.args.get("q") or "").strip()[:100]
    if not term:
        body = ('<div class="wrap">%s<h1 class="pghead">Пошук</h1><div class="notice">Введіть назву товару, '
                'бренд або категорію у рядку пошуку.</div></div>' % _crumbs(("Пошук", None)))
        return _page("Пошук — АТБ", body)
    words = [w for w in re.split(r"\s+", term) if w][:5]
    where = " AND ".join(["(p.name LIKE %s OR p.brand LIKE %s OR p.country LIKE %s)"] * len(words))
    args = []
    for w in words:
        like = "%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        args += [like, like, like]
    try:
        rows, total, page, pages = paged_products(where, args)
    except Exception:
        rows, total, page, pages = None, 0, 1, 1
    if page == 1:
        atblog.log("www.search", atblog.client_ip(request), q=term, results=total)
    tip = ""
    if total == 0:
        tip = ('<div class="box"><p>За запитом «%s» нічого не знайдено. Перевірте написання або перегляньте '
               '<a style="color:#E2001A" href="/shop/catalog/all">весь каталог</a>.</p></div>' % h(term))
    body = ('<div class="wrap">%s<h1 class="pghead">Результати пошуку «%s»</h1>%s'
            '<div class="toolbar"><span>Знайдено товарів: <b>%d</b></span>%s</div>%s%s</div>'
            % (_crumbs(("Пошук", None)), h(term), tip, total, _sort_select(),
               _grid(rows) if total else "", _pager(page, pages)))
    return _page("Пошук: %s — АТБ" % term, body)


# ---------------------------------------------------------------------------
# Cart & wishlist
# ---------------------------------------------------------------------------

def _qty(v, default=1):
    try:
        return max(1, min(99, int(float(v))))
    except (TypeError, ValueError):
        return default


@app.post("/cart/add")
def cart_add():
    pid = request.form.get("product_id", "")
    try:
        p = q1("SELECT id, name, stock FROM products WHERE id=%s", (int(pid),))
    except Exception:
        p = None
    if not p:
        flash("Товар не знайдено.", "error")
        return redirect(safe_next("/cart"))
    c = cart()
    c[str(p["id"])] = min(99, c.get(str(p["id"]), 0) + _qty(request.form.get("qty")))
    session.modified = True
    flash("«%s» додано до кошика." % p["name"], "success")
    return redirect(safe_next("/cart"))


@app.post("/cart/update")
def cart_update():
    pid = request.form.get("product_id", "")
    c = cart()
    if pid in c:
        c[pid] = _qty(request.form.get("qty"), c[pid])
        session.modified = True
    return redirect("/cart")


@app.post("/cart/remove")
def cart_remove():
    c = cart()
    c.pop(request.form.get("product_id", ""), None)
    session.modified = True
    flash("Товар видалено з кошика.", "info")
    return redirect("/cart")


@app.post("/cart/clear")
def cart_clear():
    session["cart"] = {}
    flash("Кошик очищено.", "info")
    return redirect("/cart")


def _summary(subtotal, delivery=None, button=None):
    left = FREE_DELIVERY_FROM - subtotal
    pct = min(100, int(subtotal * 100 / FREE_DELIVERY_FROM))
    fee_html = ""
    if delivery is not None:
        fee_html = '<div class="ln"><span>Доставка</span><span>%s</span></div>' % (
            "безкоштовно" if delivery == 0 else "%s грн" % money(delivery))
    total = subtotal + (delivery or 0)
    hint = ('<div class="note">До безкоштовної доставки залишилось <b>%s грн</b>'
            '<div class="progress"><i style="width:%d%%"></i></div></div>' % (money(left), pct)
            if left > 0 else '<div class="note" style="color:#3d6b12">✓ Доставка для вас безкоштовна</div>')
    return ('<div class="summary"><h3 style="margin-bottom:8px">Ваше замовлення</h3>'
            '<div class="ln"><span>Товари</span><span>%s грн</span></div>%s'
            '<div class="ln tot"><span>Разом</span><span>%s грн</span></div>%s%s</div>'
            % (money(subtotal), fee_html, money(total), hint, button or ""))


@app.get("/cart")
def cart_view():
    lines, total = cart_lines()
    if not lines:
        body = ('<div class="wrap">%s<h1 class="pghead">Кошик</h1><div class="notice" style="padding:50px">'
                '<div style="font-size:60px">\U0001F6D2</div><p style="margin:10px 0 18px">Ваш кошик порожній</p>'
                '<a class="btn" href="/shop/catalog/economy">До акційних товарів</a></div></div>'
                % _crumbs(("Кошик", None)))
        return _page("Кошик — АТБ", body)
    rows = []
    for p, qty, s in lines:
        rows.append(
            '<tr><td class="ico">%s</td><td><a href="/shop/product/%d"><b>%s</b></a><br>'
            '<small style="color:#999">%s грн/%s</small></td>'
            '<td><form method="post" action="/cart/update">%s<input type="hidden" name="product_id" value="%d">'
            '<span class="qty"><button data-step="-1" data-submit="1">−</button>'
            '<input name="qty" value="%d" data-autosubmit><button data-step="1" data-submit="1">+</button></span>'
            '</form></td><td><b>%s грн</b></td>'
            '<td><form method="post" action="/cart/remove">%s<input type="hidden" name="product_id" value="%d">'
            '<button class="x" title="Видалити">×</button></form></td></tr>'
            % (p["icon"] or "", p["id"], h(p["name"]), money(p["price"]), h(p["unit"]), csrf_field(), p["id"],
               qty, money(s), csrf_field(), p["id"]))
    body = ('<div class="wrap">%s<h1 class="pghead">Кошик</h1><div class="twocol"><div class="box" style="margin:0">'
            '<table class="cart"><tr><th></th><th>Товар</th><th>Кількість</th><th>Сума</th><th></th></tr>%s</table>'
            '<div style="display:flex;justify-content:space-between;margin-top:16px;gap:10px;flex-wrap:wrap">'
            '<a class="btn ghost sm" href="/shop/catalog/all">← Продовжити покупки</a>'
            '<form method="post" action="/cart/clear">%s<button class="btn ghost sm">Очистити кошик</button></form>'
            '</div></div>%s</div></div>'
            % (_crumbs(("Кошик", None)), "".join(rows), csrf_field(),
               _summary(total, None, '<a class="btn block" href="/checkout">Оформити замовлення</a>')))
    return _page("Кошик — АТБ", body)


@app.post("/wishlist/toggle")
def wishlist_toggle():
    try:
        pid = int(request.form.get("product_id", ""))
    except ValueError:
        return redirect(safe_next("/wishlist"))
    w = wishlist()
    if pid in w:
        w.remove(pid)
        flash("Товар прибрано з обраного.", "info")
    else:
        w.append(pid)
        flash("Товар додано до обраного.", "success")
    session.modified = True
    return redirect(safe_next("/wishlist"))


@app.get("/wishlist")
def wishlist_view():
    ids = session.get("wish") or []
    try:
        prods = products_by_ids(ids)
        rows = [prods[i] for i in ids if i in prods]
    except Exception:
        rows = None
    body = ('<div class="wrap">%s<h1 class="pghead">Обране</h1>%s</div>'
            % (_crumbs(("Обране", None)),
               _grid(rows) if rows else '<div class="notice">У списку обраного поки немає товарів. '
               'Натисніть ♡ на картці товару, щоб зберегти його тут.</div>'))
    return _page("Обране — АТБ", body)


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

def _slots():
    now = datetime.now()
    out = []
    for d in range(0, 3):
        day = now + timedelta(days=d)
        for a, b in ((9, 11), (11, 13), (13, 15), (15, 17), (17, 19), (19, 21)):
            if d == 0 and a < now.hour + 2:
                continue
            lbl = ("Сьогодні" if d == 0 else "Завтра" if d == 1 else day.strftime("%d.%m")) + \
                ", %02d:00–%02d:00" % (a, b)
            out.append(lbl)
    return out


PAYMENTS = {
    "card_courier": ("Карткою при отриманні", "Термінал у кур'єра або на касі магазину"),
    "cash": ("Готівкою при отриманні", "Будь ласка, підготуйте суму без решти"),
    "card_online": ("Карткою онлайн", "Посилання на оплату надійде в SMS після підтвердження замовлення"),
}


def _checkout_form(form, errors, lines, total):
    user = current_user()

    def val(k, default=""):
        return h(form.get(k, default))

    def err(k):
        return '<div class="err">%s</div>' % h(errors[k]) if k in errors else ""
    dtype = form.get("delivery_type", "courier")
    st_opts = "".join('<option value="%d"%s>%s, %s (%s)</option>' % (
        s["id"], " selected" if str(s["id"]) == str(form.get("store_id", session.get("store_id", 1))) else "",
        h(s["city"]), h(s["address"]), h(s["hours"])) for s in stores())
    slot_opts = "".join('<option%s>%s</option>' % (" selected" if s == form.get("slot") else "", h(s))
                        for s in _slots())
    pay = form.get("payment", "card_courier")
    pay_html = "".join('<label><input type="radio" name="payment" value="%s"%s><span>%s<small>%s</small></span></label>'
                       % (k, " checked" if k == pay else "", h(a), h(b)) for k, (a, b) in PAYMENTS.items())
    fee = 0 if dtype == "pickup" or total >= FREE_DELIVERY_FROM else DELIVERY_FEE
    login_hint = "" if user else ('<div class="flash info" style="margin:0 0 10px">Вже маєте акаунт? '
                                  '<a href="/login?return=/checkout" style="color:#E2001A;font-weight:700">Увійдіть</a>, '
                                  'щоб замовлення зберіглося в історії та нараховувались бонуси.</div>')
    items = "".join('<div class="ln"><span>%s × %d</span><span>%s</span></div>' % (h(p["name"]), qty, money(s))
                    for p, qty, s in lines)
    return (
        '<div class="wrap">%s<h1 class="pghead">Оформлення замовлення</h1>'
        '<form method="post" action="/checkout" class="twocol">%s<div class="box form" style="max-width:none;margin:0">'
        '%s<h2>1. Контактні дані</h2><div class="row"><div><label>Ім\'я та прізвище</label>'
        '<input type="text" name="name" value="%s" required>%s</div>'
        '<div><label>Телефон</label><input type="tel" name="phone" value="%s" placeholder="+380 XX XXX XX XX" required>%s</div></div>'
        '<label>E-mail (для чека)</label><input type="email" name="email" value="%s">%s'
        '<h2 style="margin-top:24px">2. Спосіб отримання</h2><div class="radios">'
        '<label><input type="radio" name="delivery_type" value="courier"%s><span>Кур\'єрська доставка<small>'
        '%d грн, безкоштовно від %d грн. Мінімальне замовлення — %d грн</small></span></label>'
        '<label><input type="radio" name="delivery_type" value="pickup"%s><span>Самовивіз з магазину<small>'
        'Безкоштовно, замовлення буде зібрано протягом 2 годин</small></span></label></div>%s'
        '<label>Адреса доставки (місто, вулиця, будинок, квартира)</label>'
        '<input type="text" name="address" value="%s">%s'
        '<label>Магазин самовивозу</label><select name="store_id">%s</select>'
        '<label>Дата та час</label><select name="slot">%s</select>'
        '<h2 style="margin-top:24px">3. Оплата</h2><div class="radios">%s</div>'
        '<label>Коментар до замовлення</label><textarea name="comment" rows="2" maxlength="500">%s</textarea>'
        '<label class="chk"><input type="checkbox" name="replace" value="1"%s> Якщо товару немає — '
        'замінити на аналогічний</label>'
        '<label class="chk"><input type="checkbox" name="agree" value="1"%s> Я погоджуюсь з умовами '
        '<a href="/delivery" style="color:#E2001A">публічної оферти</a></label>%s'
        '</div><div class="summary"><h3 style="margin-bottom:8px">Ваше замовлення</h3>%s'
        '<div class="ln" style="border-top:1px solid #eee;padding-top:8px"><span>Товари</span><span>%s грн</span></div>'
        '<div class="ln"><span>Доставка</span><span>%s</span></div>'
        '<div class="ln tot"><span>До сплати</span><span>%s грн</span></div>'
        '<button class="btn block" style="margin-top:12px">Підтвердити замовлення</button>'
        '<a class="btn ghost block sm" style="margin-top:8px" href="/cart">Змінити кошик</a></div></form></div>'
        % (_crumbs(("Кошик", "/cart"), ("Оформлення", None)), csrf_field(), login_hint,
           val("name", ("%s %s" % (user["first_name"] or "", user["last_name"] or "")).strip() if user else ""),
           err("name"), val("phone", user["phone"] if user else ""), err("phone"),
           val("email", user["email"] if user else ""), err("email"),
           " checked" if dtype == "courier" else "", DELIVERY_FEE, FREE_DELIVERY_FROM, MIN_COURIER_ORDER,
           " checked" if dtype == "pickup" else "", err("delivery_type"),
           val("address"), err("address"), st_opts, slot_opts, pay_html, val("comment"),
           " checked" if form.get("replace", "" if form else "1") else "", " checked" if form.get("agree") else "", err("agree"),
           items, money(total), "безкоштовно" if fee == 0 else "%s грн" % money(fee), money(total + fee)))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    lines, total = cart_lines()
    if not lines:
        flash("Кошик порожній — додайте товари, щоб оформити замовлення.", "info")
        return redirect("/cart")
    if request.method == "GET":
        return _page("Оформлення замовлення — АТБ", _checkout_form({}, {}, lines, total))
    f = request.form
    errors = {}
    name = (f.get("name") or "").strip()[:120]
    phone = norm_phone(f.get("phone"))
    email = (f.get("email") or "").strip()[:190]
    dtype = f.get("delivery_type")
    address = (f.get("address") or "").strip()[:250]
    if len(name) < 2:
        errors["name"] = "Вкажіть ім'я отримувача."
    if not phone:
        errors["phone"] = "Невірний формат телефону. Приклад: +380 67 123 45 67"
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errors["email"] = "Невірна адреса e-mail."
    if dtype not in ("courier", "pickup"):
        errors["delivery_type"] = "Оберіть спосіб отримання."
    if dtype == "courier":
        if len(address) < 8:
            errors["address"] = "Вкажіть повну адресу доставки."
        if total < MIN_COURIER_ORDER:
            errors["delivery_type"] = "Мінімальна сума для доставки — %d грн." % MIN_COURIER_ORDER
    store = store_by_id(f.get("store_id")) if dtype == "pickup" else None
    if dtype == "pickup" and not store:
        errors["delivery_type"] = "Оберіть магазин самовивозу."
    payment = f.get("payment") if f.get("payment") in PAYMENTS else "card_courier"
    if not f.get("agree"):
        errors["agree"] = "Необхідно погодитись з умовами."
    if errors:
        flash("Перевірте правильність заповнення форми.", "error")
        return _page("Оформлення замовлення — АТБ", _checkout_form(f, errors, lines, total), status=422)
    fee = 0 if dtype == "pickup" or total >= FREE_DELIVERY_FROM else DELIVERY_FEE
    user = current_user()
    order_no = "ATB-%07d" % secrets.randbelow(10 ** 7)
    comment = (f.get("comment") or "").strip()[:450]
    if f.get("replace"):
        comment = ("[заміна дозволена] " + comment).strip()
    try:
        oid = ex("INSERT INTO orders (order_no, user_id, customer_name, phone, email, delivery_type, address, "
                 "store_id, slot, payment, comment, subtotal, delivery_fee, status) "
                 "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'new')",
                 (order_no, user["id"] if user else None, name, phone, email or None, dtype,
                  address if dtype == "courier" else None, store["id"] if store else None,
                  (f.get("slot") or "")[:40], payment, comment, total, fee))
        for p, qty, s in lines:
            ex("INSERT INTO order_items (order_id, product_id, name, price, qty) VALUES (%s,%s,%s,%s,%s)",
               (oid, p["id"], p["name"], p["price"], qty))
    except Exception as e:
        atblog.log("www.error", atblog.client_ip(request), err=str(e)[:200], where="checkout")
        flash("Не вдалося створити замовлення. Спробуйте пізніше або зателефонуйте 0-800-500-415.", "error")
        return _page("Оформлення замовлення — АТБ", _checkout_form(f, {}, lines, total), status=503)
    atblog.log("www.order_placed", atblog.client_ip(request), order_no=order_no,
               user_id=user["id"] if user else None, items=len(lines), total=round(total + fee, 2),
               delivery_type=dtype, payment=payment)
    session["cart"] = {}
    session.setdefault("my_orders", []).append(order_no)
    session.modified = True
    return redirect("/checkout/success?order=%s" % order_no)


def _order_details(o):
    items = q("SELECT * FROM order_items WHERE order_id=%s", (o["id"],))
    rows = "".join('<tr><td>%s</td><td>%s грн</td><td>%s</td><td><b>%s грн</b></td></tr>'
                   % (h(i["name"]), money(i["price"]), ("%g" % float(i["qty"])), money(float(i["price"]) * float(i["qty"])))
                   for i in items)
    if o["delivery_type"] == "pickup":
        st = store_by_id(o["store_id"])
        where = "Самовивіз: %s" % (("%s, %s" % (st["city"], st["address"])) if st else "—")
    else:
        where = "Доставка: %s" % (o["address"] or "—")
    return ('<table class="list"><tr><th>Товар</th><th>Ціна</th><th>К-сть</th><th>Сума</th></tr>%s</table>'
            '<p style="margin-top:14px">%s<br>Час: %s<br>Оплата: %s<br>Отримувач: %s, %s</p>'
            '<p style="font-size:16px"><b>Разом: %s грн</b> (товари %s + доставка %s)</p>'
            % (rows, h(where), h(o["slot"] or "за домовленістю"),
               h(PAYMENTS.get(o["payment"], (o["payment"] or "—",))[0]),
               h(o["customer_name"] or ""), h(o["phone"] or ""),
               money(float(o["subtotal"]) + float(o["delivery_fee"])), money(o["subtotal"]), money(o["delivery_fee"])))


@app.get("/checkout/success")
def checkout_success():
    no = request.args.get("order", "")
    if no not in (session.get("my_orders") or []):
        return redirect("/")
    o = q1("SELECT * FROM orders WHERE order_no=%s", (no,))
    if not o:
        return redirect("/")
    body = ('<div class="wrap">%s<div class="box" style="max-width:820px;margin:20px auto">'
            '<div style="font-size:54px">✅</div><h2>Дякуємо! Замовлення %s прийнято</h2>'
            '<p>Оператор зателефонує вам найближчим часом для підтвердження. Статус замовлення можна '
            'відстежувати в <a href="/account" style="color:#E2001A">особистому кабінеті</a>.</p>%s'
            '<a class="btn" href="/">Повернутися до покупок</a></div></div>'
            % (_crumbs(("Замовлення %s" % no, None)), h(no), _order_details(o)))
    return _page("Замовлення %s — АТБ" % no, body)


# ---------------------------------------------------------------------------
# Customer accounts
# ---------------------------------------------------------------------------

def _find_user(login):
    login = (login or "").strip()
    phone = norm_phone(login)
    if phone:
        return q1("SELECT * FROM users WHERE phone=%s ORDER BY id LIMIT 1", (phone,))
    return q1("SELECT * FROM users WHERE email=%s ORDER BY id LIMIT 1", (login.lower(),))


def _login_form(login="", error=""):
    return ('<div class="wrap">%s<div class="box" style="max-width:480px;margin:20px auto">'
            '<h2>Вхід до кабінету</h2><form class="form" method="post" action="/login">%s'
            '<input type="hidden" name="return" value="%s">'
            '<label>Телефон або e-mail</label><input type="text" name="login" value="%s" autofocus required>'
            '<label>Пароль</label><input type="password" name="password" required>%s'
            '<label class="chk"><input type="checkbox" name="remember" value="1" checked> Запам\'ятати мене</label>'
            '<button class="btn block">Увійти</button></form>'
            '<p style="margin-top:14px;font-size:14px"><a href="/password-reset" style="color:#E2001A">Забули пароль?</a></p>'
            '<p style="font-size:14px">Ще немає акаунта? <a href="/register" style="color:#E2001A;font-weight:700">'
            'Зареєструватися</a></p></div></div>'
            % (_crumbs(("Вхід", None)), csrf_field(), h(safe_next("/account")), h(login),
               '<div class="err" style="color:#c0001a;font-size:13px;margin-top:6px">%s</div>' % h(error) if error else ""))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if current_user():
            return redirect("/account")
        return _page("Вхід — АТБ", _login_form())
    ip = atblog.client_ip(request)
    lg = (request.form.get("login") or "").strip()[:190]
    pw = request.form.get("password") or ""
    try:
        u = _find_user(lg)
    except Exception:
        u = None
    if not u or u["status"] != 10 or not check_pw(pw, u["password"]):
        atblog.log("www.login_failed", ip, login=lg, user_exists=bool(u))
        return _page("Вхід — АТБ", _login_form(lg, "Невірний логін або пароль."), status=200)
    session["uid"] = u["id"]
    try:
        ex("UPDATE users SET last_login=NOW() WHERE id=%s", (u["id"],))
    except Exception:
        pass
    atblog.log("www.login", ip, user_id=u["id"], login=lg)
    flash("Вітаємо, %s!" % (u["first_name"] or "покупець"), "success")
    return redirect(safe_next("/account"))


@app.route("/logout", methods=["GET", "POST"])
def logout():
    if session.pop("uid", None):
        atblog.log("www.logout", atblog.client_ip(request))
    flash("Ви вийшли з кабінету.", "info")
    return redirect("/")


def _register_form(f, errors):
    def val(k):
        return h(f.get(k, ""))

    def err(k):
        return '<div class="err">%s</div>' % h(errors[k]) if k in errors else ""
    return ('<div class="wrap">%s<div class="box" style="max-width:560px;margin:20px auto">'
            '<h2>Реєстрація</h2><p>Створіть акаунт, щоб відстежувати замовлення, зберігати обране та '
            'отримувати персональні пропозиції.</p><form class="form" method="post" action="/register" '
            'style="max-width:none">%s<div class="row"><div><label>Ім\'я</label><input type="text" name="first_name" '
            'value="%s" required>%s</div><div><label>Прізвище</label><input type="text" name="last_name" value="%s">'
            '</div></div><label>Телефон</label><input type="tel" name="phone" value="%s" placeholder="+380 XX XXX XX XX" '
            'required>%s<label>E-mail</label><input type="email" name="email" value="%s" required>%s'
            '<div class="row"><div><label>Пароль</label><input type="password" name="password" required>%s</div>'
            '<div><label>Повторіть пароль</label><input type="password" name="password_repeat" required>%s</div></div>'
            '<div class="hint">Не менше 6 символів.</div>'
            '<label class="chk"><input type="checkbox" name="news" value="1"> Хочу отримувати новини та акції на e-mail</label>'
            '<label class="chk"><input type="checkbox" name="agree" value="1"%s> Погоджуюсь на обробку '
            'персональних даних</label>%s<button class="btn block">Зареєструватися</button></form>'
            '<p style="margin-top:14px;font-size:14px">Вже зареєстровані? <a href="/login" style="color:#E2001A;'
            'font-weight:700">Увійти</a></p></div></div>'
            % (_crumbs(("Реєстрація", None)), csrf_field(), val("first_name"), err("first_name"), val("last_name"),
               val("phone"), err("phone"), val("email"), err("email"), err("password"), err("password_repeat"),
               " checked" if f.get("agree") else "", err("agree")))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return _page("Реєстрація — АТБ", _register_form({}, {}))
    f = request.form
    errors = {}
    fn = (f.get("first_name") or "").strip()[:60]
    ln = (f.get("last_name") or "").strip()[:60]
    phone = norm_phone(f.get("phone"))
    email = (f.get("email") or "").strip().lower()[:190]
    pw = f.get("password") or ""
    if not fn:
        errors["first_name"] = "Вкажіть ім'я."
    if not phone:
        errors["phone"] = "Невірний формат телефону. Приклад: +380 67 123 45 67"
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errors["email"] = "Невірна адреса e-mail."
    if len(pw) < 6:
        errors["password"] = "Пароль має містити щонайменше 6 символів."
    elif pw != f.get("password_repeat"):
        errors["password_repeat"] = "Паролі не збігаються."
    if not f.get("agree"):
        errors["agree"] = "Необхідна згода на обробку даних."
    if not errors:
        if phone and q1("SELECT id FROM users WHERE phone=%s", (phone,)):
            errors["phone"] = "Цей номер телефону вже зареєстрований."
        if q1("SELECT id FROM users WHERE email=%s", (email,)):
            errors["email"] = "Цей e-mail вже зареєстрований."
    if errors:
        return _page("Реєстрація — АТБ", _register_form(f, errors), status=422)
    card = "2" + "%011d" % secrets.randbelow(10 ** 11)
    uid = ex("INSERT INTO users (phone, email, password, auth_key, first_name, last_name, bonus_card, status) "
             "VALUES (%s,%s,%s,%s,%s,%s,%s,10)",
             (phone, email, hash_pw(pw), secrets.token_urlsafe(24)[:32], fn, ln or None, card))
    session["uid"] = uid
    atblog.log("www.register", atblog.client_ip(request), user_id=uid, email=email, phone=phone)
    flash("Реєстрація успішна! Вам нараховано віртуальну картку АТБ.", "success")
    return redirect("/account")


@app.route("/password-reset", methods=["GET", "POST"])
def password_reset():
    if request.method == "POST":
        lg = (request.form.get("login") or "").strip()[:190]
        atblog.log("www.password_reset_request", atblog.client_ip(request), login=lg)
        flash("Якщо акаунт існує, ми надіслали інструкції з відновлення пароля на вказаний e-mail/телефон.", "info")
        return redirect("/login")
    body = ('<div class="wrap">%s<div class="box" style="max-width:480px;margin:20px auto"><h2>Відновлення пароля</h2>'
            '<p>Вкажіть телефон або e-mail, який ви використовували під час реєстрації.</p>'
            '<form class="form" method="post">%s<label>Телефон або e-mail</label><input type="text" name="login" required>'
            '<div style="margin-top:14px"><button class="btn block">Надіслати</button></div></form></div></div>'
            % (_crumbs(("Вхід", "/login"), ("Відновлення пароля", None)), csrf_field()))
    return _page("Відновлення пароля — АТБ", body)


def _acct_layout(user, active, content):
    nav = [("/account", "Мій профіль"), ("/account/orders", "Мої замовлення"), ("/wishlist", "Обране"),
           ("/account/password", "Змінити пароль")]
    links = "".join('<a href="%s"%s>%s</a>' % (u, ' class="on"' if u == active else "", h(l)) for u, l in nav)
    links += '<form method="post" action="/logout">%s<button>Вийти</button></form>' % csrf_field()
    return ('<div class="wrap">%s<h1 class="pghead">Мій кабінет</h1><div class="acctgrid"><div><div class="bonus">'
            'Картка АТБ<b>%s</b><small>%s %s</small></div><nav class="acctnav">%s</nav></div><div>%s</div></div></div>'
            % (_crumbs(("Мій кабінет", "/account")), h(" ".join(re.findall(r".{1,4}", user["bonus_card"] or "—"))),
               h(user["first_name"] or ""), h(user["last_name"] or ""), links, content))


def _orders_table(uid, limit=None):
    rows = q("SELECT * FROM orders WHERE user_id=%s ORDER BY created_at DESC" + (" LIMIT %d" % limit if limit else ""),
             (uid,))
    if not rows:
        return '<p style="color:#999">Ви ще не робили замовлень. <a href="/shop/catalog/all" style="color:#E2001A">До каталогу</a></p>'
    st = {"new": "Нове", "delivered": "Виконано", "cancelled": "Скасовано"}
    return ('<table class="list"><tr><th>Номер</th><th>Дата</th><th>Отримання</th><th>Сума</th><th>Статус</th></tr>%s</table>'
            % "".join('<tr><td><a href="/account/orders/%s" style="color:#E2001A">%s</a></td><td>%s</td><td>%s</td>'
                      '<td>%s грн</td><td><span class="status %s">%s</span></td></tr>'
                      % (h(o["order_no"]), h(o["order_no"]), o["created_at"].strftime("%d.%m.%Y %H:%M"),
                         "Доставка" if o["delivery_type"] == "courier" else "Самовивіз",
                         money(float(o["subtotal"]) + float(o["delivery_fee"])), h(o["status"]),
                         h(st.get(o["status"], o["status"]))) for o in rows))


def _need_login():
    return redirect("/login?return=" + request.path)


@app.get("/account")
def account():
    user = current_user()
    if not user:
        return _need_login()
    content = ('<div class="box" style="margin:0 0 16px"><h2>Особисті дані</h2>'
               '<form class="form" method="post" action="/account/profile" style="max-width:none">%s<div class="row">'
               '<div><label>Ім\'я</label><input type="text" name="first_name" value="%s"></div>'
               '<div><label>Прізвище</label><input type="text" name="last_name" value="%s"></div></div>'
               '<div class="row"><div><label>Телефон</label><input type="tel" value="%s" disabled></div>'
               '<div><label>E-mail</label><input type="email" value="%s" disabled></div></div>'
               '<div class="hint">Для зміни телефону або e-mail зверніться на гарячу лінію 0-800-500-415.</div>'
               '<div style="margin-top:14px"><button class="btn sm">Зберегти</button></div></form>'
               '<p style="margin-top:12px;font-size:13px;color:#999">З нами з %s</p></div>'
               '<div class="box" style="margin:0"><h2>Останні замовлення</h2>%s</div>'
               % (csrf_field(), h(user["first_name"] or ""), h(user["last_name"] or ""), h(user["phone"] or ""),
                  h(user["email"] or ""), user["created_at"].strftime("%d.%m.%Y") if user["created_at"] else "—",
                  _orders_table(user["id"], 5)))
    return _page("Мій кабінет — АТБ", _acct_layout(user, "/account", content))


@app.post("/account/profile")
def account_profile():
    user = current_user()
    if not user:
        return _need_login()
    ex("UPDATE users SET first_name=%s, last_name=%s WHERE id=%s",
       ((request.form.get("first_name") or "").strip()[:60] or user["first_name"],
        (request.form.get("last_name") or "").strip()[:60] or None, user["id"]))
    flash("Дані профілю збережено.", "success")
    return redirect("/account")


@app.get("/account/orders")
def account_orders():
    user = current_user()
    if not user:
        return _need_login()
    return _page("Мої замовлення — АТБ", _acct_layout(
        user, "/account/orders", '<div class="box" style="margin:0"><h2>Мої замовлення</h2>%s</div>'
        % _orders_table(user["id"])))


@app.get("/account/orders/<order_no>")
def account_order(order_no):
    user = current_user()
    if not user:
        return _need_login()
    o = q1("SELECT * FROM orders WHERE order_no=%s AND user_id=%s", (order_no, user["id"]))
    if not o:
        return _page("Not Found (#404)", _errbox("Not Found (#404)", "Замовлення не знайдено."), status=404)
    reorder = ('<form method="post" action="/account/orders/%s/repeat">%s<button class="btn sm green">'
               'Повторити замовлення</button></form>' % (h(order_no), csrf_field()))
    return _page("Замовлення %s — АТБ" % order_no, _acct_layout(
        user, "/account/orders", '<div class="box" style="margin:0"><h2>Замовлення %s від %s</h2>%s%s</div>'
        % (h(order_no), o["created_at"].strftime("%d.%m.%Y"), _order_details(o), reorder)))


@app.post("/account/orders/<order_no>/repeat")
def account_order_repeat(order_no):
    user = current_user()
    if not user:
        return _need_login()
    o = q1("SELECT id FROM orders WHERE order_no=%s AND user_id=%s", (order_no, user["id"]))
    if o:
        c = cart()
        for i in q("SELECT product_id, qty FROM order_items WHERE order_id=%s", (o["id"],)):
            c[str(i["product_id"])] = min(99, c.get(str(i["product_id"]), 0) + int(float(i["qty"])))
        session.modified = True
        flash("Товари із замовлення %s додано до кошика." % order_no, "success")
    return redirect("/cart")


@app.route("/account/password", methods=["GET", "POST"])
def account_password():
    user = current_user()
    if not user:
        return _need_login()
    err = ""
    if request.method == "POST":
        old, new, rep = (request.form.get(k) or "" for k in ("old", "new", "repeat"))
        if not check_pw(old, user["password"]):
            err = "Поточний пароль введено невірно."
        elif len(new) < 6:
            err = "Новий пароль має містити щонайменше 6 символів."
        elif new != rep:
            err = "Паролі не збігаються."
        else:
            ex("UPDATE users SET password=%s WHERE id=%s", (hash_pw(new), user["id"]))
            atblog.log("www.password_changed", atblog.client_ip(request), user_id=user["id"])
            flash("Пароль змінено.", "success")
            return redirect("/account")
    content = ('<div class="box" style="margin:0"><h2>Зміна пароля</h2><form class="form" method="post">%s'
               '<label>Поточний пароль</label><input type="password" name="old" required>'
               '<label>Новий пароль</label><input type="password" name="new" required>'
               '<label>Повторіть новий пароль</label><input type="password" name="repeat" required>%s'
               '<div style="margin-top:14px"><button class="btn sm">Змінити пароль</button></div></form></div>'
               % (csrf_field(), '<div class="err">%s</div>' % h(err) if err else ""))
    return _page("Зміна пароля — АТБ", _acct_layout(user, "/account/password", content))


# ---------------------------------------------------------------------------
# Stores & static pages
# ---------------------------------------------------------------------------

@app.get("/stores")
def stores_page():
    allst = stores()
    cities = []
    for s in allst:
        if s["city"] not in cities:
            cities.append(s["city"])
    city = request.args.get("city", "")
    shown = [s for s in allst if not city or s["city"] == city]
    sel = str(session.get("store_id", 1))
    hour = datetime.now().hour
    chips = '<a href="/stores"%s>Усі міста</a>' % (' class="on"' if not city else "")
    chips += "".join('<a href="/stores?city=%s"%s>%s</a>' % (h(c), ' class="on"' if c == city else "", h(c))
                     for c in cities)
    cards = []
    for s in shown:
        try:
            a, b = [int(x[:2]) for x in s["hours"].split("–")]
            is_open = a <= hour < b
        except (ValueError, AttributeError):
            is_open = True
        cards.append('<div class="store%s"><span class="c">%s</span><b>АТБ, %s</b><span>\U0001F552 %s · '
                     '<span class="open">%s</span></span><span>\U0001F4DE %s</span>'
                     '<form method="post" action="/stores/select">%s<input type="hidden" name="store_id" value="%d">'
                     '<button class="btn sm%s" style="margin-top:6px">%s</button></form></div>'
                     % (" sel" if str(s["id"]) == sel else "", h(s["city"]), h(s["address"]), h(s["hours"]),
                        "Відчинено" if is_open else "Зачинено", h(s["phone"] or ""), csrf_field(), s["id"],
                        " ghost" if str(s["id"]) == sel else "",
                        "✓ Ваш магазин" if str(s["id"]) == sel else "Обрати цей магазин"))
    body = ('<div class="wrap">%s<h1 class="pghead">Магазини АТБ</h1><p style="color:#666">Понад 1300 магазинів '
            'у 300+ населених пунктах України. Оберіть магазин, щоб бачити актуальну наявність товарів і '
            'забирати замовлення самовивозом.</p><div class="cities">%s</div><div class="storegrid">%s</div></div>'
            % (_crumbs(("Магазини", None)), chips, "".join(cards)))
    return _page("Магазини — АТБ", body)


@app.post("/stores/select")
def stores_select():
    st = store_by_id(request.form.get("store_id"))
    if st:
        session["store_id"] = st["id"]
        flash("Обрано магазин: %s, %s" % (st["city"], st["address"]), "success")
    return redirect(safe_next("/stores"))


def _static(title, html, crumbs=None):
    body = '<div class="wrap">%s<h1 class="pghead">%s</h1>%s</div>' % (
        _crumbs((crumbs or title, None)), h(title), html)
    return _page("%s — АТБ" % title, body)


@app.get("/about")
def about():
    return _static("Про нас", """
<div class="feat"><div><b>1993</b>рік заснування в Дніпрі</div><div><b>1300+</b>магазинів по Україні</div>
<div><b>45 000+</b>працівників</div><div><b>3.5 млн</b>покупців щодня</div></div>
<div class="box"><h2>АТБ — мережа магазинів економ-класу №1 в Україні</h2>
<p>Корпорація «АТБ» розпочала свою діяльність у 1993 році в Дніпрі. Сьогодні це найбільша національна мережа
продуктових магазинів, яка щодня обслуговує мільйони покупців у більш ніж 300 населених пунктах країни.</p>
<p>Наша місія — забезпечити українців якісними товарами першої необхідності за доступними цінами.
Ми досягаємо цього завдяки власній логістичній інфраструктурі, прямим контрактам з виробниками та
ефективним бізнес-процесам.</p>
<h3>Що ми робимо</h3><ul>
<li>Власні розподільчі центри та автопарк, які доставляють товари в магазини щодня;</li>
<li>Власні торгові марки «Своя Лінія», «Розумний вибір», «Повна Чаша» та De Luxe Foods &amp; Goods;</li>
<li>Підтримка українських виробників — понад 90% асортименту вироблено в Україні;</li>
<li>Соціальні проєкти, підтримка ЗСУ та громад, що постраждали від війни.</li></ul>
<h3>Реквізити</h3><p>ТОВ «АТБ-Маркет», 49000, м. Дніпро, вул. Урицького, 45. Код ЄДРПОУ 30487219.</p></div>""")


@app.get("/delivery")
def delivery():
    return _static("Оплата та доставка", """
<div class="box"><h2>Доставка</h2>
<table class="list"><tr><th>Спосіб</th><th>Вартість</th><th>Терміни</th></tr>
<tr><td>Кур'єрська доставка</td><td>%d грн, безкоштовно від %d грн</td><td>від 2 годин, щодня 9:00–21:00</td></tr>
<tr><td>Самовивіз з магазину</td><td>безкоштовно</td><td>замовлення готове протягом 2 годин</td></tr></table>
<p style="margin-top:12px">Мінімальна сума замовлення для доставки — %d грн. Доставка доступна в Києві, Дніпрі,
Харкові, Львові, Одесі, Запоріжжі та Вінниці; самовивіз — з будь-якого магазину, де працює онлайн-замовлення.</p>
<h3>Як ми зважуємо товари</h3><p>Вагові товари (овочі, фрукти, м'ясо) зважуються під час збирання замовлення.
Остаточна сума може відрізнятися від суми в кошику не більше ніж на 10%%.</p>
<h2 style="margin-top:22px">Оплата</h2><ul><li>Карткою Visa/Mastercard при отриманні (у кур'єра є POS-термінал);</li>
<li>Готівкою при отриманні;</li><li>Онлайн-оплата карткою за посиланням із SMS після підтвердження замовлення;</li>
<li>Бонусами з картки АТБ від Райфу.</li></ul>
<h3>Повернення</h3><p>Якщо товар не відповідає якості, повідомте кур'єра під час отримання або зателефонуйте
на гарячу лінію 0-800-500-415 протягом 24 годин — ми повернемо кошти або замінимо товар.</p>
<h3>Публічна оферта</h3><p>Оформлюючи замовлення, ви погоджуєтесь з умовами продажу товарів дистанційним способом
відповідно до Закону України «Про захист прав споживачів». Продаж алкогольних напоїв та тютюнових виробів
здійснюється лише особам, які досягли 18 років, і тільки в магазині (самовивіз) з пред'явленням документа.</p></div>"""
                   % (DELIVERY_FEE, FREE_DELIVERY_FROM, MIN_COURIER_ORDER))


VACANCIES = [
    ("Продавець-касир", "Київ, Дніпро, Львів, Одеса", "від 21 000 грн", "Обслуговування покупців на касі, "
     "викладка товару. Без досвіду — навчимо!"),
    ("Комплектувальник онлайн-замовлень", "Київ, Харків", "від 23 000 грн", "Збирання замовлень інтернет-магазину, "
     "перевірка якості та термінів придатності."),
    ("Водій-експедитор (кат. C)", "Дніпро, Запоріжжя", "від 35 000 грн", "Доставка товарів з розподільчого центру "
     "до магазинів мережі."),
    ("Кур'єр на власному авто", "Київ", "від 30 000 грн + пальне", "Доставка онлайн-замовлень покупцям, гнучкий графік."),
    ("Директор магазину", "Вінниця, Полтава", "від 45 000 грн", "Управління командою магазину, контроль товарообігу."),
    ("Комірник на розподільчий центр", "Дніпро", "від 26 000 грн", "Приймання та відвантаження товару, робота з ТЗД."),
    ("Python/PHP розробник (e-commerce)", "Дніпро / віддалено", "за результатами співбесіди",
     "Розвиток сайту atbmarket.com та мобільного застосунку, інтеграції з ERP."),
]


@app.route("/career", methods=["GET", "POST"])
def career():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:100]
        phone = norm_phone(request.form.get("phone"))
        vac = (request.form.get("vacancy") or "")[:100]
        if not name or not phone:
            flash("Вкажіть ім'я та коректний номер телефону.", "error")
        else:
            atblog.log("www.career_apply", atblog.client_ip(request), vacancy=vac, phone=phone)
            flash("Дякуємо, %s! Рекрутер зателефонує вам протягом 2 робочих днів." % name, "success")
        return redirect("/career")
    vac = "".join('<div class="vac"><h3>%s</h3><div style="font-size:13px;color:#888">\U0001F4CD %s</div>'
                  '<div class="sal">%s</div><p style="margin:6px 0 0">%s</p></div>' % tuple(h(x) for x in v)
                  for v in VACANCIES)
    opts = "".join("<option>%s</option>" % h(v[0]) for v in VACANCIES)
    return _static("Кар'єра в АТБ", """
<div class="feat"><div><b>45 000+</b>колег по всій Україні</div><div><b>Офіційно</b>з першого дня, «біла» зарплата</div>
<div><b>Навчання</b>безкоштовне, з наставником</div><div><b>Ріст</b>70%% директорів виросли з продавців</div></div>
<div class="twocol"><div class="box" style="margin:0"><h2>Актуальні вакансії</h2>%s</div>
<div class="summary"><h3>Залишити заявку</h3><form class="form" method="post">%s
<label>Вакансія</label><select name="vacancy">%s</select><label>Ім'я</label><input type="text" name="name" required>
<label>Телефон</label><input type="tel" name="phone" placeholder="+380" required>
<label>Місто</label><input type="text" name="city"><div style="margin-top:14px"><button class="btn block">
Надіслати</button></div></form><p class="note">Або телефонуйте: 0-800-500-415 (відділ персоналу)</p></div></div>"""
                   % (vac, csrf_field(), opts))


@app.get("/partners")
def partners():
    host = (request.host or "localhost").split(":")[0]
    sup = (os.environ.get("PORTAL_PORTS", "8081,8082,8083,8444").split(",") + ["", "", ""])[2]
    return _static("Партнерам", """
<div class="box"><h2>Постачальникам</h2><p>АТБ співпрацює з понад 2000 виробників і дистриб'юторів. Щоб
запропонувати свій товар, зареєструйтеся на <a href="http://%s:%s/" style="color:#E2001A">порталі постачальника</a>:
там ви зможете подати комерційну пропозицію, завантажити специфікації та відстежувати замовлення.</p>
<h3>Вимоги до постачальників</h3><ul><li>Офіційна реєстрація юридичної особи або ФОП;</li>
<li>Наявність сертифікатів якості та декларацій виробника;</li><li>Можливість доставки на розподільчі центри
мережі (Дніпро, Київ, Львів, Одеса, Харків);</li><li>Робота з електронним документообігом (EDI).</li></ul>
<h2 style="margin-top:22px">Орендодавцям</h2><p>Розглядаємо пропозиції щодо оренди та купівлі приміщень площею
від 600 м² з паркуванням та зоною розвантаження. Надсилайте пропозиції на realty@atbmarket.com.</p>
<h2 style="margin-top:22px">Власна торгова марка</h2><p>Виробникам, які бажають виготовляти продукцію під
власними марками АТБ, пишіть на privatelabel@atbmarket.com.</p></div>""" % (h(host), h(sup)))


@app.get("/card")
def card():
    return _static("Картка АТБ від Райфу", """
<div class="hero" style="margin-top:0"><div class="big" style="background:linear-gradient(120deg,#2d2d2d,#E2001A)">
<h1>Кешбек до 5% на покупки в АТБ</h1><p>Безкоштовна картка АТБ від Райффайзен Банку: обслуговування 0 грн,
кешбек бонусами, які можна витрачати в будь-якому магазині мережі.</p>
<span class="deco">\U0001F4B3</span></div><div class="hside"><div class="sm"><span class="i">\U0001F381</span><div>
<b>5% кешбеку</b><span>на товари власних марок АТБ</span></div></div><div class="sm"><span class="i">\U0001F4B0</span>
<div><b>2% кешбеку</b><span>на всі інші покупки в АТБ</span></div></div></div></div>
<div class="box"><h2>Як отримати картку</h2><ul><li>Оформіть онлайн у застосунку Raiffeisen Online;</li>
<li>або в будь-якому відділенні Райффайзен Банку з паспортом та ІПН;</li>
<li>Прив'яжіть картку до свого кабінету на atbmarket.com, щоб бачити історію бонусів.</li></ul>
<p style="font-size:12px;color:#999">Банківські послуги надає АТ «Райффайзен Банк». Ліцензія НБУ №10 від 10.10.2011.
Детальні умови — на сайті банку.</p></div>""")


@app.get("/faq")
def faq():
    items = [
        ("Як змінити або скасувати замовлення?", "Зателефонуйте на гарячу лінію 0-800-500-415 до того, як замовлення "
         "передано кур'єру. Після цього змінити склад замовлення неможливо."),
        ("Чи можна замовити алкоголь з доставкою?", "Ні. Алкогольні напої можна придбати лише в магазині або "
         "оформити самовивіз з пред'явленням документа."),
        ("Чому ціна на сайті відрізняється від ціни в магазині?", "Ціни на сайті актуальні для обраного магазину. "
         "Деякі акції діють лише офлайн."),
        ("Як нараховуються бонуси?", "Бонуси нараховуються на картку АТБ від Райфу протягом 3 днів після покупки."),
        ("Я забув пароль від кабінету", "Скористайтеся формою «Забули пароль?» на сторінці входу."),
    ]
    html = "".join('<details class="box" style="margin:10px 0"><summary style="cursor:pointer;font-weight:700">%s'
                   '</summary><p style="margin-top:10px">%s</p></details>' % (h(a), h(b)) for a, b in items)
    return _static("Питання та відповіді", html)


@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /cart\nDisallow: /checkout\nDisallow: /account\n"
                    "Disallow: /search\nDisallow: /*?sort=\n", mimetype="text/plain")


@app.errorhandler(404)
def not_found(_e):
    return _page("Not Found (#404)", _errbox("Not Found (#404)", "Сторінку не знайдено."), status=404)


@app.errorhandler(405)
def bad_method(_e):
    return _page("Method Not Allowed (#405)", _errbox("Method Not Allowed (#405)",
                                                      "Метод запиту не підтримується."), status=405)


@app.get("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    # wait for DB
    for _ in range(60):
        try:
            _conn().close()
            break
        except Exception:
            time.sleep(2)
    atblog.banner()
    app.run(host="0.0.0.0", port=80, threaded=True)
