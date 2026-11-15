FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 menclave && mkdir /data && chown menclave:menclave /data
COPY --chown=menclave:menclave . .
USER menclave
EXPOSE 8000
CMD ["gunicorn", "--config", "gunicorn.conf.py", "server.wsgi:app"]
