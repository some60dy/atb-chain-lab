FROM atb-base:latest
COPY services/zabbix/app.py /app/app.py
ENV ATB_SERVICE=zabbix ATB_HOSTNAME=zb-app-p01
EXPOSE 80
CMD ["python", "/app/app.py"]
