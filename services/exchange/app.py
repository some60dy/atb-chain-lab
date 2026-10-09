"""Step 9 - ex.atbmarket.com: Exchange 2016 EWS + Outlook on the web (OWA).

* EWS  (/ews/Exchange.asmx) - SOAP over HTTP Basic auth. FindItem, GetItem,
  GetAttachment, FindFolder/GetFolder, ResolveNames, CreateItem (send).
* OWA  (/owa) - forms login, three-pane mail (folders, list, reading pane),
  compose/reply/forward with in-process delivery between mailboxes, move /
  delete / flag / junk, search, People (GAL), Calendar, Options.

State lives in a small sqlite file inside the container (seeded on first
start from mailseed.py), so it resets whenever the container is recreated.
The stolen mailbox is supplier@atbmarket.com : supplier123569 (step 4 -> 9).
TLS is omitted for the lab; compose maps plain HTTP to port 8444.
"""
import base64
import hashlib
import html
import json
import os
import re
import secrets
import sqlite3
import threading
import uuid
import xml.etree.ElementTree as ET
from calendar import monthrange
from datetime import datetime, timedelta, timezone, date as ddate
from email.utils import format_datetime
from urllib.parse import quote, urlencode

from flask import Flask, request, Response, redirect, make_response, g, abort

import atblog
import mailseed as seed

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024

EWS_USER = "supplier@atbmarket.com"
EWS_PASS = "supplier123569"
RESET_BASE = seed.RESET_BASE
DOMAIN = seed.DOMAIN
TZ = seed.TZ
DB_PATH = os.environ.get("OWA_DB", "/var/lib/owa/mailstore.db")
OWA_COOKIE = "owa_session"
BLUE = "#0078d4"
SYSTEM_SENDER = "MicrosoftExchange329e71ec88ae4615bbc36ab6ce41109e@atbmarket.com"
QUOTA_GB = 50.0

_wlock = threading.RLock()

# =========================================================================== #
# Storage                                                                     #
# =========================================================================== #
SCHEMA = """
CREATE TABLE mailboxes (email TEXT PRIMARY KEY, password TEXT, display TEXT, archived INTEGER DEFAULT 0);
CREATE TABLE folders (id INTEGER PRIMARY KEY, mailbox TEXT, name TEXT, parent_id INTEGER, kind TEXT);
CREATE TABLE messages (
  id INTEGER PRIMARY KEY, mailbox TEXT, folder_id INTEGER, msgid TEXT,
  from_email TEXT, from_name TEXT, to_json TEXT, cc_json TEXT, bcc_json TEXT,
  subject TEXT, body_html TEXT, preview TEXT, received TEXT, is_read INTEGER, flagged INTEGER,
  importance TEXT, size INTEGER, headers TEXT, reset_link TEXT, category TEXT, is_draft INTEGER DEFAULT 0);
CREATE INDEX ix_msg_folder ON messages(mailbox, folder_id, received);
CREATE TABLE attachments (id INTEGER PRIMARY KEY, message_id INTEGER, filename TEXT, mime TEXT, data BLOB);
CREATE TABLE sessions (token TEXT PRIMARY KEY, email TEXT, created TEXT, ip TEXT);
CREATE TABLE settings (mailbox TEXT, key TEXT, value TEXT, PRIMARY KEY (mailbox, key));
CREATE TABLE rules (id INTEGER PRIMARY KEY, mailbox TEXT, name TEXT, field TEXT, value TEXT, folder_id INTEGER, enabled INTEGER DEFAULT 1);
CREATE TABLE events (id INTEGER PRIMARY KEY, mailbox TEXT, uid TEXT, subject TEXT, location TEXT, start TEXT, "end" TEXT,
  organizer TEXT, attendees TEXT, body TEXT, show_as TEXT, response TEXT);
CREATE TABLE autoreplied (mailbox TEXT, sender TEXT, PRIMARY KEY (mailbox, sender));
"""


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def db():
    if "db" not in g:
        g.db = _connect()
    return g.db


@app.teardown_appcontext
def _close_db(_exc):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def _utc(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _html_from_text(text):
    out = []
    for para in re.split(r"\n{2,}", text.strip("\n")):
        esc = html.escape(para)
        esc = re.sub(r"(https?://[^\s<]+)", r'<a href="\1" target="_blank" rel="noopener">\1</a>', esc)
        out.append("<p>" + esc.replace("\n", "<br>") + "</p>")
    return '<div style="font-family:Calibri,Segoe UI,Arial,sans-serif;font-size:14.5px">' + "\n".join(out) + "</div>"


def _strip(htm):
    t = re.sub(r"(?is)<(style|script).*?</\1>", " ", htm or "")
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    return re.sub(r"[ \t\xa0]+", " ", t).strip()


def _preview(htm):
    return re.sub(r"\s+", " ", _strip(htm))[:220]


def _mkheaders(frm, to, cc, subject, when, msgid, folder_kind, internal):
    rcv = format_datetime(when.astimezone(TZ))
    hops = []
    if internal:
        hops.append(f"Received: from EX-MBX-P02.atb.local (172.16.68.21) by EX-MBX-P01.atb.local (172.16.68.20)\n"
                    f" with Microsoft SMTP Server (version=TLS1_2, cipher=TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384)\n"
                    f" id 15.1.2507.39 via Mailbox Transport; {rcv}")
    else:
        dom = frm["email"].split("@")[-1]
        h = int(hashlib.md5(dom.encode()).hexdigest()[:6], 16)
        ip = f"{(h >> 16) % 200 + 31}.{(h >> 8) % 255}.{h % 255}.{(h >> 4) % 250 + 2}"
        hops.append(f"Received: from mx1.atbmarket.com (172.16.68.25) by EX-MBX-P01.atb.local (172.16.68.20)\n"
                    f" with Microsoft SMTP Server (version=TLS1_2) id 15.1.2507.39; {rcv}")
        hops.append(f"Received: from mail.{dom} (mail.{dom} [{ip}])\n by mx1.atbmarket.com (Postfix) with ESMTPS id "
                    f"{msgid[:10].upper()}\n for <supplier@atbmarket.com>; {rcv}")
        spf = "fail" if folder_kind == "junk" else "pass"
        hops.append(f"Authentication-Results: mx1.atbmarket.com; spf={spf} smtp.mailfrom={dom}; "
                    f"dkim={'none' if spf == 'fail' else 'pass'} header.d={dom}")
    lines = hops + [
        f"From: {frm['name']} <{frm['email']}>",
        "To: " + ", ".join(f"{a['name']} <{a['email']}>" for a in to),
    ]
    if cc:
        lines.append("CC: " + ", ".join(f"{a['name']} <{a['email']}>" for a in cc))
    lines += [f"Subject: {subject}", f"Date: {rcv}", f"Message-ID: <{msgid}@{frm['email'].split('@')[-1]}>",
              "Content-Language: uk-UA", "MIME-Version: 1.0",
              f"X-MS-Exchange-Organization-AuthAs: {'Internal' if internal else 'Anonymous'}",
              f"X-MS-Exchange-Organization-SCL: {9 if folder_kind == 'junk' else (-1 if internal else 1)}",
              "X-MS-Has-Attach: ", "X-Originating-IP: [172.16.68.140]" if internal else "X-MS-Exchange-Transport-EndToEndLatency: 00:00:01.4"]
    return "\n".join(lines)


def _folder_id(con, mailbox, kind_or_name):
    r = con.execute("SELECT id FROM folders WHERE mailbox=? AND (kind=? AND kind!='user' OR name=?) ORDER BY id LIMIT 1",
                    (mailbox, kind_or_name, kind_or_name)).fetchone()
    return r["id"] if r else None


def _insert_message(con, mailbox, folder_id, frm, to, cc, subject, body_html, when, *, bcc=None, read=False,
                    flagged=False, importance="Normal", atts=(), reset_link=None, category=None, is_draft=False,
                    headers=None, folder_kind="inbox"):
    msgid = uuid.uuid4().hex
    internal = frm["email"].endswith("@" + DOMAIN)
    headers = headers or _mkheaders(frm, to, cc, subject, when, msgid, folder_kind, internal)
    size = len(body_html.encode()) + sum(len(a[2]) for a in atts) + len(headers)
    cur = con.execute(
        "INSERT INTO messages (mailbox, folder_id, msgid, from_email, from_name, to_json, cc_json, bcc_json, subject,"
        " body_html, preview, received, is_read, flagged, importance, size, headers, reset_link, category, is_draft)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (mailbox, folder_id, msgid, frm["email"], frm["name"], json.dumps(to, ensure_ascii=False),
         json.dumps(cc, ensure_ascii=False), json.dumps(bcc or [], ensure_ascii=False), subject, body_html,
         _preview(body_html), _utc(when), int(read), int(flagged), importance, size, headers, reset_link, category,
         int(is_draft)))
    mid = cur.lastrowid
    for name, mime, data in atts:
        con.execute("INSERT INTO attachments (message_id, filename, mime, data) VALUES (?,?,?,?)",
                    (mid, name, mime, data))
    return mid


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        return
    tmp = DB_PATH + ".new"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    logins = seed.mailbox_logins()
    names = {p[0]: p[1] for p in seed.PEOPLE}
    for email, pw in logins.items():
        con.execute("INSERT INTO mailboxes VALUES (?,?,?,0)", (email, pw, names.get(email, email)))
        ids = {}
        for key, disp, parent, kind in (seed.FOLDERS if email == EWS_USER else seed.FOLDERS[:6]):
            cur = con.execute("INSERT INTO folders (mailbox, name, parent_id, kind) VALUES (?,?,?,?)",
                              (email, disp, ids.get(parent), kind))
            ids[key] = cur.lastrowid
        if email == EWS_USER:
            for name, field, value, fkey in seed.RULES:
                con.execute("INSERT INTO rules (mailbox, name, field, value, folder_id) VALUES (?,?,?,?,?)",
                            (email, name, field, value, ids[fkey]))
            for m in seed.build():
                fid = ids[m["folder"]]
                body = m["html"] or _html_from_text(m["text"] or "")
                _insert_message(con, email, fid, m["frm"], m["to"], m["cc"], m["subject"], body, m["when"],
                                read=m["read"], flagged=m.get("flag"), importance=m.get("importance", "Normal"),
                                atts=m["atts"], reset_link=m.get("reset_link"), category=m.get("category"),
                                is_draft=m["folder"] == "drafts", folder_kind=m["folder"])
            for (subj, loc, st, en, org, att, body, show) in seed.events():
                con.execute('INSERT INTO events (mailbox, uid, subject, location, start, "end", organizer, attendees,'
                            ' body, show_as, response) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                            (email, uuid.uuid4().hex, subj, loc, _utc(st), _utc(en), org, att, body, show,
                             "organizer" if org == email else "accepted"))
            con.executemany("INSERT INTO settings VALUES (?,?,?)", [
                (email, "signature", "--\nATB Supplier Desk\nВідділ по роботі з постачальниками | АТБ-Маркет\n"
                                     "+380 56 790-11-40 | supplier@atbmarket.com"),
                (email, "signature_auto", "1"), (email, "page_size", "50"), (email, "reading_pane", "right"),
                (email, "oof_enabled", "0"),
                (email, "oof_message", "Дякуємо за звернення! Відповімо протягом робочого дня (пн–пт, 9:00–18:00)."),
                (email, "inbox_claimed", str(seed.CLAIMED_INBOX_TOTAL)),
            ])
        if email in seed.OOF:
            con.executemany("INSERT INTO settings VALUES (?,?,?)",
                            [(email, "oof_enabled", "1"), (email, "oof_message", seed.OOF[email])])
    con.commit()
    con.close()
    os.replace(tmp, DB_PATH)


def setting(mailbox, key, default=""):
    r = db().execute("SELECT value FROM settings WHERE mailbox=? AND key=?", (mailbox, key)).fetchone()
    return r["value"] if r else default


def set_setting(mailbox, key, value):
    with _wlock:
        db().execute("INSERT OR REPLACE INTO settings VALUES (?,?,?)", (mailbox, key, value))
        db().commit()


# =========================================================================== #
# Directory helpers                                                            #
# =========================================================================== #
GAL = {p[0].lower(): dict(zip(("email", "name", "title", "dept", "office", "phone", "mobile", "manager", "kind"), p))
       for p in seed.PEOPLE}


def display_name(email):
    e = (email or "").lower()
    if e in GAL:
        return GAL[e]["name"]
    return seed.EXT_NAMES.get(email, email)


def parse_recipients(s):
    out, seen = [], set()
    for part in re.split(r"[;,\n]", s or ""):
        part = part.strip()
        if not part:
            continue
        m = re.search(r"<([^>]+)>", part)
        email = (m.group(1) if m else part).strip().strip('"')
        if "@" not in email:
            # resolve by display name / alias
            q = email.lower()
            hit = next((p for p in GAL.values() if p["name"].lower() == q or p["email"].split("@")[0] == q), None)
            if not hit:
                out.append({"email": email, "name": email, "bad": True})
                continue
            email = hit["email"]
        if email.lower() in seen:
            continue
        seen.add(email.lower())
        out.append({"email": email, "name": display_name(email)})
    return out


def initials(name):
    parts = [p for p in re.split(r"[\s(«»\"]+", name or "?") if p and p[0].isalpha()]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def avatar_color(s):
    palette = ["#0078d4", "#8764b8", "#038387", "#ca5010", "#498205", "#c239b3", "#986f0b", "#4f6bed", "#e3008c", "#00838f"]
    return palette[int(hashlib.md5((s or "").encode()).hexdigest(), 16) % len(palette)]


# =========================================================================== #
# Delivery                                                                     #
# =========================================================================== #
def _apply_rules(con, mailbox, frm, subject):
    for r in con.execute("SELECT * FROM rules WHERE mailbox=? AND enabled=1 ORDER BY id", (mailbox,)):
        hay = frm["email"] + " " + frm["name"] if r["field"] == "from" else subject
        if r["value"].lower() in hay.lower():
            return r["folder_id"]
    return _folder_id(con, mailbox, "inbox")


def _system_mail(con, mailbox, subject, body_html, frm=None):
    frm = frm or {"email": SYSTEM_SENDER, "name": "Microsoft Outlook"}
    return _insert_message(con, mailbox, _folder_id(con, mailbox, "inbox"), frm,
                           [{"email": mailbox, "name": display_name(mailbox)}], [], subject, body_html,
                           datetime.now(TZ), read=False)


def deliver(con, sender, to, cc, bcc, subject, body_html, atts, importance="Normal", category=None):
    """Deliver to in-org mailboxes, expand groups, generate NDR / auto-replies."""
    frm = {"email": sender, "name": display_name(sender)}
    now = datetime.now(TZ)
    targets, bad = [], []
    for a in to + cc + bcc:
        e = a["email"].lower()
        if a.get("bad") or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
            bad.append(a["email"])
        elif e in seed.GROUPS:
            targets += seed.GROUPS[e]
        elif e.endswith("@" + DOMAIN):
            if con.execute("SELECT 1 FROM mailboxes WHERE email=?", (e,)).fetchone() or GAL.get(e, {}).get("kind") == "room":
                targets.append(e)
            else:
                bad.append(a["email"])
    delivered = []
    for t in dict.fromkeys(targets):
        if not con.execute("SELECT 1 FROM mailboxes WHERE email=?", (t,)).fetchone():
            continue
        fid = _apply_rules(con, t, frm, subject)
        _insert_message(con, t, fid, frm, to, cc, subject, body_html, now, importance=importance,
                        atts=atts, category=category)
        delivered.append(t)
        # auto-replies
        if t == "it-helpdesk@atbmarket.com" and t != sender:
            inc = f"INC-00{48300 + con.execute('SELECT COUNT(*) FROM messages').fetchone()[0] % 700}"
            _insert_message(con, sender, _folder_id(con, sender, "inbox"),
                            {"email": t, "name": "IT Service Desk"}, [frm], [],
                            f"[{inc}] Заявку зареєстровано: {subject}",
                            _html_from_text(f"Вашу заявку {inc} зареєстровано.\n\nТема: {subject}\nПріоритет: P4 "
                                            "(стандартний)\nЧерга: 1st line support\n\nНа заявки відповідаємо протягом "
                                            "8 робочих годин. Щоб додати інформацію, відповідайте на цей лист, не "
                                            "змінюючи тему.\n\nIT Service Desk | вн. 1919"), now + timedelta(seconds=2))
        oof = con.execute("SELECT value FROM settings WHERE mailbox=? AND key='oof_enabled'", (t,)).fetchone()
        if oof and oof["value"] == "1" and t != sender and \
                not con.execute("SELECT 1 FROM autoreplied WHERE mailbox=? AND sender=?", (t, sender)).fetchone():
            text = con.execute("SELECT value FROM settings WHERE mailbox=? AND key='oof_message'", (t,)).fetchone()
            con.execute("INSERT INTO autoreplied VALUES (?,?)", (t, sender))
            _insert_message(con, sender, _folder_id(con, sender, "inbox"),
                            {"email": t, "name": display_name(t)}, [frm], [], f"Automatic reply: {subject}",
                            _html_from_text(text["value"] if text else ""), now + timedelta(seconds=3))
    if bad:
        _system_mail(con, sender, f"Undeliverable: {subject}", f"""<div style="font-family:Segoe UI,Arial;font-size:14px">
<p style="font-size:18px;color:#c00000">Delivery has failed to these recipients or groups:</p>
<p>{'<br>'.join(html.escape(b) for b in bad)}<br>
The e-mail address you entered couldn't be found. Please check the recipient's e-mail address and try to resend the message.
If the problem continues, please contact your helpdesk.</p>
<p style="color:#666;font-size:12px">Diagnostic information for administrators:<br>Generating server: EX-MBX-P01.atb.local<br>
{'<br>'.join(html.escape(b) + "<br>Remote Server returned '550 5.1.10 RESOLVER.ADR.RecipientNotFound; Recipient not found by SMTP address lookup'" for b in bad)}<br>
Original message headers:<br>Subject: {html.escape(subject)}<br>Date: {format_datetime(now)}</p></div>""")
    return delivered, bad


# =========================================================================== #
# Auth / sessions                                                              #
# =========================================================================== #
def _parse_basic(hdr):
    if not hdr or not hdr.startswith("Basic "):
        return None
    try:
        raw = base64.b64decode(hdr.split(" ", 1)[1]).decode("utf-8", "replace")
        user, _, pw = raw.partition(":")
        return user, pw
    except Exception:
        return None


def _normalize_user(u):
    u = (u or "").strip()
    if "\\" in u:
        u = u.split("\\", 1)[1]
    if u and "@" not in u:
        u = f"{u}@{DOMAIN}"
    return u.lower()


def check_password(user, pw):
    user = _normalize_user(user)
    r = db().execute("SELECT password FROM mailboxes WHERE email=?", (user,)).fetchone()
    if r and secrets.compare_digest(r["password"], pw or ""):
        return user
    return None


def _unauthorized():
    resp = Response("Unauthorized", status=401)
    resp.headers["WWW-Authenticate"] = 'Basic realm="ex.atbmarket.com"'
    return resp


def current_user():
    tok = request.cookies.get(OWA_COOKIE)
    if not tok:
        return None
    r = db().execute("SELECT email FROM sessions WHERE token=?", (tok,)).fetchone()
    return r["email"] if r else None


def need_login(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*a, **kw):
        user = current_user()
        if not user:
            nxt = request.full_path if request.method == "GET" else "/owa/"
            return redirect("/owa/auth/logon.aspx?" + urlencode({"url": nxt, "reason": 0}))
        g.user = user
        return fn(*a, **kw)
    return wrapper


# =========================================================================== #
# EWS                                                                          #
# =========================================================================== #
NS = {"s": "http://schemas.xmlsoap.org/soap/envelope/",
      "m": "http://schemas.microsoft.com/exchange/services/2006/messages",
      "t": "http://schemas.microsoft.com/exchange/services/2006/types"}
X = html.escape


def item_id(mid):
    return "AAMkADc0" + base64.b64encode(f"ATB:{mid}".encode()).decode()


def parse_item_id(s):
    s = s or ""
    m = re.match(r"^AAMk(\d+)=$", s)            # legacy ids from the old mock
    if m:
        return int(m.group(1))
    try:
        raw = base64.b64decode(s[8:] + "==").decode()
        return int(raw.split(":", 1)[1])
    except Exception:
        return None


def folder_xml_id(fid):
    return "AQMkADc0" + base64.b64encode(f"F:{fid}".encode()).decode()


def _ews_envelope(body):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
            xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
  <s:Header>
    <t:ServerVersionInfo MajorVersion="15" MinorVersion="1" MajorBuildNumber="2507"
                         MinorBuildNumber="39" Version="V2017_07_11"/>
  </s:Header>
  <s:Body>
{body}
  </s:Body>
</s:Envelope>"""


def _ews_fault(code, text, status=500):
    body = f"""    <s:Fault>
      <faultcode xmlns:a="http://schemas.microsoft.com/exchange/services/2006/types">a:{code}</faultcode>
      <faultstring xml:lang="en-US">{X(text)}</faultstring>
      <detail><e:ResponseCode xmlns:e="http://schemas.microsoft.com/exchange/services/2006/errors">{code}</e:ResponseCode></detail>
    </s:Fault>"""
    return Response(_ews_envelope(body), status=status, content_type="text/xml; charset=utf-8")


def _mbx_xml(name, email):
    return (f"<t:Mailbox><t:Name>{X(name)}</t:Name><t:EmailAddress>{X(email)}</t:EmailAddress>"
            f"<t:RoutingType>SMTP</t:RoutingType></t:Mailbox>")


def _xml_message(m, full=False, atts=None):
    rcv = m["received"].replace("+00:00", "Z")
    body = ""
    if m["reset_link"] or full:
        body = f'\n        <t:Body BodyType="HTML">{X(m["body_html"])}</t:Body>'
    extra = ""
    if full:
        to = "".join(_mbx_xml(a["name"], a["email"]) for a in json.loads(m["to_json"]))
        cc = "".join(_mbx_xml(a["name"], a["email"]) for a in json.loads(m["cc_json"]))
        extra += f"\n        <t:ToRecipients>{to}</t:ToRecipients>"
        if cc:
            extra += f"\n        <t:CcRecipients>{cc}</t:CcRecipients>"
        if atts:
            extra += "\n        <t:Attachments>" + "".join(
                f'<t:FileAttachment><t:AttachmentId Id="{X(att_id(a["id"]))}"/><t:Name>{X(a["filename"])}</t:Name>'
                f'<t:ContentType>{X(a["mime"])}</t:ContentType><t:Size>{a["sz"]}</t:Size></t:FileAttachment>'
                for a in atts) + "</t:Attachments>"
        extra += f"\n        <t:InternetMessageId>&lt;{m['msgid']}@{X(m['from_email'].split('@')[-1])}&gt;</t:InternetMessageId>"
    return f"""      <t:Message>
        <t:ItemId Id="{item_id(m['id'])}" ChangeKey="CQAAABYAAAC{m['id']:06d}"/>
        <t:ParentFolderId Id="{folder_xml_id(m['folder_id'])}"/>
        <t:Subject>{X(m['subject'])}</t:Subject>
        <t:Sensitivity>Normal</t:Sensitivity>
        <t:DateTimeReceived>{rcv}</t:DateTimeReceived>
        <t:Size>{m['size']}</t:Size>
        <t:Importance>{m['importance']}</t:Importance>
        <t:HasAttachments>{'true' if m['natt'] else 'false'}</t:HasAttachments>
        <t:IsRead>{'true' if m['is_read'] else 'false'}</t:IsRead>
        <t:Flag><t:FlagStatus>{'Flagged' if m['flagged'] else 'NotFlagged'}</t:FlagStatus></t:Flag>
        <t:From>
          {_mbx_xml(m['from_name'], m['from_email'])}
        </t:From>
        <t:Preview>{X(m['preview'])}</t:Preview>{body}{extra}
      </t:Message>"""


def att_id(aid):
    return "AAMkADc0QQ" + base64.b64encode(f"A:{aid}".encode()).decode()


def parse_att_id(s):
    try:
        return int(base64.b64decode(s[10:] + "==").decode().split(":", 1)[1])
    except Exception:
        return None


MSG_COLS = ("m.id, m.folder_id, m.msgid, m.from_email, m.from_name, m.to_json, m.cc_json, m.subject, m.body_html,"
            " m.preview, m.received, m.is_read, m.flagged, m.importance, m.size, m.reset_link, m.category, m.is_draft,"
            " m.headers, (SELECT COUNT(*) FROM attachments a WHERE a.message_id=m.id) AS natt")


def _resolve_folder(user, el):
    """Return folder row for a DistinguishedFolderId / FolderId element."""
    con = db()
    if el is None:
        return con.execute("SELECT * FROM folders WHERE mailbox=? AND kind='inbox'", (user,)).fetchone()
    tag = el.tag.split("}")[-1]
    if tag == "DistinguishedFolderId":
        key = (el.get("Id") or "inbox").lower()
        kind = {"inbox": "inbox", "sentitems": "sent", "drafts": "drafts", "deleteditems": "deleted",
                "junkemail": "junk", "archivemsgfolderroot": "archive", "archiveinbox": "archive"}.get(key)
        if key == "msgfolderroot":
            return {"id": 0, "name": "Top of Information Store", "kind": "root"}
        if not kind:
            return None
        return con.execute("SELECT * FROM folders WHERE mailbox=? AND kind=?", (user, kind)).fetchone()
    fid = el.get("Id", "")
    try:
        n = int(base64.b64decode(fid[8:] + "==").decode().split(":", 1)[1])
    except Exception:
        return None
    return con.execute("SELECT * FROM folders WHERE mailbox=? AND id=?", (user, n)).fetchone()


def folder_total(user, f):
    con = db()
    n = con.execute("SELECT COUNT(*) FROM messages WHERE mailbox=? AND folder_id=?", (user, f["id"])).fetchone()[0]
    if f["kind"] == "inbox":
        claimed = setting(user, "inbox_claimed", "")
        if claimed:
            n = max(n, int(claimed))
    return n


def _ews_folder_xml(user, f):
    con = db()
    unread = con.execute("SELECT COUNT(*) FROM messages WHERE mailbox=? AND folder_id=? AND is_read=0",
                         (user, f["id"])).fetchone()[0]
    kids = con.execute("SELECT COUNT(*) FROM folders WHERE mailbox=? AND parent_id=?", (user, f["id"])).fetchone()[0]
    return (f'<t:Folder><t:FolderId Id="{folder_xml_id(f["id"])}" ChangeKey="AQAAAB{f["id"]:04d}"/>'
            f'<t:FolderClass>IPF.Note</t:FolderClass><t:DisplayName>{X(f["name"])}</t:DisplayName>'
            f'<t:TotalCount>{folder_total(user, f)}</t:TotalCount><t:ChildFolderCount>{kids}</t:ChildFolderCount>'
            f'<t:UnreadCount>{unread}</t:UnreadCount></t:Folder>')


def _ews_resp(op, inner, cls="Success", code="NoError"):
    return f"""    <m:{op}Response>
      <m:ResponseMessages>
        <m:{op}ResponseMessage ResponseClass="{cls}">
          <m:ResponseCode>{code}</m:ResponseCode>
{inner}
        </m:{op}ResponseMessage>
      </m:ResponseMessages>
    </m:{op}Response>"""


def ews_find_item(user, op, ip):
    con = db()
    folder = _resolve_folder(user, op.find(".//m:ParentFolderIds/*", NS))
    if folder is None or isinstance(folder, dict):
        return _ews_envelope(_ews_resp("FindItem", "", "Error", "ErrorFolderNotFound")
                             .replace("<m:ResponseCode>", "<m:MessageText>The specified folder could not be found in the store."
                                      "</m:MessageText>\n          <m:ResponseCode>"))
    view = op.find(".//m:IndexedPageItemView", NS)
    limit, offset = 50, 0
    if view is not None:
        try:
            limit = max(1, min(int(view.get("MaxEntriesReturned", 50)), 1000))
            offset = max(0, int(view.get("Offset", 0)))
        except ValueError:
            pass
    qs = op.find(".//m:QueryString", NS)
    where, args = "m.mailbox=? AND m.folder_id=?", [user, folder["id"]]
    if qs is not None and (qs.text or "").strip():
        q = f"%{qs.text.strip()}%"
        where += " AND (m.subject LIKE ? OR m.body_html LIKE ? OR m.from_email LIKE ? OR m.from_name LIKE ?)"
        args += [q, q, q, q]
    rows = con.execute(f"SELECT {MSG_COLS} FROM messages m WHERE {where} ORDER BY m.received DESC LIMIT ? OFFSET ?",
                       args + [limit, offset]).fetchall()
    total = folder_total(user, folder) if qs is None else len(rows)
    resets = sum(1 for r in rows if r["reset_link"])
    atblog.log("exchange.finditem", ip, user=user, folder=folder["name"], total=total, returned=len(rows),
               reset_links=resets, via="ews",
               msg=f"EWS FindItem returned {folder['name']}; {resets} live password-reset GUIDs present")
    items = "\n".join(_xml_message(r) for r in rows)
    last = "true" if offset + len(rows) >= total else "false"
    inner = f"""          <m:RootFolder IndexedPagingOffset="{offset + len(rows)}" TotalItemsInView="{total}" IncludesLastItemInRange="{last}">
            <t:Items>
{items}
            </t:Items>
          </m:RootFolder>"""
    return _ews_envelope(_ews_resp("FindItem", inner))


def ews_get_item(user, op, ip):
    con = db()
    out = []
    for el in op.findall(".//m:ItemIds/t:ItemId", NS):
        mid = parse_item_id(el.get("Id"))
        r = con.execute(f"SELECT {MSG_COLS} FROM messages m WHERE m.mailbox=? AND m.id=?", (user, mid)).fetchone() \
            if mid else None
        if not r:
            out.append('        <m:GetItemResponseMessage ResponseClass="Error"><m:MessageText>The specified object '
                       'was not found in the store.</m:MessageText><m:ResponseCode>ErrorItemNotFound</m:ResponseCode>'
                       '<m:Items/></m:GetItemResponseMessage>')
            continue
        atts = con.execute("SELECT id, filename, mime, length(data) AS sz FROM attachments WHERE message_id=?",
                           (r["id"],)).fetchall()
        atblog.log("exchange.ews_getitem", ip, user=user, item=r["id"], subject=r["subject"],
                   reset_link=bool(r["reset_link"]))
        out.append('        <m:GetItemResponseMessage ResponseClass="Success"><m:ResponseCode>NoError</m:ResponseCode>'
                   f'<m:Items>\n{_xml_message(r, full=True, atts=atts)}\n        </m:Items></m:GetItemResponseMessage>')
    return _ews_envelope("    <m:GetItemResponse><m:ResponseMessages>\n" + "\n".join(out) +
                         "\n    </m:ResponseMessages></m:GetItemResponse>")


def ews_get_attachment(user, op, ip):
    con = db()
    out = []
    for el in op.findall(".//m:AttachmentIds/t:AttachmentId", NS):
        aid = parse_att_id(el.get("Id", ""))
        a = con.execute("SELECT a.* FROM attachments a JOIN messages m ON m.id=a.message_id WHERE a.id=? AND m.mailbox=?",
                        (aid, user)).fetchone() if aid else None
        if not a:
            out.append('<m:GetAttachmentResponseMessage ResponseClass="Error"><m:ResponseCode>ErrorInvalidIdMalformed'
                       '</m:ResponseCode></m:GetAttachmentResponseMessage>')
            continue
        atblog.log("exchange.attachment_download", ip, user=user, filename=a["filename"], via="ews")
        out.append('<m:GetAttachmentResponseMessage ResponseClass="Success"><m:ResponseCode>NoError</m:ResponseCode>'
                   f'<m:Attachments><t:FileAttachment><t:AttachmentId Id="{att_id(a["id"])}"/><t:Name>{X(a["filename"])}'
                   f'</t:Name><t:ContentType>{X(a["mime"])}</t:ContentType><t:Content>'
                   f'{base64.b64encode(a["data"]).decode()}</t:Content></t:FileAttachment></m:Attachments>'
                   '</m:GetAttachmentResponseMessage>')
    return _ews_envelope("    <m:GetAttachmentResponse><m:ResponseMessages>" + "".join(out) +
                         "</m:ResponseMessages></m:GetAttachmentResponse>")


def ews_find_folder(user, op, ip, get=False):
    con = db()
    if get:
        fs = [f for f in (_resolve_folder(user, el) for el in op.findall(".//m:FolderIds/*", NS)) if f is not None]
        fs = [f for f in fs if not isinstance(f, dict)]
    else:
        fs = con.execute("SELECT * FROM folders WHERE mailbox=? ORDER BY id", (user,)).fetchall()
    atblog.log("exchange.ews_folders", ip, user=user, op="GetFolder" if get else "FindFolder", count=len(fs))
    xml = "".join(_ews_folder_xml(user, f) for f in fs)
    opname = "GetFolder" if get else "FindFolder"
    if get:
        inner = f"          <m:Folders>{xml}</m:Folders>"
    else:
        inner = (f'          <m:RootFolder TotalItemsInView="{len(fs)}" IncludesLastItemInRange="true">'
                 f'<t:Folders>{xml}</t:Folders></m:RootFolder>')
    return _ews_envelope(_ews_resp(opname, inner))


def ews_resolve_names(user, op, ip):
    q = (op.findtext("m:UnresolvedEntry", "", NS) or "").strip().lower()
    hits = [p for p in GAL.values() if q and (q in p["email"].lower() or q in p["name"].lower())][:100]
    atblog.log("exchange.gal_lookup", ip, user=user, query=q, results=len(hits), via="ews")
    if not hits:
        return _ews_envelope(_ews_resp("ResolveNames", "", "Error", "ErrorNameResolutionNoResults"))
    res = "".join(
        f"<t:Resolution>{_mbx_xml(p['name'], p['email'])}<t:Contact><t:DisplayName>{X(p['name'])}</t:DisplayName>"
        f"<t:JobTitle>{X(p['title'])}</t:JobTitle><t:Department>{X(p['dept'])}</t:Department>"
        f"<t:OfficeLocation>{X(p['office'])}</t:OfficeLocation>"
        f"<t:PhoneNumbers><t:Entry Key=\"BusinessPhone\">{X(p['phone'])}</t:Entry>"
        f"<t:Entry Key=\"MobilePhone\">{X(p['mobile'])}</t:Entry></t:PhoneNumbers></t:Contact></t:Resolution>"
        for p in hits)
    cls = "Success" if len(hits) == 1 else "Warning"
    code = "NoError" if len(hits) == 1 else "ErrorNameResolutionMultipleResults"
    return _ews_envelope(_ews_resp("ResolveNames",
                                   f'          <m:ResolutionSet TotalItemsInView="{len(hits)}" IncludesLastItemInRange="true">'
                                   f"{res}</m:ResolutionSet>", cls, code))


def ews_create_item(user, op, ip):
    con = db()
    msg = op.find(".//t:Message", NS)
    if msg is None:
        return _ews_fault("ErrorInvalidRequest", "Only message items are supported by this server.")
    subj = msg.findtext("t:Subject", "", NS)
    body_el = msg.find("t:Body", NS)
    body = body_el.text or "" if body_el is not None else ""
    if body_el is None or body_el.get("BodyType", "HTML") == "Text":
        body = _html_from_text(body)
    to = [{"email": e.text, "name": display_name(e.text)}
          for e in msg.findall("t:ToRecipients/t:Mailbox/t:EmailAddress", NS) if e.text]
    cc = [{"email": e.text, "name": display_name(e.text)}
          for e in msg.findall("t:CcRecipients/t:Mailbox/t:EmailAddress", NS) if e.text]
    disp = op.get("MessageDisposition", "SaveOnly")
    with _wlock:
        frm = {"email": user, "name": display_name(user)}
        if disp == "SaveOnly":
            mid = _insert_message(con, user, _folder_id(con, user, "drafts"), frm, to, cc, subj, body,
                                  datetime.now(TZ), read=True, is_draft=True)
        else:
            mid = _insert_message(con, user, _folder_id(con, user, "sent"), frm, to, cc, subj, body,
                                  datetime.now(TZ), read=True)
            deliver(con, user, to, cc, [], subj, body, [])
        con.commit()
    atblog.log("exchange.message_send" if disp != "SaveOnly" else "exchange.draft_save", ip, user=user,
               to=[a["email"] for a in to + cc], subject=subj, via="ews")
    return _ews_envelope(_ews_resp("CreateItem", f'          <m:Items><t:Message><t:ItemId Id="{item_id(mid)}"/>'
                                                 f'</t:Message></m:Items>'))


WSDL_STUB = """<?xml version="1.0" encoding="utf-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:tns="http://schemas.microsoft.com/exchange/services/2006/messages"
                  targetNamespace="http://schemas.microsoft.com/exchange/services/2006/messages">
  <wsdl:service name="ExchangeServices">
    <wsdl:port name="ExchangeServicePort" binding="tns:ExchangeServiceBinding">
      <soap:address location="https://ex.atbmarket.com/ews/Exchange.asmx"
                    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"/>
    </wsdl:port>
  </wsdl:service>
</wsdl:definitions>"""


@app.route("/ews/Exchange.asmx", methods=["GET", "POST"])
@app.route("/EWS/Exchange.asmx", methods=["GET", "POST"])
def ews():
    ip = atblog.client_ip(request)
    if request.method == "GET" and "wsdl" in request.query_string.decode().lower():
        return Response(WSDL_STUB, status=200, content_type="text/xml; charset=utf-8")

    creds = _parse_basic(request.headers.get("Authorization", ""))
    if not creds:
        atblog.log("exchange.auth_missing", ip, path="/ews/Exchange.asmx")
        return _unauthorized()
    user = check_password(*creds)
    if not user:
        atblog.log("exchange.auth_fail", ip, user=creds[0], via="ews")
        return _unauthorized()
    atblog.log("exchange.ews_auth", ip, user=user)
    if request.method == "GET":
        return Response(WSDL_STUB, status=200, content_type="text/xml; charset=utf-8")

    try:
        root = ET.fromstring(request.get_data())
        body = root.find("s:Body", NS)
        op = list(body)[0]
    except Exception:
        return _ews_fault("ErrorSchemaValidation", "The request failed schema validation: Data at the root level is invalid.")
    name = op.tag.split("}")[-1]
    handlers = {"FindItem": ews_find_item, "GetItem": ews_get_item, "GetAttachment": ews_get_attachment,
                "FindFolder": ews_find_folder, "GetFolder": lambda u, o, i: ews_find_folder(u, o, i, get=True),
                "ResolveNames": ews_resolve_names, "CreateItem": ews_create_item}
    if name not in handlers:
        atblog.log("exchange.ews_unsupported", ip, user=user, op=name)
        return _ews_fault("ErrorInvalidRequest", f"The request is invalid. Operation '{name}' is not available "
                                                 "for this account (EWS application access policy).")
    return Response(handlers[name](user, op, ip), status=200, content_type="text/xml; charset=utf-8")


@app.route("/autodiscover/autodiscover.xml", methods=["GET", "POST"])
@app.route("/Autodiscover/Autodiscover.xml", methods=["GET", "POST"])
def autodiscover():
    ip = atblog.client_ip(request)
    creds = _parse_basic(request.headers.get("Authorization", ""))
    if not creds:
        return _unauthorized()
    user = check_password(*creds)
    if not user:
        atblog.log("exchange.auth_fail", ip, user=creds[0], via="autodiscover")
        return _unauthorized()
    atblog.log("exchange.autodiscover", ip, user=user)
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006">
  <Response xmlns="http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a">
    <User><DisplayName>{X(display_name(user))}</DisplayName><AutoDiscoverSMTPAddress>{X(user)}</AutoDiscoverSMTPAddress></User>
    <Account><AccountType>email</AccountType><Action>settings</Action>
      <Protocol><Type>EXPR</Type><Server>ex.atbmarket.com</Server><SSL>On</SSL><AuthPackage>Basic</AuthPackage>
        <EwsUrl>https://ex.atbmarket.com/EWS/Exchange.asmx</EwsUrl><OOFUrl>https://ex.atbmarket.com/EWS/Exchange.asmx</OOFUrl>
        <OWAUrl AuthenticationMethod="FBA">https://ex.atbmarket.com/owa/</OWAUrl></Protocol>
    </Account>
  </Response>
</Autodiscover>"""
    return Response(xml, content_type="text/xml; charset=utf-8")


# =========================================================================== #
# OWA - presentation helpers                                                   #
# =========================================================================== #
def E(s):
    return html.escape(str(s if s is not None else ""))


def local(iso):
    return datetime.fromisoformat(iso).astimezone(TZ)


DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def fmt_list(iso):
    d = local(iso)
    now = datetime.now(TZ)
    if d.date() == now.date():
        return d.strftime("%H:%M")
    if (now.date() - d.date()).days < 7:
        return f"{DAYS[d.weekday()]} {d.strftime('%H:%M')}"
    if d.year == now.year:
        return f"{DAYS[d.weekday()]} {d.strftime('%d.%m')}"
    return d.strftime("%d.%m.%Y")


def fmt_full(iso):
    d = local(iso)
    return f"{DAYS[d.weekday()]} {d.strftime('%d.%m.%Y %H:%M')}"


def nfmt(n):
    return f"{n:,}".replace(",", "\u202f")


def fmt_size(n):
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1048576:.1f} MB"


ICONS = {
    "mail": "M3 6h18v12H3z M3 6l9 7 9-7",
    "cal": "M4 5h16v15H4z M4 9h16 M8 3v4 M16 3v4",
    "people": "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6 M16 4.3a3.5 3.5 0 0 1 0 6.4 M18 14.3c2.1.7 3.5 2.6 3.5 5.7",
    "gear": "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
    "search": "M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z M15.5 15.5L21 21",
    "reply": "M10 8V4L3 11l7 7v-4c5 0 8.5 1.6 11 5-1-5-4-10-11-11z",
    "replyall": "M7 8V5L1 11l6 6v-3 M13 9V5l-7 6 7 6v-4c4.5 0 7.5 1.4 10 4.5-1-4.5-4-9-10-9.5z",
    "fwd": "M14 8V4l7 7-7 7v-4C9 14 5.5 15.6 3 19c1-5 4-10 11-11z",
    "trash": "M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13 M10 11v6 M14 11v6",
    "flag": "M5 21V4 M5 4h11l-2 4 2 4H5",
    "folder": "M3 6h6l2 2h10v11H3z",
    "clip": "M21 11l-8.5 8.5a5 5 0 0 1-7-7L14 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 7",
    "junk": "M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z M9 9l6 6 M15 9l-6 6",
    "archive": "M3 4h18v4H3z M5 8v12h14V8 M10 12h4",
    "plus": "M12 5v14 M5 12h14",
    "inbox": "M3 13l3-8h12l3 8v6H3z M3 13h5l1 3h6l1-3h5",
    "sent": "M3 11l18-8-8 18-2-8z",
    "draft": "M4 20h4L19 9l-4-4L4 16z",
    "read": "M3 9l9 6 9-6 M3 9v11h18V9 M3 9l9-6 9 6",
    "move": "M3 6h6l2 2h10v11H3z M11 13h6 M14 10l3 3-3 3",
    "more": "M5 12h.01 M12 12h.01 M19 12h.01",
    "dl": "M12 4v11 M7 10l5 5 5-5 M5 20h14",
    "eye": "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "grid": "M4 4h4v4H4z M10 4h4v4h-4z M16 4h4v4h-4z M4 10h4v4H4z M10 10h4v4h-4z M16 10h4v4h-4z M4 16h4v4H4z M10 16h4v4h-4z M16 16h4v4h-4z",
    "bell": "M6 16V11a6 6 0 0 1 12 0v5l2 2H4z M10 20a2 2 0 0 0 4 0",
    "help": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14 M12 17h.01",
    "left": "M15 5l-7 7 7 7", "right": "M9 5l7 7-7 7",
    "imp": "M12 4v10 M12 18h.01",
    "send": "M3 11l18-8-8 18-2-8z",
    "x": "M6 6l12 12 M18 6L6 18",
    "print": "M6 9V3h12v6 M6 18H4v-7h16v7h-2 M6 14h12v7H6z",
    "check": "M4 12l5 5L20 6",
    "info": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 11v6 M12 7h.01",
}


def ico(name, size=16, cls=""):
    return (f'<svg class="ic {cls}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            f'<path d="{ICONS[name]}"/></svg>')


CSS = """
:root{--blue:#0078d4;--blue-d:#106ebe;--bg:#faf9f8;--line:#edebe9;--txt:#201f1e;--sub:#605e5c;--sel:#cfe4fa;--hov:#f3f2f1}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--txt);font:14px "Segoe UI",-apple-system,BlinkMacSystemFont,Roboto,"Helvetica Neue",Arial,sans-serif}
a{color:var(--blue);text-decoration:none} a:hover{text-decoration:underline}
.ic{vertical-align:-3px;flex:none}
button,input,select,textarea{font:inherit;color:inherit}
.top{height:48px;background:var(--blue);color:#fff;display:flex;align-items:center;gap:6px;padding:0 8px 0 0}
.top .waffle{width:48px;height:48px;display:flex;align-items:center;justify-content:center;color:#fff}
.top .waffle:hover{background:var(--blue-d)}
.top .brand{font-size:16px;font-weight:600;padding:0 14px 0 2px;color:#fff;white-space:nowrap}
.top form.search{flex:1;max-width:520px;margin:0 auto;display:flex;align-items:center;background:#deecf9;border-radius:4px;height:32px;padding:0 10px;color:var(--blue-d)}
.top form.search input{border:0;background:transparent;flex:1;padding:0 8px;outline:none;color:#201f1e}
.top form.search select{border:0;background:transparent;font-size:12px;color:var(--sub);outline:none}
.top .tb{width:48px;height:48px;display:flex;align-items:center;justify-content:center;color:#fff;position:relative}
.top .tb:hover{background:var(--blue-d);text-decoration:none}
.top .me{display:flex;align-items:center;gap:8px;color:#fff;padding:0 6px 0 8px;height:48px}
.top .me:hover{background:var(--blue-d);text-decoration:none}
.av{display:inline-flex;align-items:center;justify-content:center;border-radius:50%;color:#fff;font-weight:600;flex:none}
.shell{display:flex;height:calc(100vh - 48px)}
.rail{width:48px;background:#f0f0f0;border-right:1px solid var(--line);display:flex;flex-direction:column;align-items:center;padding-top:6px;gap:2px}
.rail a{width:40px;height:40px;display:flex;align-items:center;justify-content:center;color:#424242;border-radius:4px}
.rail a:hover{background:#e1dfdd;text-decoration:none}
.rail a.on{color:var(--blue);background:#fff;box-shadow:inset 3px 0 0 var(--blue)}
.fp{width:228px;background:var(--bg);border-right:1px solid var(--line);overflow:auto;flex:none;padding:8px 0}
.newbtn{margin:4px 12px 10px;display:flex;align-items:center;gap:8px;background:var(--blue);color:#fff;border:0;border-radius:4px;height:32px;padding:0 12px;cursor:pointer;font-weight:600}
.newbtn:hover{background:var(--blue-d);text-decoration:none}
.fp .sec{font-size:12px;font-weight:600;color:var(--sub);padding:10px 16px 4px;display:flex;align-items:center;justify-content:space-between}
.fp a.f{display:flex;align-items:center;gap:10px;padding:6px 14px;color:var(--txt);border-left:3px solid transparent}
.fp a.f:hover{background:var(--hov);text-decoration:none}
.fp a.f.on{background:var(--sel);border-left-color:var(--blue);font-weight:600}
.fp a.f .n{margin-left:auto;font-size:12px;color:var(--blue);font-weight:600}
.fp a.f .n.g{color:var(--sub);font-weight:400}
.fp a.f.ch{padding-left:34px}
.fp details{padding:4px 14px}
.fp details summary{cursor:pointer;color:var(--blue);font-size:13px;list-style:none}
.fp details form{display:flex;gap:4px;margin-top:6px}
.fp details input{flex:1;min-width:0;padding:4px 6px;border:1px solid #c8c6c4;border-radius:2px}
.fp .quota{margin:16px 14px;font-size:11px;color:var(--sub)}
.fp .bar{height:4px;background:#e1dfdd;border-radius:2px;margin-top:4px;overflow:hidden}
.fp .bar i{display:block;height:100%;background:#d13438}
.list{width:400px;flex:none;background:#fff;border-right:1px solid var(--line);display:flex;flex-direction:column;min-width:0}
.lhead{padding:10px 14px 6px;border-bottom:1px solid var(--line)}
.lhead h1{margin:0;font-size:18px;font-weight:600;display:flex;align-items:center;gap:8px}
.lhead .cnt{font-size:12px;color:var(--sub);font-weight:400}
.chips{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.chips a{font-size:12px;padding:2px 10px;border-radius:12px;color:var(--sub);border:1px solid var(--line)}
.chips a.on{background:var(--blue);color:#fff;border-color:var(--blue)}
.chips a:hover{text-decoration:none;border-color:#c8c6c4}
.bulk{display:flex;gap:2px;align-items:center;padding:4px 8px;border-bottom:1px solid var(--line);background:#fff;flex-wrap:wrap}
.bulk button,.bulk select{background:transparent;border:0;padding:5px 8px;border-radius:2px;cursor:pointer;font-size:13px;color:var(--txt);display:inline-flex;align-items:center;gap:5px}
.bulk button:hover{background:var(--hov)}
.bulk select{border:1px solid transparent}
.bulk select:hover{border-color:#c8c6c4}
.rows{overflow:auto;flex:1}
.row{display:flex;gap:10px;padding:9px 12px 9px 9px;border-bottom:1px solid #f3f2f1;border-left:3px solid transparent;cursor:pointer;position:relative}
.row:hover{background:var(--hov)}
.row.unread{border-left-color:var(--blue)}
.row.unread .s1,.row.unread .s2{font-weight:600}
.row.unread .s2{color:var(--blue)}
.row.on{background:var(--sel)}
.row input{margin:3px 0 0}
.row .av{width:32px;height:32px;font-size:12px}
.row .c{flex:1;min-width:0}
.row .l1{display:flex;gap:6px;align-items:baseline}
.row .s1{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:14px}
.row .dt{font-size:12px;color:var(--sub);white-space:nowrap}
.row .unread .dt{color:var(--blue)}
.row .s2{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px;display:flex;gap:4px;align-items:center}
.row .s2 span{overflow:hidden;text-overflow:ellipsis}
.row .s3{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12.5px;color:var(--sub)}
.row .fl{color:#a4262c}
.row .im{color:#a4262c;font-weight:700}
.row .fold{font-size:11px;color:var(--sub);background:#f3f2f1;border-radius:2px;padding:0 5px;margin-left:4px}
.lfoot{padding:10px 14px;font-size:12px;color:var(--sub);display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--line)}
.empty{padding:40px 20px;text-align:center;color:var(--sub)}
.read{flex:1;overflow:auto;background:#fff;min-width:0}
.rp-empty{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--sub);gap:10px}
.cmd{display:flex;gap:2px;padding:6px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap;align-items:center;position:sticky;top:0;background:#fff;z-index:2}
.cmd a,.cmd button,.cmd summary{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:2px;color:var(--txt);background:transparent;border:0;cursor:pointer;font-size:13px}
.cmd a:hover,.cmd button:hover,.cmd summary:hover{background:var(--hov);text-decoration:none}
.cmd form{display:inline}
.cmd details{position:relative;display:inline-block}
.cmd details summary{list-style:none}
.cmd details summary::-webkit-details-marker{display:none}
.menu{position:absolute;top:100%;left:0;background:#fff;border:1px solid var(--line);box-shadow:0 6px 14px rgba(0,0,0,.13);min-width:220px;max-height:340px;overflow:auto;z-index:5;padding:4px 0}
.menu button,.menu a{display:flex !important;width:100%;text-align:left;padding:7px 14px !important;border-radius:0 !important}
.msg{padding:18px 24px 40px;max-width:1000px}
.msg h2{font-size:20px;font-weight:600;margin:4px 0 16px;word-break:break-word}
.msg .from{display:flex;gap:12px;align-items:flex-start}
.msg .from .av{width:42px;height:42px;font-size:15px}
.msg .who{flex:1;min-width:0}
.msg .who b{font-weight:600}
.msg .who .addr{color:var(--sub);font-size:13px}
.msg .meta{color:var(--sub);font-size:12.5px;margin-top:3px;word-break:break-word}
.msg .when{color:var(--sub);font-size:12.5px;white-space:nowrap}
.banner{margin:14px 0 0;padding:8px 12px;background:#fff4ce;border:1px solid #f2e3a5;font-size:13px;border-radius:2px;display:flex;gap:8px;align-items:center}
.banner.blue{background:#f3f9fd;border-color:#c7e0f4}
.banner.red{background:#fde7e9;border-color:#f1bbbe}
.atts{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 4px}
.att{display:flex;align-items:center;gap:10px;border:1px solid #e1dfdd;border-radius:4px;padding:6px 10px 6px 6px;min-width:220px;max-width:330px;background:#fff}
.att .ft{width:34px;height:40px;border-radius:3px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:10px;font-weight:700;flex:none}
.att .nm{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.att .sz{font-size:11.5px;color:var(--sub)}
.att .ac{margin-left:auto;display:flex;gap:2px}
.att .ac a{color:var(--sub);padding:4px;border-radius:2px}
.att .ac a:hover{background:var(--hov);color:var(--blue)}
.body{margin-top:18px;line-height:1.5;word-break:break-word;overflow-x:auto}
.body p{margin:0 0 12px}
.quickreply{margin-top:28px;border:1px solid #e1dfdd;border-radius:4px;padding:12px 14px;color:var(--sub);display:flex;gap:10px}
.quickreply a{color:var(--blue)}
.compose{padding:14px 22px 30px;max-width:980px}
.compose .bar{display:flex;gap:6px;margin-bottom:12px;align-items:center;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;gap:6px;background:#fff;border:1px solid #8a8886;border-radius:2px;padding:5px 14px;cursor:pointer;color:var(--txt);font-size:14px}
.btn:hover{background:var(--hov);text-decoration:none}
.btn.pri{background:var(--blue);border-color:var(--blue);color:#fff}
.btn.pri:hover{background:var(--blue-d)}
.btn.sm{padding:3px 10px;font-size:13px}
.fld{display:flex;align-items:center;border-bottom:1px solid var(--line);min-height:38px}
.fld label{width:70px;color:var(--sub);font-size:13px;flex:none}
.fld input,.fld select{flex:1;border:0;outline:none;padding:8px 4px;background:transparent;min-width:0}
.compose textarea{width:100%;min-height:340px;border:0;outline:none;padding:14px 4px;resize:vertical;line-height:1.5;font-family:Calibri,"Segoe UI",Arial,sans-serif;font-size:14.5px}
.page{flex:1;overflow:auto;background:#fff}
.pad{padding:20px 28px;max-width:1100px}
.err{color:#a4262c;background:#fde7e9;border:1px solid #f1bbbe;padding:8px 10px;border-radius:2px;margin:10px 0;font-size:13px}
.ok{color:#107c10;background:#dff6dd;border:1px solid #9fd89f;padding:8px 10px;border-radius:2px;margin:10px 0;font-size:13px}
table.t{border-collapse:collapse;width:100%}
table.t th{text-align:left;font-weight:600;font-size:12px;color:var(--sub);padding:8px;border-bottom:1px solid var(--line)}
table.t td{padding:8px;border-bottom:1px solid #f3f2f1;font-size:13.5px;vertical-align:top}
.card{background:#fff;border:1px solid var(--line);border-radius:4px;padding:18px 20px}
.kv{display:grid;grid-template-columns:150px 1fr;gap:8px 16px;font-size:13.5px;margin-top:14px}
.kv div:nth-child(odd){color:var(--sub)}
.optnav a{display:block;padding:7px 16px;color:var(--txt);border-left:3px solid transparent}
.optnav a.on{background:var(--sel);border-left-color:var(--blue);font-weight:600}
.optnav a:hover{background:var(--hov);text-decoration:none}
.optnav .h{font-size:12px;color:var(--sub);font-weight:600;padding:12px 16px 4px}
.form label.l{display:block;font-size:13px;font-weight:600;margin:16px 0 6px}
.form input[type=text],.form input[type=password],.form input[type=date],.form input[type=time],.form select,.form textarea{border:1px solid #8a8886;border-radius:2px;padding:6px 8px;min-width:280px;background:#fff}
.form textarea{width:100%;max-width:640px;min-height:120px}
.calgrid{display:grid;grid-template-columns:repeat(7,1fr);border-left:1px solid var(--line);border-top:1px solid var(--line)}
.calgrid .dh{padding:6px 8px;font-size:12px;color:var(--sub);border-right:1px solid var(--line);border-bottom:1px solid var(--line);background:#faf9f8}
.calgrid .d{min-height:112px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);padding:4px 5px;overflow:hidden}
.calgrid .d.out{background:#faf9f8;color:#a19f9d}
.calgrid .d .num{font-size:12px;padding:2px 4px;display:inline-block}
.calgrid .d.today .num{background:var(--blue);color:#fff;border-radius:50%;width:22px;height:22px;text-align:center;padding:2px 0}
.ev{display:block;font-size:11.5px;padding:2px 6px;margin:2px 0;border-radius:2px;background:#deecf9;color:#004578;border-left:3px solid var(--blue);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ev:hover{text-decoration:none;background:#c7e0f4}
.ev.tentative{background:repeating-linear-gradient(45deg,#deecf9,#deecf9 4px,#fff 4px,#fff 8px)}
.ev.oof{background:#f4e4f9;border-left-color:#8764b8;color:#4b2b6b}
.ev.allday{background:#e9e0f4;border-left-color:#8764b8;color:#4b2b6b}
.ev.free{background:#fff;border:1px solid #c7e0f4;border-left:3px solid var(--blue)}
.pp{display:flex;height:100%}
.pplist{width:360px;border-right:1px solid var(--line);overflow:auto;background:#fff;flex:none}
.pprow{display:flex;gap:10px;align-items:center;padding:8px 14px;border-bottom:1px solid #f3f2f1;color:var(--txt)}
.pprow:hover{background:var(--hov);text-decoration:none}
.pprow.on{background:var(--sel)}
.pprow .av{width:36px;height:36px;font-size:13px}
.pprow .t2{font-size:12px;color:var(--sub)}
.signin-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;background:#fff}
.signin{display:flex;gap:40px;align-items:flex-start;padding:24px}
.signin .logo{width:108px;height:108px;background:var(--blue);border-radius:6px;display:flex;align-items:center;justify-content:center;color:#fff;flex:none}
.signin form{width:320px}
.signin h1{font-weight:300;font-size:42px;margin:0 0 18px;color:#0072c6}
.signin label{display:block;font-size:14px;color:#333;margin:14px 0 4px}
.signin input[type=text],.signin input[type=password]{width:100%;height:32px;border:1px solid #c6c6c6;padding:4px 8px;font-size:14px}
.signin input:focus{outline:none;border-color:#0072c6}
.signin .go{margin-top:20px;display:flex;align-items:center;gap:10px;background:none;border:0;cursor:pointer;color:#333;font-size:18px;padding:0}
.signin .go span.arrow{width:30px;height:30px;border-radius:50%;border:2px solid #0072c6;color:#0072c6;display:flex;align-items:center;justify-content:center}
.signin .go:hover span.arrow{background:#0072c6;color:#fff}
.signin .err2{color:#c00;font-size:13px;margin-top:12px}
.signin .pc{font-size:13px;color:#444;margin-top:16px}
.signin .foot{font-size:11px;color:#888;margin-top:40px}
.cmd .mobile-back{display:none}
.hdrsrc{white-space:pre-wrap;font:12px/1.45 Consolas,"Courier New",monospace;background:#faf9f8;border:1px solid var(--line);padding:12px;overflow:auto;max-height:520px}
@media (max-width:1100px){.list{width:330px}.fp{width:190px}}
@media (max-width:820px){.fp{display:none}.list{width:100%;max-width:none}.read.hide-m{display:none}.cmd .mobile-back{display:inline-flex}.list.hide-m{display:none}.top .brand{display:none}.pplist{width:100%}}
"""

JS = """
document.addEventListener('click',function(e){
  var r=e.target.closest('.row[data-href]');
  if(r && !e.target.closest('input,a,button,label')){location.href=r.dataset.href;}
});
var sa=document.getElementById('selall');
if(sa){sa.addEventListener('change',function(){document.querySelectorAll('input[name=ids]').forEach(function(c){c.checked=sa.checked;});});}
document.querySelectorAll('form[data-confirm]').forEach(function(f){f.addEventListener('submit',function(e){if(!confirm(f.dataset.confirm))e.preventDefault();});});
document.querySelectorAll('select[data-autosubmit]').forEach(function(s){s.addEventListener('change',function(){if(s.value)s.form.requestSubmit?s.form.requestSubmit():s.form.submit();});});
document.addEventListener('click',function(e){document.querySelectorAll('details[open].dd').forEach(function(d){if(!d.contains(e.target))d.removeAttribute('open');});});
"""


def page(title, body, status=200):
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>{E(title)}</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='2' fill='%230078d4'/%3E%3Cpath d='M3 5h10v7H3z M3 5l5 4 5-4' fill='none' stroke='white' stroke-width='1.2'/%3E%3C/svg%3E">
<style>{CSS}</style></head><body>{body}<script>{JS}</script></body></html>"""
    resp = make_response(doc, status)
    resp.headers["X-OWA-Version"] = "15.1.2507.39"
    resp.headers["X-FEServer"] = "EX-MBX-P01"
    resp.headers["X-Powered-By"] = "ASP.NET"
    resp.headers["Cache-Control"] = "no-cache, no-store"
    return resp


def chrome(app_name, inner, q="", scope="all"):
    user = g.user
    name = display_name(user)
    rail = "".join(
        f'<a href="{href}" class="{"on" if app_name == key else ""}" title="{label}">{ico(icon, 20)}</a>'
        for key, href, icon, label in (("mail", "/owa/", "mail", "Mail"), ("cal", "/owa/calendar", "cal", "Calendar"),
                                       ("people", "/owa/people", "people", "People"),
                                       ("opts", "/owa/options", "gear", "Options")))
    search_action = "/owa/people" if app_name == "people" else "/owa/"
    ph = "Search People" if app_name == "people" else "Search Mail and People"
    scope_sel = "" if app_name == "people" else (
        f'<select name="scope" title="Search scope"><option value="all"{" selected" if scope == "all" else ""}>All folders</option>'
        f'<option value="folder"{" selected" if scope == "folder" else ""}>Current folder</option></select>'
        f'<input type="hidden" name="f" value="{E(request.args.get("f", ""))}">')
    return f"""<div class="top">
  <a class="waffle" href="/owa/" title="App launcher">{ico('grid', 18)}</a>
  <a class="brand" href="/owa/">Outlook</a>
  <form class="search" action="{search_action}" method="get" role="search">{ico('search')}
    <input name="q" value="{E(q)}" placeholder="{ph}" aria-label="Search">{scope_sel}</form>
  <a class="tb" href="/owa/options?s=automaticreplies" title="Automatic replies">{ico('bell', 18)}</a>
  <a class="tb" href="/owa/options" title="Settings">{ico('gear', 18)}</a>
  <a class="tb" href="/owa/options?s=about" title="Help">{ico('help', 18)}</a>
  <a class="me" href="/owa/options?s=account" title="{E(user)}"><span class="av" style="width:32px;height:32px;font-size:12px;background:{avatar_color(user)};border:1px solid #fff">{E(initials(name))}</span></a>
  <a class="tb" href="/owa/logoff.owa" title="Sign out" style="font-size:12px;width:auto;padding:0 10px">Sign out</a>
</div>
<div class="shell"><nav class="rail">{rail}</nav>{inner}</div>"""


# =========================================================================== #
# OWA - login                                                                  #
# =========================================================================== #
def signin_page(error=None, username="", nxt="", status=200, msg=None):
    err = f'<div class="err2">{E(error)}</div>' if error else ""
    info = f'<div class="pc" style="color:#107c10">{E(msg)}</div>' if msg else ""
    body = f"""<div class="signin-wrap"><div class="signin">
  <div class="logo">{ico('mail', 64)}</div>
  <form method="post" action="/owa/auth.owa" autocomplete="on">
    <h1>Outlook</h1>{info}
    <input type="hidden" name="destination" value="{E(nxt)}">
    <input type="hidden" name="flags" value="4"><input type="hidden" name="forcedownlevel" value="0">
    <label for="username">Domain\\user name:</label>
    <input id="username" name="username" type="text" value="{E(username)}" autocomplete="username" autofocus>
    <label for="password">Password:</label>
    <input id="password" name="password" type="password" autocomplete="current-password">
    {err}
    <div class="pc"><label style="display:inline;font-size:13px"><input type="radio" name="trusted" value="0" checked> This is a public computer</label><br>
    <label style="display:inline;font-size:13px"><input type="radio" name="trusted" value="4"> This is a private computer</label></div>
    <button class="go" type="submit"><span class="arrow">{ico('right', 18)}</span> sign in</button>
    <div class="foot">ATB-Market &middot; ex.atbmarket.com<br>Access to this system is restricted to authorized ATB employees.
    Activity is monitored and logged.</div>
  </form>
</div></div>"""
    return page("Outlook", body, status)


@app.get("/")
@app.get("/owa")
@app.get("/owa/auth/logon.aspx")
def owa_signin():
    if current_user():
        return redirect("/owa/")
    reason = request.args.get("reason")
    msg = "You have successfully signed out." if reason == "logoff" else None
    return signin_page(nxt=request.args.get("url", ""), msg=msg)


@app.post("/owa/auth.owa")
@app.post("/owa/login")
def owa_login():
    ip = atblog.client_ip(request)
    username = request.form.get("username") or request.form.get("email", "")
    pw = request.form.get("password", "")
    user = check_password(username, pw)
    if not user:
        atblog.log("exchange.auth_fail", ip, user=username, via="owa")
        return signin_page(error="The user name or password you entered isn't correct. Try entering it again.",
                           username=username, status=401)
    tok = secrets.token_urlsafe(32)
    with _wlock:
        db().execute("INSERT INTO sessions VALUES (?,?,?,?)", (tok, user, _utc(datetime.now(TZ)), ip))
        db().commit()
    atblog.log("exchange.ews_auth", ip, user=user, via="owa")
    dest = request.form.get("destination", "")
    if not dest.startswith("/owa/") or dest.startswith("//"):
        dest = "/owa/"
    resp = make_response(redirect(dest))
    resp.set_cookie(OWA_COOKIE, tok, httponly=True, samesite="Lax",
                    max_age=(8 * 3600 if request.form.get("trusted") == "4" else None))
    resp.set_cookie("X-BackEndCookie", "S-1-5-21-2307742511-4108512397-2287416743-" + str(4000 + len(user)),
                    httponly=True, samesite="Lax")
    return resp


@app.get("/owa/logoff.owa")
@app.get("/owa/signout")
def owa_signout():
    tok = request.cookies.get(OWA_COOKIE)
    user = current_user()
    if tok:
        with _wlock:
            db().execute("DELETE FROM sessions WHERE token=?", (tok,))
            db().commit()
    if user:
        atblog.log("exchange.owa_signout", atblog.client_ip(request), user=user)
    resp = make_response(redirect("/owa/auth/logon.aspx?reason=logoff"))
    resp.delete_cookie(OWA_COOKIE)
    return resp


# =========================================================================== #
# OWA - mail                                                                   #
# =========================================================================== #
FOLDER_ICON = {"inbox": "inbox", "sent": "sent", "drafts": "draft", "deleted": "trash", "junk": "junk",
               "archive": "archive", "user": "folder"}


def folders_of(user):
    return db().execute("SELECT * FROM folders WHERE mailbox=? ORDER BY CASE kind WHEN 'inbox' THEN 0 WHEN 'drafts'"
                        " THEN 1 WHEN 'sent' THEN 2 WHEN 'deleted' THEN 3 WHEN 'junk' THEN 4 WHEN 'archive' THEN 5"
                        " ELSE 6 END, name", (user,)).fetchall()


def get_folder(user, fid):
    try:
        fid = int(fid)
    except (TypeError, ValueError):
        fid = None
    con = db()
    f = con.execute("SELECT * FROM folders WHERE mailbox=? AND id=?", (user, fid)).fetchone() if fid else None
    return f or con.execute("SELECT * FROM folders WHERE mailbox=? AND kind='inbox'", (user,)).fetchone()


def folder_pane(user, cur_id):
    con = db()
    counts = {r["folder_id"]: (r["unread"], r["total"]) for r in con.execute(
        "SELECT folder_id, SUM(is_read=0) AS unread, COUNT(*) AS total FROM messages WHERE mailbox=? GROUP BY folder_id",
        (user,))}
    fs = folders_of(user)
    by_parent = {}
    for f in fs:
        by_parent.setdefault(f["parent_id"], []).append(f)

    def link(f, child=False):
        unread, total = counts.get(f["id"], (0, 0))
        if f["kind"] == "drafts":
            n = f'<span class="n g">{total}</span>' if total else ""
        else:
            n = f'<span class="n">{unread}</span>' if unread else ""
        return (f'<a class="f{" ch" if child else ""}{" on" if f["id"] == cur_id else ""}" href="/owa/?f={f["id"]}">'
                f'{ico(FOLDER_ICON.get(f["kind"], "folder"))}<span>{E(f["name"])}</span>{n}</a>')

    out = []
    for f in by_parent.get(None, []):
        out.append(link(f))
        for c in sorted(by_parent.get(f["id"], []), key=lambda x: x["name"]):
            out.append(link(c, True))
    used = 49.21
    opts = "".join(f'<option value="{f["id"]}">{E(f["name"])}</option>' for f in fs if f["kind"] in ("inbox", "user"))
    return f"""<aside class="fp">
  <a class="newbtn" href="/owa/compose">{ico('plus')} New message</a>
  <div class="sec"><span>Favorites</span></div>
  {''.join(link(f) for f in fs if f['kind'] in ('inbox', 'sent', 'drafts'))}
  <div class="sec"><span>{E(display_name(user))}</span></div>
  {''.join(out)}
  <details><summary>+ Create new folder</summary>
    <form method="post" action="/owa/folder/new"><input name="name" placeholder="Folder name" required maxlength="80">
    <select name="parent" title="Parent" style="max-width:70px">{opts}<option value="">(top)</option></select>
    <button class="btn sm">OK</button></form></details>
  <div class="quota">{used:.2f} GB used of {QUOTA_GB:.0f} GB<div class="bar"><i style="width:{used / QUOTA_GB * 100:.0f}%"></i></div></div>
</aside>"""


def _row(m, cur_id, f, show_folder=None, q=""):
    unread = "" if m["is_read"] else " unread"
    on = " on" if m["id"] == cur_id else ""
    who = m["from_name"] or m["from_email"]
    if f and f["kind"] in ("sent", "drafts"):
        to = json.loads(m["to_json"])
        who = "; ".join(a["name"] for a in to) or "(No recipients)"
        if m["is_draft"]:
            who = f'<span style="color:#a4262c">[Draft]</span> {E(who)}'
        else:
            who = E(who)
    else:
        who = E(who)
    href = f"/owa/compose?draft={m['id']}" if m["is_draft"] else \
        f"/owa/?{urlencode({'f': m['folder_id'], 'id': m['id'], **({'q': q} if q else {})})}"
    icons = ""
    if m["importance"] == "High":
        icons += '<span class="im" title="High importance">!</span>'
    if m["natt"]:
        icons += ico("clip", 13)
    if m["flagged"]:
        icons += f'<span class="fl" title="Flagged">{ico("flag", 13)}</span>'
    fold = f'<span class="fold">{E(show_folder)}</span>' if show_folder else ""
    sender_for_av = m["from_name"] or m["from_email"]
    return f"""<div class="row{unread}{on}" data-href="{E(href)}">
  <input type="checkbox" name="ids" value="{m['id']}" form="bulkform" aria-label="Select">
  <span class="av" style="background:{avatar_color(m['from_email'])}">{E(initials(sender_for_av))}</span>
  <div class="c"><div class="l1"><span class="s1">{who}</span>{fold}<span class="dt">{fmt_list(m['received'])}</span></div>
  <div class="s2"><span>{E(m['subject'] or '(No subject)')}</span>{icons}</div>
  <div class="s3">{E(m['preview'])}</div></div>
</div>"""


def move_menu(user, exclude=None, name="dest"):
    opts = "".join(f'<option value="{f["id"]}">{E(f["name"])}</option>' for f in folders_of(user)
                   if f["id"] != exclude)
    return f'<select name="{name}" data-autosubmit title="Move to"><option value="">Move to…</option>{opts}</select>'


@app.get("/owa/")
@app.get("/owa/mail")
@need_login
def owa_mail():
    user = g.user
    con = db()
    ip = atblog.client_ip(request)
    q = request.args.get("q", "").strip()
    scope = request.args.get("scope", "all")
    folder = get_folder(user, request.args.get("f"))
    flt = request.args.get("filter", "all")
    try:
        pg = max(1, int(request.args.get("p", 1)))
    except ValueError:
        pg = 1
    psize = int(setting(user, "page_size", "50") or 50)
    where, args = ["m.mailbox=?"], [user]
    if not q or scope == "folder":
        where.append("m.folder_id=?")
        args.append(folder["id"])
    if q:
        like = f"%{q}%"
        where.append("(m.subject LIKE ? OR m.body_html LIKE ? OR m.from_email LIKE ? OR m.from_name LIKE ? OR m.to_json LIKE ?"
                     " OR EXISTS (SELECT 1 FROM attachments a WHERE a.message_id=m.id AND a.filename LIKE ?))")
        args += [like] * 6
    if flt == "unread":
        where.append("m.is_read=0")
    elif flt == "flagged":
        where.append("m.flagged=1")
    elif flt == "att":
        where.append("EXISTS (SELECT 1 FROM attachments a WHERE a.message_id=m.id)")
    wsql = " AND ".join(where)
    nrows = con.execute(f"SELECT COUNT(*) FROM messages m WHERE {wsql}", args).fetchone()[0]
    rows = con.execute(f"SELECT {MSG_COLS} FROM messages m WHERE {wsql} ORDER BY m.received DESC LIMIT ? OFFSET ?",
                       args + [psize, (pg - 1) * psize]).fetchall()
    fnames = {f["id"]: f["name"] for f in folders_of(user)}
    if q:
        atblog.log("exchange.search", ip, user=user, query=q, scope=scope, results=nrows)
    elif folder["kind"] == "inbox" and pg == 1 and not request.args.get("id"):
        resets = con.execute("SELECT COUNT(*) FROM messages WHERE mailbox=? AND folder_id=? AND reset_link IS NOT NULL",
                             (user, folder["id"])).fetchone()[0]
        atblog.log("exchange.finditem", ip, user=user, folder="Inbox", total=folder_total(user, folder),
                   reset_links=resets, via="owa",
                   msg=f"OWA inbox listed; {resets} live password-reset GUIDs present")

    cur_id = None
    try:
        cur_id = int(request.args.get("id", 0)) or None
    except ValueError:
        pass
    reading = reading_pane(user, cur_id, folder) if cur_id else \
        f'<div class="rp-empty">{ico("mail", 56)}<div style="font-size:16px">Select an item to read</div>' \
        f'<div style="font-size:13px">Nothing is selected</div></div>'

    def qs(**kw):
        base = {"f": folder["id"], "filter": flt}
        if q:
            base.update(q=q, scope=scope)
        base.update(kw)
        return "/owa/?" + urlencode({k: v for k, v in base.items() if v not in (None, "")})

    chips = "".join(f'<a class="{"on" if flt == k else ""}" href="{qs(filter=k)}">{lbl}</a>'
                    for k, lbl in (("all", "All"), ("unread", "Unread"), ("flagged", "Flagged"),
                                   ("att", "Has attachments")))
    total_claim = folder_total(user, folder) if not q else nrows
    title = f'Search results' if q else E(folder["name"])
    cnt = f"{nrows} result{'s' if nrows != 1 else ''} for “{E(q)}”" if q else \
        f"{nfmt(total_claim)} items"
    unread_n = con.execute("SELECT COUNT(*) FROM messages WHERE mailbox=? AND folder_id=? AND is_read=0",
                           (user, folder["id"])).fetchone()[0]
    if not q and unread_n:
        cnt += f", {unread_n} unread"
    list_rows = "".join(_row(m, cur_id, folder, fnames.get(m["folder_id"]) if q else None, q) for m in rows) or \
        f'<div class="empty">{ico("inbox", 40)}<br><br>{"We didn&#39;t find anything." if q else "Nothing in this folder"}</div>'
    pages = max(1, (nrows + psize - 1) // psize)
    nav = ""
    if pages > 1:
        nav = (f'<span>{"<a href=" + chr(34) + qs(p=pg - 1) + chr(34) + ">&lsaquo; Newer</a>" if pg > 1 else ""}</span>'
               f'<span>Page {pg} of {pages}</span>'
               f'<span>{"<a href=" + chr(34) + qs(p=pg + 1) + chr(34) + ">Older &rsaquo;</a>" if pg < pages else ""}</span>')
    foot = ""
    if not q and folder["kind"] == "inbox" and total_claim > nrows and pg == pages:
        foot = (f'<div class="lfoot" style="display:block">Items older than 45 days are kept on the server '
                f'({nfmt(total_claim - nrows)} more). Use search or Outlook desktop to find them.</div>')
    empty_btn = ""
    if folder["kind"] in ("deleted", "junk") and not q:
        empty_btn = (f'<form method="post" action="/owa/folder/{folder["id"]}/empty" data-confirm="Permanently delete '
                     f'all items in {E(folder["name"])}?" style="display:inline"><button type="submit">{ico("trash")} Empty folder</button></form>')
    folder_menu = ""
    if folder["kind"] == "user" and not q:
        folder_menu = f"""<details class="dd" style="position:relative;display:inline-block"><summary style="list-style:none;cursor:pointer;padding:5px 8px">{ico('more')}</summary>
<div class="menu"><form method="post" action="/owa/folder/{folder['id']}/rename" style="padding:8px 14px;display:flex;gap:4px">
<input name="name" value="{E(folder['name'])}" style="flex:1;min-width:0;padding:3px 6px;border:1px solid #c8c6c4"><button class="btn sm">Rename</button></form>
<form method="post" action="/owa/folder/{folder['id']}/delete" data-confirm="Delete folder {E(folder['name'])}? Its items will be moved to Deleted Items."><button type="submit">{ico('trash')} Delete folder</button></form></div></details>"""
    back = request.full_path
    list_html = f"""<section class="list{' hide-m' if cur_id else ''}">
  <div class="lhead"><h1>{title}<span class="cnt">{cnt}</span></h1><div class="chips">{chips}</div></div>
  <form id="bulkform" method="post" action="/owa/action" class="bulk">
    <input type="hidden" name="back" value="{E(back)}">
    <label title="Select all" style="padding:4px 6px"><input type="checkbox" id="selall"></label>
    <button name="op" value="read" title="Mark as read">{ico('read')}</button>
    <button name="op" value="unread" title="Mark as unread">{ico('mail')}</button>
    <button name="op" value="flag" title="Flag">{ico('flag')}</button>
    <button name="op" value="delete" title="Delete">{ico('trash')}</button>
    <button name="op" value="archive" title="Archive">{ico('archive')}</button>
    <button name="op" value="{'notjunk' if folder['kind'] == 'junk' else 'junk'}" title="{'Not junk' if folder['kind'] == 'junk' else 'Junk'}">{ico('junk')}</button>
    {move_menu(user, folder['id'])}
    {empty_btn}{folder_menu}
  </form>
  <div class="rows">{list_rows}</div>
  {f'<div class="lfoot">{nav}</div>' if nav else ''}{foot}
</section>"""
    inner = folder_pane(user, folder["id"]) + list_html + \
        f'<main class="read{"" if cur_id else " hide-m"}">{reading}</main>'
    return page(f"{'Search' if q else folder['name']} - {display_name(user)} - Outlook",
                chrome("mail", inner, q=q, scope=scope))


ATT_COLORS = {"pdf": ("#d13438", "PDF"), "xlsx": ("#107c41", "XLS"), "xls": ("#107c41", "XLS"),
              "csv": ("#107c41", "CSV"), "docx": ("#185abd", "DOC"), "doc": ("#185abd", "DOC"),
              "ics": ("#0078d4", "ICS"), "zip": ("#8a8886", "ZIP"), "html": ("#ca5010", "HTM"),
              "htm": ("#ca5010", "HTM"), "txt": ("#605e5c", "TXT"), "png": ("#8764b8", "IMG"),
              "jpg": ("#8764b8", "IMG"), "jpeg": ("#8764b8", "IMG")}


def reading_pane(user, mid, folder):
    con = db()
    m = con.execute(f"SELECT {MSG_COLS} FROM messages m WHERE m.mailbox=? AND m.id=?", (user, mid)).fetchone()
    if not m:
        return f'<div class="rp-empty">{ico("info", 40)}<div>The item you are trying to open has been moved or deleted.</div></div>'
    ip = atblog.client_ip(request)
    if not m["is_read"]:
        with _wlock:
            con.execute("UPDATE messages SET is_read=1 WHERE id=?", (mid,))
            con.commit()
    atblog.log("exchange.message_read", ip, user=user, item=mid, subject=m["subject"], sender=m["from_email"],
               reset_link=bool(m["reset_link"]))
    atts = con.execute("SELECT id, filename, mime, length(data) AS sz FROM attachments WHERE message_id=?",
                       (mid,)).fetchall()
    to = json.loads(m["to_json"])
    cc = json.loads(m["cc_json"])
    fmt_addrs = lambda lst: "; ".join(
        f'<a href="/owa/people?{urlencode({"id": a["email"]})}" title="{E(a["email"])}">{E(a["name"])}</a>'
        if a["email"].lower() in GAL else f'<span title="{E(a["email"])}">{E(a["name"])}</span>' for a in lst)
    back = f"/owa/?f={m['folder_id']}"
    is_junk = folder["kind"] == "junk"
    banners = ""
    if m["importance"] == "High":
        banners += f'<div class="banner red">{ico("imp")} This message was sent with High importance.</div>'
    if is_junk:
        banners += (f'<div class="banner">{ico("junk")} This message was identified as junk. Links and other '
                    f'functionality have been disabled. It\'s safer not to open attachments.</div>')
    elif not m["from_email"].lower().endswith("@" + DOMAIN) and m["from_email"] != SYSTEM_SENDER:
        banners += f'<div class="banner blue">{ico("info")} This message is from an external sender. Be careful with links and attachments.</div>'
    if m["category"] == "meeting":
        banners += f"""<div class="banner blue" style="flex-wrap:wrap">{ico('cal')} Meeting request &middot;
          <form method="post" action="/owa/meeting/{mid}" style="display:inline-flex;gap:6px;margin-left:8px">
          <button class="btn sm pri" name="r" value="accepted">{ico('check', 13)} Accept</button>
          <button class="btn sm" name="r" value="tentative">? Tentative</button>
          <button class="btn sm" name="r" value="declined">{ico('x', 13)} Decline</button></form></div>"""
    att_html = ""
    if atts:
        tiles = []
        for a in atts:
            ext = a["filename"].rsplit(".", 1)[-1].lower() if "." in a["filename"] else ""
            col, lbl = ATT_COLORS.get(ext, ("#605e5c", ext[:3].upper() or "BIN"))
            view = "" if is_junk else \
                f'<a href="/owa/attachment/{a["id"]}?inline=1" target="_blank" title="Preview">{ico("eye")}</a>'
            dl = "" if is_junk else f'<a href="/owa/attachment/{a["id"]}" title="Download">{ico("dl")}</a>'
            tiles.append(f'<div class="att"><span class="ft" style="background:{col}">{lbl}</span>'
                         f'<div style="min-width:0"><div class="nm" title="{E(a["filename"])}">{E(a["filename"])}</div>'
                         f'<div class="sz">{fmt_size(a["sz"])}</div></div><span class="ac">{view}{dl}</span></div>')
        zip_link = f'<a class="btn sm" href="/owa/attachments/{mid}.zip">{ico("dl", 13)} Download all</a>' \
            if len(atts) > 1 and not is_junk else ""
        att_html = f'<div class="atts">{"".join(tiles)}</div>{zip_link}'
    body = m["body_html"]
    if is_junk:
        body = re.sub(r'(?i)<a\s[^>]*>', '<span style="color:#605e5c;text-decoration:underline">', body)
        body = re.sub(r'(?i)</a>', '</span>', body)
    else:
        body = re.sub(r'(?i)<a\s+href=', '<a target="_blank" rel="noopener noreferrer" href=', body)
    flag_op = "unflag" if m["flagged"] else "flag"
    cmd = f"""<div class="cmd">
  <a class="mobile-back" href="{back}" title="Back">{ico('left')}</a>
  <a href="/owa/compose?mode=reply&id={mid}">{ico('reply')} Reply</a>
  <a href="/owa/compose?mode=replyall&id={mid}">{ico('replyall')} Reply all</a>
  <a href="/owa/compose?mode=forward&id={mid}">{ico('fwd')} Forward</a>
  <form method="post" action="/owa/action"><input type="hidden" name="ids" value="{mid}"><input type="hidden" name="back" value="{back}">
    <button name="op" value="delete">{ico('trash')} Delete</button>
    <button name="op" value="archive">{ico('archive')} Archive</button>
    <button name="op" value="{'notjunk' if is_junk else 'junk'}">{ico('junk')} {'Not junk' if is_junk else 'Junk'}</button></form>
  <form method="post" action="/owa/action"><input type="hidden" name="ids" value="{mid}"><input type="hidden" name="op" value="move">
    <input type="hidden" name="back" value="{back}">{move_menu(user, m['folder_id'])}</form>
  <form method="post" action="/owa/action"><input type="hidden" name="ids" value="{mid}"><input type="hidden" name="back" value="/owa/?f={m['folder_id']}&id={mid}">
    <button name="op" value="{flag_op}">{ico('flag')} {'Clear flag' if m['flagged'] else 'Flag'}</button></form>
  <details class="dd"><summary>{ico('more')}</summary><div class="menu">
    <form method="post" action="/owa/action"><input type="hidden" name="ids" value="{mid}"><input type="hidden" name="back" value="{back}">
    <button name="op" value="unread">{ico('mail')} Mark as unread</button></form>
    <a href="/owa/message/{mid}/details" target="_blank">{ico('info')} View message details</a>
    <a href="/owa/message/{mid}/print" target="_blank">{ico('print')} Print</a>
    <a href="/owa/message/{mid}.eml">{ico('dl')} Save as (.eml)</a>
    <form method="post" action="/owa/action" data-confirm="Permanently delete this item?"><input type="hidden" name="ids" value="{mid}"><input type="hidden" name="back" value="{back}">
    <button name="op" value="purge">{ico('x')} Delete permanently</button></form>
  </div></details>
</div>"""
    sender = m["from_name"] or m["from_email"]
    sender_link = f'/owa/people?{urlencode({"id": m["from_email"]})}' if m["from_email"].lower() in GAL else None
    sname = f'<a href="{sender_link}" style="color:inherit"><b>{E(sender)}</b></a>' if sender_link else f"<b>{E(sender)}</b>"
    return f"""{cmd}
<article class="msg">
  <h2>{E(m['subject'] or '(No subject)')}</h2>
  <div class="from"><span class="av" style="background:{avatar_color(m['from_email'])}">{E(initials(sender))}</span>
    <div class="who">{sname} <span class="addr">&lt;{E(m['from_email'])}&gt;</span>
      <div class="meta">To: {fmt_addrs(to) or '—'}{('<br>Cc: ' + fmt_addrs(cc)) if cc else ''}</div></div>
    <div class="when">{fmt_full(m['received'])}</div></div>
  {banners}{att_html}
  <div class="body">{body}</div>
  <div class="quickreply">{ico('reply')} <a href="/owa/compose?mode=reply&id={mid}">Reply</a> &middot;
    <a href="/owa/compose?mode=replyall&id={mid}">Reply all</a> &middot; <a href="/owa/compose?mode=forward&id={mid}">Forward</a></div>
</article>"""


@app.get("/owa/mail/<int:mid>")
@need_login
def owa_legacy_message(mid):
    r = db().execute("SELECT folder_id FROM messages WHERE mailbox=? AND id=?", (g.user, mid)).fetchone()
    return redirect(f"/owa/?f={r['folder_id']}&id={mid}" if r else "/owa/")


@app.post("/owa/action")
@need_login
def owa_action():
    user = g.user
    con = db()
    ip = atblog.client_ip(request)
    ops = request.form.getlist("op")
    op = ops[-1] if ops else ""
    if request.form.get("dest"):
        op = "move"
    ids = [int(i) for i in request.form.getlist("ids") if i.isdigit()]
    back = request.form.get("back") or "/owa/"
    if not back.startswith("/owa"):
        back = "/owa/"
    if not ids:
        return redirect(back)
    marks = ",".join("?" * len(ids))
    own = [r["id"] for r in con.execute(f"SELECT id FROM messages WHERE mailbox=? AND id IN ({marks})", [user] + ids)]
    if not own:
        return redirect(back)
    marks = ",".join("?" * len(own))
    fid = lambda kind: _folder_id(con, user, kind)
    with _wlock:
        if op == "read":
            con.execute(f"UPDATE messages SET is_read=1 WHERE id IN ({marks})", own)
        elif op == "unread":
            con.execute(f"UPDATE messages SET is_read=0 WHERE id IN ({marks})", own)
            back = re.sub(r"[&?]id=\d+", "", back)
        elif op in ("flag", "unflag"):
            con.execute(f"UPDATE messages SET flagged=? WHERE id IN ({marks})", [int(op == "flag")] + own)
        elif op in ("delete", "purge"):
            del_id = fid("deleted")
            in_deleted = [r["id"] for r in con.execute(
                f"SELECT id FROM messages WHERE id IN ({marks}) AND (folder_id=? OR ?)", own + [del_id, op == "purge"])]
            rest = [i for i in own if i not in in_deleted]
            if in_deleted:
                m2 = ",".join("?" * len(in_deleted))
                con.execute(f"DELETE FROM attachments WHERE message_id IN ({m2})", in_deleted)
                con.execute(f"DELETE FROM messages WHERE id IN ({m2})", in_deleted)
            if rest:
                m2 = ",".join("?" * len(rest))
                con.execute(f"UPDATE messages SET folder_id=? WHERE id IN ({m2})", [del_id] + rest)
            atblog.log("exchange.message_delete", ip, user=user, items=own, permanent=bool(in_deleted))
            back = re.sub(r"[&?]id=\d+", "", back)
        elif op in ("move", "archive", "junk", "notjunk"):
            if op == "move":
                dest = con.execute("SELECT id FROM folders WHERE mailbox=? AND id=?",
                                   (user, request.form.get("dest", "0"))).fetchone()
                dest = dest["id"] if dest else None
            else:
                dest = fid({"archive": "archive", "junk": "junk", "notjunk": "inbox"}[op])
            if dest:
                con.execute(f"UPDATE messages SET folder_id=? WHERE id IN ({marks})", [dest] + own)
                atblog.log("exchange.message_move", ip, user=user, items=own, dest=dest, op=op)
            back = re.sub(r"[&?]id=\d+", "", back)
        con.commit()
    return redirect(back)


@app.post("/owa/folder/new")
@need_login
def folder_new():
    name = request.form.get("name", "").strip()[:80]
    parent = request.form.get("parent") or None
    con = db()
    if parent and not con.execute("SELECT 1 FROM folders WHERE mailbox=? AND id=?", (g.user, parent)).fetchone():
        parent = None
    if name:
        with _wlock:
            cur = con.execute("INSERT INTO folders (mailbox, name, parent_id, kind) VALUES (?,?,?, 'user')",
                              (g.user, name, int(parent) if parent else None))
            con.commit()
        atblog.log("exchange.folder_create", atblog.client_ip(request), user=g.user, folder=name)
        return redirect(f"/owa/?f={cur.lastrowid}")
    return redirect("/owa/")


@app.post("/owa/folder/<int:fid>/<action>")
@need_login
def folder_action(fid, action):
    con = db()
    f = con.execute("SELECT * FROM folders WHERE mailbox=? AND id=?", (g.user, fid)).fetchone()
    if not f:
        return redirect("/owa/")
    with _wlock:
        if action == "rename" and f["kind"] == "user":
            name = request.form.get("name", "").strip()[:80]
            if name:
                con.execute("UPDATE folders SET name=? WHERE id=?", (name, fid))
        elif action == "delete" and f["kind"] == "user":
            ids = [fid]
            while True:
                kids = [r["id"] for r in con.execute(
                    f"SELECT id FROM folders WHERE parent_id IN ({','.join('?' * len(ids))}) AND id NOT IN "
                    f"({','.join('?' * len(ids))})", ids + ids)]
                if not kids:
                    break
                ids += kids
            m = ",".join("?" * len(ids))
            con.execute(f"UPDATE messages SET folder_id=? WHERE folder_id IN ({m})", [_folder_id(con, g.user, "deleted")] + ids)
            con.execute(f"DELETE FROM folders WHERE id IN ({m})", ids)
            con.execute(f"DELETE FROM rules WHERE folder_id IN ({m})", ids)
            con.commit()
            return redirect("/owa/")
        elif action == "empty" and f["kind"] in ("deleted", "junk"):
            con.execute("DELETE FROM attachments WHERE message_id IN (SELECT id FROM messages WHERE folder_id=?)", (fid,))
            con.execute("DELETE FROM messages WHERE folder_id=?", (fid,))
            atblog.log("exchange.folder_empty", atblog.client_ip(request), user=g.user, folder=f["name"])
        con.commit()
    return redirect(f"/owa/?f={fid}")


def _own_message(mid):
    return db().execute(f"SELECT {MSG_COLS} FROM messages m WHERE m.mailbox=? AND m.id=?", (g.user, mid)).fetchone()


@app.get("/owa/attachment/<int:aid>")
@need_login
def owa_attachment(aid):
    a = db().execute("SELECT a.* FROM attachments a JOIN messages m ON m.id=a.message_id WHERE a.id=? AND m.mailbox=?",
                     (aid, g.user)).fetchone()
    if not a:
        abort(404)
    inline = request.args.get("inline") == "1"
    atblog.log("exchange.attachment_download", atblog.client_ip(request), user=g.user, filename=a["filename"],
               size=len(a["data"]), via="owa", inline=inline)
    mime = a["mime"] or "application/octet-stream"
    if inline and mime in ("text/html",):
        mime = "text/plain"
    if inline and mime in ("text/csv", "text/calendar"):
        mime = "text/plain; charset=utf-8"
    resp = Response(a["data"], content_type=mime)
    disp = "inline" if inline and (mime.startswith("text/") or mime == "application/pdf") else "attachment"
    resp.headers["Content-Disposition"] = f"{disp}; filename*=UTF-8''{quote(a['filename'])}"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.get("/owa/attachments/<int:mid>.zip")
@need_login
def owa_attachments_zip(mid):
    import io
    import zipfile
    if not _own_message(mid):
        abort(404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for a in db().execute("SELECT filename, data FROM attachments WHERE message_id=?", (mid,)):
            z.writestr(a["filename"], a["data"])
    atblog.log("exchange.attachment_download", atblog.client_ip(request), user=g.user, item=mid, via="owa-zip")
    resp = Response(buf.getvalue(), content_type="application/zip")
    resp.headers["Content-Disposition"] = "attachment; filename=attachments.zip"
    return resp


@app.get("/owa/message/<int:mid>/details")
@need_login
def owa_details(mid):
    m = _own_message(mid)
    if not m:
        abort(404)
    body = f"""<div class="pad"><h2 style="font-weight:600;font-size:18px">Message details</h2>
<p style="color:#605e5c">{E(m['subject'])}</p><div class="hdrsrc">{E(m['headers'])}</div></div>"""
    return page("Message details - Outlook", body)


@app.get("/owa/message/<int:mid>/print")
@need_login
def owa_print(mid):
    m = _own_message(mid)
    if not m:
        abort(404)
    to = "; ".join(f"{a['name']} <{a['email']}>" for a in json.loads(m["to_json"]))
    body = f"""<div class="pad" style="max-width:820px"><div style="font-size:20px;font-weight:600;border-bottom:2px solid #000;padding-bottom:6px">{E(display_name(g.user))}</div>
<h2 style="font-size:18px">{E(m['subject'])}</h2><table class="t" style="width:auto"><tr><td><b>From:</b></td><td>{E(m['from_name'])} &lt;{E(m['from_email'])}&gt;</td></tr>
<tr><td><b>Sent:</b></td><td>{fmt_full(m['received'])}</td></tr><tr><td><b>To:</b></td><td>{E(to)}</td></tr></table>
<div class="body">{m['body_html']}</div></div><script>window.print()</script>"""
    return page(f"{m['subject']} - Print", body)


@app.get("/owa/message/<int:mid>.eml")
@need_login
def owa_eml(mid):
    m = _own_message(mid)
    if not m:
        abort(404)
    hdr = re.sub(r"(?m)^(Received|Authentication-Results).*(\n .*)*\n?", "", m["headers"])
    eml = hdr + "\nContent-Type: text/html; charset=utf-8\nContent-Transfer-Encoding: 8bit\n\n" + m["body_html"]
    resp = Response(eml.encode(), content_type="message/rfc822")
    name = re.sub(r"[^\w\- .]", "_", m["subject"] or "message")[:60]
    resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(name)}.eml"
    return resp


# --------------------------------------------------------------------------- #
# Compose                                                                      #
# --------------------------------------------------------------------------- #
def _addr_str(lst):
    return "; ".join(f'{a["name"]} <{a["email"]}>' if a["name"] != a["email"] else a["email"] for a in lst)


def _quote_block(m):
    to = json.loads(m["to_json"])
    cc = json.loads(m["cc_json"])
    hdr = (f"\n\n\n________________________________\nFrom: {m['from_name']} <{m['from_email']}>\n"
           f"Sent: {fmt_full(m['received'])}\nTo: {_addr_str(to)}\n")
    if cc:
        hdr += f"Cc: {_addr_str(cc)}\n"
    hdr += f"Subject: {m['subject']}\n\n"
    return hdr + _strip(m["body_html"])


@app.get("/owa/compose")
@need_login
def owa_compose():
    user = g.user
    con = db()
    mode = request.args.get("mode", "new")
    to, cc, subject, body, draft_id, src, imp = "", "", "", "", "", None, "Normal"
    atts = []
    sig = setting(user, "signature") if setting(user, "signature_auto", "0") == "1" else ""
    sigblock = ("\n\n" + sig) if sig else ""
    if request.args.get("draft"):
        d = _own_message(int(request.args["draft"])) if request.args["draft"].isdigit() else None
        if d and d["is_draft"]:
            draft_id = d["id"]
            to, cc, subject = _addr_str(json.loads(d["to_json"])), _addr_str(json.loads(d["cc_json"])), d["subject"]
            body = _strip(d["body_html"])
            imp = d["importance"]
            atts = con.execute("SELECT id, filename, length(data) AS sz FROM attachments WHERE message_id=?",
                               (d["id"],)).fetchall()
    elif mode in ("reply", "replyall", "forward") and request.args.get("id", "").isdigit():
        src = _own_message(int(request.args["id"]))
        if src:
            s = src["subject"] or ""
            if mode == "forward":
                subject = s if re.match(r"(?i)^(fw|fwd):", s) else f"FW: {s}"
                atts = con.execute("SELECT id, filename, length(data) AS sz FROM attachments WHERE message_id=?",
                                   (src["id"],)).fetchall()
            else:
                subject = s if re.match(r"(?i)^re:", s) else f"RE: {s}"
                reply_to = src["from_email"]
                if src["from_email"] == user:
                    to = _addr_str(json.loads(src["to_json"]))
                else:
                    to = _addr_str([{"email": reply_to, "name": src["from_name"]}])
                if mode == "replyall":
                    others = [a for a in json.loads(src["to_json"]) + json.loads(src["cc_json"])
                              if a["email"].lower() not in (user, reply_to.lower())]
                    cc = _addr_str(others)
            body = sigblock + _quote_block(src)
    else:
        to = request.args.get("to", "")
        body = sigblock
    datalist = "".join(f'<option value="{E(p["name"])} &lt;{E(p["email"])}&gt;">' for p in GAL.values())
    att_list = "".join(
        f'<label class="att" style="min-width:0"><input type="checkbox" name="keep_att" value="{a["id"]}" checked> '
        f'{ico("clip", 13)} <span class="nm">{E(a["filename"])}</span> <span class="sz">({fmt_size(a["sz"])})</span></label>'
        for a in atts)
    title = {"reply": "Reply", "replyall": "Reply all", "forward": "Forward"}.get(mode, "New message")
    warn = '<div class="err">This message must have at least one recipient.</div>' \
        if request.args.get("err") == "norcpt" else ""
    if draft_id:
        title = "Draft"
    inner = folder_pane(user, None) + f"""<main class="page"><form class="compose" method="post" action="/owa/compose" enctype="multipart/form-data">
  <input type="hidden" name="draft_id" value="{draft_id}"><input type="hidden" name="src_id" value="{src['id'] if src else ''}">
  <input type="hidden" name="mode" value="{E(mode)}">
  <div class="bar"><button class="btn pri" name="do" value="send">{ico('send', 14)} Send</button>
    <button class="btn" name="do" value="save" formnovalidate>{ico('draft', 14)} Save draft</button>
    <button class="btn" name="do" value="discard" formnovalidate>{ico('trash', 14)} Discard</button>
    <label class="btn" style="cursor:pointer">{ico('clip', 14)} Attach <input type="file" name="files" multiple style="display:none" onchange="document.getElementById('fsel').textContent=Array.from(this.files).map(function(f){{return f.name}}).join(', ')"></label>
    <span id="fsel" style="font-size:12px;color:#605e5c"></span>
    <span style="margin-left:auto;font-size:13px;color:#605e5c">{E(title)}</span></div>
  {warn}<div class="fld"><label>From</label><input value="{E(display_name(user))} &lt;{E(user)}&gt;" disabled></div>
  <div class="fld"><label for="to">To</label><input id="to" name="to" list="gal" value="{E(to)}" autocomplete="off"></div>
  <div class="fld"><label for="cc">Cc</label><input id="cc" name="cc" list="gal" value="{E(cc)}" autocomplete="off"></div>
  <div class="fld"><label for="bcc">Bcc</label><input id="bcc" name="bcc" list="gal" autocomplete="off"></div>
  <div class="fld"><label for="subject">Subject</label><input id="subject" name="subject" value="{E(subject)}" maxlength="250"></div>
  <div class="fld"><label for="imp">Importance</label><select id="imp" name="importance" style="max-width:160px">
    {''.join(f'<option{" selected" if imp == v else ""}>{v}</option>' for v in ("Normal", "High", "Low"))}</select></div>
  {f'<div class="atts">{att_list}</div>' if att_list else ''}
  <textarea name="body" aria-label="Message body" {'autofocus' if mode in ('reply', 'replyall') else ''}>{E(body)}</textarea>
  <datalist id="gal">{datalist}</datalist>
</form></main>"""
    return page(f"{title} - Outlook", chrome("mail", inner))


@app.post("/owa/compose")
@need_login
def owa_compose_post():
    user = g.user
    con = db()
    ip = atblog.client_ip(request)
    f = request.form
    do = f.get("do", "send")
    draft_id = int(f["draft_id"]) if f.get("draft_id", "").isdigit() else None
    draft = _own_message(draft_id) if draft_id else None
    if draft and not draft["is_draft"]:
        draft = None
    if do == "discard":
        if draft:
            with _wlock:
                con.execute("DELETE FROM attachments WHERE message_id=?", (draft["id"],))
                con.execute("DELETE FROM messages WHERE id=?", (draft["id"],))
                con.commit()
        return redirect("/owa/")
    to, cc, bcc = parse_recipients(f.get("to")), parse_recipients(f.get("cc")), parse_recipients(f.get("bcc"))
    subject = f.get("subject", "").strip()
    body_text = f.get("body", "")
    body_html = _html_from_text(body_text) if body_text.strip() else "<div></div>"
    importance = f.get("importance") if f.get("importance") in ("Normal", "High", "Low") else "Normal"
    # attachments: kept (from draft / forwarded source) + new uploads
    keep = [int(i) for i in f.getlist("keep_att") if i.isdigit()]
    atts = []
    if keep:
        m = ",".join("?" * len(keep))
        atts += [(r["filename"], r["mime"], r["data"]) for r in con.execute(
            f"SELECT a.* FROM attachments a JOIN messages m ON m.id=a.message_id WHERE m.mailbox=? AND a.id IN ({m})",
            [user] + keep)]
    for up in request.files.getlist("files"):
        if up and up.filename:
            data = up.read()
            atts.append((os.path.basename(up.filename)[:120], up.mimetype or "application/octet-stream", data))
    frm = {"email": user, "name": display_name(user)}
    now = datetime.now(TZ)
    with _wlock:
        if draft:
            con.execute("DELETE FROM attachments WHERE message_id=?", (draft["id"],))
            con.execute("DELETE FROM messages WHERE id=?", (draft["id"],))
        if do == "save" or (do == "send" and not (to or cc or bcc)):
            mid = _insert_message(con, user, _folder_id(con, user, "drafts"), frm, to, cc, subject, body_html, now,
                                  bcc=bcc, read=True, importance=importance, atts=atts, is_draft=True)
            con.commit()
            atblog.log("exchange.draft_save", ip, user=user, subject=subject)
            if do == "send":
                return redirect(f"/owa/compose?draft={mid}&err=norcpt")
            return redirect(f"/owa/?f={_folder_id(con, user, 'drafts')}")
        _insert_message(con, user, _folder_id(con, user, "sent"), frm, to, cc, subject, body_html, now,
                        bcc=bcc, read=True, importance=importance, atts=atts)
        delivered, bad = deliver(con, user, to, cc, bcc, subject, body_html, atts, importance)
        con.commit()
    atblog.log("exchange.message_send", ip, user=user, to=[a["email"] for a in to + cc + bcc], subject=subject,
               attachments=len(atts), internal_delivered=delivered, undeliverable=bad, via="owa")
    return redirect("/owa/?f=" + str(_folder_id(con, user, "inbox")))


@app.post("/owa/meeting/<int:mid>")
@need_login
def owa_meeting(mid):
    user = g.user
    con = db()
    m = _own_message(mid)
    r = request.form.get("r")
    if not m or r not in ("accepted", "tentative", "declined"):
        return redirect("/owa/")
    ics = con.execute("SELECT data FROM attachments WHERE message_id=? AND filename LIKE '%.ics'", (mid,)).fetchone()
    title = re.sub(r"(?i)^(re|fw):\s*", "", m["subject"])
    with _wlock:
        ev = con.execute("SELECT id FROM events WHERE mailbox=? AND subject=?", (user, title)).fetchone()
        if ev:
            con.execute("UPDATE events SET response=? WHERE id=?", (r, ev["id"]))
        elif ics and r != "declined":
            txt = ics["data"].decode("utf-8", "replace")
            gs = lambda k: (re.search(rf"^{k}[^:]*:(.*)$", txt, re.M) or [None, ""])[1].strip()
            try:
                st = datetime.strptime(gs("DTSTART"), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                en = datetime.strptime(gs("DTEND"), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                con.execute('INSERT INTO events (mailbox, uid, subject, location, start, "end", organizer, attendees, body,'
                            ' show_as, response) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                            (user, gs("UID"), gs("SUMMARY") or title, gs("LOCATION"), _utc(st), _utc(en),
                             m["from_email"], "", "", "busy" if r == "accepted" else "tentative", r))
            except ValueError:
                pass
        word = {"accepted": "Accepted", "tentative": "Tentative", "declined": "Declined"}[r]
        frm = {"email": user, "name": display_name(user)}
        to = [{"email": m["from_email"], "name": m["from_name"]}]
        body = _html_from_text(f"{display_name(user)} {word.lower()} this meeting.")
        _insert_message(con, user, _folder_id(con, user, "sent"), frm, to, [], f"{word}: {title}", body,
                        datetime.now(TZ), read=True)
        deliver(con, user, to, [], [], f"{word}: {title}", body, [])
        con.execute("UPDATE messages SET category=NULL, folder_id=? WHERE id=?",
                    (_folder_id(con, user, "deleted"), mid))
        con.commit()
    atblog.log("exchange.calendar_response", atblog.client_ip(request), user=user, subject=title, response=r)
    return redirect("/owa/calendar")


# =========================================================================== #
# OWA - People                                                                 #
# =========================================================================== #
@app.get("/owa/people")
@need_login
def owa_people():
    user = g.user
    q = request.args.get("q", "").strip()
    kind = request.args.get("k", "all")
    sel = request.args.get("id", "").lower()
    ql = q.lower()
    items = sorted(GAL.values(), key=lambda p: (p["kind"] != "user", p["name"]))
    if kind != "all":
        items = [p for p in items if p["kind"] == kind]
    if q:
        items = [p for p in items if ql in " ".join(str(v) for v in p.values()).lower()]
        atblog.log("exchange.gal_lookup", atblog.client_ip(request), user=user, query=q, results=len(items), via="owa")
    if not sel and items:
        sel = items[0]["email"].lower()
    rows = "".join(
        f'<a class="pprow{" on" if p["email"].lower() == sel else ""}" href="/owa/people?{urlencode({"q": q, "k": kind, "id": p["email"]})}">'
        f'<span class="av" style="background:{avatar_color(p["email"])}">{E(initials(p["name"]))}</span>'
        f'<span style="min-width:0"><div>{E(p["name"])}</div><div class="t2">{E(p["title"])} &middot; {E(p["dept"])}</div></span></a>'
        for p in items) or '<div class="empty">No results</div>'
    tabs = "".join(f'<a class="{"on" if kind == k else ""}" href="/owa/people?{urlencode({"k": k, "q": q})}">{l}</a>'
                   for k, l in (("all", "All"), ("user", "People"), ("shared", "Shared mailboxes"),
                                ("group", "Groups"), ("room", "Rooms")))
    p = GAL.get(sel)
    card = '<div class="rp-empty">Select a contact</div>'
    if p:
        mgr = GAL.get((p["manager"] or "").lower())
        reports = [x for x in GAL.values() if (x["manager"] or "").lower() == p["email"].lower()]
        members = [GAL.get(m) for m in seed.GROUPS.get(p["email"].lower(), []) if GAL.get(m)]
        member_of = [GAL[gk] for gk, mem in seed.GROUPS.items() if p["email"].lower() in mem]
        link = lambda x: f'<a href="/owa/people?{urlencode({"id": x["email"]})}">{E(x["name"])}</a>'
        kv = [("Email", f'<a href="/owa/compose?{urlencode({"to": p["name"] + " <" + p["email"] + ">"})}">{E(p["email"])}</a>'),
              ("Job title", E(p["title"])), ("Department", E(p["dept"])), ("Company", "ТОВ «АТБ-Маркет»"),
              ("Office", E(p["office"]) or "—"), ("Work phone", E(p["phone"]) or "—"), ("Mobile", E(p["mobile"]) or "—")]
        if mgr:
            kv.append(("Manager", link(mgr)))
        if reports:
            kv.append(("Direct reports", "<br>".join(link(x) for x in reports)))
        if members:
            kv.append(("Members", "<br>".join(link(x) for x in members)))
        if member_of:
            kv.append(("Member of", "<br>".join(link(x) for x in member_of)))
        kvh = "".join(f"<div>{k}</div><div>{v}</div>" for k, v in kv)
        presence = {"user": ("#6bb700", "Available"), "shared": ("#8a8886", "Shared mailbox")}.get(p["kind"], ("#8a8886", ""))
        if p["email"] in seed.OOF:
            presence = ("#c239b3", "Out of office")
        card = f"""<div class="pad"><div class="card" style="max-width:720px">
<div style="display:flex;gap:18px;align-items:center"><span class="av" style="width:72px;height:72px;font-size:26px;background:{avatar_color(p['email'])}">{E(initials(p['name']))}</span>
<div><div style="font-size:22px;font-weight:600">{E(p['name'])}</div><div style="color:#605e5c">{E(p['title'])}</div>
<div style="font-size:12px;margin-top:4px"><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:{presence[0]}"></span> {presence[1]}</div></div>
<div style="margin-left:auto;display:flex;gap:6px"><a class="btn pri" href="/owa/compose?{urlencode({'to': p['name'] + ' <' + p['email'] + '>'})}">{ico('mail', 14)} Email</a>
<a class="btn" href="/owa/calendar/new?{urlencode({'att': p['email']})}">{ico('cal', 14)} Meeting</a></div></div>
{f'<div class="banner" style="margin-top:14px">{ico("info")} Automatic replies are turned on for this person.</div>' if p['email'] in seed.OOF else ''}
<div class="kv">{kvh}</div></div></div>"""
    inner = f"""<main class="page" style="overflow:hidden"><div class="pp"><div class="pplist">
<div class="lhead"><h1>Directory <span class="cnt">{len(items)} entries</span></h1><div class="chips">{tabs}</div></div>{rows}</div>
<div style="flex:1;overflow:auto">{card}</div></div></main>"""
    return page("People - Outlook", chrome("people", inner, q=q))


# =========================================================================== #
# OWA - Calendar                                                               #
# =========================================================================== #
def _events_between(user, start, end):
    return db().execute('SELECT * FROM events WHERE mailbox=? AND start < ? AND "end" > ? AND '
                        "COALESCE(response,'')!='declined' ORDER BY start",
                        (user, _utc(end), _utc(start))).fetchall()


@app.get("/owa/calendar")
@need_login
def owa_calendar():
    user = g.user
    view = request.args.get("view", "month")
    today = datetime.now(TZ).date()
    try:
        cur = ddate.fromisoformat(request.args.get("d", "")) if request.args.get("d") else today
    except ValueError:
        cur = today
    sel = request.args.get("id")
    detail = ""
    if sel and sel.isdigit():
        ev = db().execute("SELECT * FROM events WHERE mailbox=? AND id=?", (user, int(sel))).fetchone()
        if ev:
            s, e = local(ev["start"]), local(ev["end"])
            when = (f"{DAYS[s.weekday()]} {s:%d.%m.%Y}" + (f" – {DAYS[e.weekday()]} {e:%d.%m.%Y}" if ev["show_as"] == "allday"
                                                          else f" {s:%H:%M}–{e:%H:%M}"))
            atts = ", ".join(E(display_name(a.strip())) for a in (ev["attendees"] or "").split(";") if a.strip())
            detail = f"""<div class="card" style="margin-bottom:16px"><div style="display:flex;gap:10px;align-items:flex-start">
<div style="flex:1"><div style="font-size:18px;font-weight:600">{E(ev['subject'])}</div>
<div class="kv" style="grid-template-columns:110px 1fr"><div>When</div><div>{when}</div><div>Where</div><div>{E(ev['location']) or '—'}</div>
<div>Organizer</div><div>{E(display_name(ev['organizer']))}</div><div>Attendees</div><div>{atts or '—'}</div>
<div>Show as</div><div>{E({'busy': 'Busy', 'tentative': 'Tentative', 'free': 'Free', 'oof': 'Away', 'allday': 'Free (all day)'}.get(ev['show_as'], ev['show_as']))}</div>
<div>Notes</div><div>{E(ev['body']) or '—'}</div></div></div>
<div style="display:flex;gap:6px"><a class="btn sm" href="/owa/calendar?d={s.date().isoformat()}&view={view}">{ico('x', 12)} Close</a>
<form method="post" action="/owa/calendar/{ev['id']}/delete" data-confirm="{'Cancel this meeting' if ev['organizer'] == user else 'Remove this event from your calendar'}?"><button class="btn sm">{ico('trash', 12)} {'Cancel meeting' if ev['organizer'] == user and ev['attendees'] else 'Delete'}</button></form></div></div></div>"""
    if view == "agenda":
        start = datetime.combine(cur, datetime.min.time(), TZ)
        evs = _events_between(user, start, start + timedelta(days=30))
        rows, last = [], None
        for ev in evs:
            s, e = local(ev["start"]), local(ev["end"])
            if s.date() != last:
                rows.append(f'<tr><td colspan="3" style="background:#faf9f8;font-weight:600">{DAYS[s.weekday()]} {s:%d.%m.%Y}</td></tr>')
                last = s.date()
            tm = "All day" if ev["show_as"] == "allday" else f"{s:%H:%M}–{e:%H:%M}"
            rows.append(f'<tr><td style="width:110px">{tm}</td><td><a href="/owa/calendar?view=agenda&d={cur}&id={ev["id"]}">'
                        f'{E(ev["subject"])}</a></td><td style="color:#605e5c">{E(ev["location"])}</td></tr>')
        grid = f'<table class="t">{"".join(rows) or "<tr><td>No events in the next 30 days.</td></tr>"}</table>'
        title = f"Agenda from {cur:%d.%m.%Y}"
        prev_d, next_d = cur - timedelta(days=30), cur + timedelta(days=30)
    else:
        first = cur.replace(day=1)
        gstart = first - timedelta(days=first.weekday())
        start = datetime.combine(gstart, datetime.min.time(), TZ)
        evs = _events_between(user, start, start + timedelta(days=42))
        cells = "".join(f'<div class="dh">{d}</div>' for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                                                               "Saturday", "Sunday"))
        for i in range(42):
            d = gstart + timedelta(days=i)
            ds = datetime.combine(d, datetime.min.time(), TZ)
            de = ds + timedelta(days=1)
            chips = []
            for ev in evs:
                s, e = local(ev["start"]), local(ev["end"])
                if s < de and e > ds:
                    lbl = E(ev["subject"]) if ev["show_as"] == "allday" else f"{s:%H:%M} {E(ev['subject'])}"
                    cls = ev["show_as"] if ev["response"] != "tentative" else "tentative"
                    chips.append(f'<a class="ev {cls}" href="/owa/calendar?d={cur}&id={ev["id"]}" title="{E(ev["subject"])}">{lbl}</a>')
            more = ""
            if len(chips) > 4:
                more = f'<div style="font-size:11px;color:#605e5c">+{len(chips) - 4} more</div>'
                chips = chips[:4]
            cls = ("" if d.month == cur.month else " out") + (" today" if d == today else "")
            cells += (f'<div class="d{cls}"><a class="num" href="/owa/calendar/new?d={d}" title="New event">'
                      f'{d.day if d.day != 1 else d.strftime("%-d %b")}</a>{"".join(chips)}{more}</div>')
        grid = f'<div class="calgrid">{cells}</div>'
        title = f"{MONTHS[cur.month - 1]} {cur.year}"
        prev_d = (first - timedelta(days=1)).replace(day=1)
        next_d = (first + timedelta(days=32)).replace(day=1)
    upcoming = _events_between(user, datetime.now(TZ), datetime.now(TZ) + timedelta(days=7))[:8]
    up = "".join(f'<a class="f" href="/owa/calendar?d={local(e["start"]).date()}&id={e["id"]}" style="display:block">'
                 f'<div style="font-size:12px;color:#605e5c">{DAYS[local(e["start"]).weekday()]} {local(e["start"]):%d.%m %H:%M}</div>'
                 f'<div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{E(e["subject"])}</div></a>'
                 for e in upcoming)
    side = f"""<aside class="fp"><a class="newbtn" href="/owa/calendar/new">{ico('plus')} New event</a>
<div class="sec">Calendars</div><a class="f on" href="/owa/calendar">{ico('cal')} Calendar</a>
<a class="f" href="/owa/calendar?view=agenda">{ico('cal')} Agenda</a>
<div class="sec">Next 7 days</div>{up or '<div style="padding:6px 16px;color:#605e5c;font-size:13px">Nothing planned</div>'}</aside>"""
    inner = side + f"""<main class="page"><div class="pad" style="max-width:none">
<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap">
<a class="btn sm" href="/owa/calendar?view={view}&d={today}">Today</a>
<a class="btn sm" href="/owa/calendar?view={view}&d={prev_d}" title="Previous">{ico('left', 14)}</a>
<a class="btn sm" href="/owa/calendar?view={view}&d={next_d}" title="Next">{ico('right', 14)}</a>
<h1 style="margin:0 8px;font-size:20px;font-weight:600">{title}</h1>
<span style="margin-left:auto" class="chips"><a class="{'on' if view == 'month' else ''}" href="/owa/calendar?view=month&d={cur}">Month</a>
<a class="{'on' if view == 'agenda' else ''}" href="/owa/calendar?view=agenda&d={cur}">Agenda</a></span></div>
{detail}{grid}</div></main>"""
    return page("Calendar - Outlook", chrome("cal", inner))


@app.route("/owa/calendar/new", methods=["GET", "POST"])
@need_login
def owa_calendar_new():
    user = g.user
    err = ""
    if request.method == "POST":
        f = request.form
        try:
            d = ddate.fromisoformat(f.get("date", ""))
            allday = f.get("allday") == "1"
            if allday:
                st = datetime.combine(d, datetime.min.time(), TZ)
                en = st + timedelta(days=1)
            else:
                st = datetime.combine(d, datetime.strptime(f.get("start", "09:00"), "%H:%M").time(), TZ)
                en = datetime.combine(d, datetime.strptime(f.get("end", "09:30"), "%H:%M").time(), TZ)
            if en <= st:
                raise ValueError("end")
        except ValueError:
            err = "The end time must be after the start time."
        subj = f.get("subject", "").strip() or "(No subject)"
        atts = parse_recipients(f.get("attendees", ""))
        if not err:
            uid = uuid.uuid4().hex
            con = db()
            with _wlock:
                con.execute('INSERT INTO events (mailbox, uid, subject, location, start, "end", organizer, attendees, body,'
                            ' show_as, response) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                            (user, uid, subj, f.get("location", ""), _utc(st), _utc(en), user,
                             "; ".join(a["email"] for a in atts), f.get("body", ""),
                             "allday" if allday else f.get("show_as", "busy"), "organizer"))
                if atts:
                    ics = seed.make_ics(uid, subj, st, en, f.get("location", ""), user, [a["email"] for a in atts],
                                        f.get("body", "").replace("\n", " "))
                    body = _html_from_text(f"{f.get('body', '')}\n\nWhen: {DAYS[st.weekday()]} {st:%d.%m.%Y %H:%M}–{en:%H:%M}"
                                           f" (UTC+02:00/+03:00) Kyiv\nWhere: {f.get('location', '') or '—'}")
                    frm = {"email": user, "name": display_name(user)}
                    _insert_message(con, user, _folder_id(con, user, "sent"), frm, atts, [], subj, body,
                                    datetime.now(TZ), read=True, atts=[("invite.ics", "text/calendar", ics)])
                    deliver(con, user, atts, [], [], subj, body, [("invite.ics", "text/calendar", ics)],
                            category="meeting")
                con.commit()
            atblog.log("exchange.calendar_event", atblog.client_ip(request), user=user, subject=subj,
                       attendees=[a["email"] for a in atts])
            return redirect(f"/owa/calendar?d={d}")
    d = request.args.get("d") or datetime.now(TZ).date().isoformat()
    att = request.args.get("att", "")
    datalist = "".join(f'<option value="{E(p["name"])} &lt;{E(p["email"])}&gt;">' for p in GAL.values())
    inner = f"""<main class="page"><div class="pad"><h1 style="font-size:20px;font-weight:600;margin:0 0 6px">New event</h1>
{f'<div class="err">{E(err)}</div>' if err else ''}
<form class="form" method="post">
<label class="l">Title</label><input type="text" name="subject" required style="width:100%;max-width:640px">
<label class="l">Location</label><input type="text" name="location" list="rooms" style="width:100%;max-width:640px">
<datalist id="rooms">{''.join(f'<option value="{E(p["name"])}">' for p in GAL.values() if p["kind"] == "room")}<option value="Teams"></datalist>
<label class="l">Date and time</label>
<input type="date" name="date" value="{E(d)}" style="min-width:0"> <input type="time" name="start" value="10:00" style="min-width:0"> –
<input type="time" name="end" value="10:30" style="min-width:0"> <label style="font-size:13px"><input type="checkbox" name="allday" value="1"> All day</label>
<label class="l">Invite attendees (separate with ;)</label><input type="text" name="attendees" list="gal" value="{E(att)}" style="width:100%;max-width:640px">
<datalist id="gal">{datalist}</datalist>
<label class="l">Show as</label><select name="show_as"><option value="busy">Busy</option><option value="tentative">Tentative</option>
<option value="free">Free</option><option value="oof">Away</option></select>
<label class="l">Notes</label><textarea name="body"></textarea>
<div style="margin-top:18px;display:flex;gap:8px"><button class="btn pri">{ico('send', 14)} Save / Send</button>
<a class="btn" href="/owa/calendar">Discard</a></div></form></div></main>"""
    return page("New event - Outlook", chrome("cal", inner))


@app.post("/owa/calendar/<int:eid>/delete")
@need_login
def owa_calendar_delete(eid):
    con = db()
    with _wlock:
        con.execute("DELETE FROM events WHERE mailbox=? AND id=?", (g.user, eid))
        con.commit()
    return redirect("/owa/calendar")


# =========================================================================== #
# OWA - Options                                                                #
# =========================================================================== #
@app.route("/owa/options", methods=["GET", "POST"])
@need_login
def owa_options():
    user = g.user
    con = db()
    ip = atblog.client_ip(request)
    s = request.values.get("s", "account")
    ok = err = ""
    if request.method == "POST":
        f = request.form
        if s == "automaticreplies":
            set_setting(user, "oof_enabled", "1" if f.get("oof") == "1" else "0")
            set_setting(user, "oof_message", f.get("message", "")[:4000])
            with _wlock:
                con.execute("DELETE FROM autoreplied WHERE mailbox=?", (user,))
                con.commit()
            ok = "Your automatic reply settings have been saved."
        elif s == "signature":
            set_setting(user, "signature", f.get("signature", "")[:4000])
            set_setting(user, "signature_auto", "1" if f.get("auto") == "1" else "0")
            ok = "Saved."
        elif s == "general":
            ps = f.get("page_size", "50")
            set_setting(user, "page_size", ps if ps in ("25", "50", "100") else "50")
            ok = "Saved."
        elif s == "rules":
            if f.get("delete", "").isdigit():
                with _wlock:
                    con.execute("DELETE FROM rules WHERE mailbox=? AND id=?", (user, int(f["delete"])))
                    con.commit()
                ok = "Rule deleted."
            elif f.get("value", "").strip():
                dest = con.execute("SELECT id FROM folders WHERE mailbox=? AND id=?", (user, f.get("folder"))).fetchone()
                if dest:
                    with _wlock:
                        con.execute("INSERT INTO rules (mailbox, name, field, value, folder_id) VALUES (?,?,?,?,?)",
                                    (user, f.get("name", "").strip() or f.get("value").strip(),
                                     "from" if f.get("field") == "from" else "subject", f["value"].strip(), dest["id"]))
                        con.commit()
                    ok = "Rule created."
        elif s == "password":
            old, new1, new2 = f.get("old", ""), f.get("new1", ""), f.get("new2", "")
            row = con.execute("SELECT password FROM mailboxes WHERE email=?", (user,)).fetchone()
            atblog.log("exchange.password_change_attempt", ip, user=user, old_ok=row["password"] == old)
            if row["password"] != old:
                err = "The current password you entered is incorrect."
            elif new1 != new2:
                err = "The passwords you entered don't match."
            else:
                err = ("Your password couldn't be changed. The new password doesn't meet the length, complexity, or "
                       "history requirements of your organization, or the minimum password age (1 day) hasn't passed "
                       "since the last change.")
        if ok:
            atblog.log("exchange.settings_change", ip, user=user, section=s)
    nav_items = [("General", [("account", "My account"), ("general", "Mail view"), ("password", "Change password"),
                              ("about", "About")]),
                 ("Mail", [("automaticreplies", "Automatic replies"), ("signature", "Email signature"),
                           ("rules", "Inbox rules")])]
    nav = "".join(f'<div class="h">{h}</div>' + "".join(
        f'<a class="{"on" if s == k else ""}" href="/owa/options?s={k}">{l}</a>' for k, l in items)
        for h, items in nav_items)
    msg = (f'<div class="ok">{E(ok)}</div>' if ok else "") + (f'<div class="err">{E(err)}</div>' if err else "")
    p = GAL.get(user, {"name": display_name(user), "title": "", "dept": "", "office": "", "phone": ""})
    if s == "automaticreplies":
        on = setting(user, "oof_enabled", "0") == "1"
        body = f"""<h2>Automatic replies</h2><p style="color:#605e5c">Create automatic reply (Out of Office) messages here.
You can set your reply to start at a specific time, or leave it on until you turn it off.</p>
<form class="form" method="post"><input type="hidden" name="s" value="automaticreplies">
<label style="display:block;margin:8px 0"><input type="radio" name="oof" value="0"{'' if on else ' checked'}> Don't send automatic replies</label>
<label style="display:block;margin:8px 0"><input type="radio" name="oof" value="1"{' checked' if on else ''}> Send automatic replies</label>
<label class="l">Send a reply once to each sender with the following message:</label>
<textarea name="message">{E(setting(user, 'oof_message'))}</textarea>
<div style="margin-top:14px"><button class="btn pri">Save</button></div></form>"""
    elif s == "signature":
        body = f"""<h2>Email signature</h2><form class="form" method="post"><input type="hidden" name="s" value="signature">
<textarea name="signature" style="min-height:160px">{E(setting(user, 'signature'))}</textarea>
<label style="display:block;margin:10px 0;font-size:13px"><input type="checkbox" name="auto" value="1"{' checked' if setting(user, 'signature_auto') == '1' else ''}>
Automatically include my signature on new messages, replies and forwards</label>
<button class="btn pri">Save</button></form>"""
    elif s == "rules":
        rules = con.execute("SELECT r.*, f.name AS fname FROM rules r LEFT JOIN folders f ON f.id=r.folder_id WHERE r.mailbox=?",
                            (user,)).fetchall()
        rows = "".join(f'<tr><td>{E(r["name"])}</td><td>If {"sender" if r["field"] == "from" else "subject"} includes '
                       f'“{E(r["value"])}” → move to <b>{E(r["fname"])}</b></td><td><form method="post">'
                       f'<input type="hidden" name="s" value="rules"><button class="btn sm" name="delete" value="{r["id"]}">'
                       f'Delete</button></form></td></tr>' for r in rules)
        opts = "".join(f'<option value="{f["id"]}">{E(f["name"])}</option>' for f in folders_of(user))
        body = f"""<h2>Inbox rules</h2><p style="color:#605e5c">Rules are applied to new messages in the order shown.</p>
<table class="t"><tr><th>Name</th><th>Condition and action</th><th></th></tr>{rows or '<tr><td colspan="3">No rules.</td></tr>'}</table>
<h3 style="font-size:15px;margin-top:24px">New rule</h3><form class="form" method="post"><input type="hidden" name="s" value="rules">
<input type="text" name="name" placeholder="Name" style="min-width:180px">
<select name="field" style="min-width:0"><option value="from">Sender includes</option><option value="subject">Subject includes</option></select>
<input type="text" name="value" placeholder="text" required style="min-width:180px"> → <select name="folder" style="min-width:0">{opts}</select>
<button class="btn pri">Create</button></form>"""
    elif s == "password":
        body = f"""<h2>Change password</h2><p style="color:#605e5c">Enter your current password, type a new password, and then confirm it.</p>
<form class="form" method="post" autocomplete="off"><input type="hidden" name="s" value="password">
<label class="l">Domain\\user name</label><input type="text" value="ATB\\{E(user.split('@')[0])}" disabled>
<label class="l">Current password</label><input type="password" name="old" required>
<label class="l">New password</label><input type="password" name="new1" required>
<label class="l">Confirm new password</label><input type="password" name="new2" required>
<div style="margin-top:14px"><button class="btn pri">Save</button></div></form>"""
    elif s == "general":
        ps = setting(user, "page_size", "50")
        body = f"""<h2>Mail view</h2><form class="form" method="post"><input type="hidden" name="s" value="general">
<label class="l">Items per page in the message list</label><select name="page_size">{''.join(f'<option{" selected" if ps == v else ""}>{v}</option>' for v in ("25", "50", "100"))}</select>
<label class="l">Language</label><select disabled><option>English (United States)</option></select>
<label class="l">Time zone</label><select disabled><option>(UTC+02:00) Kyiv</option></select>
<label class="l">Date format</label><select disabled><option>dd.MM.yyyy</option></select>
<div style="margin-top:14px"><button class="btn pri">Save</button></div></form>"""
    elif s == "about":
        body = f"""<h2>About</h2><div class="kv" style="grid-template-columns:200px 1fr">
<div>User</div><div>{E(display_name(user))}</div><div>Email address</div><div>{E(user)}</div>
<div>Mailbox server</div><div>EX-MBX-P01.atb.local</div><div>Client access server</div><div>ex.atbmarket.com</div>
<div>Exchange version</div><div>15.1 (Build 2507.39)</div><div>OWA version</div><div>15.1.2507.39</div>
<div>Client</div><div>{E(request.headers.get('User-Agent', '')[:120])}</div><div>Client IP</div><div>{E(ip)}</div>
<div>Help desk</div><div>IT Service Desk, вн. 1919, it-helpdesk@atbmarket.com</div></div>"""
    else:
        s = "account"
        used = 49.21
        n = con.execute("SELECT COUNT(*) FROM messages WHERE mailbox=?", (user,)).fetchone()[0]
        body = f"""<h2>My account</h2><div class="card" style="max-width:720px"><div style="display:flex;gap:16px;align-items:center">
<span class="av" style="width:64px;height:64px;font-size:22px;background:{avatar_color(user)}">{E(initials(p['name']))}</span>
<div><div style="font-size:20px;font-weight:600">{E(p['name'])}</div><div style="color:#605e5c">{E(user)}</div></div></div>
<div class="kv"><div>Department</div><div>{E(p.get('dept', '')) or '—'}</div><div>Office</div><div>{E(p.get('office', '')) or '—'}</div>
<div>Work phone</div><div>{E(p.get('phone', '')) or '—'}</div><div>Mailbox usage</div><div>{used:.2f} GB of {QUOTA_GB:.0f} GB
<div class="bar" style="height:6px;background:#e1dfdd;margin-top:4px;max-width:300px"><i style="display:block;height:100%;width:{used / QUOTA_GB * 100:.0f}%;background:#d13438"></i></div></div>
<div>Items</div><div>{nfmt(folder_total(user, get_folder(user, None)) + n)}</div>
<div>Last sign-in</div><div>{fmt_full(_utc(datetime.now(TZ)))} from {E(ip)}</div></div>
<p style="font-size:13px;margin-top:16px"><a href="/owa/options?s=password">Change your password</a> &middot; <a href="/owa/options?s=automaticreplies">Automatic replies</a></p></div>"""
    inner = f"""<aside class="fp optnav"><div style="padding:8px 16px 6px;font-size:16px;font-weight:600">Options</div>{nav}
<div style="padding:16px"><a href="/owa/">&larr; Back to Mail</a></div></aside>
<main class="page"><div class="pad"><style>.pad h2{{font-size:20px;font-weight:600;margin:0 0 10px}}</style>{msg}{body}</div></main>"""
    return page("Options - Outlook", chrome("opts", inner))


# --------------------------------------------------------------------------- #
@app.get("/healthz")
def healthz():
    return "ok", 200


@app.errorhandler(404)
def not_found(_e):
    body = f"""<div style="max-width:560px;margin:12vh auto;padding:0 20px"><div style="color:#0072c6;font-size:36px;font-weight:300">
:-( Something went wrong</div><p>The resource you are looking for has been removed, had its name changed, or is temporarily unavailable.</p>
<p style="color:#888;font-size:12px">X-OWA-Error: Microsoft.Exchange.Clients.Owa2.Server.Core.OwaObjectNotFoundException<br>
X-FEServer: EX-MBX-P01 &middot; {datetime.now(timezone.utc):%m/%d/%Y %H:%M:%S}</p><p><a href="/owa/">Go to Outlook</a></p></div>"""
    return page("Error", body, 404)


init_db()

if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80, threaded=True)
