"""Step 1a - mobapp.atbmarket.com: ATB Market mobile app site + mobile gateway API.

Hard-coded Basic service credential (reg_user:basic*88password!prod99) ships in
the APK's assets/index.android.bundle; the gateway accepts it for the
registration + catalogue endpoints. Member endpoints use a Bearer token issued
after OTP verification. In-world findings (intentional): OTP echoed in a debug
response header, loyalty-card lookup by number without ownership check, public
OpenAPI document.
"""
import base64
import hashlib
import hmac
import html
import io
import json
import os
import random
import secrets
import struct
import time
import uuid
import zipfile
import zlib
from datetime import date, datetime, timedelta, timezone

from flask import Flask, Response, g, jsonify, request, send_file
import atblog

app = Flask(__name__)
app.json.sort_keys = False

REG_USER = "reg_user"
REG_PASS = "basic*88password!prod99"

API_BASE = "https://mobapp.atbmarket.com"
APK_PATH = os.environ.get("ATB_APK_PATH", "/tmp/atb-market.apk")
APP_VERSION = "8.0.48"
APP_VERSION_CODE = 80048
GATEWAY_VERSION = "3.14.2"
GATEWAY_BUILD = "2026.09.30-1f3c9ab"
JWT_SECRET = b"mgw-prod-6c1f0e7a9d2b4c88a1e35f02b7d9c461"
JWT_TTL = 3600
OTP_TTL = 180

FAKE_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJyZWciLCJwaG9uZSI6IjM4MCIsImlhdCI6MTcwMH0."
    "S1gn4tur3Pr0dReg1str4t10nT0k3n0000"
)

# --------------------------------------------------------------------------- data
FIRST = ["Olena", "Andriy", "Iryna", "Serhii", "Oksana", "Dmytro", "Natalia",
         "Oleksandr", "Yulia", "Mykola", "Tetiana", "Vasyl", "Kateryna", "Ihor",
         "Svitlana", "Bohdan", "Halyna", "Roman", "Maryna", "Taras", "Liudmyla",
         "Yurii", "Viktoriia", "Pavlo", "Anastasiia", "Volodymyr", "Inna", "Maksym"]
LAST = ["Koval", "Bondarenko", "Tkachenko", "Melnyk", "Shevchenko", "Kravchenko",
        "Boyko", "Kovalenko", "Oliinyk", "Lysenko", "Moroz", "Savchenko",
        "Rudenko", "Marchenko", "Petrenko", "Klymenko", "Pavlenko", "Ponomarenko",
        "Levchenko", "Kharchenko", "Zinchenko", "Hnatiuk", "Sydorenko", "Romaniuk"]

CITIES = [
    ("Dnipro", 48.4647, 35.0462, ["Yavornytskoho Ave", "Pushkina Ave", "Hladkova St",
     "Slobozhanskyi Ave", "Polia Ave", "Naberezhna Peremohy", "Kalynova St"]),
    ("Kyiv", 50.4501, 30.5234, ["Peremohy Ave", "Kharkivske Hwy", "Zabolotnoho Ave",
     "Obolonskyi Ave", "Mykoly Bazhana Ave", "Lobanovskoho Ave", "Akhmatovoi St"]),
    ("Kharkiv", 49.9935, 36.2304, ["Nauky Ave", "Heroiv Kharkova Ave", "Klochkivska St",
     "Traktorobudivnykiv Ave", "Sumska St", "Poltavskyi Shliakh"]),
    ("Zaporizhzhia", 47.8388, 35.1396, ["Sobornyi Ave", "Ukrainska St", "Zaporizka St",
     "Metalurhiv Ave", "Ladozhska St"]),
    ("Lviv", 49.8397, 24.0297, ["Horodotska St", "Naukova St", "Chervonoyi Kalyny Ave",
     "Stryiska St", "Shevchenka St"]),
    ("Odesa", 46.4825, 30.7233, ["Akademika Hlushka Ave", "Kanatna St",
     "Dniprovska Doroha", "Balkivska St", "Koroliova St"]),
    ("Kryvyi Rih", 47.9105, 33.3918, ["Metalurhiv Ave", "Hagarina Ave", "Kosmonavtiv St",
     "Pivdennyi Ave"]),
    ("Poltava", 49.5883, 34.5514, ["Zinkivska St", "Pershotravnevyi Ave",
     "Kyivskyi Shliakh"]),
    ("Vinnytsia", 49.2331, 28.4682, ["Keleckaya St", "Khmelnytske Hwy", "Soborna St"]),
    ("Kamianske", 48.5079, 34.6132, ["Kh. Bohdana Ave", "Svobody Ave"]),
]

PRODUCTS = [
    ("Milk 2.5% \"Yagotynske\" 900 g", "Dairy", 42.90),
    ("Butter 73% \"Selianske\" 180 g", "Dairy", 79.90),
    ("Kefir 1% \"Galychyna\" 850 g", "Dairy", 39.40),
    ("Cottage cheese 5% 350 g", "Dairy", 64.50),
    ("Hard cheese \"Komo Poshekhonskyi\" per kg", "Dairy", 349.00),
    ("Chicken fillet chilled per kg", "Meat", 189.90),
    ("Pork neck chilled per kg", "Meat", 259.00),
    ("Doctor's sausage \"Globino\" per kg", "Meat", 299.00),
    ("Bananas per kg", "Fruit & Veg", 59.90),
    ("Apples \"Golden\" per kg", "Fruit & Veg", 34.90),
    ("Potatoes washed per kg", "Fruit & Veg", 21.90),
    ("Tomatoes pink per kg", "Fruit & Veg", 89.00),
    ("Cucumbers short per kg", "Fruit & Veg", 74.90),
    ("Bread \"Darnytskyi\" 650 g", "Bakery", 31.50),
    ("Baton \"Nareznyi\" 450 g", "Bakery", 26.90),
    ("Buckwheat \"Zhmenka\" 1 kg", "Grocery", 62.90),
    ("Sunflower oil \"Oleina\" 850 ml", "Grocery", 72.40),
    ("Pasta \"Chumak\" spaghetti 400 g", "Grocery", 34.90),
    ("Sugar white 1 kg", "Grocery", 36.90),
    ("Eggs C1 10 pcs", "Grocery", 54.90),
    ("Coffee \"Jacobs Monarch\" ground 225 g", "Hot drinks", 189.00),
    ("Tea \"Greenfield\" black 100 bags", "Hot drinks", 139.90),
    ("Chocolate \"Roshen\" milk 90 g", "Sweets", 46.90),
    ("Biscuits \"Maria\" 155 g", "Sweets", 24.90),
    ("Mineral water \"Morshynska\" 1.5 L", "Drinks", 23.90),
    ("Juice \"Sandora\" orange 0.95 L", "Drinks", 59.90),
    ("Beer \"Obolon Premium\" 0.5 L", "Drinks", 34.90),
    ("Washing powder \"Gala\" 3 kg", "Household", 169.00),
    ("Toilet paper \"Ruta\" 8 rolls", "Household", 89.90),
    ("Dish liquid \"Fairy\" 500 ml", "Household", 64.90),
    ("Shower gel \"Dove\" 250 ml", "Care", 119.00),
    ("Toothpaste \"Colgate\" 100 ml", "Care", 72.90),
    ("Cat food \"Whiskas\" 85 g", "Pets", 18.90),
    ("Frozen dumplings \"Three Bears\" 800 g", "Frozen", 129.00),
    ("Ice cream \"Rud\" plombir 70 g", "Frozen", 27.90),
    ("Herring fillet in oil 500 g", "Fish", 119.90),
]

COUPON_TEMPLATES = [
    ("-15% on all dairy", "Dairy", 15, 200),
    ("-20% fruit & vegetables on Mondays", "Fruit & Veg", 20, 300),
    ("x3 points on coffee and tea", "Hot drinks", 0, 0),
    ("-10% on your next basket over 500 UAH", "All", 10, 500),
    ("Free bread with any purchase over 300 UAH", "Bakery", 100, 300),
    ("-25% household chemicals", "Household", 25, 150),
    ("-30% on frozen dumplings", "Frozen", 30, 0),
    ("Birthday bonus: 200 points", "All", 0, 0),
    ("-12% pet food", "Pets", 12, 0),
    ("-50 UAH on baskets over 800 UAH", "All", 0, 800),
]

TIERS = [("Standard", 0), ("Silver", 2500), ("Gold", 8000), ("Platinum", 20000)]


def _rng(*parts):
    seed = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return random.Random(int.from_bytes(seed[:8], "big"))


def _stores():
    out = []
    n = 1
    for city, lat, lng, streets in CITIES:
        r = _rng("stores", city)
        count = {"Dnipro": 38, "Kyiv": 26, "Kharkiv": 18, "Zaporizhzhia": 14}.get(city, 8)
        for _ in range(count):
            fmt = r.choice(["ATB", "ATB", "ATB", "ATB Express", "ATB Market"])
            svc = sorted(r.sample(["card_payment", "self_checkout", "atm", "bakery",
                                   "pharmacy_point", "parcel_lockers", "parking",
                                   "contactless", "gas_station"], r.randint(2, 5)))
            open_h = r.choice(["07:00", "07:30", "08:00"])
            close_h = r.choice(["22:00", "22:00", "23:00", "21:00"])
            out.append({
                "id": f"ST{n:04d}",
                "code": f"{100 + n * 7 % 1700:04d}",
                "format": fmt,
                "city": city,
                "address": f"{r.choice(streets)}, {r.randint(1, 180)}"
                           + (f"{r.choice('ABV')}" if r.random() < .12 else ""),
                "lat": round(lat + r.uniform(-.08, .08), 6),
                "lng": round(lng + r.uniform(-.11, .11), 6),
                "hours": {"mon_sat": f"{open_h}-{close_h}", "sun": f"{open_h}-{close_h}"},
                "phone": f"+38056{r.randint(3000000, 7999999)}",
                "services": svc,
                "isOpen24h": False,
            })
            n += 1
    return out


STORES = _stores()


def _week_bounds(today=None):
    today = today or date.today()
    start = today - timedelta(days=(today.weekday() - 3) % 7)  # Thursday
    return start, start + timedelta(days=6)


def _weekly_promo():
    start, end = _week_bounds()
    r = _rng("promo", start.isoformat())
    items = []
    for i, (name, cat, price) in enumerate(r.sample(PRODUCTS, 24)):
        pct = r.choice([10, 15, 20, 25, 30, 35, 40, 50])
        new = round(price * (100 - pct) / 100, 2)
        items.append({
            "sku": f"{4820000000000 + int(hashlib.md5(name.encode()).hexdigest()[:8], 16) % 9999999:013d}",
            "title": name,
            "category": cat,
            "oldPrice": price,
            "price": new,
            "discountPercent": pct,
            "currency": "UAH",
            "badge": r.choice(["Economy", "Hit", "Only in app", "Weekly price", None]),
            "limitPerReceipt": r.choice([None, None, 2, 4, 6]),
            "image": f"https://static.atbmarket.com/promo/{start:%Y%m%d}/{i + 1:02d}.webp",
        })
    return {"id": f"PROMO-{start:%Y-W%V}", "title": "Economy week",
            "validFrom": start.isoformat(), "validTo": end.isoformat(),
            "items": items}


def _card_for_phone(phone):
    digits = "".join(c for c in phone if c.isdigit())
    h = int(hashlib.sha1(("card:" + digits).encode()).hexdigest(), 16)
    return "29" + f"{h % 10**11:011d}"


def _customer(card):
    r = _rng("cust", card)
    first, last = r.choice(FIRST), r.choice(LAST)
    points = r.randint(0, 26000)
    tier = [t for t, lim in TIERS if points >= lim][-1]
    return {
        "firstName": first, "lastName": last,
        "email": f"{first.lower()}.{last.lower()}{r.randint(1, 99)}@{r.choice(['gmail.com', 'ukr.net', 'i.ua', 'meta.ua'])}",
        "birthDate": f"{r.randint(1958, 2004)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}",
        "city": r.choice(CITIES)[0],
        "points": points, "tier": tier,
        "memberSince": f"{r.randint(2014, 2025)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}",
        "favouriteStore": r.choice(STORES)["id"],
        "phoneMasked": f"+380{r.randint(50, 99)}***{r.randint(10, 99)}{r.randint(10, 99)}",
    }


# member state (in-memory, per container lifetime)
CHALLENGES = {}
PROFILE_EDITS = {}
ACTIVATED = {}
REVOKED = set()


# --------------------------------------------------------------------------- helpers
def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64u_dec(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def jwt_encode(payload):
    head = _b64u(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "mgw-2026-03"},
                            separators=(",", ":")).encode())
    body = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(JWT_SECRET, f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64u(sig)}"


def jwt_decode(tok):
    try:
        head, body, sig = tok.split(".")
        exp_sig = hmac.new(JWT_SECRET, f"{head}.{body}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(exp_sig, _b64u_dec(sig)):
            return None
        data = json.loads(_b64u_dec(body))
        if data.get("exp", 0) < time.time() or data.get("jti") in REVOKED:
            return None
        return data
    except Exception:
        return None


def _basic_b64():
    return base64.b64encode(f"{REG_USER}:{REG_PASS}".encode()).decode()


def _check_basic(hdr):
    if not hdr or not hdr.startswith("Basic "):
        return None
    try:
        raw = base64.b64decode(hdr.split(" ", 1)[1]).decode("utf-8", "replace")
        user, _, pw = raw.partition(":")
        return user, pw
    except Exception:
        return None


def err(status, code, message, **extra):
    body = {"error": {"code": code, "message": message, **extra},
            "requestId": g.get("rid", "-")}
    resp = jsonify(body)
    resp.status_code = status
    if status == 401:
        resp.headers["WWW-Authenticate"] = 'Basic realm="atb-mobile-gateway"'
    return resp


def _is_api():
    p = request.path
    return p.startswith("/api") or p.startswith("/register")


@app.before_request
def _rid():
    g.rid = uuid.uuid4().hex[:16]


@app.after_request
def _headers(resp):
    resp.headers["X-Request-Id"] = g.get("rid", "-")
    if _is_api():
        resp.headers["X-Api-Version"] = "v1"
        resp.headers["X-Gateway"] = f"atb-mgw/{GATEWAY_VERSION}"
        resp.headers["Cache-Control"] = "no-store"
    resp.headers["Server"] = "nginx"
    return resp


def require_service_auth():
    """Gate for app-level endpoints: the Basic credential baked into the client."""
    ip = atblog.client_ip(request)
    creds = _check_basic(request.headers.get("Authorization", ""))
    if not creds:
        atblog.log("mobapp.auth_missing", ip, path=request.path)
        return err(401, "AUTH_REQUIRED", "Client authentication required")
    if creds != (REG_USER, REG_PASS):
        atblog.log("mobapp.auth_fail", ip, user=creds[0], path=request.path)
        return err(401, "INVALID_CLIENT", "Invalid client credentials")
    return None


def require_member():
    hdr = request.headers.get("Authorization", "")
    if not hdr.startswith("Bearer "):
        return None, err(401, "TOKEN_REQUIRED", "Bearer access token required")
    data = jwt_decode(hdr[7:].strip())
    if not data or data.get("typ") != "access":
        atblog.log("mobapp.token_invalid", atblog.client_ip(request), path=request.path)
        return None, err(401, "TOKEN_INVALID", "Access token is invalid or expired")
    return data, None


def _profile(claims):
    phone, card = claims["phone"], claims["card"]
    c = _customer(card)
    c.update(PROFILE_EDITS.get(card, {}))
    return {
        "id": claims["sub"],
        "phone": phone,
        "firstName": c["firstName"], "lastName": c["lastName"],
        "email": c["email"], "birthDate": c["birthDate"], "city": c["city"],
        "language": c.get("language", "uk"),
        "favouriteStoreId": c["favouriteStore"],
        "marketingConsent": c.get("marketingConsent", True),
        "loyaltyCard": card,
        "memberSince": c["memberSince"],
    }


def _card_payload(card, own=True, phone=None):
    c = _customer(card)
    tier_idx = [t for t, _ in TIERS].index(c["tier"])
    nxt = TIERS[tier_idx + 1] if tier_idx + 1 < len(TIERS) else None
    return {
        "cardNumber": card,
        "barcode": {"type": "EAN13", "value": card[:12] + str(_ean_check(card[:12]))},
        "holder": f"{c['firstName']} {c['lastName']}",
        "phone": phone if own and phone else c["phoneMasked"],
        "status": "ACTIVE",
        "tier": c["tier"],
        "points": c["points"],
        "pointsValueUah": round(c["points"] / 10, 2),
        "nextTier": ({"name": nxt[0], "pointsNeeded": nxt[1] - c["points"]} if nxt else None),
        "memberSince": c["memberSince"],
        "issuedIn": c["city"],
    }


def _ean_check(d12):
    s = sum(int(x) * (3 if i % 2 else 1) for i, x in enumerate(d12))
    return (10 - s % 10) % 10


def _coupons(card):
    r = _rng("coupons", card, _week_bounds()[0].isoformat())
    start, end = _week_bounds()
    out = []
    for i, (title, cat, pct, min_basket) in enumerate(r.sample(COUPON_TEMPLATES, 6)):
        cid = f"CPN-{hashlib.md5(f'{card}{i}{start}'.encode()).hexdigest()[:10].upper()}"
        out.append({
            "id": cid, "title": title, "category": cat,
            "discountPercent": pct or None, "minBasketUah": min_basket or None,
            "validFrom": start.isoformat(),
            "validTo": (end + timedelta(days=r.choice([0, 7, 14]))).isoformat(),
            "activated": cid in ACTIVATED.get(card, set()),
            "personal": r.random() < .5,
        })
    return out


# --------------------------------------------------------------------------- APK
def _android_bundle():
    """React-Native index.android.bundle (plain JS, minified style). The client
    config module embeds the Basic service credential, so strings/grep on the
    bundle recovers it (see docs/apk-recon.md)."""
    b64 = _basic_b64()
    mods = []
    mods.append(
        '__d(function(g,r,i,a,m,e,d){"use strict";Object.defineProperty(e,"__esModule",{value:!0});'
        'e.default={env:"production",appVersion:"' + APP_VERSION + '",versionCode:' + str(APP_VERSION_CODE) + ','
        'API_BASE:"' + API_BASE + '",API_STAGE:"https://mobapp-stage.atbmarket.com",'
        'CDN_BASE:"https://static.atbmarket.com/mobile/",'
        'SUPPORT_PHONE:"0 800 500 415",SENTRY_DSN:"https://4b1e7f0c2a9d4e61b5a0c3d8e2f61a77@sentry.atbmarket.com/14",'
        'REQUEST_TIMEOUT:15e3,OTP_LENGTH:6,OTP_RESEND_SEC:60}},101,[],"src/config/env.js");'
    )
    mods.append(
        '__d(function(g,r,i,a,m,e,d){"use strict";Object.defineProperty(e,"__esModule",{value:!0});'
        'var t={username:"' + REG_USER + '",password:"' + REG_PASS + '"};'
        'e.SERVICE_CLIENT=t;e.basicAuthHeader=function(){return"Basic ' + b64 + '"};'
        'e.REGISTER_LOGIN="/register/login";e.REGISTER_VERIFY="/register/verify";'
        'e.REGISTER_REFRESH="/register/refresh";e.REGISTER_LOGOUT="/register/logout"'
        '},102,[101],"src/api/auth.js");'
    )
    mods.append(
        '__d(function(g,r,i,a,m,e,d){"use strict";var n=r(d[0]).default,o=r(d[1]),s=r(d[2]).default;'
        'function c(e,t){var u=Object.assign({"Content-Type":"application/json","Accept":"application/json",'
        '"X-App-Version":n.appVersion,"X-Platform":"android","X-Device-Id":s.getDeviceId()},t&&t.headers||{});'
        'return fetch(n.API_BASE+e,Object.assign({},t,{headers:u})).then(function(e){return e.status>=400?'
        'e.json().then(function(t){var n=new Error(t&&t.error&&t.error.message||"HTTP "+e.status);'
        'n.code=t&&t.error&&t.error.code;n.status=e.status;throw n}):e.json()})}'
        'function p(e,t){return c(e,Object.assign({},t,{headers:{Authorization:o.basicAuthHeader()}}))}'
        'function l(e,t){return s.getAccessToken().then(function(n){return c(e,Object.assign({},t,'
        '{headers:{Authorization:"Bearer "+n}}))})}'
        'm.exports={'
        'registerLogin:function(e){return p(o.REGISTER_LOGIN,{method:"POST",body:JSON.stringify({phoneNumber:e})})},'
        'verifyOtp:function(e,t){return p(o.REGISTER_VERIFY,{method:"POST",body:JSON.stringify({token:e,otp:t})})},'
        'refresh:function(e){return p(o.REGISTER_REFRESH,{method:"POST",body:JSON.stringify({refreshToken:e})})},'
        'logout:function(){return l(o.REGISTER_LOGOUT,{method:"POST"})},'
        'getConfig:function(){return p("/api/v1/config")},'
        'getStores:function(e){return p("/api/v1/stores?"+new URLSearchParams(e||{}).toString())},'
        'getStore:function(e){return p("/api/v1/stores/"+encodeURIComponent(e))},'
        'getWeeklyPromo:function(){return p("/api/v1/promo/weekly")},'
        'getProfile:function(){return l("/api/v1/profile")},'
        'updateProfile:function(e){return l("/api/v1/profile",{method:"PATCH",body:JSON.stringify(e)})},'
        'getLoyaltyCard:function(){return l("/api/v1/loyalty/card")},'
        'lookupCard:function(e){return l("/api/v1/loyalty/card/"+e)},'
        'getTransactions:function(){return l("/api/v1/loyalty/transactions")},'
        'getCoupons:function(){return l("/api/v1/coupons")},'
        'activateCoupon:function(e){return l("/api/v1/coupons/"+e+"/activate",{method:"POST"})}'
        '}},103,[101,102,104],"src/api/client.js");'
    )
    mods.append(
        '__d(function(g,r,i,a,m,e,d){"use strict";var t=r(d[0]).default,n=r(d[1]).default;'
        'm.exports={getDeviceId:function(){return n.getUniqueId()},'
        'getAccessToken:function(){return t.getItem("@atb/accessToken")},'
        'setTokens:function(e){return t.multiSet([["@atb/accessToken",e.accessToken],'
        '["@atb/refreshToken",e.refreshToken]])},clear:function(){return t.clear()}}'
        '},104,[201,202],"src/services/session.js");'
    )
    mods.append(
        '__d(function(g,r,i,a,m,e,d){"use strict";var t=r(d[0]),n=r(d[1]).default;'
        'function o(e){var o=e.navigation,a=t.useState(""),i=a[0],l=a[1],c=t.useState(!1),s=c[0],u=c[1];'
        'return t.createElement(n.Screen,{title:"Sign in"},'
        't.createElement(n.PhoneInput,{value:i,onChangeText:l,placeholder:"+380 XX XXX XX XX"}),'
        't.createElement(n.Button,{loading:s,title:"Get code",onPress:function(){u(!0);'
        'r(d[2]).registerLogin(i).then(function(e){o.navigate("Otp",{token:e.token,phone:i})})'
        '.catch(function(e){n.toast(e.message)}).finally(function(){u(!1)})}}))}'
        'm.exports=o},310,[1,220,103],"src/screens/Auth/PhoneScreen.js");'
    )
    mods.append(
        '__d(function(g,r,i,a,m,e,d){"use strict";var t=r(d[0]),n=r(d[1]).default,c=r(d[2]),s=r(d[3]);'
        'function o(e){var o=e.route.params,a=t.useState(""),i=a[0],l=a[1];'
        'return t.createElement(n.Screen,{title:"Confirmation code"},'
        't.createElement(n.Text,null,"We sent an SMS with a 6-digit code to "+o.phone),'
        't.createElement(n.OtpInput,{length:6,value:i,onChangeText:function(t){l(t);'
        'if(t.length===6)c.verifyOtp(o.token,t).then(function(t){return s.setTokens(t)})'
        '.then(function(){e.navigation.reset({index:0,routes:[{name:"Home"}]})})'
        '.catch(function(e){n.toast(e.code==="OTP_INVALID"?"Wrong code":e.message)})}}))}'
        'm.exports=o},311,[1,220,103,104],"src/screens/Auth/OtpScreen.js");'
    )
    mods.append(
        '__d(function(g,r,i,a,m,e,d){"use strict";var t=r(d[0]),n=r(d[1]).default,c=r(d[2]);'
        'm.exports=function(){var e=t.useState(null),o=e[0],a=e[1];t.useEffect(function(){'
        'Promise.all([c.getLoyaltyCard(),c.getCoupons()]).then(function(e){a({card:e[0],coupons:e[1].items})})},[]);'
        'return o?t.createElement(n.Screen,{title:"My ATB card"},t.createElement(n.Barcode,{value:o.card.barcode.value,format:"EAN13"}),'
        't.createElement(n.Text,{style:{fontSize:28}},o.card.points+" points"),'
        't.createElement(n.CouponList,{data:o.coupons,onActivate:c.activateCoupon})):t.createElement(n.Spinner,null)}'
        '},320,[1,220,103],"src/screens/Loyalty/CardScreen.js");'
    )
    mods.append(
        '__d(function(g,r,i,a,m,e,d){"use strict";var t=r(d[0]),n=r(d[1]).default,c=r(d[2]),l=r(d[3]);'
        'm.exports=function(){var e=t.useState([]),o=e[0],a=e[1];t.useEffect(function(){'
        'l.getCurrentPosition(function(e){c.getStores({lat:e.coords.latitude,lng:e.coords.longitude,radius:5e3})'
        '.then(function(e){a(e.items)})})},[]);return t.createElement(n.MapScreen,{title:"Stores",markers:o})}'
        '},330,[1,220,103,230],"src/screens/Stores/StoresMapScreen.js");'
    )
    mods.append(
        '__d(function(g,r,i,a,m,e,d){"use strict";var t=r(d[0]),n=r(d[1]).default,c=r(d[2]),f=r(d[3]).default;'
        'm.exports=function(){var e=[{k:"API",v:f.API_BASE},{k:"Stage",v:f.API_STAGE},{k:"Version",v:f.appVersion+" ("+f.versionCode+")"},'
        '{k:"API reference",v:f.API_BASE+"/api/v1/openapi.json"},{k:"Health",v:f.API_BASE+"/api/v1/health"}];'
        'return __DEV__?t.createElement(n.Screen,{title:"Developer menu"},e.map(function(e){'
        'return t.createElement(n.Row,{key:e.k,label:e.k,value:e.v})})):null}'
        '},390,[1,220,103,101],"src/screens/Dev/DevMenuScreen.js");'
    )
    mods.append(
        '__d(function(g,r,i,a,m,e,d){m.exports={uk:{"auth.title":"Вхід","auth.getCode":"Отримати код",'
        '"otp.sent":"Ми надіслали SMS з кодом","card.title":"Моя картка АТБ","promo.title":"Економія тижня",'
        '"stores.title":"Магазини","errors.network":"Немає з\'єднання з сервером"},'
        'en:{"auth.title":"Sign in","auth.getCode":"Get code","otp.sent":"We sent you an SMS code",'
        '"card.title":"My ATB card","promo.title":"Economy week","stores.title":"Stores",'
        '"errors.network":"No connection to the server"}}},400,[],"src/i18n/index.js");'
    )
    filler = []
    r = _rng("bundle-filler")
    names = ["react-native/Libraries/Renderer/implementations/ReactNativeRenderer-prod.js",
             "node_modules/react/cjs/react.production.min.js",
             "node_modules/@react-navigation/native/lib/module/NavigationContainer.js",
             "node_modules/@react-native-async-storage/async-storage/lib/module/AsyncStorage.native.js",
             "node_modules/react-native-device-info/src/index.ts",
             "node_modules/react-native-maps/lib/MapView.js",
             "node_modules/@sentry/react-native/dist/js/sdk.js",
             "node_modules/axios/lib/core/Axios.js",
             "node_modules/react-native-barcode-svg/index.js",
             "node_modules/@react-native-firebase/messaging/lib/index.js"]
    for idx, nm in enumerate(names):
        body = ";".join(
            f"function {chr(97 + r.randint(0, 25))}{r.randint(0, 99)}(e,t){{return e&&e.{r.choice(['props', 'state', 'current', 'value', 'length'])}"
            f"!==void 0?t(e):null}}" for _ in range(60))
        filler.append(f'__d(function(g,r,i,a,m,e,d){{"use strict";{body}}},{idx + 1},[],"{nm}");')
    return (
        "var __BUNDLE_START_TIME__=this.nativePerformanceNow?nativePerformanceNow():Date.now(),"
        "__DEV__=false,process=this.process||{};process.env=process.env||{};"
        "process.env.NODE_ENV=process.env.NODE_ENV||\"production\";\n"
        "!(function(e){\"use strict\";e.__r=o,e.__d=function(e,n,i){null==t[n]&&(t[n]={dependencyMap:i,"
        "factory:e,hasError:!1,importedAll:r,importedDefault:r,isInitialized:!1,publicModule:{exports:{}}})};"
        "var t=Object.create(null),r={};function o(e){var r=t[e];return r&&r.isInitialized?r.publicModule.exports:"
        "n(e,r)}})(\"undefined\"!=typeof globalThis?globalThis:this);\n"
        + "\n".join(filler) + "\n" + "\n".join(mods) + "\n"
        "__r(57);\n__r(0);\n"
        "//# sourceMappingURL=index.android.bundle.map\n"
    )


def _android_manifest():
    return f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="ua.com.atbmarket" android:versionCode="{APP_VERSION_CODE}"
    android:versionName="{APP_VERSION}" android:compileSdkVersion="34"
    android:compileSdkVersionCodename="14">
  <uses-sdk android:minSdkVersion="23" android:targetSdkVersion="34"/>
  <uses-permission android:name="android.permission.INTERNET"/>
  <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE"/>
  <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
  <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>
  <uses-permission android:name="android.permission.CAMERA"/>
  <uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
  <uses-permission android:name="android.permission.VIBRATE"/>
  <uses-permission android:name="com.google.android.c2dm.permission.RECEIVE"/>
  <application android:name=".MainApplication" android:label="@string/app_name"
      android:icon="@mipmap/ic_launcher" android:allowBackup="true"
      android:usesCleartextTraffic="false"
      android:networkSecurityConfig="@xml/network_security_config"
      android:theme="@style/AppTheme">
    <activity android:name=".MainActivity" android:exported="true"
        android:launchMode="singleTask" android:screenOrientation="portrait"
        android:windowSoftInputMode="adjustResize">
      <intent-filter>
        <action android:name="android.intent.action.MAIN"/>
        <category android:name="android.intent.category.LAUNCHER"/>
      </intent-filter>
      <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW"/>
        <category android:name="android.intent.category.DEFAULT"/>
        <category android:name="android.intent.category.BROWSABLE"/>
        <data android:scheme="https" android:host="mobapp.atbmarket.com" android:pathPrefix="/promo"/>
        <data android:scheme="atbmarket"/>
      </intent-filter>
    </activity>
    <activity android:name="com.facebook.react.devsupport.DevSettingsActivity" android:exported="false"/>
    <service android:name="io.invertase.firebase.messaging.ReactNativeFirebaseMessagingService"
        android:exported="false">
      <intent-filter><action android:name="com.google.firebase.MESSAGING_EVENT"/></intent-filter>
    </service>
    <meta-data android:name="com.google.android.geo.API_KEY" android:value="@string/google_maps_key"/>
    <meta-data android:name="io.sentry.dsn" android:value="@string/sentry_dsn"/>
  </application>
</manifest>
"""


def _strings_xml():
    return f"""<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">ATB</string>
    <string name="app_full_name">ATB Market</string>
    <string name="api_base_url">{API_BASE}</string>
    <string name="api_stage_url">https://mobapp-stage.atbmarket.com</string>
    <string name="cdn_base_url">https://static.atbmarket.com/mobile/</string>
    <string name="support_phone">0 800 500 415</string>
    <string name="support_email">mobile@atbmarket.com</string>
    <string name="google_maps_key">AIzaSyB7wQ2r0Qn5m8XkFvA1tY3eS9cJpLhU4dE</string>
    <string name="gcm_defaultSenderId">604318772951</string>
    <string name="google_app_id">1:604318772951:android:3e8a4c1f5b7d2a90</string>
    <string name="project_id">atb-market-mobile</string>
    <string name="sentry_dsn">https://4b1e7f0c2a9d4e61b5a0c3d8e2f61a77@sentry.atbmarket.com/14</string>
    <string name="default_notification_channel_id">atb_promo</string>
    <string name="otp_sms_hint">ATB: your code is %1$s</string>
    <string name="no_connection">No connection to the server</string>
    <string name="update_required">Please update the app to continue</string>
</resources>
"""


def _network_security_config():
    return """<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system"/>
        </trust-anchors>
    </base-config>
    <domain-config>
        <domain includeSubdomains="false">mobapp.atbmarket.com</domain>
        <pin-set expiration="2027-01-31">
            <pin digest="SHA-256">r/mIkG3eEpVdm+u/ko/cwxzOMo1bk4TyHIlByibiA5E=</pin>
            <pin digest="SHA-256">YLh1dUR9y6Kja30RrAn7JKnbQG/uEtLMkBgFF2Fuihg=</pin>
        </pin-set>
    </domain-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="true">mobapp-stage.atbmarket.com</domain>
        <domain includeSubdomains="false">10.0.2.2</domain>
        <domain includeSubdomains="false">localhost</domain>
    </domain-config>
    <debug-overrides>
        <trust-anchors>
            <certificates src="user"/>
        </trust-anchors>
    </debug-overrides>
</network-security-config>
"""


def _build_config_smali():
    return f""".class public final Lua/com/atbmarket/BuildConfig;
.super Ljava/lang/Object;
.source "BuildConfig.java"

.field public static final APPLICATION_ID:Ljava/lang/String; = "ua.com.atbmarket"
.field public static final BUILD_TYPE:Ljava/lang/String; = "release"
.field public static final DEBUG:Z = false
.field public static final FLAVOR:Ljava/lang/String; = "prod"
.field public static final IS_HERMES_ENABLED:Z = false
.field public static final IS_NEW_ARCHITECTURE_ENABLED:Z = false
.field public static final VERSION_CODE:I = {hex(APP_VERSION_CODE)}
.field public static final VERSION_NAME:Ljava/lang/String; = "{APP_VERSION}"
.field public static final API_BASE_URL:Ljava/lang/String; = "{API_BASE}"
.field public static final SENTRY_ENV:Ljava/lang/String; = "production"
"""


def _dex():
    strs = [
        "Lua/com/atbmarket/BuildConfig;", "Lua/com/atbmarket/MainActivity;",
        "Lua/com/atbmarket/MainApplication;", "APPLICATION_ID", "ua.com.atbmarket",
        "BUILD_TYPE", "release", "FLAVOR", "prod", "VERSION_NAME", APP_VERSION,
        "VERSION_CODE", "API_BASE_URL", API_BASE, "IS_HERMES_ENABLED",
        "getMainComponentName", "ATBMarket", "getJSBundleFile",
        "assets://index.android.bundle", "Lcom/facebook/react/ReactActivity;",
        "Lcom/facebook/react/defaults/DefaultReactNativeHost;",
        "Lokhttp3/OkHttpClient;", "Lokhttp3/CertificatePinner;",
        "sha256/r/mIkG3eEpVdm+u/ko/cwxzOMo1bk4TyHIlByibiA5E=",
        "Lio/sentry/android/core/SentryAndroid;", "onCreate", "SoLoader",
    ]
    r = _rng("dex")
    blob = bytearray(b"dex\n035\x00")
    blob += bytes(r.getrandbits(8) for _ in range(104))
    for s in strs:
        blob += bytes([len(s)]) + s.encode() + b"\x00"
        blob += bytes(r.getrandbits(8) for _ in range(r.randint(40, 200)))
    blob += bytes(r.getrandbits(8) for _ in range(24000))
    return bytes(blob)


def _elf(name, strs):
    r = _rng("elf", name)
    blob = bytearray(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 8 + b"\x03\x00\xb7\x00")
    blob += bytes(r.getrandbits(8) for _ in range(2000))
    for s in strs:
        blob += s.encode() + b"\x00" + bytes(r.getrandbits(8) for _ in range(300))
    blob += bytes(r.getrandbits(8) for _ in range(30000))
    return bytes(blob)


def _png(w, h, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def build_apk(path=APK_PATH):
    """Build the downloadable APK (a ZIP laid out like a release RN build)."""
    entries = [
        ("AndroidManifest.xml", _android_manifest().encode()),
        ("classes.dex", _dex()),
        ("resources.arsc", b"\x02\x00\x0c\x00" + _rng("arsc").randbytes(9000)),
        ("assets/index.android.bundle", _android_bundle().encode()),
        ("assets/fonts/ATBSans-Regular.ttf", b"\x00\x01\x00\x00" + _rng("ttf").randbytes(6000)),
        ("res/values/strings.xml", _strings_xml().encode()),
        ("res/xml/network_security_config.xml", _network_security_config().encode()),
        ("res/mipmap-xxhdpi/ic_launcher.png", _png(144, 144, (0xe2, 0x00, 0x1a))),
        ("res/mipmap-mdpi/ic_launcher.png", _png(48, 48, (0xe2, 0x00, 0x1a))),
        ("res/drawable/splash_logo.png", _png(288, 96, (0xff, 0xff, 0xff))),
        ("smali/ua/com/atbmarket/BuildConfig.smali", _build_config_smali().encode()),
        ("lib/arm64-v8a/libjsc.so", _elf("jsc", ["JSGlobalContextCreate", "JSEvaluateScript"])),
        ("lib/arm64-v8a/libreactnativejni.so",
         _elf("rnjni", ["Java_com_facebook_react_bridge_CatalystInstanceImpl_initializeBridge",
                        "assets://index.android.bundle", "loadScriptFromAssets"])),
        ("lib/arm64-v8a/libc++_shared.so", _elf("cxx", ["_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEE"])),
        ("kotlin/kotlin.kotlin_builtins", _rng("kt").randbytes(3000)),
        ("okhttp3/internal/publicsuffix/publicsuffixes.gz", zlib.compress(b"com\nua\ncom.ua\n" * 400)),
    ]
    mf = ["Manifest-Version: 1.0", "Built-By: Signflinger", "Created-By: Android Gradle 8.2.1", ""]
    for name, data in entries:
        mf += [f"Name: {name}", "SHA-256-Digest: " + base64.b64encode(hashlib.sha256(data).digest()).decode(), ""]
    mf_bytes = ("\r\n".join(mf) + "\r\n").encode()
    sf = ("Signature-Version: 1.0\r\nCreated-By: 1.0 (Android)\r\nSHA-256-Digest-Manifest: "
          + base64.b64encode(hashlib.sha256(mf_bytes).digest()).decode()
          + "\r\nX-Android-APK-Signed: 2, 3\r\n\r\n").encode()
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
        zf.writestr("META-INF/MANIFEST.MF", mf_bytes)
        zf.writestr("META-INF/CERT.SF", sf)
        zf.writestr("META-INF/CERT.RSA", b"\x30\x82\x05\x8a" + _rng("rsa").randbytes(1400))
    os.replace(tmp, path)
    return path


# --------------------------------------------------------------------------- OpenAPI
def _openapi():
    def op(summary, tag, sec="basic", params=None, body=None, resp="object"):
        o = {"summary": summary, "tags": [tag],
             "responses": {"200": {"description": "OK"},
                           "401": {"$ref": "#/components/responses/Unauthorized"}}}
        if sec:
            o["security"] = [{sec + "Auth": []}]
        if params:
            o["parameters"] = params
        if body:
            o["requestBody"] = {"required": True, "content": {"application/json": {"schema": body}}}
        return o

    q = lambda n, t="string", d="": {"name": n, "in": "query", "required": False,
                                     "schema": {"type": t}, "description": d}
    p = lambda n, d="": {"name": n, "in": "path", "required": True,
                         "schema": {"type": "string"}, "description": d}
    login = op("Request an SMS one-time code for a phone number", "Registration",
               body={"type": "object", "required": ["phoneNumber"],
                     "properties": {"phoneNumber": {"type": "string", "example": "+380671234567"}}})
    login["responses"]["201"] = {"description": "OTP challenge created"}
    return {
        "openapi": "3.0.3",
        "info": {"title": "ATB Mobile Gateway API", "version": GATEWAY_VERSION,
                 "description": "Backend for the ATB Market Android/iOS apps. "
                                "Client endpoints authenticate the app build with HTTP Basic; "
                                "member endpoints use the Bearer access token issued by /register/verify.",
                 "contact": {"name": "ATB Mobile Team", "email": "mobile@atbmarket.com"}},
        "servers": [{"url": API_BASE, "description": "production"},
                    {"url": "https://mobapp-stage.atbmarket.com", "description": "staging"}],
        "tags": [{"name": n} for n in ["Registration", "Catalogue", "Member", "Loyalty", "Service"]],
        "paths": {
            "/register/login": {"post": login},
            "/register/verify": {"post": op("Verify the OTP and obtain tokens", "Registration",
                                            body={"type": "object", "required": ["token", "otp"],
                                                  "properties": {"token": {"type": "string"},
                                                                 "otp": {"type": "string", "example": "123456"}}})},
            "/register/refresh": {"post": op("Exchange a refresh token", "Registration",
                                             body={"type": "object", "properties": {"refreshToken": {"type": "string"}}})},
            "/register/logout": {"post": op("Revoke the current access token", "Registration", sec="bearer")},
            "/api/v1/config": {"get": op("Remote app configuration", "Catalogue")},
            "/api/v1/stores": {"get": op("Store finder", "Catalogue", params=[
                q("city"), q("q", d="address search"), q("service"), q("lat", "number"), q("lng", "number"),
                q("radius", "integer", "metres"), q("page", "integer"), q("size", "integer")])},
            "/api/v1/stores/{id}": {"get": op("Store details", "Catalogue", params=[p("id", "e.g. ST0001")])},
            "/api/v1/promo/weekly": {"get": op("Current weekly promo catalogue", "Catalogue",
                                               params=[q("category")])},
            "/api/v1/profile": {"get": op("Current member profile", "Member", sec="bearer"),
                                "patch": op("Update member profile", "Member", sec="bearer",
                                            body={"type": "object", "properties": {
                                                k: {"type": "string"} for k in
                                                ["firstName", "lastName", "email", "birthDate", "city", "language"]}})},
            "/api/v1/loyalty/card": {"get": op("Member loyalty card", "Loyalty", sec="bearer")},
            "/api/v1/loyalty/card/{cardNumber}": {"get": op("Loyalty card by number (cashier / family cards)",
                                                            "Loyalty", sec="bearer", params=[p("cardNumber")])},
            "/api/v1/loyalty/transactions": {"get": op("Points history", "Loyalty", sec="bearer")},
            "/api/v1/coupons": {"get": op("Personal coupons", "Loyalty", sec="bearer")},
            "/api/v1/coupons/{id}/activate": {"post": op("Activate a coupon", "Loyalty", sec="bearer",
                                                         params=[p("id")])},
            "/api/version": {"get": op("Gateway build info", "Service", sec=None)},
            "/api/v1/health": {"get": op("Health check", "Service", sec=None)},
        },
        "components": {
            "securitySchemes": {"basicAuth": {"type": "http", "scheme": "basic",
                                              "description": "App client credential (per build)"},
                                "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}},
            "responses": {"Unauthorized": {"description": "Missing or invalid credentials",
                                           "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}}},
            "schemas": {"Error": {"type": "object", "properties": {
                "error": {"type": "object", "properties": {"code": {"type": "string"},
                                                           "message": {"type": "string"}}},
                "requestId": {"type": "string"}}}},
        },
    }


# --------------------------------------------------------------------------- HTML
CSS = """
:root{--red:#e2001a;--red2:#b80016;--ink:#1c1c1c;--mute:#5d6470;--bg:#f4f5f7;--card:#fff;--line:#e6e8ec}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
background:var(--bg);color:var(--ink);line-height:1.5}a{color:var(--red)}
.nav{background:var(--red);color:#fff}.nav .in{max-width:1080px;margin:0 auto;padding:12px 16px;display:flex;
align-items:center;gap:18px;flex-wrap:wrap}.logo{font-weight:900;font-size:24px;letter-spacing:1px;color:#fff;text-decoration:none}
.logo small{font-weight:500;font-size:12px;opacity:.85;margin-left:6px}.nav a.l{color:#fff;text-decoration:none;font-size:14px;opacity:.92}
.nav a.l:hover{opacity:1;text-decoration:underline}.sp{flex:1}
.wrap{max-width:1080px;margin:0 auto;padding:20px 16px 40px}
.hero{display:grid;grid-template-columns:1.2fr .8fr;gap:24px;align-items:center;background:var(--card);border-radius:18px;
padding:28px;box-shadow:0 6px 24px rgba(0,0,0,.07)}.hero h1{font-size:34px;line-height:1.15;margin:0 0 10px}
.hero p{color:var(--mute);margin:0 0 18px}.btns{display:flex;gap:10px;flex-wrap:wrap}
.btn{display:inline-block;background:var(--red);color:#fff;text-decoration:none;font-weight:700;padding:12px 18px;border-radius:12px}
.btn:hover{background:var(--red2)}.btn.ghost{background:#fff;color:var(--ink);border:1px solid var(--line)}
.phone{justify-self:center;width:220px;height:420px;border-radius:34px;background:#111;padding:12px;box-shadow:0 18px 40px rgba(0,0,0,.25)}
.screen{background:#fff;border-radius:24px;height:100%;overflow:hidden;display:flex;flex-direction:column}
.screen .bar{background:var(--red);color:#fff;font-weight:800;padding:14px;font-size:15px}
.screen .cardv{margin:12px;border-radius:14px;background:linear-gradient(135deg,#e2001a,#ff5a3c);color:#fff;padding:14px;font-size:12px}
.screen .cardv b{display:block;font-size:22px}.bars{height:34px;margin-top:8px;background:repeating-linear-gradient(90deg,#fff 0 2px,transparent 2px 4px,#fff 4px 5px,transparent 5px 8px)}
.screen .row{margin:6px 12px;padding:9px;border:1px solid var(--line);border-radius:10px;font-size:12px}
h2{font-size:22px;margin:30px 0 12px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.tile{background:var(--card);border-radius:14px;padding:16px;box-shadow:0 2px 8px rgba(0,0,0,.05)}
.tile h3{margin:0 0 6px;font-size:16px}.tile p{margin:0;color:var(--mute);font-size:14px}
.promo .tile{position:relative}.old{text-decoration:line-through;color:var(--mute);font-size:13px}.price{font-size:22px;font-weight:800;color:var(--red)}
.pct{position:absolute;top:12px;right:12px;background:var(--red);color:#fff;font-weight:800;font-size:12px;padding:3px 7px;border-radius:8px}
.cat{font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.4px}
table{width:100%;border-collapse:collapse;background:var(--card);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);font-size:14px}th{font-size:12px;color:var(--mute);text-transform:uppercase}
form.f{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}input,select{padding:10px 12px;border:1px solid #c9ced6;border-radius:10px;font-size:14px;background:#fff}
button{background:var(--red);color:#fff;border:0;border-radius:10px;padding:10px 16px;font-weight:700;cursor:pointer}
details{background:var(--card);border-radius:12px;padding:12px 16px;margin-bottom:8px}summary{font-weight:700;cursor:pointer}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}code{background:#eef0f3;padding:1px 6px;border-radius:5px}
pre{background:#14171c;color:#e6e6e6;padding:12px;border-radius:10px;overflow:auto}
.m{font-weight:800;font-size:11px;padding:2px 6px;border-radius:5px;color:#fff;margin-right:6px}.GET{background:#2f7fd3}.POST{background:#1f9d55}.PATCH{background:#c47f00}
.ep{background:var(--card);border-radius:10px;padding:10px 14px;margin-bottom:8px;border-left:4px solid var(--line)}
.ep small{color:var(--mute)}.lock{font-size:12px;color:var(--mute)}
footer{background:#1c1c1c;color:#aab;font-size:13px}footer .in{max-width:1080px;margin:0 auto;padding:24px 16px;display:flex;gap:24px;flex-wrap:wrap}
footer a{color:#dde;text-decoration:none}footer .col{min-width:180px}footer b{color:#fff;display:block;margin-bottom:6px}
@media(max-width:760px){.hero{grid-template-columns:1fr}.phone{display:none}.hero h1{font-size:26px}}
"""


def page(title, body):
    return Response(f"""<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="Мобільний застосунок АТБ-Маркет: картка лояльності, акції тижня, пошук магазинів.">
<link rel="icon" href="/favicon.ico"><style>{CSS}</style></head><body>
<div class="nav"><div class="in"><a class="logo" href="/">АТБ<small>mobile</small></a>
<a class="l" href="/#features">Можливості</a><a class="l" href="/promo">Акції тижня</a><a class="l" href="/stores">Магазини</a>
<a class="l" href="/support">Підтримка</a><span class="sp"></span><a class="l" href="/download/atb-market.apk">Завантажити для Android</a></div></div>
<div class="wrap">{body}</div>
<footer><div class="in"><div class="col"><b>ТОВ «АТБ-Маркет»</b>Дніпро, Україна<br>Гаряча лінія 0 800 500 415 (безкоштовно)<br>mobile@atbmarket.com</div>
<div class="col"><b>Застосунок</b><a href="/download/atb-market.apk">Android APK {APP_VERSION}</a><br><a href="/support">Довідка та FAQ</a><br><a href="/changelog">Що нового</a></div>
<div class="col"><b>Правове</b><a href="/privacy">Політика конфіденційності</a><br><a href="/terms">Умови програми лояльності</a></div>
<div class="col"><b>Партнерам</b><a href="/api/docs">Довідник Mobile API</a><br><a href="/api/v1/health">Стан сервісу</a></div>
<div class="col" style="flex:1;text-align:right">&copy; 2014&ndash;{date.today().year} ТОВ «АТБ-Маркет»</div></div></footer>
</body></html>""", mimetype="text/html")


def _promo_tiles(items):
    return "".join(
        f'<div class="tile"><span class="pct">-{i["discountPercent"]}%</span><div class="cat">{html.escape(i["category"])}</div>'
        f'<h3>{html.escape(i["title"])}</h3><span class="old">{i["oldPrice"]:.2f}</span> '
        f'<span class="price">{i["price"]:.2f} &#8372;</span>'
        + (f'<p>{html.escape(i["badge"])}</p>' if i["badge"] else "") + "</div>" for i in items)


@app.get("/")
def index():
    promo = _weekly_promo()
    body = f"""
<div class="hero"><div><h1>АТБ у твоїй кишені.<br>Купуй. Скануй. Економ.</h1>
<p>Твоя цифрова картка АТБ, персональні купони та щотижневий каталог <b>«Економія»</b> &mdash; оновлюється щочетверга.
Реєстрація за номером телефону менш ніж за хвилину.</p>
<div class="btns"><a class="btn" href="/download/atb-market.apk">&#11015; Завантажити APK ({APP_VERSION})</a>
<a class="btn ghost" href="/promo">Акції цього тижня</a></div>
<p style="font-size:12px;margin-top:12px">Android 6.0+ &middot; 31 МБ &middot; версія для iOS незабаром</p></div>
<div class="phone"><div class="screen"><div class="bar">Моя картка АТБ</div>
<div class="cardv">Олена К. &middot; Gold<b>4 812 балів</b><div class="bars"></div></div>
<div class="row">-15% на всю молочку &middot; <b>Активувати</b></div><div class="row">x3 бали на каву</div>
<div class="row">Найближчий магазин: 350 м</div></div></div></div>
<h2 id="features">Усе потрібне для покупок на тиждень</h2>
<div class="grid">
<div class="tile"><h3>Цифрова картка лояльності</h3><p>Покажи штрихкод на касі, накопичуй бали з кожного чека, розраховуйся балами.</p></div>
<div class="tile"><h3>Персональні купони</h3><p>Купони, підібрані саме для тебе щотижня. Активація в один дотик &mdash; знижка застосовується автоматично.</p></div>
<div class="tile"><h3>Каталог тижня</h3><p>Усі ціни «Економія» на тиждень, зі списком покупок і нагадуваннями.</p></div>
<div class="tile"><h3>Пошук магазинів</h3><p>{len(STORES)}+ магазинів на мапі з годинами роботи та послугами.</p></div>
<div class="tile"><h3>Швидка реєстрація</h3><p>Лише номер телефону та SMS-код &mdash; жодних паролів запам'ятовувати.</p></div>
<div class="tile"><h3>Електронні чеки</h3><p>Історія покупок і рух балів завжди під рукою.</p></div></div>
<h2>Тиждень «Економія» &middot; {promo["validFrom"]} &ndash; {promo["validTo"]}</h2>
<div class="grid promo">{_promo_tiles(promo["items"][:8])}</div>
<p><a href="/promo">Переглянути всі {len(promo["items"])} пропозицій &rarr;</a></p>
<h2>Питання</h2>
<details><summary>Як встановити застосунок?</summary><p>Завантаж Android-пакет із цієї сторінки та дозволь встановлення з цього джерела, коли з'явиться запит. Розміщення в магазинах оновлюється.</p></details>
<details><summary>Не прийшов SMS-код</summary><p>Зачекай 60 секунд і натисни «Надіслати ще раз». Перевір, що номер у форматі +380. Досі нічого? Телефонуй 0 800 500 415.</p></details>
<details><summary>Чи можу я залишити пластикову картку?</summary><p>Так. Введи її номер у розділі Профіль &rarr; Картки, і бали об'єднаються з цифровою карткою.</p></details>
<details><summary>Я розробник / партнер</summary><p>Довідник API мобільного шлюзу опубліковано за адресою <a href="/api/docs">/api/docs</a>
(<a href="/api/v1/openapi.json">OpenAPI 3 JSON</a>). Доступ клієнта потребує виданого облікового запису застосунку.</p></details>
"""
    return page("АТБ-Маркет — Мобільний застосунок", body)


@app.get("/promo")
def promo_page():
    promo = _weekly_promo()
    cat = request.args.get("category", "")
    items = [i for i in promo["items"] if not cat or i["category"] == cat]
    cats = sorted({i["category"] for i in promo["items"]})
    opts = "".join(f'<option{" selected" if c == cat else ""}>{html.escape(c)}</option>' for c in cats)
    body = (f'<h2>Тиждень «Економія» &middot; {promo["validFrom"]} &ndash; {promo["validTo"]}</h2>'
            f'<form class="f"><select name="category"><option value="">Усі категорії</option>{opts}</select>'
            f'<button>Фільтр</button></form><div class="grid promo">{_promo_tiles(items)}</div>')
    return page("Акції тижня — АТБ-Маркет", body)


@app.get("/stores")
def stores_page():
    city = request.args.get("city", "")
    qs = (request.args.get("q") or "").strip().lower()
    rows = [s for s in STORES if (not city or s["city"] == city) and (not qs or qs in s["address"].lower())]
    opts = "".join(f'<option{" selected" if c[0] == city else ""}>{c[0]}</option>' for c in CITIES)
    tr = "".join(
        f'<tr><td>{s["id"]}</td><td>{s["format"]}</td><td>{s["city"]}</td><td>{html.escape(s["address"])}</td>'
        f'<td>{s["hours"]["mon_sat"]}</td><td>{", ".join(x.replace("_", " ") for x in s["services"])}</td></tr>'
        for s in rows[:200])
    body = (f'<h2>Пошук магазинів</h2><form class="f"><select name="city"><option value="">Усі міста</option>{opts}</select>'
            f'<input name="q" placeholder="Вулиця" value="{html.escape(qs)}"><button>Пошук</button></form>'
            f'<p>{len(rows)} магазин(ів)</p><table><thead><tr><th>ID</th><th>Формат</th><th>Місто</th><th>Адреса</th>'
            f'<th>Години</th><th>Послуги</th></tr></thead><tbody>{tr}</tbody></table>')
    return page("Магазини — АТБ-Маркет", body)


@app.get("/support")
def support_page():
    body = """<h2>Довідка та підтримка</h2><div class="grid">
<div class="tile"><h3>Гаряча лінія</h3><p>0 800 500 415 &mdash; безкоштовно з будь-якого українського номера, щодня 08:00&ndash;21:00.</p></div>
<div class="tile"><h3>E-mail</h3><p>mobile@atbmarket.com &mdash; будь ласка, вкажи свій номер телефону та версію застосунку (Профіль &rarr; Про застосунок).</p></div>
<div class="tile"><h3>Загублена картка</h3><p>Твої бали прив'язані до номера телефону. Увійди на новому пристрої &mdash; і цифрова картка відновиться.</p></div></div>
<h2>Відомі проблеми у 8.0.48</h2><ul><li>На деяких пристроях Xiaomi мапа може показувати магазини без годин роботи &mdash; виправлення у 8.0.50.</li>
<li>Push-сповіщення затримуються на Android 14, коли увімкнено режим енергозбереження.</li></ul>"""
    return page("Підтримка — АТБ-Маркет", body)


@app.get("/changelog")
def changelog_page():
    body = """<h2>Що нового</h2>
<div class="tile"><h3>8.0.48</h3><p>Оновлений екран купонів; швидший штрихкод картки; виправлення помилок.</p></div><br>
<div class="tile"><h3>8.0.30</h3><p>Фільтри пошуку магазинів за послугами (банкомат, пекарня, поштомати). Експорт історії балів.</p></div><br>
<div class="tile"><h3>8.0.16</h3><p>Нова реєстрація за номером телефону + SMS-код. Каталог тижня зі списком покупок.</p></div>"""
    return page("Що нового — АТБ-Маркет", body)


@app.get("/privacy")
def privacy_page():
    body = """<h2>Політика конфіденційності</h2><p>ТОВ «АТБ-Маркет» обробляє твій номер телефону, ім'я, дату народження, історію покупок та
приблизне місцезнаходження для роботи програми лояльності, персоналізації пропозицій і показу магазинів поблизу. Дані зберігаються в
Україні впродовж усього членства плюс 3 роки. Ти можеш запросити експорт або видалення своїх даних
на mobile@atbmarket.com.</p><p>Аналітика та звіти про збої збираються без рекламних ідентифікаторів.</p>"""
    return page("Конфіденційність — АТБ-Маркет", body)


@app.get("/terms")
def terms_page():
    body = """<h2>Умови програми лояльності</h2><ol><li>1 бал нараховується за кожні 10 грн у чеку (крім тютюну та алкоголю).</li>
<li>10 балів = 1 грн при розрахунку балами; бали згорають через 12 місяців після останньої покупки.</li>
<li>Рівні: Standard, Silver (2 500 балів/рік), Gold (8 000), Platinum (20 000).</li>
<li>Одна цифрова картка на один номер телефону. Персональні купони не передаються іншим особам.</li></ol>"""
    return page("Умови — АТБ-Маркет", body)


@app.get("/api/docs")
def api_docs():
    ip = atblog.client_ip(request)
    atblog.log("mobapp.api_docs_view", ip, path=request.path)
    spec = _openapi()
    eps = []
    for path, ops in spec["paths"].items():
        for m, o in ops.items():
            sec = o.get("security")
            lock = ("Basic (app client)" if sec and "basicAuth" in sec[0]
                    else "Bearer (member)" if sec else "public")
            eps.append(f'<div class="ep"><span class="m {m.upper()}">{m.upper()}</span><code>{html.escape(path)}</code> '
                       f'<small>{html.escape(o["summary"])}</small> <span class="lock">&middot; {lock}</span></div>')
    body = (f'<h2>{spec["info"]["title"]} <small style="font-size:14px;color:#888">v{spec["info"]["version"]}</small></h2>'
            f'<p>{html.escape(spec["info"]["description"])}</p>'
            f'<p>Machine-readable spec: <a href="/api/v1/openapi.json">/api/v1/openapi.json</a> &middot; '
            f'Servers: {", ".join("<code>" + s["url"] + "</code>" for s in spec["servers"])}</p>'
            + "".join(eps) +
            '<h2>Процес реєстрації</h2><pre>POST /register/login   {"phoneNumber":"+380671234567"}      (Basic)\n'
            '  -> 201 {"token":"&lt;challenge&gt;","expiresIn":180,...}\n'
            'POST /register/verify  {"token":"&lt;challenge&gt;","otp":"123456"}  (Basic)\n'
            '  -> 200 {"accessToken":"...","refreshToken":"..."}\n'
            'GET  /api/v1/profile   Authorization: Bearer &lt;accessToken&gt;</pre>')
    return page("API reference - ATB Mobile Gateway", body)


@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /api/\nDisallow: /register/\nAllow: /\n", mimetype="text/plain")


@app.get("/.well-known/assetlinks.json")
def assetlinks():
    return jsonify([{"relation": ["delegate_permission/common.handle_all_urls"],
                     "target": {"namespace": "android_app", "package_name": "ua.com.atbmarket",
                                "sha256_cert_fingerprints": [
                                    "6F:1A:93:0C:B2:47:E5:8D:21:7C:4E:A0:9B:3F:D6:52:88:C1:0E:7A:44:B9:F3:12:65:DE:08:A7:3C:91:5B:E4"]}}])


@app.get("/favicon.ico")
def favicon():
    return Response(_png(32, 32, (0xe2, 0x00, 0x1a)), mimetype="image/png")


@app.get("/download/atb-market.apk")
def download_apk():
    ip = atblog.client_ip(request)
    atblog.log("mobapp.apk_download", ip, path="/download/atb-market.apk",
               file="atb-market.apk", msg="ATB mobile app package downloaded")
    if not os.path.exists(APK_PATH):
        build_apk(APK_PATH)
    return send_file(APK_PATH, mimetype="application/vnd.android.package-archive",
                     as_attachment=True, download_name="atb-market.apk")


# --------------------------------------------------------------------------- API: registration
def _phone_ok(phone):
    d = "".join(c for c in phone if c.isdigit())
    return phone.strip().startswith("+380") and len(d) == 12


@app.post("/register/login")
def register_login():
    ip = atblog.client_ip(request)
    creds = _check_basic(request.headers.get("Authorization", ""))
    body = request.get_json(silent=True) or {}
    phone = str(body.get("phoneNumber", "")).replace(" ", "")
    if not creds:
        atblog.log("mobapp.auth_missing", ip, path="/register/login")
        return err(401, "AUTH_REQUIRED", "Client authentication required")
    user, pw = creds
    if not (user == REG_USER and pw == REG_PASS):
        atblog.log("mobapp.auth_fail", ip, user=user, phone=phone)
        return err(401, "INVALID_CLIENT", "Invalid client credentials")
    atblog.log("mobapp.hardcoded_cred_used", ip, user=user, phone=phone,
               msg="APK hard-coded reg credentials accepted")
    if not phone:
        return err(400, "VALIDATION_ERROR", "phoneNumber is required", field="phoneNumber")
    if not _phone_ok(phone):
        return err(422, "PHONE_INVALID", "Phone number must be in +380XXXXXXXXX format", field="phoneNumber")
    otp = f"{secrets.randbelow(10**6):06d}"
    cid = uuid.uuid4().hex
    now = int(time.time())
    CHALLENGES[cid] = {"phone": phone, "otp": otp, "exp": now + OTP_TTL, "attempts": 0}
    token = jwt_encode({"typ": "otp_challenge", "cid": cid, "phone": phone[:6] + "***" + phone[-2:],
                        "iat": now, "exp": now + OTP_TTL})
    atblog.log("mobapp.otp_requested", ip, phone=phone, challenge=cid)
    resp = jsonify(token=token, challengeId=cid, message="Auth OTP was sent...",
                   channel="sms", otpLength=6, expiresIn=OTP_TTL, resendIn=60)
    resp.status_code = 201
    # leftover from the SMS-provider integration test toggle
    resp.headers["X-Debug-OTP"] = otp
    return resp


def _issue_tokens(phone):
    now = int(time.time())
    card = _card_for_phone(phone)
    sub = "m_" + hashlib.sha1(phone.encode()).hexdigest()[:12]
    access = jwt_encode({"typ": "access", "sub": sub, "phone": phone, "card": card,
                         "scope": "profile loyalty coupons", "jti": uuid.uuid4().hex,
                         "iat": now, "exp": now + JWT_TTL})
    refresh = jwt_encode({"typ": "refresh", "sub": sub, "phone": phone, "jti": uuid.uuid4().hex,
                          "iat": now, "exp": now + 30 * 86400})
    return {"accessToken": access, "refreshToken": refresh, "tokenType": "Bearer",
            "expiresIn": JWT_TTL, "memberId": sub,
            "isNewMember": int(hashlib.md5(phone.encode()).hexdigest(), 16) % 3 == 0}


@app.post("/register/verify")
def register_verify():
    deny = require_service_auth()
    if deny:
        return deny
    ip = atblog.client_ip(request)
    body = request.get_json(silent=True) or request.form or {}
    tok, otp = str(body.get("token") or body.get("challengeId") or ""), str(body.get("otp") or "")
    cid = tok
    if "." in tok:
        data = jwt_decode(tok)
        cid = data.get("cid") if data else None
    ch = CHALLENGES.get(cid or "")
    if not ch or ch["exp"] < time.time():
        return err(410, "CHALLENGE_EXPIRED", "Code expired, request a new one")
    if not otp:
        return err(400, "VALIDATION_ERROR", "otp is required", field="otp")
    if ch["attempts"] >= 5:
        CHALLENGES.pop(cid, None)
        atblog.log("mobapp.otp_lockout", ip, phone=ch["phone"])
        return err(429, "TOO_MANY_ATTEMPTS", "Too many attempts, request a new code")
    if not hmac.compare_digest(otp, ch["otp"]):
        ch["attempts"] += 1
        atblog.log("mobapp.otp_verify_fail", ip, phone=ch["phone"], attempts=ch["attempts"])
        return err(401, "OTP_INVALID", "Invalid confirmation code", attemptsLeft=5 - ch["attempts"])
    CHALLENGES.pop(cid, None)
    atblog.log("mobapp.otp_verify_ok", ip, phone=ch["phone"])
    return jsonify(_issue_tokens(ch["phone"]))


@app.post("/register/refresh")
def register_refresh():
    deny = require_service_auth()
    if deny:
        return deny
    body = request.get_json(silent=True) or {}
    data = jwt_decode(str(body.get("refreshToken", "")))
    if not data or data.get("typ") != "refresh":
        return err(401, "TOKEN_INVALID", "Refresh token is invalid or expired")
    return jsonify(_issue_tokens(data["phone"]))


@app.post("/register/logout")
def register_logout():
    claims, deny = require_member()
    if deny:
        return deny
    REVOKED.add(claims.get("jti"))
    return jsonify(ok=True)


# --------------------------------------------------------------------------- API: catalogue
@app.get("/api/v1/config")
def api_config():
    deny = require_service_auth()
    if deny:
        return deny
    atblog.log("mobapp.api_request", atblog.client_ip(request), path=request.path, user=REG_USER)
    return jsonify({
        "minSupportedVersion": "8.0.16", "latestVersion": APP_VERSION, "forceUpdate": False,
        "updateUrl": API_BASE + "/download/atb-market.apk",
        "maintenance": {"enabled": False, "message": None},
        "features": {"coupons": True, "eReceipts": True, "payWithPoints": True,
                     "storeMapClustering": True, "familyCards": True, "chatSupport": False,
                     "applePay": False, "newOnboarding": {"enabled": True, "rollout": 35}},
        "otp": {"length": 6, "ttlSec": OTP_TTL, "resendSec": 60, "maxAttempts": 5},
        "endpoints": {"api": API_BASE, "cdn": "https://static.atbmarket.com/mobile/",
                      "promoImages": "https://static.atbmarket.com/promo/",
                      "privacy": API_BASE + "/privacy", "terms": API_BASE + "/terms"},
        "support": {"phone": "0 800 500 415", "email": "mobile@atbmarket.com"},
        "loyalty": {"pointsPerUah": 0.1, "pointValueUah": 0.1, "tiers": [{"name": t, "points": p} for t, p in TIERS]},
        "remoteConfigVersion": 412,
    })


@app.get("/api/v1/stores")
def api_stores():
    deny = require_service_auth()
    if deny:
        return deny
    a = request.args
    items = STORES
    if a.get("city"):
        items = [s for s in items if s["city"].lower() == a["city"].lower()]
    if a.get("q"):
        items = [s for s in items if a["q"].lower() in s["address"].lower()]
    if a.get("service"):
        items = [s for s in items if a["service"] in s["services"]]
    try:
        if a.get("lat") and a.get("lng"):
            import math
            lat, lng, radius = float(a["lat"]), float(a["lng"]), float(a.get("radius", 5000))
            def dist(s):
                dx = (s["lng"] - lng) * 111320 * math.cos(math.radians(lat))
                dy = (s["lat"] - lat) * 110540
                return math.hypot(dx, dy)
            items = sorted(({**s, "distanceM": int(dist(s))} for s in items), key=lambda s: s["distanceM"])
            items = [s for s in items if s["distanceM"] <= radius]
        page_n = max(1, int(a.get("page", 1)))
        size = min(100, max(1, int(a.get("size", 20))))
    except ValueError:
        return err(400, "VALIDATION_ERROR", "lat, lng, radius, page and size must be numeric")
    atblog.log("mobapp.api_request", atblog.client_ip(request), path=request.path, user=REG_USER)
    return jsonify(total=len(items), page=page_n, size=size,
                   items=items[(page_n - 1) * size: page_n * size])


@app.get("/api/v1/stores/<sid>")
def api_store(sid):
    deny = require_service_auth()
    if deny:
        return deny
    s = next((x for x in STORES if x["id"] == sid.upper()), None)
    if not s:
        return err(404, "NOT_FOUND", f"Store {sid} not found")
    return jsonify(s)


@app.get("/api/v1/promo/weekly")
def api_promo():
    deny = require_service_auth()
    if deny:
        return deny
    atblog.log("mobapp.api_request", atblog.client_ip(request), path=request.path, user=REG_USER)
    promo = _weekly_promo()
    if request.args.get("category"):
        promo["items"] = [i for i in promo["items"] if i["category"].lower() == request.args["category"].lower()]
    promo["total"] = len(promo["items"])
    return jsonify(promo)


# --------------------------------------------------------------------------- API: member
@app.route("/api/v1/profile", methods=["GET", "PATCH"])
def api_profile():
    claims, deny = require_member()
    if deny:
        return deny
    if request.method == "PATCH":
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return err(400, "VALIDATION_ERROR", "JSON object body required")
        allowed = {"firstName", "lastName", "email", "birthDate", "city", "language", "marketingConsent"}
        bad = sorted(set(body) - allowed)
        if bad:
            return err(422, "FIELD_NOT_EDITABLE", "Some fields cannot be changed", fields=bad)
        PROFILE_EDITS.setdefault(claims["card"], {}).update(
            {k: (v if k == "marketingConsent" else str(v)[:80]) for k, v in body.items()})
        atblog.log("mobapp.profile_update", atblog.client_ip(request), member=claims["sub"],
                   fields=sorted(body))
    return jsonify(_profile(claims))


@app.get("/api/v1/loyalty/card")
def api_card():
    claims, deny = require_member()
    if deny:
        return deny
    return jsonify(_card_payload(claims["card"], own=True, phone=claims["phone"]))


@app.get("/api/v1/loyalty/card/<number>")
def api_card_lookup(number):
    claims, deny = require_member()
    if deny:
        return deny
    if not (number.isdigit() and len(number) == 13 and number.startswith("29")):
        return err(400, "CARD_INVALID", "Card number must be 13 digits starting with 29")
    own = number == claims["card"]
    if not own:
        atblog.log("mobapp.card_lookup_other", atblog.client_ip(request), member=claims["sub"],
                   card=number, msg="loyalty card of another member read")
    return jsonify(_card_payload(number, own=own, phone=claims["phone"] if own else None))


@app.get("/api/v1/loyalty/transactions")
def api_transactions():
    claims, deny = require_member()
    if deny:
        return deny
    r = _rng("tx", claims["card"])
    now = datetime.now(timezone.utc)
    items = []
    for i in range(r.randint(8, 25)):
        amt = round(r.uniform(45, 1800), 2)
        st = r.choice(STORES)
        items.append({"id": f"RC{r.randint(10**9, 10**10 - 1)}",
                      "date": (now - timedelta(days=i * r.randint(1, 4), hours=r.randint(0, 12))).isoformat(timespec="seconds"),
                      "storeId": st["id"], "store": f'{st["city"]}, {st["address"]}',
                      "amountUah": amt, "pointsEarned": int(amt // 10),
                      "pointsSpent": r.choice([0, 0, 0, 0, 100, 250])})
    return jsonify(total=len(items), items=items)


@app.get("/api/v1/coupons")
def api_coupons():
    claims, deny = require_member()
    if deny:
        return deny
    items = _coupons(claims["card"])
    return jsonify(total=len(items), items=items)


@app.post("/api/v1/coupons/<cid>/activate")
def api_coupon_activate(cid):
    claims, deny = require_member()
    if deny:
        return deny
    coupons = {c["id"]: c for c in _coupons(claims["card"])}
    if cid not in coupons:
        return err(404, "NOT_FOUND", "Coupon not found")
    ACTIVATED.setdefault(claims["card"], set()).add(cid)
    atblog.log("mobapp.coupon_activate", atblog.client_ip(request), member=claims["sub"], coupon=cid)
    return jsonify({**coupons[cid], "activated": True})


# --------------------------------------------------------------------------- API: service
@app.get("/api/v1/openapi.json")
@app.get("/api/openapi.json")
def openapi_json():
    atblog.log("mobapp.openapi_fetch", atblog.client_ip(request), path=request.path)
    return jsonify(_openapi())


@app.get("/api/version")
@app.get("/api/v1/version")
def api_version():
    return jsonify(service="atb-mobile-gateway", version=GATEWAY_VERSION, build=GATEWAY_BUILD,
                   apiVersions=["v1"], minClientVersion="8.0.16", env="production")


@app.get("/api/v1/health")
def api_health():
    return jsonify(status="UP", checks={"loyaltyCore": "UP", "smsGateway": "UP", "promoCache": "UP",
                                        "storeIndex": "UP"}, time=datetime.now(timezone.utc).isoformat(timespec="seconds"))


@app.get("/healthz")
def healthz():
    return "ok", 200


@app.errorhandler(404)
def nf(e):
    if _is_api():
        return err(404, "NOT_FOUND", "Resource not found")
    return page("Not found - ATB Market", '<h2>Page not found</h2><p><a href="/">Back to the home page</a></p>'), 404


@app.errorhandler(405)
def mna(e):
    if _is_api():
        return err(405, "METHOD_NOT_ALLOWED", f"{request.method} not allowed on {request.path}")
    return page("Not allowed", "<h2>Method not allowed</h2>"), 405


@app.errorhandler(500)
def ise(e):
    if _is_api():
        return err(500, "INTERNAL_ERROR", "Unexpected error")
    return page("Error", "<h2>Something went wrong</h2>"), 500


# Build the downloadable package once at startup.
try:
    build_apk(APK_PATH)
except OSError:
    pass


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80, threaded=True)
