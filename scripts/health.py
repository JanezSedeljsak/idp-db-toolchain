from __future__ import annotations

from dataclasses import dataclass, field

from scripts import s3
from scripts.config import Config
from scripts.database import ping


@dataclass
class HealthCheck:
    name: str
    ok: bool
    detail: str | None = None


@dataclass
class HealthReport:
    ok: bool
    checks: list[HealthCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "checks": [
                {"name": check.name, "ok": check.ok, "detail": check.detail}
                for check in self.checks
            ],
        }


def liveness() -> HealthReport:
    return HealthReport(ok=True, checks=[HealthCheck(name="process", ok=True)])


def readiness(cfg: Config) -> HealthReport:
    checks: list[HealthCheck] = []
    for target in cfg.databases:
        name = f"database:{target.id}"
        try:
            ping(target.database_url)
            checks.append(HealthCheck(name=name, ok=True))
        except Exception as exc:
            checks.append(HealthCheck(name=name, ok=False, detail=str(exc)))
    try:
        s3.check_reachable(cfg)
        checks.append(HealthCheck(name="s3", ok=True, detail=cfg.s3_bucket))
    except Exception as exc:
        checks.append(HealthCheck(name="s3", ok=False, detail=str(exc)))
    ok = all(check.ok for check in checks)
    return HealthReport(ok=ok, checks=checks)


def full(cfg: Config) -> HealthReport:
    report = readiness(cfg)
    report.checks.insert(0, HealthCheck(name="process", ok=True))
    return report
