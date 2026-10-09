"""`Prometheus` data source (prom-p01) behind the ATB Grafana: a small PromQL
evaluator over the exporters that scrape the prod web tier (nginx,
node_exporter, the SuiteCRM supplier-portal exporter, the e-shop order counter).
The "Zabbix DB" data source is the real Zabbix database (see app.py)."""
import math
import re
import time
import zlib

# ===================================================================== signal
def _h(*parts):
    """Deterministic hash in [0, 1)."""
    return zlib.crc32("|".join(map(str, parts)).encode()) / 4294967296.0


def _smooth(key, t, period=900.0):
    k = t / period
    i = math.floor(k)
    f = k - i
    a = _h(key, i) * 2 - 1
    b = _h(key, i + 1) * 2 - 1
    w = (1 - math.cos(math.pi * f)) / 2
    return a * (1 - w) + b * w


def _jit(key, t, step=60):
    return _h(key, "j", int(t // step)) * 2 - 1


def _daily(t, peak=19.0):
    local = t + 3 * 3600  # Europe/Kyiv
    return math.cos(2 * math.pi * (local / 86400.0 - peak / 24.0))


def wave(key, t, base, amp=0.3, noise=0.1, jit=0.03, peak=19.0, lo=None, hi=None):
    v = base * (1 + amp * _daily(t, peak) + noise * _smooth(key, t) + 0.35 * jit * _jit(key, t))
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


# ======================================================== Prometheus catalogue
class _S:
    __slots__ = ("labels", "kind", "fn")

    def __init__(self, labels, kind, fn):
        self.labels = labels  # dict incl. __name__
        self.kind = kind      # gauge | counter | hist
        self.fn = fn          # t -> value (gauge/hist) or rate (counter)


CATALOG = []
NGINX = {"www-p01": 142, "www-p02": 136, "mob-api-p01": 61, "sp-web-p01": 9.5, "edu-web-p01": 14}
VHOSTS = {
    "www-p01": [("atbmarket.com", .62), ("www.atbmarket.com", .23), ("static.atbmarket.com", .15)],
    "www-p02": [("atbmarket.com", .61), ("www.atbmarket.com", .24), ("static.atbmarket.com", .15)],
    "mob-api-p01": [("api.mobapp.atbmarket.com", .93), ("mobapp.atbmarket.com", .07)],
    "sp-web-p01": [("supplier.atbmarket.com", 1.0)],
    "edu-web-p01": [("education.atbmarket.com", 1.0)],
}
STATUS = [("200", .862), ("304", .071), ("301", .021), ("404", .029), ("499", .011),
          ("500", .0042), ("502", .0018)]
LATENCY = {"www-p01": .048, "www-p02": .051, "mob-api-p01": .083, "sp-web-p01": .214, "edu-web-p01": .31}
NODES = {  # instance: (cpu util frac, mem util, mem GiB, fs used frac, fs GiB, net Bps)
    "www-p01": (.31, .58, 16, .41, 80, 4.1e6), "www-p02": (.29, .55, 16, .40, 80, 3.9e6),
    "mob-api-p01": (.22, .47, 8, .36, 50, 1.6e6), "sp-web-p01": (.14, .63, 8, .72, 50, 3.1e5),
    "edu-web-p01": (.19, .81, 8, .58, 100, 5.2e5), "zb-app-p01": (.33, .61, 16, .48, 200, 6.1e5),
}
SP_MODULES = [("Home", .22), ("Accounts", .17), ("Contacts", .12), ("Documents", .14),
              ("AOS_Quotes", .12), ("Emails", .08), ("Users", .09), ("Import", .06)]

def _add(name, labels, kind, fn):
    lb = {"__name__": name}
    lb.update(labels)
    CATALOG.append(_S(lb, kind, fn))


def _build():
    for inst, rps in NGINX.items():
        for vh, vs in VHOSTS[inst]:
            for st, ss in STATUS:
                if inst == "sp-web-p01" and st == "500":
                    ss = .011
                k = f"ng|{inst}|{vh}|{st}"
                n = .5 if st.startswith("5") else .14
                _add("nginx_http_requests_total", {"job": "nginx", "instance": inst, "host": vh, "status": st},
                     "counter", lambda t, k=k, b=rps * vs * ss, n=n: wave(k, t, b, .45, n, .06, lo=0))
        _add("nginx_connections_active", {"job": "nginx", "instance": inst}, "gauge",
             lambda t, k=f"nc|{inst}", b=rps * .9: round(wave(k, t, b, .45, .15, .08, lo=1)))
        _add("nginx_request_duration_seconds_bucket", {"job": "nginx", "instance": inst}, "hist",
             lambda t, k=f"nl|{inst}", b=LATENCY[inst]: wave(k, t, b, .25, .3, .1, lo=.004))
        _add("up", {"job": "nginx", "instance": inst}, "gauge", lambda t: 1)
    for inst, (cpu, mem, memg, fs, fsg, net) in NODES.items():
        tot = memg * 1024 ** 3
        for mode, share in (("user", .64), ("system", .24), ("iowait", .09), ("steal", .03)):
            _add("node_cpu_seconds_total", {"job": "node", "instance": inst, "mode": mode}, "counter",
                 lambda t, k=f"cpu|{inst}", b=cpu, s=share: s * wave(k, t, b, .4, .3, .1, lo=.002, hi=.98))
        _add("node_cpu_seconds_total", {"job": "node", "instance": inst, "mode": "idle"}, "counter",
             lambda t, k=f"cpu|{inst}", b=cpu: 1 - wave(k, t, b, .4, .3, .1, lo=.002, hi=.98))
        _add("node_memory_MemTotal_bytes", {"job": "node", "instance": inst}, "gauge", lambda t, v=tot: v)
        _add("node_memory_MemAvailable_bytes", {"job": "node", "instance": inst}, "gauge",
             lambda t, k=f"mem|{inst}", v=tot, m=mem: v * (1 - wave(k, t, m, .05, .05, .01, hi=.99)))
        fss = fsg * 1024 ** 3
        fl = {"job": "node", "instance": inst, "mountpoint": "/", "device": "/dev/sda1", "fstype": "ext4"}
        _add("node_filesystem_size_bytes", fl, "gauge", lambda t, v=fss: v)
        _add("node_filesystem_avail_bytes", fl, "gauge",
             lambda t, k=f"fs|{inst}", v=fss, f=fs: v * (1 - f - .01 * _smooth(k, t, 7200)))
        for d, m in (("receive", .55), ("transmit", 1.0)):
            _add(f"node_network_{d}_bytes_total", {"job": "node", "instance": inst, "device": "eth0"}, "counter",
                 lambda t, k=f"net{d}|{inst}", b=net * m: wave(k, t, b, .45, .2, .1, lo=100))
        _add("node_load1", {"job": "node", "instance": inst}, "gauge",
             lambda t, k=f"ld|{inst}", b=cpu * 4: wave(k, t, b, .4, .35, .15, lo=.01))
        bt = 1767225600 + int(_h(inst, "boot") * 86400 * 120)
        _add("node_boot_time_seconds", {"job": "node", "instance": inst}, "gauge", lambda t, b=bt: b)
        _add("node_time_seconds", {"job": "node", "instance": inst}, "gauge", lambda t: t)
        _add("up", {"job": "node", "instance": inst}, "gauge", lambda t: 1)
    for ch, r in (("web", .92), ("mobile", .61)):
        _add("ishop_orders_total", {"job": "ishop", "instance": "www-p01", "channel": ch}, "counter",
             lambda t, k=f"ord|{ch}", b=r: wave(k, t, b, .55, .18, .1, peak=20, lo=0))
    sp = {"job": "suitecrm", "instance": "sp-web-p01"}
    for res, r in (("success", .052), ("failure", .0045)):
        _add("suitecrm_logins_total", dict(sp, result=res), "counter",
             lambda t, k=f"lg|{res}", b=r: wave(k, t, b, .6, .35, .2, peak=11, lo=0))
    for st, r in (("ok", .0012), ("failed", .00009)):
        _add("suitecrm_import_jobs_total", dict(sp, status=st), "counter",
             lambda t, k=f"imp|{st}", b=r: wave(k, t, b, .6, .4, .2, peak=10, lo=0))
    _add("suitecrm_upload_bytes_total", sp, "counter",
         lambda t: wave("upl", t, 26000, .6, .45, .3, peak=11, lo=0))
    _add("suitecrm_active_sessions", sp, "gauge", lambda t: round(wave("sess", t, 38, .55, .2, .05, peak=12, lo=2)))
    for mod, s in SP_MODULES:
        _add("suitecrm_requests_total", dict(sp, module=mod), "counter",
             lambda t, k=f"mod|{mod}", b=9.5 * s: wave(k, t, b, .5, .2, .08, peak=12, lo=0))
    _add("phpfpm_active_processes", dict(sp, pool="www"), "gauge",
         lambda t: round(wave("fpm", t, 6, .5, .3, .15, peak=12, lo=1)))
    _add("phpfpm_idle_processes", dict(sp, pool="www"), "gauge",
         lambda t: max(0, 20 - round(wave("fpm", t, 6, .5, .3, .15, peak=12, lo=1))))
    _add("up", {"job": "suitecrm", "instance": "sp-web-p01"}, "gauge", lambda t: 1)


_build()
METRIC_NAMES = sorted({s.labels["__name__"] for s in CATALOG})


# ================================================================ PromQL eval
class PromError(Exception):
    pass


_TOK = re.compile(r"""\s*(?:
    (?P<dur>\d+[smhdwy])(?![a-zA-Z_0-9])
  | (?P<num>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<id>[a-zA-Z_:][a-zA-Z0-9_:]*)
  | (?P<op>=~|!~|!=|==|>=|<=|[-+*/(){}\[\],=<>^%])
)""", re.X)

AGGS = {"sum", "avg", "min", "max", "count", "topk", "bottomk"}
FUNCS = {"rate", "irate", "increase", "delta", "avg_over_time", "max_over_time", "min_over_time",
         "sum_over_time", "histogram_quantile", "abs", "round", "ceil", "floor", "clamp_min",
         "clamp_max", "time", "vector", "scalar", "label_values", "sort", "sort_desc"}


def _dur(s):
    return int(s[:-1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800, "y": 31536000}[s[-1]]


def _tokenize(q):
    pos, out = 0, []
    q = q.rstrip()
    while pos < len(q):
        m = _TOK.match(q, pos)
        if not m or m.end() == pos:
            raise PromError(f'bad_data: 1:{pos + 1}: parse error: unexpected character: "{q[pos]}"')
        kind = m.lastgroup
        out.append((kind, m.group(kind), pos))
        pos = m.end()
    return out


class _P:
    def __init__(self, q):
        self.t = _tokenize(q)
        self.i = 0

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else (None, None, -1)

    def take(self, val=None):
        tok = self.peek()
        if tok[0] is None:
            raise PromError("bad_data: parse error: unexpected end of input")
        if val is not None and tok[1] != val:
            raise PromError(f'bad_data: 1:{tok[2] + 1}: parse error: unexpected "{tok[1]}", expected "{val}"')
        self.i += 1
        return tok

    def parse(self):
        node = self.expr()
        if self.peek()[0] is not None:
            tok = self.peek()
            raise PromError(f'bad_data: 1:{tok[2] + 1}: parse error: unexpected "{tok[1]}"')
        return node

    def expr(self):
        node = self.arith()
        while self.peek()[1] in (">", "<", ">=", "<=", "==", "!="):
            op = self.take()[1]
            node = ("bin", op, node, self.arith())
        return node

    def arith(self):
        node = self.term()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            node = ("bin", op, node, self.term())
        return node

    def term(self):
        node = self.factor()
        while self.peek()[1] in ("*", "/", "%"):
            op = self.take()[1]
            node = ("bin", op, node, self.factor())
        return node

    def labels(self):
        self.take("(")
        out = []
        while self.peek()[1] != ")":
            out.append(self.take()[1])
            if self.peek()[1] == ",":
                self.take()
        self.take(")")
        return out

    def factor(self):
        kind, val, pos = self.peek()
        if val == "-":
            self.take()
            return ("bin", "*", ("num", -1.0), self.factor())
        if kind == "num":
            self.take()
            return ("num", float(val))
        if val == "(":
            self.take()
            n = self.expr()
            self.take(")")
            return n
        if kind == "id" and val in AGGS:
            self.take()
            grp = None
            if self.peek()[1] in ("by", "without"):
                grp = (self.take()[1], self.labels())
            self.take("(")
            param = None
            if val in ("topk", "bottomk"):
                param = self.expr()
                self.take(",")
            inner = self.expr()
            self.take(")")
            if self.peek()[1] in ("by", "without"):
                grp = (self.take()[1], self.labels())
            return ("agg", val, grp, param, inner)
        if kind == "id" and val in FUNCS and self.peek(1)[1] == "(":
            self.take()
            self.take("(")
            args = []
            while self.peek()[1] != ")":
                args.append(self.expr())
                if self.peek()[1] == ",":
                    self.take()
            self.take(")")
            return ("call", val, args)
        if kind == "id" or val == "{":
            name = None
            if kind == "id":
                self.take()
                name = val
            matchers = []
            if self.peek()[1] == "{":
                self.take()
                while self.peek()[1] != "}":
                    ln = self.take()[1]
                    op = self.take()[1]
                    if op not in ("=", "!=", "=~", "!~"):
                        raise PromError(f"bad_data: parse error: unexpected {op} in label matching")
                    sv = self.take()
                    if sv[0] != "str":
                        raise PromError("bad_data: parse error: unexpected identifier in label matching, "
                                        "expected string")
                    matchers.append((ln, op, sv[1][1:-1]))
                    if self.peek()[1] == ",":
                        self.take()
                self.take("}")
            if name:
                matchers.insert(0, ("__name__", "=", name))
            rng = None
            if self.peek()[1] == "[":
                self.take()
                d = self.take()
                if d[0] != "dur":
                    raise PromError(f'bad_data: parse error: bad duration "{d[1]}"')
                rng = _dur(d[1])
                self.take("]")
            if not matchers:
                raise PromError("bad_data: parse error: vector selector must contain at least one "
                                "non-empty matcher")
            return ("sel", matchers, rng)
        if kind is None:
            raise PromError("bad_data: parse error: unexpected end of input")
        raise PromError(f'bad_data: 1:{pos + 1}: parse error: unexpected "{val}"')


class _V:
    """Instant-vector over the evaluation grid."""

    def __init__(self, series=None, hist=False):
        self.s = series or {}  # labels tuple -> [values]
        self.hist = hist


def _match(labels, matchers):
    for ln, op, v in matchers:
        lv = labels.get(ln, "")
        if op == "=" and lv != v:
            return False
        if op == "!=" and lv == v:
            return False
        if op == "=~" and not re.fullmatch(v, lv):
            return False
        if op == "!~" and re.fullmatch(v, lv):
            return False
    return True


def _key(d):
    return tuple(sorted(d.items()))


_QF = {0.5: 1.0, 0.75: 1.55, 0.9: 2.2, 0.95: 2.9, 0.99: 5.4}


class Evaluator:
    def __init__(self, grid):
        self.grid = grid

    def run(self, q):
        return self.ev(_P(q).parse())

    def _select(self, matchers):
        try:
            hits = [s for s in CATALOG if _match(s.labels, matchers)]
        except re.error as e:
            raise PromError(f"bad_data: invalid regular expression: {e}")
        return hits

    def _sel_vec(self, matchers, mode, rng=None):
        hits = self._select(matchers)
        out, hist = {}, False
        for s in hits:
            lb = dict(s.labels)
            if s.kind == "counter":
                if mode == "rate":
                    lb.pop("__name__", None)
                    if rng and rng > 900:
                        n = 8
                        vals = [sum(s.fn(t - rng * i / n) for i in range(n)) / n for t in self.grid]
                    else:
                        vals = [s.fn(t) for t in self.grid]
                else:
                    r = s.fn(self.grid[0]) if self.grid else 0
                    vals = [r * (t - 1.75e9) + 1e7 * _h(str(s.labels)) for t in self.grid]
            elif s.kind == "hist":
                hist = True
                if mode == "rate":
                    lb.pop("__name__", None)
                vals = [s.fn(t) for t in self.grid]
            else:
                vals = [s.fn(t) for t in self.grid]
            out[_key(lb)] = vals
        return _V(out, hist)

    def ev(self, n):
        k = n[0]
        if k == "num":
            return n[1]
        if k == "sel":
            return self._sel_vec(n[1], "raw", n[2])
        if k == "call":
            return self.call(n[1], n[2])
        if k == "agg":
            return self.agg(*n[1:])
        if k == "bin":
            return self.bin(n[1], self.ev(n[2]), self.ev(n[3]))
        raise PromError("unsupported expression")

    def call(self, fn, args):
        if fn in ("rate", "irate", "increase", "delta"):
            if not args or args[0][0] != "sel" or args[0][2] is None:
                raise PromError(f"bad_data: parse error: expected type range vector in call to function "
                                f'"{fn}", got instant vector')
            v = self._sel_vec(args[0][1], "rate", args[0][2])
            if fn in ("increase", "delta"):
                for key in v.s:
                    v.s[key] = [x * args[0][2] for x in v.s[key]]
            return v
        if fn.endswith("_over_time"):
            if not args or args[0][0] != "sel" or args[0][2] is None:
                raise PromError(f'bad_data: expected type range vector in call to function "{fn}"')
            v = self._sel_vec(args[0][1], "raw", None)
            for key in list(v.s):
                d = dict(key)
                d.pop("__name__", None)
                v.s[_key(d)] = v.s.pop(key)
            return v
        if fn == "histogram_quantile":
            if len(args) != 2:
                raise PromError("bad_data: expected 2 arguments in call to histogram_quantile")
            q = self.ev(args[0])
            v = self.ev(args[1])
            if not isinstance(v, _V):
                raise PromError("bad_data: expected instant vector")
            if not v.hist:
                return _V({})
            f = _QF.get(round(q, 2), 1 + 4.4 * max(0, q - .5) / .49)
            out = {}
            for key, vals in v.s.items():
                d = {a: b for a, b in key if a != "le"}
                out[_key(d)] = [None if x is None else x * f for x in vals]
            return _V(out)
        if fn == "time":
            return _V({(): [float(t) for t in self.grid]})
        if fn == "vector":
            x = self.ev(args[0])
            return _V({(): [x] * len(self.grid)}) if not isinstance(x, _V) else x
        if fn == "scalar":
            x = self.ev(args[0])
            return x
        if fn == "label_values":
            raise PromError("label_values is only valid in variable queries")
        v = self.ev(args[0]) if args else None
        if not isinstance(v, _V):
            raise PromError(f'bad_data: expected instant vector in call to function "{fn}"')
        ops = {"abs": abs, "ceil": math.ceil, "floor": math.floor}
        if fn in ops:
            v.s = {k2: [None if x is None else ops[fn](x) for x in vals] for k2, vals in v.s.items()}
        elif fn == "round":
            to = self.ev(args[1]) if len(args) > 1 else 1
            v.s = {k2: [None if x is None else round(x / to) * to for x in vals] for k2, vals in v.s.items()}
        elif fn in ("clamp_min", "clamp_max"):
            lim = self.ev(args[1])
            f = max if fn == "clamp_min" else min
            v.s = {k2: [None if x is None else f(x, lim) for x in vals] for k2, vals in v.s.items()}
        return v

    def agg(self, op, grp, param, inner):
        v = self.ev(inner)
        if not isinstance(v, _V):
            raise PromError("bad_data: expected instant vector in aggregation")
        groups = {}
        for key, vals in v.s.items():
            d = dict(key)
            d.pop("__name__", None)
            if grp is None:
                g = {}
            elif grp[0] == "by":
                g = {a: d[a] for a in grp[1] if a in d}
            else:
                g = {a: b for a, b in d.items() if a not in grp[1]}
            groups.setdefault(_key(g), []).append(vals)
        if op in ("topk", "bottomk"):
            kk = int(self.ev(param))
            ranked = sorted(v.s.items(), key=lambda kv: (kv[1][-1] or 0), reverse=(op == "topk"))
            return _V(dict(ranked[:kk]), v.hist)
        out = {}
        n = len(self.grid)
        for g, lists in groups.items():
            res = []
            for i in range(n):
                xs = [l[i] for l in lists if l[i] is not None]
                if not xs:
                    res.append(None)
                elif op == "sum" and not v.hist:
                    res.append(sum(xs))
                elif op in ("avg",) or (op == "sum" and v.hist):
                    res.append(sum(xs) / len(xs))
                elif op == "min":
                    res.append(min(xs))
                elif op == "max":
                    res.append(max(xs))
                elif op == "count":
                    res.append(float(len(xs)))
            out[g] = res
        return _V(out, v.hist)

    def bin(self, op, a, b):
        def f(x, y):
            if x is None or y is None:
                return None
            try:
                if op == "+": return x + y
                if op == "-": return x - y
                if op == "*": return x * y
                if op == "/": return x / y if y else None
                if op == "%": return x % y if y else None
                if op == "^": return x ** y
                cmp = {">": x > y, "<": x < y, ">=": x >= y, "<=": x <= y, "==": x == y, "!=": x != y}[op]
                return x if cmp else None
            except Exception:
                return None

        if not isinstance(a, _V) and not isinstance(b, _V):
            return f(a, b)
        if isinstance(a, _V) and not isinstance(b, _V):
            return _V({k: [f(x, b) for x in vals] for k, vals in a.s.items()}, a.hist)
        if not isinstance(a, _V):
            return _V({k: [f(a, y) for y in vals] for k, vals in b.s.items()}, b.hist)

        def strip(key):
            return tuple(kv for kv in key if kv[0] != "__name__")

        bm = {strip(k): vals for k, vals in b.s.items()}
        out = {}
        for k, vals in a.s.items():
            sk = strip(k)
            other = bm.get(sk)
            if other is None and len(bm) == 1:
                other = next(iter(bm.values()))
            if other is None:
                continue
            out[sk] = [f(x, y) for x, y in zip(vals, other)]
        return _V(out)


def label_values(q):
    m = re.fullmatch(r"\s*label_values\(\s*(?:(.+?)\s*,\s*)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\)\s*", q)
    if not m:
        return None
    sel, label = m.group(1), m.group(2)
    if sel:
        node = _P(sel).parse()
        if node[0] != "sel":
            raise PromError("bad_data: label_values expects a series selector")
        hits = [s for s in CATALOG if _match(s.labels, node[1])]
    else:
        hits = CATALOG
    return sorted({s.labels[label] for s in hits if label in s.labels})


def prom_eval(expr, t_from, t_to, step, instant=False):
    """-> list of (labels dict, [(t, v), ...])"""
    if instant:
        grid = [t_to]
    else:
        step = max(15, int(step))
        start = int(t_from // step * step)
        grid = list(range(start, int(t_to) + 1, step))
        if len(grid) > 11000:
            raise PromError("bad_data: exceeded maximum resolution of 11,000 points per timeseries. "
                            "Try decreasing the query resolution (?step=XX)")
    res = Evaluator(grid).run(expr)
    if not isinstance(res, _V):
        return [({}, [(t, res) for t in grid])]
    out = []
    for key, vals in sorted(res.s.items()):
        pts = [(t, v) for t, v in zip(grid, vals) if v is not None]
        if pts:
            out.append((dict(key), pts))
    return out
