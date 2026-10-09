# zb-app-p01 — the real Zabbix 6.0 LTS server (official image).
# Misconfiguration on purpose: the daemon runs as root (AllowRoot=1), so global
# scripts executed "on Zabbix server" run as root. zabbix_get ships with the image.
FROM zabbix/zabbix-server-mysql:ubuntu-6.0-latest
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client netcat-openbsd \
    && rm -rf /var/lib/apt/lists/* \
    && echo 'AllowRoot=1' >> /etc/zabbix/zabbix_server.conf
