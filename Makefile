# Atajos del proyecto D'CASA. `make help` para ver todo.
PYTHON ?= .venv/bin/python
ODOO := $(PYTHON) vendor/odoo/odoo-bin --addons-path=vendor/odoo/addons,vendor/odoo/odoo/addons,addons
DB ?= dcasa
MODULES ?= dcasa_base,dcasa_invoice,dcasa_referral,website_dcasa

.PHONY: help setup test lint run init update up down edge-test

help: ## Muestra esta ayuda
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup: ## Clona Odoo (submódulo) y crea el entorno Python
	git submodule update --init --depth 1
	python3 -m venv .venv
	.venv/bin/pip install -r vendor/odoo/requirements.txt ruff

test: ## Tests de los módulos de D'CASA (necesita PostgreSQL)
	PYTHON=$(PYTHON) scripts/test.sh

lint: ## Ruff sobre los módulos propios
	.venv/bin/ruff check addons

init: ## Crea la base $(DB) con los módulos y español
	$(ODOO) -d $(DB) -i $(MODULES) --load-language=es_419 --stop-after-init

update: ## Actualiza los módulos de D'CASA en la base $(DB)
	$(ODOO) -d $(DB) -u $(MODULES) --stop-after-init

run: ## Levanta Odoo en http://localhost:8069 con recarga de vistas
	$(ODOO) -d $(DB) --dev=xml

up: ## Todo en Docker (PostgreSQL + Odoo)
	docker compose up --build

down: ## Apaga Docker
	docker compose down

edge-test: ## Tests y typecheck del Worker de Cloudflare
	cd edge && npm ci && npm run typecheck && npm test
