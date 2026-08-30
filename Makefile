.PHONY: install migrate seed-demo cleanup-runtime closed-test live-smoke api web

install:
	python3 -m pip install -e '.[dev,openrouter,media]'

migrate:
	python3 -m apps.api.app.db.migrate

seed-demo:
	APP_MODE=closed_test AI_PROVIDER=fake python3 scripts/seed_demo.py

cleanup-runtime:
	python3 scripts/cleanup_runtime.py

closed-test:
	APP_MODE=closed_test AI_PROVIDER=fake python3 scripts/closed_test.py

live-smoke:
	APP_MODE=live_test python3 scripts/live_smoke_test.py

api:
	uvicorn apps.api.app.main:app --host $${API_HOST:-0.0.0.0} --port $${API_PORT:-8000}

web:
	cd apps/web && npm run dev
