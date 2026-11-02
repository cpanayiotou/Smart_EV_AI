FROM python:3.12-alpine
RUN apk add --no-cache tzdata
WORKDIR /app
RUN adduser -D -H -u 10001 connector && mkdir /data && chown connector:connector /data && chmod 700 /data
COPY app.py abrp.py solar.py automation.py control.py pairing.py cloud_main.py setup_web.py wizard.html wizard.js wizard.css /app/
RUN chmod 0755 /app && chmod 0644 /app/*.py /app/wizard.html /app/wizard.js /app/wizard.css
USER connector
RUN python -B -c "import app, abrp, cloud_main, setup_web; from pathlib import Path; [Path(p).read_bytes() for p in ('wizard.html', 'wizard.js', 'wizard.css')]"
EXPOSE 7080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import os,urllib.request; host=os.getenv('CONNECTOR_HOST','0.0.0.0'); host='127.0.0.1' if host=='0.0.0.0' else host; urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://'+host+':7080/health', timeout=3)"
CMD ["python", "/app/cloud_main.py"]
