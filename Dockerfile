FROM python:3.12-slim

WORKDIR /app

# Install first for layer caching.
COPY pyproject.toml README.md ./
COPY acme ./acme
RUN pip install --no-cache-dir -e ".[server,durable]"

# Company packs (operator-controlled).
COPY companies ./companies

ENV ACME_COMPANIES_DIR=/app/companies \
    ACME_RP_ID=localhost \
    ACME_RP_ORIGIN=https://localhost

EXPOSE 8080

# In-process by default; set ACME_DATABASE_URL to go durable (Postgres + DBOS).
CMD ["python", "-m", "acme.cli", "serve", "--host", "0.0.0.0", "--port", "8080"]
