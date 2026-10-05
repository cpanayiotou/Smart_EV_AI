FROM python:3.12-alpine
WORKDIR /app
COPY app.py pairing.py cloud_main.py /app/
RUN adduser -D -H connector
USER connector
EXPOSE 7080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7080/health', timeout=3)"
CMD ["python", "/app/cloud_main.py"]
