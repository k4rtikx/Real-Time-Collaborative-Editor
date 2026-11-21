FROM python:3.13-slim

# Security: run as non-root user
RUN groupadd --gid 1001 collabedit && \
    useradd --uid 1001 --gid 1001 --no-create-home collabedit

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Collect static files
RUN python manage.py collectstatic --no-input --settings=doc_editor.settings.production || true

# Change ownership
RUN chown -R collabedit:collabedit /app

USER collabedit

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1

CMD ["uvicorn", "doc_editor.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
