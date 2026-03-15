SHELL := /bin/bash
COMPOSE := docker compose

.PHONY: up down logs migrate seed test smoke

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down --remove-orphans

logs:
	$(COMPOSE) logs -f --tail=200

migrate:
	$(COMPOSE) exec identity-service alembic upgrade head
	$(COMPOSE) exec tracks-service alembic upgrade head
	$(COMPOSE) exec upload-service alembic upgrade head
	$(COMPOSE) exec social-service alembic upgrade head

seed:
	$(COMPOSE) exec tracks-service python -m app.seed

test:
	$(COMPOSE) exec api-gateway sh -lc "PYTHONPATH=/app pytest -q"
	$(COMPOSE) exec identity-service sh -lc "PYTHONPATH=/app pytest -q"
	$(COMPOSE) exec tracks-service sh -lc "PYTHONPATH=/app pytest -q"
	$(COMPOSE) exec upload-service sh -lc "PYTHONPATH=/app pytest -q"
	$(COMPOSE) exec social-service sh -lc "PYTHONPATH=/app pytest -q"
	$(COMPOSE) exec processing-worker sh -lc "PYTHONPATH=/app pytest -q"

smoke:
	./scripts/backend_smoke.sh
