FROM atb-base:latest
COPY services/oracle-mocks/app.py /app/app.py
ENV ATB_SERVICE=oracle-mocks ATB_HOSTNAME=oracle-db
EXPOSE 1581 1521 1251
CMD ["python", "/app/app.py"]
