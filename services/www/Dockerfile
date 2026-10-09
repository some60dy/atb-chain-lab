FROM atb-base:latest
RUN pip install --no-cache-dir bcrypt==4.2.1
COPY services/www/app.py /app/app.py
ENV ATB_SERVICE=www ATB_HOSTNAME=www.atbmarket.com
EXPOSE 80
CMD ["python", "/app/app.py"]
