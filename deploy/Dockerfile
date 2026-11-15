FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY requirements.txt requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock.txt && useradd --create-home --uid 10001 menclave && mkdir /data && chown menclave:menclave /data
COPY --chown=menclave:menclave . .
USER menclave
EXPOSE 8000
CMD ["uvicorn", "server.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--log-level", "warning"]
