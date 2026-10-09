FROM atb-base:latest
COPY services/grafana/app.py services/grafana/gdata.py services/grafana/gmetrics.py /app/
COPY services/grafana/static /app/static
ENV ATB_SERVICE=grafana ATB_HOSTNAME=grafana.atbmarket.com
EXPOSE 3000
CMD ["python", "/app/app.py"]
