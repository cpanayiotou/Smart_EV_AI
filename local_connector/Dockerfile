FROM python:3.12-alpine
WORKDIR /app
RUN adduser -D -H -u 10001 connector && mkdir /data && chown connector:connector /data && chmod 700 /data
COPY app.py pairing.py cloud_main.py setup_web.py wizard.html wizard.js wizard.css /app/
USER connector
EXPOSE 7080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import os,urllib.request; host=os.getenv('CONNECTOR_HOST','0.0.0.0'); host='127.0.0.1' if host=='0.0.0.0' else host; urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://'+host+':7080/health', timeout=3)"
CMD ["python", "/app/cloud_main.py"]
