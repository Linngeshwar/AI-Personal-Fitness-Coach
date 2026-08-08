import os
from contextlib import asynccontextmanager

import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global pool
    pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=2, max_size=10)


async def close_pool() -> None:
    global pool
    if pool is not None:
        await pool.close()
        pool = None


@asynccontextmanager
async def get_conn():
    async with pool.acquire() as conn:
        yield conn
