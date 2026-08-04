from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.settings import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

engine = create_engine(
    str(settings.database_url),
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
