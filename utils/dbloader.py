from datetime import datetime

import pandas as pd
from sqlalchemy import Connection, Engine, create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from config import Settings, get_conf
from models import Base
from utils.logging import logger


def get_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_conf()
    engine_kwargs = {"future": True}
    if settings.database_backend.lower() == "sqlserver":
        engine_kwargs["fast_executemany"] = True
    engine = create_engine(settings.sqlalchemy_url(), **engine_kwargs)
    if settings.database_backend.lower() == "sqlite":
        return engine.execution_options(schema_translate_map={"STG.Marketing": None})
    return engine


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def get_session_factory(engine: Engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def open_session(connection: Engine | Connection | Session | None = None) -> tuple[Session, bool]:
    if isinstance(connection, Session):
        return connection, False
    if isinstance(connection, Connection):
        return Session(bind=connection, expire_on_commit=False), True
    engine = connection or get_engine()
    return get_session_factory(engine)(), True


def resolve_token(session: Session | None = None, settings: Settings | None = None) -> str:
    settings = settings or get_conf()
    source = settings.token_source.lower()
    if source in {"env", "auto"} and settings.user_token:
        return settings.user_token
    if source in {"db", "auto"} and session and settings.token_query:
        token = session.execute(text(settings.token_query)).scalar_one_or_none()
        if token:
            return str(token)
    raise ValueError("No Meta access token found in METAETL_USER_TOKEN or the configured token query")


def read_ids(session: Session, model: type[Base], column: str) -> list[str]:
    values = session.execute(select(getattr(model, column)).distinct()).scalars().all()
    return [str(value) for value in values if value is not None]


def upsert(
    df: pd.DataFrame,
    model: type[Base],
    key_columns: list[str],
    session: Session | None = None,
    engine: Engine | None = None,
    commit: bool = True,
) -> int:
    if df.empty:
        logger.info("No rows to load into %s", model.__tablename__)
        return 0
    if session is None:
        if engine is None:
            engine = get_engine()
        session = get_session_factory(engine)()
        owns_session = True
    else:
        owns_session = False

    try:
        records = []
        for raw_record in df.to_dict(orient="records"):
            record = {}
            for column, value in raw_record.items():
                if value is None or value is pd.NaT:
                    record[column] = None
                elif pd.api.types.is_scalar(value) and pd.isna(value):
                    record[column] = None
                else:
                    record[column] = value
            records.append(record)
        for record in records:
            record.setdefault("LoadDate", datetime.now())
            filters = [getattr(model, key) == record[key] for key in key_columns]
            existing = session.execute(select(model).where(*filters)).scalar_one_or_none()
            if existing is None:
                session.add(model(**record))
            else:
                for column, value in record.items():
                    setattr(existing, column, value)
        if commit:
            session.commit()
        logger.info("Upserted %d rows into %s", len(records), model.__tablename__)
        return len(records)
    except Exception:
        session.rollback()
        logger.exception("Failed loading %s", model.__tablename__)
        raise
    finally:
        if owns_session:
            session.close()
