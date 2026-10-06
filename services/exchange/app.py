"""Step 9 - ex.atbmarket.com Microsoft Exchange EWS mock.

Speaks a minimal Exchange Web Services (EWS) SOAP endpoint protected by HTTP
Basic auth. Valid creds (supplier@atbmarket.com:supplier123569) unlock a
FindItem response whose inbox contains live password-reset GUID links.

TLS is omitted for the lab; the compose layer maps plain HTTP to port 8444.
"""
import base64
import uuid

from flask import Flask, request, Response
import atblog

app = Flask(__name__)

EWS_USER = "supplier@atbmarket.com"
EWS_PASS = "supplier123569"

RESET_BASE = "https://supplier.atbmarket.com/index.php?entryPoint=Changenewpassword&guid="


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


def _reset_message(subject, mid, sender):
    guid = uuid.uuid4()
    link = RESET_BASE + str(guid)
    return f"""      <t:Message>
        <t:ItemId Id="AAMk{mid}=" ChangeKey="CQAAAB{mid}"/>
        <t:Subject>{subject}</t:Subject>
        <t:Sensitivity>Normal</t:Sensitivity>
        <t:DateTimeReceived>2024-05-1{mid}T09:2{mid}:11Z</t:DateTimeReceived>
        <t:Size>5120</t:Size>
        <t:Importance>High</t:Importance>
        <t:IsRead>false</t:IsRead>
        <t:From>
          <t:Mailbox>
            <t:Name>{sender}</t:Name>
            <t:EmailAddress>{sender}</t:EmailAddress>
            <t:RoutingType>SMTP</t:RoutingType>
          </t:Mailbox>
        </t:From>
        <t:Preview>Please reset your password. Click the secure link to continue: {link}</t:Preview>
        <t:Body BodyType="HTML">&lt;html&gt;&lt;body&gt;To reset your password click &lt;a href="{link}"&gt;{link}&lt;/a&gt;&lt;/body&gt;&lt;/html&gt;</t:Body>
      </t:Message>"""


def _plain_message(subject, mid, sender, preview):
    return f"""      <t:Message>
        <t:ItemId Id="AAMk{mid}=" ChangeKey="CQAAAB{mid}"/>
        <t:Subject>{subject}</t:Subject>
        <t:Sensitivity>Normal</t:Sensitivity>
        <t:DateTimeReceived>2024-05-0{mid}T14:0{mid}:03Z</t:DateTimeReceived>
        <t:Size>3072</t:Size>
        <t:Importance>Normal</t:Importance>
        <t:IsRead>true</t:IsRead>
        <t:From>
          <t:Mailbox>
            <t:Name>{sender}</t:Name>
            <t:EmailAddress>{sender}</t:EmailAddress>
            <t:RoutingType>SMTP</t:RoutingType>
          </t:Mailbox>
        </t:From>
        <t:Preview>{preview}</t:Preview>
      </t:Message>"""


def _find_item_response():
    items = [
        _plain_message("Weekly logistics report", 1, "logistics@atbmarket.com",
                       "Attached is the weekly logistics summary for review."),
        _reset_message("Password reset - action required", 2,
                       "no-reply@supplier.atbmarket.com"),
        _plain_message("Invoice #44821 approved", 3, "finance@atbmarket.com",
                       "Your invoice has been approved and scheduled for payment."),
        _reset_message("Password reset - action required", 4,
                       "no-reply@supplier.atbmarket.com"),
        _plain_message("Supplier portal maintenance window", 5,
                       "it-ops@atbmarket.com",
                       "Scheduled maintenance this weekend; expect brief downtime."),
    ]
    messages = "\n".join(items)
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


@app.get("/")
def index():
    return ("<html><head><title>Exchange EWS</title></head>"
            "<body><h1>Exchange EWS</h1>"
            "<p>Microsoft Exchange Web Services endpoint: "
            "<code>/ews/Exchange.asmx</code></p></body></html>"), 200


@app.get("/healthz")
def healthz():
    return "ok", 200


if __name__ == "__main__":
    atblog.banner()
    app.run(host="0.0.0.0", port=80)
