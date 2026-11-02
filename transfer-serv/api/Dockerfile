FROM python:3.12-slim-bookworm

WORKDIR /app

COPY api/requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt && pip check

COPY api/app ./app

RUN python -m compileall -q app

RUN useradd --uid 10001 --create-home transfer \
    && mkdir -p /data/database /data/uploads \
    && chown -R transfer:transfer /data

USER transfer

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--workers", "2", "--no-access-log"]