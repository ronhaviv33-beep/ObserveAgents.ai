import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# On Render the persistent disk is mounted at /data (DATA_DIR=/data).
# Locally (no DATA_DIR set) the DB sits in the project root.
_data_dir = os.getenv("DATA_DIR", ".")
DATABASE_URL = f"sqlite:///{_data_dir}/telemetry.db"

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
