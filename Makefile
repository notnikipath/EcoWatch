.PHONY: up down lint test compose
up:
	docker compose up --build -d
down:
	docker compose down
lint:
	python -m ruff check .
test:
	python -m pytest -q
compose:
	docker compose config
