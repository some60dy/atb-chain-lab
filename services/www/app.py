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
MySQL, so extraction returns genuine values.
"""
import os
import re
import time
from html import escape

import pymysql
from flask import Flask, request, Response
import atblog

app = Flask(__name__)

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
# Presentation helpers (store chrome). These are pure HTML/CSS: they do NOT
# touch the injectable SQL, the status codes, or the atblog events above.
# ---------------------------------------------------------------------------

STYLE = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  background:#f2f2f2;color:#333;line-height:1.4;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
.wrap{max-width:1240px;margin:0 auto;padding:0 16px}
/* top dark header */
.hdr{background:#2d2d2d;color:#fff}
.hdr .wrap{display:flex;align-items:center;gap:14px;padding:12px 16px}
.brand{font-weight:900;font-size:30px;color:#E2001A;letter-spacing:1px}
.catbtn{background:#E2001A;color:#fff;border:0;border-radius:22px;padding:11px 18px;
  font-weight:700;font-size:14px;white-space:nowrap;cursor:pointer;display:inline-flex;
  align-items:center;gap:8px}
.hsearch{flex:1;min-width:120px;display:flex;background:#fff;border-radius:22px;
  align-items:center;padding:0 16px}
.hsearch input{flex:1;border:0;outline:0;padding:11px 8px;font-size:14px;color:#333}
.hsearch .mag{color:#E2001A;font-size:16px}
.lang{display:flex;align-items:center;gap:6px;font-size:13px;white-space:nowrap}
.lang .tog{width:30px;height:16px;background:#E2001A;border-radius:10px;position:relative}
.lang .tog::after{content:"";position:absolute;right:2px;top:2px;width:12px;height:12px;
  background:#fff;border-radius:50%}
.addr{font-size:11px;line-height:1.25;white-space:nowrap;opacity:.9}
.addr b{color:#fff;font-weight:600}
.acct{font-size:12px;white-space:nowrap;text-align:center}
.wish{font-size:13px;white-space:nowrap}
.cart{background:#E2001A;color:#fff;border-radius:22px;padding:9px 16px;font-weight:700;
  font-size:13px;white-space:nowrap;display:inline-flex;align-items:center;gap:8px}
/* secondary nav */
.snav{background:#fff;border-bottom:1px solid #e6e6e6}
.snav .wrap{display:flex;align-items:center;gap:20px;padding:11px 16px;flex-wrap:wrap}
.snav a{font-size:13px;color:#333;white-space:nowrap}
.snav a.active{color:#E2001A;font-weight:700}
.snav a:hover{color:#E2001A}
.snav .phone{margin-left:auto;color:#E2001A;font-weight:700;font-size:13px}
/* category tiles */
.tiles{display:grid;grid-template-columns:repeat(8,1fr);gap:12px;margin:20px 0}
.tile{background:#fff;border-radius:12px;padding:16px 8px;text-align:center;
  display:flex;flex-direction:column;align-items:center;gap:8px;box-shadow:0 1px 3px rgba(0,0,0,.06);
  transition:box-shadow .15s,transform .15s}
.tile:hover{box-shadow:0 6px 16px rgba(0,0,0,.12);transform:translateY(-2px)}
.tile .ic{width:58px;height:58px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:30px}
.tile .lb{font-size:12px;color:#333;line-height:1.25;min-height:30px}
/* section */
.section{background:#fff;border-radius:12px;padding:18px 18px 24px;margin:20px 0;
  box-shadow:0 1px 3px rgba(0,0,0,.06)}
.sechead{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.sechead h2{font-size:22px;font-weight:800;color:#2d2d2d}
.sechead .right{display:flex;align-items:center;gap:14px}
.sechead .showall{color:#E2001A;font-weight:600;font-size:14px}
.sechead .arrows span{display:inline-flex;align-items:center;justify-content:center;
  width:32px;height:32px;border:1px solid #e0e0e0;border-radius:50%;color:#888;cursor:pointer}
.crumbs{font-size:13px;color:#9a9a9a;margin:16px 0 4px}
.crumbs a:hover{color:#E2001A}
.activefilter{background:#fff6ed;border:1px solid #ffd9b0;color:#8a4b00;border-radius:10px;
  padding:10px 14px;font-size:14px;margin:12px 0}
.activefilter code{background:#fff;border:1px solid #ffd9b0;border-radius:6px;padding:1px 6px;
  font-family:ui-monospace,Menlo,Consolas,monospace}
/* product grid + cards */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(205px,1fr));gap:14px}
.card{position:relative;background:#fff;border:1px solid #efefef;border-radius:12px;
  padding:14px;display:flex;flex-direction:column;transition:box-shadow .15s}
.card:hover{box-shadow:0 8px 22px rgba(20,20,30,.10)}
.card .toprow{display:flex;align-items:center;justify-content:space-between;font-size:12px}
.stars{color:#f5a623;letter-spacing:1px}
.stars .off{color:#e0e0e0}
.reviews{color:#9a9a9a;margin-left:5px}
.heart{color:#c9c9c9;font-size:16px;cursor:pointer}
.badges{position:absolute;top:40px;left:14px;display:flex;flex-direction:column;gap:5px;z-index:2}
.badge{font-size:11px;font-weight:700;color:#fff;border-radius:6px;padding:2px 7px;
  width:max-content}
.badge.disc{background:#E2001A}
.badge.nov{background:#8bc34a}
.badge.own{background:#E2001A;display:inline-flex;align-items:center;gap:4px}
.thumb{height:130px;display:flex;align-items:center;justify-content:center;font-size:58px;
  margin:6px 0 10px}
.card .nm{font-size:14px;color:#2d2d2d;min-height:38px;line-height:1.35}
.priceblk{display:flex;align-items:flex-end;justify-content:space-between;margin-top:10px}
.oldp{font-size:13px;color:#9a9a9a;text-decoration:line-through}
.newp{color:#E2001A;font-weight:900;font-size:26px;line-height:1}
.newp sup{font-size:13px;font-weight:800;vertical-align:super}
.newp .u{display:block;font-size:11px;font-weight:600;color:#9a9a9a}
.addbtn{border:0;background:#78BE20;color:#fff;width:42px;height:42px;border-radius:50%;
  font-size:18px;cursor:pointer;flex:0 0 auto;align-self:flex-end}
.addbtn:hover{filter:brightness(1.05)}
.notice{background:#fff;border:1px dashed #e0e0e0;border-radius:12px;padding:28px;
  text-align:center;color:#9a9a9a}
/* error page */
.errpage{max-width:760px;margin:40px auto}
.errcard{background:#fff;border:1px solid #efefef;border-top:5px solid #E2001A;
  border-radius:12px;padding:28px}
.errcard h1{font-size:22px;margin-bottom:6px;color:#E2001A}
.errcard p{color:#9a9a9a;margin-bottom:14px}
.errcard pre{background:#2d2d2d;color:#ff9f9f;border-radius:10px;padding:16px;overflow:auto;
  font-size:13px;font-family:ui-monospace,Menlo,Consolas,monospace}
.foot{color:#9a9a9a;font-size:13px;border-top:1px solid #e6e6e6;margin-top:24px}
.foot .wrap{padding:24px 16px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:18px}
.foot .fcol{display:flex;flex-direction:column;gap:6px}
.foot .fcol b{color:#555;margin-bottom:2px}
.foot .fcol a{color:#e30613;text-decoration:none}.foot .fcol a:hover{text-decoration:underline}
@media(max-width:1000px){.tiles{grid-template-columns:repeat(4,1fr)}}
@media(max-width:760px){
  .hdr .wrap{flex-wrap:wrap}
  .hsearch{order:5;flex-basis:100%}
  .addr,.acct,.wish{display:none}
  .tiles{grid-template-columns:repeat(2,1fr)}
}
"""

# secondary-nav links (left to right); first is active red
SNAV = [
    ("\U0001F4CD Акції", True),
    ("Партнерам ⌄", False),
    ("О нас ⌄", False),
    ("Картка АТБ від Райфу", False),
    ("Товари власних брендів", False),
    ("Кар'єра", False),
    ("Магазини", False),
    ("Оплата та доставка", False),
]

# 8 category tiles: (label, bg colour, emoji)
TILES = [
    ("Овочі та фрукти", "#e9f7e8", "\U0001F345"),
    ("Бакалея", "#f3f3f3", "\U0001F35D"),
    ("Хлібобулочні вироби", "#fbf1e0", "\U0001F35E"),
    ("Молочні продукти", "#e4f6fb", "\U0001F95B"),
    ("М'ясо та яйця", "#fdeeee", "\U0001F969"),
    ("Алкогольні напої", "#f0ebf6", "\U0001F943"),
    ("Безалкогольні напої", "#fdeef0", "\U0001F9C3"),
    ("Товари для тварин", "#eef6fb", "\U0001F436"),
]

# emoji per product name stem (purely cosmetic)
_EMOJI = [
    ("молок", "\U0001F95B"),   # молоко
    ("сир", "\U0001F9C0"),               # сир
    ("хліб", "\U0001F35E"),         # хліб
    ("кав", "☕"),                    # кава
    ("вод", "\U0001F4A7"),               # вода
    ("чай", "\U0001F375"),               # чай
    ("яйц", "\U0001F95A"),               # яйця
    ("масл", "\U0001F9C8"),         # масло
]


def _emoji_for(name):
    low = (name or "").lower()
    for stem, ico in _EMOJI:
        if stem in low:
            return ico
    return "\U0001F6D2"


def _fmt_int_dec(price):
    try:
        f = float(price)
    except (TypeError, ValueError):
        return escape(str(price)), "00"
    return str(int(f)), "%02d" % int(round((f - int(f)) * 100))


def fetch_products(limit=48):
    """Live product grid data. Caller wraps for DB-down resilience."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,name,price FROM products LIMIT %s", (limit,))
            return list(cur.fetchall())
    finally:
        conn.close()


def fetch_group8_attrs():
    """Available filter attributes for group 8 (the injectable parameter group)."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT attr_id FROM product_attr "
                "WHERE group_id=8 ORDER BY attr_id")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def _header():
    return (
        '<header class="hdr"><div class="wrap">'
        '<a class="brand" href="/">АТБ</a>'
        '<button class="catbtn">▦ Каталог '
        'товарів ⌄</button>'
        '<form class="hsearch" onsubmit="return false">'
        '<span class="mag">\U0001F50D</span>'
        '<input placeholder="Я шукаю…" aria-label="Пошук">'
        '</form>'
        '<div class="lang"><span class="tog"></span>Рус</div>'
        '<div class="addr">\U0001F4CD Змінити адресу/магазин<br>'
        '<b>Київ, вул. Архітектора Городецького, 9</b></div>'
        '<div class="acct">\U0001F464<br>Мій кабінет</div>'
        '<div class="wish">♡ 5</div>'
        '<div class="cart">\U0001F6D2 23 &middot; 250.00 грн</div>'
        '</div></header>'
    )


def _snav():
    items = []
    for label, active in SNAV:
        cls = ' class="active"' if active else ""
        items.append('<a%s>%s</a>' % (cls, escape(label)))
    items.append('<span class="phone">\U0001F4DE 0-800-500-415 (8:00-22:00)</span>')
    return '<nav class="snav"><div class="wrap">%s</div></nav>' % "".join(items)


def _tiles(attrs, category="novetly"):
    """Category tiles. Each links to the injectable filter, attr id varied per tile."""
    base = attrs if attrs else [490]
    out = []
    for i, (label, bg, emoji) in enumerate(TILES):
        attr = base[i % len(base)]
        href = "/shop/catalog/%s?filter[8][%s]=1" % (escape(str(category)), escape(str(attr)))
        out.append(
            '<a class="tile" href="%s"><span class="ic" style="background:%s">%s</span>'
            '<span class="lb">%s</span></a>' % (href, bg, emoji, escape(label)))
    return '<div class="wrap"><div class="tiles">%s</div></div>' % "".join(out)


def _stars(pid):
    filled = 2 + (pid % 3)  # 2..4
    s = ""
    for i in range(5):
        s += "★" if i < filled else '<span class="off">★</span>'
    reviews = 3 + (pid * 7) % 40
    return ('<span class="stars">%s<span class="reviews">(%d)</span></span>'
            % (s, reviews))


def _card_badges(pid):
    out = ['<span class="badge disc">-15%</span>']
    if pid % 5 == 0:
        out.append('<span class="badge nov">новинка</span>')
    if pid % 7 == 0:
        out.append('<span class="badge own">▰ власна '
                   'марка АТБ</span>')
    return '<div class="badges">%s</div>' % "".join(out)


def _card(row):
    pid = row[0]
    name = row[1]
    price = row[2]
    try:
        oldp = "%.2f" % (float(price) * 1.18)
    except (TypeError, ValueError):
        oldp = ""
    intp, decp = _fmt_int_dec(price)
    oldhtml = ('<span class="oldp">%s грн</span>' % escape(oldp)) if oldp else ""
    return (
        '<div class="card">'
        '<div class="toprow">%s<span class="heart">♡</span></div>'
        '%s'
        '<div class="thumb">%s</div>'
        '<div class="nm">%s</div>'
        '<div style="margin-top:8px">%s</div>'
        '<div class="priceblk"><div>'
        '<span class="newp">%s<sup>.%s</sup>'
        '<span class="u">грн/шт</span></span></div>'
        '<button class="addbtn" type="button" title="До кошика">\U0001F6D2</button>'
        '</div></div>'
        % (_stars(pid), _card_badges(pid), _emoji_for(name), escape(str(name)),
           oldhtml, intp, decp)
    )


def _product_grid(products):
    if products is None:
        return ('<div class="notice">\U0001F6D2 Каталог '
                'тимчасово '
                'недоступний.</div>')
    if not products:
        return ('<div class="notice">Товарів '
                'не знайдено.</div>')
    return '<div class="grid">%s</div>' % "".join(_card(r) for r in products)


def _section(title, products):
    return (
        '<div class="wrap"><div class="section">'
        '<div class="sechead"><h2>%s</h2><div class="right">'
        '<a class="showall">Показати '
        'всі</a><span class="arrows"><span>‹</span>'
        '<span>›</span></span></div></div>'
        '%s</div></div>' % (escape(title), _product_grid(products))
    )


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
            '<div class="fcol"><b>АТБ онлайн</b>%s</div>'
            '<div class="fcol"><span>&copy; 2026 АТБ-Маркет &middot; www.atbmarket.com</span>'
            '<span>Гаряча лінія: 0-800-500-415</span></div>'
            '</div></footer>' % portals)


def _page(title, body, status=200):
    html = (
        '<!doctype html><html lang="uk"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>%s</title><style>%s</style></head><body>%s</body></html>'
        % (escape(title), STYLE, body)
    )
    return Response(html, status=status, mimetype="text/html")


def _store_page(title, category, active_filter=None, heading=None,
                section_title=None, show_tiles=True, status=200):
    """Full store layout: chrome + category tiles + product section (all live DB)."""
    try:
        products = fetch_products()
    except Exception:
        products = None
    try:
        attrs = fetch_group8_attrs()
    except Exception:
        attrs = None

    parts = [_header(), _snav()]
    if show_tiles:
        parts.append(_tiles(attrs, category))
    if heading:
        parts.append('<div class="wrap"><div class="crumbs">'
                     '<a href="/">Головна</a> / '
                     'Каталог / %s</div></div>'
                     % escape(heading))
    if active_filter:
        g, a, v = active_filter
        parts.append('<div class="wrap"><div class="activefilter">Active filter: '
                     '<code>filter[%s][%s]=%s</code></div></div>'
                     % (escape(str(g)), escape(str(a)), escape(str(v))))
    parts.append(_section(section_title or "Акція "
                          "«Економія»",
                          products))
    parts.append(_footer())
    return _page(title, "".join(parts), status=status)


def _error_page(sqlstate_line):
    body = (
        _header() + _snav() +
        '<div class="wrap"><div class="errpage"><div class="errcard">'
        '<h1>Database Exception</h1>'
        '<p>Під час обробки '
        'фільтра каталогу '
        'сталася помилка '
        'бази даних.</p>'
        '<pre>%s\n  in /var/www/ishop/vendor/yiisoft/yii2/db/Command.php:1304</pre>'
        '</div></div></div>' % sqlstate_line + _footer()
    )
    return body


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    return _store_page("ATB Market — онлайн-"
                       "супермаркет",
                       "novetly")


@app.get("/shop/catalog/<category>")
def catalog(category):
    ip = atblog.client_ip(request)
    # Flask parses filter[8][490]=1 into request.args as 'filter[8][490]'
    found = None
    for k in request.args:
        m = re.match(r"^filter\[(?P<g>[^\]]+)\]\[(?P<a>.+)\]$", k)
        if m:
            found = (m.group("g"), m.group("a"), request.args.get(k))
            break
    if not found:
        return _store_page("ATB Market — %s" % category, category,
                           heading="%s" % category)
    group, attr, value = found
    suspicious = bool(INJECT_SIGNS.search(attr))
    try:
        run_filter(group, attr, value)
        if suspicious:
            atblog.log("www.sqli_probe_true", ip, category=category,
                       filter_key=attr, qs=request.query_string.decode("latin1"),
                       status=200, msg="injected key evaluated TRUE (boolean oracle)")
        return _store_page("ATB Market — %s" % category, category,
                           active_filter=(group, attr, value),
                           heading="%s" % category, status=200)
    except pymysql.err.ProgrammingError as e:
        code = e.args[0] if e.args else 0
        atblog.log("www.sqli_error", ip, category=category, filter_key=attr,
                   qs=request.query_string.decode("latin1"), status=500,
                   sqlstate="42000", err=str(e)[:200],
                   msg="SQL syntax error from injected key (#42000)")
        line = ("PDOException: SQLSTATE[42000]: Syntax error or access "
                "violation: %s" % escape(str(code)))
        return _page("ATB Market — помилка",
                     _error_page(line), status=500)
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
