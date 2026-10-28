FROM python:3.12-slim AS upstream
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN git init /source && cd /source && git remote add origin https://github.com/John6810/myaudi-api.git && git fetch --depth 1 origin afd531e830971f042f1c0319d3614442c05009d4 && git checkout --detach FETCH_HEAD && test "$(git rev-parse HEAD)" = afd531e830971f042f1c0319d3614442c05009d4

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 1000 --create-home bridge && mkdir /data && chown bridge:bridge /data
COPY --from=upstream /source/audi_connect ./audi_connect
COPY --from=upstream /source/LICENSE ./UPSTREAM-LICENSE
COPY bridge.py .
USER bridge
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "bridge.py"]
CMD ["serve"]
