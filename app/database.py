import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# On Render the persistent disk is mounted at /data.
# Locally falls back to ./telemetry.db.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/telemetry.db") \
    if os.path.isdir("/data") else "sqlite:///./telemetry.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
