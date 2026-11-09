"""Database connection (SQLite file by default)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def add_missing_columns() -> list[str]:
    """Tiny 'migration': when a new version of PayDesk adds a column to an existing table,
    add it to the database automatically - so you don't have to delete the database."""
    from sqlalchemy import inspect, text

    added = []
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                default = ""
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    value = column.default.arg
                    default = f" DEFAULT {int(value) if isinstance(value, bool) else repr(value)}"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{default}'))
                added.append(f"{table.name}.{column.name}")
    return added
