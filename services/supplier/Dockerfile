FROM atb-base:latest
# mirror the report: service runs as unprivileged nginx (uid 993) on sp-web-p01
RUN groupadd -g 990 nginx && useradd -u 993 -g 990 -M -s /usr/sbin/nologin nginx \
    && mkdir -p /var/www /app/upload \
    && chown -R nginx:nginx /app
COPY services/supplier/app.py /app/app.py
COPY services/supplier/config.php /var/www/config.php
# also at the app CWD so the report's relative read (importFile=config.php) works
COPY services/supplier/config.php /app/config.php
COPY services/supplier/config_override.php /var/www/config_override.php
ENV ATB_SERVICE=supplier ATB_HOSTNAME=sp-web-p01
USER nginx
EXPOSE 80
CMD ["python", "/app/app.py"]
