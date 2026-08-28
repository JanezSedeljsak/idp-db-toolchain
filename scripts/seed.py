from __future__ import annotations

import random
import time

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from scripts.models import AuditLog, Order, User

COUNTS = {"users": 50, "orders": 200, "audit": 100}


def run(session: Session, job: str | None = None, count: int = 50) -> None:
    if job:
        _job(session, job, count)
        return
    _job(session, "users", COUNTS["users"])
    _job(session, "orders", COUNTS["orders"])
    _job(session, "audit", COUNTS["audit"])


def _job(session: Session, job: str, count: int) -> None:
    rng = random.Random(time.time())
    if job == "users":
        for i in range(count):
            email = f"user{int(time.time())}_{i}@example.com"
            name = f"User {rng.randint(0, 9999)}"
            session.execute(
                insert(User)
                .values(email=email, name=name)
                .on_conflict_do_nothing(index_elements=["email"])
            )
    elif job == "orders":
        from sqlalchemy import select

        user_ids = list(session.scalars(select(User.id).limit(100)))
        if not user_ids:
            raise RuntimeError("seed users first")
        for _ in range(count):
            session.add(
                Order(
                    user_id=rng.choice(user_ids),
                    amount_cents=rng.randint(100, 50000),
                    status=rng.choice(["pending", "paid", "shipped", "cancelled"]),
                )
            )
    elif job == "audit":
        for _ in range(count):
            verb = rng.choice(["created", "updated", "backup"])
            session.add(
                AuditLog(
                    source=rng.choice(["api", "worker", "scheduler", "cli"]),
                    message=f"{verb} #{rng.randint(0, 9999)}",
                )
            )
    else:
        raise ValueError(f"unknown job: {job}")
