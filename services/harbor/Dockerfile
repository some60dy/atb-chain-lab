FROM atb-base:latest
COPY services/harbor/app.py services/harbor/harbor_data.py /app/
ENV ATB_SERVICE=harbor ATB_HOSTNAME=sh-harb-p01
EXPOSE 80
CMD ["python", "/app/app.py"]
