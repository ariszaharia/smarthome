import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://aris:aris@db:5432/smarthome"

engine = create_async_engine(
    DATABASE_URL,
    echo = True
    )

async_session = sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession
)