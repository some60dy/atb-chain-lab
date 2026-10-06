FROM atb-base:latest
COPY services/mobapp/app.py /app/app.py
ENV ATB_SERVICE=mobapp ATB_HOSTNAME=mobapp.atbmarket.com
EXPOSE 80
CMD ["python", "/app/app.py"]
