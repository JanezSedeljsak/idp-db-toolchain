from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from scripts import s3
from scripts.config import Config, cfg_for_db


def subtract_months(day: date, months: int) -> date:
    year = day.year
    month = day.month - months
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def month_bounds(month_start: date) -> tuple[date, date]:
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    return month_start, next_month - timedelta(days=1)


def retention_target_month(today: date | None = None) -> date:
    """Month processed on the 1st (two calendar months ago)."""
    today = today or date.today()
    return subtract_months(today.replace(day=1), 2)


def last_month_start(today: date | None = None) -> date:
    today = today or date.today()
    return subtract_months(today.replace(day=1), 1)


def current_month_start(today: date | None = None) -> date:
    return (today or date.today()).replace(day=1)


def retention_expiry_cutoff(today: date | None = None) -> date:
    today = today or date.today()
    return subtract_months(today.replace(day=1), 12)


def last_week_start(month_start: date) -> date:
    _, end = month_bounds(month_start)
    return max(month_start, end - timedelta(days=6))


def in_last_week(day: date, month_start: date) -> bool:
    _, end = month_bounds(month_start)
    return last_week_start(month_start) <= day <= end


def _backup_day(obj: dict[str, Any]) -> date | None:
    return s3.backup_date_from_key(obj["Key"])


def pick_monthly_keeper(objects: list[dict[str, Any]], month_start: date) -> dict[str, Any]:
    last_week = [
        obj
        for obj in objects
        if (day := _backup_day(obj)) is not None and in_last_week(day, month_start)
    ]
    pool = last_week if last_week else objects
    return max(pool, key=lambda obj: obj["LastModified"])


def pick_weekly_keepers(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_week: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for obj in objects:
        day = _backup_day(obj)
        if day is None:
            continue
        by_week[day.isocalendar()[:2]].append(obj)
    return [max(group, key=lambda obj: obj["LastModified"]) for group in by_week.values()]


def group_backups_by_month(objects: list[dict[str, Any]]) -> dict[date, list[dict[str, Any]]]:
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for obj in objects:
        day = _backup_day(obj)
        if day is None:
            continue
        grouped[day.replace(day=1)].append(obj)
    return grouped


@dataclass
class RetentionPlan:
    weekly_collapsed: list[str]
    monthly_collapsed: list[str]
    expired: list[str]

    @property
    def to_delete(self) -> list[str]:
        return self.weekly_collapsed + self.monthly_collapsed + self.expired


@dataclass
class RetentionResult:
    weekly_collapsed: list[str]
    monthly_collapsed: list[str]
    expired: list[str]

    @property
    def collapsed(self) -> list[str]:
        return self.weekly_collapsed + self.monthly_collapsed

    @property
    def deleted(self) -> list[str]:
        return self.collapsed + self.expired


def plan_retention(cfg: Config, *, today: date | None = None) -> RetentionPlan:
    today = today or date.today()
    current = current_month_start(today)
    last_month = last_month_start(today)
    cutoff = retention_expiry_cutoff(today)

    weekly_collapsed: list[str] = []
    monthly_collapsed: list[str] = []
    expired: list[str] = []

    by_month = group_backups_by_month(s3.list_backups(cfg))

    if last_month in by_month:
        keepers = {obj["Key"] for obj in pick_weekly_keepers(by_month[last_month])}
        for obj in by_month[last_month]:
            if obj["Key"] not in keepers:
                weekly_collapsed.append(obj["Key"])

    for month_start, month_objs in by_month.items():
        if month_start >= last_month:
            continue
        keeper = pick_monthly_keeper(month_objs, month_start)
        for obj in month_objs:
            if obj["Key"] != keeper["Key"]:
                monthly_collapsed.append(obj["Key"])

    for obj in s3.list_backups(cfg):
        day = _backup_day(obj)
        if day is not None and day < cutoff:
            expired.append(obj["Key"])

    _ = current  # current month: keep all daily backups untouched
    return RetentionPlan(
        weekly_collapsed=weekly_collapsed,
        monthly_collapsed=monthly_collapsed,
        expired=expired,
    )


def apply_retention(cfg: Config, db_id: str, *, today: date | None = None) -> RetentionResult:
    db_cfg = cfg_for_db(cfg, db_id)
    plan = plan_retention(db_cfg, today=today)
    for key in plan.to_delete:
        s3.delete_object(cfg, key)
    return RetentionResult(
        weekly_collapsed=plan.weekly_collapsed,
        monthly_collapsed=plan.monthly_collapsed,
        expired=plan.expired,
    )
