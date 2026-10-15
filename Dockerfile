FROM metacubex/mihomo:v1.19.32 AS core
FROM python:3.12-slim-bookworm
COPY --from=core /mihomo /usr/local/bin/mihomo
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker.py test_worker.py panel.py panel.html ./
COPY assets/icon-c-crystal.png ./assets/icon-c-crystal.png
ENV PYTHONUNBUFFERED=1
CMD ["python", "worker.py"]
