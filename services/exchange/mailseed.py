"""Seed content for the ex.atbmarket.com mailbox store.

Everything here is fictional scenario data: people, suppliers, invoices.
`build()` returns plain dicts; app.py writes them into sqlite on first start.
Dates are relative to "now" so the mailbox always looks current.
"""
import csv
import io
import random
import uuid
import zipfile
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Kyiv")
DOMAIN = "atbmarket.com"
RESET_BASE = "https://supplier.atbmarket.com/index.php?entryPoint=Changenewpassword&guid="
CLAIMED_INBOX_TOTAL = 15907

# --------------------------------------------------------------------------- #
# Directory (GAL)                                                             #
# --------------------------------------------------------------------------- #
# email, display, title, department, office, phone, mobile, manager, kind
PEOPLE = [
    ("supplier@atbmarket.com", "ATB Supplier Desk", "Shared mailbox", "Відділ по роботі з постачальниками",
     "Дніпро, вул. Урицького 40, каб. 3.08", "+380 56 790-11-40", "", "o.kovalenko@atbmarket.com", "shared"),
    ("o.kovalenko@atbmarket.com", "Коваленко Олена", "Head of Supplier Relations", "Відділ по роботі з постачальниками",
     "Дніпро, каб. 3.10", "+380 56 790-11-41", "+380 67 512 40 18", "", "user"),
    ("a.melnyk@atbmarket.com", "Мельник Андрій", "Category Manager - Dairy", "Комерційна дирекція",
     "Дніпро, каб. 4.02", "+380 56 790-12-07", "+380 50 311 72 09", "o.kovalenko@atbmarket.com", "user"),
    ("i.shevchenko@atbmarket.com", "Шевченко Ірина", "Category Manager - Grocery", "Комерційна дирекція",
     "Дніпро, каб. 4.02", "+380 56 790-12-08", "+380 67 900 15 33", "o.kovalenko@atbmarket.com", "user"),
    ("y.oliinyk@atbmarket.com", "Олійник Юлія", "Procurement Specialist", "Відділ закупівель",
     "Дніпро, каб. 3.14", "+380 56 790-11-52", "", "o.kovalenko@atbmarket.com", "user"),
    ("d.bondarenko@atbmarket.com", "Бондаренко Дмитро", "Logistics Coordinator", "Логістика",
     "РЦ Дніпро, адмінкорпус", "+380 56 790-30-15", "+380 96 441 08 27", "r.petrenko@atbmarket.com", "user"),
    ("r.petrenko@atbmarket.com", "Петренко Роман", "DC Manager - Dnipro", "Логістика",
     "РЦ Дніпро", "+380 56 790-30-01", "+380 67 630 22 90", "", "user"),
    ("n.tkachenko@atbmarket.com", "Ткаченко Наталія", "Accounts Payable Specialist", "Фінансовий департамент",
     "Дніпро, каб. 2.21", "+380 56 790-14-33", "", "i.polishchuk@atbmarket.com", "user"),
    ("i.polishchuk@atbmarket.com", "Поліщук Ігор", "Financial Controller", "Фінансовий департамент",
     "Дніпро, каб. 2.25", "+380 56 790-14-01", "+380 50 120 88 41", "", "user"),
    ("m.lysenko@atbmarket.com", "Лисенко Максим", "QA Engineer", "Служба якості",
     "Дніпро, лабораторія", "+380 56 790-17-12", "+380 63 228 51 70", "", "user"),
    ("t.hnatiuk@atbmarket.com", "Гнатюк Тарас", "Business Applications Engineer (CRM)", "ІТ - Бізнес-застосунки",
     "Дніпро, каб. 5.07", "+380 56 790-19-24", "", "s.kravchenko@atbmarket.com", "user"),
    ("s.kravchenko@atbmarket.com", "Кравченко Сергій", "IT Service Desk Lead", "ІТ - Підтримка користувачів",
     "Дніпро, каб. 5.01", "+380 56 790-19-00", "+380 67 455 19 00", "", "user"),
    ("v.savchenko@atbmarket.com", "Савченко Віктор", "Information Security Officer", "Служба інформаційної безпеки",
     "Дніпро, каб. 5.12", "+380 56 790-19-60", "", "", "user"),
    ("o.rudenko@atbmarket.com", "Руденко Оксана", "HR Business Partner", "Управління персоналом",
     "Дніпро, каб. 1.18", "+380 56 790-15-09", "", "", "user"),
    ("s.moroz@atbmarket.com", "Мороз Світлана", "Legal Counsel", "Юридичний департамент",
     "Дніпро, каб. 2.04", "+380 56 790-16-02", "", "", "user"),
    ("h.marchenko@atbmarket.com", "Марченко Галина", "Office Manager", "Адміністративний відділ",
     "Дніпро, ресепшн", "+380 56 790-10-00", "", "", "user"),
    ("k.savytska@atbmarket.com", "Савицька Катерина", "Category Manager - Fresh", "Комерційна дирекція",
     "Дніпро, каб. 4.04", "+380 56 790-12-11", "", "o.kovalenko@atbmarket.com", "user"),
    ("p.zinchenko@atbmarket.com", "Зінченко Павло", "Logistics Planner", "Логістика",
     "РЦ Київ (Бровари)", "+380 44 390-22-17", "+380 93 117 40 52", "r.petrenko@atbmarket.com", "user"),
    ("it-helpdesk@atbmarket.com", "IT Service Desk", "Shared mailbox", "ІТ - Підтримка користувачів",
     "", "+380 56 790-19-19 (вн. 1919)", "", "s.kravchenko@atbmarket.com", "shared"),
    ("logistics@atbmarket.com", "ATB Logistics", "Shared mailbox", "Логістика", "", "+380 56 790-30-00", "", "", "shared"),
    ("finance@atbmarket.com", "ATB Finance (AP)", "Shared mailbox", "Фінансовий департамент", "", "", "", "", "shared"),
    ("procurement@atbmarket.com", "ATB Procurement", "Shared mailbox", "Відділ закупівель", "", "", "", "", "shared"),
    ("edi@atbmarket.com", "EDI Gateway", "System mailbox", "ІТ - Інтеграції", "", "", "", "", "shared"),
    ("hr@atbmarket.com", "HR ATB", "Shared mailbox", "Управління персоналом", "", "", "", "", "shared"),
    ("it-ops@atbmarket.com", "IT Operations", "Shared mailbox", "ІТ - Інфраструктура", "", "", "", "", "shared"),
    ("education@atbmarket.com", "Навчальний центр АТБ", "Shared mailbox", "Навчальний центр", "", "", "", "", "shared"),
    ("security@atbmarket.com", "Information Security", "Shared mailbox", "Служба інформаційної безпеки",
     "", "", "", "v.savchenko@atbmarket.com", "shared"),
    ("room-3.12@atbmarket.com", "Переговорна 3.12 (Дніпро, 12 місць)", "Room", "Ресурси", "Дніпро, 3 поверх", "", "", "", "room"),
    ("room-4.01@atbmarket.com", "Переговорна 4.01 (Дніпро, 6 місць)", "Room", "Ресурси", "Дніпро, 4 поверх", "", "", "", "room"),
    ("all-supplier-relations@atbmarket.com", "Supplier Relations (all)", "Distribution list",
     "Відділ по роботі з постачальниками", "", "", "", "", "group"),
    ("category-managers@atbmarket.com", "Category Managers", "Distribution list", "Комерційна дирекція",
     "", "", "", "", "group"),
]

GROUPS = {
    "all-supplier-relations@atbmarket.com": ["o.kovalenko@atbmarket.com", "y.oliinyk@atbmarket.com",
                                             "supplier@atbmarket.com"],
    "category-managers@atbmarket.com": ["a.melnyk@atbmarket.com", "i.shevchenko@atbmarket.com",
                                        "k.savytska@atbmarket.com"],
}

# Mailboxes that can sign in. Only the supplier desk password exists anywhere
# else in the world (step 4/9); the rest are random and never disclosed.
def _pw():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!#%"
    return "".join(random.SystemRandom().choice(alphabet) for _ in range(20))


def mailbox_logins():
    out = {"supplier@atbmarket.com": "supplier123569"}
    for p in PEOPLE:
        if p[8] in ("user", "shared") and p[0] not in out:
            out[p[0]] = _pw()
    return out


# Auto-responders for in-process delivery
OOF = {
    "d.bondarenko@atbmarket.com": (
        "Доброго дня! Я у відпустці до 20.10 включно, доступ до пошти обмежений.\n"
        "З питань слотів розвантаження РЦ Дніпро звертайтеся до Зінченка Павла "
        "(p.zinchenko@atbmarket.com, +380 93 117 40 52) або на logistics@atbmarket.com.\n\n"
        "Hello, I am on vacation until 20 October with limited access to e-mail."),
}

# --------------------------------------------------------------------------- #
# Attachment generators                                                       #
# --------------------------------------------------------------------------- #
def _pdf_escape(s):
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(title, lines):
    """Tiny single/multi-page text PDF (Helvetica, ASCII)."""
    pages, cur = [], []
    for ln in lines:
        cur.append(ln)
        if len(cur) >= 52:
            pages.append(cur)
            cur = []
    if cur or not pages:
        pages.append(cur)
    objs = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{4 + i * 2} 0 R" for i in range(len(pages)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for pi, pl in enumerate(pages):
        stream = ["BT", "/F1 15 Tf", "50 800 Td", f"({_pdf_escape(title)}) Tj", "/F1 9.5 Tf", "0 -24 Td"] \
            if pi == 0 else ["BT", "/F1 9.5 Tf", "50 800 Td"]
        for ln in pl:
            stream.append(f"({_pdf_escape(ln)}) Tj")
            stream.append("0 -14 Td")
        stream.append("ET")
        data = "\n".join(stream).encode("latin-1", "replace")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + pi * 2} 0 R >>".encode())
        objs.append(b"<< /Length " + str(len(data)).encode() + b" >>\nstream\n" + data + b"\nendstream")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for o in offs:
        out.write(f"{o:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Producer (ATB DocFlow 4.2) >>\n"
              f"startxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def _xml(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def make_xlsx(rows, sheet="Sheet1"):
    """Minimal valid XLSX (inline strings, numbers as numbers)."""
    srows = []
    for r, row in enumerate(rows, 1):
        cells = []
        for c, v in enumerate(row):
            ref = f"{_col(c)}{r}"
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                st = ' s="1"' if r == 1 else ""
                cells.append(f'<c r="{ref}" t="inlineStr"{st}><is><t>{_xml(v)}</t></is></c>')
        srows.append(f'<row r="{r}">{"".join(cells)}</row>')
    sheet_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                 f'<sheetData>{"".join(srows)}</sheetData></worksheet>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="2"><fill><patternFill patternType="none"/></fill>'
              '<fill><patternFill patternType="gray125"/></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
              '</styleSheet>')
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{_xml(sheet)}" sheetId="1" r:id="rId1"/></sheets></workbook>'),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'),
        "xl/worksheets/sheet1.xml": sheet_xml,
        "xl/styles.xml": styles,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d)
    return buf.getvalue()


def make_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    for r in rows:
        w.writerow(r)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def make_ics(uid, summary, start, end, location, organizer, attendees, description=""):
    def f(d):
        return d.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    att = "\r\n".join(f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{a}"
                      for a in attendees)
    return ("BEGIN:VCALENDAR\r\nMETHOD:REQUEST\r\nPRODID:Microsoft Exchange Server 2016\r\n"
            "VERSION:2.0\r\nBEGIN:VEVENT\r\n"
            f"ORGANIZER;CN={organizer}:mailto:{organizer}\r\n{att}\r\n"
            f"DESCRIPTION;LANGUAGE=uk-UA:{description}\r\nUID:{uid}\r\nSUMMARY;LANGUAGE=uk-UA:{summary}\r\n"
            f"DTSTART:{f(start)}\r\nDTEND:{f(end)}\r\nLOCATION;LANGUAGE=uk-UA:{location}\r\n"
            f"DTSTAMP:{f(datetime.now(TZ))}\r\nSTATUS:CONFIRMED\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n").encode()


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"
CSV = "text/csv"
ICS = "text/calendar"
TXT = "text/plain"

# --------------------------------------------------------------------------- #
# Message helpers                                                             #
# --------------------------------------------------------------------------- #
NOW = None


def at(days_ago, hh, mm=0):
    base = NOW.date() - timedelta(days=days_ago)
    d = datetime.combine(base, dtime(hh, mm), TZ)
    # never in the future
    if d > NOW:
        d = NOW - timedelta(minutes=7 + (hh * mm) % 50)
    return d


def addr(email, name=None):
    return {"email": email, "name": name or _name_of(email)}


def _name_of(email):
    for p in PEOPLE:
        if p[0] == email:
            return p[1]
    return EXT_NAMES.get(email, email)


EXT_NAMES = {
    "s.hrytsenko@agro-svit.com.ua": "Гриценко Світлана (ТОВ «Агро-Світ»)",
    "buh@agro-svit.com.ua": "Бухгалтерія ТОВ «Агро-Світ»",
    "sales@khlibodar.ua": "ТОВ «Хлібодар Плюс» — відділ продажів",
    "m.wisniewska@nordic-pack.pl": "Magdalena Wiśniewska (Nordic Packaging Sp. z o.o.)",
    "dispatch@logitrans.ua": "LogiTrans UA — диспетчерська",
    "kovalchuk.fop@ukr.net": "ФОП Ковальчук О.В.",
    "o.danylenko@moloko-alliance.ua": "Даниленко Олег (ТОВ «Молочний Альянс»)",
    "export@balticfish.ee": "Kristjan Tamm (Baltic Fish Export OÜ)",
    "no-reply@supplier.atbmarket.com": "ATB Supplier Portal",
    "MicrosoftExchange329e71ec88ae4615bbc36ab6ce41109e@atbmarket.com": "Microsoft Outlook",
    "info@ovochi-pivden.com.ua": "ТОВ «Овочі Півдня»",
    "orders@sunflower-oil.com.ua": "ПП «Соняшникова долина»",
}

ME = "supplier@atbmarket.com"

P_ACCOUNTS = [
    ("agrosvit_sales", "ТОВ «Агро-Світ»"), ("khlibodar_acc", "ТОВ «Хлібодар Плюс»"),
    ("moloko_alliance", "ТОВ «Молочний Альянс»"), ("fop_kovalchuk", "ФОП Ковальчук О.В."),
    ("ovochi_pivden", "ТОВ «Овочі Півдня»"), ("sunvalley_oil", "ПП «Соняшникова долина»"),
    ("nordicpack_ua", "Nordic Packaging Sp. z o.o."), ("balticfish", "Baltic Fish Export OÜ"),
    ("kondyter_lviv", "ТОВ «Львівський кондитер»"), ("myasna_hata", "ТОВ «М'ясна хата»"),
    ("chystodim", "ТОВ «Чистодім»"), ("zernoprod", "ПрАТ «Зернопродукт Схід»"),
    ("ribka_plus", "ТОВ «Рибка Плюс»"), ("vodograi", "ТОВ «Водограй-Трейд»"),
    ("logitrans_ua", "ТОВ «ЛогіТранс Україна»"),
]


def reset_mail(days_ago, hh, mm, login, company, read=False):
    guid = str(uuid.uuid4())
    link = RESET_BASE + guid
    body = f"""<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#222">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:620px;border:1px solid #e1e1e1">
<tr><td style="background:#d71920;color:#fff;padding:14px 20px;font-size:18px;font-weight:600">АТБ &middot; Портал постачальників</td></tr>
<tr><td style="padding:20px">
<p>Шановний користувачу <b>{login}</b> ({company})!</p>
<p>Ми отримали запит на відновлення пароля до Вашого облікового запису на порталі постачальників АТБ.
Щоб встановити новий пароль, перейдіть за посиланням:</p>
<p><a href="{link}">{link}</a></p>
<p>Посилання дійсне протягом 24 годин. Якщо Ви не надсилали запит, просто проігноруйте цей лист.</p>
<hr style="border:none;border-top:1px solid #eee">
<p style="color:#555">Dear <b>{login}</b>, we received a request to reset your ATB Supplier Portal password.
To reset your password click the secure link: <a href="{link}">{link}</a></p>
<p style="color:#888;font-size:12px">Лист сформовано автоматично системою SuiteCRM 7.10.25. Будь ласка, не відповідайте на нього.<br>
Копія: скринька відділу по роботі з постачальниками (журнал аудиту).</p>
</td></tr></table></div>"""
    return dict(folder="inbox", frm=addr("no-reply@supplier.atbmarket.com"), to=[addr(ME)],
                subject="Password reset - action required / Відновлення пароля",
                when=at(days_ago, hh, mm), html=body, read=read, importance="High",
                reset_guid=guid, reset_link=link)


def msg(folder, frm, subject, when, text=None, html=None, to=None, cc=None, read=True,
        flag=False, importance="Normal", atts=None, category=None):
    return dict(folder=folder, frm=frm if isinstance(frm, dict) else addr(frm),
                to=to or [addr(ME)], cc=cc or [], subject=subject, when=when, text=text,
                html=html, read=read, flag=flag, importance=importance, atts=atts or [],
                category=category)


def invoice_pdf(no, date, seller, edrpou, items, buyer="TOV \"ATB-Market\", EDRPOU 30487219"):
    lines = [f"Seller: {seller}  (EDRPOU {edrpou})", f"Buyer:  {buyer}",
             f"Invoice No: {no}     Date: {date}", "Delivery: DC Dnipro, vul. Marshala Malynovskoho 114", "",
             f"{'#':<3}{'Item':<44}{'Qty':>8}{'Price':>11}{'Sum':>13}", "-" * 82]
    total = 0
    for i, (name, qty, price) in enumerate(items, 1):
        s = qty * price
        total += s
        lines.append(f"{i:<3}{name:<44}{qty:>8}{price:>11.2f}{s:>13.2f}")
    vat = round(total * 0.2, 2)
    lines += ["-" * 82, f"{'Total without VAT:':>66}{total:>13.2f}", f"{'VAT 20%:':>66}{vat:>13.2f}",
              f"{'TOTAL, UAH:':>66}{total + vat:>13.2f}", "",
              "Payment terms: 30 calendar days from delivery (supply agreement)",
              "IBAN UA21 3052 9900 0002 6006 0160 1234 5 (fictional)", "",
              "Signed with qualified e-signature (KEP) via ATB DocFlow."]
    return make_pdf(f"INVOICE {no}", lines)


# --------------------------------------------------------------------------- #
# Main builder                                                                #
# --------------------------------------------------------------------------- #
def _fri(h, m):
    d = NOW.date()
    d = d - timedelta(days=d.weekday()) + timedelta(days=4)
    return datetime.combine(d, dtime(h, m), TZ)


def build(now=None):
    global NOW
    NOW = now or datetime.now(TZ)
    rnd = random.Random(20261009)
    M = []

    # ---- password-reset copies (27, the classic step-9 loot) ---------------
    slots = [(0, 8, 41), (0, 7, 12), (0, 6, 55), (1, 17, 3), (1, 11, 26), (1, 9, 48), (2, 16, 30),
             (2, 10, 2), (3, 14, 19), (3, 8, 7), (4, 18, 44), (5, 12, 13), (6, 9, 1), (7, 15, 37),
             (8, 10, 50), (9, 13, 22), (11, 9, 9), (12, 16, 41), (14, 11, 15), (16, 8, 58),
             (19, 14, 4), (21, 10, 33), (24, 9, 20), (27, 15, 11), (31, 12, 47), (35, 10, 5), (40, 9, 30)]
    for i, (d, h, m) in enumerate(slots):
        login, comp = P_ACCOUNTS[i % len(P_ACCOUNTS)]
        M.append(reset_mail(d, h, m, login, comp, read=d >= 4))

    # ---- hand-written inbox ------------------------------------------------
    M.append(msg("inbox", "i.shevchenko@atbmarket.com",
                 "Акція «Ціна тижня» 16–22.10 — потрібні підтвердження від постачальників",
                 at(0, 9, 14), read=False, importance="High",
                 to=[addr(ME)], cc=[addr("category-managers@atbmarket.com")],
                 text="""Колеги, добрий день!

Прошу до вівторка 14.10 (12:00) зібрати підтвердження від постачальників бакалії щодо участі в акції «Ціна тижня» 16–22.10:
 - гречка 1 кг (Зернопродукт Схід) — промо-ціна 52,90;
 - олія соняшникова 0,85 л (Соняшникова долина) — 61,40;
 - макарони 400 г (Львівський кондитер — СТМ) — 24,90.

Потрібні: підтверджений обсяг на РЦ Дніпро та РЦ Київ, компенсація знижки (%), дата першого відвантаження.
Шаблон у вкладенні, заповнений файл — відповіддю на цей лист.

Дякую!
--
Ірина Шевченко
Category Manager - Grocery | АТБ-Маркет
+380 56 790-12-08""",
                 atts=[("Promo_Cina_tyzhnia_16-22.10_shablon.xlsx", XLSX, make_xlsx([
                     ["Постачальник", "SKU", "Назва", "Промо-ціна", "Компенсація, %", "Обсяг РЦ Дніпро, шт",
                      "Обсяг РЦ Київ, шт", "Перше відвантаження"],
                     ["ПрАТ «Зернопродукт Схід»", "100245871", "Гречка ядриця 1 кг", 52.9, "", "", "", ""],
                     ["ПП «Соняшникова долина»", "100311902", "Олія соняшникова раф. 0,85 л", 61.4, "", "", "", ""],
                     ["ТОВ «Львівський кондитер»", "100478015", "Макарони спіраль 400 г", 24.9, "", "", "", ""],
                 ], "Промо"))]))

    M.append(msg("inbox", "s.hrytsenko@agro-svit.com.ua", "RE: Рахунок-фактура № АС-2026/1187 від 02.10.2026",
                 at(1, 16, 22), read=False, to=[addr(ME)], cc=[addr("buh@agro-svit.com.ua")],
                 text="""Добрий день!

Підкажіть, будь ласка, чи передано рахунок АС-2026/1187 на оплату? У Вашій системі на порталі статус досі «На перевірці».
За договором відстрочка 30 днів, але нам важливо розуміти дату, бо закриваємо квартал.

Також нагадую: з понеділка я не можу зайти на портал постачальників — пароль не підходить. Надіслала запит на відновлення двічі.

З повагою,
Світлана Гриценко
менеджер з ключових клієнтів
ТОВ «Агро-Світ»
+380 67 441 20 19

-----Original Message-----
From: ATB Supplier Desk <supplier@atbmarket.com>
Sent: Friday, October 3, 2026 10:12 AM
Subject: RE: Рахунок-фактура № АС-2026/1187 від 02.10.2026

Світлано, добрий день. Рахунок отримали, передали в AP на звірку з видатковими накладними."""))

    M.append(msg("inbox", "d.bondarenko@atbmarket.com", "Перенесення слоту розвантаження — РЦ Дніпро, 10.10",
                 at(1, 13, 5), read=False, flag=True, importance="High",
                 cc=[addr("p.zinchenko@atbmarket.com")],
                 text="""Привіт!

Через ремонт рампи №7 переносимо слоти розвантаження на 10.10:
 - ТОВ «Хлібодар Плюс» — з 06:00 на 05:30, рампа 3;
 - ТОВ «Молочний Альянс» — з 08:00 на 09:30, рампа 5;
 - ПП «Соняшникова долина» — без змін, 11:00, рампа 2.

Передайте, будь ласка, постачальникам і попросіть водіїв мати при собі ТТН у паперовому вигляді — сканер на КПП-2 тимчасово не працює.

Дмитро"""))

    M.append(msg(
        "inbox", addr("MicrosoftExchange329e71ec88ae4615bbc36ab6ce41109e@atbmarket.com"),
        "Your mailbox is almost full / Ваша поштова скринька майже заповнена", at(1, 6, 0), read=False,
        importance="High",
        html="""<div style="font-family:Segoe UI,Arial;font-size:14px">
<p style="font-size:20px;color:#c00000">Your mailbox is almost full.</p>
<p><b>49.21 GB</b> used of <b>50 GB</b> (15 907 items in Inbox).</p>
<p>Your mailbox is almost full. Please reduce the size of your mailbox. Delete any items you don't need,
empty your Deleted Items folder and move older items to an archive.</p>
<p>Поштова скринька майже заповнена. Видаліть непотрібні елементи або перенесіть старі листи до архіву.</p>
<p style="color:#666;font-size:12px">Sent by Microsoft Exchange Server 2016</p></div>"""))

    M.append(msg("inbox", "o.kovalenko@atbmarket.com",
                 "Нарада: підсумки Q3 з постачальниками молочної групи", at(1, 10, 31),
                 to=[addr(ME), addr("a.melnyk@atbmarket.com"), addr("y.oliinyk@atbmarket.com")],
                 text="""Колеги,

запрошую на нараду щодо підсумків Q3 з постачальниками молочної групи (fill rate, повернення, претензії QA).
Від постачальників — Молочний Альянс (Даниленко О.) підключиться через Teams.

Підготуйте, будь ласка:
 - Андрій — динаміку fill rate по SKU;
 - Supplier Desk — перелік відкритих звернень з порталу;
 - Юлія — статус перепідписання додаткових угод.

Олена Коваленко
Head of Supplier Relations""",
                 atts=[("invite.ics", ICS, make_ics("040000008200E00074C5B7101A82E00800000000Q3DAIRY",
                     "Нарада: підсумки Q3 з постачальниками молочної групи", _fri(10, 0), _fri(11, 30),
                     "Переговорна 3.12 / Teams", "o.kovalenko@atbmarket.com",
                     [ME, "a.melnyk@atbmarket.com", "y.oliinyk@atbmarket.com"]))], category="meeting"))

    M.append(msg("inbox", "it-ops@atbmarket.com",
                 "Планові роботи: портал постачальників, субота 11.10, 02:00–05:00", at(2, 15, 40),
                 to=[addr("all-supplier-relations@atbmarket.com")],
                 html="""<div style="font-family:Segoe UI,Arial;font-size:14px">
<table style="border-collapse:collapse;max-width:640px" cellpadding="8">
<tr><td style="background:#2b579a;color:#fff;font-weight:600">IT Operations &middot; Повідомлення про планові роботи</td></tr>
<tr><td>
<p><b>Система:</b> Портал постачальників (supplier.atbmarket.com, SuiteCRM)<br>
<b>Вікно:</b> субота 11.10.2026, 02:00–05:00 (Київ)<br>
<b>Вплив:</b> портал недоступний; вхідні листи порталу (скринька supplier@) будуть оброблені після завершення робіт.<br>
<b>Причина:</b> оновлення PHP-FPM, ротація журналів, перевірка резервних копій.</p>
<p>Під час вікна не виконуйте масові імпорти через Import. Питання — IT Service Desk, вн. 1919.</p>
<p style="color:#666">Scheduled maintenance this weekend; expect brief downtime.</p>
</td></tr></table></div>"""))

    M.append(msg("inbox", "it-helpdesk@atbmarket.com",
                 "Нагадування: термін дії пароля облікового запису спливає через 7 днів", at(2, 7, 0),
                 text="""Шановний користувачу!

Термін дії пароля облікового запису ATB\\supplier спливає через 7 днів.
Змінити пароль можна в Outlook (Параметри -> Загальні -> Мій обліковий запис -> Змінити пароль) або натиснувши Ctrl+Alt+Del на робочому ПК.

Вимоги: не менше 12 символів, великі й малі літери, цифри; не можна використовувати 24 попередні паролі.

Не повідомляйте пароль нікому, зокрема працівникам ІТ.

IT Service Desk | вн. 1919 | it-helpdesk@atbmarket.com"""))

    M.append(msg("inbox", "dispatch@logitrans.ua", "Підтвердження бронювання авто на 14.10 — рейс DN-4471",
                 at(2, 11, 18),
                 text="""Доброго дня!

Підтверджуємо подачу авто на 14.10.2026:
  Маршрут: Бровари (РЦ Київ) -> Дніпро (РЦ Дніпро)
  Авто: DAF XF, АЕ 4471 КМ / причіп АЕ 9022 XF, реф. +2..+4
  Водій: Савчук В.П., +380 97 551 03 18
  Подача: 05:00, рампа 12

ТТН буде сформовано після завантаження. Рахунок — за фактом.

LogiTrans UA, диспетчерська 24/7""",
                 atts=[("Zayavka_DN-4471.pdf", PDF, make_pdf("TRANSPORT ORDER DN-4471", [
                     "Carrier: TOV \"LogiTrans Ukraina\"", "Customer: TOV \"ATB-Market\"",
                     "Route: Brovary (DC Kyiv) -> Dnipro (DC Dnipro)", "Date: 14.10.2026, loading 05:00, dock 12",
                     "Truck: DAF XF AE4471KM / trailer AE9022XF (reefer +2..+4 C)", "Driver: Savchuk V.P.",
                     "Cargo: dairy, 18 pallets, 9.6 t", "Rate: 21 400.00 UAH incl. VAT"]))]))

    M.append(msg("inbox", "kovalchuk.fop@ukr.net", "Не приходить лист з паролем на порталі постачальників",
                 at(3, 19, 47), read=False,
                 text="""Добрий вечір.
Я зареєструвалась на вашому порталі постачальників ще минулого тижня, натиснула «Зареєструватися», а там пише що посилання надіслано і треба чекати модератора. Лист так і не прийшов, у спамі теж нема.
Логін fop_kovalchuk. Що робити? Нам треба завантажити сертифікати якості на мед.

Ковальчук Ольга
ФОП, м. Полтава
+380 66 712 33 08"""))

    M.append(msg("inbox", "finance@atbmarket.com", "Рахунок № 44821 погоджено до оплати", at(3, 12, 2),
                 text="""Рахунок № 44821 (ТОВ «Хлібодар Плюс», 412 880,40 грн з ПДВ) погоджено та включено до платіжного реєстру на 15.10.2026.

Your invoice has been approved and scheduled for payment.

ATB Finance — Accounts Payable
Це автоматичне повідомлення SAP FI."""))

    M.append(msg("inbox", "logistics@atbmarket.com", "Тижневий звіт логістики — тиждень 40",
                 at(4, 8, 30),
                 text="""Доброго ранку!
У вкладенні — тижневий звіт по постачальниках (OTIF, недопоставки, відхилення по температурі) за тиждень 40.
Червоним виділено постачальників з OTIF < 92%.

Attached is the weekly logistics summary for review.

ATB Logistics""",
                 atts=[("Logistics_weekly_W40_2026.xlsx", XLSX, make_xlsx(
                     [["Постачальник", "Поставок", "OTIF, %", "Недопоставка, шт", "Темп. відхилення", "Коментар"]] +
                     [[n, rnd.randint(8, 40), round(rnd.uniform(86, 99.8), 1), rnd.randint(0, 900),
                       rnd.choice(["0", "0", "1", "2"]), rnd.choice(["", "", "перевірити ТТН", "запізнення 2 год"])]
                      for _, n in P_ACCOUNTS], "W40"))]))

    M.append(msg("inbox", "sales@khlibodar.ua", "Оновлений прайс-лист з 01.11.2026", at(5, 14, 9),
                 text="""Шановні партнери!

Повідомляємо про зміну цін на хлібобулочну продукцію з 01.11.2026 у зв'язку зі зростанням вартості борошна та енергоносіїв (в середньому +6,8%).
Оновлений прайс-лист та обґрунтування — у вкладенні. Просимо погодити до 20.10.

З повагою,
відділ продажів ТОВ «Хлібодар Плюс»""",
                 atts=[("Prais_Khlibodar_01.11.2026.xlsx", XLSX, make_xlsx([
                     ["Код", "Найменування", "Вага, г", "Ціна до 01.11", "Ціна з 01.11", "Зміна, %"],
                     ["KH-001", "Батон нарізний", 450, 27.6, 29.4, 6.5], ["KH-002", "Хліб український", 750, 31.2, 33.5, 7.4],
                     ["KH-014", "Хліб житній з кмином", 500, 34.0, 36.1, 6.2], ["KH-021", "Булочка з маком", 90, 9.8, 10.5, 7.1],
                     ["KH-033", "Лаваш тонкий", 250, 22.4, 23.9, 6.7], ["KH-040", "Багет французький", 280, 24.0, 25.6, 6.7],
                 ], "Прайс")), ("Obgruntuvannia_cin.pdf", PDF, make_pdf("Price change justification", [
                     "TOV \"Khlibodar Plus\" - price revision from 01.11.2026", "",
                     "Wheat flour (1st grade): +11.2% since July", "Electricity tariff: +9.0% (non-household)",
                     "Logistics (diesel): +4.5%", "Packaging film: +3.1%", "",
                     "Weighted average increase requested: 6.8%"]))]))

    M.append(msg("inbox", "o.kovalenko@atbmarket.com", "Accepted: Нарада: підсумки Q3 з постачальниками молочної групи",
                 at(1, 11, 2), text="Коваленко Олена прийняла запрошення."))

    M.append(msg("inbox", "s.hrytsenko@agro-svit.com.ua", "Рахунок-фактура № АС-2026/1187 від 02.10.2026",
                 at(6, 9, 51),
                 text="""Добрий день!
Надсилаємо рахунок-фактуру за поставку від 01.10 (ВН № 2026-1187, РЦ Дніпро). Оригінал підписано КЕП у системі ЕДО.

Світлана Гриценко, ТОВ «Агро-Світ»""",
                 atts=[("AS-2026-1187.pdf", PDF, invoice_pdf("AS-2026/1187", "02.10.2026", "TOV \"Agro-Svit\"", "41827733", [
                     ("Potatoes washed, kg", 12000, 14.20), ("Carrots, kg", 4500, 16.80), ("Onions yellow, kg", 6000, 13.10),
                     ("Beetroot, kg", 3000, 12.40), ("Cabbage white, kg", 5000, 9.90)]))]))

    M.append(msg("inbox", "m.wisniewska@nordic-pack.pl", "RE: Delivery schedule for shrink film, PO 4500987712",
                 at(7, 15, 26), to=[addr(ME)], cc=[addr("y.oliinyk@atbmarket.com")],
                 text="""Dear colleagues,

thank you for the confirmation. Please find below the updated schedule for PO 4500987712:

  Lot 1 - 22 pallets - ETD Gdansk 13.10, ETA DC Kyiv 16.10
  Lot 2 - 18 pallets - ETD Gdansk 27.10, ETA DC Kyiv 30.10

Customs broker on your side remains TOV "Brokerservice Lviv". CMR and EUR.1 will be sent the day before departure.
Could you also confirm the new delivery address for Lot 2 - DC Dnipro or DC Kyiv?

Best regards,
Magdalena Wiśniewska
Key Account Manager CEE | Nordic Packaging Sp. z o.o.
+48 58 344 21 90

-----Original Message-----
From: ATB Supplier Desk <supplier@atbmarket.com>
Subject: RE: Delivery schedule for shrink film, PO 4500987712

Dear Magdalena, we confirm Lot 1 for DC Kyiv. Regarding Lot 2 we will come back to you this week."""))

    M.append(msg("inbox", "v.savchenko@atbmarket.com",
                 "Увага: фішингові листи «Ваше відправлення затримано»", at(8, 10, 3), importance="High",
                 to=[addr("all-supplier-relations@atbmarket.com")],
                 html="""<div style="font-family:Segoe UI,Arial;font-size:14px">
<p>Колеги, вітаю.</p>
<p>З понеділка фіксуємо розсилку листів нібито від служби доставки з темою <b>«Ваше відправлення затримано»</b>
та вкладенням <code>.html</code> / архівом. Посилання веде на підробну сторінку входу в пошту.</p>
<ul><li>не відкривайте вкладення і не вводьте корпоративний пароль на сторонніх сайтах;</li>
<li>справжня сторінка пошти — лише <b>ex.atbmarket.com/owa</b>;</li>
<li>підозрілий лист перешліть як вкладення на <a href="mailto:security@atbmarket.com">security@atbmarket.com</a>.</li></ul>
<p>Окремо нагадую: скриньки порталу постачальників (supplier@) отримують копії системних листів з посиланнями на зміну пароля.
Не пересилайте їх нікому — ці посилання дають доступ до облікових записів постачальників.</p>
<p>Віктор Савченко<br>Служба інформаційної безпеки</p></div>"""))

    M.append(msg("inbox", "a.melnyk@atbmarket.com", "FW: Акт звірки з ТОВ «Молочний Альянс» за Q3", at(9, 17, 12),
                 text="""Supplier Desk, перевірте, будь ласка, і відправте постачальнику підписаний скан. У нас розбіжність 18 214,60 грн — це повернення по акту QA від 26.09 (лот 2609-14), його в них нема.

Андрій

-----Original Message-----
From: Даниленко Олег <o.danylenko@moloko-alliance.ua>
Sent: Wednesday, September 30, 2026 4:40 PM
To: Мельник Андрій <a.melnyk@atbmarket.com>
Subject: Акт звірки з ТОВ «Молочний Альянс» за Q3

Андрію, доброго дня. Надсилаю акт звірки взаєморозрахунків за 3 квартал. Просимо підписати або надати розбіжності.""",
                 atts=[("Akt_zvirky_Moloko_Q3_2026.xlsx", XLSX, make_xlsx([
                     ["Дата", "Документ", "Дебет (Молочний Альянс)", "Кредит (АТБ)"],
                     ["01.07.2026", "Сальдо на початок", 1204551.2, ""], ["15.07.2026", "ВН 2026-0715", 640220.0, ""],
                     ["31.07.2026", "Оплата п/д 88412", "", 1204551.2], ["14.08.2026", "ВН 2026-0814", 712884.4, ""],
                     ["29.08.2026", "Оплата п/д 90233", "", 640220.0], ["12.09.2026", "ВН 2026-0912", 598110.0, ""],
                     ["30.09.2026", "Оплата п/д 92741", "", 712884.4], ["30.09.2026", "Сальдо на кінець", 598110.0, ""],
                 ], "Q3"))]))

    M.append(msg("inbox", "y.oliinyk@atbmarket.com", "Тендер на поставку овочів Q1 2027 — список учасників",
                 at(10, 11, 40),
                 text="""Привіт!

Надсилаю список учасників тендеру (овочі, Q1 2027). Прохання перевірити, чи всі мають активний обліковий запис на порталі постачальників — комерційні пропозиції приймаємо лише через портал до 24.10.

Ті, хто не може увійти, нехай роблять відновлення пароля з форми входу (посилання приходить на їхню пошту, копія — до нас).

Юля""",
                 atts=[("Tender_ovochi_Q1_2027_uchasnyky.xlsx", XLSX, make_xlsx([
                     ["№", "Учасник", "ЄДРПОУ", "Логін порталу", "Контакт", "Статус"],
                     [1, "ТОВ «Агро-Світ»", "41827733", "agrosvit_sales", "s.hrytsenko@agro-svit.com.ua", "активний"],
                     [2, "ТОВ «Овочі Півдня»", "39004127", "ovochi_pivden", "info@ovochi-pivden.com.ua", "активний"],
                     [3, "ФОП Ковальчук О.В.", "3124509876", "fop_kovalchuk", "kovalchuk.fop@ukr.net", "очікує модерації"],
                     [4, "ТОВ «Фермер-Схід»", "40551290", "-", "tender@fermer-shid.com.ua", "не зареєстрований"],
                 ], "Учасники"))]))

    M.append(msg("inbox", "m.lysenko@atbmarket.com", "Невідповідність партії йогурту (лот 2609-14) — акт",
                 at(11, 14, 55), importance="High", cc=[addr("a.melnyk@atbmarket.com")],
                 text="""Добрий день.

За результатами лабораторного контролю партія «Йогурт питний полуниця 2,5% 900 г» (лот 2609-14, ТОВ «Молочний Альянс») не відповідає специфікації: кислотність 132 °Т при нормі до 120 °Т.
Партію заблоковано, оформлено акт повернення. Акт у вкладенні — прошу направити постачальнику через портал і проконтролювати компенсацію.

Максим Лисенко, QA""",
                 atts=[("QA_akt_2609-14.pdf", PDF, make_pdf("QA NON-CONFORMANCE REPORT 2609-14", [
                     "Product: Drinking yoghurt strawberry 2.5% 900 g", "Supplier: TOV \"Molochnyi Aliians\"",
                     "Lot: 2609-14   Received: 26.09.2026, DC Dnipro, dock 5", "",
                     "Parameter          Spec        Result", "Acidity, T         <= 120      132",
                     "Temperature, C     +2..+6      +5.1", "Packaging          intact      intact", "",
                     "Decision: REJECTED. Return to supplier, 1 140 units, amount 18 214.60 UAH.",
                     "QA engineer: M. Lysenko"]))]))

    M.append(msg("inbox", "hr@atbmarket.com", "Опитування залученості працівників 2026 — 10 хвилин", at(12, 9, 0),
                 html="""<div style="font-family:Segoe UI,Arial;font-size:14px"><p>Шановні колеги!</p>
<p>Запрошуємо взяти участь в анонімному опитуванні залученості. Воно займе близько 10 хвилин і доступне до 24.10.</p>
<p>Посилання є в навчальному порталі (розділ «Опитування») — увійдіть під своїм корпоративним обліковим записом.</p>
<p>Дякуємо!<br>Управління персоналом АТБ</p></div>"""))

    M.append(msg("inbox", addr("MicrosoftExchange329e71ec88ae4615bbc36ab6ce41109e@atbmarket.com"),
                 "Undeliverable: RE: Оновлений прайс-лист", at(13, 16, 3),
                 html="""<div style="font-family:Segoe UI,Arial;font-size:14px">
<p style="font-size:18px;color:#c00000">Delivery has failed to these recipients or groups:</p>
<p><a href="mailto:pricing@khlibodar.ua">pricing@khlibodar.ua</a><br>
The e-mail address you entered couldn't be found. Please check the recipient's e-mail address and try to resend the message.</p>
<p style="color:#666;font-size:12px">Diagnostic information for administrators:<br>Generating server: ex.atbmarket.com<br>
pricing@khlibodar.ua<br>Remote Server returned '550 5.1.1 &lt;pricing@khlibodar.ua&gt;: Recipient address rejected: User unknown'</p></div>"""))

    M.append(msg("inbox", "export@balticfish.ee", "Request for supplier onboarding - Baltic Fish Export OU",
                 at(14, 10, 17),
                 text="""Hello,

we are an Estonian exporter of chilled and frozen fish (herring, mackerel, Baltic sprat) and would like to become a supplier of ATB-Market.
We registered on your supplier portal (login: balticfish) but the account is still pending. Could you please advise on the onboarding procedure and the documents required (certificates, veterinary approval number)?

Company presentation and certificates attached.

Kind regards,
Kristjan Tamm
Baltic Fish Export OU, Tallinn""",
                 atts=[("BalticFish_company_profile.pdf", PDF, make_pdf("Baltic Fish Export OU - Company profile", [
                     "Founded 2009, Tallinn, Estonia", "Production: 14 000 t/year chilled & frozen fish",
                     "Certificates: IFS Food v8, MSC CoC, BRCGS", "EU veterinary approval: EE 12 345 EC (fictional)",
                     "Export markets: PL, LT, LV, FI, DE, UA", "Contact: export@balticfish.ee"]))]))

    M.append(msg("inbox", "procurement@atbmarket.com", "Нові вимоги до маркування з 01.01.2027", at(15, 12, 0),
                 to=[addr("all-supplier-relations@atbmarket.com")],
                 text="""Колеги,

з 01.01.2027 набувають чинності оновлені вимоги до маркування харчової продукції (алергени, поживна цінність на 100 г, країна походження основного інгредієнта).
Прохання до Supplier Desk — розіслати всім активним постачальникам інформаційний лист (шаблон у вкладенні) через портал і зібрати підтвердження до 15.11.

ATB Procurement""",
                 atts=[("Markuvannia_2027_info_lyst.pdf", PDF, make_pdf("Labelling requirements from 01.01.2027", [
                     "1. Allergens highlighted in the list of ingredients.", "2. Nutrition declaration per 100 g / 100 ml.",
                     "3. Country of origin of the primary ingredient if different from the product.",
                     "4. Minimum font size 1.2 mm (x-height).", "5. Barcode GS1 EAN-13 registered to the supplier.",
                     "", "Confirmation via Supplier Portal -> Documents -> Labelling 2027 by 15.11.2026."]))]))

    M.append(msg("inbox", "it-helpdesk@atbmarket.com", "[INC-0048213] Заявку закрито: не працює сканер штрих-кодів",
                 at(16, 15, 21),
                 text="""Ваша заявка INC-0048213 закрита.

Опис: Не працює сканер штрих-кодів Zebra DS2208 на робочому місці 3.08.
Рішення: Замінено USB-кабель, перевстановлено драйвер. Перевірено разом з користувачем.

Якщо проблема повториться — відповідайте на цей лист протягом 5 днів, заявку буде відкрито повторно.

IT Service Desk"""))

    M.append(msg("inbox", "n.tkachenko@atbmarket.com", "Квартальна звірка взаєморозрахунків — постачальники бакалії",
                 at(18, 11, 11),
                 text="""Добрий день!
Відправте, будь ласка, постачальникам зі списку акти звірки за Q3 через портал (розділ «Документи»). Термін повернення підписаних — до 25.10.

Наталія Ткаченко, AP""",
                 atts=[("Zvirka_Q3_bakaliia.xlsx", XLSX, make_xlsx([
                     ["Постачальник", "ЄДРПОУ", "Сальдо АТБ, грн", "Відповідальний"],
                     ["ПрАТ «Зернопродукт Схід»", "00952411", 1840220.15, "Шевченко І."],
                     ["ПП «Соняшникова долина»", "35110846", 922410.0, "Шевченко І."],
                     ["ТОВ «Львівський кондитер»", "38220147", 410775.9, "Шевченко І."],
                     ["ТОВ «Водограй-Трейд»", "42003318", 155002.4, "Савицька К."]], "Q3"))]))

    M.append(msg("inbox", "t.hnatiuk@atbmarket.com",
                 "Портал постачальників: копії листів відновлення пароля в цій скриньці", at(20, 16, 48),
                 to=[addr(ME)], cc=[addr("o.kovalenko@atbmarket.com")],
                 text="""Привіт, колеги.

Після оновлення порталу (SuiteCRM 7.10.25) системні листи відновлення пароля для постачальників надсилаються з копією у вашу скриньку — це вимога аудиту, щоб ви бачили, хто і коли скидав доступ.

Нічого з ними робити не треба: постачальник отримує той самий лист на свою адресу і сам встановлює пароль. Посилання діє 24 години.
Якщо постачальник скаржиться, що лист не прийшов, — перевірте, чи є копія тут, і перешліть мені логін, я подивлюсь журнал відправки.

Також нагадую: портал забирає вхідну пошту з цієї ж скриньки (InboundEmail), тому, будь ласка, не міняйте пароль скриньки самостійно — спершу напишіть мені, щоб я оновив його в налаштуваннях CRM, інакше перестане працювати обробка звернень.

Тарас Гнатюк
ІТ — Бізнес-застосунки (CRM)"""))

    M.append(msg("inbox", "h.marchenko@atbmarket.com", "Нові перепустки до офісу — заміна до 31.10", at(22, 13, 30),
                 to=[addr("all-supplier-relations@atbmarket.com")],
                 text="""Колеги, добрий день!
З 01.11 старі перепустки перестануть працювати. Нові можна отримати на ресепшн (1 поверх) з 9:00 до 17:00, при собі мати паспорт або ID.
Для гостей (постачальники на переговорах) — заявку на тимчасову перепустку подавайте за день до візиту.

Галина Марченко"""))

    M.append(msg("inbox", "s.moroz@atbmarket.com", "Типовий договір поставки — редакція 2026", at(25, 10, 22),
                 text="""Надсилаю актуальну редакцію типового договору поставки (зміни: розділ 7 «Штрафні санкції», додаток 4 «Логістичні вимоги»).
Для нових постачальників використовуйте лише цю редакцію.

Світлана Мороз, Юридичний департамент""",
                 atts=[("Typovyi_dohovir_postavky_2026.pdf", PDF, make_pdf("SUPPLY AGREEMENT (standard form, rev. 2026)", [
                     "1. Subject of the agreement", "2. Price and payment terms (deferral 30-60 days)",
                     "3. Ordering via EDI (ORDERS / ORDRSP / DESADV / INVOIC)", "4. Delivery, acceptance, dock slots",
                     "5. Quality, returns, QA non-conformance", "6. Marketing services", "7. Penalties (revised)",
                     "8. Force majeure", "9. Anti-corruption clause", "Annex 4. Logistics requirements (revised)"]))]))

    M.append(msg("inbox", "r.petrenko@atbmarket.com", "Графік роботи РЦ Дніпро у вихідні 18–19.10", at(5, 17, 50),
                 to=[addr("logistics@atbmarket.com"), addr(ME)],
                 text="""18.10 (субота) РЦ Дніпро приймає за звичайним графіком, 19.10 (неділя) — лише свіжа продукція (молочка, хліб, овочі), рампи 1–5, 05:00–14:00.
Повідомте постачальників.

Петренко Р."""))

    M.append(msg("inbox", "o.danylenko@moloko-alliance.ua", "Претензія по лоту 2609-14 — наша позиція", at(4, 15, 15),
                 text="""Доброго дня.

Отримали акт QA по лоту 2609-14. Наша лабораторія на відвантаженні фіксувала кислотність 112 °Т, протокол додаємо.
Просимо провести повторний відбір проб у присутності нашого представника або прийняти арбітражне дослідження.

До вирішення питання просимо не зараховувати повернення в акт звірки.

Олег Даниленко, комерційний директор
ТОВ «Молочний Альянс»""",
                 atts=[("Protokol_lab_2609-14.pdf", PDF, make_pdf("LAB TEST REPORT (supplier) lot 2609-14", [
                     "Sample taken at shipment 25.09.2026 18:40", "Acidity: 112 T (spec <= 120 T)",
                     "Fat: 2.5 %", "Coliforms: not detected", "Lab: TOV Molochnyi Aliians, accredited No. 201/26"]))]))

    M.append(msg("inbox", "orders@sunflower-oil.com.ua", "Підтвердження участі в акції 16–22.10", at(0, 10, 2), read=False,
                 text="""Доброго дня!
ПП «Соняшникова долина» підтверджує участь в акції «Ціна тижня» 16–22.10.
Компенсація 12%, обсяг: РЦ Дніпро 18 000 шт, РЦ Київ 14 000 шт, перше відвантаження 14.10.

Менеджер з продажу, Олексій"""))

    M.append(msg("inbox", "education@atbmarket.com", "Обов'язковий курс: «Інформаційна безпека для працівників офісу»",
                 at(30, 9, 0),
                 text="""Шановні колеги!
До 31.10 необхідно пройти обов'язковий курс «Інформаційна безпека для працівників офісу» на навчальному порталі АТБ.
Вхід — під корпоративним обліковим записом. Тривалість — 40 хвилин, наприкінці тест.

Навчальний центр АТБ"""))

    # ---- generated: EDI notifications (rule → EDI folder) -------------------
    edi_sup = ["ТОВ «Агро-Світ»", "ТОВ «Хлібодар Плюс»", "ТОВ «Молочний Альянс»", "ПП «Соняшникова долина»",
               "ПрАТ «Зернопродукт Схід»", "ТОВ «Водограй-Трейд»", "ТОВ «М'ясна хата»"]
    for d in range(1, 46):
        for k in range(rnd.randint(1, 2)):
            kind = rnd.choice(["ORDERS", "ORDRSP", "DESADV", "INVOIC"])
            po = 4500980000 + d * 37 + k * 11
            sup = rnd.choice(edi_sup)
            dc = rnd.choice(["РЦ Дніпро", "РЦ Київ", "РЦ Львів"])
            M.append(msg("EDI", "edi@atbmarket.com", f"EDI {kind} №{po} — {sup} — {dc}",
                         at(d, rnd.randint(5, 21), rnd.randint(0, 59)), read=True,
                         text=f"""Документ EDI {kind} оброблено.

Номер документа: {po}
Постачальник: {sup}
Пункт доставки: {dc}
Позицій: {rnd.randint(3, 48)}
Статус: {rnd.choice(['Доставлено', 'Прийнято', 'Підтверджено', 'Прийнято з розбіжностями'])}

Повідомлення сформовано автоматично EDI Gateway. Не відповідайте на цей лист."""))

    # ---- generated: daily shipment reports (→ Звіти) -----------------------
    for d in range(1, 31):
        day = (NOW - timedelta(days=d))
        if day.weekday() == 6:
            continue
        rows = [["Постачальник", "РЦ", "Палет", "Вага, кг", "Статус"]]
        for _, n in rnd.sample(P_ACCOUNTS, 6):
            rows.append([n, rnd.choice(["Дніпро", "Київ", "Львів"]), rnd.randint(2, 33),
                         rnd.randint(400, 21000), rnd.choice(["прийнято", "прийнято", "з розбіжностями"])])
        M.append(msg("Звіти", "logistics@atbmarket.com",
                     f"Щоденний звіт про приймання — {day.strftime('%d.%m.%Y')}", at(d, 6, 15), read=True,
                     text=f"Звіт про приймання товару на РЦ за {day.strftime('%d.%m.%Y')} у вкладенні (CSV).\n\nATB Logistics",
                     atts=[(f"pryimannia_{day.strftime('%Y%m%d')}.csv", CSV, make_csv(rows))]))

    # ---- invoices folder ---------------------------------------------------
    inv_sup = [("TOV \"Agro-Svit\"", "41827733", "s.hrytsenko@agro-svit.com.ua", "АС"),
               ("TOV \"Khlibodar Plus\"", "37755120", "sales@khlibodar.ua", "ХП"),
               ("PP \"Soniashnykova Dolyna\"", "35110846", "orders@sunflower-oil.com.ua", "СД"),
               ("TOV \"Ovochi Pivdnia\"", "39004127", "info@ovochi-pivden.com.ua", "ОП")]
    for i in range(18):
        s = rnd.choice(inv_sup)
        d = 7 + i * 3
        no = f"{s[3]}-2026/{1000 + rnd.randint(1, 180)}"
        dt = (NOW - timedelta(days=d)).strftime("%d.%m.%Y")
        M.append(msg("Рахунки 2026", s[2], f"Рахунок-фактура № {no} від {dt}", at(d, rnd.randint(8, 17), rnd.randint(0, 59)),
                     text=f"Добрий день! Надсилаємо рахунок № {no} від {dt}. Оригінал підписано КЕП в системі ЕДО.\n\nЗ повагою, бухгалтерія",
                     atts=[(f"{no.replace('/', '-')}.pdf", PDF, invoice_pdf(no, dt, s[0], s[1], [
                         (rnd.choice(["Goods per specification", "Bread & bakery assortment", "Sunflower oil 0.85 l",
                                      "Fresh vegetables assortment"]), rnd.randint(100, 9000),
                          round(rnd.uniform(8, 70), 2))]))]))

    # ---- Постачальники folder ----------------------------------------------
    M.append(msg("Постачальники", "info@ovochi-pivden.com.ua", "Сертифікати якості — сезон 2026/27", at(33, 11, 0),
                 text="Надсилаємо сертифікати та протоколи досліджень на овочі сезону 2026/27.\n\nТОВ «Овочі Півдня»",
                 atts=[("Sertyfikaty_2026-27.pdf", PDF, make_pdf("Quality certificates 2026/27", [
                     "GlobalG.A.P. GGN 4063061000000 (fictional)", "Pesticide residues: compliant (protocol 4471/26)",
                     "Nitrates: compliant", "Heavy metals: compliant"]))]))
    M.append(msg("Постачальники", "o.danylenko@moloko-alliance.ua", "Контактні особи ТОВ «Молочний Альянс» з 01.09",
                 at(38, 9, 30),
                 text="""Доброго дня! Інформуємо про зміну контактних осіб:
 - комерційні питання: Даниленко Олег, +380 50 400 18 22
 - логістика/слоти: Ярошенко Інна, +380 67 300 91 40, logistics@moloko-alliance.ua
 - бухгалтерія/звірки: buh@moloko-alliance.ua"""))
    M.append(msg("Постачальники", "sales@khlibodar.ua", "Графік поставок на жовтень", at(36, 14, 12),
                 text="Графік поставок хлібобулочних виробів на жовтень у вкладенні.",
                 atts=[("Hrafik_zhovten.xlsx", XLSX, make_xlsx(
                     [["Дата", "РЦ", "Слот", "Палет"]] +
                     [[f"{dd:02d}.10.2026", rnd.choice(["Дніпро", "Київ"]), "05:30", rnd.randint(8, 22)]
                      for dd in range(1, 32) if dd % 2], "Жовтень"))]))

    # ---- Sent Items ----------------------------------------------------------
    S = lambda to, subj, when, text, cc=None, atts=None: M.append(dict(
        folder="sent", frm=addr(ME), to=[addr(t) for t in to], cc=[addr(c) for c in (cc or [])],
        subject=subj, when=when, text=text, html=None, read=True, flag=False, importance="Normal",
        atts=atts or [], category=None))
    S(["s.hrytsenko@agro-svit.com.ua"], "RE: Рахунок-фактура № АС-2026/1187 від 02.10.2026", at(6, 10, 12),
      "Світлано, добрий день. Рахунок отримали, передали в AP на звірку з видатковими накладними.\n\n--\nATB Supplier Desk\nВідділ по роботі з постачальниками\n+380 56 790-11-40")
    S(["m.wisniewska@nordic-pack.pl"], "RE: Delivery schedule for shrink film, PO 4500987712", at(8, 9, 40),
      "Dear Magdalena, we confirm Lot 1 for DC Kyiv. Regarding Lot 2 we will come back to you this week.\n\nBest regards,\nATB Supplier Desk", cc=["y.oliinyk@atbmarket.com"])
    S(["t.hnatiuk@atbmarket.com"], "Не приходять листи відновлення пароля — agrosvit_sales", at(5, 11, 5),
      "Тарасе, привіт. Постачальник Агро-Світ (логін agrosvit_sales) каже, що не отримує листи відновлення. Копії в нас є (останні 3 дні — по два на день). Подивись, будь ласка, журнал відправки.\n\nSupplier Desk")
    S(["o.danylenko@moloko-alliance.ua"], "RE: Претензія по лоту 2609-14 — наша позиція", at(4, 17, 2),
      "Олегу, доброго дня. Передали Ваш протокол у службу якості, повторний відбір проб можливий 13.10 о 10:00 на РЦ Дніпро. Підтвердіть, будь ласка, присутність представника.\n\nATB Supplier Desk", cc=["m.lysenko@atbmarket.com", "a.melnyk@atbmarket.com"])
    S(["export@balticfish.ee"], "RE: Request for supplier onboarding - Baltic Fish Export OU", at(13, 12, 30),
      "Dear Kristjan,\n\nthank you for your interest. Your portal account will be activated after the moderator review (usually 3-5 working days). Required documents: company registration extract, veterinary approval, IFS/BRC certificate, price list in UAH, product specifications.\n\nBest regards,\nATB Supplier Desk")
    S(["sales@khlibodar.ua"], "RE: Оновлений прайс-лист", at(13, 16, 1),
      "Добрий день. Прайс отримали, передали категорійному менеджеру. Відповідь щодо погодження — до 20.10.", )
    S(["kovalchuk.fop@ukr.net"], "RE: Не приходить лист з паролем на порталі постачальників", at(2, 9, 20),
      "Ольго, добрий день. Ваша реєстрація очікує перевірки модератором — після активації Ви отримаєте лист автоматично. Якщо протягом 3 робочих днів листа не буде, скористайтеся «Забули пароль?» на сторінці входу.\n\nATB Supplier Desk")
    S(["i.shevchenko@atbmarket.com"], "RE: Акція «Ціна тижня» 16–22.10", at(0, 10, 20),
      "Ірино, Соняшникова долина підтвердила (12%, 18 000 / 14 000 шт, з 14.10). Інших чекаємо.",
      atts=[])
    S(["d.bondarenko@atbmarket.com"], "RE: Перенесення слоту розвантаження — РЦ Дніпро, 10.10", at(1, 14, 30),
      "Дмитре, Хлібодар і Молочний Альянс повідомлені, підтвердження отримали телефоном.")

    # ---- Drafts --------------------------------------------------------------
    M.append(dict(folder="drafts", frm=addr(ME), to=[addr("o.kovalenko@atbmarket.com")], cc=[],
                  subject="Звіт по зверненнях з порталу за вересень", when=at(3, 18, 2),
                  text="Олено, добрий день.\n\nЗа вересень через портал надійшло 214 звернень, з них:\n - відновлення доступу — 71\n - питання оплати — 58\n - документи/сертифікати — 49\n - інше — 36\n\nСередній час відповіді ",
                  html=None, read=True, flag=False, importance="Normal", atts=[], category=None))
    M.append(dict(folder="drafts", frm=addr(ME), to=[addr("export@balticfish.ee")], cc=[],
                  subject="Documents for onboarding", when=at(9, 12, 0),
                  text="Dear Kristjan,\n\nplease upload the following documents to the portal:\n",
                  html=None, read=True, flag=False, importance="Normal", atts=[], category=None))

    # ---- Deleted Items -------------------------------------------------------
    M.append(msg("deleted", "hr@atbmarket.com", "Привітання з Днем працівників торгівлі!", at(40, 9, 0),
                 text="Шановні колеги, щиро вітаємо з професійним святом! У п'ятницю — святковий фуршет у їдальні, 15:00."))
    M.append(msg("deleted", "h.marchenko@atbmarket.com", "Хто забув парасольку в 3.12?", at(19, 17, 40),
                 text="Колеги, у переговорній 3.12 лишилась чорна парасолька. Заберіть на ресепшн :)"))
    M.append(msg("deleted", "it-helpdesk@atbmarket.com", "[INC-0047650] Заявку зареєстровано", at(28, 10, 2),
                 text="Вашу заявку INC-0047650 «Не друкує принтер HP 3.08» зареєстровано. Пріоритет: P4."))
    M.append(reset_mail(44, 10, 10, "zernoprod", "ПрАТ «Зернопродукт Схід»", read=True) | {"folder": "deleted"})

    # ---- Junk ----------------------------------------------------------------
    M.append(msg("junk", addr("delivery-notice@parcel-track-ua.top", "Служба доставки"),
                 "Ваше відправлення затримано", at(2, 3, 14), read=False,
                 html="""<div style="font-family:Arial"><p>Шановний клієнте!</p><p>Ваше відправлення <b>№ 20450091224817</b> затримано на складі через неповну адресу.</p>
<p>Щоб уникнути повернення, підтвердіть дані доставки протягом 24 годин у вкладеному документі.</p></div>""",
                 atts=[("Povidomlennia_20450091224817.html", "text/html",
                        "<html><body><h3>Document preview unavailable</h3><p>Sign in to view the document.</p></body></html>".encode())]))
    M.append(msg("junk", addr("billing@docs-secure-sign.net", "E-Sign Notification"),
                 "Invoice overdue - please review and sign", at(5, 2, 51),
                 text="You have 1 pending document: INV-88241 (Overdue). Review document: hxxp://docs-secure-sign.net/r/88241\nThis link expires in 48 hours."))
    M.append(msg("junk", addr("promo@superdeals-24.biz", "Super Deals"), "Знижки до -90% тільки сьогодні!!!", at(6, 4, 0),
                 text="Тільки сьогодні знижки до 90% на побутову техніку! Встигніть замовити."))
    M.append(msg("junk", addr("hr-recruit@jobs-ukr-hiring.com", "HR Department"), "Вакансія: віддалена робота 2 год/день, 40 000 грн",
                 at(9, 23, 12), text="Шукаємо відповідальних людей для обробки замовлень. Досвід не потрібен. Напишіть у Telegram."))
    M.append(msg("junk", addr("it-support@atbmarket-mail.com", "IT Support"), "Mailbox quota exceeded - validate account",
                 at(11, 1, 33), read=False,
                 text="Your mailbox has exceeded its quota. To continue receiving messages validate your account within 24 hours:\nhxxp://atbmarket-mail.com/owa/validate\n\nIT Support Team"))
    M.append(msg("junk", addr("crypto@fastprofit.io", "Investor Club"), "Пасивний дохід від 2000$ на місяць", at(17, 5, 5),
                 text="Інвестуйте в нашу платформу та отримуйте пасивний дохід. Гарантія прибутку!"))

    # ---- Archive -------------------------------------------------------------
    M.append(msg("archive", "o.kovalenko@atbmarket.com", "KPI відділу на 2026 рік", at(270, 10, 0),
                 text="Колеги, KPI на 2026: час відповіді на звернення постачальників < 8 робочих годин; 100% актів звірки щокварталу; онбординг нового постачальника < 10 робочих днів.",
                 atts=[("KPI_SupplierRelations_2026.xlsx", XLSX, make_xlsx([
                     ["KPI", "Ціль", "Вага"], ["Час першої відповіді, год", 8, 0.3], ["Акти звірки, %", 100, 0.3],
                     ["Онбординг, роб. днів", 10, 0.2], ["NPS постачальників", 40, 0.2]], "KPI"))]))
    M.append(msg("archive", "t.hnatiuk@atbmarket.com", "Портал постачальників — інструкція для Supplier Desk", at(190, 15, 0),
                 text="""Коротка інструкція для роботи з порталом:
1. Модерація реєстрацій: Адміністрування -> Користувачі порталу -> «Очікують».
2. Документи постачальника: картка контрагента -> вкладка «Документи».
3. Звернення з пошти створюються автоматично з листів на supplier@ (InboundEmail, кожні 5 хв).
4. Масовий імпорт контрагентів: Import (CSV, до 2 МБ). Після імпорту перевіряйте журнал помилок.

Питання — мені або в IT Service Desk."""))

    for m in M:
        m.setdefault("cc", [])
        m.setdefault("atts", [])
        m.setdefault("flag", False)
        m.setdefault("category", None)
        m.setdefault("text", None)
        m.setdefault("html", None)
    return M


FOLDERS = [
    # key, display, parent, kind
    ("inbox", "Inbox", None, "inbox"),
    ("drafts", "Drafts", None, "drafts"),
    ("sent", "Sent Items", None, "sent"),
    ("deleted", "Deleted Items", None, "deleted"),
    ("junk", "Junk Email", None, "junk"),
    ("archive", "Archive", None, "archive"),
    ("EDI", "EDI", "inbox", "user"),
    ("Звіти", "Звіти", "inbox", "user"),
    ("Рахунки 2026", "Рахунки 2026", "inbox", "user"),
    ("Постачальники", "Постачальники", "inbox", "user"),
]

RULES = [
    ("EDI-повідомлення", "from", "edi@atbmarket.com", "EDI"),
    ("Щоденні звіти приймання", "subject", "Щоденний звіт про приймання", "Звіти"),
]


def events(now=None):
    """Calendar events for the supplier desk mailbox."""
    now = now or datetime.now(TZ)
    today = now.date()
    monday = today - timedelta(days=today.weekday())

    def dt(d, h, m=0):
        return datetime.combine(d, dtime(h, m), TZ)
    E = []
    for w in range(-3, 5):
        d = monday + timedelta(weeks=w)
        E.append(("Щотижнева нарада Supplier Relations", "Переговорна 3.12", dt(d, 9, 30), dt(d, 10, 15),
                  "o.kovalenko@atbmarket.com", "all-supplier-relations@atbmarket.com", "Статус звернень, онбординг, ескалації.", "busy"))
        E.append(("Перевірка черги модерації порталу", "", dt(d + timedelta(days=2), 14, 0), dt(d + timedelta(days=2), 14, 30),
                  ME, "", "Нові реєстрації постачальників — перевірити документи.", "tentative"))
    fri = monday + timedelta(days=4)
    E += [
        ("Нарада: підсумки Q3 з постачальниками молочної групи", "Переговорна 3.12 / Teams", dt(fri, 10), dt(fri, 11, 30),
         "o.kovalenko@atbmarket.com", "supplier@atbmarket.com; a.melnyk@atbmarket.com; y.oliinyk@atbmarket.com; o.danylenko@moloko-alliance.ua",
         "Fill rate, повернення, претензії QA.", "busy"),
        ("Повторний відбір проб — лот 2609-14", "РЦ Дніпро, лабораторія", dt(today + timedelta(days=4), 10), dt(today + timedelta(days=4), 11),
         "m.lysenko@atbmarket.com", "supplier@atbmarket.com; o.danylenko@moloko-alliance.ua", "", "busy"),
        ("Дедлайн: підтвердження акції «Ціна тижня»", "", dt(today + timedelta(days=5), 12), dt(today + timedelta(days=5), 12, 30),
         ME, "", "", "free"),
        ("Портал постачальників — планові роботи", "", dt(today + timedelta(days=(5 - today.weekday()) % 7), 2),
         dt(today + timedelta(days=(5 - today.weekday()) % 7), 5), "it-ops@atbmarket.com", "", "", "oof"),
        ("Зустріч з Baltic Fish Export (онбординг)", "Teams", dt(today + timedelta(days=8), 15), dt(today + timedelta(days=8), 15, 45),
         ME, "export@balticfish.ee; y.oliinyk@atbmarket.com", "", "busy"),
        ("Тендер: овочі Q1 2027 — розкриття пропозицій", "Переговорна 4.01", dt(today + timedelta(days=15), 11), dt(today + timedelta(days=15), 13),
         "y.oliinyk@atbmarket.com", "supplier@atbmarket.com; procurement@atbmarket.com", "", "busy"),
        ("Навчання: SuiteCRM для Supplier Desk", "Переговорна 4.01", dt(today - timedelta(days=12), 14), dt(today - timedelta(days=12), 16),
         "t.hnatiuk@atbmarket.com", "all-supplier-relations@atbmarket.com", "", "busy"),
        ("Відпустка Бондаренко Д.", "", dt(today - timedelta(days=1), 0), dt(today + timedelta(days=11), 0),
         "d.bondarenko@atbmarket.com", "", "", "allday"),
    ]
    return E
