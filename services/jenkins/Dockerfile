FROM atb-base:latest
COPY services/jenkins/fs/zabbix_agentd.conf /etc/zabbix/zabbix_agentd.conf
COPY services/jenkins/fs/fstab /etc/fstab
COPY services/jenkins/app.py /app/app.py
ENV ATB_SERVICE=jenkins ATB_HOSTNAME=jenkins.atbmarket.com
EXPOSE 10050
CMD ["python", "/app/app.py"]
