FROM atb-base:latest
# zb-app-p01 is the monitoring server: it ships zabbix_get and an ssh client
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*
COPY services/zabbix/fs/zabbix_get /usr/bin/zabbix_get
RUN chmod 755 /usr/bin/zabbix_get
COPY services/zabbix/app.py /app/app.py
ENV ATB_SERVICE=zabbix ATB_HOSTNAME=zb-app-p01
EXPOSE 80
CMD ["python", "/app/app.py"]
