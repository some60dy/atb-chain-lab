FROM atb-base:latest
COPY services/grafana/app.py /app/app.py
ENV ATB_SERVICE=grafana ATB_HOSTNAME=grafana.atbmarket.com
EXPOSE 3000
CMD ["python", "/app/app.py"]
