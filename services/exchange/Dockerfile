FROM atb-base:latest
COPY services/exchange/app.py services/exchange/mailseed.py /app/
RUN mkdir -p /var/lib/owa
ENV ATB_SERVICE=exchange ATB_HOSTNAME=ex.atbmarket.com
EXPOSE 80
CMD ["python", "/app/app.py"]
