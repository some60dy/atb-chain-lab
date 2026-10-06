FROM atb-base:latest
COPY services/exchange/app.py /app/app.py
ENV ATB_SERVICE=exchange ATB_HOSTNAME=ex.atbmarket.com
EXPOSE 80
CMD ["python", "/app/app.py"]
