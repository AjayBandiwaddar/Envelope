FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps needed to build psycopg2 and friends.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Development entrypoint. A production image should use gunicorn/uvicorn
# instead of the Django development server; that is deferred until the
# "Deployment Architecture" work in ARCHITECTURE.md §24 is implemented.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
