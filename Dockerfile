# Backend image: FastAPI app served by Uvicorn.
#   docker build -t professor-io-backend .
#   docker run -p 8000:8000 --env-file .env professor-io-backend
FROM python:3.12-slim

# Don't write .pyc files; print logs immediately instead of buffering them.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Keep the SQLite file in /app/data so it can live on a Docker volume
    # (otherwise it is lost whenever the container is recreated).
    DATABASE_URL=sqlite:////app/data/professor_io.db

WORKDIR /app

# Install dependencies first: this layer is cached and only rebuilt
# when requirements.txt changes, which makes rebuilds much faster.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code (see .dockerignore for what is left out).
COPY app ./app
COPY scripts ./scripts

# Run as a normal user instead of root, for safety.
RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data
USER appuser

EXPOSE 8000

# Lets Docker (and hosts) know if the app stops responding. Uses Python
# because the slim image has no curl.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# No --reload here: that is only for development.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
