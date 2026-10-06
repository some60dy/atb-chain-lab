FROM atb-base:latest
COPY services/ad-ldap/app.py /app/app.py
ENV ATB_SERVICE=ad-ldap ATB_HOSTNAME=DC-MAIN-01.atbmarket.com
EXPOSE 80
CMD ["python", "/app/app.py"]
