from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

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
    today = today or date.today()
    return subtract_months(today.replace(day=1), 2)


def retention_expiry_cutoff(today: date | None = None) -> date:
    today = today or date.today()
    return subtract_months(today.replace(day=1), 12)


def should_run_scheduled_retention(today: date | None = None) -> bool:
    return (today or date.today()).day == 1


@dataclass
class RetentionResult:
    collapsed: list[str]
    expired: list[str]

    @property
    def deleted(self) -> list[str]:
        return self.collapsed + self.expired


def _keys_in_month(cfg: Config, month_start: date) -> list[dict]:
    start, end = month_bounds(month_start)
    return [
        obj
        for obj in s3.list_backups(cfg)
        if (day := s3.backup_date_from_key(obj["Key"])) is not None and start <= day <= end
    ]


def apply_retention(cfg: Config, db_id: str, *, today: date | None = None) -> RetentionResult:
    db_cfg = cfg_for_db(cfg, db_id)
    collapsed: list[str] = []
    expired: list[str] = []

    target_month = retention_target_month(today)
    in_month = _keys_in_month(db_cfg, target_month)
    if len(in_month) > 1:
        in_month.sort(key=lambda o: o["LastModified"], reverse=True)
        for obj in in_month[1:]:
            s3.delete_object(cfg, obj["Key"])
            collapsed.append(obj["Key"])

    cutoff = retention_expiry_cutoff(today)
    for obj in s3.list_backups(db_cfg):
        day = s3.backup_date_from_key(obj["Key"])
        if day is not None and day < cutoff:
            s3.delete_object(cfg, obj["Key"])
            expired.append(obj["Key"])

    return RetentionResult(collapsed=collapsed, expired=expired)
