FROM atb-base:latest
# sp-web-p01 is a real ops jump-off: it ships the clients an attacker would use
# to pivot from the web-shell (DB clients, ssh, nc) — mirrors the report's host.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         default-mysql-client postgresql-client openssh-client \
         netcat-openbsd curl iputils-ping ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# mirror the report: service runs as unprivileged nginx (uid 993) on sp-web-p01
RUN groupadd -g 990 nginx && useradd -u 993 -g 990 -M -s /usr/sbin/nologin nginx \
    && mkdir -p /var/www /app/upload \
    && chown -R nginx:nginx /app
# small client for the Oracle mocks (tab protocol), on PATH for the shell user
COPY attack/oracle_probe.py /usr/local/bin/oracle_probe.py
COPY services/supplier/app.py /app/app.py
COPY services/supplier/crm.py /app/crm.py
COPY services/supplier/suitecrm_seed.py /app/suitecrm_seed.py
COPY services/supplier/config.php /var/www/config.php
# also at the app CWD so the report's relative read (importFile=config.php) works
COPY services/supplier/config.php /app/config.php
COPY services/supplier/config_override.php /var/www/config_override.php
COPY services/supplier/config_override.php /app/config_override.php
COPY services/supplier/fs/InboundEmail.php /var/www/custom/blowfish/InboundEmail.php
COPY services/supplier/fs/zabbix_agentd.conf /etc/zabbix/zabbix_agentd.conf
COPY services/supplier/fs/README.ops /var/www/README.ops
ENV ATB_SERVICE=supplier ATB_HOSTNAME=sp-web-p01
USER nginx
EXPOSE 80
CMD ["python", "/app/app.py"]
