import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# DATABASE_URL env var takes precedence. Falls back to /data (Render) or ./telemetry.db (local).
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or ("sqlite:////data/telemetry.db" if os.path.isdir("/data") else "sqlite:///./telemetry.db")
)

# Render/Heroku-style URLs use the legacy "postgres://" scheme; SQLAlchemy 2.x
# only accepts "postgresql://".
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

_is_sqlite = DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    # check_same_thread is a SQLite-only flag (FastAPI threads share the engine).
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Postgres (or other server DBs): recycle broken connections transparently
    # and keep a small steady pool — managed Postgres closes idle connections.
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=300,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
