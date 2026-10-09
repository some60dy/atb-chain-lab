"""Step 1b - education.atbmarket.com Moodle employee-training portal.
Unauthenticated config-disclosure bug in the moco_news block's ajax endpoint:
POST /md/blocks/moco_news/ajax.php?procedure=getPosts leaks DB/SMTP creds,
the Moodle password salt, and the site admin user ids with no auth.
"""
from flask import Flask, request, jsonify

import atblog

app = Flask(__name__)

CONFIG_LEAK = {
    "dbuser": "tmx",
    "dbpass": "DGGS845k45lkk340",
    "smtpuser": "education@atbmarket.com",
    "smtppass": "Edu003868$",
    "passwordsaltmain": "4STvnJrt33TTbdIY4Qt",
    "siteadmins": "2,3,5,8999,56948",
}


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
        return jsonify(posts=NEWS), 200
    atblog.log("education.ajax", ip, procedure=procedure)
    return jsonify(error="unknown procedure", procedure=procedure), 400


NEWS = [
    {"title": "Оновлено курс «Інформаційна безпека» — пройдіть до 30.11"},
    {"title": "Нова версія мобільного застосунку АТБ 8.0.48 для персоналу"},
    {"title": "Технічні роботи на порталі постачальників у суботу"},
]


# ---------------------------------------------------------------------------
# Moodle-style UI (static HTML, inline CSS, no external libs, offline-safe).
# ---------------------------------------------------------------------------

PAGE_CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  background:#f2f4f7;color:#2d2f31}
a{color:#0f6cbf;text-decoration:none}
a:hover{text-decoration:underline}
.navbar{background:#0f6cbf;color:#fff;display:flex;align-items:center;
  gap:14px;padding:0 18px;height:56px;box-shadow:0 2px 4px rgba(0,0,0,.15)}
.navbar .brand{display:flex;align-items:center;gap:10px;font-weight:700;
  font-size:1.05rem}
.navbar .logo{width:34px;height:34px;border-radius:7px;background:#fff;
  color:#0f6cbf;display:flex;align-items:center;justify-content:center;
  font-weight:800;font-size:1rem}
.navbar .sub{font-weight:400;font-size:.85rem;opacity:.85}
.navbar .spacer{flex:1}
.navbar .nav-link{color:#fff;font-size:.9rem;opacity:.95}
.wrap{max-width:1040px;margin:0 auto;padding:22px 16px 60px}
.hero{display:flex;flex-wrap:wrap;gap:22px;align-items:flex-start;
  margin-bottom:26px}
.hero-text{flex:1 1 320px}
.hero-text h1{margin:.2em 0 .3em;font-size:1.7rem;color:#1d2125}
.hero-text p{margin:.2em 0;color:#5c6066;line-height:1.5}
.login-card{flex:0 0 300px;background:#fff;border:1px solid #e0e3e7;
  border-radius:10px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.login-card h2{margin:0 0 14px;font-size:1.1rem;color:#1d2125}
.login-card label{display:block;font-size:.8rem;color:#5c6066;
  margin:10px 0 4px}
.login-card input{width:100%;padding:9px 10px;border:1px solid #c7ccd1;
  border-radius:6px;font-size:.95rem}
.login-card input:focus{outline:none;border-color:#0f6cbf;
  box-shadow:0 0 0 2px rgba(15,108,191,.18)}
.btn{display:inline-block;background:#0f6cbf;color:#fff;border:none;
  border-radius:6px;padding:10px 16px;font-size:.95rem;cursor:pointer;
  width:100%;margin-top:16px;font-weight:600}
.btn:hover{background:#0d5ca3}
.muted{font-size:.8rem;color:#8a9099;margin-top:12px;text-align:center}
.section-title{font-size:1.15rem;color:#1d2125;margin:30px 0 14px;
  border-bottom:2px solid #0f6cbf;padding-bottom:6px;display:inline-block}
.courses{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));
  gap:16px}
.course{background:#fff;border:1px solid #e0e3e7;border-radius:10px;
  overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.07);
  transition:box-shadow .15s}
.course:hover{box-shadow:0 4px 12px rgba(0,0,0,.12)}
.course .cover{height:90px;display:flex;align-items:center;
  justify-content:center;font-size:2rem;color:#fff}
.course .body{padding:12px 14px}
.course h3{margin:0 0 6px;font-size:1rem;color:#1d2125}
.course p{margin:0;font-size:.82rem;color:#6b7076}
.news{background:#fff;border:1px solid #e0e3e7;border-radius:10px;
  padding:16px 18px;margin-top:14px;box-shadow:0 1px 3px rgba(0,0,0,.07)}
.news h3{margin:0 0 10px;font-size:1rem;color:#1d2125}
#news-list{list-style:none;margin:0;padding:0;font-size:.88rem;color:#5c6066}
#news-list li{padding:7px 0;border-bottom:1px solid #eef0f2}
#news-list li:last-child{border-bottom:none}
.footer{background:#1d2125;color:#aeb4ba;text-align:center;
  padding:18px;font-size:.82rem;margin-top:40px}
.footer a{color:#cdd3d9}
@media(max-width:640px){
  .login-card{flex:1 1 100%}
  .navbar .sub{display:none}
}
"""

NEWS_JS = """
// Load the "Новини" block the same way the moco_news Moodle block does.
// <!-- moco_news block ajax: /md/blocks/moco_news/ajax.php -->
// moco_news 1.4: procedures getNews (block) / getPosts (legacy, admin dashboard)
(function () {
  var list = document.getElementById('news-list');
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
      list.innerHTML = posts.map(function (p) {
        return '<li>' + (p.title || p) + '</li>';
      }).join('');
    })
    .catch(function (e) {
      console.log('moco_news load failed', e);
      list.innerHTML = '<li>Не вдалося завантажити новини.</li>';
    });
})();
"""

COURSES = [
    ("Охорона праці", "Обов'язковий курс з техніки безпеки", "#1565c0", "⛑"),
    ("Касова дисципліна", "Правила роботи на касовому вузлі", "#2e7d32", "\U0001f4b3"),
    ("Інформаційна безпека", "Захист даних та фішинг", "#6a1b9a", "\U0001f512"),
    ("Онбординг", "Адаптація нових співробітників", "#ef6c00", "\U0001f44b"),
]


def _navbar():
    return (
        "<div class=\"navbar\">"
        "<div class=\"brand\"><span class=\"logo\">АТ</span>"
        "<span>ATB Education"
        "<span class=\"sub\"> &middot; Навчальний портал АТБ</span></span></div>"
        "<div class=\"spacer\"></div>"
        "<a class=\"nav-link\" href=\"/login/index.php\">Вхід</a>"
        "</div>"
    )


def _login_card(action="#"):
    return (
        f"<form class=\"login-card\" method=\"post\" action=\"{action}\">"
        "<h2>Вхід до порталу</h2>"
        "<label for=\"username\">Імʼя користувача</label>"
        "<input id=\"username\" name=\"username\" type=\"text\" "
        "autocomplete=\"username\" placeholder=\"ivan.petrenko\">"
        "<label for=\"password\">Пароль</label>"
        "<input id=\"password\" name=\"password\" type=\"password\" "
        "autocomplete=\"current-password\" placeholder=\"••••••••\">"
        "<button class=\"btn\" type=\"submit\">Увійти</button>"
        "<div class=\"muted\">Забули пароль? Зверніться до HR-відділу.</div>"
        "</form>"
    )


def _courses_html():
    cards = []
    for title, desc, color, icon in COURSES:
        cards.append(
            "<div class=\"course\">"
            f"<div class=\"cover\" style=\"background:{color}\">{icon}</div>"
            f"<div class=\"body\"><h3>{title}</h3><p>{desc}</p></div>"
            "</div>"
        )
    return "<div class=\"courses\">" + "".join(cards) + "</div>"


def _news_block():
    return (
        "<!-- moco_news block ajax: /md/blocks/moco_news/ajax.php -->"
        "<div class=\"news\">"
        "<h3>News / Новини</h3>"
        "<ul id=\"news-list\"><li>Завантаження новин…</li></ul>"
        "</div>"
    )


def _footer():
    return (
        "<div class=\"footer\">"
        "<div>ATB Education &mdash; Навчальний портал АТБ</div>"
        "<div>Powered by Moodle 3.x</div>"
        "</div>"
    )


def _shell(title, main_html):
    return (
        "<!doctype html><html lang=\"uk\"><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{title}</title>"
        f"<style>{PAGE_CSS}</style>"
        "</head><body>"
        + _navbar()
        + main_html
        + _footer()
        + f"<script>{NEWS_JS}</script>"
        "</body></html>"
    )


@app.get("/")
def index():
    main = (
        "<div class=\"wrap\">"
        "<div class=\"hero\">"
        "<div class=\"hero-text\">"
        "<h1>Навчальний портал АТБ</h1>"
        "<p>Ласкаво просимо до корпоративної системи навчання "
        "співробітників ТОВ «АТБ-маркет». Проходьте обовʼязкові тренінги, "
        "складайте тести та відстежуйте свій прогрес.</p>"
        "<p>Для доступу до курсів увійдіть за корпоративними обліковими "
        "даними.</p>"
        + _news_block()
        + "</div>"
        + _login_card("#")
        + "</div>"
        "<h2 class=\"section-title\">Доступні курси</h2>"
        + _courses_html()
        + "</div>"
    )
    return _shell("ATB Education — Навчальний портал АТБ", main), 200


@app.get("/login/index.php")
def login():
    main = (
        "<div class=\"wrap\">"
        "<div class=\"hero\">"
        "<div class=\"hero-text\">"
        "<h1>Вхід до ATB Education</h1>"
        "<p>Навчальний портал АТБ. Використовуйте корпоративний логін "
        "(формат <code>ім'я.прізвище</code>) для входу.</p>"
        + _news_block()
        + "</div>"
        + _login_card("#")
        + "</div>"
        "</div>"
    )
    return _shell("Вхід — ATB Education", main), 200


@app.get("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80)
