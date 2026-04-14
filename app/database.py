from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./research.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}


def _ensure_postgres_db():
    """Crea research_lab_db si no existe (solo para PostgreSQL)."""
    if not DATABASE_URL.startswith("postgresql"):
        return
    # Conectar a la DB 'postgres' para poder hacer CREATE DATABASE
    admin_url = DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    tmp = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with tmp.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'research_lab_db'")
        ).fetchone()
        if not exists:
            conn.execute(text("CREATE DATABASE research_lab_db"))
    tmp.dispose()


_ensure_postgres_db()

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
