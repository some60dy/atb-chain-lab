.PHONY: bootstrap base up down build logs ps chain clean splunk-wait reset

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
	@echo "Splunk:   http://localhost:8000  (admin / changeme)"
	@echo "Shop:     http://localhost:8080   Supplier: http://localhost:8083"

down:
	docker compose down

reset:
	docker compose down -v
	rm -f logs/*.json

ps:
	docker compose ps

logs:
	docker compose logs -f --tail=50

# run the whole attack chain end-to-end
chain:
	bash attack/run_chain.sh

clean: down
	docker image rm atb-base:latest 2>/dev/null || true
