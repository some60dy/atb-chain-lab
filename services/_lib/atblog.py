"""Shared structured-logging + tiny-HTTP helpers for ATB lab services.

Every service appends one JSON object per line to /var/log/atb/<service>.json.
Splunk monitors that directory (index=atb, sourcetype=atb:json), so the field
names here ARE the detection schema. Keep them stable.
"""
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime, timezone

SERVICE = os.environ.get("ATB_SERVICE", "unknown")
HOSTNAME = os.environ.get("ATB_HOSTNAME", socket.gethostname())
LOG_DIR = os.environ.get("ATB_LOG_DIR", "/var/log/atb")
LOG_PATH = os.path.join(LOG_DIR, f"{SERVICE}.json")

_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def log(event, src_ip="-", **fields):
    """Write one structured event. `event` is the detection key (e.g. 'sqli.error')."""
    rec = {
        "time": _now(),
        "host": HOSTNAME,
        "service": SERVICE,
        "src_ip": src_ip,
        "event": event,
    }
    rec.update(fields)
    line = json.dumps(rec, ensure_ascii=False, default=str)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with _lock, open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    # also to stdout so `docker logs` shows it
    print(line, file=sys.stderr, flush=True)
    return rec


def client_ip(request):
    """Best-effort source IP from a Flask request."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "-"


def banner():
    log("service.start", msg=f"{SERVICE} up on {HOSTNAME}")
