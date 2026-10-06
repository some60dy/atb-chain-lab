"""Mock of THREE production Oracle databases as lightweight TCP listeners.

Step 8 of the chain probes each instance with "SELECT 1 FROM DUAL". This is NOT
a real Oracle TNS listener -- it speaks a trivial tab-delimited line protocol so
the lab can exercise credential-use detections without a real DB.

Wire protocol (one request per connection):
    client -> USER<TAB>PASSWORD<TAB>SQL\n     (UTF-8, fields split on literal \t)
    server -> response bytes, then connection stays open for the line reader

Responses:
    creds OK  + sql == "select 1 from dual"  -> b"1\n"
    creds OK  + any other sql                -> b"OK\n"
    creds bad                                -> b"ORA-01017: invalid username/password\n"
    malformed input                          -> b"ORA-00900: invalid SQL statement\n"
"""
import socketserver
import threading

import atblog

# instance definitions: port -> metadata
INSTANCES = {
    1581: {"name": "erpdb/PROD",          "user": "XX_SUP_PORTAL_RO", "password": "S0h6jWot2fTLSMm"},
    1521: {"name": "retaildb/retekdb",    "user": "SUPP_PORT_READER", "password": "C3KPgME{p=VyYmeTD6BqaIjN2"},
    1251: {"name": "ISMEDOC-DB/ZVITZAKUP", "user": "MEDOC",           "password": "HIr3t4G8Zso7"},
}


class OracleHandler(socketserver.StreamRequestHandler):
    def handle(self):
        instance = self.server.instance
        port = self.server.server_address[1]
        src_ip = self.client_address[0]

        raw = self.rfile.readline()
        if not raw:
            return
        try:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
        except Exception:
            self.wfile.write(b"ORA-00900: invalid SQL statement\n")
            return

        parts = line.split("\t")
        if len(parts) != 3:
            self.wfile.write(b"ORA-00900: invalid SQL statement\n")
            return

        user, password, sql = parts

        if user == instance["user"] and password == instance["password"]:
            atblog.log(
                "oracle.auth_ok",
                src_ip=src_ip,
                instance=instance["name"],
                user=user,
                sql=sql,
                port=port,
            )
            atblog.log(
                "oracle.query",
                src_ip=src_ip,
                instance=instance["name"],
                sql=sql,
            )
            if sql.strip().lower() == "select 1 from dual":
                self.wfile.write(b"1\n")
            else:
                self.wfile.write(b"OK\n")
        else:
            atblog.log(
                "oracle.auth_fail",
                src_ip=src_ip,
                instance=instance["name"],
                user=user,
                port=port,
            )
            self.wfile.write(b"ORA-01017: invalid username/password\n")


class OracleServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, port, instance):
        self.instance = instance
        super().__init__(("0.0.0.0", port), OracleHandler)


def main():
    atblog.banner()
    for port, instance in INSTANCES.items():
        server = OracleServer(port, instance)
        atblog.log(
            "oracle.listen",
            instance=instance["name"],
            port=port,
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Event().wait()


if __name__ == "__main__":
    main()
