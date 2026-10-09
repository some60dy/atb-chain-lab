"""Step 8 - DC-MAIN-01.atbmarket.com Active Directory (HTTP stand-in).

The LDAP wire protocol is NOT implemented; an HTTP gateway (POST /bind,
GET|POST /search with RFC 4515 filters, base/scope/attributes/paging, /rootDSE)
plus the "ATB Directory" self-service portal stand in for it.

The directory is generated deterministically in code: ~1k office objects
(users, groups, computers, OUs) plus bulk store-staff accounts generated on
demand, so that user+computer objects add up to SEARCH_TOTAL.

Valid bind creds were reused from the Moodle leak:
    bind DN:  education@atbmarket.com
    password: Edu003868$
"""
import base64
import functools
import hashlib
import html
import random
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from flask import Flask, jsonify, redirect, request, session, url_for
import atblog

app = Flask(__name__)
app.json.sort_keys = False
# Lab-only signing key for the browser portal session cookie.
app.secret_key = "atb-lab-ad-ldap-portal-not-secret"

VALID_DN = "education@atbmarket.com"
VALID_PW = "Edu003868$"

SEARCH_TOTAL = 68250          # user-class objects (people + computer accounts)

DOMAIN = "atbmarket.com"
NETBIOS = "ATBMARKET"
BASE_DN = "DC=atbmarket,DC=com"
ROOT_OU = "OU=ATB," + BASE_DN
DOMAIN_SID = "S-1-5-21-3623811015-3361044348-30300820"
SCHEMA = "CN=Schema,CN=Configuration," + BASE_DN
MAX_PAGE = 1000               # AD MaxPageSize

NOW = time.time()


def filetime(ts):
    return str(int((ts + 11644473600) * 10**7)) if ts else "0"


def gentime(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y%m%d%H%M%S.0Z")


def from_filetime(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None
    if v <= 0 or v >= 9223372036854775807:
        return None
    return v / 10**7 - 11644473600


def from_gentime(v):
    try:
        return datetime.strptime(v[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None


def human(ts, never="Never"):
    if not ts:
        return never
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# --------------------------------------------------------------------------- name pools
FIRST = ["Olena", "Andriy", "Iryna", "Serhii", "Oksana", "Dmytro", "Natalia", "Oleksandr",
         "Yulia", "Mykola", "Tetiana", "Vasyl", "Kateryna", "Ihor", "Svitlana", "Bohdan",
         "Halyna", "Roman", "Maryna", "Taras", "Liudmyla", "Yurii", "Viktoriia", "Pavlo",
         "Anastasiia", "Volodymyr", "Inna", "Maksym", "Larysa", "Artem", "Alla", "Vitalii",
         "Nadiia", "Denys", "Valentyna", "Ruslan", "Khrystyna", "Oleh", "Daryna", "Yevhen",
         "Zoriana", "Stanislav", "Lesia", "Hennadii", "Sofiia", "Anatolii", "Vira", "Kostiantyn"]
LAST = ["Koval", "Bondarenko", "Tkachenko", "Melnyk", "Shevchenko", "Kravchenko", "Boyko",
        "Kovalenko", "Oliinyk", "Lysenko", "Moroz", "Savchenko", "Rudenko", "Marchenko",
        "Petrenko", "Klymenko", "Pavlenko", "Ponomarenko", "Levchenko", "Kharchenko",
        "Zinchenko", "Hnatiuk", "Sydorenko", "Romaniuk", "Tymoshenko", "Yakovenko",
        "Honcharenko", "Kuzmenko", "Prykhodko", "Danylenko", "Vlasenko", "Babenko",
        "Fedorenko", "Hrytsenko", "Ostapenko", "Karpenko", "Bilyk", "Polishchuk",
        "Lytvynenko", "Demchenko", "Kyrylenko", "Nesterenko", "Mazur", "Zhuk", "Kostenko",
        "Herasymenko", "Bilous", "Vovk", "Dovhan", "Panchenko"]
CITIES = ["Dnipro", "Dnipro", "Dnipro", "Kyiv", "Kyiv", "Kharkiv", "Zaporizhzhia", "Kryvyi Rih",
          "Kamianske", "Poltava", "Lviv", "Odesa", "Vinnytsia", "Cherkasy", "Kropyvnytskyi",
          "Nikopol", "Pavlohrad", "Bila Tserkva", "Kremenchuk", "Zhytomyr"]

# location key -> (OU path below OU=ATB, city, office name, phone prefix)
LOCS = {
    "hq": ("OU=Head Office", "Dnipro", "Head Office, 15 Kalynova St, Dnipro", "+380 56 790"),
    "kyiv": ("OU=Kyiv Office", "Kyiv", "Kyiv Office, 7 Zhylianska St", "+380 44 593"),
    "dc": ("OU=Distribution Centers", "Dnipro", "DC-1 Dnipro (Novooleksandrivka)", "+380 56 372"),
}

# department -> (location, size, head title, [titles])
DEPTS = {
    "Executive Board": ("hq", 6, "Chief Executive Officer",
                        ["Chief Financial Officer", "Chief Operating Officer", "Chief Information Officer",
                         "Chief Commercial Officer", "Executive Assistant"]),
    "Finance": ("hq", 44, "Finance Director", ["Financial Analyst", "Senior Financial Analyst",
                "Treasury Specialist", "Budget Controller", "Head of FP&A"]),
    "Accounting": ("hq", 36, "Chief Accountant", ["Accountant", "Senior Accountant",
                   "Payroll Accountant", "Tax Specialist", "AP Specialist"]),
    "Human Resources": ("hq", 28, "HR Director", ["HR Business Partner", "Recruiter",
                        "HR Generalist", "Compensation & Benefits Specialist", "Training Coordinator"]),
    "IT": ("hq", 54, "IT Director", ["System Administrator", "Senior System Administrator",
           "Network Engineer", "1C Developer", "Service Desk Engineer", "DBA",
           "DevOps Engineer", "Software Developer", "Head of Infrastructure"]),
    "Information Security": ("hq", 9, "CISO", ["Security Analyst", "Security Engineer",
                             "Head of SOC"]),
    "Logistics": ("dc", 52, "Logistics Director", ["Logistics Coordinator", "Warehouse Supervisor",
                  "Transport Planner", "Fleet Manager", "Inventory Controller", "Dispatcher"]),
    "Purchasing": ("hq", 40, "Purchasing Director", ["Category Manager", "Buyer",
                   "Senior Buyer", "Supplier Quality Specialist", "Pricing Analyst"]),
    "Marketing": ("kyiv", 27, "Marketing Director", ["Brand Manager", "Marketing Specialist",
                  "CRM Analyst", "Loyalty Programme Manager", "Designer"]),
    "E-commerce": ("kyiv", 24, "Head of E-commerce", ["Product Manager", "Mobile Developer",
                   "QA Engineer", "UX Designer", "Data Analyst"]),
    "Legal": ("hq", 12, "General Counsel", ["Lawyer", "Senior Lawyer", "Compliance Officer"]),
    "Retail Operations": ("hq", 44, "Retail Operations Director", ["Regional Manager",
                          "Area Manager", "Operations Analyst", "Planogram Specialist"]),
    "Internal Audit": ("hq", 10, "Head of Internal Audit", ["Internal Auditor", "Senior Internal Auditor"]),
    "Facilities": ("hq", 14, "Facilities Manager", ["Facilities Engineer", "Energy Engineer",
                   "Maintenance Coordinator"]),
    "Store Development": ("hq", 16, "Store Development Director", ["Construction Project Manager",
                          "Real Estate Manager", "Architect"]),
}

FIXED = {  # continuity with earlier directory samples
    "o.koval": ("Olha", "Koval", "Finance", "Head of FP&A"),
    "a.bondarenko": ("Andriy", "Bondarenko", "IT", "Head of Infrastructure"),
    "i.tkachenko": ("Iryna", "Tkachenko", "Human Resources", "HR Business Partner"),
    "s.melnyk": ("Serhii", "Melnyk", "Logistics", "Warehouse Supervisor"),
}

STAFF_TITLES = (["Store Manager", "Deputy Store Manager", "Senior Cashier", "Senior Cashier"]
                + ["Cashier"] * 27 + ["Sales Assistant"] * 15 + ["Merchandiser"] * 4
                + ["Baker"] * 3 + ["Security Guard"] * 2)
STAFF_PER_STORE = len(STAFF_TITLES)  # 55

# --------------------------------------------------------------------------- directory build
OBJ = []          # static objects (dicts)
BY_DN = {}        # dn.lower() -> index
BY_SAM = {}       # sam.lower() -> index
BY_UPN = {}
GROUPS = {}       # cn -> index
_rid = [1100]


def _next_rid():
    _rid[0] += 1
    return _rid[0]


def _guid(seed):
    return str(uuid.UUID(hashlib.md5(("guid:" + seed).encode()).hexdigest()))


def add(o):
    o.setdefault("objectGUID", _guid(o["distinguishedName"]))
    BY_DN[o["distinguishedName"].lower()] = len(OBJ)
    if "sAMAccountName" in o:
        BY_SAM[o["sAMAccountName"].lower()] = len(OBJ)
    if "userPrincipalName" in o:
        BY_UPN[o["userPrincipalName"].lower()] = len(OBJ)
    OBJ.append(o)
    return o


def container(dn, cls="organizationalUnit", desc=None, created=1262304000):
    name = dn.split(",", 1)[0].split("=", 1)[1]
    o = {"distinguishedName": dn,
         "objectClass": ["top", cls] if cls != "domainDNS" else ["top", "domain", "domainDNS"],
         "objectCategory": f"CN={'Organizational-Unit' if cls == 'organizationalUnit' else 'Container' if cls == 'container' else 'Domain-DNS'},{SCHEMA}",
         ("ou" if cls == "organizationalUnit" else "dc" if cls == "domainDNS" else "cn"): name,
         "name": name, "whenCreated": gentime(created), "whenChanged": gentime(NOW - 86400 * 40)}
    if desc:
        o["description"] = desc
    return add(o)


def group(cn, parent, desc, gtype="-2147483646", rid=None, builtin=False):
    dn = f"CN={cn},{parent}"
    o = {"distinguishedName": dn, "objectClass": ["top", "group"],
         "objectCategory": f"CN=Group,{SCHEMA}", "cn": cn, "name": cn,
         "sAMAccountName": cn, "description": desc, "groupType": gtype,
         "objectSid": f"{DOMAIN_SID}-{rid or _next_rid()}" if not builtin else f"S-1-5-32-{rid}",
         "member": [], "memberOf": [],
         "whenCreated": gentime(1262304000 if builtin or rid else 1420070400 + (int(hashlib.md5(cn.encode()).hexdigest(), 16) % 300) * 86400),
         "whenChanged": gentime(NOW - 86400 * (5 + len(cn) % 60))}
    add(o)
    GROUPS[cn] = BY_DN[dn.lower()]
    return o


def gdn(cn):
    return OBJ[GROUPS[cn]]["distinguishedName"]


def join(user, *gcns):
    for cn in gcns:
        g = OBJ[GROUPS[cn]]
        if user["distinguishedName"] not in g["member"]:
            g["member"].append(user["distinguishedName"])
            user.setdefault("memberOf", []).append(g["distinguishedName"])


def _build():
    r = random.Random(20260309)
    container(BASE_DN, "domainDNS", created=1199145600)
    for c, d in [("Users", "Default container for upgraded user accounts"),
                 ("Computers", "Default container for upgraded computer accounts"),
                 ("Builtin", None), ("Managed Service Accounts", "Default container for managed service accounts"),
                 ("System", "Builtin system settings")]:
        container(f"CN={c},{BASE_DN}", "container", d, created=1199145600)
    container(f"OU=Domain Controllers,{BASE_DN}", desc="Default container for domain controllers", created=1199145600)
    container(ROOT_OU, desc="ATB-Market LLC")
    for loc in ("OU=Head Office", "OU=Kyiv Office", "OU=Distribution Centers"):
        container(f"{loc},{ROOT_OU}")
        container(f"OU=Users,{loc},{ROOT_OU}")
        container(f"OU=Workstations,{loc},{ROOT_OU}")
    container(f"OU=Stores,{ROOT_OU}", desc="Retail network")
    container(f"OU=Store Staff,OU=Stores,{ROOT_OU}", desc="Store personnel accounts (HR sync, nightly)")
    container(f"OU=Servers,{ROOT_OU}", desc="Member servers")
    container(f"OU=Groups,{ROOT_OU}", desc="Security and distribution groups")
    container(f"OU=Service Accounts,{ROOT_OU}", desc="Non-personal accounts. Owner required in 'info'.")
    container(f"OU=Admin Accounts,{ROOT_OU}", desc="Tier-0/1 privileged accounts")
    container(f"OU=Disabled Users,{ROOT_OU}", desc="Leavers - kept 180 days")

    users_c = f"CN=Users,{BASE_DN}"
    builtin_c = f"CN=Builtin,{BASE_DN}"
    for cn, rid, desc in [("Domain Admins", 512, "Designated administrators of the domain"),
                          ("Domain Users", 513, "All domain users"),
                          ("Domain Guests", 514, "All domain guests"),
                          ("Domain Computers", 515, "All workstations and servers joined to the domain"),
                          ("Domain Controllers", 516, "All domain controllers in the domain"),
                          ("Schema Admins", 518, "Designated administrators of the schema"),
                          ("Enterprise Admins", 519, "Designated administrators of the enterprise"),
                          ("Group Policy Creator Owners", 520, "Members in this group can modify group policy for the domain"),
                          ("Protected Users", 525, "Members of this group are afforded additional protections against authentication security threats"),
                          ("DnsAdmins", 1101, "DNS Administrators Group")]:
        group(cn, users_c, desc, rid=rid,
              gtype="-2147483640" if cn in ("Schema Admins", "Enterprise Admins") else "-2147483646")
    for cn, rid, desc in [("Administrators", 544, "Administrators have complete and unrestricted access to the computer/domain"),
                          ("Account Operators", 548, "Members can administer domain user and group accounts"),
                          ("Server Operators", 549, "Members can administer domain servers"),
                          ("Backup Operators", 551, "Backup Operators can override security restrictions for the sole purpose of backing up or restoring files"),
                          ("Print Operators", 550, "Members can administer printers installed on domain controllers"),
                          ("Remote Desktop Users", 555, "Members in this group are granted the right to logon remotely")]:
        group(cn, builtin_c, desc, gtype="-2147483643", rid=rid, builtin=True)

    gou = f"OU=Groups,{ROOT_OU}"
    for dept in DEPTS:
        group("GG_" + dept.replace(" ", "_").replace("&", "and"), gou, f"{dept} department (all staff)")
    for cn, desc in [("IT Admins", "Server and infrastructure administrators"),
                     ("Helpdesk", "Service Desk - password resets, workstation support"),
                     ("VPN Users", "Remote access (FortiClient)"),
                     ("RDP-Servers", "RDP to member servers"),
                     ("SQL Admins", "sysadmin on SQL-1C-01 / SQL-BI-01"),
                     ("Exchange Mailbox Admins", "Mailbox management"),
                     ("Monitoring Operators", "Zabbix / Grafana operators"),
                     ("GitLab Developers", "Developer access to source control"),
                     ("1C Users", "1C:Enterprise ERP users"),
                     ("Oracle EBS Users", "Oracle EBS / supplier portal back office"),
                     ("BI Readers", "Power BI / reports read access"),
                     ("Wi-Fi Corp", "802.1X corporate Wi-Fi"),
                     ("Wi-Fi Stores", "802.1X store Wi-Fi (handhelds)"),
                     ("LDAP Readers", "Applications allowed to bind and read the directory"),
                     ("Service Accounts", "All non-personal accounts"),
                     ("GG_Store_Staff", "All store personnel (HR sync)"),
                     ("GG_Store_Managers", "Store managers and deputies (HR sync)"),
                     ("Regional Managers", "Retail regional/area managers"),
                     ("Finance-Approvers", "Payment approval in 1C"),
                     ("HR-Confidential", "Access to \\\\FS-01\\HR$"),
                     ("Remote Workers", "Home-office policy GPO-RemoteWork"),
                     ("Printers-HQ", "Printer deployment GPO - Head Office"),
                     ("DL_All_HQ", "Distribution list - all Head Office"),
                     ("DL_IT_Announcements", "Distribution list - IT announcements")]:
        group(cn, gou, desc, gtype="2" if cn.startswith("DL_") else "-2147483646")

    # built-in accounts
    def account(cn, sam, parent, uac=512, desc=None, created=1199145600, last=None, pls=None, **kw):
        dn = f"CN={cn},{parent}"
        o = {"distinguishedName": dn, "objectClass": ["top", "person", "organizationalPerson", "user"],
             "objectCategory": f"CN=Person,{SCHEMA}", "cn": cn, "name": cn, "displayName": cn,
             "sAMAccountName": sam, "userPrincipalName": f"{sam}@{DOMAIN}",
             "objectSid": f"{DOMAIN_SID}-{kw.pop('rid', None) or _next_rid()}",
             "userAccountControl": str(uac), "primaryGroupID": "513",
             "whenCreated": gentime(created), "whenChanged": gentime(NOW - r.randint(1, 90) * 86400),
             "pwdLastSet": filetime(pls if pls is not None else NOW - r.randint(5, 85) * 86400),
             "lastLogonTimestamp": filetime(last if last is not None else NOW - r.randint(600, 6 * 86400)),
             "badPwdCount": "0", "logonCount": str(r.randint(40, 4000)),
             "accountExpires": "9223372036854775807", "memberOf": []}
        if desc:
            o["description"] = desc
        o.update(kw)
        return add(o)

    adm = account("Administrator", "Administrator", users_c, 66048, rid=500,
                  desc="Built-in account for administering the computer/domain",
                  pls=NOW - 1400 * 86400, last=NOW - 92 * 86400)
    join(adm, "Domain Admins", "Enterprise Admins", "Schema Admins", "Administrators", "Group Policy Creator Owners")
    account("Guest", "Guest", users_c, 66082, rid=501, desc="Built-in account for guest access to the computer/domain",
            pls=0, last=0, logonCount="0")
    account("krbtgt", "krbtgt", users_c, 514, rid=502, desc="Key Distribution Center Service Account",
            pls=NOW - 2190 * 86400, last=0, logonCount="0")

    # office staff
    used = set()

    def mk_sam(first, last):
        base = f"{first[0]}.{last}".lower()
        sam, n = base, 1
        while sam in used:
            n += 1
            sam = f"{base}{n}"
        used.add(sam)
        return sam

    for s in FIXED:
        used.add(s)
    people = []
    for dept, (loc, size, head_title, titles) in DEPTS.items():
        ou, city, office, pref = LOCS[loc]
        members = []
        for i in range(size):
            fixed = next((k for k, v in FIXED.items() if v[2] == dept and i == list(FIXED).index(k) + 3), None)
            if fixed:
                first, last, _, title = FIXED[fixed]
                sam = fixed
            else:
                first, last = r.choice(FIRST), r.choice(LAST)
                sam = mk_sam(first, last)
                title = head_title if i == 0 else r.choice(titles)
            if dept == "Executive Board" and 0 < i < 5:
                title = titles[i - 1]
            this_ou, this_office, this_pref = ou, office, pref
            if dept in ("Marketing", "E-commerce", "IT") and r.random() < .25:
                this_ou, this_office, this_pref = LOCS["kyiv"][0], LOCS["kyiv"][2], LOCS["kyiv"][3]
            cn = f"{first} {last}"
            if f"cn={cn},ou=users,{this_ou},{ROOT_OU}".lower() in BY_DN:
                cn = f"{first} {last} ({sam})"
            created = 1293840000 + r.randint(0, 4900) * 86400
            ext = r.randint(1000, 9899)
            u = account(cn, sam, f"OU=Users,{this_ou},{ROOT_OU}", created=created,
                        givenName=first, sn=last, title=title, department=dept,
                        company="ATB-Market LLC", physicalDeliveryOfficeName=this_office,
                        l="Kyiv" if "Kyiv" in this_office else city, co="Ukraine", c="UA",
                        mail=f"{sam}@{DOMAIN}", telephoneNumber=f"{this_pref} {ext}",
                        ipPhone=str(ext),
                        mobile=f"+380 {r.choice(['50', '63', '66', '67', '68', '73', '93', '95', '97', '98', '99'])} "
                               f"{r.randint(100, 999)} {r.randint(10, 99)} {r.randint(10, 99)}",
                        employeeID=str(100000 + len(people) * 7 + r.randint(0, 6)),
                        directReports=[])
            u["displayName"] = f"{last} {first}"
            if r.random() < .08:
                u["userAccountControl"] = "66048"
            members.append(u)
            people.append(u)
            join(u, "GG_" + dept.replace(" ", "_").replace("&", "and"), "1C Users", "Wi-Fi Corp")
            if "Kyiv" not in this_office and r.random() < .3:
                join(u, "Printers-HQ", "DL_All_HQ")
            if r.random() < .35:
                join(u, "VPN Users")
            if r.random() < .15:
                join(u, "Remote Workers")
        head = members[0]
        leads = [m for m in members[1:] if any(w in m["title"] for w in ("Head", "Senior", "Chief", "Manager", "Director"))][:4]
        for m in members[1:]:
            boss = head if (m in leads or not leads) else r.choice(leads)
            m["manager"] = boss["distinguishedName"]
            boss["directReports"].append(m["distinguishedName"])
        DEPTS[dept] = DEPTS[dept] + (head,)
    ceo = DEPTS["Executive Board"][-1]
    for dept, v in DEPTS.items():
        if dept != "Executive Board":
            v[-1]["manager"] = ceo["distinguishedName"]
            ceo["directReports"].append(v[-1]["distinguishedName"])
    for p in people:
        d = p["department"]
        if d == "IT":
            join(p, "GitLab Developers" if "Developer" in p["title"] or "DevOps" in p["title"] else "Helpdesk"
                 if "Service Desk" in p["title"] else "IT Admins")
            if "DBA" in p["title"]:
                join(p, "SQL Admins")
            if "Administrator" in p["title"] or "Infrastructure" in p["title"]:
                join(p, "RDP-Servers", "Monitoring Operators")
        if d == "E-commerce" and ("Developer" in p["title"] or "QA" in p["title"]):
            join(p, "GitLab Developers")
        if d in ("Finance", "Accounting", "Executive Board") and r.random() < .3:
            join(p, "Finance-Approvers")
        if d == "Human Resources":
            join(p, "HR-Confidential")
        if d == "Purchasing":
            join(p, "Oracle EBS Users")
        if d == "Retail Operations" and "Manager" in p["title"]:
            join(p, "Regional Managers")
        if d in ("Finance", "Marketing", "Retail Operations", "Executive Board") and r.random() < .5:
            join(p, "BI Readers")
        if d == "IT" and r.random() < .5:
            join(p, "DL_IT_Announcements")
    join(next(p for p in people if p["sAMAccountName"] == "a.bondarenko"), "Domain Admins", "Exchange Mailbox Admins")

    # privileged admin accounts (tiering)
    for p in [p for p in people if p["department"] == "IT" and
              ("Administrator" in p["title"] or "Infrastructure" in p["title"])][:6]:
        a = account(f"ADM {p['sn']} {p['givenName']}", "adm." + p["sAMAccountName"],
                    f"OU=Admin Accounts,{ROOT_OU}", 512, desc=f"Privileged account of {p['displayName']}",
                    givenName=p["givenName"], sn=p["sn"], department="IT", title="Administrative account",
                    manager=p.get("manager"))
        join(a, "IT Admins", "RDP-Servers", "Protected Users")
        if r.random() < .5 or p["sAMAccountName"] == "a.bondarenko":
            join(a, "Domain Admins")
        else:
            join(a, "Server Operators")

    # service accounts
    sa_ou = f"OU=Service Accounts,{ROOT_OU}"
    for cn, sam, desc, groups, spn, pls_days in [
        ("Education Service", "education", "Moodle LMS (education.atbmarket.com) - LDAP auth and user sync",
         ["LDAP Readers"], None, 2400),
        ("svc_exchange", "svc_exchange", "Exchange hybrid / journaling", ["Exchange Mailbox Admins"], None, 900),
        ("svc_sql1c", "svc_sql1c", "SQL Server service - SQL-1C-01", [],
         ["MSSQLSvc/sql-1c-01.atbmarket.com:1433", "MSSQLSvc/sql-1c-01.atbmarket.com"], 1650),
        ("svc_sqlbi", "svc_sqlbi", "SQL Server + SSRS - SQL-BI-01", [],
         ["MSSQLSvc/sql-bi-01.atbmarket.com:1433", "HTTP/reports.atbmarket.com"], 1100),
        ("svc_backup", "svc_backup", "Veeam B&R service account", ["Backup Operators"], None, 760),
        ("svc_scan", "svc_scan", "MFP scan-to-folder (\\\\FS-01\\Scans)", [], None, 2900),
        ("svc_crm", "svc_crm", "Supplier portal (SuiteCRM) LDAP lookup", ["LDAP Readers"], None, 1300),
        ("svc_1c", "svc_1c", "1C:Enterprise server agent", [], ["1C/app-1c-01.atbmarket.com"], 1500),
        ("svc_monitoring", "svc_monitoring", "Zabbix WMI/LDAP checks", ["Monitoring Operators", "LDAP Readers"],
         None, 640),
        ("svc_wsus", "svc_wsus", "WSUS / SCCM client push", [], None, 1210),
        ("svc_printers", "svc_printers", "PaperCut print management", ["Print Operators"], None, 990),
        ("svc_hrsync", "svc_hrsync", "HR -> AD nightly sync (store staff provisioning)", ["Account Operators"],
         None, 410),
    ]:
        kw = {"department": "Service Accounts", "info": "Owner: IT Infrastructure"}
        if spn:
            kw["servicePrincipalName"] = spn
        s = account(cn, sam, sa_ou, 66048, desc=desc, created=1356998400 + len(cn) * 86400 * 30,
                    pls=NOW - pls_days * 86400, **kw)
        if sam == "education":
            s["mail"] = VALID_DN
            s["info"] = "Owner: HR / Training. Ticket SD-20114"
            s["lastLogonTimestamp"] = filetime(NOW - 1800)
            s["logonCount"] = "48713"
        join(s, "Service Accounts", *groups)

    # leavers
    dis_ou = f"OU=Disabled Users,{ROOT_OU}"
    for i in range(24):
        first, last = r.choice(FIRST), r.choice(LAST)
        sam = mk_sam(first, last)
        left = NOW - r.randint(5, 175) * 86400
        dept = r.choice(list(DEPTS))
        u = account(f"{first} {last}", sam, dis_ou, 514, created=left - r.randint(300, 3000) * 86400,
                    desc=f"Left {datetime.fromtimestamp(left, timezone.utc):%Y-%m-%d} / HR-{r.randint(4000, 6999)}",
                    pls=left - r.randint(10, 80) * 86400, last=left - r.randint(1, 5) * 86400,
                    givenName=first, sn=last, department=dept, title=r.choice(DEPTS[dept][3]),
                    company="ATB-Market LLC", mail=f"{sam}@{DOMAIN}")
        u["displayName"] = f"{last} {first}"

    # computers
    def computer(name, parent, os_, ver, desc=None, uac=4096, managed=None, last=None, created=None):
        dn = f"CN={name},{parent}"
        o = {"distinguishedName": dn,
             "objectClass": ["top", "person", "organizationalPerson", "user", "computer"],
             "objectCategory": f"CN=Computer,{SCHEMA}", "cn": name, "name": name,
             "sAMAccountName": name + "$", "dNSHostName": f"{name.lower()}.{DOMAIN}",
             "objectSid": f"{DOMAIN_SID}-{_next_rid()}", "userAccountControl": str(uac),
             "primaryGroupID": "516" if uac == 532480 else "515",
             "operatingSystem": os_, "operatingSystemVersion": ver,
             "whenCreated": gentime(created or NOW - r.randint(60, 2500) * 86400),
             "whenChanged": gentime(NOW - r.randint(0, 20) * 86400),
             "lastLogonTimestamp": filetime(last if last is not None else NOW - r.randint(1800, 12 * 86400)),
             "pwdLastSet": filetime(NOW - r.randint(1, 29) * 86400), "memberOf": []}
        if desc:
            o["description"] = desc
        if managed:
            o["managedBy"] = managed
        return add(o)

    dcs = f"OU=Domain Controllers,{BASE_DN}"
    for name, desc in [("DC-MAIN-01", "PDC emulator / RID master - Dnipro HQ"),
                       ("DC-MAIN-02", "Dnipro HQ - GC"), ("DC-KYV-01", "Kyiv office - GC, DNS")]:
        computer(name, dcs, "Windows Server 2016 Standard", "10.0 (14393)", desc, uac=532480,
                 created=1199145600 if name == "DC-MAIN-01" else None)
    srv = f"OU=Servers,{ROOT_OU}"
    for name, os_, ver, desc in [
        ("EXCH-MBX-01", "Windows Server 2016 Standard", "10.0 (14393)", "Exchange 2016 Mailbox (DAG01)"),
        ("EXCH-MBX-02", "Windows Server 2016 Standard", "10.0 (14393)", "Exchange 2016 Mailbox (DAG01)"),
        ("EXCH-EDGE-01", "Windows Server 2016 Standard", "10.0 (14393)", "Exchange Edge - DMZ"),
        ("FS-01", "Windows Server 2019 Standard", "10.0 (17763)", "File server - HQ shares"),
        ("FS-02", "Windows Server 2019 Standard", "10.0 (17763)", "File server - DFS replica"),
        ("PRINT-01", "Windows Server 2019 Standard", "10.0 (17763)", "Print server / PaperCut"),
        ("SQL-1C-01", "Windows Server 2019 Standard", "10.0 (17763)", "SQL Server 2017 - 1C databases"),
        ("SQL-BI-01", "Windows Server 2019 Standard", "10.0 (17763)", "SQL Server 2019 - DWH / SSRS"),
        ("APP-1C-01", "Windows Server 2019 Standard", "10.0 (17763)", "1C:Enterprise 8.3 application server"),
        ("APP-1C-02", "Windows Server 2019 Standard", "10.0 (17763)", "1C:Enterprise 8.3 application server"),
        ("RDS-01", "Windows Server 2019 Datacenter", "10.0 (17763)", "RD Session Host - 1C clients"),
        ("RDS-02", "Windows Server 2019 Datacenter", "10.0 (17763)", "RD Session Host - 1C clients"),
        ("RDS-03", "Windows Server 2019 Datacenter", "10.0 (17763)", "RD Session Host - finance"),
        ("RDGW-01", "Windows Server 2019 Standard", "10.0 (17763)", "RD Gateway"),
        ("WSUS-01", "Windows Server 2016 Standard", "10.0 (14393)", "WSUS"),
        ("SCCM-01", "Windows Server 2019 Standard", "10.0 (17763)", "SCCM primary site ATB"),
        ("VEEAM-01", "Windows Server 2019 Standard", "10.0 (17763)", "Veeam Backup & Replication"),
        ("CA-01", "Windows Server 2016 Standard", "10.0 (14393)", "Enterprise issuing CA (ATBMARKET-CA)"),
        ("ADFS-01", "Windows Server 2019 Standard", "10.0 (17763)", "AD FS"),
        ("NPS-01", "Windows Server 2019 Standard", "10.0 (17763)", "RADIUS for Wi-Fi Corp/Stores"),
        ("KMS-01", "Windows Server 2012 R2 Standard", "6.3 (9600)", "KMS host"),
        ("HYPERV-01", "Windows Server 2019 Datacenter", "10.0 (17763)", "Hyper-V cluster node"),
        ("HYPERV-02", "Windows Server 2019 Datacenter", "10.0 (17763)", "Hyper-V cluster node"),
        ("HYPERV-03", "Windows Server 2019 Datacenter", "10.0 (17763)", "Hyper-V cluster node"),
        ("POS-MGMT-01", "Windows Server 2016 Standard", "10.0 (14393)", "Store POS management (cash registers)"),
        ("OLDERP-01", "Windows Server 2008 R2 Standard", "6.1 (7601) Service Pack 1", "Legacy ERP - decommission Q4"),
    ]:
        computer(name, srv, os_, ver, desc)
    for loc_key, prefix, n in [("hq", "WS-DNP", 150), ("kyiv", "WS-KYV", 46), ("dc", "WS-DC1", 32)]:
        ou = f"OU=Workstations,{LOCS[loc_key][0]},{ROOT_OU}"
        loc_people = [p for p in people if LOCS[loc_key][2] == p.get("physicalDeliveryOfficeName")] or people
        for i in range(n):
            owner = r.choice(loc_people)
            win11 = r.random() < .45
            computer(f"{prefix}-{1000 + i * 3 + r.randint(0, 2):04d}", ou,
                     "Windows 11 Enterprise" if win11 else "Windows 10 Enterprise",
                     "10.0 (22631)" if win11 else r.choice(["10.0 (19045)", "10.0 (19045)", "10.0 (19044)"]),
                     f"{owner['displayName']} / inv. {r.randint(100000, 199999)}",
                     managed=owner["distinguishedName"])
    for i in range(34):
        owner = r.choice(people)
        computer(f"NB-{2000 + i * 7:04d}", f"OU=Workstations,OU=Head Office,{ROOT_OU}",
                 "Windows 11 Enterprise", "10.0 (22631)", f"Laptop - {owner['displayName']}",
                 managed=owner["distinguishedName"])


_build()
STATIC = len(OBJ)
STATIC_USERCLASS = sum(1 for o in OBJ if "user" in o["objectClass"])
LAZY = SEARCH_TOTAL - STATIC_USERCLASS
TOTAL = STATIC + LAZY
STAFF_OU = f"OU=Store Staff,OU=Stores,{ROOT_OU}"
STAFF_EMP_BASE = 300000
STAFF_GROUP_DN = gdn("GG_Store_Staff")
STAFFMGR_GROUP_DN = gdn("GG_Store_Managers")
WIFI_STORES_DN = gdn("Wi-Fi Stores")
_ADMIN_RID_BASE = _rid[0] + 1


@functools.lru_cache(maxsize=4096)
def staff(k):
    """Bulk store-staff account #k, generated on demand."""
    h = hashlib.blake2b(k.to_bytes(4, "big"), digest_size=12).digest()
    a, b, c = (int.from_bytes(h[i:i + 4], "big") for i in (0, 4, 8))
    first, last = FIRST[a % len(FIRST)], LAST[b % len(LAST)]
    store = k // STAFF_PER_STORE + 1
    title = STAFF_TITLES[k % STAFF_PER_STORE]
    emp = STAFF_EMP_BASE + k
    sam = f"e{emp}"
    cn = f"{first} {last} ({sam})"
    city = CITIES[(store * 7) % len(CITIES)]
    created = NOW - (c % 3000 + 20) * 86400
    disabled = (c >> 12) % 19 == 0
    pos = title in ("Cashier", "Senior Cashier", "Sales Assistant", "Baker", "Security Guard")
    last_logon = 0 if (pos and (c >> 5) % 4) else NOW - ((c >> 3) % (40 * 86400) + 600)
    member_of = [STAFF_GROUP_DN]
    if title in ("Store Manager", "Deputy Store Manager"):
        member_of += [STAFFMGR_GROUP_DN, WIFI_STORES_DN]
    o = {"distinguishedName": f"CN={cn},{STAFF_OU}",
         "objectClass": ["top", "person", "organizationalPerson", "user"],
         "objectCategory": f"CN=Person,{SCHEMA}", "cn": cn, "name": cn,
         "displayName": f"{last} {first}", "givenName": first, "sn": last,
         "sAMAccountName": sam, "userPrincipalName": f"{sam}@{DOMAIN}",
         "employeeID": str(emp), "title": title, "department": "Stores",
         "company": "ATB-Market LLC", "physicalDeliveryOfficeName": f"Store {store:04d}, {city}",
         "l": city, "co": "Ukraine", "c": "UA",
         "objectSid": f"{DOMAIN_SID}-{_ADMIN_RID_BASE + 5000 + k}",
         "objectGUID": str(uuid.UUID(bytes=h + h[:4])),
         "userAccountControl": "514" if disabled else "512", "primaryGroupID": "513",
         "whenCreated": gentime(created), "whenChanged": gentime(created + (a % 400) * 86400 if not disabled else NOW - (a % 90) * 86400),
         "pwdLastSet": filetime(max(created, NOW - (b % 200) * 86400)),
         "lastLogonTimestamp": filetime(last_logon), "badPwdCount": "0",
         "logonCount": str(0 if not last_logon else c % 900),
         "accountExpires": "9223372036854775807", "memberOf": member_of,
         "description": "HR sync" + (" - dismissed" if disabled else "")}
    if title in ("Store Manager", "Deputy Store Manager"):
        o["mail"] = f"store{store:04d}.{'manager' if title == 'Store Manager' else 'deputy'}@{DOMAIN}"
        o["telephoneNumber"] = f"+380 56 {700 + store % 200} {1000 + store:04d}"
    return o


def get(i):
    return OBJ[i] if i < STATIC else staff(i - STATIC)


_STAFF_RE = re.compile(r"^e(\d{6})$")


def find_sam(sam):
    s = (sam or "").lower().rstrip()
    if s in BY_SAM:
        return BY_SAM[s]
    m = _STAFF_RE.match(s)
    if m and 0 <= int(m.group(1)) - STAFF_EMP_BASE < LAZY:
        return STATIC + int(m.group(1)) - STAFF_EMP_BASE
    return None


def find_dn(dn):
    d = (dn or "").strip().lower()
    if d in BY_DN:
        return BY_DN[d]
    m = re.search(r"\(e(\d{6})\),ou=store staff,", d)
    if m and d.endswith(STAFF_OU.lower()):
        return find_sam("e" + m.group(1))
    return None


def is_user(o):
    return "user" in o["objectClass"] and "computer" not in o["objectClass"]


def is_computer(o):
    return "computer" in o["objectClass"]


def is_group(o):
    return "group" in o["objectClass"]


def cn_of(dn):
    return dn.split(",", 1)[0].split("=", 1)[1]


def parent_of(dn):
    return dn.split(",", 1)[1] if "," in dn else ""


# --------------------------------------------------------------------------- LDAP filter
class FilterError(ValueError):
    pass


def _unescape(v):
    return re.sub(r"\\([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), v)


def parse_filter(s):
    s = (s or "").strip()
    if not s:
        s = "(objectClass=*)"
    if not s.startswith("("):
        s = f"({s})"
    node, pos = _parse(s, 0)
    if pos != len(s):
        raise FilterError("trailing characters")
    return node


def _parse(s, i):
    if i >= len(s) or s[i] != "(":
        raise FilterError(f"expected '(' at {i}")
    i += 1
    if i < len(s) and s[i] in "&|":
        op = s[i]
        i += 1
        kids = []
        while i < len(s) and s[i] == "(":
            k, i = _parse(s, i)
            kids.append(k)
        if i >= len(s) or s[i] != ")":
            raise FilterError("unbalanced parentheses")
        return (op, kids), i + 1
    if i < len(s) and s[i] == "!":
        k, i = _parse(s, i + 1)
        if i >= len(s) or s[i] != ")":
            raise FilterError("unbalanced parentheses")
        return ("!", k), i + 1
    j = s.find(")", i)
    if j < 0:
        raise FilterError("unbalanced parentheses")
    item = s[i:j]
    m = re.match(r"^([A-Za-z0-9\-;.]+)(?::([0-9.]+))?:?(~=|>=|<=|=)(.*)$", item, re.S)
    if not m:
        raise FilterError(f"bad item '{item}'")
    attr, rule, op, val = m.groups()
    return ("item", attr, rule, op, val), j + 1


CANON = {}
for _o in OBJ[:200]:
    for _k in _o:
        CANON[_k.lower()] = _k
for _k in ["givenName", "sn", "title", "department", "mail", "manager", "directReports", "member",
           "memberOf", "telephoneNumber", "mobile", "employeeID", "servicePrincipalName",
           "operatingSystem", "operatingSystemVersion", "dNSHostName", "managedBy", "description",
           "physicalDeliveryOfficeName", "groupType", "info", "company", "l", "ipPhone", "ou", "dc"]:
    CANON[_k.lower()] = _k
CANON["objectclass"] = "objectClass"


def _vals(o, attr):
    a = CANON.get(attr.lower(), attr)
    v = o.get(a)
    if v is None:
        if a == "member" and is_group(o):
            return []
        return None
    return v if isinstance(v, list) else [v]


ANR_ATTRS = ("cn", "displayName", "givenName", "sn", "sAMAccountName", "mail", "userPrincipalName",
             "physicalDeliveryOfficeName")


def match(node, o):
    t = node[0]
    if t == "&":
        return all(match(k, o) for k in node[1])
    if t == "|":
        return any(match(k, o) for k in node[1])
    if t == "!":
        return not match(node[1], o)
    _, attr, rule, op, val = node
    al = attr.lower()
    if al == "anr":
        v = _unescape(val).strip().lower().rstrip("*")
        if not v:
            return False
        for a in ANR_ATTRS:
            for x in _vals(o, a) or []:
                xs = str(x).lower()
                if xs.startswith(v) or any(w.startswith(v) for w in xs.split()):
                    return True
        return False
    vals = _vals(o, attr)
    if op == "=" and val == "*" and not rule:
        return bool(vals)
    if not vals:
        return False
    if rule in ("1.2.840.113556.1.4.803", "1.2.840.113556.1.4.804"):
        try:
            bits = int(val)
            n = int(vals[0])
        except ValueError:
            return False
        return (n & bits) == bits if rule.endswith("803") else bool(n & bits)
    if al == "objectcategory" and "=" not in val:
        target = val.lower()
        target = {"person": "person", "user": "person", "computer": "computer", "group": "group",
                  "organizationalunit": "organizational-unit"}.get(target, target)
        return any(cn_of(x).lower() == target for x in vals)
    if rule == "1.2.840.113556.1.4.1941" and al == "memberof":
        rule = None  # chain match approximated by direct membership
    want = _unescape(val)
    if op in (">=", "<="):
        for x in vals:
            try:
                a, b = int(x), int(want)
            except ValueError:
                a, b = str(x).lower(), want.lower()
            if (a >= b) if op == ">=" else (a <= b):
                return True
        return False
    if "*" in want:
        parts = [re.escape(p.lower()) for p in want.split("*")]
        rx = re.compile("^" + ".*".join(parts) + "$", re.S)
        return any(rx.match(str(x).lower()) for x in vals)
    wl = want.lower()
    return any(str(x).lower() == wl for x in vals)


def _in_scope(dn, base, scope):
    d, b = dn.lower(), base.lower()
    if scope == "base":
        return d == b
    if scope == "one":
        return parent_of(d) == b
    return d == b or d.endswith("," + b) or b == ""


@functools.lru_cache(maxsize=64)
def run_search(base, scope, flt):
    node = parse_filter(flt)
    out = []
    b = base.lower()
    for i in range(STATIC):
        o = OBJ[i]
        if _in_scope(o["distinguishedName"], base, scope) and match(node, o):
            out.append(i)
    staff_dn = STAFF_OU.lower()
    lazy_ok = (scope == "sub" and (staff_dn == b or staff_dn.endswith("," + b) or b == "")) or \
              (scope == "one" and b == staff_dn)
    if lazy_ok and may_match_lazy(node):
        for k in range(LAZY):
            if match(node, staff(k) if k < 4096 else _staff_nocache(k)):
                out.append(STATIC + k)
    elif scope == "base" and find_dn(base) is not None and find_dn(base) >= STATIC:
        i = find_dn(base)
        if match(node, get(i)):
            out.append(i)
    return tuple(out)


_staff_nocache = staff.__wrapped__
LAZY_ATTRS = {k.lower() for k in staff(0)} | {k.lower() for k in staff(1)} | {"anr"}
LAZY_CLASSES = {"top", "person", "organizationalperson", "user", "*"}


def may_match_lazy(node):
    """Cheap pre-check so queries that can never hit store-staff accounts
    (computers, groups, SPNs, ...) skip the bulk scan."""
    t = node[0]
    if t == "&":
        return all(may_match_lazy(k) for k in node[1])
    if t == "|":
        return any(may_match_lazy(k) for k in node[1])
    if t == "!":
        return True
    _, attr, rule, op, val = node
    al = attr.lower()
    if al not in LAZY_ATTRS:
        return False
    if al == "objectclass" and op == "=" and val.lower() not in LAZY_CLASSES:
        return False
    if al == "objectcategory" and op == "=" and val.lower().split(",")[0].replace("cn=", "") not in ("person", "user", "*"):
        return False
    return True


# --------------------------------------------------------------------------- auth
def _basic_creds(hdr):
    if not hdr or not hdr.startswith("Basic "):
        return None
    try:
        raw = base64.b64decode(hdr.split(" ", 1)[1]).decode("utf-8", "replace")
        user, _, pw = raw.partition(":")
        return user, pw
    except Exception:
        return None


def _submitted_creds():
    """Pull (bind_dn, password) from form, json, or Basic auth header."""
    body = request.get_json(silent=True) or {}
    form = request.values or {}
    bind_dn = (form.get("bind_dn") or form.get("user") or form.get("username")
               or body.get("bind_dn") or body.get("user") or body.get("username"))
    password = form.get("password") or body.get("password")
    if bind_dn is None or password is None:
        creds = _basic_creds(request.headers.get("Authorization", ""))
        if creds:
            bind_dn = bind_dn if bind_dn is not None else creds[0]
            password = password if password is not None else creds[1]
    return (bind_dn or "").strip(), password or ""


def resolve_account(name):
    """UPN, DOMAIN\\sam, sam or full DN -> object index."""
    n = (name or "").strip()
    if not n:
        return None
    if "\\" in n:
        dom, _, n = n.partition("\\")
        if dom.upper() not in (NETBIOS, DOMAIN.upper()):
            return None
    if "=" in n and "," in n:
        return find_dn(n)
    if "@" in n:
        idx = BY_UPN.get(n.lower())
        if idx is None:
            idx = next((i for i, o in enumerate(OBJ) if o.get("mail", "").lower() == n.lower()), None)
        if idx is None and n.lower().endswith("@" + DOMAIN):
            idx = find_sam(n.split("@")[0])
        return idx
    return find_sam(n)


EDU_IDX = BY_SAM["education"]


def check_bind(name, password):
    """-> (ok, ldap_code, ad_data, idx)"""
    idx = resolve_account(name)
    if idx == EDU_IDX and password == VALID_PW:
        return True, 0, None, idx
    if idx is not None and int(get(idx).get("userAccountControl", "512")) & 2 and password:
        return False, 49, "533", idx
    return False, 49, "52e", idx


def ldap_err(code_data):
    return (f"80090308: LdapErr: DSID-0C09044E, comment: AcceptSecurityContext error, "
            f"data {code_data}, v4563")


def _authed():
    return session.get("bind_dn") == VALID_DN


# --------------------------------------------------------------------------- API
def _project(o, attrs):
    if attrs == ["1.1"]:
        return {}
    if not attrs or "*" in attrs:
        keys = list(o.keys())
    else:
        keys = [CANON.get(a.lower(), a) for a in attrs]
    out = {}
    for k in keys:
        if k in o and o[k] not in (None, []):
            v = o[k]
            if k == "member" and isinstance(v, list) and len(v) > 1500:
                out["member;range=0-1499"] = v[:1500]
                continue
            out[k] = v
        elif k == "member" and is_group(o):
            mem = group_member_dns(o, 0, 1500)
            if mem:
                out["member;range=0-1499" if group_member_count(o) > 1500 else "member"] = mem
    return out


def group_member_count(g):
    cn = g["cn"]
    if cn == "GG_Store_Staff":
        return LAZY
    if cn == "GG_Store_Managers":
        return 2 * ((LAZY + STAFF_PER_STORE - 1) // STAFF_PER_STORE)
    if cn == "Wi-Fi Stores":
        return 2 * ((LAZY + STAFF_PER_STORE - 1) // STAFF_PER_STORE) + len(g["member"])
    return len(g["member"])


def group_member_dns(g, start, n):
    cn = g["cn"]
    if cn == "GG_Store_Staff":
        return [staff(k)["distinguishedName"] for k in range(start, min(LAZY, start + n))]
    if cn in ("GG_Store_Managers", "Wi-Fi Stores"):
        ks = [s * STAFF_PER_STORE + j for s in range((LAZY + STAFF_PER_STORE - 1) // STAFF_PER_STORE)
              for j in (0, 1) if s * STAFF_PER_STORE + j < LAZY]
        dns = [staff(k)["distinguishedName"] for k in ks[start:start + n]]
        return (g["member"] + dns)[:n] if cn == "Wi-Fi Stores" and start == 0 else dns
    return g["member"][start:start + n]


def _pagecookie(key, off):
    return base64.b64encode(f"{hashlib.md5(key.encode()).hexdigest()[:8]}:{off}".encode()).decode()


def _uncookie(key, c):
    try:
        h, off = base64.b64decode(c).decode().split(":")
        if h != hashlib.md5(key.encode()).hexdigest()[:8]:
            return None
        return int(off)
    except Exception:
        return None


@app.post("/bind")
def bind():
    ip = atblog.client_ip(request)
    bind_dn, password = _submitted_creds()
    if not password:
        atblog.log("ad.bind_fail", ip, bind_dn=bind_dn, reason="anonymous")
        return jsonify(ok=False, result={"code": 49, "message": "invalidCredentials"},
                       error="invalid credentials (49)",
                       diagnosticMessage=ldap_err("52e")), 401
    ok, code, data, idx = check_bind(bind_dn, password)
    if ok:
        atblog.log("ad.bind_reused_creds", ip, bind_dn=bind_dn,
                   msg="LDAP bind with reused Moodle credentials")
        o = get(idx)
        return jsonify(ok=True, dn=VALID_DN, result={"code": 0, "message": "success"},
                       boundAs=o["distinguishedName"], whoami=f"u:{NETBIOS}\\{o['sAMAccountName']}",
                       server="DC-MAIN-01.atbmarket.com", defaultNamingContext=BASE_DN)
    atblog.log("ad.bind_fail", ip, bind_dn=bind_dn, data=data)
    return jsonify(ok=False, result={"code": code, "message": "invalidCredentials"},
                   error="invalid credentials (49)", diagnosticMessage=ldap_err(data)), 401


def root_dse():
    return {"currentTime": gentime(time.time()), "subschemaSubentry": f"CN=Aggregate,{SCHEMA}",
            "dsServiceName": f"CN=NTDS Settings,CN=DC-MAIN-01,CN=Servers,CN=Dnipro-HQ,CN=Sites,CN=Configuration,{BASE_DN}",
            "namingContexts": [BASE_DN, f"CN=Configuration,{BASE_DN}", SCHEMA,
                               f"DC=DomainDnsZones,{BASE_DN}", f"DC=ForestDnsZones,{BASE_DN}"],
            "defaultNamingContext": BASE_DN, "rootDomainNamingContext": BASE_DN,
            "configurationNamingContext": f"CN=Configuration,{BASE_DN}", "schemaNamingContext": SCHEMA,
            "supportedControl": ["1.2.840.113556.1.4.319", "1.2.840.113556.1.4.473",
                                 "1.2.840.113556.1.4.528", "1.2.840.113556.1.4.801",
                                 "1.2.840.113556.1.4.1339", "1.2.840.113556.1.4.1340"],
            "supportedLDAPVersion": ["3", "2"],
            "supportedLDAPPolicies": ["MaxPageSize", "MaxQueryDuration", "MaxResultSetSize"],
            "supportedSASLMechanisms": ["GSSAPI", "GSS-SPNEGO", "EXTERNAL", "DIGEST-MD5"],
            "dnsHostName": "DC-MAIN-01.atbmarket.com", "ldapServiceName": f"{DOMAIN}:dc-main-01$@{DOMAIN.upper()}",
            "serverName": f"CN=DC-MAIN-01,CN=Servers,CN=Dnipro-HQ,CN=Sites,CN=Configuration,{BASE_DN}",
            "isSynchronized": "TRUE", "isGlobalCatalogReady": "TRUE",
            "domainFunctionality": "7", "forestFunctionality": "7", "domainControllerFunctionality": "7",
            "highestCommittedUSN": str(41820000 + int(time.time()) % 100000)}


@app.get("/rootDSE")
@app.get("/rootdse")
def rootdse():
    atblog.log("ad.rootdse_read", atblog.client_ip(request))
    return jsonify(ok=True, dn="", attributes=root_dse())


@app.route("/search", methods=["GET", "POST"])
def search():
    ip = atblog.client_ip(request)
    if _authed() and not request.headers.get("Authorization") and "password" not in request.values:
        bind_dn = VALID_DN
    else:
        bind_dn, password = _submitted_creds()
        if not check_bind(bind_dn, password)[0]:
            atblog.log("ad.search_unauth", ip, bind_dn=bind_dn)
            return jsonify(ok=False, result={"code": 1, "message": "operationsError"},
                           error="invalid credentials (49)",
                           diagnosticMessage="000004DC: LdapErr: DSID-0C090A5C, comment: In order to perform "
                                             "this operation a successful bind must be completed on the "
                                             "connection., data 0, v4563"), 401
    body = request.get_json(silent=True) or {}
    def v(k, d=None):
        if k in request.values:
            return request.values.get(k)
        return body.get(k, d) if isinstance(body, dict) else d
    base = v("base", v("base_dn", BASE_DN)).strip()
    scope = (v("scope", "sub") or "sub").lower()
    scope = {"subtree": "sub", "2": "sub", "onelevel": "one", "1": "one", "0": "base"}.get(scope, scope)
    ldap_filter = v("filter") or ("(objectClass=*)" if scope == "base" else "(objectClass=user)")
    attrs = v("attributes") or v("attrs")
    if isinstance(attrs, str):
        attrs = [a.strip() for a in attrs.split(",") if a.strip()]
    if scope not in ("base", "one", "sub"):
        return jsonify(ok=False, result={"code": 2, "message": "protocolError"},
                       error="scope must be base, one or sub"), 400
    if base == "" and scope == "base":
        atblog.log("ad.rootdse_read", ip, bind_dn=bind_dn)
        return jsonify(ok=True, result={"code": 0, "message": "success"}, total=1, returned=1,
                       entries=[{"dn": "", "attributes": root_dse()}], cookie=None)
    if base and find_dn(base) is None:
        return jsonify(ok=False, result={"code": 32, "message": "noSuchObject"},
                       error="no such object",
                       diagnosticMessage=f"0000208D: NameErr: DSID-03100241, problem 2001 (NO_OBJECT), "
                                         f"data 0, best match of:\n\t'{BASE_DN}'"), 404
    try:
        hits = run_search(base, scope, ldap_filter)
    except FilterError as e:
        return jsonify(ok=False, result={"code": 87, "message": "filterError"},
                       error=f"bad search filter: {e}", filter=ldap_filter), 400
    try:
        page_size = int(v("page_size", v("pageSize", 0)) or 0)
        size_limit = int(v("size_limit", v("sizeLimit", 0)) or 0)
    except ValueError:
        return jsonify(ok=False, result={"code": 2, "message": "protocolError"},
                       error="page_size/size_limit must be integers"), 400
    key = f"{base}|{scope}|{ldap_filter}"
    off = 0
    if v("cookie"):
        off = _uncookie(key, v("cookie"))
        if off is None:
            return jsonify(ok=False, result={"code": 2, "message": "protocolError"},
                           error="invalid paged results cookie"), 400
    result = {"code": 0, "message": "success"}
    if page_size:
        n = min(page_size, MAX_PAGE)
        sel = hits[off:off + n]
        cookie = _pagecookie(key, off + n) if off + n < len(hits) else None
    else:
        lim = min(size_limit or MAX_PAGE, MAX_PAGE)
        sel = hits[:lim]
        cookie = None
        if len(hits) > lim:
            result = {"code": 4, "message": "sizeLimitExceeded"}
    entries = [{"dn": get(i)["distinguishedName"], "attributes": _project(get(i), attrs)} for i in sel]
    atblog.log("ad.search", ip, filter=ldap_filter, base=base, scope=scope, count=len(hits),
               returned=len(entries), paged=bool(page_size), bind_dn=bind_dn,
               msg="LDAP search returned directory")
    return jsonify(ok=True, result=result, base=base, scope=scope, filter=ldap_filter,
                   total=len(hits), returned=len(entries), cookie=cookie, entries=entries)


# --------------------------------------------------------------------------- portal UI
CSS = """
:root{--brand:#0b3d66;--brand2:#0d4b7f;--bg:#eef1f5;--card:#fff;--ink:#1f2733;--mute:#6b7684;--line:#e3e7ed;--ok:#1f7a3d;--bad:#a3221b}
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink);font-size:14px}
a{color:var(--brand)}.top{background:var(--brand);color:#fff;padding:10px 20px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.top .brand{font-weight:600;font-size:17px}.top .brand small{display:block;font-weight:400;opacity:.75;font-size:11px}
.top .sp{flex:1}.top a{color:#cfe3f5;text-decoration:none}.top form{margin:0}.top input{padding:7px 10px;border-radius:4px;border:0;width:240px}
.layout{display:flex;min-height:calc(100vh - 56px)}.side{width:210px;background:#fff;border-right:1px solid var(--line);padding:14px 0;flex:none}
.side a{display:block;padding:9px 20px;color:var(--ink);text-decoration:none}.side a:hover,.side a.on{background:#e8f0f8;color:var(--brand);font-weight:600}
.side .h{padding:12px 20px 4px;font-size:11px;text-transform:uppercase;color:var(--mute);letter-spacing:.5px}
.main{flex:1;padding:20px 24px 48px;min-width:0}.card{background:var(--card);border:1px solid #d7dde6;border-radius:6px;padding:18px;margin-bottom:16px}
h1{font-size:20px;margin:0 0 12px}h2{font-size:15px;margin:0 0 10px;color:var(--brand)}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--mute);background:#f7f9fb}tr:hover td{background:#f6f9fc}
.f{display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:12px}.f label{display:block;font-size:12px;color:var(--mute);margin-bottom:3px}
input,select{padding:8px 10px;border:1px solid #b9c2cf;border-radius:4px;font-size:14px;background:#fff;color:var(--ink)}
button,.btn{background:var(--brand);color:#fff;border:0;padding:9px 16px;border-radius:4px;font-size:14px;cursor:pointer;text-decoration:none;display:inline-block}
button:hover{background:var(--brand2)}.muted{color:var(--mute)}.small{font-size:12px}
.err{background:#fdecea;border:1px solid #f5c6c2;color:var(--bad);padding:10px 12px;border-radius:4px;margin-bottom:12px}
.okm{background:#e8f5ec;border:1px solid #b9dfc5;color:var(--ok);padding:10px 12px;border-radius:4px;margin-bottom:12px}
.kv{display:grid;grid-template-columns:190px 1fr;gap:0}.kv div{padding:7px 0;border-bottom:1px solid var(--line)}.kv .k{color:var(--mute);font-weight:600;font-size:13px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}
.stat{background:#f7f9fb;border:1px solid var(--line);border-radius:6px;padding:12px}.stat b{display:block;font-size:22px;color:var(--brand)}
.tag{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;background:#e8f0f8;color:var(--brand);margin:1px 2px}
.tag.red{background:#fdecea;color:var(--bad)}.tag.green{background:#e8f5ec;color:var(--ok)}
.pager{margin-top:12px;display:flex;gap:6px;align-items:center}.pager a{padding:5px 10px;border:1px solid var(--line);border-radius:4px;text-decoration:none;background:#fff}
ul.tree{list-style:none;padding-left:18px;margin:0;border-left:1px dotted #c9d1db}ul.tree li{padding:3px 0}
.login{max-width:420px;margin:60px auto}.login input{width:100%}.login label{display:block;font-weight:600;font-size:13px;margin:12px 0 4px}
.avatar{width:56px;height:56px;border-radius:50%;background:var(--brand);color:#fff;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:600;flex:none}
.head{display:flex;gap:14px;align-items:center;margin-bottom:14px}
@media(max-width:800px){.side{display:none}.grid2{grid-template-columns:1fr}.kv{grid-template-columns:1fr}.top input{width:150px}}
"""

NAV = [("home", "/home", "Home"), ("people", "/directory", "People"), ("groups", "/groups", "Groups"),
       ("ous", "/ous", "Organizational units"), ("computers", "/computers", "Computers"),
       ("me", "/me", "My account"), ("password", "/password", "Change password"), ("domain", "/domain", "Domain info")]


def page(title, body, active=None):
    if not _authed():
        return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
                "content=\"width=device-width, initial-scale=1\">"
                f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>"
                "<div class=\"top\"><div class=\"brand\">ATB Directory<small>DC-MAIN-01 &middot; atbmarket.com</small></div></div>"
                f"{body}</body></html>")
    me = get(EDU_IDX)
    side = "".join(
        (f'<div class="h">Self-service</div>' if key == "me" else "")
        + f'<a href="{href}" class="{"on" if key == active else ""}">{label}</a>' for key, href, label in NAV)
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            "content=\"width=device-width, initial-scale=1\">"
            f"<title>{html.escape(title)} - ATB Directory</title><style>{CSS}</style></head><body>"
            "<div class=\"top\"><div class=\"brand\">ATB Directory<small>DC-MAIN-01 &middot; atbmarket.com</small></div>"
            "<form action=\"/directory\"><input name=\"q\" placeholder=\"Find people (name, login, e-mail)\"></form>"
            f"<span class=\"sp\"></span><span>{html.escape(NETBIOS)}\\{html.escape(me['sAMAccountName'])}</span>"
            "<a href=\"/signout\">Sign out</a></div>"
            f"<div class=\"layout\"><nav class=\"side\"><div class=\"h\">Directory</div>{side}</nav>"
            f"<main class=\"main\">{body}</main></div></body></html>")


def esc(x):
    return html.escape(str(x)) if x is not None else ""


def link_dn(dn):
    i = find_dn(dn)
    if i is None:
        return esc(cn_of(dn) if "=" in dn else dn)
    o = get(i)
    if is_group(o):
        return f'<a href="/groups/{quote(o["cn"])}">{esc(o["cn"])}</a>'
    if is_computer(o):
        return f'<a href="/computers/{quote(o["cn"])}">{esc(o["cn"])}</a>'
    if is_user(o):
        return f'<a href="/directory/{quote(o["sAMAccountName"])}">{esc(o.get("displayName") or o["cn"])}</a>'
    return f'<a href="/directory?ou={quote(o["distinguishedName"])}">{esc(o["name"])}</a>'


def ou_path(dn):
    parts = [p.split("=", 1)[1] for p in dn.split(",") if p.upper().startswith(("OU=", "CN="))]
    return " / ".join(reversed(parts)) or DOMAIN


UAC_FLAGS = [(0x2, "ACCOUNTDISABLE"), (0x10, "LOCKOUT"), (0x20, "PASSWD_NOTREQD"),
             (0x200, "NORMAL_ACCOUNT"), (0x1000, "WORKSTATION_TRUST_ACCOUNT"),
             (0x2000, "SERVER_TRUST_ACCOUNT"), (0x10000, "DONT_EXPIRE_PASSWORD"),
             (0x80000, "TRUSTED_FOR_DELEGATION"), (0x400000, "DONT_REQ_PREAUTH")]


def uac_tags(v):
    v = int(v or 0)
    out = []
    for bit, name in UAC_FLAGS:
        if v & bit:
            cls = "red" if bit in (0x2, 0x10) else ""
            out.append(f'<span class="tag {cls}">{name}</span>')
    return "".join(out)


def status_tag(o):
    return ('<span class="tag red">Disabled</span>' if int(o.get("userAccountControl", 0)) & 2
            else '<span class="tag green">Enabled</span>')


def pager(total, pg, per, args):
    pages = max(1, (total + per - 1) // per)
    if pages == 1:
        return ""
    def u(p):
        a = dict(args)
        a["page"] = p
        return "?" + urlencode(a)
    s = f'<div class="pager"><span class="muted">Page {pg} of {pages:,}</span>'
    if pg > 1:
        s += f'<a href="{u(1)}">&laquo; First</a><a href="{u(pg - 1)}">&lsaquo; Prev</a>'
    if pg < pages:
        s += f'<a href="{u(pg + 1)}">Next &rsaquo;</a><a href="{u(pages)}">Last &raquo;</a>'
    return s + "</div>"


def _int(v, d=1):
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return d


def need_auth():
    if not _authed():
        return redirect(url_for("index", next=request.full_path))
    return None


@app.get("/")
def index():
    if _authed():
        return redirect("/home")
    err = request.args.get("err")
    msgs = {"1": "The user name or password is incorrect.",
            "2": "Your account has been disabled. Please contact the Service Desk.",
            "3": "Your session has expired. Please sign in again."}
    err_html = f'<div class="err">{msgs.get(err, msgs["1"])}</div>' if err else ""
    nxt = esc(request.args.get("next", ""))
    body = (f'<div class="login"><div class="card"><h1>Sign in</h1>'
            f'<p class="muted">Use your ATBMARKET domain account.</p>{err_html}'
            '<form method="post" action="/login">'
            f'<input type="hidden" name="next" value="{nxt}">'
            '<label for="u">User name</label><input type="text" id="u" name="bind_dn" '
            'placeholder="name@atbmarket.com or ATBMARKET\\name" autocomplete="username" autofocus>'
            '<label for="p">Password</label><input type="password" id="p" name="password" autocomplete="current-password">'
            '<div style="margin-top:16px"><button type="submit">Sign in</button></div></form></div>'
            '<p class="small muted" style="text-align:center">ATB-Market LLC &middot; IT Service Desk ext. 4357 &middot; '
            'servicedesk@atbmarket.com</p></div>')
    return page("Sign in - ATB Directory", body)


@app.post("/login")
def login():
    ip = atblog.client_ip(request)
    bind_dn, password = _submitted_creds()
    ok, code, data, idx = check_bind(bind_dn, password)
    if ok:
        atblog.log("ad.bind_reused_creds", ip, bind_dn=bind_dn, via="portal",
                   msg="LDAP bind with reused Moodle credentials")
        session["bind_dn"] = VALID_DN
        nxt = request.form.get("next") or ""
        return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/home")
    atblog.log("ad.bind_fail", ip, bind_dn=bind_dn, data=data, via="portal")
    return redirect(url_for("index", err=2 if data == "533" else 1))


@app.get("/signout")
def signout():
    session.pop("bind_dn", None)
    return redirect(url_for("index"))


def _counts():
    users = sum(1 for o in OBJ if is_user(o)) + LAZY
    disabled = sum(1 for o in OBJ if is_user(o) and int(o["userAccountControl"]) & 2)
    disabled += sum(1 for k in range(0, LAZY, 97) if staff(k)["userAccountControl"] == "514") * 97
    return {"users": users, "computers": sum(1 for o in OBJ if is_computer(o)),
            "groups": len(GROUPS), "ous": sum(1 for o in OBJ if "organizationalUnit" in o["objectClass"]),
            "disabled": disabled}


COUNTS = _counts()


@app.get("/home")
def home():
    deny = need_auth()
    if deny:
        return deny
    me = get(EDU_IDX)
    pls = from_filetime(me["pwdLastSet"])
    recent = sorted((o for o in OBJ if is_user(o) and "OU=Users" in o["distinguishedName"]),
                    key=lambda o: o["whenCreated"], reverse=True)[:8]
    rows = "".join(f"<tr><td>{link_dn(o['distinguishedName'])}</td><td>{esc(o.get('title'))}</td>"
                   f"<td>{esc(o.get('department'))}</td><td>{human(from_gentime(o['whenCreated']))[:10]}</td></tr>"
                   for o in recent)
    body = (f'<h1>Welcome, {esc(me["displayName"])}</h1>'
            '<div class="card"><h2>Directory at a glance</h2><div class="stats">'
            f'<div class="stat"><b>{COUNTS["users"]:,}</b>user accounts</div>'
            f'<div class="stat"><b>{COUNTS["computers"]:,}</b>computer accounts</div>'
            f'<div class="stat"><b>{COUNTS["groups"]:,}</b>groups</div>'
            f'<div class="stat"><b>{COUNTS["ous"]:,}</b>organizational units</div>'
            f'<div class="stat"><b>~{COUNTS["disabled"]:,}</b>disabled accounts</div></div></div>'
            '<div class="grid2"><div class="card"><h2>My account</h2><div class="kv">'
            f'<div class="k">Logon name</div><div>{NETBIOS}\\{esc(me["sAMAccountName"])}</div>'
            f'<div class="k">E-mail</div><div>{esc(me.get("mail"))}</div>'
            f'<div class="k">Password last set</div><div>{human(pls)}</div>'
            '<div class="k">Password expires</div><div>Never</div>'
            f'<div class="k">Groups</div><div>{"".join(link_dn(g) + "<br>" for g in me["memberOf"])}</div></div>'
            '<p><a href="/me">View full profile &rarr;</a></p></div>'
            '<div class="card"><h2>Notices</h2><ul class="small">'
            '<li>Password policy: 10+ characters, 3 of 4 character classes, max age 90 days.</li>'
            '<li>New starters are provisioned overnight from HR; store staff accounts appear in <i>Stores / Store Staff</i>.</li>'
            '<li>Lost access to e-mail or 1C? Service Desk ext. 4357.</li></ul></div></div>'
            f'<div class="card"><h2>Recently created office accounts</h2><table><thead><tr><th>Name</th>'
            f'<th>Title</th><th>Department</th><th>Created</th></tr></thead><tbody>{rows}</tbody></table></div>')
    return page("Home", body, "home")


def _people_filter(q, dept, title, ou, status):
    parts = ["(objectCategory=person)", "(objectClass=user)"]
    if q:
        parts.append(f"(anr={q})")
    if dept:
        parts.append(f"(department={dept})")
    if title:
        parts.append(f"(title=*{title}*)")
    if status == "enabled":
        parts.append("(!(userAccountControl:1.2.840.113556.1.4.803:=2))")
    elif status == "disabled":
        parts.append("(userAccountControl:1.2.840.113556.1.4.803:=2)")
    return "(&" + "".join(parts) + ")", (ou or BASE_DN)


ALL_DEPTS = sorted(set(list(DEPTS) + ["Stores", "Service Accounts"]))


@app.get("/directory")
def directory():
    deny = need_auth()
    if deny:
        return deny
    ip = atblog.client_ip(request)
    a = request.args
    q = (a.get("q") or "").strip().replace("(", "").replace(")", "")
    dept, title, ou, status = a.get("department", ""), (a.get("title") or "").strip(), a.get("ou", ""), a.get("status", "")
    flt, base = _people_filter(q, dept, title.replace("(", "").replace(")", ""), ou, status)
    if find_dn(base) is None:
        base = BASE_DN
    hits = run_search(base, "sub", flt)
    if q or dept or title or ou or status:
        atblog.log("ad.search", ip, filter=flt, base=base, scope="sub", count=len(hits),
                   via="portal", msg="LDAP search returned directory")
    per = 50
    pg = _int(a.get("page"))
    sel = hits[(pg - 1) * per: pg * per]
    rows = "".join(
        f"<tr><td>{link_dn(get(i)['distinguishedName'])}</td><td>{esc(get(i).get('sAMAccountName'))}</td>"
        f"<td>{esc(get(i).get('title'))}</td><td>{esc(get(i).get('department'))}</td>"
        f"<td>{esc(get(i).get('physicalDeliveryOfficeName') or ou_path(parent_of(get(i)['distinguishedName'])))}</td>"
        f"<td>{esc(get(i).get('telephoneNumber'))}</td><td>{status_tag(get(i))}</td></tr>" for i in sel)
    dopts = "".join(f'<option{" selected" if d == dept else ""}>{esc(d)}</option>' for d in ALL_DEPTS)
    ous = [o for o in OBJ if "organizationalUnit" in o["objectClass"] or o["distinguishedName"] == f"CN=Users,{BASE_DN}"]
    oopts = "".join(f'<option value="{esc(o["distinguishedName"])}"{" selected" if o["distinguishedName"] == ou else ""}>'
                    f'{esc(ou_path(o["distinguishedName"]) if o["distinguishedName"] != ROOT_OU else "ATB")}</option>'
                    for o in ous)
    sopts = "".join(f'<option value="{v}"{" selected" if v == status else ""}>{lbl}</option>'
                    for v, lbl in [("", "Any status"), ("enabled", "Enabled"), ("disabled", "Disabled")])
    args = {k: v for k, v in a.items() if k != "page" and v}
    body = (f'<h1>People</h1><div class="card"><form class="f" method="get">'
            f'<div><label>Name / login / e-mail</label><input name="q" value="{esc(q)}" placeholder="e.g. Koval"></div>'
            f'<div><label>Department</label><select name="department"><option value="">All departments</option>{dopts}</select></div>'
            f'<div><label>Title contains</label><input name="title" value="{esc(title)}" placeholder="e.g. Manager"></div>'
            f'<div><label>Organizational unit</label><select name="ou"><option value="">Whole domain</option>{oopts}</select></div>'
            f'<div><label>Status</label><select name="status">{sopts}</select></div>'
            '<div><button>Search</button></div></form>'
            f'<p class="muted small">{len(hits):,} account(s) &middot; <code>{esc(flt)}</code></p>'
            '<table><thead><tr><th>Name</th><th>Logon</th><th>Title</th><th>Department</th><th>Office</th>'
            f'<th>Phone</th><th>Status</th></tr></thead><tbody>{rows or "<tr><td colspan=7 class=muted>No matching accounts.</td></tr>"}'
            f'</tbody></table>{pager(len(hits), pg, per, args)}</div>')
    return page("People", body, "people")


def user_view(o, active="people"):
    ip = atblog.client_ip(request)
    atblog.log("ad.user_view", ip, target=o["sAMAccountName"], dn=o["distinguishedName"])
    initials = "".join(w[0] for w in (o.get("givenName", ""), o.get("sn", "")) if w) or o["cn"][:2]
    pls, last = from_filetime(o.get("pwdLastSet")), from_filetime(o.get("lastLogonTimestamp"))
    uac = int(o.get("userAccountControl", 0))
    if uac & 0x10000:
        expires = "Never"
    elif pls:
        expires = human(pls + 90 * 86400)
    else:
        expires = "Must change at next logon"
    gen = [("Display name", esc(o.get("displayName"))), ("First name", esc(o.get("givenName"))),
           ("Last name", esc(o.get("sn"))), ("Description", esc(o.get("description"))),
           ("E-mail", esc(o.get("mail"))), ("Office", esc(o.get("physicalDeliveryOfficeName"))),
           ("City", esc(o.get("l"))), ("Telephone", esc(o.get("telephoneNumber"))),
           ("Mobile", esc(o.get("mobile"))), ("Notes", esc(o.get("info")))]
    org = [("Title", esc(o.get("title"))), ("Department", esc(o.get("department"))),
           ("Company", esc(o.get("company"))), ("Employee ID", esc(o.get("employeeID"))),
           ("Manager", link_dn(o["manager"]) if o.get("manager") else ""),
           ("Direct reports", "<br>".join(link_dn(d) for d in o.get("directReports", [])))]
    acct = [("User logon name", esc(o.get("userPrincipalName"))),
            ("Pre-Windows 2000", f"{NETBIOS}\\{esc(o['sAMAccountName'])}"),
            ("Distinguished name", f"<code class=small>{esc(o['distinguishedName'])}</code>"),
            ("Organizational unit", esc(ou_path(parent_of(o["distinguishedName"])))),
            ("Status", status_tag(o)), ("userAccountControl", f"{uac} {uac_tags(uac)}"),
            ("Account created", human(from_gentime(o["whenCreated"]))),
            ("Last changed", human(from_gentime(o["whenChanged"]))),
            ("Last logon", human(last)), ("Logon count", esc(o.get("logonCount"))),
            ("Password last set", human(pls)), ("Password expires", expires),
            ("Bad password count", esc(o.get("badPwdCount", "0"))),
            ("Account expires", "Never"), ("objectSid", f"<code class=small>{esc(o['objectSid'])}</code>"),
            ("objectGUID", f"<code class=small>{esc(o['objectGUID'])}</code>")]
    if o.get("servicePrincipalName"):
        acct.append(("Service principal names", "<br>".join(esc(s) for s in o["servicePrincipalName"])))
    kv = lambda rows: '<div class="kv">' + "".join(f'<div class="k">{k}</div><div>{v or "&mdash;"}</div>' for k, v in rows) + "</div>"
    groups = "".join(f"<tr><td>{link_dn(g)}</td><td class=small>{esc(ou_path(parent_of(g)))}</td></tr>"
                     for g in o.get("memberOf", []))
    groups = '<tr><td><a href="/groups/Domain%20Users">Domain Users</a> <span class="tag">primary</span></td><td class=small>Users</td></tr>' + groups
    body = (f'<div class="head"><div class="avatar">{esc(initials.upper())}</div><div><h1 style="margin:0">'
            f'{esc(o.get("displayName") or o["cn"])}</h1><div class="muted">{esc(o.get("title") or o.get("description") or "")}'
            f'</div></div></div><div class="grid2"><div class="card"><h2>General</h2>{kv(gen)}</div>'
            f'<div class="card"><h2>Organization</h2>{kv(org)}</div></div>'
            f'<div class="card"><h2>Account</h2>{kv(acct)}</div>'
            f'<div class="card"><h2>Member of</h2><table><thead><tr><th>Group</th><th>Location</th></tr></thead>'
            f'<tbody>{groups}</tbody></table></div>')
    return page(o.get("displayName") or o["cn"], body, active)


@app.get("/directory/<path:sam>")
def directory_entry(sam):
    deny = need_auth()
    if deny:
        return deny
    i = find_sam(sam)
    if i is None or not is_user(get(i)):
        body = ('<div class="card"><h1>Not found</h1><p class="muted">No user account with that logon name.</p>'
                '<p><a href="/directory">&larr; Back to People</a></p></div>')
        return page("Not found", body, "people"), 404
    return user_view(get(i))


@app.get("/me")
def me():
    deny = need_auth()
    if deny:
        return deny
    return user_view(get(EDU_IDX), "me")


GTYPES = {"-2147483646": "Security - Global", "-2147483644": "Security - Domain local",
          "-2147483643": "Security - Builtin local", "-2147483640": "Security - Universal",
          "2": "Distribution - Global", "8": "Distribution - Universal"}


def _gcount(g):
    if g["cn"] == "Domain Users":
        return COUNTS["users"]
    if g["cn"] == "Domain Computers":
        return sum(1 for o in OBJ if is_computer(o) and o.get("primaryGroupID") == "515")
    if g["cn"] == "Domain Controllers":
        return sum(1 for o in OBJ if is_computer(o) and o.get("primaryGroupID") == "516")
    return group_member_count(g)


@app.get("/groups")
def groups():
    deny = need_auth()
    if deny:
        return deny
    q = (request.args.get("q") or "").strip().lower()
    t = request.args.get("type", "")
    gs = [OBJ[i] for i in GROUPS.values()]
    if q:
        gs = [g for g in gs if q in g["cn"].lower() or q in g.get("description", "").lower()]
    if t == "security":
        gs = [g for g in gs if g["groupType"].startswith("-")]
    elif t == "distribution":
        gs = [g for g in gs if not g["groupType"].startswith("-")]
    gs.sort(key=lambda g: g["cn"].lower())
    rows = "".join(f"<tr><td>{link_dn(g['distinguishedName'])}</td><td class=small>{GTYPES.get(g['groupType'], g['groupType'])}</td>"
                   f"<td>{_gcount(g):,}</td><td class=small>{esc(g.get('description'))}</td>"
                   f"<td class=small>{esc(ou_path(parent_of(g['distinguishedName'])))}</td></tr>" for g in gs)
    topts = "".join(f'<option value="{v}"{" selected" if v == t else ""}>{l}</option>'
                    for v, l in [("", "All types"), ("security", "Security"), ("distribution", "Distribution")])
    body = (f'<h1>Groups</h1><div class="card"><form class="f"><div><label>Search</label>'
            f'<input name="q" value="{esc(q)}" placeholder="Group name or description"></div>'
            f'<div><label>Type</label><select name="type">{topts}</select></div><div><button>Filter</button></div></form>'
            f'<p class="muted small">{len(gs)} group(s)</p>'
            '<table><thead><tr><th>Name</th><th>Type</th><th>Members</th><th>Description</th><th>Location</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')
    return page("Groups", body, "groups")


@app.get("/groups/<path:cn>")
def group_view(cn):
    deny = need_auth()
    if deny:
        return deny
    if cn not in GROUPS:
        return page("Not found", '<div class="card"><h1>Not found</h1><p><a href="/groups">&larr; Groups</a></p></div>',
                    "groups"), 404
    g = OBJ[GROUPS[cn]]
    atblog.log("ad.group_view", atblog.client_ip(request), group=cn)
    per, pg = 100, _int(request.args.get("page"))
    note = ""
    if cn in ("Domain Users", "Domain Computers", "Domain Controllers"):
        pgid = {"Domain Users": "513", "Domain Computers": "515", "Domain Controllers": "516"}[cn]
        total = _gcount(g)
        if cn == "Domain Users":
            idx = [i for i, o in enumerate(OBJ) if is_user(o) and o.get("primaryGroupID") == pgid]
            allidx = idx + list(range(STATIC, STATIC + LAZY))
        else:
            allidx = [i for i, o in enumerate(OBJ) if is_computer(o) and o.get("primaryGroupID") == pgid]
        dns = [get(i)["distinguishedName"] for i in allidx[(pg - 1) * per: pg * per]]
        note = '<p class="muted small">Members listed through the primary group (primaryGroupID=' + pgid + ').</p>'
    else:
        total = group_member_count(g)
        dns = group_member_dns(g, (pg - 1) * per, per)
    rows = []
    for dn in dns:
        i = find_dn(dn)
        o = get(i) if i is not None else {}
        kind = "Group" if o and is_group(o) else "Computer" if o and is_computer(o) else "User"
        rows.append(f"<tr><td>{link_dn(dn)}</td><td>{kind}</td><td class=small>{esc(o.get('title') or o.get('description'))}</td>"
                    f"<td class=small>{esc(ou_path(parent_of(dn)))}</td></tr>")
    member_of = "".join(link_dn(x) + "<br>" for x in g.get("memberOf", [])) or "&mdash;"
    body = (f'<h1>{esc(cn)}</h1><div class="grid2"><div class="card"><h2>Properties</h2><div class="kv">'
            f'<div class="k">Description</div><div>{esc(g.get("description"))}</div>'
            f'<div class="k">Group type</div><div>{GTYPES.get(g["groupType"], g["groupType"])}</div>'
            f'<div class="k">Distinguished name</div><div><code class=small>{esc(g["distinguishedName"])}</code></div>'
            f'<div class="k">objectSid</div><div><code class=small>{esc(g["objectSid"])}</code></div>'
            f'<div class="k">Created</div><div>{human(from_gentime(g["whenCreated"]))}</div>'
            f'<div class="k">Changed</div><div>{human(from_gentime(g["whenChanged"]))}</div>'
            f'<div class="k">Member of</div><div>{member_of}</div></div></div>'
            f'<div class="card"><h2>Summary</h2><div class="stats"><div class="stat"><b>{total:,}</b>members</div></div></div></div>'
            f'<div class="card"><h2>Members</h2>{note}<table><thead><tr><th>Name</th><th>Type</th><th>Title / description</th>'
            f'<th>Location</th></tr></thead><tbody>{"".join(rows) or "<tr><td colspan=4 class=muted>No members.</td></tr>"}'
            f'</tbody></table>{pager(total, pg, per, {})}</div>')
    return page(cn, body, "groups")


def _ou_counts():
    c = {}
    for o in OBJ:
        p = parent_of(o["distinguishedName"]).lower()
        c[p] = c.get(p, 0) + 1
    c[STAFF_OU.lower()] = c.get(STAFF_OU.lower(), 0) + LAZY
    return c


OU_COUNTS = _ou_counts()


@app.get("/ous")
def ous():
    deny = need_auth()
    if deny:
        return deny
    nodes = [o for o in OBJ if "organizationalUnit" in o["objectClass"] or "container" in o["objectClass"]]
    def kids(dn):
        return sorted((o for o in nodes if parent_of(o["distinguishedName"]).lower() == dn.lower()),
                      key=lambda o: ("container" in o["objectClass"], o["name"]))
    def render(dn):
        ks = kids(dn)
        if not ks:
            return ""
        out = '<ul class="tree">'
        for o in ks:
            d = o["distinguishedName"]
            out += (f'<li><a href="/ous/view?dn={quote(d)}">{esc(o["name"])}</a> '
                    f'<span class="muted small">({OU_COUNTS.get(d.lower(), 0):,} objects)</span>'
                    + (f' <span class="small muted">&mdash; {esc(o["description"])}</span>' if o.get("description") else "")
                    + render(d) + "</li>")
        return out + "</ul>"
    body = (f'<h1>Organizational units</h1><div class="card"><h2>{DOMAIN}</h2>'
            f'<p class="muted small"><code>{BASE_DN}</code></p>{render(BASE_DN)}</div>')
    return page("Organizational units", body, "ous")


@app.get("/ous/view")
def ou_view():
    deny = need_auth()
    if deny:
        return deny
    dn = request.args.get("dn", BASE_DN)
    i = find_dn(dn)
    if i is None:
        return page("Not found", '<div class="card"><h1>No such object</h1></div>', "ous"), 404
    o = get(i)
    dn = o["distinguishedName"]
    hits = run_search(dn, "one", "(objectClass=*)")
    per, pg = 100, _int(request.args.get("page"))
    rows = "".join(
        f"<tr><td>{link_dn(get(j)['distinguishedName'])}</td><td>{get(j)['objectClass'][-1]}</td>"
        f"<td class=small>{esc(get(j).get('title') or get(j).get('description') or get(j).get('operatingSystem'))}</td></tr>"
        for j in hits[(pg - 1) * per: pg * per])
    body = (f'<h1>{esc(o["name"])}</h1><div class="card"><p class="muted small"><code>{esc(dn)}</code></p>'
            + (f'<p>{esc(o.get("description"))}</p>' if o.get("description") else "")
            + f'<p><a href="/ous">&larr; OU tree</a></p><table><thead><tr><th>Name</th><th>Class</th><th>Details</th></tr></thead>'
            f'<tbody>{rows or "<tr><td colspan=3 class=muted>Empty.</td></tr>"}</tbody></table>'
            f'{pager(len(hits), pg, per, {"dn": dn})}</div>')
    return page(o["name"], body, "ous")


@app.get("/computers")
def computers():
    deny = need_auth()
    if deny:
        return deny
    a = request.args
    q, os_, ou = (a.get("q") or "").strip().lower(), a.get("os", ""), a.get("ou", "")
    cs = [o for o in OBJ if is_computer(o)]
    if q:
        cs = [c for c in cs if q in c["cn"].lower() or q in c.get("description", "").lower()]
    if os_:
        cs = [c for c in cs if c["operatingSystem"] == os_]
    if ou:
        cs = [c for c in cs if c["distinguishedName"].lower().endswith("," + ou.lower())]
    if q or os_ or ou:
        atblog.log("ad.computer_search", atblog.client_ip(request), q=q, os=os_, ou=ou, count=len(cs))
    oses = sorted({o["operatingSystem"] for o in OBJ if is_computer(o)})
    ous_ = sorted({parent_of(o["distinguishedName"]) for o in OBJ if is_computer(o)})
    per, pg = 100, _int(a.get("page"))
    rows = "".join(
        f"<tr><td>{link_dn(c['distinguishedName'])}</td><td class=small>{esc(c['operatingSystem'])} "
        f"<span class=muted>{esc(c['operatingSystemVersion'])}</span></td><td class=small>{esc(c.get('description'))}</td>"
        f"<td class=small>{esc(ou_path(parent_of(c['distinguishedName'])))}</td>"
        f"<td class=small>{human(from_filetime(c['lastLogonTimestamp']))}</td></tr>"
        for c in cs[(pg - 1) * per: pg * per])
    oopt = "".join(f'<option{" selected" if x == os_ else ""}>{esc(x)}</option>' for x in oses)
    uopt = "".join(f'<option value="{esc(x)}"{" selected" if x == ou else ""}>{esc(ou_path(x))}</option>' for x in ous_)
    body = (f'<h1>Computers</h1><div class="card"><form class="f"><div><label>Name / description</label>'
            f'<input name="q" value="{esc(q)}"></div><div><label>Operating system</label><select name="os">'
            f'<option value="">Any</option>{oopt}</select></div><div><label>Location</label><select name="ou">'
            f'<option value="">Any</option>{uopt}</select></div><div><button>Filter</button></div></form>'
            f'<p class="muted small">{len(cs)} computer(s)</p><table><thead><tr><th>Name</th><th>Operating system</th>'
            f'<th>Description</th><th>Location</th><th>Last logon</th></tr></thead><tbody>{rows}</tbody></table>'
            f'{pager(len(cs), pg, per, {k: v for k, v in a.items() if k != "page" and v})}</div>')
    return page("Computers", body, "computers")


@app.get("/computers/<name>")
def computer_view(name):
    deny = need_auth()
    if deny:
        return deny
    i = find_sam(name + "$")
    if i is None:
        return page("Not found", '<div class="card"><h1>Not found</h1><p><a href="/computers">&larr; Computers</a></p></div>',
                    "computers"), 404
    c = get(i)
    rows = [("DNS name", esc(c["dNSHostName"])), ("Description", esc(c.get("description"))),
            ("Operating system", esc(c["operatingSystem"])), ("OS version", esc(c["operatingSystemVersion"])),
            ("Managed by", link_dn(c["managedBy"]) if c.get("managedBy") else ""),
            ("Distinguished name", f"<code class=small>{esc(c['distinguishedName'])}</code>"),
            ("Role", "Domain controller" if c["primaryGroupID"] == "516" else
             "Server" if "Server" in c["operatingSystem"] else "Workstation"),
            ("userAccountControl", f"{c['userAccountControl']} {uac_tags(c['userAccountControl'])}"),
            ("Created", human(from_gentime(c["whenCreated"]))),
            ("Last logon", human(from_filetime(c["lastLogonTimestamp"]))),
            ("Machine password set", human(from_filetime(c["pwdLastSet"]))),
            ("objectSid", f"<code class=small>{esc(c['objectSid'])}</code>")]
    kv = '<div class="kv">' + "".join(f'<div class="k">{k}</div><div>{v or "&mdash;"}</div>' for k, v in rows) + "</div>"
    return page(c["cn"], f'<h1>{esc(c["cn"])}</h1><div class="card">{kv}</div>'
                         '<p><a href="/computers">&larr; Computers</a></p>', "computers")


@app.route("/password", methods=["GET", "POST"])
def password():
    deny = need_auth()
    if deny:
        return deny
    msg = ""
    if request.method == "POST":
        ip = atblog.client_ip(request)
        cur, new, rep = (request.form.get(k, "") for k in ("current", "new", "confirm"))
        if cur != VALID_PW:
            atblog.log("ad.password_change_fail", ip, account="education", reason="bad_current")
            msg = '<div class="err">The current password is incorrect.</div>'
        elif new != rep:
            msg = '<div class="err">The new passwords do not match.</div>'
        elif len(new) < 10 or sum(bool(re.search(p, new)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]")) < 3:
            msg = ('<div class="err">The password does not meet the password policy requirements: at least 10 '
                   'characters and 3 of: lower case, upper case, digits, symbols.</div>')
        else:
            atblog.log("ad.password_change_denied", ip, account="education",
                       msg="self-service password change refused for service account")
            msg = ('<div class="err">Access is denied (0x00000005). This account is not allowed to change its own '
                   'password. Service account passwords are managed by IT Infrastructure &mdash; raise a request '
                   'with the Service Desk (ext. 4357).</div>')
    me_ = get(EDU_IDX)
    body = (f'<h1>Change password</h1><div class="card" style="max-width:520px">{msg}'
            f'<p class="muted">Account: <b>{NETBIOS}\\{esc(me_["sAMAccountName"])}</b></p>'
            '<form method="post"><div class="f" style="display:block">'
            '<label>Current password</label><input type="password" name="current" style="width:100%" autocomplete="current-password">'
            '<label style="margin-top:10px">New password</label><input type="password" name="new" style="width:100%" autocomplete="new-password">'
            '<label style="margin-top:10px">Confirm new password</label><input type="password" name="confirm" style="width:100%" autocomplete="new-password">'
            '</div><button>Change password</button></form>'
            '<p class="small muted">Requirements: minimum 10 characters, 3 of 4 character classes, cannot reuse '
            'the last 12 passwords, minimum age 1 day.</p></div>')
    return page("Change password", body, "password")


@app.get("/domain")
def domain():
    deny = need_auth()
    if deny:
        return deny
    dcs = [o for o in OBJ if is_computer(o) and o["primaryGroupID"] == "516"]
    dcrows = "".join(f"<tr><td>{link_dn(d['distinguishedName'])}</td><td>{esc(d['operatingSystem'])}</td>"
                     f"<td class=small>{esc(d.get('description'))}</td></tr>" for d in dcs)
    kv = lambda rows: '<div class="kv">' + "".join(f'<div class="k">{k}</div><div>{v}</div>' for k, v in rows) + "</div>"
    body = ('<h1>Domain information</h1><div class="grid2"><div class="card"><h2>Domain</h2>'
            + kv([("DNS name", DOMAIN), ("NetBIOS name", NETBIOS), ("Distinguished name", BASE_DN),
                  ("Domain SID", f"<code class=small>{DOMAIN_SID}</code>"),
                  ("Domain functional level", "Windows Server 2016"), ("Forest functional level", "Windows Server 2016"),
                  ("Created", human(1199145600)), ("Sites", "Dnipro-HQ, Kyiv, DC1-Logistics")])
            + '</div><div class="card"><h2>Default password policy</h2>'
            + kv([("Minimum length", "10"), ("Complexity", "Enabled"), ("Maximum age", "90 days"),
                  ("Minimum age", "1 day"), ("History", "12 passwords"), ("Lockout threshold", "10 invalid attempts"),
                  ("Lockout duration", "15 minutes"), ("Fine-grained policies", "PSO-Admins, PSO-ServiceAccounts")])
            + '</div></div><div class="card"><h2>FSMO roles</h2>'
            + kv([("Schema master", "DC-MAIN-01"), ("Domain naming master", "DC-MAIN-01"),
                  ("PDC emulator", "DC-MAIN-01"), ("RID master", "DC-MAIN-01"), ("Infrastructure master", "DC-MAIN-02")])
            + f'</div><div class="card"><h2>Domain controllers</h2><table><thead><tr><th>Name</th><th>OS</th>'
            f'<th>Description</th></tr></thead><tbody>{dcrows}</tbody></table></div>')
    return page("Domain info", body, "domain")


@app.get("/healthz")
def healthz():
    return "ok", 200


@app.errorhandler(404)
def nf(e):
    if request.path in ("/bind", "/search", "/rootDSE") or request.accept_mimetypes.best == "application/json":
        return jsonify(ok=False, error="not found"), 404
    return page("Not found", '<div class="card"><h1>Not found</h1><p><a href="/">Home</a></p></div>'), 404


@app.errorhandler(405)
def mna(e):
    return jsonify(ok=False, error=f"method {request.method} not allowed"), 405


def _warm():
    """Pre-compute the portal's default listings so first page loads are fast."""
    for args in [("", "", "", "", ""), ("", "", "", "", "enabled"), ("", "", "", "", "disabled"),
                 ("", "Stores", "", "", "")]:
        flt, base = _people_filter(*args)
        run_search(base, "sub", flt)
    run_search(BASE_DN, "sub", "(objectClass=user)")
    run_search(STAFF_OU, "one", "(objectClass=*)")


if __name__ == "__main__":
    import threading
    threading.Thread(target=_warm, daemon=True).start()
    atblog.banner()
    app.run(host="0.0.0.0", port=80, threaded=True)
