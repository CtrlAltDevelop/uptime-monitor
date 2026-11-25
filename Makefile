.DEFAULT_GOAL := help
DJ := DEBUG=1 uv run python manage.py
PROD := docker compose -f compose.yaml -f compose.production.yaml

.PHONY: help install env migrate superuser seed run worker check-once test check static \
        build up down logs docker-superuser docker-seed \
        seed-realistic demo-site prod-env prod-up prod-down prod-logs prod-ps prod-superuser prod-seed

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- local development (uv) ----
install: ## Install dependencies with uv
	uv sync

migrate: ## Apply database migrations
	$(DJ) migrate

superuser: ## Create an admin user
	$(DJ) createsuperuser

seed: ## Create 50 demo services that monitor public hosts
	$(DJ) seed_demo

run: ## Run the web server on http://localhost:8000
	$(DJ) runserver

worker: ## Run the background health-check worker
	$(DJ) run_checks

seed-realistic: ## Demo services + 30 days of realistic history (replaces results)
	$(DJ) seed_realistic

demo-site: ## Rebuild the static live demo in docs/demo/ for GitHub Pages
	./scripts/build_demo.sh

check-once: ## Check every active service once and exit
	$(DJ) run_checks --once

test: ## Run the test suite
	$(DJ) test

check: ## Django system check + verify no migrations are missing
	$(DJ) check
	$(DJ) makemigrations --check --dry-run

static: ## Collect static files into ./staticfiles
	$(DJ) collectstatic --noinput

# ---- docker compose ----
.env:
	@python3 -c "import secrets, pathlib; pathlib.Path('.env').write_text(pathlib.Path('.env.example').read_text().replace('change-me', secrets.token_urlsafe(50)))"
	@echo "Created .env with a generated SECRET_KEY"

env: .env ## Create .env from .env.example with a generated SECRET_KEY

build: .env ## Build the docker image
	docker compose build

up: .env ## Start web + worker in the background
	docker compose up -d --build
	@echo "Status page: http://localhost:$${PORT:-8000}/   Admin: http://localhost:$${PORT:-8000}/admin/"

down: ## Stop the containers (data volume is kept)
	docker compose down

logs: ## Follow container logs
	docker compose logs -f

docker-superuser: ## Create an admin user inside the running container
	docker compose exec web python manage.py createsuperuser

docker-seed: ## Seed the 50 demo services inside the running container
	docker compose exec web python manage.py seed_demo

# ---- production-like stack: PostgreSQL + Caddy HTTPS (see compose.production.yaml) ----
prod-env: ## Create .env for the production stack with random secrets
	@if [ -f .env ]; then echo ".env already exists, leaving it untouched"; else \
	python3 -c "import re, secrets, pathlib; t = pathlib.Path('.env.production.example').read_text(); pathlib.Path('.env').write_text(re.sub('change-me', lambda m: secrets.token_urlsafe(40), t))" \
	&& echo "Created .env with random SECRET_KEY and POSTGRES_PASSWORD"; fi

prod-up: prod-env ## Build and start db + web + worker + caddy
	$(PROD) up -d --build

prod-down: ## Stop the production stack (volumes are kept)
	$(PROD) down

prod-logs: ## Follow production logs
	$(PROD) logs -f

prod-ps: ## Show production containers
	$(PROD) ps

prod-superuser: ## Create an admin user in the production stack
	$(PROD) exec web python manage.py createsuperuser

prod-seed: ## Seed demo services with 30 days of realistic history
	$(PROD) exec web python manage.py seed_realistic
