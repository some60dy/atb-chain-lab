"""Provisioned objects of the ATB Grafana instance: org, users, teams, data
sources, folders, dashboards (JSON model), alert rules, plugins."""
import os
import time

VERSION = "10.2.3"
COMMIT = "1e84fede54"
BUILD_TS = 1702289186

NOW = int(time.time())
DAY = 86400

# ---------------------------------------------------------------- org/users
ORGS = [
    {"id": 1, "name": "Main Org.", "address": {"address1": "", "city": "Dnipro", "country": "Ukraine"}},
    {"id": 2, "name": "ATB Suppliers", "address": {"address1": "", "city": "", "country": ""}},
]

# login / e-mail / name / org role / grafana admin / auth module / last seen (seconds ago)
USERS = [
    {"id": 1, "login": "admin", "email": "admin@localhost", "name": "", "role": "Admin",
     "isGrafanaAdmin": True, "authLabels": [], "lastSeen": 112 * DAY, "created": "2022-03-14"},
    {"id": 2, "login": "education@atbmarket.com", "email": "education@atbmarket.com",
     "name": "Education Portal", "role": "Admin", "isGrafanaAdmin": True, "authLabels": ["LDAP"],
     "lastSeen": 0, "created": "2022-09-02"},
    {"id": 3, "login": "d.kovalenko", "email": "d.kovalenko@atbmarket.com", "name": "Dmytro Kovalenko",
     "role": "Admin", "isGrafanaAdmin": False, "authLabels": ["LDAP"], "lastSeen": 3 * 3600,
     "created": "2022-03-15"},
    {"id": 4, "login": "o.melnyk", "email": "o.melnyk@atbmarket.com", "name": "Olena Melnyk",
     "role": "Editor", "isGrafanaAdmin": False, "authLabels": ["LDAP"], "lastSeen": 26 * 3600,
     "created": "2022-05-30"},
    {"id": 5, "login": "i.bondarenko", "email": "i.bondarenko@atbmarket.com", "name": "Ihor Bondarenko",
     "role": "Editor", "isGrafanaAdmin": False, "authLabels": ["LDAP"], "lastSeen": 2 * DAY,
     "created": "2023-01-11"},
    {"id": 6, "login": "s.tkachenko", "email": "s.tkachenko@atbmarket.com", "name": "Serhii Tkachenko",
     "role": "Viewer", "isGrafanaAdmin": False, "authLabels": ["LDAP"], "lastSeen": 9 * DAY,
     "created": "2023-06-19"},
    {"id": 7, "login": "noc-wall", "email": "noc-wall@atbmarket.com", "name": "NOC video wall",
     "role": "Viewer", "isGrafanaAdmin": False, "authLabels": [], "lastSeen": 40,
     "created": "2022-04-01"},
    {"id": 8, "login": "a.savchuk", "email": "a.savchuk@atbmarket.com", "name": "Andrii Savchuk",
     "role": "Viewer", "isGrafanaAdmin": False, "authLabels": ["LDAP"], "lastSeen": 64 * DAY,
     "created": "2022-11-21"},
]

TEAMS = [
    {"id": 1, "name": "NOC", "email": "noc@atbmarket.com", "members": [3, 4, 7]},
    {"id": 2, "name": "Infrastructure", "email": "infra@atbmarket.com", "members": [3, 5]},
    {"id": 3, "name": "E-commerce", "email": "ecom-dev@atbmarket.com", "members": [4, 8]},
    {"id": 4, "name": "Supplier integration", "email": "supplier-it@atbmarket.com", "members": [6]},
    {"id": 5, "name": "E-learning", "email": "education@atbmarket.com", "members": [2]},
]

SERVICE_ACCOUNTS = [
    {"id": 9, "name": "sa-noc-wall", "login": "sa-1-noc-wall", "role": "Viewer", "tokens": 1,
     "isDisabled": False},
    {"id": 10, "name": "sa-alert-export", "login": "sa-1-alert-export", "role": "Editor", "tokens": 2,
     "isDisabled": False},
    {"id": 11, "name": "sa-terraform", "login": "sa-1-terraform", "role": "Admin", "tokens": 0,
     "isDisabled": True},
]

# ------------------------------------------------------------- data sources
DS_HOST = os.environ.get("ZABBIX_DB_HOST", "zabbix-db")
DS_DB = os.environ.get("ZABBIX_DB_NAME", "zabbix")
DS_USER = os.environ.get("ZABBIX_DB_USER", "grafana")

DATASOURCES = [
    {"id": 1, "uid": "zbx-mysql", "orgId": 1, "name": "Zabbix DB", "type": "mysql", "typeName": "MySQL",
     "access": "proxy", "url": f"{DS_HOST}:3306", "user": DS_USER, "database": DS_DB,
     "basicAuth": False, "isDefault": True, "readOnly": True,
     "jsonData": {"connMaxLifetime": 14400, "maxIdleConns": 100, "maxIdleConnsAuto": True,
                  "maxOpenConns": 100, "timezone": "", "tlsAuth": False, "tlsSkipVerify": True,
                  "database": DS_DB},
     "secureJsonFields": {"password": True}},
    {"id": 2, "uid": "prom-prod", "orgId": 1, "name": "Prometheus", "type": "prometheus",
     "typeName": "Prometheus", "access": "proxy", "url": "http://prom-p01.atbmarket.com:9090",
     "user": "", "database": "", "basicAuth": False, "isDefault": False, "readOnly": True,
     "jsonData": {"httpMethod": "POST", "prometheusType": "Prometheus", "prometheusVersion": "2.47.0",
                  "timeInterval": "30s", "cacheLevel": "Low", "incrementalQuerying": False},
     "secureJsonFields": {}},
    {"id": 3, "uid": "zbx-api", "orgId": 1, "name": "Zabbix", "type": "alexanderzobnin-zabbix-datasource",
     "typeName": "Zabbix", "access": "proxy", "url": "http://zabbix.atbmarket.com/api_jsonrpc.php",
     "user": "", "database": "", "basicAuth": False, "isDefault": False, "readOnly": True,
     "jsonData": {"username": "grafana_api", "trends": True, "trendsFrom": "7d", "trendsRange": "4d",
                  "cacheTTL": "1h", "timeout": 30, "dbConnectionEnable": True,
                  "dbConnectionDatasourceId": 1, "dbConnectionDatasourceName": "Zabbix DB",
                  "disableReadOnlyUsersAck": False},
     "secureJsonFields": {"password": True}},
    {"id": 4, "uid": "grafana-testdata", "orgId": 1, "name": "TestData", "type": "grafana-testdata-datasource",
     "typeName": "TestData", "access": "proxy", "url": "", "user": "", "database": "",
     "basicAuth": False, "isDefault": False, "readOnly": False, "jsonData": {}, "secureJsonFields": {}},
]
DS_BY_UID = {d["uid"]: d for d in DATASOURCES}
DS_BY_NAME = {d["name"]: d for d in DATASOURCES}

MYSQL = {"type": "mysql", "uid": "zbx-mysql"}
PROM = {"type": "prometheus", "uid": "prom-prod"}

# ------------------------------------------------------------------ plugins
PLUGINS = [
    # id, name, type, version, author, signature, core, description
    ("alexanderzobnin-zabbix-app", "Zabbix", "app", "4.4.5", "Alexander Zobnin", "community", False,
     "Zabbix plugin for Grafana"),
    ("alexanderzobnin-zabbix-datasource", "Zabbix", "datasource", "4.4.5", "Alexander Zobnin", "community",
     False, "Zabbix data source (bundled with the Zabbix app)"),
    ("grafana-clock-panel", "Clock", "panel", "2.1.3", "Grafana Labs", "grafana", False,
     "Clock panel for Grafana"),
    ("grafana-piechart-panel", "Pie Chart (old)", "panel", "1.6.4", "Grafana Labs", "grafana", False,
     "Pie chart panel for Grafana (deprecated, replaced by core Pie chart)"),
    ("marcusolsson-json-datasource", "JSON API", "datasource", "1.3.6", "Grafana Labs", "grafana", False,
     "A data source plugin for loading JSON APIs into Grafana"),
    ("mysql", "MySQL", "datasource", VERSION, "Grafana Labs", "internal", True,
     "Data source for MySQL databases"),
    ("prometheus", "Prometheus", "datasource", VERSION, "Grafana Labs", "internal", True,
     "Open source time series database & alerting"),
    ("postgres", "PostgreSQL", "datasource", VERSION, "Grafana Labs", "internal", True,
     "Data source for PostgreSQL and compatible databases"),
    ("loki", "Loki", "datasource", VERSION, "Grafana Labs", "internal", True,
     "Like Prometheus but for logs. OSS logging solution from Grafana Labs"),
    ("elasticsearch", "Elasticsearch", "datasource", VERSION, "Grafana Labs", "internal", True,
     "Open source logging & analytics database"),
    ("grafana-testdata-datasource", "TestData", "datasource", VERSION, "Grafana Labs", "internal", True,
     "Generates test data in different forms"),
    ("timeseries", "Time series", "panel", VERSION, "Grafana Labs", "internal", True,
     "Time based line, area and bar charts"),
    ("stat", "Stat", "panel", VERSION, "Grafana Labs", "internal", True,
     "Big stat values & sparklines"),
    ("gauge", "Gauge", "panel", VERSION, "Grafana Labs", "internal", True,
     "Standard gauge visualization"),
    ("bargauge", "Bar gauge", "panel", VERSION, "Grafana Labs", "internal", True,
     "Horizontal and vertical gauges"),
    ("table", "Table", "panel", VERSION, "Grafana Labs", "internal", True,
     "Supports many column styles"),
    ("text", "Text", "panel", VERSION, "Grafana Labs", "internal", True,
     "Supports markdown and html content"),
    ("dashlist", "Dashboard list", "panel", VERSION, "Grafana Labs", "internal", True,
     "List of dynamic links to other dashboards"),
    ("alertlist", "Alert list", "panel", VERSION, "Grafana Labs", "internal", True,
     "Shows list of alerts and their current status"),
    ("piechart", "Pie chart", "panel", VERSION, "Grafana Labs", "internal", True,
     "The new core pie chart visualization"),
    ("state-timeline", "State timeline", "panel", VERSION, "Grafana Labs", "internal", True,
     "State changes and durations"),
    ("logs", "Logs", "panel", VERSION, "Grafana Labs", "internal", True, "Logs panel"),
]

# ---------------------------------------------------------------- dashboards
FOLDERS = [
    {"id": 11, "uid": "atb-prod", "title": "ATB Prod"},
    {"id": 12, "uid": "infra", "title": "Infrastructure"},
    {"id": 13, "uid": "zabbix", "title": "Zabbix"},
]
FOLDER_BY_UID = {f["uid"]: f for f in FOLDERS}

_pid = [0]


def _thr(*steps):
    out = [{"color": steps[0], "value": None}]
    for i in range(1, len(steps), 2):
        out.append({"color": steps[i + 1], "value": steps[i]})
    return {"mode": "absolute", "steps": out}


GREEN = _thr("green")
CPU_THR = _thr("green", 70, "#EAB839", 85, "red")


def panel(ptype, title, x, y, w, h, targets=None, ds=None, unit=None, desc="", thresholds=None,
          options=None, minv=None, maxv=None, decimals=None, custom=None, overrides=None, **extra):
    _pid[0] += 1
    defaults = {"color": {"mode": "palette-classic" if ptype in ("timeseries", "bargauge") else "thresholds"},
                "thresholds": thresholds or GREEN, "mappings": []}
    if unit:
        defaults["unit"] = unit
    if minv is not None:
        defaults["min"] = minv
    if maxv is not None:
        defaults["max"] = maxv
    if decimals is not None:
        defaults["decimals"] = decimals
    if ptype == "timeseries":
        defaults["custom"] = {"drawStyle": "line", "lineInterpolation": "smooth", "lineWidth": 1,
                              "fillOpacity": 12, "gradientMode": "opacity", "showPoints": "never",
                              "spanNulls": True, "stacking": {"mode": "none", "group": "A"},
                              "axisPlacement": "auto", "thresholdsStyle": {"mode": "off"}}
        defaults["custom"].update(custom or {})
    p = {"id": _pid[0], "type": ptype, "title": title, "description": desc,
         "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
         "options": options or {}}
    if ds:
        p["datasource"] = ds
    if targets is not None:
        p["targets"] = targets
    p.update(extra)
    return p


def prom(expr, legend="", ref="A", instant=False, fmt="time_series"):
    return {"refId": ref, "datasource": PROM, "expr": expr, "legendFormat": legend, "range": not instant,
            "instant": instant, "format": fmt, "editorMode": "code"}


def sql(raw, ref="A", fmt="time_series"):
    return {"refId": ref, "datasource": MYSQL, "rawSql": raw, "format": fmt, "rawQuery": True,
            "editorMode": "code"}


def stat_opts(calc="lastNotNull", graph="area", color="value"):
    return {"reduceOptions": {"calcs": [calc], "fields": "", "values": False},
            "graphMode": graph, "colorMode": color, "textMode": "auto", "justifyMode": "auto",
            "orientation": "auto"}


def ts_opts(calcs=None, mode="list", placement="bottom"):
    return {"legend": {"displayMode": mode, "placement": placement, "showLegend": True,
                       "calcs": calcs or []},
            "tooltip": {"mode": "multi", "sort": "desc"}}


def dashboard(uid, title, folder, tags, panels, templating=None, time_from="now-6h", refresh="1m",
              desc="", version=1, links=None):
    return {"uid": uid, "title": title, "folderUid": folder, "tags": tags, "description": desc,
            "editable": False, "graphTooltip": 1, "panels": panels, "refresh": refresh,
            "schemaVersion": 38, "style": "dark", "timezone": "browser", "version": version,
            "time": {"from": time_from, "to": "now"},
            "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h"]},
            "templating": {"list": templating or []}, "annotations": {"list": [
                {"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True,
                 "hide": True, "iconColor": "rgba(0, 211, 255, 1)", "name": "Annotations & Alerts",
                 "type": "dashboard"}]},
            "links": links or [], "fiscalYearStartMonth": 0, "liveNow": False, "weekStart": ""}


def var_custom(name, label, options, multi=True, include_all=True, current=None):
    return {"name": name, "label": label, "type": "custom", "multi": multi, "includeAll": include_all,
            "query": ",".join(options), "options": [{"text": o, "value": o} for o in options],
            "current": current or ({"text": "All", "value": "$__all"} if include_all
                                   else {"text": options[0], "value": options[0]})}


def var_query(name, label, ds, query, multi=False, include_all=False, current=None):
    return {"name": name, "label": label, "type": "query", "datasource": ds, "query": query,
            "refresh": 1, "multi": multi, "includeAll": include_all, "sort": 1,
            "current": current or {}, "options": []}


# ---------- Web frontends (Prometheus / nginx exporter)
_I = 'instance=~"$instance"'
WEB = dashboard("atb-web-fe", "Web frontends", "atb-prod", ["nginx", "prod", "e-shop"], [
    panel("stat", "Requests / s", 0, 0, 4, 4, [prom(f'sum(rate(nginx_http_requests_total{{{_I}}}[5m]))')],
          PROM, "reqps", decimals=1, options=stat_opts()),
    panel("stat", "5xx ratio", 4, 0, 4, 4, [prom(
        f'sum(rate(nginx_http_requests_total{{{_I},status=~"5.."}}[5m])) / '
        f'sum(rate(nginx_http_requests_total{{{_I}}}[5m])) * 100')],
          PROM, "percent", decimals=2, thresholds=_thr("green", 1, "#EAB839", 2, "red"),
          options=stat_opts()),
    panel("stat", "Latency p95", 8, 0, 4, 4, [prom(
        f'histogram_quantile(0.95, sum by (le) (rate(nginx_request_duration_seconds_bucket{{{_I}}}[5m])))')],
          PROM, "s", thresholds=_thr("green", .5, "#EAB839", .8, "red"), options=stat_opts()),
    panel("stat", "Active connections", 12, 0, 4, 4, [prom(f'sum(nginx_connections_active{{{_I}}})')],
          PROM, "short", decimals=0, options=stat_opts()),
    panel("stat", "Orders / min", 16, 0, 4, 4, [prom('sum(rate(ishop_orders_total[5m])) * 60')],
          PROM, "short", decimals=1, options=stat_opts(), thresholds=_thr("blue")),
    panel("stat", "Upstreams up", 20, 0, 4, 4, [prom(f'sum(up{{job="nginx",{_I}}})')], PROM, "short",
          options=stat_opts(graph="none", color="background"), thresholds=_thr("red", 1, "green")),
    panel("timeseries", "Requests by instance", 0, 4, 12, 8,
          [prom(f'sum by (instance) (rate(nginx_http_requests_total{{{_I}}}[5m]))', "{{instance}}")],
          PROM, "reqps", options=ts_opts(["mean", "max", "lastNotNull"], "table")),
    panel("timeseries", "Responses by status", 12, 4, 12, 8,
          [prom(f'sum by (status) (rate(nginx_http_requests_total{{{_I}}}[5m]))', "{{status}}")],
          PROM, "reqps", options=ts_opts(), custom={"stacking": {"mode": "normal", "group": "A"},
                                                     "fillOpacity": 30}),
    panel("timeseries", "Request latency", 0, 12, 12, 8, [
        prom(f'histogram_quantile(0.50, sum by (le) (rate(nginx_request_duration_seconds_bucket{{{_I}}}[5m])))',
             "p50", "A"),
        prom(f'histogram_quantile(0.95, sum by (le) (rate(nginx_request_duration_seconds_bucket{{{_I}}}[5m])))',
             "p95", "B"),
        prom(f'histogram_quantile(0.99, sum by (le) (rate(nginx_request_duration_seconds_bucket{{{_I}}}[5m])))',
             "p99", "C")], PROM, "s", options=ts_opts(["mean", "max"])),
    panel("timeseries", "E-shop orders per minute", 12, 12, 12, 8,
          [prom('sum by (channel) (rate(ishop_orders_total[5m])) * 60', "{{channel}}")], PROM, "short",
          options=ts_opts(["mean", "lastNotNull"])),
    panel("timeseries", "Network egress (eth0)", 0, 20, 12, 8,
          [prom(f'rate(node_network_transmit_bytes_total{{{_I},device="eth0"}}[5m]) * 8', "{{instance}}")],
          PROM, "bps", options=ts_opts()),
    panel("table", "Traffic by virtual host (now)", 12, 20, 12, 8,
          [prom(f'sum by (instance, host) (rate(nginx_http_requests_total{{{_I}}}[5m]))', "", instant=True,
                fmt="table")], PROM, "reqps", decimals=1,
          options={"showHeader": True, "sortBy": [{"displayName": "Value", "desc": True}]}),
], [var_custom("instance", "Instance", ["www-p01", "www-p02", "mob-api-p01"])],
    desc="nginx edge for atbmarket.com, www and the mobile API")

# ---------- Supplier portal (sp-web-p01, SuiteCRM)
_SP = 'instance="sp-web-p01"'
SUPPLIER = dashboard("sp-portal", "Supplier portal traffic", "atb-prod", ["suitecrm", "suppliers", "prod"], [
    panel("stat", "Requests / s", 0, 0, 4, 4, [prom(f'sum(rate(nginx_http_requests_total{{{_SP}}}[5m]))')],
          PROM, "reqps", decimals=2, options=stat_opts()),
    panel("stat", "Active sessions", 4, 0, 4, 4, [prom('sum(suitecrm_active_sessions)')], PROM, "short",
          options=stat_opts()),
    panel("stat", "Logins / h", 8, 0, 4, 4,
          [prom('sum(rate(suitecrm_logins_total{result="success"}[1h])) * 3600')], PROM, "short",
          decimals=0, options=stat_opts()),
    panel("stat", "Failed logins / h", 12, 0, 4, 4,
          [prom('sum(rate(suitecrm_logins_total{result="failure"}[1h])) * 3600')], PROM, "short",
          decimals=0, thresholds=_thr("green", 30, "#EAB839", 60, "red"), options=stat_opts()),
    panel("stat", "Imports (24h)", 16, 0, 4, 4, [prom('sum(increase(suitecrm_import_jobs_total[24h]))')],
          PROM, "short", decimals=0, options=stat_opts(graph="none"), thresholds=_thr("blue")),
    panel("gauge", "PHP-FPM busy workers", 20, 0, 4, 4,
          [prom('sum(phpfpm_active_processes) / (sum(phpfpm_active_processes) + '
                'sum(phpfpm_idle_processes)) * 100')], PROM, "percent", minv=0, maxv=100,
          thresholds=_thr("green", 70, "#EAB839", 90, "red"),
          options={"reduceOptions": {"calcs": ["lastNotNull"]}, "showThresholdMarkers": True}),
    panel("timeseries", "Responses by status", 0, 4, 12, 8,
          [prom(f'sum by (status) (rate(nginx_http_requests_total{{{_SP}}}[5m]))', "{{status}}")], PROM,
          "reqps", options=ts_opts(), custom={"stacking": {"mode": "normal", "group": "A"},
                                              "fillOpacity": 30}),
    panel("timeseries", "Logins", 12, 4, 12, 8,
          [prom('sum by (result) (rate(suitecrm_logins_total[5m])) * 60', "{{result}}")], PROM,
          "short", options=ts_opts(["sum", "max"]),
          overrides=[{"matcher": {"id": "byName", "options": "failure"},
                      "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]},
                     {"matcher": {"id": "byName", "options": "success"},
                      "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]}]),
    panel("timeseries", "Response time", 0, 12, 12, 8, [
        prom(f'histogram_quantile(0.50, sum by (le) (rate(nginx_request_duration_seconds_bucket{{{_SP}}}[5m])))',
             "p50", "A"),
        prom(f'histogram_quantile(0.95, sum by (le) (rate(nginx_request_duration_seconds_bucket{{{_SP}}}[5m])))',
             "p95", "B")], PROM, "s", options=ts_opts(["mean", "max"])),
    panel("timeseries", "Upload volume", 12, 12, 12, 8,
          [prom('sum(rate(suitecrm_upload_bytes_total[5m]))', "uploads")], PROM, "Bps",
          options=ts_opts(["mean", "max"])),
    panel("bargauge", "Requests by module (now)", 0, 20, 12, 9,
          [prom('sum by (module) (rate(suitecrm_requests_total[5m]))', "{{module}}", instant=True)], PROM,
          "reqps", decimals=2, options={"orientation": "horizontal", "displayMode": "gradient",
                                        "reduceOptions": {"calcs": ["lastNotNull"]}}),
    panel("timeseries", "Import jobs", 12, 20, 12, 9,
          [prom('sum by (status) (increase(suitecrm_import_jobs_total[1h]))', "{{status}}")], PROM, "short",
          options=ts_opts(["sum"]), custom={"drawStyle": "bars", "fillOpacity": 60}),
], desc="supplier.atbmarket.com (SuiteCRM on sp-web-p01)", time_from="now-12h")

# ---------- Node exporter
_N = 'instance="$instance"'
NODE = dashboard("node-linux", "Node exporter — Linux hosts", "infra", ["linux", "node-exporter"], [
    panel("gauge", "CPU busy", 0, 0, 4, 5,
          [prom(f'100 - avg(rate(node_cpu_seconds_total{{{_N},mode="idle"}}[5m])) * 100')], PROM, "percent",
          minv=0, maxv=100, thresholds=CPU_THR, options={"reduceOptions": {"calcs": ["lastNotNull"]}}),
    panel("gauge", "RAM used", 4, 0, 4, 5,
          [prom(f'(1 - node_memory_MemAvailable_bytes{{{_N}}} / node_memory_MemTotal_bytes{{{_N}}}) * 100')],
          PROM, "percent", minv=0, maxv=100, thresholds=_thr("green", 80, "#EAB839", 90, "red"),
          options={"reduceOptions": {"calcs": ["lastNotNull"]}}),
    panel("gauge", "Root FS used", 8, 0, 4, 5,
          [prom(f'(1 - node_filesystem_avail_bytes{{{_N},mountpoint="/"}} / '
                f'node_filesystem_size_bytes{{{_N},mountpoint="/"}}) * 100')],
          PROM, "percent", minv=0, maxv=100, thresholds=_thr("green", 80, "#EAB839", 90, "red"),
          options={"reduceOptions": {"calcs": ["lastNotNull"]}}),
    panel("stat", "Load (1m)", 12, 0, 4, 5, [prom(f'node_load1{{{_N}}}')], PROM, "short", decimals=2,
          options=stat_opts()),
    panel("stat", "RAM total", 16, 0, 4, 5, [prom(f'node_memory_MemTotal_bytes{{{_N}}}')], PROM, "bytes",
          options=stat_opts(graph="none"), thresholds=_thr("blue")),
    panel("stat", "Uptime", 20, 0, 4, 5, [prom(f'node_time_seconds{{{_N}}} - node_boot_time_seconds{{{_N}}}')],
          PROM, "s", options=stat_opts(graph="none"), thresholds=_thr("blue"), decimals=1),
    panel("timeseries", "CPU", 0, 5, 12, 8,
          [prom(f'sum by (mode) (rate(node_cpu_seconds_total{{{_N},mode!="idle"}}[5m])) * 100', "{{mode}}")],
          PROM, "percent", minv=0, options=ts_opts(["mean", "max"]),
          custom={"stacking": {"mode": "normal", "group": "A"}, "fillOpacity": 40}),
    panel("timeseries", "Memory", 12, 5, 12, 8, [
        prom(f'node_memory_MemTotal_bytes{{{_N}}} - node_memory_MemAvailable_bytes{{{_N}}}', "used", "A"),
        prom(f'node_memory_MemTotal_bytes{{{_N}}}', "total", "B")], PROM, "bytes", minv=0,
          options=ts_opts(["lastNotNull"])),
    panel("timeseries", "Network traffic (eth0)", 0, 13, 12, 8, [
        prom(f'rate(node_network_receive_bytes_total{{{_N},device="eth0"}}[5m]) * 8', "rx", "A"),
        prom(f'rate(node_network_transmit_bytes_total{{{_N},device="eth0"}}[5m]) * 8', "tx", "B")],
          PROM, "bps", options=ts_opts(["mean", "max"])),
    panel("timeseries", "Disk space used (/)", 12, 13, 12, 8,
          [prom(f'node_filesystem_size_bytes{{{_N},mountpoint="/"}} - '
                f'node_filesystem_avail_bytes{{{_N},mountpoint="/"}}', "/")], PROM, "bytes",
          options=ts_opts(["lastNotNull"])),
], [var_query("instance", "Host", PROM, 'label_values(up{job="node"}, instance)',
              current={"text": "www-p01", "value": "www-p01"})],
    desc="node_exporter 1.6 — prod Linux fleet")

# ---------- Zabbix host overview (MySQL — the Zabbix 6.0 database)
_HOSTS_WHERE = "h.status IN (0, 1) AND h.flags IN (0, 4)"
_SEV = ("CASE p.severity WHEN 5 THEN 'Disaster' WHEN 4 THEN 'High' WHEN 3 THEN 'Average' "
        "WHEN 2 THEN 'Warning' WHEN 1 THEN 'Information' ELSE 'Not classified' END")
_OPEN = "p.source = 0 AND p.object = 0 AND p.r_eventid IS NULL"


def _item_ts(tbl, where):
    return ("SELECT $__unixEpochGroupAlias(x.clock, $__interval), i.name AS metric, AVG(x.value) AS value\n"
            f"FROM {tbl} x\nJOIN items i ON i.itemid = x.itemid\nJOIN hosts h ON h.hostid = i.hostid\n"
            f"WHERE {where} AND $__unixEpochFilter(x.clock)\nGROUP BY 1, 2\nORDER BY 1")


def _key_ts(tbl, key_cond):
    return _item_ts(tbl, f"h.status = 0 AND {key_cond}")


ZBX_HOSTS = dashboard("zbx-hosts", "Zabbix — host overview", "zabbix", ["zabbix", "hosts"], [
    panel("stat", "Monitored hosts", 0, 0, 4, 4, [sql(
        "SELECT COUNT(*) AS hosts FROM hosts h WHERE h.status = 0 AND h.flags IN (0, 4)", fmt="table")],
          MYSQL, "short", options=stat_opts(graph="none"), thresholds=_thr("blue")),
    panel("stat", "Enabled items", 4, 0, 4, 4, [sql(
        "SELECT COUNT(*) AS items FROM items i JOIN hosts h ON h.hostid = i.hostid\n"
        "WHERE h.status = 0 AND h.flags IN (0, 4) AND i.status = 0 AND i.flags IN (0, 4)", fmt="table")],
          MYSQL, "short", options=stat_opts(graph="none"), thresholds=_thr("blue")),
    panel("stat", "Agents available", 8, 0, 4, 4, [sql(
        "SELECT COUNT(*) AS available FROM interface n JOIN hosts h ON h.hostid = n.hostid\n"
        "WHERE h.status = 0 AND h.flags IN (0, 4) AND n.type = 1 AND n.main = 1 AND n.available = 1",
        fmt="table")],
          MYSQL, "short", options=stat_opts(graph="none"), thresholds=_thr("blue")),
    panel("stat", "Interfaces unavailable", 12, 0, 4, 4, [sql(
        "SELECT COUNT(*) AS unavailable FROM interface n JOIN hosts h ON h.hostid = n.hostid\n"
        "WHERE h.status = 0 AND h.flags IN (0, 4) AND n.main = 1 AND n.available = 2", fmt="table")],
          MYSQL, "short", options=stat_opts(graph="none", color="background"), thresholds=_thr("green", 1, "red")),
    panel("stat", "Open problems", 16, 0, 4, 4, [sql(
        f"SELECT COUNT(*) AS problems FROM problem p WHERE {_OPEN}", fmt="table")], MYSQL, "short",
          options=stat_opts(graph="none", color="background"), thresholds=_thr("green", 1, "#EAB839", 10, "red")),
    panel("stat", "Values stored (1h)", 20, 0, 4, 4, [sql(
        "SELECT (SELECT COUNT(*) FROM history WHERE clock > UNIX_TIMESTAMP() - 3600)\n"
        "     + (SELECT COUNT(*) FROM history_uint WHERE clock > UNIX_TIMESTAMP() - 3600) AS `values`",
        fmt="table")], MYSQL, "short", options=stat_opts(graph="none"), thresholds=_thr("blue")),
    panel("table", "Hosts", 0, 4, 24, 8, [sql(
        "SELECT h.host AS `Host`, h.name AS `Visible name`,\n"
        "       CASE h.status WHEN 0 THEN 'Enabled' ELSE 'Disabled' END AS `Status`,\n"
        "       CONCAT(IF(n.useip = 1, n.ip, n.dns), ':', n.port) AS `Interface`,\n"
        "       CASE n.type WHEN 1 THEN 'ZBX' WHEN 2 THEN 'SNMP' WHEN 3 THEN 'IPMI' WHEN 4 THEN 'JMX' ELSE '' END AS `Type`,\n"
        "       CASE n.available WHEN 1 THEN 'Available' WHEN 2 THEN 'Unavailable' ELSE 'Unknown' END AS `Availability`,\n"
        "       (SELECT COUNT(*) FROM items it WHERE it.hostid = h.hostid AND it.status = 0 AND it.flags IN (0, 4)) AS `Items`\n"
        "FROM hosts h\nLEFT JOIN interface n ON n.hostid = h.hostid AND n.main = 1\n"
        f"WHERE {_HOSTS_WHERE}\nORDER BY h.host", fmt="table")], MYSQL,
          options={"showHeader": True, "cellHeight": "sm"},
          overrides=[{"matcher": {"id": "byName", "options": "Availability"},
                      "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}},
                                     {"id": "mappings", "value": [{"type": "value", "options": {
                                         "Available": {"color": "green"}, "Unavailable": {"color": "red"},
                                         "Unknown": {"color": "text"}}}]}]}]),
    panel("timeseries", "$item — $host", 0, 12, 16, 9, [
        sql(_item_ts("history", "h.host = '$host' AND i.name = '$item'"), "A"),
        sql(_item_ts("history_uint", "h.host = '$host' AND i.name = '$item'"), "B")], MYSQL, "",
          options=ts_opts(["mean", "max", "lastNotNull"])),
    panel("bargauge", "Open problems by severity", 16, 12, 8, 9, [sql(
        f"SELECT {_SEV} AS severity, COUNT(*) AS problems\nFROM problem p\nWHERE {_OPEN}\n"
        "GROUP BY p.severity ORDER BY p.severity DESC", fmt="table")], MYSQL, "short", decimals=0,
          options={"orientation": "horizontal", "displayMode": "gradient", "reduceOptions": {"calcs": ["lastNotNull"]}}),
    panel("table", "Latest data — $host", 0, 21, 24, 10, [sql(
        "SELECT i.name AS `Item`, i.key_ AS `Key`,\n"
        "       COALESCE((SELECT ROUND(x.value, 4) FROM history x WHERE x.itemid = i.itemid ORDER BY x.clock DESC LIMIT 1),\n"
        "                (SELECT x.value FROM history_uint x WHERE x.itemid = i.itemid ORDER BY x.clock DESC LIMIT 1)) AS `Last value`,\n"
        "       i.units AS `Units`,\n"
        "       FROM_UNIXTIME(NULLIF(GREATEST(COALESCE((SELECT MAX(x.clock) FROM history x WHERE x.itemid = i.itemid), 0),\n"
        "                                     COALESCE((SELECT MAX(x.clock) FROM history_uint x WHERE x.itemid = i.itemid), 0)), 0)) AS `Last check`\n"
        "FROM items i\nJOIN hosts h ON h.hostid = i.hostid\n"
        "WHERE h.host = '$host' AND i.status = 0 AND i.flags IN (0, 4) AND i.value_type IN (0, 3)\nORDER BY i.name",
        fmt="table")], MYSQL, options={"showHeader": True, "cellHeight": "sm"}),
    panel("table", "Problems", 0, 31, 24, 9, [sql(
        f"SELECT FROM_UNIXTIME(p.clock) AS `Time`, {_SEV} AS `Severity`,\n"
        "       MIN(h.host) AS `Host`, p.name AS `Problem`, IF(p.acknowledged = 1, 'Yes', 'No') AS `Ack`\n"
        "FROM problem p\nJOIN functions f ON f.triggerid = p.objectid\nJOIN items i ON i.itemid = f.itemid\n"
        f"JOIN hosts h ON h.hostid = i.hostid\nWHERE {_OPEN}\n"
        "GROUP BY p.eventid, p.clock, p.severity, p.name, p.acknowledged\nORDER BY p.clock DESC\nLIMIT 100",
        fmt="table")], MYSQL, options={"showHeader": True, "cellHeight": "sm"},
          overrides=[{"matcher": {"id": "byName", "options": "Severity"},
                      "properties": [{"id": "custom.cellOptions", "value": {"type": "color-background"}},
                                     {"id": "mappings", "value": [{"type": "value", "options": {
                                         "Disaster": {"color": "#E45959"}, "High": {"color": "#E97659"},
                                         "Average": {"color": "#FFA059"}, "Warning": {"color": "#FFC859"},
                                         "Information": {"color": "#7499FF"},
                                         "Not classified": {"color": "#97AAB3"}}}]}]}]),
], [var_query("host", "Host", MYSQL,
              f"SELECT h.host FROM hosts h WHERE {_HOSTS_WHERE} ORDER BY h.host",
              current={"text": "Zabbix server", "value": "Zabbix server"}),
    var_query("item", "Item", MYSQL,
              "SELECT DISTINCT i.name FROM items i JOIN hosts h ON h.hostid = i.hostid\n"
              "WHERE h.host = '$host' AND i.status = 0 AND i.flags IN (0, 4) AND i.value_type IN (0, 3)\n"
              "ORDER BY 1")],
    desc="Hosts, items, history and problems straight from the Zabbix database", refresh="1m")

# ---------- Zabbix server health (internal items of the "Zabbix server health" template)
ZBX_SERVER = dashboard("zbx-server", "Zabbix server health", "zabbix", ["zabbix"], [
    panel("stat", "New values per second", 0, 0, 5, 4, [sql(_key_ts("history", "i.key_ = 'zabbix[wcache,values]'"))],
          MYSQL, "short", decimals=1, options=stat_opts()),
    panel("stat", "Queue (over 10 min)", 5, 0, 5, 4, [sql(_key_ts("history_uint", "i.key_ = 'zabbix[queue,10m]'"))],
          MYSQL, "short", thresholds=_thr("green", 10, "#EAB839", 100, "red"), options=stat_opts()),
    panel("stat", "Preprocessing queue", 10, 0, 5, 4,
          [sql(_key_ts("history_uint", "i.key_ = 'zabbix[preprocessing_queue]'"))], MYSQL, "short",
          thresholds=_thr("green", 100, "#EAB839", 1000, "red"), options=stat_opts()),
    panel("stat", "Value cache used", 15, 0, 5, 4, [sql(_key_ts("history", "i.key_ = 'zabbix[vcache,buffer,pused]'"))],
          MYSQL, "percent", decimals=1, thresholds=_thr("green", 75, "#EAB839", 95, "red"), options=stat_opts()),
    panel("stat", "Frontend sessions (active)", 20, 0, 4, 4, [sql(
        "SELECT COUNT(*) AS sessions FROM sessions WHERE status = 0", fmt="table")], MYSQL, "short",
          options=stat_opts(graph="none"), thresholds=_thr("blue")),
    panel("timeseries", "Utilization of data collector processes", 0, 4, 12, 9,
          [sql(_key_ts("history", "i.key_ LIKE 'zabbix[process,%,avg,busy]' AND i.name LIKE '%collector%'"))],
          MYSQL, "percent", minv=0, options=ts_opts(["mean", "max"], "table", "right")),
    panel("timeseries", "Utilization of internal processes", 12, 4, 12, 9,
          [sql(_key_ts("history", "i.key_ LIKE 'zabbix[process,%,avg,busy]' AND i.name NOT LIKE '%collector%'"))],
          MYSQL, "percent", minv=0, options=ts_opts(["mean", "max"], "table", "right")),
    panel("timeseries", "Cache usage", 0, 13, 12, 8,
          [sql(_key_ts("history", "i.key_ LIKE 'zabbix[%,pused]'"))], MYSQL, "percent", minv=0,
          options=ts_opts(["lastNotNull"], "table", "right")),
    panel("timeseries", "Values processed / queue", 12, 13, 12, 8, [
        sql(_key_ts("history", "i.key_ = 'zabbix[wcache,values]'"), "A"),
        sql(_key_ts("history_uint", "i.key_ IN ('zabbix[queue]', 'zabbix[queue,10m]')"), "B")], MYSQL, "short",
          options=ts_opts(["mean", "max"])),
    panel("table", "Items per host", 0, 21, 12, 8, [sql(
        "SELECT h.host AS `Host`, COUNT(i.itemid) AS `Items`,\n"
        "       SUM(i.value_type = 0) AS `Float`, SUM(i.value_type = 3) AS `Unsigned`,\n"
        "       SUM(i.value_type IN (1, 2, 4)) AS `Text/log`\n"
        "FROM hosts h LEFT JOIN items i ON i.hostid = h.hostid AND i.status = 0 AND i.flags IN (0, 4)\n"
        f"WHERE {_HOSTS_WHERE}\nGROUP BY h.host ORDER BY 2 DESC", fmt="table")], MYSQL, options={"showHeader": True}),
    panel("table", "Frontend sessions by user", 12, 21, 12, 8, [sql(
        "SELECT u.username AS `User`, COUNT(*) AS `Sessions`,\n"
        "       FROM_UNIXTIME(MAX(s.lastaccess)) AS `Last access`\n"
        "FROM sessions s JOIN users u ON u.userid = s.userid\nWHERE s.status = 0\n"
        "GROUP BY u.username ORDER BY 3 DESC", fmt="table")], MYSQL, options={"showHeader": True}),
], desc="zb-app-p01 internals (Zabbix server health template)", refresh="1m", time_from="now-3h")

# ---------- Home
HOME = dashboard("noc-home", "ATB NOC — Home", None, ["noc"], [
    panel("text", "", 0, 0, 24, 4, options={"mode": "html", "content":
        '<div class="home-hero"><div><h2>ATB Monitoring</h2>'
        '<p>Production observability for atbmarket.com, the supplier portal and the e-learning platform. '
        'Data sources: <b>Prometheus</b> (prom-p01) and the <b>Zabbix</b> database.</p>'
        '<p class="muted">On-call: NOC, ext. 4410 &middot; noc@atbmarket.com &middot; '
        'escalation matrix in Confluence &rarr; OPS / On-call.</p></div></div>'}),
    panel("dashlist", "Starred dashboards", 0, 4, 8, 9, options={"showStarred": True}),
    panel("dashlist", "Recently viewed dashboards", 8, 4, 8, 9, options={"showRecentlyViewed": True}),
    panel("alertlist", "Alert rules", 16, 4, 8, 9, options={"stateFilter": {"firing": True, "pending": True}}),
    panel("stat", "Web requests / s", 0, 13, 6, 5,
          [prom('sum(rate(nginx_http_requests_total{job="nginx"}[5m]))')], PROM, "reqps", decimals=0,
          options=stat_opts()),
    panel("stat", "Orders / min", 6, 13, 6, 5, [prom('sum(rate(ishop_orders_total[5m])) * 60')], PROM,
          "short", decimals=1, options=stat_opts(), thresholds=_thr("blue")),
    panel("stat", "Supplier portal sessions", 12, 13, 6, 5, [prom('sum(suitecrm_active_sessions)')], PROM,
          "short", options=stat_opts(), thresholds=_thr("purple")),
    panel("stat", "Zabbix problems", 18, 13, 6, 5, [sql(
        f"SELECT COUNT(*) AS problems FROM problem p WHERE {_OPEN}", fmt="table")],
          MYSQL, "short", options=stat_opts(graph="none", color="background"),
          thresholds=_thr("green", 1, "#EAB839", 10, "red")),
], time_from="now-6h", refresh="")

DASHBOARDS = [HOME, WEB, SUPPLIER, NODE, ZBX_HOSTS, ZBX_SERVER]
for _i, _d in enumerate(DASHBOARDS):
    _d["id"] = 20 + _i
DASH_BY_UID = {d["uid"]: d for d in DASHBOARDS}
HOME_UID = "noc-home"


def slug(title):
    import re
    s = title.lower().replace("—", "-")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-+", "-", s)


def dash_url(d):
    return f"/d/{d['uid']}/{slug(d['title'])}"


PLAYLISTS = [{"id": 1, "uid": "noc-wall", "name": "NOC video wall", "interval": "2m",
              "items": ["atb-web-fe", "sp-portal", "zbx-hosts", "node-linux"]}]

# ------------------------------------------------------------- alert rules
# (uid, title, folder, group, datasource, query, reducer, op, threshold, for, labels, summary)
ALERT_RULES = [
    {"uid": "a1sp5xx", "title": "Supplier portal 5xx ratio > 2%", "folder": "atb-prod", "group": "supplier-portal",
     "interval": "1m", "ds": PROM, "for": "5m", "op": ">", "threshold": 2.0,
     "query": 'sum(rate(nginx_http_requests_total{instance="sp-web-p01",status=~"5.."}[5m])) / '
              'sum(rate(nginx_http_requests_total{instance="sp-web-p01"}[5m])) * 100',
     "labels": {"severity": "warning", "team": "supplier-it"},
     "summary": "More than 2% of supplier.atbmarket.com responses are 5xx."},
    {"uid": "a2splogin", "title": "Supplier portal failed logins spike", "folder": "atb-prod",
     "group": "supplier-portal", "interval": "1m", "ds": PROM, "for": "10m", "op": ">", "threshold": 60,
     "query": 'sum(rate(suitecrm_logins_total{result="failure"}[1h])) * 3600',
     "labels": {"severity": "warning", "team": "supplier-it"},
     "summary": "Failed SuiteCRM logins above 60/h — possible credential stuffing."},
    {"uid": "a3webp95", "title": "Web p95 latency > 800 ms", "folder": "atb-prod", "group": "web-frontends",
     "interval": "1m", "ds": PROM, "for": "5m", "op": ">", "threshold": 0.8,
     "query": 'histogram_quantile(0.95, sum by (le) (rate(nginx_request_duration_seconds_bucket'
              '{instance=~"www-p01|www-p02"}[5m])))',
     "labels": {"severity": "critical", "team": "ecom"}, "summary": "Storefront p95 above 800 ms."},
    {"uid": "a4orders", "title": "E-shop orders dropped below 10/min", "folder": "atb-prod",
     "group": "web-frontends", "interval": "1m", "ds": PROM, "for": "15m", "op": "<", "threshold": 10,
     "query": 'sum(rate(ishop_orders_total[5m])) * 60',
     "labels": {"severity": "critical", "team": "ecom"}, "summary": "Checkout may be broken."},
    {"uid": "a5nodemem", "title": "Node memory > 90%", "folder": "infra", "group": "linux", "interval": "1m",
     "ds": PROM, "for": "10m", "op": ">", "threshold": 90,
     "query": 'max((1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100)',
     "labels": {"severity": "warning", "team": "infra"}, "summary": "A Linux host is running out of memory."},
    {"uid": "a6nodecpu", "title": "Node CPU busy > 85%", "folder": "infra", "group": "linux", "interval": "1m",
     "ds": PROM, "for": "15m", "op": ">", "threshold": 85,
     "query": 'max(100 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
     "labels": {"severity": "warning", "team": "infra"}, "summary": "Sustained high CPU on a prod host."},
    {"uid": "a7zbxhigh", "title": "Zabbix: High/Disaster problems open", "folder": "zabbix",
     "group": "zabbix-problems", "interval": "1m", "ds": MYSQL, "for": "0s", "op": ">", "threshold": 0,
     "query": "SELECT 'zabbix' AS metric, COUNT(*) AS value\nFROM problem p\n"
              "WHERE p.source = 0 AND p.object = 0 AND p.r_eventid IS NULL AND p.severity >= 4",
     "labels": {"severity": "critical", "team": "noc"},
     "summary": "There are High or Disaster problems open in Zabbix."},
    {"uid": "a8zbxping", "title": "Zabbix agent unreachable", "folder": "zabbix", "group": "zabbix-agents",
     "interval": "1m", "ds": MYSQL, "for": "5m", "op": "<", "threshold": 1,
     "query": "SELECT h.host AS metric, IF(n.available = 2, 0, 1) AS value\nFROM hosts h\n"
              "JOIN interface n ON n.hostid = h.hostid AND n.main = 1 AND n.type = 1\n"
              "WHERE h.status = 0 AND h.flags IN (0, 4)",
     "labels": {"severity": "critical", "team": "noc"}, "summary": "Zabbix agent on {{ $labels.metric }} is unavailable."},
]

CONTACT_POINTS = [
    {"name": "NOC e-mail", "type": "email", "settings": "noc@atbmarket.com; infra@atbmarket.com"},
    {"name": "Telegram NOC", "type": "telegram", "settings": "Chat ID -1001738264410 · Bot token configured"},
    {"name": "E-commerce on-call", "type": "email", "settings": "ecom-oncall@atbmarket.com"},
    {"name": "grafana-default-email", "type": "email", "settings": "<example@email.com>"},
]

SETTINGS = {
    "DEFAULT": {"app_mode": "production", "instance_name": "grafana.atbmarket.com"},
    "analytics": {"check_for_updates": "false", "reporting_enabled": "false"},
    "auth": {"disable_login_form": "false", "login_maximum_inactive_lifetime_duration": "7d",
             "oauth_auto_login": "false"},
    "auth.anonymous": {"enabled": "false"},
    "auth.ldap": {"allow_sign_up": "true", "config_file": "/etc/grafana/ldap.toml", "enabled": "true"},
    "database": {"type": "sqlite3", "path": "grafana.db", "host": "127.0.0.1:3306", "name": "grafana",
                 "user": "root", "password": "************"},
    "log": {"level": "info", "mode": "console file"},
    "paths": {"data": "/var/lib/grafana", "logs": "/var/log/grafana", "plugins": "/var/lib/grafana/plugins",
              "provisioning": "/etc/grafana/provisioning"},
    "security": {"admin_user": "admin", "admin_password": "************", "secret_key": "************",
                 "cookie_secure": "false", "disable_gravatar": "true", "allow_embedding": "true"},
    "server": {"protocol": "http", "http_port": "3000", "domain": "grafana.atbmarket.com",
               "root_url": "http://grafana.atbmarket.com:3000/", "enable_gzip": "true"},
    "smtp": {"enabled": "true", "host": "mail.atbmarket.com:25", "user": "grafana@atbmarket.com",
             "password": "************", "from_address": "grafana@atbmarket.com", "from_name": "ATB Grafana",
             "skip_verify": "true"},
    "users": {"allow_sign_up": "false", "auto_assign_org_role": "Viewer", "default_theme": "dark"},
    "unified_alerting": {"enabled": "true", "evaluation_timeout": "30s"},
}
