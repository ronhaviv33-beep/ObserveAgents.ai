#!/usr/bin/env bash
cd /vercel/share/v0-project
export APP_ENV=demo
export DEMO_MODE=true
export JWT_SECRET=dev-super-secret-key-for-local-preview-only-1234567890
export SECRET_KEY=devsecret
export CREDENTIAL_ENCRYPTION_KEY=hzC2cX8Tzx2w4DRxs6NgAEZQnFllgF0Ha8Fdtp_2AWw=
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning
