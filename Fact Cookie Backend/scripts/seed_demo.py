"""Seed default plans and a demo user/API key for local development."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.models import User
from app.db.session import engine, session_factory
from app.services import api_key_service, auth_service, plan_service


async def main() -> None:
    async with session_factory() as db:
        await plan_service.seed_plans(db)

        email = "demo@factcookie.local"
        user = await auth_service.get_user_by_email(db, email)
        if user is None:
            user = await auth_service.register_user(db, email, "demo-password-123", "Demo User")
            print(f"Created demo user: {email}")
        else:
            print(f"Demo user already exists: {email}")

        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        existing = await api_key_service.list_api_keys(db, str(user.id))
        if existing:
            print(f"Demo API key already exists: {existing[0].prefix}...")
        else:
            _, full_key = await api_key_service.create_api_key(db, str(user.id), "demo")
            print("Demo API key (shown once):")
            print(full_key)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
