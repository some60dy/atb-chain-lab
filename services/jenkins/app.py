"""Mock Zabbix AGENT for jenkins.atbmarket.com (ATB security lab).

Speaks the Zabbix passive-agent ZBXD protocol on 0.0.0.0:10050. The attacker
pivots through a proxy (chain step 7) and sends a ZBXD system.run[...] request;
the agent executes the command as the local `zabbix` user. A CIFS backup is
mounted at /mnt/BACKUP (contains root.tar.gz).

Plain sockets -- NOT Flask.
"""
import socket
import socketserver
import struct
import subprocess
import threading

import atblog

HOST = "0.0.0.0"
PORT = 10050

ZBXD_HEADER = b"ZBXD"
ZBXD_FLAG = b"\x01"


def frame(payload):
    """Wrap payload bytes in the ZBXD passive-agent framing."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return ZBXD_HEADER + ZBXD_FLAG + struct.pack("<Q", len(payload)) + payload


def _recv_exact(conn, n):
    """Read exactly n bytes from conn (or fewer if the peer closes early)."""
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


class ZabbixHandler(socketserver.BaseRequestHandler):
    def handle(self):
        conn = self.request
        src_ip = self.client_address[0]

        header = _recv_exact(conn, 4)
        if not header:
            return

        if header == ZBXD_HEADER:
            # flag byte (1) + payload length (8-byte little-endian)
            _flag = _recv_exact(conn, 1)
            length_raw = _recv_exact(conn, 8)
            if len(length_raw) < 8:
                return
            (length,) = struct.unpack("<Q", length_raw)
            payload = _recv_exact(conn, length)
            key = payload.decode("utf-8", errors="replace").strip()
        else:
            # Not ZBXD framed: treat the whole recv buffer as the raw key.
            rest = conn.recv(65535)
            key = (header + rest).decode("utf-8", errors="replace").strip()

        response = self.dispatch(key, src_ip)
        try:
            conn.sendall(frame(response))
        except OSError:
            pass

    def dispatch(self, key, src_ip):
        if key.startswith("system.run[") and "]" in key:
            cmd = key[key.index("[") + 1:key.rindex("]")]
            try:
                proc = subprocess.run(
                    ["/bin/sh", "-c", cmd],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                output = (proc.stdout + proc.stderr)
            except subprocess.TimeoutExpired:
                output = "zabbix_agent: command timed out\n"
            out_bytes = output.encode("utf-8", errors="replace")
            atblog.log(
                "jenkins.zbxd_system_run",
                src_ip=src_ip,
                cmd=cmd,
                bytes=len(out_bytes),
                msg="command executed via Zabbix agent system.run as user zabbix",
            )
            return out_bytes

        if key == "agent.ping":
            return "1"

        if key == "agent.hostname":
            return "jenkins.atbmarket.com"

        atblog.log("jenkins.zbxd_unsupported", src_ip=src_ip, key=key)
        return b"ZBX_NOTSUPPORTED\x00Unsupported item key."


class ThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    atblog.banner()
    server = ThreadingTCPServer((HOST, PORT), ZabbixHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    threading.Event().wait()


if __name__ == "__main__":
    main()
