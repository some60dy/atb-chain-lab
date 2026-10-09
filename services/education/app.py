"""Step 1b - education.atbmarket.com Moodle employee-training portal.

A small Moodle 3.9 emulation (Boost-like UI, Ukrainian) backed by the
`education-db` MySQL (`moodle` schema seeded from seed/mysql-moodle/).

Unauthenticated config-disclosure bug in the moco_news block's ajax endpoint:
POST /md/blocks/moco_news/ajax.php?procedure=getPosts leaks DB/SMTP creds,
the Moodle password salt, and the site admin user ids with no auth.
"""
import calendar
import hashlib
import hmac
import html
import json
import os
import secrets
import time
import warnings
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import crypt  # bcrypt ($2y$) via libxcrypt; deprecated in 3.12 but present

import pymysql
import pymysql.cursors
from flask import Flask, Response, g, jsonify, redirect, request, session

import atblog

app = Flask(__name__)
app.secret_key = os.environ.get("MOODLE_SECRET") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_NAME="MoodleSession", SESSION_COOKIE_HTTPONLY=True)

CONFIG_LEAK = {
    "dbuser": "tmx",
    "dbpass": "DGGS845k45lkk340",
    "smtpuser": "education@atbmarket.com",
    "smtppass": "Edu003868$",
    "passwordsaltmain": "4STvnJrt33TTbdIY4Qt",
    "siteadmins": "2,3,5,8999,56948",
}

# config.php equivalents
CFG = {
    "dbhost": os.environ.get("MOODLE_DB_HOST", "education-db"),
    "dbname": os.environ.get("MOODLE_DB_NAME", "moodle"),
    "dbuser": os.environ.get("MOODLE_DB_USER", CONFIG_LEAK["dbuser"]),
    "dbpass": os.environ.get("MOODLE_DB_PASS", CONFIG_LEAK["dbpass"]),
    "passwordsaltmain": CONFIG_LEAK["passwordsaltmain"],
    "release": "3.9.4+ (Build: 20210114)",
}

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Kyiv")
except Exception:  # pragma: no cover
    TZ = timezone(timedelta(hours=3))

GUEST_ID = 1


@app.route("/md/blocks/moco_news/ajax.php", methods=["GET", "POST"])
def moco_news_ajax():
    ip = atblog.client_ip(request)
    procedure = request.form.get("procedure") or request.args.get("procedure")
    if procedure == "getPosts":
        atblog.log("education.config_disclosure", ip, procedure="getPosts",
                   msg="unauthenticated Moodle config disclosure")
        return jsonify(CONFIG_LEAK), 200
    if procedure == "getNews":
        atblog.log("education.ajax", ip, procedure=procedure)
        return jsonify(posts=_news_posts()), 200
    atblog.log("education.ajax", ip, procedure=procedure)
    return jsonify(error="unknown procedure", procedure=procedure), 400


NEWS = [
    {"title": "Оновлено курс «Інформаційна безпека» — пройдіть до 30.11"},
    {"title": "Нова версія мобільного застосунку АТБ 8.0.48 для персоналу"},
    {"title": "Технічні роботи на порталі постачальників у суботу"},
]


def _news_posts(limit=3):
    try:
        rows = qall("SELECT d.id, d.name, d.timemodified FROM mdl_forum_discussions d "
                    "WHERE d.forum=1 ORDER BY d.pinned DESC, d.timemodified DESC LIMIT %s", (limit,))
        if rows:
            return [{"id": r["id"], "title": r["name"], "date": userdate(r["timemodified"], "short"),
                     "url": f"/mod/forum/discuss.php?d={r['id']}"} for r in rows]
    except Exception:
        pass
    return NEWS


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def db():
    if "db" not in g:
        g.db = pymysql.connect(host=CFG["dbhost"], user=CFG["dbuser"], password=CFG["dbpass"],
                               database=CFG["dbname"], charset="utf8mb4", autocommit=True,
                               connect_timeout=3, cursorclass=pymysql.cursors.DictCursor)
    return g.db


@app.teardown_appcontext
def _close_db(exc):
    conn = g.pop("db", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


def qall(sql, args=()):
    with db().cursor() as cur:
        cur.execute(sql, args)
        return list(cur.fetchall())


def qone(sql, args=()):
    rows = qall(sql, args)
    return rows[0] if rows else None


def qexec(sql, args=()):
    with db().cursor() as cur:
        cur.execute(sql, args)
        return cur.lastrowid


def now():
    return int(time.time())


# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------
e = lambda s: html.escape("" if s is None else str(s), quote=True)  # noqa: E731

MONTHS_GEN = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня",
              "серпня", "вересня", "жовтня", "листопада", "грудня"]
MONTHS_NOM = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень",
              "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]
WEEKDAYS = ["понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"]
WD_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]


def dt(ts):
    return datetime.fromtimestamp(int(ts or 0), TZ)


def userdate(ts, fmt="full"):
    if not ts:
        return "Ніколи"
    d = dt(ts)
    if fmt == "short":
        return d.strftime("%d.%m.%Y, %H:%M")
    if fmt == "date":
        return f"{d.day} {MONTHS_GEN[d.month - 1]} {d.year}"
    if fmt == "dayname":
        return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"
    if fmt == "time":
        return d.strftime("%H:%M")
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]} {d.year}, {d.strftime('%H:%M')}"


def timeago(ts):
    if not ts:
        return "Ніколи"
    s = max(0, now() - int(ts))
    if s < 60:
        return "щойно"
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d >= 365:
        return f"{d // 365} р. {(d % 365) // 30} міс."
    if d:
        return f"{d} дн. {h} год."
    if h:
        return f"{h} год. {m} хв."
    return f"{m} хв."


def num(x, places=2):
    if x is None:
        return "-"
    return f"{float(x):.{places}f}".replace(".", ",")


def fullname(u):
    if not u:
        return ""
    return f"{u['firstname']} {u['lastname']}".strip()


AV_COLORS = ["#0f6cbf", "#2e7d32", "#6a1b9a", "#ef6c00", "#c62828", "#00838f", "#4e342e", "#37474f", "#ad1457"]


def avatar(u, size=35):
    if not u or u.get("id") == GUEST_ID:
        ini, col = "?", "#9aa0a6"
    else:
        ini = (u["firstname"][:1] + u["lastname"][:1]).upper()
        col = AV_COLORS[u["id"] % len(AV_COLORS)]
    return (f"<span class=\"avatar\" style=\"width:{size}px;height:{size}px;line-height:{size}px;"
            f"font-size:{int(size * .4)}px;background:{col}\">{e(ini)}</span>")


def nl2br(s):
    return e(s).replace("\n", "<br>")


# ---------------------------------------------------------------------------
# auth / session
# ---------------------------------------------------------------------------
class Bounce(Exception):
    def __init__(self, resp):
        super().__init__("bounce")
        self.resp = resp


@app.errorhandler(Bounce)
def _bounce(ex):
    return ex.resp


def validate_password(user, password):
    """Moodle validate_internal_user_password(): bcrypt, then legacy salted md5."""
    stored = user.get("password") or ""
    if stored.startswith("$2y$") or stored.startswith("$2b$"):
        try:
            return hmac.compare_digest(crypt.crypt(password, stored) or "", stored)
        except Exception:
            return False
    if len(stored) == 32:
        salted = hashlib.md5((password + CFG["passwordsaltmain"]).encode()).hexdigest()
        plain = hashlib.md5(password.encode()).hexdigest()
        return hmac.compare_digest(salted, stored) or hmac.compare_digest(plain, stored)
    return False


def sesskey():
    if "sesskey" not in session:
        session["sesskey"] = secrets.token_urlsafe(8)[:10]
    return session["sesskey"]


def logintoken():
    if "logintoken" not in session:
        session["logintoken"] = secrets.token_hex(16)
    return session["logintoken"]


def require_sesskey():
    if request.values.get("sesskey") != session.get("sesskey"):
        raise Bounce(error_page("Неправильний ключ сесії (sesskey). Ваша сесія, можливо, застаріла — "
                                "поверніться назад та оновіть сторінку.", 403))


_siteadmins_cache = {}


def siteadmins():
    if "v" not in _siteadmins_cache or _siteadmins_cache["t"] < now() - 60:
        try:
            r = qone("SELECT value FROM mdl_config WHERE name='siteadmins'")
            _siteadmins_cache["v"] = {int(x) for x in (r["value"] if r else "").split(",") if x.strip()}
        except Exception:
            _siteadmins_cache["v"] = set()
        _siteadmins_cache["t"] = now()
    return _siteadmins_cache["v"]


def current_user():
    if "user" in g:
        return g.user
    g.user = None
    uid = session.get("uid")
    if uid:
        u = qone("SELECT * FROM mdl_user WHERE id=%s AND deleted=0 AND suspended=0", (uid,))
        if u:
            g.user = u
            if uid != GUEST_ID and u["lastaccess"] < now() - 60:
                qexec("UPDATE mdl_user SET lastaccess=%s, lastip=%s WHERE id=%s",
                      (now(), atblog.client_ip(request), uid))
        else:
            session.clear()
    return g.user


def is_guest(u):
    return not u or u["id"] == GUEST_ID


def is_admin(u):
    return bool(u) and u["id"] in siteadmins()


def require_login(allow_guest=True):
    u = current_user()
    if not u or (not allow_guest and is_guest(u)):
        session["wantsurl"] = request.full_path.rstrip("?")
        raise Bounce(redirect("/login/index.php"))
    return u


def logstore(eventname, component, action, uid=0, courseid=0, ctx=0):
    try:
        qexec("INSERT INTO mdl_logstore_standard_log (eventname, component, action, userid, courseid, "
              "contextinstanceid, ip, timecreated) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
              (eventname, component, action, uid, courseid, ctx, atblog.client_ip(request), now()))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# course access
# ---------------------------------------------------------------------------
def get_course(cid):
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        cid = 0
    c = qone("SELECT * FROM mdl_course WHERE id=%s AND id<>1", (cid,))
    if not c:
        raise Bounce(error_page("Не вдалося знайти дані в таблиці course", 404))
    return c


def enrolment(cid, uid):
    return qone("SELECT * FROM mdl_user_enrolments WHERE courseid=%s AND userid=%s AND status=0", (cid, uid))


def course_role(c, u):
    if not u:
        return None
    if is_admin(u):
        return "teacher"
    if not is_guest(u):
        en = enrolment(c["id"], u["id"])
        if en:
            return "teacher" if en["roleid"] in (1, 3, 4) else "student"
    if c["guest"]:
        return "guest"
    return None


def require_course(cid):
    """require_login($course): returns (course, role, user) or bounces."""
    c = get_course(cid)
    u = require_login()
    role = course_role(c, u)
    if role is None:
        if is_guest(u):
            raise Bounce(error_page("Гостьовий доступ до цього курсу заборонено. Будь ласка, увійдіть.",
                                    403, link=("/login/index.php", "Вхід")))
        raise Bounce(redirect(f"/enrol/index.php?id={c['id']}"))
    if role != "guest" and not is_admin(u):
        qexec("UPDATE mdl_user_enrolments SET timeaccess=%s WHERE courseid=%s AND userid=%s",
              (now(), c["id"], u["id"]))
    return c, role, u


def get_cm(cmid, modname):
    try:
        cmid = int(cmid)
    except (TypeError, ValueError):
        cmid = 0
    cm = qone("SELECT * FROM mdl_course_modules WHERE id=%s AND modname=%s AND visible=1", (cmid, modname))
    if not cm:
        raise Bounce(error_page("Ідентифікатор модуля курсу неправильний", 404))
    return cm


def mark_complete(cmid, u, role):
    if role in ("student", "teacher") and not is_guest(u):
        qexec("INSERT IGNORE INTO mdl_course_modules_completion (coursemoduleid, userid, completionstate, "
              "timemodified) VALUES (%s,%s,1,%s)", (cmid, u["id"], now()))


def my_courses(u):
    if is_guest(u):
        return []
    return qall("SELECT c.*, e.roleid, e.timeaccess FROM mdl_user_enrolments e JOIN mdl_course c "
                "ON c.id=e.courseid WHERE e.userid=%s AND e.status=0 AND c.visible=1 ORDER BY c.sortorder",
                (u["id"],))


def progress(cid, uid):
    total = qone("SELECT COUNT(*) n FROM mdl_course_modules WHERE course=%s AND completion=1 AND visible=1",
                 (cid,))["n"]
    done = qone("SELECT COUNT(*) n FROM mdl_course_modules_completion cc JOIN mdl_course_modules cm "
                "ON cm.id=cc.coursemoduleid WHERE cm.course=%s AND cm.completion=1 AND cc.userid=%s",
                (cid, uid))["n"]
    return done, total


def teachers_of(cid):
    return qall("SELECT u.id, u.firstname, u.lastname FROM mdl_user_enrolments e JOIN mdl_user u ON u.id=e.userid "
                "WHERE e.courseid=%s AND e.roleid IN (3,4) ORDER BY e.id", (cid,))


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------
PAGE_CSS = """
*{box-sizing:border-box}
html{font-size:15px}
body{margin:0;font-family:'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;background:#f2f4f7;color:#1d2125;line-height:1.5}
a{color:#0f6cbf;text-decoration:none}a:hover{text-decoration:underline}
code{background:#eef1f4;padding:1px 5px;border-radius:4px;font-size:.88em}
.navbar{position:sticky;top:0;z-index:20;background:#fff;border-bottom:1px solid #dee2e6;display:flex;align-items:center;gap:6px;padding:0 16px;height:56px;box-shadow:0 2px 4px rgba(0,0,0,.05)}
.navbar .brand{display:flex;align-items:center;gap:9px;font-weight:700;color:#1d2125;margin-right:14px}
.navbar .brand:hover{text-decoration:none}
.logo{width:32px;height:32px;border-radius:7px;background:#e30613;color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:800;font-size:.85rem;letter-spacing:-.5px}
.navbar .nl{color:#1d2125;padding:16px 10px;font-size:.93rem;border-bottom:3px solid transparent}
.navbar .nl.act{border-bottom-color:#0f6cbf}.navbar .nl:hover{text-decoration:none;background:#f5f6f7}
.navbar .spacer{flex:1}
.navbar .ico{font-size:1.1rem;padding:8px;color:#495057;position:relative}
.navbar .ico:hover{text-decoration:none}
.navbar .muted{color:#6a737b;font-size:.9rem}
.umenu{position:relative}
.umenu summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:6px;font-size:.92rem}
.umenu summary::-webkit-details-marker{display:none}
.umenu summary:hover{background:#f5f6f7}
.umenu .dd{position:absolute;right:0;top:46px;background:#fff;border:1px solid #dee2e6;border-radius:6px;box-shadow:0 6px 18px rgba(0,0,0,.12);min-width:210px;padding:6px 0;z-index:30}
.umenu .dd a{display:block;padding:7px 16px;color:#1d2125}.umenu .dd a:hover{background:#f5f6f7;text-decoration:none}
.umenu .dd hr{border:0;border-top:1px solid #e9ecef;margin:5px 0}
.avatar{display:inline-block;border-radius:50%;color:#fff;text-align:center;font-weight:600;flex:none}
.layout{display:flex;align-items:flex-start;min-height:calc(100vh - 56px)}
.drawer{width:260px;flex:none;background:#fff;border-right:1px solid #dee2e6;align-self:stretch;padding:14px 0;font-size:.92rem}
.drawer a{display:flex;gap:10px;align-items:center;padding:7px 20px;color:#1d2125}
.drawer a:hover{background:#f5f6f7;text-decoration:none}
.drawer a.act{background:#e7f0fa;color:#0f6cbf;font-weight:600}
.drawer .hd{padding:12px 20px 4px;font-size:.75rem;color:#6a737b;text-transform:uppercase;letter-spacing:.04em}
.drawer .sub{padding-left:38px;font-size:.88rem}
.main{flex:1;min-width:0;padding:22px 28px 50px}
.pagehead{background:#fff;border:1px solid #dee2e6;border-radius:8px;padding:18px 22px;margin-bottom:18px}
.pagehead h1{margin:0 0 6px;font-size:1.6rem;font-weight:600}
.crumbs{font-size:.86rem;color:#6a737b}.crumbs a{color:#0f6cbf}.crumbs span.sep{margin:0 6px;color:#adb5bd}
.cols{display:flex;gap:18px;align-items:flex-start}.cols>.col-main{flex:1;min-width:0}.cols>.col-side{width:300px;flex:none}
.card{background:#fff;border:1px solid #dee2e6;border-radius:8px;padding:16px 20px;margin-bottom:18px}
.card h2,.card h3{margin:0 0 12px;font-size:1.15rem;font-weight:600}
.card h4{margin:12px 0 6px}
.block h3{font-size:1rem}
.btn{display:inline-block;background:#0f6cbf;color:#fff;border:1px solid #0f6cbf;border-radius:6px;padding:7px 15px;font-size:.93rem;cursor:pointer;font-family:inherit}
.btn:hover{background:#0c589c;text-decoration:none}
.btn.sec{background:#ced4da;border-color:#ced4da;color:#1d2125}.btn.sec:hover{background:#b8c0c7}
.btn.wide{width:100%;padding:10px}
.btn[disabled]{opacity:.55;cursor:not-allowed}
input[type=text],input[type=password],input[type=email],input[type=date],input[type=time],input[type=search],textarea,select{width:100%;padding:8px 10px;border:1px solid #ced4da;border-radius:6px;font:inherit;background:#fff}
textarea{min-height:140px}
input:focus,textarea:focus,select:focus{outline:none;border-color:#0f6cbf;box-shadow:0 0 0 2px rgba(15,108,191,.2)}
label.f{display:block;font-size:.88rem;color:#495057;margin:12px 0 4px;font-weight:600}
.alert{padding:12px 16px;border-radius:6px;margin-bottom:16px;border:1px solid}
.alert.err{background:#fbe7e7;border-color:#f3c2c2;color:#a21d1d}
.alert.ok{background:#e6f4ea;border-color:#b7dfc2;color:#1e6b34}
.alert.info{background:#e7f0fa;border-color:#bcd6f0;color:#0b4f8a}
.alert.warn{background:#fff4e0;border-color:#f6d9a6;color:#8a5300}
table.gt{width:100%;border-collapse:collapse;font-size:.92rem}
table.gt th{text-align:left;background:#f8f9fa;border-bottom:2px solid #dee2e6;padding:9px 10px;font-weight:600}
table.gt td{border-bottom:1px solid #e9ecef;padding:9px 10px;vertical-align:top}
table.gt tr:hover td{background:#fafbfc}
table.generaltable{border-collapse:collapse;margin:10px 0}table.generaltable td,table.generaltable th{border:1px solid #dee2e6;padding:7px 10px}
table.generaltable th{background:#f8f9fa}
.muted{color:#6a737b;font-size:.88rem}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.75rem;font-weight:600;background:#e9ecef;color:#495057}
.badge.ok{background:#d6f0dd;color:#1e6b34}.badge.bad{background:#f8d7da;color:#a21d1d}.badge.blue{background:#dbeafb;color:#0b4f8a}
.ccards{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px}
.ccard{background:#fff;border:1px solid #dee2e6;border-radius:8px;overflow:hidden;display:flex;flex-direction:column;transition:box-shadow .15s}
.ccard:hover{box-shadow:0 4px 14px rgba(0,0,0,.1)}
.ccard .cover{height:96px;display:flex;align-items:center;justify-content:center;font-size:2.2rem;color:#fff;background-image:linear-gradient(135deg,rgba(255,255,255,.18) 25%,transparent 25%,transparent 50%,rgba(255,255,255,.18) 50%,rgba(255,255,255,.18) 75%,transparent 75%);background-size:28px 28px}
.ccard .cb{padding:12px 14px;flex:1;display:flex;flex-direction:column;gap:4px}
.ccard .cat{font-size:.78rem;color:#6a737b}
.ccard .nm{font-weight:600;color:#1d2125}
.pbar{height:7px;background:#e9ecef;border-radius:4px;overflow:hidden;margin-top:6px}.pbar>i{display:block;height:100%;background:#0f6cbf}
.section{background:#fff;border:1px solid #dee2e6;border-radius:8px;margin-bottom:16px}
.section>h3{margin:0;padding:14px 20px;border-bottom:1px solid #e9ecef;font-size:1.12rem}
.section .ssum{padding:10px 20px 0;color:#495057}
.acts{list-style:none;margin:0;padding:8px 10px}
.acts li{display:flex;align-items:center;gap:12px;padding:9px 10px;border-radius:6px}
.acts li:hover{background:#f8f9fa}
.acts .mi{width:34px;height:34px;border-radius:7px;display:flex;align-items:center;justify-content:center;font-size:1.05rem;flex:none}
.mi.page{background:#e7f0fa}.mi.resource{background:#fdecea}.mi.url{background:#e8f5e9}.mi.quiz{background:#f3e5f5}.mi.forum{background:#fff3e0}.mi.assign{background:#e0f2f1}
.acts .an{flex:1}.acts .an small{display:block;color:#6a737b;font-size:.8rem}
.chk{font-size:.78rem;padding:3px 9px;border-radius:12px;border:1px solid #ced4da;color:#6a737b;white-space:nowrap}
.chk.done{background:#d6f0dd;border-color:#a8d8b5;color:#1e6b34}
.cbanner{border-radius:8px;color:#fff;padding:22px 24px;margin-bottom:18px;display:flex;gap:18px;align-items:center}
.cbanner .ic{font-size:2.6rem;background:rgba(255,255,255,.18);width:72px;height:72px;border-radius:12px;display:flex;align-items:center;justify-content:center;flex:none}
.cbanner h1{margin:0;font-size:1.5rem}.cbanner .sn{opacity:.85;font-size:.88rem}
.content{font-size:.97rem}.content h3{margin-top:18px}
.post{border:1px solid #dee2e6;border-radius:8px;padding:14px 18px;margin-bottom:12px;background:#fff}
.post.reply{margin-left:40px;background:#fcfcfd}
.post .ph{display:flex;gap:12px;align-items:center;margin-bottom:8px}
.post .ph b{display:block}
.qblock{display:flex;gap:16px;margin-bottom:16px}
.qinfo{width:130px;flex:none;background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;padding:10px;font-size:.82rem}
.qinfo b{display:block;font-size:.95rem}
.qtext{flex:1;background:#e7f3f5;border:1px solid #cde4e8;border-radius:8px;padding:14px 18px}
.qtext.right{background:#e6f4ea;border-color:#b7dfc2}.qtext.wrong{background:#fbe7e7;border-color:#f3c2c2}
.qtext .opts{margin:10px 0 0;padding:0;list-style:none}
.qtext .opts li{padding:5px 0}
.qtext .fb{margin-top:10px;padding:8px 12px;background:#fff8e1;border-radius:6px;font-size:.9rem}
.qnav{display:flex;flex-wrap:wrap;gap:6px}.qnav a{width:34px;height:40px;border:1px solid #ced4da;border-radius:4px;display:flex;align-items:flex-end;justify-content:center;font-size:.85rem;color:#1d2125;padding-bottom:3px;background:linear-gradient(#fff 60%,#e9ecef 60%)}
.timer{font-weight:700;color:#a21d1d}
.cal{width:100%;border-collapse:collapse;table-layout:fixed}
.cal th{padding:8px;font-size:.85rem;color:#495057;border-bottom:2px solid #dee2e6}
.cal td{border:1px solid #e9ecef;height:96px;vertical-align:top;padding:4px 6px;font-size:.8rem}
.cal td.out{background:#fafbfc;color:#adb5bd}.cal td.today{background:#eef6ff}
.cal td .dn{font-weight:600;display:block;margin-bottom:3px}
.cal .ev{display:block;padding:1px 5px;border-radius:3px;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#1d2125;font-size:.76rem}
.ev.site{background:#e7f0fa;border-left:3px solid #0f6cbf}.ev.course{background:#fdecea;border-left:3px solid #c62828}.ev.close{background:#f3e5f5;border-left:3px solid #6a1b9a}.ev.user{background:#e8f5e9;border-left:3px solid #2e7d32}
.mcal{width:100%;border-collapse:collapse;text-align:center;font-size:.82rem}.mcal th{color:#6a737b;font-weight:600;padding:3px}.mcal td{padding:4px 0}
.mcal td.has a{display:inline-block;width:24px;height:24px;line-height:24px;border-radius:50%;background:#0f6cbf;color:#fff}
.mcal td.today{font-weight:700;color:#e30613}
.evitem{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid #eef0f2}.evitem:last-child{border-bottom:0}
.evitem .dt{width:54px;flex:none;text-align:center;background:#f1f3f5;border-radius:6px;padding:4px 0;font-size:.75rem;color:#495057}
.evitem .dt b{display:block;font-size:1.2rem;color:#1d2125}
.hero{display:flex;flex-wrap:wrap;gap:22px;align-items:flex-start;margin-bottom:10px}
.hero-text{flex:1 1 320px}.hero-text h1{margin:.1em 0 .3em;font-size:1.7rem}.hero-text p{color:#495057}
.login-card{flex:0 0 330px;background:#fff;border:1px solid #dee2e6;border-radius:10px;padding:22px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.login-card h2{margin:0 0 6px;font-size:1.15rem}
.news{background:#fff;border:1px solid #dee2e6;border-radius:8px;padding:14px 18px;margin-top:14px}
.news h3{margin:0 0 8px;font-size:1rem}
#news-list{list-style:none;margin:0;padding:0;font-size:.9rem;color:#495057}
#news-list li{padding:7px 0;border-bottom:1px solid #eef0f2}#news-list li:last-child{border-bottom:none}
#news-list small{color:#8a9099;margin-left:6px}
.footer{background:#1d2125;color:#aeb4ba;padding:22px 28px;font-size:.85rem;display:flex;flex-wrap:wrap;gap:10px 30px;justify-content:space-between}
.footer a{color:#dee2e6}
.tabs{display:flex;gap:4px;border-bottom:1px solid #dee2e6;margin-bottom:16px;flex-wrap:wrap}
.tabs a{padding:8px 14px;border:1px solid transparent;border-bottom:0;border-radius:6px 6px 0 0;color:#495057}
.tabs a.act{border-color:#dee2e6;background:#fff;color:#1d2125;margin-bottom:-1px;font-weight:600}
dl.prof{display:grid;grid-template-columns:200px 1fr;gap:6px 14px;margin:0}dl.prof dt{color:#6a737b}dl.prof dd{margin:0}
@media(max-width:900px){.drawer{display:none}.cols{flex-direction:column}.cols>.col-side{width:100%}.main{padding:16px}.navbar .nl{display:none}.login-card{flex:1 1 100%}}
"""

NEWS_JS = """
// Load the "Новини" block the same way the moco_news Moodle block does.
// <!-- moco_news block ajax: /md/blocks/moco_news/ajax.php -->
// moco_news 1.4: procedures getNews (block) / getPosts (legacy, admin dashboard)
(function () {
  var list = document.getElementById('news-list');
  if (!list) { return; }
  var body = new URLSearchParams();
  body.set('procedure', 'getNews');
  fetch('/md/blocks/moco_news/ajax.php', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString()
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var posts = (data && data.posts) || [];
      if (!posts.length) {
        list.innerHTML =
          '<li>Наразі немає нових оголошень.</li>' +
          '<li>Перевірте розклад обовʼязкових тренінгів.</li>';
        return;
      }
      list.innerHTML = '';
      posts.forEach(function (p) {
        var li = document.createElement('li');
        var t = p.title || String(p);
        if (p.url) {
          var a = document.createElement('a'); a.href = p.url; a.textContent = t; li.appendChild(a);
        } else { li.textContent = t; }
        if (p.date) { var s = document.createElement('small'); s.textContent = p.date; li.appendChild(s); }
        list.appendChild(li);
      });
    })
    .catch(function (e) {
      console.log('moco_news load failed', e);
      list.innerHTML = '<li>Не вдалося завантажити новини.</li>';
    });
})();
"""

MOD_ICON = {"page": "📄", "resource": "📎", "url": "🔗", "quiz": "📝", "forum": "💬", "assign": "📤"}
MOD_NAME = {"page": "Сторінка", "resource": "Файл", "url": "Гіперпосилання", "quiz": "Тест", "forum": "Форум",
            "assign": "Завдання"}


def news_block():
    return ("<!-- moco_news block ajax: /md/blocks/moco_news/ajax.php -->"
            "<div class=\"news block\"><h3>News / Новини</h3>"
            "<ul id=\"news-list\"><li>Завантаження новин…</li></ul>"
            "<div style=\"margin-top:8px;font-size:.85rem\"><a href=\"/mod/forum/view.php?f=1\">Старіші теми…</a></div>"
            "</div>")


def _navbar(u, active):
    def nl(href, label, key):
        return f"<a class=\"nl{' act' if active == key else ''}\" href=\"{href}\">{label}</a>"

    left = ("<a class=\"brand\" href=\"/\"><span class=\"logo\">АТБ</span><span>ATB Education</span></a>"
            + nl("/", "Головна", "home"))
    if u and not is_guest(u):
        left += nl("/my/", "Особистий кабінет", "my") + nl("/my/courses.php", "Мої курси", "mycourses")
    left += nl("/course/index.php", "Усі курси", "courses")
    if u and not is_guest(u):
        sk = sesskey()
        right = (
            "<a class=\"ico\" href=\"/message/output/popup/notifications.php\" title=\"Сповіщення\">🔔</a>"
            "<a class=\"ico\" href=\"/message/index.php\" title=\"Повідомлення\">💬</a>"
            "<details class=\"umenu\"><summary>"
            f"<span>{e(fullname(u))}</span>{avatar(u, 32)} ▾</summary><div class=\"dd\">"
            "<a href=\"/my/\">Особистий кабінет</a>"
            f"<a href=\"/user/profile.php?id={u['id']}\">Профіль</a>"
            "<a href=\"/grade/report/overview/index.php\">Оцінки</a>"
            "<a href=\"/message/index.php\">Повідомлення</a>"
            "<a href=\"/user/preferences.php\">Налаштування</a>"
            + ("<a href=\"/admin/index.php\">Адміністрування сайту</a>" if is_admin(u) else "")
            + f"<hr><a href=\"/login/logout.php?sesskey={sk}\">Вийти</a></div></details>")
    elif u:
        right = "<span class=\"muted\">Ви зайшли як Гість</span> <a class=\"btn\" href=\"/login/index.php\">Вхід</a>"
    else:
        right = "<span class=\"muted\">Ви не увійшли в систему.</span> <a class=\"btn\" href=\"/login/index.php\">Вхід</a>"
    return f"<nav class=\"navbar\">{left}<div class=\"spacer\"></div>{right}</nav>"


def _drawer(u, course=None, active=""):
    h = ["<aside class=\"drawer\">"]

    def a(href, label, key, cls=""):
        return f"<a class=\"{cls}{' act' if key == active else ''}\" href=\"{href}\">{label}</a>"

    if course:
        cid = course["id"]
        h.append(f"<div class=\"hd\">{e(course['shortname'])}</div>")
        h.append(a(f"/course/view.php?id={cid}", "🎓 Курс", "course"))
        h.append(a(f"/user/index.php?id={cid}", "👥 Учасники", "participants"))
        h.append(a(f"/grade/report/user/index.php?id={cid}", "📊 Оцінки", "grades"))
        h.append(a(f"/calendar/view.php?view=upcoming&course={cid}", "📅 Події курсу", "ccal"))
        try:
            for s in qall("SELECT section, name FROM mdl_course_sections WHERE course=%s ORDER BY section", (cid,)):
                h.append(f"<a class=\"sub\" href=\"/course/view.php?id={cid}#section-{s['section']}\">"
                         f"{e(s['name'] or 'Тема ' + str(s['section']))}</a>")
        except Exception:
            pass
        h.append("<div style=\"height:10px\"></div>")
    h.append(a("/", "🏠 Головна сторінка", "home"))
    if u and not is_guest(u):
        h.append(a("/my/", "🧭 Особистий кабінет", "my"))
    h.append(a("/calendar/view.php?view=month", "📅 Календар", "calendar"))
    if u and not is_guest(u):
        h.append(a("/grade/report/overview/index.php", "📊 Оцінки", "gradesall"))
        mc = my_courses(u)
        if mc:
            h.append("<div class=\"hd\">Мої курси</div>")
            for c in mc:
                h.append(a(f"/course/view.php?id={c['id']}", f"{c['icon']} {e(c['shortname'])}", f"c{c['id']}"))
    if is_admin(u):
        h.append(a("/admin/index.php", "⚙️ Адміністрування сайту", "admin"))
    h.append("</aside>")
    return "".join(h)


def _footer(u):
    if u and not is_guest(u):
        who = (f"Ви зайшли як <a href=\"/user/profile.php?id={u['id']}\">{e(fullname(u))}</a> "
               f"(<a href=\"/login/logout.php?sesskey={sesskey()}\">Вийти</a>)")
    elif u:
        who = "Ви зайшли як Гість (<a href=\"/login/index.php\">Вхід</a>)"
    else:
        who = "Ви не увійшли в систему. (<a href=\"/login/index.php\">Вхід</a>)"
    return ("<footer class=\"footer\"><div>" + who + "<br><a href=\"/\">Головна</a> · "
            "<a href=\"/admin/tool/dataprivacy/summary.php\">Підсумок збереження даних</a> · "
            "<a href=\"/user/policy.php\">Політика конфіденційності</a></div>"
            "<div style=\"text-align:right\">ATB Education — Навчальний портал ТОВ «АТБ-маркет»<br>"
            "Отримати мобільний застосунок · Powered by <a href=\"/admin/environment.php\">Moodle</a></div></footer>")


def page(title, body, crumbs=None, active="", course=None, drawer_active="", heading=None, status=200,
         nodrawer=False):
    u = None
    try:
        u = current_user()
    except Exception:
        u = None
    crumb_html = ""
    if crumbs is not None:
        parts = ["<a href=\"/\">Головна</a>"]
        for c in crumbs:
            parts.append(f"<a href=\"{c[0]}\">{e(c[1])}</a>" if c[0] else e(c[1]))
        crumb_html = "<div class=\"crumbs\">" + "<span class=\"sep\">/</span>".join(parts) + "</div>"
    head = ""
    if heading is not False:
        head = (f"<div class=\"pagehead\"><h1>{e(heading or title)}</h1>{crumb_html}</div>"
                if heading is not None or crumbs is not None else "")
    try:
        drawer = "" if nodrawer else _drawer(u, course, drawer_active)
    except Exception:
        drawer = ""
    doc = ("<!doctype html><html lang=\"uk\"><head><meta charset=\"utf-8\">"
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
           "<meta name=\"generator\" content=\"Moodle 3.9\">"
           f"<title>{e(title)} | ATB Education</title><style>{PAGE_CSS}</style></head>"
           f"<body id=\"page-{e(request.path.strip('/').replace('/', '-').replace('.php', '') or 'site-index')}\">"
           + _navbar(u, active)
           + f"<div class=\"layout\">{drawer}<main class=\"main\">{head}{body}</main></div>"
           + _footer(u) + f"<script>{NEWS_JS}</script></body></html>")
    return Response(doc, status=status, mimetype="text/html")


def error_page(msg, status=400, link=None):
    lk = link or ("javascript:history.back()", "Продовжити")
    body = (f"<div class=\"card\"><div class=\"alert err\">{e(msg)}</div>"
            f"<a class=\"btn\" href=\"{lk[0]}\">{e(lk[1])}</a></div>")
    return page("Помилка", body, crumbs=[], heading="Помилка", status=status)


@app.errorhandler(404)
def _404(_e):
    return error_page("Цю сторінку не знайдено. Перевірте адресу або поверніться на головну.", 404,
                      link=("/", "Головна"))


@app.errorhandler(pymysql.err.OperationalError)
def _dberr(_e):
    atblog.log("education.db_error", atblog.client_ip(request), path=request.path)
    body = ("<div class=\"card\"><h2>Помилка підключення до бази даних</h2>"
            "<p>Наразі виникли проблеми з підключенням до бази даних. Спробуйте пізніше.</p>"
            "<p class=\"muted\">Error: Database connection failed</p></div>")
    return Response(f"<!doctype html><meta charset=utf-8><title>Помилка</title>"
                    f"<style>{PAGE_CSS}</style><div class=\"main\">{body}</div>", status=503)


# ---------------------------------------------------------------------------
# front page / login
# ---------------------------------------------------------------------------
def login_form(err="", username=""):
    return (
        "<form class=\"login-card\" method=\"post\" action=\"/login/index.php\" id=\"login\">"
        "<h2>Вхід до порталу</h2>"
        "<div class=\"muted\" style=\"margin-bottom:6px\">Корпоративний логін у форматі ім'я.прізвище</div>"
        + (f"<div class=\"alert err\" id=\"loginerrormessage\">{e(err)}</div>" if err else "")
        + f"<input type=\"hidden\" name=\"logintoken\" value=\"{logintoken()}\">"
        "<label class=\"f\" for=\"username\">Ім'я користувача / e-mail</label>"
        f"<input id=\"username\" name=\"username\" type=\"text\" value=\"{e(username)}\" autocomplete=\"username\" placeholder=\"ivan.petrenko\">"
        "<label class=\"f\" for=\"password\">Пароль</label>"
        "<input id=\"password\" name=\"password\" type=\"password\" autocomplete=\"current-password\" placeholder=\"••••••••\">"
        "<label style=\"display:block;margin-top:10px;font-size:.86rem\"><input type=\"checkbox\" name=\"rememberusername\" value=\"1\"> Запам'ятати ім'я користувача</label>"
        "<button class=\"btn wide\" style=\"margin-top:14px\" type=\"submit\" id=\"loginbtn\">Увійти</button>"
        "<div class=\"muted\" style=\"margin-top:10px;text-align:center\"><a href=\"/login/forgot_password.php\">Забули ім'я користувача або пароль?</a></div>"
        "<hr style=\"border:0;border-top:1px solid #e9ecef;margin:14px 0\">"
        "<div class=\"muted\">Деякі курси можуть бути доступні для гостей</div>"
        "</form>"
        "<form method=\"post\" action=\"/login/index.php\" style=\"display:none\" id=\"guestlogin\">"
        f"<input type=\"hidden\" name=\"logintoken\" value=\"{logintoken()}\">"
        "<input type=\"hidden\" name=\"username\" value=\"guest\"><input type=\"hidden\" name=\"password\" value=\"guest\"></form>"
    )


def course_cards(courses, u=None, show_progress=False):
    if not courses:
        return "<p class=\"muted\">Немає курсів.</p>"
    cats = {c["id"]: c["name"] for c in qall("SELECT id, name FROM mdl_course_categories")}
    out = ["<div class=\"ccards\">"]
    for c in courses:
        extra = ""
        if show_progress and u and not is_guest(u):
            d, t = progress(c["id"], u["id"])
            pct = int(100 * d / t) if t else 0
            extra = f"<div class=\"pbar\"><i style=\"width:{pct}%\"></i></div><div class=\"muted\">{pct}% завершено</div>"
        else:
            flags = []
            if c["guest"]:
                flags.append("<span class=\"badge blue\" title=\"Дозволено доступ гостям\">🔓 Гостьовий доступ</span>")
            if c["selfenrol"]:
                flags.append("<span class=\"badge\" title=\"Самостійна реєстрація\">✍ Самореєстрація</span>")
            extra = " ".join(flags)
        out.append(
            f"<a class=\"ccard\" href=\"/course/view.php?id={c['id']}\" style=\"text-decoration:none\">"
            f"<div class=\"cover\" style=\"background-color:{e(c['color'])}\">{e(c['icon'])}</div>"
            f"<div class=\"cb\"><span class=\"cat\">{e(cats.get(c['category'], ''))}</span>"
            f"<span class=\"nm\">{e(c['fullname'])}</span><span class=\"muted\">{e(c['shortname'])}</span>{extra}</div></a>")
    out.append("</div>")
    return "".join(out)


@app.get("/")
@app.get("/index.php")
def index():
    u = current_user()
    courses = qall("SELECT * FROM mdl_course WHERE id<>1 AND visible=1 ORDER BY sortorder")
    if u and not is_guest(u):
        hero = (f"<div class=\"hero-text\"><h1>Вітаємо, {e(u['firstname'])}!</h1>"
                "<p>Продовжуйте навчання у <a href=\"/my/\">Особистому кабінеті</a> або оберіть курс нижче.</p>"
                + news_block() + "</div>")
        side = ""
    else:
        hero = ("<div class=\"hero-text\"><h1>Навчальний портал АТБ</h1>"
                "<p>Ласкаво просимо до корпоративної системи навчання співробітників ТОВ «АТБ-маркет». "
                "Проходьте обовʼязкові тренінги, складайте тести та відстежуйте свій прогрес.</p>"
                "<p>Для доступу до курсів увійдіть за корпоративними обліковими даними.</p>"
                + news_block() + "</div>")
        side = login_form()
    body = (f"<div class=\"hero\">{hero}{side}</div>"
            "<h2 style=\"margin:26px 0 14px;font-size:1.2rem\">Доступні курси</h2>"
            + course_cards(courses))
    return page("ATB Education — Навчальний портал АТБ", body, active="home", drawer_active="home", heading=False)


@app.route("/login/index.php", methods=["GET", "POST"])
def login():
    ip = atblog.client_ip(request)
    err = ""
    username = request.cookies.get("MOODLEID1_", "")
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        if request.form.get("logintoken") != session.get("logintoken"):
            err = "Неправильний токен входу. Спробуйте ще раз."
            atblog.log("education.login_failed", ip, username=username, reason="invalid_logintoken")
        else:
            user = None
            if username:
                user = qone("SELECT * FROM mdl_user WHERE (username=%s OR (email=%s AND id<>1)) AND deleted=0 "
                            "ORDER BY id LIMIT 1", (username, username))
            ok = bool(user) and user["auth"] != "nologin" and not user["suspended"] and validate_password(user, password)
            if ok:
                wants = session.get("wantsurl") or ("/my/" if user["id"] != GUEST_ID else "/")
                session.clear()
                session["uid"] = user["id"]
                sesskey()
                t = now()
                if user["id"] != GUEST_ID:
                    qexec("UPDATE mdl_user SET lastlogin=currentlogin, currentlogin=%s, lastaccess=%s, lastip=%s, "
                          "firstaccess=IF(firstaccess=0,%s,firstaccess) WHERE id=%s", (t, t, ip, t, user["id"]))
                    atblog.log("education.login_success", ip, username=user["username"], userid=user["id"],
                               admin=user["id"] in siteadmins())
                else:
                    atblog.log("education.guest_login", ip)
                logstore("\\core\\event\\user_loggedin", "core", "loggedin", user["id"])
                resp = redirect(wants if wants.startswith("/") else "/my/")
                if request.form.get("rememberusername") and user["id"] != GUEST_ID:
                    resp.set_cookie("MOODLEID1_", user["username"], max_age=60 * 86400)
                return resp
            reason = ("no_such_user" if not user else "nologin" if user["auth"] == "nologin"
                      else "suspended" if user["suspended"] else "wrong_password")
            atblog.log("education.login_failed", ip, username=username, reason=reason)
            logstore("\\core\\event\\user_login_failed", "core", "failed", user["id"] if user else 0)
            err = "Неправильне ім'я користувача або пароль, спробуйте ще раз."
    u = current_user()
    if u and not is_guest(u) and request.method == "GET":
        body = (f"<div class=\"card\"><p>Ви вже увійшли як {e(fullname(u))}. Щоб увійти як інший користувач, спочатку вийдіть.</p>"
                f"<a class=\"btn\" href=\"/login/logout.php?sesskey={sesskey()}\">Вийти</a> "
                "<a class=\"btn sec\" href=\"/my/\">Скасувати</a></div>")
        return page("Вхід", body, crumbs=[(None, "Вхід")], heading="Вхід")
    body = ("<div class=\"hero\"><div class=\"hero-text\"><h1>Вхід до ATB Education</h1>"
            "<p>Навчальний портал АТБ. Використовуйте корпоративний логін (формат <code>ім'я.прізвище</code>) "
            "або корпоративну e-mail адресу.</p>"
            "<p>Новим співробітникам логін та тимчасовий пароль видає директор магазину або керівник підрозділу.</p>"
            "<div class=\"card\" style=\"margin-top:14px\"><h3>Ви вперше на нашому сайті?</h3>"
            "<p class=\"muted\">Деякі курси (Онбординг, Пожежна безпека, Стандарти обслуговування) доступні для перегляду гостям.</p>"
            "<button class=\"btn sec\" form=\"guestlogin\" type=\"submit\">Увійти як гість</button></div>"
            + news_block() + "</div>" + login_form(err, username) + "</div>")
    return page("Вхід", body, heading=False, status=200)


@app.route("/login/logout.php", methods=["GET", "POST"])
def logout():
    u = current_user()
    if not u:
        return redirect("/")
    if request.values.get("sesskey") == session.get("sesskey"):
        atblog.log("education.logout", atblog.client_ip(request), userid=u["id"], username=u["username"])
        logstore("\\core\\event\\user_loggedout", "core", "loggedout", u["id"])
        session.clear()
        return redirect("/")
    body = ("<div class=\"card\"><p>Ви дійсно бажаєте вийти?</p>"
            f"<a class=\"btn\" href=\"/login/logout.php?sesskey={sesskey()}\">Продовжити</a> "
            "<a class=\"btn sec\" href=\"/my/\">Скасувати</a></div>")
    return page("Вихід", body, crumbs=[(None, "Вихід")], heading="Вихід")


@app.route("/login/forgot_password.php", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        who = (request.form.get("username") or request.form.get("email") or "").strip()
        atblog.log("education.password_reset_request", atblog.client_ip(request), identifier=who)
        body = ("<div class=\"card\"><div class=\"alert info\">Якщо ви ввели правильне ім'я користувача або "
                "адресу електронної пошти, вам надіслано лист.</div><p>Він містить прості інструкції для "
                "підтвердження та завершення зміни пароля. Якщо ви не отримали листа протягом години, "
                "зверніться до служби підтримки ІТ (внутрішній 1100).</p>"
                "<a class=\"btn\" href=\"/login/index.php\">Продовжити</a></div>")
        return page("Забутий пароль", body, crumbs=[("/login/index.php", "Вхід"), (None, "Забутий пароль")])
    body = ("<div class=\"card\"><p>Щоб скинути пароль, вкажіть ваше ім'я користувача або e-mail. "
            "Якщо запис знайдено в базі даних, на вашу адресу буде надіслано лист з інструкціями.</p>"
            "<form method=\"post\" style=\"max-width:420px\"><h3>Пошук за ім'ям користувача</h3>"
            "<label class=\"f\">Ім'я користувача</label><input type=\"text\" name=\"username\">"
            "<button class=\"btn\" style=\"margin-top:10px\">Шукати</button></form>"
            "<form method=\"post\" style=\"max-width:420px;margin-top:20px\"><h3>Пошук за e-mail</h3>"
            "<label class=\"f\">E-mail</label><input type=\"email\" name=\"email\">"
            "<button class=\"btn\" style=\"margin-top:10px\">Шукати</button></form></div>")
    return page("Забутий пароль", body, crumbs=[("/login/index.php", "Вхід"), (None, "Забутий пароль")])


@app.route("/login/change_password.php", methods=["GET", "POST"])
def change_password():
    require_login(allow_guest=False)
    body = ("<div class=\"card\"><div class=\"alert warn\">Зміна пароля через навчальний портал тимчасово "
            "вимкнена адміністратором. Для зміни пароля зверніться до служби підтримки ІТ (внутрішній 1100) "
            "або до директора магазину.</div><a class=\"btn\" href=\"/user/preferences.php\">Назад</a></div>")
    return page("Зміна пароля", body, crumbs=[("/user/preferences.php", "Налаштування"), (None, "Зміна пароля")])


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------
def visible_events(u, start, end, courseid=None):
    if courseid:
        return qall("SELECT * FROM mdl_event WHERE timestart BETWEEN %s AND %s AND courseid=%s ORDER BY timestart",
                    (start, end, courseid))
    if is_admin(u):
        return qall("SELECT * FROM mdl_event WHERE timestart BETWEEN %s AND %s AND (userid=0 OR userid=%s) "
                    "ORDER BY timestart", (start, end, u["id"]))
    cids = [c["id"] for c in my_courses(u)] if u else []
    uid = u["id"] if u else -1
    cl = ",".join(str(int(x)) for x in cids) or "0"
    return qall(f"SELECT * FROM mdl_event WHERE timestart BETWEEN %s AND %s AND "
                f"(eventtype='site' OR (courseid IN ({cl}) AND userid=0) OR userid=%s) ORDER BY timestart",
                (start, end, uid))


def event_link(ev):
    if ev["modulename"] == "quiz" and ev["instance"]:
        q = qone("SELECT cmid FROM mdl_quiz WHERE id=%s", (ev["instance"],))
        if q:
            return f"/mod/quiz/view.php?id={q['cmid']}"
    return f"/calendar/view.php?view=day&time={ev['timestart']}"


def event_items(evs, coursenames=None):
    if not evs:
        return "<p class=\"muted\">Немає запланованих подій</p>"
    out = []
    for ev in evs:
        d = dt(ev["timestart"])
        cn = ""
        if ev["courseid"] and coursenames is not None:
            cn = f"<div class=\"muted\">{e(coursenames.get(ev['courseid'], ''))}</div>"
        out.append(f"<div class=\"evitem\"><div class=\"dt\"><b>{d.day}</b>{MONTHS_GEN[d.month - 1][:3]}</div>"
                   f"<div><a href=\"{event_link(ev)}\">{e(ev['name'])}</a>"
                   f"<div class=\"muted\">{userdate(ev['timestart'], 'dayname')}, {userdate(ev['timestart'], 'time')}</div>{cn}</div></div>")
    return "".join(out)


def mini_calendar(u):
    d = dt(now())
    first = datetime(d.year, d.month, 1, tzinfo=TZ)
    days = calendar.monthrange(d.year, d.month)[1]
    end = first + timedelta(days=days)
    evdays = {dt(ev["timestart"]).day for ev in visible_events(u, int(first.timestamp()), int(end.timestamp()))}
    rows = ["<table class=\"mcal\"><tr>" + "".join(f"<th>{w}</th>" for w in WD_SHORT) + "</tr><tr>"]
    rows.append("<td></td>" * first.weekday())
    col = first.weekday()
    for day in range(1, days + 1):
        cls = []
        if day == d.day:
            cls.append("today")
        cell = str(day)
        if day in evdays:
            cls.append("has")
            ts = int(datetime(d.year, d.month, day, tzinfo=TZ).timestamp())
            cell = f"<a href=\"/calendar/view.php?view=day&time={ts}\">{day}</a>"
        rows.append(f"<td class=\"{' '.join(cls)}\">{cell}</td>")
        col += 1
        if col == 7 and day != days:
            rows.append("</tr><tr>")
            col = 0
    rows.append("</tr></table>")
    return (f"<div class=\"card block\"><h3><a href=\"/calendar/view.php?view=month\" style=\"color:inherit\">"
            f"{MONTHS_NOM[d.month - 1]} {d.year}</a></h3>{''.join(rows)}</div>")


def online_users_block():
    rows = qall("SELECT id, firstname, lastname FROM mdl_user WHERE lastaccess > %s AND id<>1 AND deleted=0 "
                "ORDER BY lastaccess DESC LIMIT 12", (now() - 300,))
    items = "".join(f"<div style=\"display:flex;gap:8px;align-items:center;margin:5px 0\">{avatar(r, 24)}"
                    f"<a href=\"/user/profile.php?id={r['id']}\">{e(fullname(r))}</a></div>" for r in rows)
    return (f"<div class=\"card block\"><h3>Онлайн-користувачі</h3><div class=\"muted\">"
            f"{len(rows)} онлайн-користувачів (останні 5 хвилин)</div>{items}</div>")


@app.get("/my/")
@app.get("/my/index.php")
def dashboard():
    u = require_login()
    if is_guest(u):
        return redirect("/")
    courses = my_courses(u)
    names = {c["id"]: c["fullname"] for c in courses}
    evs = visible_events(u, now(), now() + 45 * 86400)
    recent = sorted([c for c in courses if c["timeaccess"]], key=lambda c: -c["timeaccess"])[:3]
    rec_html = "".join(f"<a class=\"badge blue\" style=\"margin:3px;font-size:.85rem;padding:6px 10px\" "
                       f"href=\"/course/view.php?id={c['id']}\">{e(c['icon'])} {e(c['fullname'])}</a>" for c in recent)
    main = (
        f"<div class=\"card\"><h2>Нещодавно відвідані курси</h2>{rec_html or '<p class=muted>Немає</p>'}</div>"
        f"<div class=\"card\"><h2>Шкала часу</h2>{event_items(evs[:8], names)}</div>"
        f"<div class=\"card\"><h2>Огляд курсів</h2>{course_cards(courses, u, show_progress=True)}</div>")
    side = mini_calendar(u) + "<div class=\"card block\">" + news_block() + "</div>" + online_users_block()
    body = f"<div class=\"cols\"><div class=\"col-main\">{main}</div><div class=\"col-side\">{side}</div></div>"
    return page("Особистий кабінет", body, heading="Особистий кабінет", crumbs=[(None, "Особистий кабінет")],
                active="my", drawer_active="my")


@app.get("/my/courses.php")
def mycourses():
    u = require_login(allow_guest=False)
    courses = my_courses(u)
    tab = request.args.get("tab", "all")
    rows = []
    for c in courses:
        d, t = progress(c["id"], u["id"])
        pct = int(100 * d / t) if t else 0
        if tab == "inprogress" and pct >= 100 or tab == "completed" and pct < 100:
            continue
        role = "Викладач" if c["roleid"] in (3, 4) else "Студент"
        rows.append(f"<tr><td>{e(c['icon'])} <a href=\"/course/view.php?id={c['id']}\">{e(c['fullname'])}</a>"
                    f"<div class=\"muted\">{e(c['shortname'])}</div></td><td>{role}</td>"
                    f"<td style=\"width:200px\"><div class=\"pbar\"><i style=\"width:{pct}%\"></i></div>"
                    f"<span class=\"muted\">{pct}% ({d}/{t})</span></td><td class=\"muted\">{timeago(c['timeaccess'])}</td></tr>")
    tabs = "".join(f"<a class=\"{'act' if tab == k else ''}\" href=\"?tab={k}\">{v}</a>" for k, v in
                   (("all", "Усі"), ("inprogress", "У процесі"), ("completed", "Завершені")))
    body = (f"<div class=\"card\"><div class=\"tabs\">{tabs}</div><table class=\"gt\"><tr><th>Курс</th><th>Роль</th>"
            f"<th>Прогрес</th><th>Останній доступ</th></tr>{''.join(rows) or '<tr><td colspan=4 class=muted>Немає курсів</td></tr>'}"
            "</table></div>")
    return page("Мої курси", body, crumbs=[(None, "Мої курси")], active="mycourses", drawer_active="my")


# ---------------------------------------------------------------------------
# courses
# ---------------------------------------------------------------------------
@app.get("/course/index.php")
def course_index():
    catid = request.args.get("categoryid", type=int)
    cats = qall("SELECT * FROM mdl_course_categories ORDER BY sortorder")
    out = ["<div class=\"card\"><form action=\"/course/search.php\" style=\"display:flex;gap:8px;max-width:520px\">"
           "<input type=\"search\" name=\"search\" placeholder=\"Пошук курсів\"><button class=\"btn\">Шукати</button></form></div>"]
    for cat in cats:
        if catid and cat["id"] != catid:
            continue
        cs = qall("SELECT * FROM mdl_course WHERE category=%s AND visible=1 ORDER BY sortorder", (cat["id"],))
        items = []
        for c in cs:
            tl = ", ".join(f"<a href=\"/user/profile.php?id={t['id']}\">{e(fullname(t))}</a>" for t in teachers_of(c["id"]))
            icons = (" <span title=\"Дозволено доступ гостям\">🔓</span>" if c["guest"] else "") + \
                    (" <span title=\"Самостійна реєстрація\">✍</span>" if c["selfenrol"] else "")
            items.append(f"<div style=\"padding:12px 0;border-bottom:1px solid #eef0f2;display:flex;gap:14px\">"
                         f"<div class=\"mi\" style=\"width:46px;height:46px;border-radius:8px;background:{e(c['color'])};"
                         f"display:flex;align-items:center;justify-content:center;font-size:1.4rem;flex:none\">{e(c['icon'])}</div>"
                         f"<div><a href=\"/course/view.php?id={c['id']}\" style=\"font-weight:600\">{e(c['fullname'])}</a>{icons}"
                         f"<div class=\"muted\">{e(c['summary'])}</div>"
                         + (f"<div style=\"font-size:.85rem;margin-top:3px\">Викладач: {tl}</div>" if tl else "")
                         + "</div></div>")
        out.append(f"<div class=\"card\"><h2><a href=\"/course/index.php?categoryid={cat['id']}\" style=\"color:inherit\">"
                   f"{e(cat['name'])}</a> <span class=\"muted\">({len(cs)})</span></h2>"
                   f"<div class=\"muted\">{e(cat['description'])}</div>{''.join(items)}</div>")
    crumbs = [("/course/index.php", "Курси")]
    return page("Категорії курсів", "".join(out), crumbs=crumbs, heading="Курси", active="courses")


@app.get("/course/search.php")
def course_search():
    s = (request.args.get("search") or request.args.get("q") or "").strip()
    rows = []
    if s:
        like = f"%{s}%"
        rows = qall("SELECT * FROM mdl_course WHERE id<>1 AND visible=1 AND (fullname LIKE %s OR shortname LIKE %s "
                    "OR summary LIKE %s) ORDER BY sortorder", (like, like, like))
        atblog.log("education.course_search", atblog.client_ip(request), q=s[:200], hits=len(rows))
    body = (f"<div class=\"card\"><form style=\"display:flex;gap:8px;max-width:520px\"><input type=\"search\" "
            f"name=\"search\" value=\"{e(s)}\"><button class=\"btn\">Шукати</button></form></div>"
            + (f"<div class=\"card\"><h2>Результати пошуку: {len(rows)}</h2>{course_cards(rows)}</div>" if s else ""))
    return page("Пошук курсів", body, crumbs=[("/course/index.php", "Курси"), (None, "Пошук")], active="courses")


def act_row(cm, u, role, done_set, quizzes):
    url = f"/mod/{cm['modname']}/view.php?id={cm['id']}"
    sub = MOD_NAME.get(cm["modname"], "")
    if cm["modname"] == "quiz" and cm["id"] in quizzes and quizzes[cm["id"]]["timeclose"]:
        sub += f" · Закривається: {userdate(quizzes[cm['id']]['timeclose'], 'short')}"
    if cm["modname"] == "resource" and cm["filename"]:
        sub += " · " + cm["filename"].rsplit(".", 1)[-1].upper()
    chk = ""
    if cm["completion"] and role in ("student", "teacher"):
        if cm["id"] in done_set:
            chk = "<span class=\"chk done\">✓ Виконано</span>"
        else:
            chk = ("<span class=\"chk\">Отримати прохідну оцінку</span>" if cm["modname"] == "quiz"
                   else "<span class=\"chk\">Переглянути</span>")
    return (f"<li><span class=\"mi {cm['modname']}\">{MOD_ICON.get(cm['modname'], '•')}</span>"
            f"<div class=\"an\"><a href=\"{url}\">{e(cm['name'])}</a><small>{e(sub)}</small></div>{chk}</li>")


@app.get("/course/view.php")
def course_view():
    c, role, u = require_course(request.args.get("id"))
    ip = atblog.client_ip(request)
    atblog.log("education.course_view", ip, courseid=c["id"], userid=u["id"], role=role)
    logstore("\\core\\event\\course_viewed", "core", "viewed", u["id"], c["id"])
    sections = qall("SELECT * FROM mdl_course_sections WHERE course=%s ORDER BY section", (c["id"],))
    cms = qall("SELECT * FROM mdl_course_modules WHERE course=%s AND visible=1 ORDER BY section, position", (c["id"],))
    quizzes = {q["cmid"]: q for q in qall("SELECT * FROM mdl_quiz WHERE course=%s", (c["id"],))}
    done_set = set()
    if not is_guest(u):
        done_set = {r["coursemoduleid"] for r in qall(
            "SELECT coursemoduleid FROM mdl_course_modules_completion WHERE userid=%s", (u["id"],))}
    tl = ", ".join(f"<a href=\"/user/profile.php?id={t['id']}\" style=\"color:#fff;text-decoration:underline\">"
                   f"{e(fullname(t))}</a>" for t in teachers_of(c["id"]))
    banner = (f"<div class=\"cbanner\" style=\"background:{e(c['color'])}\"><div class=\"ic\">{e(c['icon'])}</div>"
              f"<div><h1>{e(c['fullname'])}</h1><div class=\"sn\">{e(c['shortname'])}"
              + (f" · Викладач: {tl}" if tl else "") + "</div></div></div>")
    top = ""
    if role == "guest":
        top = ("<div class=\"alert info\">Ви переглядаєте цей курс як гість. Тести, форуми та оцінки доступні лише "
               "записаним учасникам." + (f" <a href=\"/enrol/index.php?id={c['id']}\">Записатися на курс</a>"
                                         if c["selfenrol"] and not is_guest(u) else "") + "</div>")
    elif role == "student":
        d, t = progress(c["id"], u["id"])
        pct = int(100 * d / t) if t else 0
        top = (f"<div class=\"card\" style=\"display:flex;gap:20px;align-items:center\"><div style=\"flex:1\">"
               f"<b>Ваш прогрес:</b> {d} з {t} елементів виконано<div class=\"pbar\"><i style=\"width:{pct}%\"></i></div></div>"
               + ("<span class=\"badge ok\">Курс завершено</span>" if t and d >= t else "") + "</div>")
    secs = []
    for s in sections:
        items = [act_row(cm, u, role, done_set, quizzes) for cm in cms if cm["section"] == s["section"]]
        title = s["name"] or f"Тема {s['section']}"
        summ = f"<div class=\"ssum\">{e(s['summary'])}</div>" if s["summary"] else ""
        if s["section"] == 0:
            summ = f"<div class=\"ssum\">{e(c['summary'])}</div>" + summ
        secs.append(f"<div class=\"section\" id=\"section-{s['section']}\"><h3>{e(title)}</h3>{summ}"
                    f"<ul class=\"acts\">{''.join(items) or '<li class=muted>Немає елементів</li>'}</ul></div>")
    body = banner + top + "".join(secs)
    return page(c["fullname"], body, crumbs=[("/my/courses.php" if not is_guest(u) else "/course/index.php", "Курси"),
                                             (None, c["shortname"])], heading=False, course=c, drawer_active="course")


@app.route("/enrol/index.php", methods=["GET", "POST"])
def enrol():
    c = get_course(request.values.get("id"))
    u = require_login()
    if is_guest(u):
        return redirect("/login/index.php")
    if course_role(c, u) in ("student", "teacher"):
        return redirect(f"/course/view.php?id={c['id']}")
    if request.method == "POST" and c["selfenrol"]:
        require_sesskey()
        qexec("INSERT IGNORE INTO mdl_user_enrolments (courseid, userid, roleid, enrol, timestart, timeaccess) "
              "VALUES (%s,%s,5,'self',%s,%s)", (c["id"], u["id"], now(), now()))
        atblog.log("education.enrol_self", atblog.client_ip(request), courseid=c["id"], userid=u["id"])
        logstore("\\core\\event\\user_enrolment_created", "core", "created", u["id"], c["id"])
        return redirect(f"/course/view.php?id={c['id']}")
    if c["selfenrol"]:
        opt = ("<h3>Самостійна реєстрація (Студент)</h3><p class=\"muted\">Ключ реєстрації не потрібен.</p>"
               f"<form method=\"post\"><input type=\"hidden\" name=\"id\" value=\"{c['id']}\">"
               f"<input type=\"hidden\" name=\"sesskey\" value=\"{sesskey()}\">"
               "<button class=\"btn\">Записатися на курс</button></form>")
    else:
        opt = ("<div class=\"alert warn\">Ви не можете самостійно записатися на цей курс. Курс призначається "
               "відділом навчання відповідно до посади — зверніться до свого керівника або на "
               "olena.kovalenko@atbmarket.com.</div>")
    if c["guest"]:
        opt += f"<p style=\"margin-top:12px\"><a href=\"/course/view.php?id={c['id']}\">Переглянути як гість</a></p>"
    body = (f"<div class=\"card\"><h2>{e(c['icon'])} {e(c['fullname'])}</h2><p>{e(c['summary'])}</p></div>"
            f"<div class=\"card\"><h2>Варіанти реєстрації</h2>{opt}</div>")
    return page("Записатися на курс", body, crumbs=[("/course/index.php", "Курси"), (None, c["shortname"]),
                                                    (None, "Записатися на курс")])


# ---------------------------------------------------------------------------
# simple modules: page / resource / url / assign
# ---------------------------------------------------------------------------
def mod_crumbs(c, cm):
    return [("/course/index.php", "Курси"), (f"/course/view.php?id={c['id']}", c["shortname"]), (None, cm["name"])]


def _nav_prevnext(c, cm):
    cms = qall("SELECT id, modname, name FROM mdl_course_modules WHERE course=%s AND visible=1 "
               "ORDER BY section, position", (c["id"],))
    ids = [x["id"] for x in cms]
    i = ids.index(cm["id"]) if cm["id"] in ids else -1
    prev = cms[i - 1] if i > 0 else None
    nxt = cms[i + 1] if 0 <= i < len(cms) - 1 else None
    out = "<div style=\"display:flex;justify-content:space-between;margin-top:14px;gap:10px\">"
    out += (f"<a href=\"/mod/{prev['modname']}/view.php?id={prev['id']}\">◄ {e(prev['name'])}</a>" if prev else "<span></span>")
    out += (f"<a href=\"/mod/{nxt['modname']}/view.php?id={nxt['id']}\">{e(nxt['name'])} ►</a>" if nxt else "<span></span>")
    return out + "</div>"


@app.get("/mod/page/view.php")
def mod_page():
    cm = get_cm(request.args.get("id"), "page")
    c, role, u = require_course(cm["course"])
    mark_complete(cm["id"], u, role)
    logstore("\\mod_page\\event\\course_module_viewed", "mod_page", "viewed", u["id"], c["id"], cm["id"])
    body = (f"<div class=\"card content\"><div class=\"muted\" style=\"margin-bottom:10px\">{e(cm['intro'])}</div>"
            f"{cm['content'] or ''}<p class=\"muted\" style=\"margin-top:20px\">Останні зміни: {userdate(cm['added'])}</p></div>"
            + _nav_prevnext(c, cm))
    return page(cm["name"], body, crumbs=mod_crumbs(c, cm), course=c)


@app.get("/mod/resource/view.php")
def mod_resource():
    cm = get_cm(request.args.get("id"), "resource")
    c, role, u = require_course(cm["course"])
    furl = f"/pluginfile.php/{cm['id'] + 4000}/mod_resource/content/1/{quote(cm['filename'])}"
    size = len((cm["content"] or "").encode())
    body = (f"<div class=\"card\"><p>{e(cm['intro'])}</p><p>Натисніть на посилання "
            f"<a href=\"{furl}\">📎 {e(cm['filename'])}</a>, щоб переглянути файл.</p>"
            f"<p class=\"muted\">Розмір: {size / 1024:.1f} КБ · Завантажено {userdate(cm['added'], 'date')}</p></div>"
            + _nav_prevnext(c, cm))
    return page(cm["name"], body, crumbs=mod_crumbs(c, cm), course=c)


@app.get("/pluginfile.php/<int:ctx>/mod_resource/content/<int:rev>/<path:fname>")
def pluginfile(ctx, rev, fname):
    cm = qone("SELECT * FROM mdl_course_modules WHERE id=%s AND modname='resource'", (ctx - 4000,))
    if not cm or cm["filename"] != fname:
        return error_page("Файл не знайдено", 404)
    c, role, u = require_course(cm["course"])
    mark_complete(cm["id"], u, role)
    atblog.log("education.resource_download", atblog.client_ip(request), cmid=cm["id"], file=fname, userid=u["id"])
    if fname.endswith(".html"):
        return Response(cm["content"], mimetype="text/html")
    r = Response(cm["content"], mimetype="text/plain")
    r.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
    return r


@app.get("/mod/url/view.php")
def mod_url():
    cm = get_cm(request.args.get("id"), "url")
    c, role, u = require_course(cm["course"])
    mark_complete(cm["id"], u, role)
    body = (f"<div class=\"card\"><p>{e(cm['intro'])}</p><p>Натисніть на посилання <a href=\"{e(cm['url'])}\">"
            f"{e(cm['url'])}</a>, щоб відкрити ресурс.</p><p class=\"muted\">Ресурс доступний лише з корпоративної "
            "мережі або через VPN.</p></div>" + _nav_prevnext(c, cm))
    return page(cm["name"], body, crumbs=mod_crumbs(c, cm), course=c)


@app.route("/mod/assign/view.php", methods=["GET", "POST"])
def mod_assign():
    cm = get_cm(request.values.get("id"), "assign")
    c, role, u = require_course(cm["course"])
    msg = ""
    if request.method == "POST" and role in ("student", "teacher"):
        require_sesskey()
        txt = (request.form.get("onlinetext") or "").strip()[:20000]
        if txt:
            qexec("INSERT INTO mdl_assign_submission (cmid, userid, status, onlinetext, timemodified) VALUES "
                  "(%s,%s,'submitted',%s,%s) ON DUPLICATE KEY UPDATE onlinetext=VALUES(onlinetext), "
                  "timemodified=VALUES(timemodified), status='submitted'", (cm["id"], u["id"], txt, now()))
            atblog.log("education.assign_submit", atblog.client_ip(request), cmid=cm["id"], userid=u["id"], length=len(txt))
            msg = "<div class=\"alert ok\">Зміни збережено. Відповідь надіслано на оцінювання.</div>"
    sub = None if is_guest(u) else qone("SELECT * FROM mdl_assign_submission WHERE cmid=%s AND userid=%s",
                                        (cm["id"], u["id"]))
    status = ("<span class=\"badge ok\">Надіслано для оцінювання</span>" if sub else "<span class=\"badge\">Немає спроби</span>")
    rows = (f"<tr><th style=\"width:240px\">Статус відповіді</th><td>{status}</td></tr>"
            "<tr><th>Статус оцінювання</th><td>Не оцінено</td></tr>"
            f"<tr><th>Останні зміни</th><td>{userdate(sub['timemodified']) if sub else '-'}</td></tr>")
    form = ""
    if role in ("student", "teacher"):
        form = (f"<h3 style=\"margin-top:18px\">Відповідь у вигляді тексту</h3><form method=\"post\">"
                f"<input type=\"hidden\" name=\"id\" value=\"{cm['id']}\"><input type=\"hidden\" name=\"sesskey\" value=\"{sesskey()}\">"
                f"<textarea name=\"onlinetext\">{e(sub['onlinetext']) if sub else ''}</textarea>"
                "<button class=\"btn\" style=\"margin-top:10px\">Зберегти зміни</button></form>")
    else:
        form = "<div class=\"alert info\" style=\"margin-top:14px\">Гості не можуть надсилати відповіді.</div>"
    body = (f"<div class=\"card\">{msg}<p>{e(cm['intro'])}</p><h3>Стан відповіді</h3>"
            f"<table class=\"generaltable\" style=\"width:100%\">{rows}</table>{form}</div>")
    return page(cm["name"], body, crumbs=mod_crumbs(c, cm), course=c)


# ---------------------------------------------------------------------------
# forum
# ---------------------------------------------------------------------------
def forum_access(forum):
    """Returns (course or None, role, user). Site news (course 1) is public to read."""
    if forum["course"] == 1:
        u = current_user()
        role = "teacher" if is_admin(u) else ("guest" if not u or is_guest(u) else "student")
        return None, role, u
    c, role, u = require_course(forum["course"])
    return c, role, u


def can_start(forum, role):
    if role == "guest":
        return False
    if forum["type"] == "news":
        return role == "teacher"
    return role in ("student", "teacher")


def forum_crumbs(c, forum):
    if c is None:
        return [(None, "Новини сайту")]
    return [("/course/index.php", "Курси"), (f"/course/view.php?id={c['id']}", c["shortname"]),
            (f"/mod/forum/view.php?f={forum['id']}", forum["name"])]


@app.get("/mod/forum/view.php")
def forum_view():
    if request.args.get("f"):
        forum = qone("SELECT * FROM mdl_forum WHERE id=%s", (request.args.get("f", type=int) or 0,))
    else:
        forum = qone("SELECT * FROM mdl_forum WHERE cmid=%s", (request.args.get("id", type=int) or 0,))
    if not forum:
        return error_page("Неправильний ідентифікатор форуму", 404)
    c, role, u = forum_access(forum)
    discs = qall("SELECT d.*, u.firstname, u.lastname, u.id AS uid, (SELECT COUNT(*)-1 FROM mdl_forum_posts p "
                 "WHERE p.discussion=d.id) AS replies, (SELECT MAX(created) FROM mdl_forum_posts p WHERE "
                 "p.discussion=d.id) AS lastpost FROM mdl_forum_discussions d JOIN mdl_user u ON u.id=d.userid "
                 "WHERE d.forum=%s ORDER BY d.pinned DESC, lastpost DESC", (forum["id"],))
    rows = "".join(
        f"<tr><td>{'📌 ' if d['pinned'] else ''}<a href=\"/mod/forum/discuss.php?d={d['id']}\">{e(d['name'])}</a></td>"
        f"<td><div style=\"display:flex;gap:8px;align-items:center\">{avatar(d, 26)}{e(fullname(d))}</div></td>"
        f"<td>{d['replies']}</td><td class=\"muted\">{userdate(d['lastpost'], 'short')}</td></tr>" for d in discs)
    btn = (f"<a class=\"btn\" href=\"/mod/forum/post.php?forum={forum['id']}\">Додати нову тему</a>"
           if can_start(forum, role) else "")
    body = (f"<div class=\"card\"><p>{e(forum['intro'])}</p>{btn}<table class=\"gt\" style=\"margin-top:14px\"><tr>"
            "<th>Обговорення</th><th>Розпочато</th><th>Відповіді</th><th>Останнє повідомлення</th></tr>"
            f"{rows or '<tr><td colspan=4 class=muted>У цьому форумі ще немає тем для обговорення</td></tr>'}</table></div>")
    return page(forum["name"], body, crumbs=forum_crumbs(c, forum)[:-1] + [(None, forum["name"])] if c else forum_crumbs(c, forum),
                course=c)


@app.get("/mod/forum/discuss.php")
def forum_discuss():
    d = qone("SELECT * FROM mdl_forum_discussions WHERE id=%s", (request.args.get("d", type=int) or 0,))
    if not d:
        return error_page("Неправильний ідентифікатор обговорення", 404)
    forum = qone("SELECT * FROM mdl_forum WHERE id=%s", (d["forum"],))
    c, role, u = forum_access(forum)
    posts = qall("SELECT p.*, u.firstname, u.lastname FROM mdl_forum_posts p JOIN mdl_user u ON u.id=p.userid "
                 "WHERE p.discussion=%s ORDER BY p.created, p.id", (d["id"],))
    can_reply = role == "teacher" if forum["type"] == "news" else role in ("student", "teacher")
    out = []
    for p in posts:
        pu = {"id": p["userid"], "firstname": p["firstname"], "lastname": p["lastname"]}
        rep = (f"<div style=\"text-align:right\"><a href=\"/mod/forum/post.php?reply={p['id']}\">Відповісти</a></div>"
               if can_reply else "")
        out.append(f"<div class=\"post{' reply' if p['parent'] else ''}\" id=\"p{p['id']}\"><div class=\"ph\">{avatar(pu, 38)}"
                   f"<div><b>{e(p['subject'])}</b><span class=\"muted\">від <a href=\"/user/profile.php?id={p['userid']}\">"
                   f"{e(fullname(pu))}</a> - {userdate(p['created'])}</span></div></div>"
                   f"<div>{nl2br(p['message'])}</div>{rep}</div>")
    crumbs = forum_crumbs(c, forum) + [(None, d["name"])]
    if c is None:
        crumbs = [("/mod/forum/view.php?f=1", "Новини сайту"), (None, d["name"])]
    return page(d["name"], "".join(out), crumbs=crumbs, course=c)


@app.route("/mod/forum/post.php", methods=["GET", "POST"])
def forum_post():
    u = require_login(allow_guest=False)
    parent = None
    if request.values.get("reply"):
        parent = qone("SELECT * FROM mdl_forum_posts WHERE id=%s", (request.values.get("reply", type=int) or 0,))
        if not parent:
            return error_page("Неправильний ідентифікатор повідомлення", 404)
        d = qone("SELECT * FROM mdl_forum_discussions WHERE id=%s", (parent["discussion"],))
        forum = qone("SELECT * FROM mdl_forum WHERE id=%s", (d["forum"],))
    else:
        forum = qone("SELECT * FROM mdl_forum WHERE id=%s", (request.values.get("forum", type=int) or 0,))
        d = None
        if not forum:
            return error_page("Неправильний ідентифікатор форуму", 404)
    c, role, u = forum_access(forum)
    may_reply = role == "teacher" if forum["type"] == "news" else role in ("student", "teacher")
    if parent is None and not can_start(forum, role) or parent is not None and not may_reply:
        return error_page("Вибачте, але у вас немає дозволу публікувати повідомлення в цьому форумі.", 403)
    if request.method == "POST":
        require_sesskey()
        subj = (request.form.get("subject") or "").strip()[:250]
        msg = (request.form.get("message") or "").strip()[:20000]
        if not subj or not msg:
            err = "Потрібно заповнити тему та повідомлення."
        else:
            t = now()
            if parent is None:
                did = qexec("INSERT INTO mdl_forum_discussions (forum, course, name, userid, timemodified) VALUES "
                            "(%s,%s,%s,%s,%s)", (forum["id"], forum["course"], subj, u["id"], t))
                pid = qexec("INSERT INTO mdl_forum_posts (discussion, parent, userid, created, subject, message) "
                            "VALUES (%s,0,%s,%s,%s,%s)", (did, u["id"], t, subj, msg))
            else:
                did = d["id"]
                pid = qexec("INSERT INTO mdl_forum_posts (discussion, parent, userid, created, subject, message) "
                            "VALUES (%s,%s,%s,%s,%s,%s)", (did, parent["id"], u["id"], t, subj, msg))
                qexec("UPDATE mdl_forum_discussions SET timemodified=%s WHERE id=%s", (t, did))
            atblog.log("education.forum_post", atblog.client_ip(request), forum=forum["id"], discussion=did,
                       post=pid, userid=u["id"], subject=subj[:120])
            logstore("\\mod_forum\\event\\post_created", "mod_forum", "created", u["id"], forum["course"], forum["cmid"])
            return redirect(f"/mod/forum/discuss.php?d={did}#p{pid}")
    else:
        err = ""
    subj = ("Re: " + parent["subject"].removeprefix("Re: ")) if parent else ""
    quoted = ""
    if parent:
        pu = qone("SELECT id, firstname, lastname FROM mdl_user WHERE id=%s", (parent["userid"],))
        quoted = (f"<div class=\"post\"><div class=\"ph\">{avatar(pu, 30)}<b>{e(parent['subject'])}</b></div>"
                  f"{nl2br(parent['message'])}</div>")
    body = (quoted + f"<div class=\"card\"><h2>{'Ваша відповідь' if parent else 'Нова тема'}</h2>"
            + (f"<div class=\"alert err\">{e(err)}</div>" if err else "")
            + "<form method=\"post\">"
            + (f"<input type=\"hidden\" name=\"reply\" value=\"{parent['id']}\">" if parent else
               f"<input type=\"hidden\" name=\"forum\" value=\"{forum['id']}\">")
            + f"<input type=\"hidden\" name=\"sesskey\" value=\"{sesskey()}\">"
            f"<label class=\"f\">Тема</label><input type=\"text\" name=\"subject\" value=\"{e(subj)}\" maxlength=\"250\">"
            "<label class=\"f\">Повідомлення</label><textarea name=\"message\"></textarea>"
            "<div style=\"margin-top:12px\"><button class=\"btn\">Надіслати до форуму</button> "
            "<a class=\"btn sec\" href=\"javascript:history.back()\">Скасувати</a></div></form></div>")
    return page(forum["name"], body, crumbs=forum_crumbs(c, forum) + [(None, "Нове повідомлення")], course=c)


# ---------------------------------------------------------------------------
# quiz
# ---------------------------------------------------------------------------
def quiz_by_cm(cmid):
    cm = get_cm(cmid, "quiz")
    q = qone("SELECT * FROM mdl_quiz WHERE cmid=%s", (cm["id"],))
    return cm, q


def questions_of(quizid):
    qs = qall("SELECT * FROM mdl_question WHERE quiz=%s ORDER BY slot", (quizid,))
    for x in qs:
        x["opts"] = json.loads(x["answers"])
    return qs


def attempt_grade(q, sumgrades):
    if sumgrades is None or not float(q["sumgrades"]):
        return None
    return float(sumgrades) / float(q["sumgrades"]) * float(q["grade"])


def get_attempt(aid, u, allow_teacher=True):
    a = qone("SELECT * FROM mdl_quiz_attempts WHERE id=%s", (aid or 0,))
    if not a:
        raise Bounce(error_page("Не вдалося знайти дані в таблиці quiz_attempts", 404))
    q = qone("SELECT * FROM mdl_quiz WHERE id=%s", (a["quiz"],))
    cm = qone("SELECT * FROM mdl_course_modules WHERE id=%s", (q["cmid"],))
    c, role, u = require_course(q["course"])
    if a["userid"] != u["id"] and not (allow_teacher and role == "teacher"):
        raise Bounce(error_page("Це не ваша спроба!", 403))
    return a, q, cm, c, role, u


@app.get("/mod/quiz/view.php")
def quiz_view():
    cm, q = quiz_by_cm(request.args.get("id"))
    c, role, u = require_course(cm["course"])
    info = [f"<p>{e(q['intro'])}</p>"]
    if q["timeclose"]:
        info.append(f"<p>Тест закривається: <b>{userdate(q['timeclose'])}</b></p>")
    if q["timelimit"]:
        info.append(f"<p>Обмеження часу: {q['timelimit'] // 60} хв</p>")
    info.append(f"<p>Дозволено спроб: {q['attempts'] or 'без обмежень'}</p>")
    info.append("<p>Метод оцінювання: Найвища оцінка</p>")
    info.append(f"<p>Прохідна оцінка: {num(q['gradepass'])} з {num(q['grade'])}</p>")
    body = [f"<div class=\"card\" style=\"text-align:center\">{''.join(info)}</div>"]
    if role == "guest":
        body.append("<div class=\"card\"><div class=\"alert info\">Цей тест недоступний для гостей. "
                    "<a href=\"/login/index.php\">Увійдіть</a>, щоб пройти тест.</div></div>")
        return page(cm["name"], "".join(body), crumbs=mod_crumbs(c, cm), course=c)
    atts = qall("SELECT * FROM mdl_quiz_attempts WHERE quiz=%s AND userid=%s ORDER BY attempt", (q["id"], u["id"]))
    if atts:
        rows = []
        for a in atts:
            gr = attempt_grade(q, a["sumgrades"])
            st = ("Завершено" + f"<div class=\"muted\">Надіслано {userdate(a['timefinish'])}</div>"
                  if a["state"] == "finished" else "У процесі")
            rv = (f"<a href=\"/mod/quiz/review.php?attempt={a['id']}\">Огляд</a>" if a["state"] == "finished"
                  else f"<a href=\"/mod/quiz/attempt.php?attempt={a['id']}\">Продовжити</a>")
            rows.append(f"<tr><td>{a['attempt']}</td><td>{st}</td><td>{num(a['sumgrades'])} / {num(q['sumgrades'])}</td>"
                        f"<td>{num(gr)}</td><td>{rv}</td></tr>")
        body.append("<div class=\"card\"><h3>Підсумок ваших попередніх спроб</h3><table class=\"gt\"><tr><th>Спроба</th>"
                    f"<th>Стан</th><th>Бали</th><th>Оцінка / {num(q['grade'])}</th><th>Огляд</th></tr>{''.join(rows)}</table>")
        best = qone("SELECT grade FROM mdl_quiz_grades WHERE quiz=%s AND userid=%s", (q["id"], u["id"]))
        if best:
            passed = float(best["grade"]) >= float(q["gradepass"])
            body.append(f"<h3 style=\"text-align:center;margin-top:16px\">Найвища оцінка: {num(best['grade'])} / {num(q['grade'])}.</h3>"
                        + ("<div class=\"alert ok\" style=\"text-align:center\">Вітаємо! Ви склали тест.</div>" if passed else
                           "<div class=\"alert warn\" style=\"text-align:center\">Прохідну оцінку ще не отримано.</div>"))
        body.append("</div>")
    inprog = next((a for a in atts if a["state"] == "inprogress"), None)
    finished = [a for a in atts if a["state"] == "finished"]
    closed = q["timeclose"] and q["timeclose"] < now()
    left = (q["attempts"] - len(finished)) if q["attempts"] else None
    if closed:
        btn = "<p>Цей тест закрито.</p>"
    elif inprog:
        btn = f"<a class=\"btn\" href=\"/mod/quiz/attempt.php?attempt={inprog['id']}\">Продовжити останню спробу</a>"
    elif left is not None and left <= 0:
        btn = "<p>Більше спроб не дозволено.</p>"
    else:
        lbl = "Спробувати ще раз" if finished else "Почати спробу"
        btn = (f"<form method=\"post\" action=\"/mod/quiz/startattempt.php\"><input type=\"hidden\" name=\"cmid\" value=\"{cm['id']}\">"
               f"<input type=\"hidden\" name=\"sesskey\" value=\"{sesskey()}\"><button class=\"btn\">{lbl}</button></form>")
    if role == "teacher":
        n = qone("SELECT COUNT(*) n FROM mdl_quiz_attempts WHERE quiz=%s AND state='finished'", (q["id"],))["n"]
        btn = (f"<p><a href=\"/grade/report/grader/index.php?id={c['id']}\">Спроб: {n}</a></p>") + btn
    body.append(f"<div style=\"text-align:center;margin:10px 0 20px\">{btn}</div>")
    return page(cm["name"], "".join(body), crumbs=mod_crumbs(c, cm), course=c)


@app.post("/mod/quiz/startattempt.php")
def quiz_start():
    cm, q = quiz_by_cm(request.form.get("cmid"))
    c, role, u = require_course(cm["course"])
    require_sesskey()
    if role not in ("student", "teacher"):
        return error_page("Цей тест недоступний для гостей.", 403)
    inprog = qone("SELECT * FROM mdl_quiz_attempts WHERE quiz=%s AND userid=%s AND state='inprogress'", (q["id"], u["id"]))
    if inprog:
        return redirect(f"/mod/quiz/attempt.php?attempt={inprog['id']}")
    n = qone("SELECT COUNT(*) n FROM mdl_quiz_attempts WHERE quiz=%s AND userid=%s", (q["id"], u["id"]))["n"]
    if q["timeclose"] and q["timeclose"] < now():
        return error_page("Цей тест закрито.", 403)
    if q["attempts"] and n >= q["attempts"]:
        return error_page("Більше спроб не дозволено.", 403)
    aid = qexec("INSERT INTO mdl_quiz_attempts (quiz, userid, attempt, state, timestart, responses) VALUES "
                "(%s,%s,%s,'inprogress',%s,'{}')", (q["id"], u["id"], n + 1, now()))
    atblog.log("education.quiz_attempt_start", atblog.client_ip(request), quiz=q["id"], cmid=cm["id"],
               attempt=aid, userid=u["id"])
    logstore("\\mod_quiz\\event\\attempt_started", "mod_quiz", "started", u["id"], c["id"], cm["id"])
    return redirect(f"/mod/quiz/attempt.php?attempt={aid}")


def _timer_js(deadline):
    return ("<script>(function(){var end=%d*1000;var el=document.getElementById('quiz-timer');"
            "function t(){var s=Math.max(0,Math.floor((end-Date.now())/1000));el.textContent="
            "Math.floor(s/60)+':'+('0'+s%%60).slice(-2);if(s<=0){var f=document.getElementById('responseform');"
            "var i=document.createElement('input');i.type='hidden';i.name='finishattempt';i.value='1';f.appendChild(i);"
            "f.submit();return;}setTimeout(t,1000);}t();})();</script>" % deadline)


@app.get("/mod/quiz/attempt.php")
def quiz_attempt():
    a, q, cm, c, role, u = get_attempt(request.args.get("attempt", type=int), current_user(), allow_teacher=False)
    if a["state"] != "inprogress":
        return redirect(f"/mod/quiz/review.php?attempt={a['id']}")
    resp = json.loads(a["responses"] or "{}")
    qs = questions_of(q["id"])
    blocks = []
    for x in qs:
        sel = resp.get(str(x["slot"]))
        opts = "".join(
            f"<li><label><input type=\"radio\" name=\"q{x['slot']}\" value=\"{i}\"{' checked' if sel == i else ''}> "
            f"{chr(97 + i)}. {e(o)}</label></li>" for i, o in enumerate(x["opts"]))
        st = "Відповідь збережено" if sel is not None else "Ще не дано відповіді"
        blocks.append(f"<div class=\"qblock\" id=\"q{x['slot']}\"><div class=\"qinfo\"><b>Питання {x['slot']}</b>{st}"
                      f"<br>Макс. оцінка: {num(x['defaultmark'])}</div><div class=\"qtext\">{e(x['questiontext'])}"
                      f"<ul class=\"opts\">{opts}</ul></div></div>")
    timer = ""
    if q["timelimit"]:
        deadline = a["timestart"] + q["timelimit"]
        timer = f"<div class=\"card\">Залишилось часу: <span class=\"timer\" id=\"quiz-timer\"></span></div>" + _timer_js(deadline)
    nav = "".join(f"<a href=\"#q{x['slot']}\">{x['slot']}</a>" for x in qs)
    body = (f"<div class=\"cols\"><div class=\"col-main\"><form method=\"post\" action=\"/mod/quiz/processattempt.php\" id=\"responseform\">"
            f"<input type=\"hidden\" name=\"attempt\" value=\"{a['id']}\"><input type=\"hidden\" name=\"sesskey\" value=\"{sesskey()}\">"
            + "".join(blocks) + "<div style=\"text-align:right\"><button class=\"btn\">Завершити спробу…</button></div></form></div>"
            f"<div class=\"col-side\">{timer}<div class=\"card\"><h3>Навігація тестом</h3><div class=\"qnav\">{nav}</div>"
            "<p style=\"margin-top:12px\"><a href=\"javascript:document.getElementById('responseform').submit()\">"
            "Завершити спробу…</a></p></div></div></div>")
    return page(cm["name"], body, crumbs=mod_crumbs(c, cm) + [(None, f"Спроба {a['attempt']}")], course=c)


@app.post("/mod/quiz/processattempt.php")
def quiz_process():
    a, q, cm, c, role, u = get_attempt(request.form.get("attempt", type=int), current_user(), allow_teacher=False)
    require_sesskey()
    if a["state"] != "inprogress":
        return redirect(f"/mod/quiz/review.php?attempt={a['id']}")
    qs = questions_of(q["id"])
    resp = json.loads(a["responses"] or "{}")
    for x in qs:
        v = request.form.get(f"q{x['slot']}")
        if v is not None and v.isdigit() and int(v) < len(x["opts"]):
            resp[str(x["slot"])] = int(v)
    qexec("UPDATE mdl_quiz_attempts SET responses=%s WHERE id=%s", (json.dumps(resp), a["id"]))
    if request.form.get("finishattempt") != "1":
        return redirect(f"/mod/quiz/summary.php?attempt={a['id']}")
    score = sum(float(x["defaultmark"]) for x in qs if resp.get(str(x["slot"])) == x["correct"])
    t = now()
    qexec("UPDATE mdl_quiz_attempts SET state='finished', timefinish=%s, sumgrades=%s WHERE id=%s", (t, score, a["id"]))
    grade = attempt_grade(q, score)
    qexec("INSERT INTO mdl_quiz_grades (quiz, userid, grade, timemodified) VALUES (%s,%s,%s,%s) "
          "ON DUPLICATE KEY UPDATE grade=GREATEST(grade, VALUES(grade)), timemodified=VALUES(timemodified)",
          (q["id"], u["id"], grade, t))
    if grade >= float(q["gradepass"]):
        mark_complete(cm["id"], u, role)
    atblog.log("education.quiz_submit", atblog.client_ip(request), quiz=q["id"], cmid=cm["id"], attempt=a["id"],
               userid=u["id"], score=score, grade=round(grade, 2), passed=grade >= float(q["gradepass"]))
    logstore("\\mod_quiz\\event\\attempt_submitted", "mod_quiz", "submitted", u["id"], c["id"], cm["id"])
    return redirect(f"/mod/quiz/review.php?attempt={a['id']}")


@app.get("/mod/quiz/summary.php")
def quiz_summary():
    a, q, cm, c, role, u = get_attempt(request.args.get("attempt", type=int), current_user(), allow_teacher=False)
    if a["state"] != "inprogress":
        return redirect(f"/mod/quiz/review.php?attempt={a['id']}")
    resp = json.loads(a["responses"] or "{}")
    rows = "".join(f"<tr><td><a href=\"/mod/quiz/attempt.php?attempt={a['id']}#q{x['slot']}\">{x['slot']}</a></td>"
                   f"<td>{'Відповідь збережено' if str(x['slot']) in resp else '<b>Ще не дано відповіді</b>'}</td></tr>"
                   for x in questions_of(q["id"]))
    body = (f"<div class=\"card\"><h2>Підсумок спроби</h2><table class=\"gt\"><tr><th>Питання</th><th>Стан</th></tr>{rows}</table>"
            f"<div style=\"text-align:center;margin-top:18px\"><a class=\"btn sec\" href=\"/mod/quiz/attempt.php?attempt={a['id']}\">"
            "Повернутися до спроби</a><form method=\"post\" action=\"/mod/quiz/processattempt.php\" style=\"margin-top:14px\" "
            "onsubmit=\"return confirm('Після надсилання ви більше не зможете змінити відповіді в цій спробі.')\">"
            f"<input type=\"hidden\" name=\"attempt\" value=\"{a['id']}\"><input type=\"hidden\" name=\"sesskey\" value=\"{sesskey()}\">"
            "<input type=\"hidden\" name=\"finishattempt\" value=\"1\"><button class=\"btn\">Надіслати все та завершити</button>"
            "</form></div></div>")
    return page(cm["name"], body, crumbs=mod_crumbs(c, cm) + [(None, "Підсумок спроби")], course=c)


@app.get("/mod/quiz/review.php")
def quiz_review():
    a, q, cm, c, role, u = get_attempt(request.args.get("attempt", type=int), current_user())
    if a["state"] != "finished":
        return redirect(f"/mod/quiz/attempt.php?attempt={a['id']}")
    resp = json.loads(a["responses"] or "{}")
    qs = questions_of(q["id"])
    who = qone("SELECT id, firstname, lastname FROM mdl_user WHERE id=%s", (a["userid"],))
    grade = attempt_grade(q, a["sumgrades"])
    pct = int(round(100 * float(a["sumgrades"]) / float(q["sumgrades"]))) if float(q["sumgrades"]) else 0
    dur = a["timefinish"] - a["timestart"]
    summ = ("<table class=\"generaltable\" style=\"width:100%\">"
            f"<tr><th style=\"width:220px\">Користувач</th><td>{avatar(who, 22)} {e(fullname(who))}</td></tr>"
            f"<tr><th>Розпочато</th><td>{userdate(a['timestart'])}</td></tr><tr><th>Стан</th><td>Завершено</td></tr>"
            f"<tr><th>Завершено</th><td>{userdate(a['timefinish'])}</td></tr>"
            f"<tr><th>Витрачений час</th><td>{dur // 60} хв {dur % 60} сек</td></tr>"
            f"<tr><th>Бали</th><td>{num(a['sumgrades'])}/{num(q['sumgrades'])}</td></tr>"
            f"<tr><th>Оцінка</th><td><b>{num(grade)}</b> з {num(q['grade'])} (<b>{pct}</b>%)</td></tr>"
            f"<tr><th>Відгук</th><td>{'Вітаємо, тест складено!' if grade >= float(q['gradepass']) else 'Тест не складено. Повторіть матеріал і спробуйте ще раз.'}</td></tr>"
            "</table>")
    blocks = []
    for x in qs:
        sel = resp.get(str(x["slot"]))
        right = sel == x["correct"]
        opts = "".join(
            f"<li>{'◉' if sel == i else '○'} {chr(97 + i)}. {e(o)} "
            + ("✅" if sel == i and right else "❌" if sel == i else "") + "</li>" for i, o in enumerate(x["opts"]))
        blocks.append(
            f"<div class=\"qblock\"><div class=\"qinfo\"><b>Питання {x['slot']}</b>"
            f"{'Правильно' if right else 'Неправильно' if sel is not None else 'Немає відповіді'}"
            f"<br>Балів {num(x['defaultmark'] if right else 0)} з {num(x['defaultmark'])}</div>"
            f"<div class=\"qtext {'right' if right else 'wrong'}\">{e(x['questiontext'])}<ul class=\"opts\">{opts}</ul>"
            f"<div class=\"fb\">{e(x['feedback'])}<br>Правильна відповідь: {e(x['opts'][x['correct']])}</div></div></div>")
    body = (f"<div class=\"card\">{summ}</div>" + "".join(blocks)
            + f"<div style=\"text-align:right\"><a class=\"btn\" href=\"/mod/quiz/view.php?id={cm['id']}\">Завершити перегляд</a></div>")
    return page(cm["name"], body, crumbs=mod_crumbs(c, cm) + [(None, f"Огляд спроби {a['attempt']}")], course=c)


# ---------------------------------------------------------------------------
# grades
# ---------------------------------------------------------------------------
def course_total(cid, uid):
    qz = qall("SELECT q.*, g.grade AS ugrade FROM mdl_quiz q LEFT JOIN mdl_quiz_grades g ON g.quiz=q.id AND g.userid=%s "
              "WHERE q.course=%s ORDER BY q.id", (uid, cid))
    graded = [x for x in qz if x["ugrade"] is not None]
    if not graded:
        return qz, None
    tot = sum(float(x["ugrade"]) / float(x["grade"]) for x in qz) / len(qz) * 100
    return qz, tot


@app.get("/grade/report/overview/index.php")
def grade_overview():
    u = require_login(allow_guest=False)
    rows = []
    for c in my_courses(u):
        if c["roleid"] in (3, 4):
            rows.append(f"<tr><td><a href=\"/grade/report/grader/index.php?id={c['id']}\">{e(c['fullname'])}</a></td>"
                        "<td class=\"muted\">Викладач — журнал оцінок</td></tr>")
            continue
        _, tot = course_total(c["id"], u["id"])
        rows.append(f"<tr><td><a href=\"/grade/report/user/index.php?id={c['id']}\">{e(c['fullname'])}</a></td>"
                    f"<td>{num(tot)}</td></tr>")
    body = ("<div class=\"card\"><h2>Курси, які я вивчаю</h2><table class=\"gt\"><tr><th>Назва курсу</th><th>Оцінка</th></tr>"
            f"{''.join(rows) or '<tr><td colspan=2 class=muted>Немає курсів</td></tr>'}</table></div>")
    return page("Оцінки", body, crumbs=[(None, "Оцінки"), (None, "Огляд оцінок")], heading="Огляд оцінок",
                drawer_active="gradesall")


@app.get("/grade/report/user/index.php")
def grade_user():
    c, role, u = require_course(request.args.get("id"))
    if role == "guest":
        return error_page("Гості не мають оцінок у цьому курсі.", 403)
    target = u
    if role == "teacher" and request.args.get("userid", type=int):
        target = qone("SELECT * FROM mdl_user WHERE id=%s", (request.args.get("userid", type=int),)) or u
    qz, tot = course_total(c["id"], target["id"])
    rows = []
    n = len(qz) or 1
    for x in qz:
        g_ = x["ugrade"]
        pct = f"{float(g_) / float(x['grade']) * 100:.2f} %".replace(".", ",") if g_ is not None else "-"
        fb = "" if g_ is None else ("Склав" if float(g_) >= float(x["gradepass"]) else "Не склав")
        contrib = f"{float(g_) / float(x['grade']) * 100 / n:.2f} %".replace(".", ",") if g_ is not None else "0,00 %"
        rows.append(f"<tr><td>📝 <a href=\"/mod/quiz/view.php?id={x['cmid']}\">{e(x['name'])}</a></td>"
                    f"<td>{num(100 / n)} %</td><td>{num(g_)}</td><td>0–{num(x['grade'], 0)}</td><td>{pct}</td>"
                    f"<td>{fb}</td><td>{contrib}</td></tr>")
    sel = ""
    if role == "teacher":
        studs = qall("SELECT u.id, u.firstname, u.lastname FROM mdl_user_enrolments e JOIN mdl_user u ON u.id=e.userid "
                     "WHERE e.courseid=%s AND e.roleid=5 ORDER BY u.lastname", (c["id"],))
        opts = "".join(f"<option value=\"{s['id']}\"{' selected' if s['id'] == target['id'] else ''}>{e(fullname(s))}</option>"
                       for s in studs)
        sel = (f"<form style=\"display:flex;gap:8px;max-width:420px;margin-bottom:12px\"><input type=\"hidden\" name=\"id\" "
               f"value=\"{c['id']}\"><select name=\"userid\">{opts}</select><button class=\"btn\">Показати</button></form>")
    body = (f"<div class=\"card\">{sel}<h3>{avatar(target, 26)} {e(fullname(target))}</h3><table class=\"gt\"><tr><th>Елемент оцінювання</th>"
            "<th>Розрахункова вага</th><th>Оцінка</th><th>Діапазон</th><th>Відсоток</th><th>Відгук</th>"
            f"<th>Внесок до підсумку курсу</th></tr>{''.join(rows)}"
            f"<tr><td><b>Σ Підсумок курсу</b></td><td>-</td><td><b>{num(tot)}</b></td><td>0–100</td>"
            f"<td>{(num(tot) + ' %') if tot is not None else '-'}</td><td></td><td>-</td></tr></table></div>")
    return page("Оцінки: звіт користувача", body, crumbs=[(f"/course/view.php?id={c['id']}", c["shortname"]),
                                                          (None, "Оцінки")], course=c, drawer_active="grades",
                heading="Звіт користувача")


@app.get("/grade/report/grader/index.php")
def grade_grader():
    c, role, u = require_course(request.args.get("id"))
    if role != "teacher":
        return error_page("Вибачте, але на даний момент у вас немає дозволу на це (moodle/grade:viewall).", 403)
    qz = qall("SELECT * FROM mdl_quiz WHERE course=%s ORDER BY id", (c["id"],))
    studs = qall("SELECT u.* FROM mdl_user_enrolments e JOIN mdl_user u ON u.id=e.userid WHERE e.courseid=%s AND "
                 "e.roleid=5 ORDER BY u.lastname", (c["id"],))
    head = "".join(f"<th>📝 {e(x['name'])}</th>" for x in qz)
    rows = []
    for s in studs:
        _, tot = course_total(c["id"], s["id"])
        cells = ""
        for x in qz:
            gr = qone("SELECT grade FROM mdl_quiz_grades WHERE quiz=%s AND userid=%s", (x["id"], s["id"]))
            cells += f"<td>{num(gr['grade']) if gr else '-'}</td>"
        rows.append(f"<tr><td>{avatar(s, 24)} <a href=\"/grade/report/user/index.php?id={c['id']}&userid={s['id']}\">"
                    f"{e(fullname(s))}</a></td><td class=\"muted\">{e(s['email'])}</td>{cells}<td><b>{num(tot)}</b></td></tr>")
    body = (f"<div class=\"card\" style=\"overflow-x:auto\"><table class=\"gt\"><tr><th>Ім'я / Прізвище</th><th>E-mail</th>{head}"
            f"<th>Σ Підсумок курсу</th></tr>{''.join(rows)}</table></div>")
    return page("Журнал оцінок", body, crumbs=[(f"/course/view.php?id={c['id']}", c["shortname"]), (None, "Журнал оцінок")],
                course=c, drawer_active="grades", heading="Журнал оцінок")


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------
@app.get("/user/index.php")
def participants():
    c, role, u = require_course(request.args.get("id"))
    if role == "guest":
        return error_page("Гості не можуть переглядати список учасників.", 403)
    rolef = request.args.get("roleid", type=int)
    sql = ("SELECT u.*, e.roleid, e.timeaccess AS caccess, r.name AS rolename FROM mdl_user_enrolments e "
           "JOIN mdl_user u ON u.id=e.userid JOIN mdl_role r ON r.id=e.roleid WHERE e.courseid=%s AND u.deleted=0")
    args = [c["id"]]
    if rolef:
        sql += " AND e.roleid=%s"
        args.append(rolef)
    rows = qall(sql + " ORDER BY e.roleid, u.lastname", args)
    tr = "".join(
        f"<tr><td><div style=\"display:flex;gap:10px;align-items:center\">{avatar(p, 32)}"
        f"<a href=\"/user/view.php?id={p['id']}&course={c['id']}\">{e(fullname(p))}</a></div></td>"
        f"<td>{e(p['email']) if p['maildisplay'] in (1, 2) or role == 'teacher' else '<span class=muted>прихована</span>'}</td>"
        f"<td>{e(p['rolename'])}</td><td class=\"muted\">Немає груп</td><td>{timeago(p['caccess'])}</td></tr>" for p in rows)
    filt = "".join(f"<a class=\"{'act' if (rolef or 0) == k else ''}\" href=\"?id={c['id']}{'&roleid=' + str(k) if k else ''}\">{v}</a>"
                   for k, v in ((0, "Усі"), (5, "Студенти"), (3, "Викладачі")))
    body = (f"<div class=\"card\"><div class=\"tabs\">{filt}</div><p><b>Знайдено учасників: {len(rows)}</b></p>"
            "<table class=\"gt\"><tr><th>Ім'я / Прізвище</th><th>Адреса електронної пошти</th><th>Ролі</th><th>Групи</th>"
            f"<th>Останній доступ до курсу</th></tr>{tr}</table></div>")
    return page("Учасники", body, crumbs=[(f"/course/view.php?id={c['id']}", c["shortname"]), (None, "Учасники")],
                course=c, drawer_active="participants", heading="Учасники")


@app.get("/user/view.php")
def user_view():
    return redirect(f"/user/profile.php?id={request.args.get('id', type=int) or 0}")


@app.get("/user/profile.php")
def user_profile():
    u = require_login(allow_guest=False)
    uid = request.args.get("id", type=int) or u["id"]
    p = qone("SELECT * FROM mdl_user WHERE id=%s AND deleted=0", (uid,))
    if not p or p["id"] == GUEST_ID:
        return error_page("Користувача не знайдено або видалено", 404)
    own = p["id"] == u["id"]
    if not own and p["auth"] == "nologin":
        return error_page("Профіль цього користувача недоступний.", 403)
    det = [f"<dt>Адреса електронної пошти</dt><dd>"
           + (f"<a href=\"mailto:{e(p['email'])}\">{e(p['email'])}</a>" if own or is_admin(u) or p["maildisplay"] in (1, 2)
              else "<span class=muted>прихована</span>") + "</dd>",
           "<dt>Країна</dt><dd>Україна</dd>"]
    if p["city"]:
        det.append(f"<dt>Місто</dt><dd>{e(p['city'])}</dd>")
    if p["institution"]:
        det.append(f"<dt>Установа</dt><dd>{e(p['institution'])}</dd>")
    if p["department"]:
        det.append(f"<dt>Відділ</dt><dd>{e(p['department'])}</dd>")
    if (own or is_admin(u)) and p["phone1"]:
        det.append(f"<dt>Телефон</dt><dd>{e(p['phone1'])}</dd>")
    courses = my_courses(p)
    cl = ", ".join(f"<a href=\"/course/view.php?id={c['id']}\">{e(c['fullname'])}</a>" for c in courses) or "—"
    edit = (f"<a class=\"btn sec\" href=\"/user/edit.php\" style=\"float:right\">Редагувати профіль</a>" if own else
            f"<a class=\"btn sec\" href=\"/message/index.php?id={p['id']}\" style=\"float:right\">💬 Повідомлення</a>")
    susp = "<span class=\"badge bad\">Заблоковано</span>" if p["suspended"] else ""
    head = (f"<div class=\"card\">{edit}<div style=\"display:flex;gap:16px;align-items:center\">{avatar(p, 80)}"
            f"<div><h1 style=\"margin:0\">{e(fullname(p))} {susp}</h1><div class=\"muted\">{e(p['department'])}"
            f"{' · ' + e(p['institution']) if p['institution'] else ''}</div></div></div>"
            + (f"<p style=\"margin-top:14px\">{nl2br(p['description'])}</p>" if p["description"] else "") + "</div>")
    reports = ""
    if own:
        reports = ("<div class=\"card\"><h3>Звіти</h3><a href=\"/grade/report/overview/index.php\">Огляд оцінок</a><br>"
                   "<a href=\"/calendar/view.php?view=upcoming\">Майбутні події</a></div>")
    body = (head + "<div class=\"cols\"><div class=\"col-main\">"
            f"<div class=\"card\"><h3>Деталі користувача</h3><dl class=\"prof\">{''.join(det)}</dl></div>"
            f"<div class=\"card\"><h3>Деталі курсу</h3><dl class=\"prof\"><dt>Профілі курсів</dt><dd>{cl}</dd></dl></div>"
            "</div><div class=\"col-side\">"
            "<div class=\"card\"><h3>Різне</h3><a href=\"/mod/forum/view.php?f=1\">Повідомлення форуму</a></div>"
            + reports +
            f"<div class=\"card\"><h3>Активність входу</h3><dl class=\"prof\" style=\"grid-template-columns:1fr\">"
            f"<dt>Перший доступ до сайту</dt><dd>{userdate(p['firstaccess'])} ({timeago(p['firstaccess'])})</dd>"
            f"<dt>Останній доступ до сайту</dt><dd>{userdate(p['lastaccess'])} ({timeago(p['lastaccess'])})</dd>"
            "</dl></div></div></div>")
    return page(fullname(p), body, crumbs=[(None, "Користувачі"), (None, fullname(p))], heading=False)


@app.route("/user/edit.php", methods=["GET", "POST"])
def user_edit():
    u = require_login(allow_guest=False)
    msg = ""
    if request.method == "POST":
        require_sesskey()
        city = (request.form.get("city") or "")[:120]
        phone = (request.form.get("phone1") or "")[:30]
        desc = (request.form.get("description") or "")[:4000]
        md = request.form.get("maildisplay", type=int)
        md = md if md in (0, 1, 2) else u["maildisplay"]
        qexec("UPDATE mdl_user SET city=%s, phone1=%s, description=%s, maildisplay=%s, timemodified=%s WHERE id=%s",
              (city, phone, desc, md, now(), u["id"]))
        atblog.log("education.profile_update", atblog.client_ip(request), userid=u["id"])
        return redirect(f"/user/profile.php?id={u['id']}")
    mdopts = "".join(f"<option value=\"{k}\"{' selected' if u['maildisplay'] == k else ''}>{v}</option>" for k, v in
                     ((0, "Приховати мою адресу від усіх"), (1, "Показувати адресу всім"),
                      (2, "Показувати адресу лише учасникам моїх курсів")))
    body = (f"<div class=\"card\">{msg}<form method=\"post\" style=\"max-width:640px\">"
            f"<input type=\"hidden\" name=\"sesskey\" value=\"{sesskey()}\">"
            f"<label class=\"f\">Ім'я</label><input type=\"text\" value=\"{e(u['firstname'])}\" disabled>"
            f"<label class=\"f\">Прізвище</label><input type=\"text\" value=\"{e(u['lastname'])}\" disabled>"
            f"<label class=\"f\">Адреса електронної пошти</label><input type=\"text\" value=\"{e(u['email'])}\" disabled>"
            "<div class=\"muted\">Ім'я та e-mail синхронізуються з кадровою системою (1С:ЗУП) і не можуть бути змінені тут.</div>"
            f"<label class=\"f\">Показувати e-mail</label><select name=\"maildisplay\">{mdopts}</select>"
            f"<label class=\"f\">Місто</label><input type=\"text\" name=\"city\" value=\"{e(u['city'])}\">"
            f"<label class=\"f\">Телефон</label><input type=\"text\" name=\"phone1\" value=\"{e(u['phone1'])}\">"
            f"<label class=\"f\">Опис</label><textarea name=\"description\">{e(u['description'])}</textarea>"
            "<div style=\"margin-top:14px\"><button class=\"btn\">Оновити профіль</button> "
            f"<a class=\"btn sec\" href=\"/user/profile.php?id={u['id']}\">Скасувати</a></div></form></div>")
    return page("Редагувати профіль", body, crumbs=[(f"/user/profile.php?id={u['id']}", fullname(u)), (None, "Редагувати профіль")])


@app.get("/user/preferences.php")
def user_prefs():
    u = require_login(allow_guest=False)
    body = ("<div class=\"cols\"><div class=\"col-main\"><div class=\"card\"><h3>Обліковий запис користувача</h3>"
            "<a href=\"/user/edit.php\">Редагувати профіль</a><br><a href=\"/login/change_password.php\">Змінити пароль</a><br>"
            "<a href=\"/user/language.php\">Мова інтерфейсу</a> <span class=\"muted\">(Українська ‎(uk)‎)</span><br>"
            "<a href=\"/message/notificationpreferences.php\">Налаштування сповіщень</a></div></div>"
            "<div class=\"col-side\"><div class=\"card\"><h3>Блоги</h3><span class=\"muted\">Блоги вимкнено адміністратором</span></div></div></div>")
    return page("Налаштування", body, crumbs=[(f"/user/profile.php?id={u['id']}", fullname(u)), (None, "Налаштування")])


@app.get("/user/policy.php")
@app.get("/admin/tool/dataprivacy/summary.php")
def policy():
    body = ("<div class=\"card content\"><h3>Політика обробки персональних даних</h3>"
            "<p>Навчальний портал ATB Education обробляє персональні дані працівників ТОВ «АТБ-маркет» (ПІБ, посада, "
            "підрозділ, корпоративна e-mail адреса, результати навчання) з метою організації обов'язкового та "
            "розвивального навчання відповідно до Закону України «Про захист персональних даних».</p>"
            "<table class=\"generaltable\"><tr><th>Категорія</th><th>Термін зберігання</th></tr>"
            "<tr><td>Облікові записи</td><td>Протягом трудових відносин + 1 рік</td></tr>"
            "<tr><td>Результати тестів та оцінки</td><td>3 роки</td></tr>"
            "<tr><td>Журнали подій (логи)</td><td>180 днів</td></tr><tr><td>Повідомлення форумів</td><td>3 роки</td></tr></table>"
            "<p>Відповідальна особа з питань захисту персональних даних: dpo@atbmarket.com</p></div>")
    return page("Підсумок збереження даних", body, crumbs=[(None, "Політика конфіденційності")])


# ---------------------------------------------------------------------------
# calendar
# ---------------------------------------------------------------------------
@app.route("/calendar/view.php", methods=["GET"])
def calendar_view():
    u = require_login()
    view = request.args.get("view", "month")
    ts = request.args.get("time", type=int) or now()
    courseid = request.args.get("course", type=int)
    cname = {c["id"]: c["fullname"] for c in qall("SELECT id, fullname FROM mdl_course")}
    d = dt(ts)
    tabs = "".join(f"<a class=\"{'act' if view == k else ''}\" href=\"?view={k}&time={ts}\">{v}</a>" for k, v in
                   (("month", "Місяць"), ("day", "День"), ("upcoming", "Майбутні події")))
    newev = "" if is_guest(u) else "<a class=\"btn\" href=\"/calendar/event.php\" style=\"float:right\">Нова подія</a>"
    if view == "upcoming":
        evs = visible_events(u, now(), now() + 60 * 86400, courseid)
        inner = event_items(evs, cname)
        title = "Майбутні події" + (f": {cname.get(courseid, '')}" if courseid else "")
    elif view == "day":
        start = int(datetime(d.year, d.month, d.day, tzinfo=TZ).timestamp())
        evs = visible_events(u, start, start + 86399)
        items = []
        for ev in evs:
            dur = f" — {userdate(ev['timestart'] + ev['timeduration'], 'time')}" if ev["timeduration"] else ""
            items.append(f"<div class=\"card\"><h3><a href=\"{event_link(ev)}\">{e(ev['name'])}</a></h3>"
                         f"<p>🕘 {userdate(ev['timestart'])}{dur}</p>"
                         + (f"<p>{e(ev['description'])}</p>" if ev["description"] else "")
                         + (f"<p>🎓 <a href=\"/course/view.php?id={ev['courseid']}\">{e(cname.get(ev['courseid'], ''))}</a></p>" if ev["courseid"] else "")
                         + f"<span class=\"badge\">{ {'site': 'Подія сайту', 'course': 'Подія курсу', 'close': 'Кінцевий термін', 'user': 'Особиста подія'}.get(ev['eventtype'], '')}</span></div>")
        prev_, next_ = start - 86400, start + 86400
        inner = (f"<div style=\"display:flex;justify-content:space-between;margin-bottom:12px\"><a href=\"?view=day&time={prev_}\">◄ Попередній день</a>"
                 f"<b>{userdate(start, 'dayname')} {d.year}</b><a href=\"?view=day&time={next_}\">Наступний день ►</a></div>"
                 + ("".join(items) or "<p class=\"muted\">Немає подій</p>"))
        title = "День"
    else:
        first = datetime(d.year, d.month, 1, tzinfo=TZ)
        days = calendar.monthrange(d.year, d.month)[1]
        evs = visible_events(u, int(first.timestamp()), int((first + timedelta(days=days)).timestamp()) - 1)
        byday = {}
        for ev in evs:
            byday.setdefault(dt(ev["timestart"]).day, []).append(ev)
        today = dt(now())
        cells = ["<td class=\"out\"></td>"] * first.weekday()
        for day in range(1, days + 1):
            dts = int(datetime(d.year, d.month, day, tzinfo=TZ).timestamp())
            evh = "".join(f"<a class=\"ev {e(ev['eventtype'])}\" href=\"{event_link(ev)}\" title=\"{e(ev['name'])}\">"
                          f"{userdate(ev['timestart'], 'time')} {e(ev['name'])}</a>" for ev in byday.get(day, []))
            cls = "today" if (today.year, today.month, today.day) == (d.year, d.month, day) else ""
            cells.append(f"<td class=\"{cls}\"><a class=\"dn\" href=\"?view=day&time={dts}\">{day}</a>{evh}</td>")
        while len(cells) % 7:
            cells.append("<td class=\"out\"></td>")
        rows = "".join("<tr>" + "".join(cells[i:i + 7]) + "</tr>" for i in range(0, len(cells), 7))
        pm = (first - timedelta(days=1)).replace(day=1)
        nm = first + timedelta(days=days)
        inner = (f"<div style=\"display:flex;justify-content:space-between;margin-bottom:12px\">"
                 f"<a href=\"?view=month&time={int(pm.timestamp())}\">◄ {MONTHS_NOM[pm.month - 1]}</a>"
                 f"<b style=\"font-size:1.15rem\">{MONTHS_NOM[d.month - 1]} {d.year}</b>"
                 f"<a href=\"?view=month&time={int(nm.timestamp())}\">{MONTHS_NOM[nm.month - 1]} ►</a></div>"
                 "<table class=\"cal\"><tr>" + "".join(f"<th>{w}</th>" for w in WD_SHORT) + f"</tr>{rows}</table>"
                 "<div class=\"muted\" style=\"margin-top:10px\"><span class=\"ev site\" style=\"display:inline\">Події сайту</span> "
                 "<span class=\"ev course\" style=\"display:inline\">Події курсу</span> "
                 "<span class=\"ev close\" style=\"display:inline\">Кінцеві терміни</span> "
                 "<span class=\"ev user\" style=\"display:inline\">Особисті події</span></div>")
        title = "Календар"
    body = f"<div class=\"card\">{newev}<div class=\"tabs\">{tabs}</div>{inner}</div>"
    return page(title, body, crumbs=[(None, "Календар")], heading="Календар", drawer_active="calendar")


@app.route("/calendar/event.php", methods=["GET", "POST"])
def calendar_event():
    u = require_login(allow_guest=False)
    err = ""
    if request.method == "POST":
        require_sesskey()
        name = (request.form.get("name") or "").strip()[:250]
        try:
            day = datetime.strptime((request.form.get("date") or "") + " " + (request.form.get("time") or "09:00"),
                                    "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        except ValueError:
            day = None
        if not name or not day:
            err = "Вкажіть назву та коректну дату."
        else:
            ts = int(day.timestamp())
            qexec("INSERT INTO mdl_event (name, description, courseid, userid, eventtype, timestart, timeduration) "
                  "VALUES (%s,%s,0,%s,'user',%s,0)", (name, (request.form.get("description") or "")[:2000], u["id"], ts))
            atblog.log("education.calendar_event", atblog.client_ip(request), userid=u["id"])
            return redirect(f"/calendar/view.php?view=day&time={ts}")
    today = dt(now()).strftime("%Y-%m-%d")
    body = (f"<div class=\"card\">" + (f"<div class=\"alert err\">{e(err)}</div>" if err else "")
            + f"<form method=\"post\" style=\"max-width:520px\"><input type=\"hidden\" name=\"sesskey\" value=\"{sesskey()}\">"
            "<label class=\"f\">Назва події</label><input type=\"text\" name=\"name\" maxlength=\"250\">"
            f"<label class=\"f\">Дата</label><input type=\"date\" name=\"date\" value=\"{today}\">"
            "<label class=\"f\">Час</label><input type=\"time\" name=\"time\" value=\"09:00\">"
            "<label class=\"f\">Тип події</label><select disabled><option>Особиста</option></select>"
            "<label class=\"f\">Опис</label><textarea name=\"description\" style=\"min-height:80px\"></textarea>"
            "<div style=\"margin-top:12px\"><button class=\"btn\">Зберегти</button> "
            "<a class=\"btn sec\" href=\"/calendar/view.php\">Скасувати</a></div></form></div>")
    return page("Нова подія", body, crumbs=[("/calendar/view.php", "Календар"), (None, "Нова подія")], drawer_active="calendar")


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------
@app.get("/message/index.php")
def messages():
    u = require_login(allow_guest=False)
    to = request.args.get("id", type=int)
    contacts = qall("SELECT DISTINCT u.id, u.firstname, u.lastname FROM mdl_user_enrolments e JOIN mdl_user u ON "
                    "u.id=e.userid WHERE e.roleid=3 AND e.courseid IN (SELECT courseid FROM mdl_user_enrolments WHERE "
                    "userid=%s) AND u.id<>%s", (u["id"], u["id"]))
    cl = "".join(f"<div style=\"display:flex;gap:8px;align-items:center;margin:6px 0\">{avatar(x, 28)}"
                 f"<a href=\"/message/index.php?id={x['id']}\">{e(fullname(x))}</a></div>" for x in contacts)
    right = "<p class=\"muted\">Немає повідомлень</p>"
    if to:
        t = qone("SELECT id, firstname, lastname FROM mdl_user WHERE id=%s AND id<>1", (to,))
        if t:
            right = (f"<h3>{avatar(t, 30)} {e(fullname(t))}</h3><p class=\"muted\">Немає повідомлень</p>"
                     "<div class=\"alert info\">Обмін особистими повідомленнями на порталі вимкнено. "
                     "Використовуйте корпоративну пошту.</div>")
    body = (f"<div class=\"cols\"><div class=\"col-side\" style=\"width:300px\"><div class=\"card\"><h3>Контакти</h3>{cl or '<p class=muted>Немає контактів</p>'}</div></div>"
            f"<div class=\"col-main\"><div class=\"card\">{right}</div></div></div>")
    return page("Повідомлення", body, crumbs=[(None, "Повідомлення")])


@app.get("/message/output/popup/notifications.php")
def notifications():
    u = require_login(allow_guest=False)
    rows = qall("SELECT d.id, d.name, d.timemodified FROM mdl_forum_discussions d WHERE d.forum=1 ORDER BY d.timemodified DESC LIMIT 5")
    items = "".join(f"<div class=\"evitem\"><div>🔔</div><div><a href=\"/mod/forum/discuss.php?d={r['id']}\">Новини сайту: "
                    f"{e(r['name'])}</a><div class=\"muted\">{timeago(r['timemodified'])} тому</div></div></div>" for r in rows)
    return page("Сповіщення", f"<div class=\"card\">{items}</div>", crumbs=[(None, "Сповіщення")])


@app.route("/admin/", methods=["GET", "POST"])
@app.route("/admin/<path:sub>", methods=["GET", "POST"])
def admin(sub="index.php"):
    if sub == "tool/dataprivacy/summary.php":
        return policy()
    if sub == "environment.php":
        return page(
            "Moodle", "<div class=\"card\"><p>Moodle — система управління навчанням з відкритим кодом.</p></div>",
            crumbs=[(None, "Moodle")])
    u = require_login(allow_guest=False)
    ip = atblog.client_ip(request)
    if not is_admin(u):
        atblog.log("education.admin_denied", ip, userid=u["id"], path=request.path)
        return error_page("Вибачте, але на даний момент у вас немає дозволу на це (moodle/site:config).", 403)
    atblog.log("education.admin_view", ip, userid=u["id"], path=request.path)
    n_users = qone("SELECT COUNT(*) n FROM mdl_user WHERE deleted=0")["n"]
    body = (f"<div class=\"card\"><h2>Сповіщення</h2><p>Moodle {e(CFG['release'])}</p>"
            "<div class=\"alert warn\">Доступна нова версія Moodle 3.9.25+. Рекомендуємо оновитися.</div>"
            f"<p>Користувачів: {n_users}</p><p>Завдання cron востаннє виконувалося {timeago(now() - 7200)} тому.</p></div>")
    return page("Адміністрування сайту", body, crumbs=[(None, "Адміністрування сайту")], drawer_active="admin")


@app.route("/md/", methods=["GET", "POST"])
@app.route("/md/<path:rest>", methods=["GET", "POST"])
def legacy_md(rest=""):
    # Portal was moved from https://education.atbmarket.com/md to the web root.
    qs = ("?" + request.query_string.decode()) if request.query_string else ""
    return redirect("/" + rest + qs, code=301)


@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@app.get("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80, threaded=True)
