"""Check RLS status on all public tables and verify backend role can read."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings


async def main() -> None:
    # Convert SQLAlchemy async URL to a plain postgresql:// DSN for asyncpg.
    url = settings.database_url
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql://" + url[len("postgresql+asyncpg://"):]
    url = url.split("?")[0]  # asyncpg ssl handled below

    conn = await asyncpg.connect(url, ssl="require", timeout=15)
    try:
        rows = await conn.fetch(
            """
            select c.relname, c.relrowsecurity, c.relforcerowsecurity
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r'
            order by c.relname
            """
        )
        print(f"{'table':30} {'rls':5} {'force':5}")
        print("-" * 45)
        for r in rows:
            print(f"{r['relname']:30} {str(r['relrowsecurity']):5} {str(r['relforcerowsecurity']):5}")

        for table in ("users", "plans", "verifications"):
            try:
                count = await conn.fetchval(f"select count(*) from {table}")
                print(f"{table}: readable, rows={count}")
            except Exception as exc:
                print(f"{table}: READ FAILED -> {exc}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
