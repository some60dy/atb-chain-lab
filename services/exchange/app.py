"""Step 9 - ex.atbmarket.com Microsoft Exchange EWS + OWA mock.

Speaks a minimal Exchange Web Services (EWS) SOAP endpoint protected by HTTP
Basic auth, plus a clickable Outlook Web Access (OWA) browser UI. Valid creds
(supplier@atbmarket.com:supplier123569) unlock a FindItem response / inbox view
whose contents include live password-reset GUID links.

Both the EWS XML and the OWA UI are rendered from the SAME inbox message set
(`_build_inbox`), so they can never drift.

TLS is omitted for the lab; the compose layer maps plain HTTP to port 8444.
"""
import base64
import html
import uuid

from flask import Flask, request, Response, redirect, make_response
import atblog

app = Flask(__name__)

EWS_USER = "supplier@atbmarket.com"
EWS_PASS = "supplier123569"

RESET_BASE = "https://supplier.atbmarket.com/index.php?entryPoint=Changenewpassword&guid="

OWA_COOKIE = "owa_session"
BLUE = "#0078d4"


def _parse_basic(hdr):
    """Return (user, pass) from a Basic auth header, or None."""
    if not hdr or not hdr.startswith("Basic "):
        return None
    try:
        raw = base64.b64decode(hdr.split(" ", 1)[1]).decode("utf-8", "replace")
        user, _, pw = raw.partition(":")
        return user, pw
    except Exception:
        return None


def _unauthorized():
    resp = Response("Unauthorized", status=401)
    resp.headers["WWW-Authenticate"] = 'Basic realm="ews"'
    return resp


# --------------------------------------------------------------------------- #
# Inbox model - the single source of truth for BOTH the EWS XML response and  #
# the OWA browser UI. Fresh reset GUIDs (uuid4) are minted on every call, just #
# as the original EWS mock did.                                               #
# --------------------------------------------------------------------------- #
def _build_inbox():
    """Return the inbox as a list of message dicts.

    Keys: id, subject, sender, received, preview, is_reset, reset_link,
          body_html, importance, is_read, size.
    """
    def reset(subject, mid, sender):
        guid = uuid.uuid4()
        link = RESET_BASE + str(guid)
        return {
            "id": mid,
            "subject": subject,
            "sender": sender,
            "received": f"2024-05-1{mid}T09:2{mid}:11Z",
            "preview": f"Please reset your password. Click the secure link to continue: {link}",
            "is_reset": True,
            "reset_link": link,
            "body_html": (f'<html><body>To reset your password click '
                          f'<a href="{link}">{link}</a></body></html>'),
            "importance": "High",
            "is_read": False,
            "size": 5120,
        }

    def plain(subject, mid, sender, preview):
        return {
            "id": mid,
            "subject": subject,
            "sender": sender,
            "received": f"2024-05-0{mid}T14:0{mid}:03Z",
            "preview": preview,
            "is_reset": False,
            "reset_link": None,
            "body_html": f"<html><body>{preview}</body></html>",
            "importance": "Normal",
            "is_read": True,
            "size": 3072,
        }

    return [
        plain("Weekly logistics report", 1, "logistics@atbmarket.com",
              "Attached is the weekly logistics summary for review."),
        reset("Password reset - action required", 2,
              "no-reply@supplier.atbmarket.com"),
        plain("Invoice #44821 approved", 3, "finance@atbmarket.com",
              "Your invoice has been approved and scheduled for payment."),
        reset("Password reset - action required", 4,
              "no-reply@supplier.atbmarket.com"),
        plain("Supplier portal maintenance window", 5, "it-ops@atbmarket.com",
              "Scheduled maintenance this weekend; expect brief downtime."),
    ]


def _xml_message(m):
    """Render one inbox dict as an EWS <t:Message> fragment (byte-identical to
    the original mock's output)."""
    if m["is_reset"]:
        link = m["reset_link"]
        body = (f'&lt;html&gt;&lt;body&gt;To reset your password click '
                f'&lt;a href="{link}"&gt;{link}&lt;/a&gt;&lt;/body&gt;&lt;/html&gt;')
        return f"""      <t:Message>
        <t:ItemId Id="AAMk{m['id']}=" ChangeKey="CQAAAB{m['id']}"/>
        <t:Subject>{m['subject']}</t:Subject>
        <t:Sensitivity>Normal</t:Sensitivity>
        <t:DateTimeReceived>{m['received']}</t:DateTimeReceived>
        <t:Size>5120</t:Size>
        <t:Importance>High</t:Importance>
        <t:IsRead>false</t:IsRead>
        <t:From>
          <t:Mailbox>
            <t:Name>{m['sender']}</t:Name>
            <t:EmailAddress>{m['sender']}</t:EmailAddress>
            <t:RoutingType>SMTP</t:RoutingType>
          </t:Mailbox>
        </t:From>
        <t:Preview>{m['preview']}</t:Preview>
        <t:Body BodyType="HTML">{body}</t:Body>
      </t:Message>"""
    return f"""      <t:Message>
        <t:ItemId Id="AAMk{m['id']}=" ChangeKey="CQAAAB{m['id']}"/>
        <t:Subject>{m['subject']}</t:Subject>
        <t:Sensitivity>Normal</t:Sensitivity>
        <t:DateTimeReceived>{m['received']}</t:DateTimeReceived>
        <t:Size>3072</t:Size>
        <t:Importance>Normal</t:Importance>
        <t:IsRead>true</t:IsRead>
        <t:From>
          <t:Mailbox>
            <t:Name>{m['sender']}</t:Name>
            <t:EmailAddress>{m['sender']}</t:EmailAddress>
            <t:RoutingType>SMTP</t:RoutingType>
          </t:Mailbox>
        </t:From>
        <t:Preview>{m['preview']}</t:Preview>
      </t:Message>"""


def _find_item_response(inbox=None):
    if inbox is None:
        inbox = _build_inbox()
    messages = "\n".join(_xml_message(m) for m in inbox)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
            xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
  <s:Header>
    <t:ServerVersionInfo MajorVersion="15" MinorVersion="2" MajorBuildNumber="1118"
                         MinorBuildNumber="25" Version="Exchange2016"/>
  </s:Header>
  <s:Body>
    <m:FindItemResponse>
      <m:ResponseMessages>
        <m:FindItemResponseMessage ResponseClass="Success">
          <m:ResponseCode>NoError</m:ResponseCode>
          <m:RootFolder TotalItemsInView="15907" IncludesLastItemInRange="false">
            <t:Items>
{messages}
            </t:Items>
          </m:RootFolder>
        </m:FindItemResponseMessage>
      </m:ResponseMessages>
    </m:FindItemResponse>
  </s:Body>
</s:Envelope>"""


WSDL_STUB = """<?xml version="1.0" encoding="utf-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
                  xmlns:tns="http://schemas.microsoft.com/exchange/services/2006/messages"
                  targetNamespace="http://schemas.microsoft.com/exchange/services/2006/messages">
  <wsdl:service name="ExchangeServices">
    <wsdl:port name="ExchangeServicePort" binding="tns:ExchangeServiceBinding">
      <soap:address location="http://ex.atbmarket.com/ews/Exchange.asmx"
                    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"/>
    </wsdl:port>
  </wsdl:service>
</wsdl:definitions>"""


@app.route("/ews/Exchange.asmx", methods=["GET", "POST"])
def ews():
    ip = atblog.client_ip(request)

    if request.method == "GET":
        return Response(WSDL_STUB, status=200,
                        content_type="text/xml; charset=utf-8")

    creds = _parse_basic(request.headers.get("Authorization", ""))
    if not creds:
        atblog.log("exchange.auth_missing", ip, path="/ews/Exchange.asmx")
        return _unauthorized()

    user, pw = creds
    if user != EWS_USER or pw != EWS_PASS:
        atblog.log("exchange.auth_fail", ip, user=user)
        return _unauthorized()

    atblog.log("exchange.ews_auth", ip, user=user)
    atblog.log("exchange.finditem", ip, total=15907, reset_links=27,
               msg="EWS FindItem returned inbox; 27 live password-reset GUIDs present")
    return Response(_find_item_response(), status=200,
                    content_type="text/xml; charset=utf-8")


# --------------------------------------------------------------------------- #
# OWA (Outlook Web Access) browser UI                                         #
# --------------------------------------------------------------------------- #
def _owa_token():
    """Opaque session marker (lab-grade; no server-side session store)."""
    return base64.urlsafe_b64encode(EWS_USER.encode()).decode().rstrip("=")


def _owa_authed():
    return request.cookies.get(OWA_COOKIE) == _owa_token()


def _page(title, body, inner_width="960px"):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: #f3f2f1; color: #201f1e;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif;
    font-size: 14px;
  }}
  a {{ color: {BLUE}; }}
  .topbar {{
    background: {BLUE}; color: #fff; height: 48px; display: flex;
    align-items: center; padding: 0 16px; gap: 12px;
  }}
  .topbar .brand {{ font-weight: 600; font-size: 16px; }}
  .topbar .spacer {{ flex: 1; }}
  .topbar a {{ color: #fff; text-decoration: none; font-size: 13px; }}
  .wrap {{ max-width: {inner_width}; margin: 0 auto; padding: 16px; }}
  .card {{
    background: #fff; border: 1px solid #edebe9; border-radius: 4px;
    box-shadow: 0 1.6px 3.6px rgba(0,0,0,.08); overflow: hidden;
  }}
  .folderhdr {{
    padding: 12px 16px; border-bottom: 1px solid #edebe9;
    display: flex; align-items: baseline; gap: 10px;
  }}
  .folderhdr h2 {{ margin: 0; font-size: 18px; }}
  .folderhdr .count {{ color: #605e5c; font-size: 12px; }}
  ul.msglist {{ list-style: none; margin: 0; padding: 0; }}
  ul.msglist li a {{
    display: block; padding: 12px 16px; border-bottom: 1px solid #f3f2f1;
    text-decoration: none; color: inherit;
  }}
  ul.msglist li a:hover {{ background: #f3f2f1; }}
  .row1 {{ display: flex; justify-content: space-between; gap: 10px; }}
  .sender {{ font-weight: 600; color: #201f1e; }}
  .unread .sender {{ color: {BLUE}; }}
  .when {{ color: #605e5c; font-size: 12px; white-space: nowrap; }}
  .subject {{ margin: 2px 0; font-weight: 600; }}
  .preview {{ color: #605e5c; font-size: 13px; overflow: hidden;
             text-overflow: ellipsis; white-space: nowrap; }}
  .badge {{
    display: inline-block; background: #fde7e9; color: #a4262c;
    border-radius: 10px; padding: 1px 8px; font-size: 11px; font-weight: 600;
    margin-left: 6px; vertical-align: middle;
  }}
  .msgview .hdr {{ padding: 16px; border-bottom: 1px solid #edebe9; }}
  .msgview .hdr h2 {{ margin: 0 0 6px; font-size: 18px; }}
  .msgview .meta {{ color: #605e5c; font-size: 13px; }}
  .msgbody {{ padding: 16px; line-height: 1.5; }}
  .resetbox {{
    margin-top: 16px; padding: 12px; background: #f3f9fd;
    border: 1px solid #c7e0f4; border-radius: 4px; word-break: break-all;
  }}
  .back {{ display: inline-block; margin-bottom: 12px; }}
  /* sign-in */
  .signin {{ max-width: 420px; margin: 8vh auto; padding: 0 16px; }}
  .signin .card {{ padding: 28px 24px; }}
  .signin h1 {{ font-size: 22px; margin: 0 0 4px; font-weight: 600; }}
  .signin p.sub {{ color: #605e5c; margin: 0 0 20px; }}
  .signin label {{ display: block; font-size: 13px; margin: 14px 0 4px; }}
  .signin input {{
    width: 100%; padding: 8px 10px; font-size: 15px;
    border: none; border-bottom: 2px solid #8a8886; background: transparent;
  }}
  .signin input:focus {{ outline: none; border-bottom-color: {BLUE}; }}
  .signin button {{
    margin-top: 22px; width: 100%; background: {BLUE}; color: #fff;
    border: none; padding: 10px; font-size: 15px; cursor: pointer;
    border-radius: 2px;
  }}
  .signin button:hover {{ background: #106ebe; }}
  .err {{ color: #a4262c; background: #fde7e9; border: 1px solid #f1bbbe;
         padding: 8px 10px; border-radius: 2px; margin-top: 14px; font-size: 13px; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def _signin_page(error=None, email=""):
    err = f'<div class="err">{html.escape(error)}</div>' if error else ""
    body = f"""<div class="signin">
  <div class="card">
    <h1>Outlook</h1>
    <p class="sub">ex.atbmarket.com &middot; Sign in to your mailbox</p>
    <form method="post" action="/owa/login">
      <label for="email">Email address</label>
      <input id="email" name="email" type="email" autocomplete="username"
             value="{html.escape(email)}" placeholder="name@atbmarket.com" autofocus>
      <label for="password">Password</label>
      <input id="password" name="password" type="password"
             autocomplete="current-password" placeholder="Password">
      {err}
      <button type="submit">Sign in</button>
    </form>
  </div>
</div>"""
    return _page("Sign in - Outlook", body)


def _owa_chrome(inner):
    return f"""<div class="topbar">
  <span class="brand">Outlook</span>
  <span class="spacer"></span>
  <span>{html.escape(EWS_USER)}</span>
  <a href="/owa/signout">Sign out</a>
</div>
<div class="wrap">
{inner}
</div>"""


@app.get("/")
@app.get("/owa")
def owa_signin():
    if _owa_authed():
        return redirect("/owa/mail")
    return _signin_page()


@app.post("/owa/login")
def owa_login():
    ip = atblog.client_ip(request)
    email = request.form.get("email", "")
    pw = request.form.get("password", "")
    if email == EWS_USER and pw == EWS_PASS:
        atblog.log("exchange.ews_auth", ip, user=email, via="owa")
        resp = make_response(redirect("/owa/mail"))
        resp.set_cookie(OWA_COOKIE, _owa_token(), httponly=True, samesite="Lax")
        return resp
    atblog.log("exchange.auth_fail", ip, user=email, via="owa")
    return _signin_page(error="Your account or password is incorrect.",
                        email=email), 401


@app.get("/owa/signout")
def owa_signout():
    resp = make_response(redirect("/owa"))
    resp.delete_cookie(OWA_COOKIE)
    return resp


@app.get("/owa/mail")
def owa_mail():
    if not _owa_authed():
        return redirect("/owa")
    ip = atblog.client_ip(request)
    inbox = _build_inbox()
    atblog.log("exchange.finditem", ip, total=15907, reset_links=27,
               msg="EWS FindItem returned inbox; 27 live password-reset GUIDs present")

    rows = []
    for m in inbox:
        unread = "unread" if not m["is_read"] else ""
        badge = '<span class="badge">reset link</span>' if m["is_reset"] else ""
        rows.append(f"""    <li>
      <a href="/owa/mail/{m['id']}" class="{unread}">
        <div class="row1">
          <span class="sender">{html.escape(m['sender'])}</span>
          <span class="when">{html.escape(m['received'])}</span>
        </div>
        <div class="subject">{html.escape(m['subject'])}{badge}</div>
        <div class="preview">{html.escape(m['preview'])}</div>
      </a>
    </li>""")
    listing = "\n".join(rows)
    inner = f"""<div class="card">
  <div class="folderhdr">
    <h2>Inbox</h2>
    <span class="count">15907 items</span>
  </div>
  <ul class="msglist">
{listing}
  </ul>
</div>"""
    return _page("Inbox - Outlook", _owa_chrome(inner))


@app.get("/owa/mail/<int:mid>")
def owa_message(mid):
    if not _owa_authed():
        return redirect("/owa")
    inbox = _build_inbox()
    msg = next((m for m in inbox if m["id"] == mid), None)
    if msg is None:
        return redirect("/owa/mail")

    if msg["is_reset"]:
        link = msg["reset_link"]
        body_html = (
            "<p>To reset your password click the secure link below:</p>"
            f'<p><a href="{html.escape(link)}">{html.escape(link)}</a></p>'
            f'<div class="resetbox"><strong>Password reset link:</strong><br>'
            f'<a href="{html.escape(link)}">{html.escape(link)}</a></div>'
        )
    else:
        body_html = f"<p>{html.escape(msg['preview'])}</p>"

    inner = f"""<a class="back" href="/owa/mail">&larr; Back to Inbox</a>
<div class="card msgview">
  <div class="hdr">
    <h2>{html.escape(msg['subject'])}</h2>
    <div class="meta">
      From <strong>{html.escape(msg['sender'])}</strong><br>
      Received {html.escape(msg['received'])} &middot; Importance: {html.escape(msg['importance'])}
    </div>
  </div>
  <div class="msgbody">
{body_html}
  </div>
</div>"""
    return _page(f"{msg['subject']} - Outlook", _owa_chrome(inner))


@app.get("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80)
