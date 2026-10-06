#!/usr/bin/env python3
"""Step 8 - probe an Oracle mock with SELECT 1 FROM DUAL.

Usage: python3 oracle_probe.py <host> <port> <user> <password> [sql]
Example: python3 oracle_probe.py localhost 1581 XX_SUP_PORTAL_RO S0h6jWot2fTLSMm
"""
import socket
import sys

if len(sys.argv) < 5:
    print(__doc__)
    sys.exit(1)

host, port, user, pw = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
sql = sys.argv[5] if len(sys.argv) > 5 else "SELECT 1 FROM DUAL"

line = f"{user}\t{pw}\t{sql}\n".encode()
s = socket.create_connection((host, port), timeout=10)
s.sendall(line)
resp = s.recv(4096).decode(errors="replace").strip()
s.close()
print(f"{host}:{port}  {user}  '{sql}'  -> {resp}")
