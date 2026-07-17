.PHONY: venv install test test-infra pg-up pg-down run schema clean

VENV := .venv
PY := $(VENV)/bin/python
DSN := postgresql://postgres:comcmd@127.0.0.1:5433/comcmd

venv:
	python3 -m venv $(VENV)

install: venv
	$(PY) -m pip install -e ".[dev,durable]"

test:
	$(PY) -m pytest -q

# Runs the durable (Postgres + DBOS) tests too. Requires `make pg-up` first.
test-infra:
	COMCMD_TEST_DATABASE_URL=$(DSN) COMCMD_TEST_DBOS_URL=$(DSN) $(PY) -m pytest -q

pg-up:
	docker run -d --name comcmd-pg -e POSTGRES_PASSWORD=comcmd -e POSTGRES_DB=comcmd \
		-p 5433:5432 postgres:16-alpine

pg-down:
	docker rm -f comcmd-pg

run:
	$(PY) -m comcmd.cli run companies/auto-steam ship-title

# Durable run against Postgres+DBOS.
run-durable:
	COMCMD_DATABASE_URL=$(DSN) $(PY) -m comcmd.cli run companies/auto-steam ship-title --durable

schema:
	$(PY) -m comcmd.cli schema -o schemas/company.schema.json

clean:
	rm -rf $(VENV) .pytest_cache **/__pycache__ *.sqlite
