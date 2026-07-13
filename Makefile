.PHONY: verify test

verify:
	@echo "=== Running isolation + structural harnesses ==="
	python tests/test_mgmt_isolation.py
	python tests/test_w1_alerts.py
	python tests/test_teams.py
	python tests/test_guardmode_recheck.py
	python tests/test_proxy_team_register.py
	python tests/test_team_scope.py
	@echo "=== All harnesses passed ==="

# Full test sweep. Each test file bootstraps its own sqlite DB at import time,
# so pytest must run them one file per process (a single combined run collides).
# Script-style harnesses (incl. the verify set) run via `python` directly.
SCRIPT_TESTS := test_mgmt_isolation test_w1_alerts test_teams test_guardmode_recheck \
                test_proxy_team_register test_team_scope test_credential_save_errors \
                test_provider_not_configured test_slowapi_response_compat test_startup_secret_check

test:
	@echo "=== Running full backend test sweep (per-file) ==="
	@set -e; for f in tests/test_*.py; do \
		base=$$(basename $$f .py); \
		if echo "$(SCRIPT_TESTS)" | grep -qw "$$base"; then \
			echo "-- $$base (script)"; python $$f >/dev/null; \
		else \
			echo "-- $$base (pytest)"; python -m pytest $$f -q --no-header -p no:cacheprovider >/dev/null; \
		fi; \
	done
	@echo "=== Running SDK tests ==="
	python -m pytest sdk/python/tests -q --no-header -p no:cacheprovider
	@echo "=== Full test sweep passed ==="
