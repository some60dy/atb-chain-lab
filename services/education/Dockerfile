FROM atb-base:latest
COPY services/education/app.py /app/app.py
ENV ATB_SERVICE=education ATB_HOSTNAME=education.atbmarket.com
EXPOSE 80
CMD ["python", "/app/app.py"]
