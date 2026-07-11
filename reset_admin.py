"""
Ensure the default admin user exists and reset its password.

The new password must be supplied explicitly — this script no longer ships a
hardcoded default so it cannot silently set a well-known password on a live
deployment.

Local:  ADMIN_RESET_PASSWORD='<strong-pw>' python reset_admin.py
        (or)  python reset_admin.py '<strong-pw>'
Render: run via the Shell tab on the ai-asset-backend (or ai-asset-app) service,
        passing the password the same way.
"""
import os
import sys
from passlib.context import CryptContext

EMAIL = "admin@ai-asset-mgmt.local"

NEW_PASSWORD = os.environ.get("ADMIN_RESET_PASSWORD") or (sys.argv[1] if len(sys.argv) > 1 else "")
if not NEW_PASSWORD:
    print(
        "ERROR: no password supplied.\n"
        "  Usage: ADMIN_RESET_PASSWORD='<strong-pw>' python reset_admin.py\n"
        "     or: python reset_admin.py '<strong-pw>'",
    )
    sys.exit(1)

# Match the same DB-path resolution as app/database.py
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url.startswith("sqlite:///"):
    DB = _db_url.replace("sqlite:///", "")
elif _db_url:
    DB = _db_url
elif os.path.isdir("/data"):          # Render persistent-disk mount
    DB = "/data/telemetry.db"
else:
    DB = "telemetry.db"               # local dev fallback

pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
hashed = pwd.hash(NEW_PASSWORD)

try:
    import sqlite3
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Try to update first
    cur.execute(
        "UPDATE users SET hashed_password=?, is_active=1 WHERE email=?",
        (hashed, EMAIL),
    )
    conn.commit()

    if cur.rowcount:
        print(f"Password reset.  Login with:  {EMAIL}  /  (the password you supplied)")
    else:
        # User doesn't exist — look up the platform org and insert
        cur.execute("SELECT id FROM organizations WHERE is_internal=1 LIMIT 1")
        row = cur.fetchone()
        if not row:
            print("ERROR: platform org not found. Run the app once so migrations create it.")
            sys.exit(1)
        org_id = row[0]
        cur.execute(
            """INSERT INTO users (email, name, hashed_password, role, team, organization_id, is_active)
               VALUES (?, ?, ?, 'admin', 'platform', ?, 1)""",
            (EMAIL, "Admin", hashed, org_id),
        )
        conn.commit()
        print(f"Admin user created.  Login with:  {EMAIL}  /  (the password you supplied)")

    conn.close()
except FileNotFoundError:
    print(f"ERROR: database not found at {DB}.")
    sys.exit(1)
