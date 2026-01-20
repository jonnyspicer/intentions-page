FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Pin setuptools to avoid compatibility issues with older packages
RUN pip install --upgrade pip && pip install "setuptools<58" wheel
COPY requirements/base.txt requirements/base.txt
COPY requirements/production.txt requirements/production.txt
# Use --no-build-isolation to use our pinned setuptools
RUN pip install --no-cache-dir --no-build-isolation -r requirements/production.txt
# Install missing dependencies and upgrade incompatible packages
RUN pip install --no-cache-dir crispy-bootstrap4 "djangorestframework>=3.14"

# Copy application code
COPY . .

# Create data directory for SQLite
RUN mkdir -p /app/data

# Collect static files
ENV DJANGO_SETTINGS_MODULE=config.settings.docker
RUN python manage.py collectstatic --noinput

# Create non-root user and set permissions
RUN useradd -m -u 1001 appuser && \
    chown -R appuser:appuser /app && \
    chmod 777 /app/data
USER appuser

EXPOSE 8000

# Start script: run migrations then start gunicorn
CMD python manage.py migrate --noinput && \
    gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
