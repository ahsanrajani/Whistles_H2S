# Test-tier entrypoints. Thin delegates to the npm scripts so
# there is one implementation. Run from the repo root.
#
#   make check-unit MODULE=tests.test_scam   # T0 — one module, < 10s
#   make check-api                            # T1 — backend suite
#   make check-web                            # T1 — tsc + eslint + next build
#   make check-all                            # T2 — everything (phase gate only)
#
# npm equivalents (identical): npm run check:unit -- tests.test_scam,
# npm run check:api, npm run check:web, npm run check:all.

.PHONY: check-unit check-api check-web check-all check

check-unit:
	cd apps/api && python -m unittest -q $(MODULE)

check-api:
	npm run check:api

check-web:
	npm run check:web

check-all:
	npm run check:all

check: check-all
