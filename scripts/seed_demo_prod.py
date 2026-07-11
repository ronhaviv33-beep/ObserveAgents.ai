"""One-off: seed realistic demo data into an org using the app's own populate_demo_org().

Run with the production DATABASE_URL in the environment. Idempotent.
"""
import sys

from app.database import SessionLocal
from app.routes.admin import populate_demo_org

ORG_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1


def main() -> None:
    db = SessionLocal()
    try:
        result = populate_demo_org(db, ORG_ID)
        print("SEED_RESULT:", result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
