.PHONY: bootstrap base up up-dev down build logs ps chain solve clean splunk-wait reset

# generate the lab's throwaway ssh key + leaked backup (idempotent)
bootstrap:
	bash bootstrap.sh

# build the shared python base image (all app services FROM it)
base: bootstrap
	docker build -t atb-base:latest -f services/_base/Dockerfile .

build: base
	docker compose build

up: base
	docker compose up -d
	@echo "Players reach only the perimeter (shop, app, LMS, supplier, OWA, Splunk):"
	@docker compose ps --format '  {{.Name}}\t{{.Ports}}' | grep -- '->' || true

# organizer mode: ALSO expose the internal services on host ports (see docker-compose.dev.yml)
up-dev: base
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
	@echo "DEV: internal services also exposed (grafana 3000, zabbix 8084, harbor 8085, ...)."

down:
	docker compose down

reset:
	docker compose down -v
	rm -f logs/*.json

ps:
	docker compose ps

logs:
	docker compose logs -f --tail=50

# run the whole attack chain end-to-end (organizer reference solve)
chain: solve
solve:
	python3 attack/solve.py

clean: down
	docker image rm atb-base:latest 2>/dev/null || true
