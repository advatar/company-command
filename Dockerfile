FROM python:3.12-slim

WORKDIR /app

# Install first for layer caching.
COPY pyproject.toml README.md ./
COPY comcmd ./comcmd
RUN pip install --no-cache-dir -e ".[server,durable]"

# Company packs (operator-controlled).
COPY companies ./companies

ENV COMCMD_COMPANIES_DIR=/app/companies \
    COMCMD_RP_ID=localhost \
    COMCMD_RP_ORIGIN=https://localhost

EXPOSE 8080

# In-process by default; set COMCMD_DATABASE_URL to go durable (Postgres + DBOS).
CMD ["python", "-m", "comcmd.cli", "serve", "--host", "0.0.0.0", "--port", "8080"]
