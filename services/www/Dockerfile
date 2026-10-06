FROM atb-base:latest
COPY services/www/app.py /app/app.py
ENV ATB_SERVICE=www ATB_HOSTNAME=www.atbmarket.com
EXPOSE 80
CMD ["python", "/app/app.py"]
