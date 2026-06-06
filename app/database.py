import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# DATABASE_URL env var takes precedence. Falls back to /data (Render) or ./telemetry.db (local).
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or ("sqlite:////data/telemetry.db" if os.path.isdir("/data") else "sqlite:///./telemetry.db")
)

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
