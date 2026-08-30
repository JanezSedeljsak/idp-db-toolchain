from __future__ import annotations

import random
import time

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from scripts.models import AuditLog, Order, User

COUNTS = {"users": 50, "orders": 200, "audit": 100}
INTEGRATION_COUNTS = {"users": 5, "orders": 10, "audit": 5}
INTEGRATION_RNG_SEED = 42


def run(
    session: Session,
    job: str | None = None,
    count: int = 50,
    *,
    counts: dict[str, int] | None = None,
    rng_seed: int | None = None,
    prefix: str = "default",
) -> None:
    profile = counts or COUNTS
    rng = random.Random(rng_seed if rng_seed is not None else time.time())
    if job:
        _job(session, job, count, rng=rng, prefix=prefix)
        return
    _job(session, "users", profile["users"], rng=rng, prefix=prefix)
    _job(session, "orders", profile["orders"], rng=rng, prefix=prefix)
    _job(session, "audit", profile["audit"], rng=rng, prefix=prefix)


def _job(session: Session, job: str, count: int, *, rng: random.Random, prefix: str) -> None:
    if job == "users":
        for i in range(count):
            email = f"{prefix}_user_{i}@example.com"
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


def seed_config(cfg, *, profile: str = "default") -> None:
    from scripts.config import cfg_for_db
    from scripts.database import session

    if profile == "integration":
        counts = INTEGRATION_COUNTS
        rng_seed = INTEGRATION_RNG_SEED
    else:
        counts = COUNTS
        rng_seed = None

    for target in cfg.databases:
        with session(target.database_url) as s:
            run(s, counts=counts, rng_seed=rng_seed, prefix=target.id)
