from __future__ import annotations

import base64
import json
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from scripts.models import TABLE_ORDER


def quote_ident(name: str) -> str:
    return f'"{name.replace(chr(34), chr(34) * 2)}"'


def format_sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, uuid.UUID):
        return f"'{value}'"
    if isinstance(value, datetime):
        return f"'{value.astimezone().isoformat()}'"
    if isinstance(value, (date, time)):
        return f"'{value.isoformat()}'"
    if isinstance(value, (dict, list)):
        return "'" + json.dumps(value).replace("'", "''") + "'"
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        return f"'\\x{value.hex()}'"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return "'" + str(value).replace("'", "''") + "'"


def list_tables(session: Session) -> list[str]:
    rows = session.execute(
        text(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        )
    ).fetchall()
    return [row[0] for row in rows]


def order_tables(tables: list[str]) -> list[str]:
    order = {name: index for index, name in enumerate(TABLE_ORDER)}
    return sorted(tables, key=lambda table: (order.get(table, 99), table))


def dump_table(session: Session, table: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    columns = [
        row[0]
        for row in session.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :table
                ORDER BY ordinal_position
                """
            ),
            {"table": table},
        ).fetchall()
    ]
    rows = session.execute(text(f"SELECT * FROM {quote_ident(table)} ORDER BY 1")).fetchall()
    return columns, [tuple(row) for row in rows]


def dump(session: Session) -> str:
    tables = order_tables(list_tables(session))
    parts = ["-- db-backupper SQL dump"]
    table_idents = [quote_ident(table) for table in tables]
    parts.append(f"TRUNCATE {', '.join(table_idents)} RESTART IDENTITY CASCADE;")

    for table in tables:
        columns, rows = dump_table(session, table)
        if not rows:
            continue
        parts.append(f"\n-- table: {table}")
        col_list = ", ".join(quote_ident(column) for column in columns)
        table_ident = quote_ident(table)
        for row in rows:
            vals = ", ".join(format_sql_value(value) for value in row)
            parts.append(f"INSERT INTO {table_ident} ({col_list}) VALUES ({vals});")

    return "\n".join(parts) + "\n"


def split_sql_statements(text_sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for line in text_sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
    if current:
        stmt = "\n".join(current).strip()
        if stmt:
            statements.append(stmt)
    return statements


def reset_sequences(session: Session) -> None:
    rows = session.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND column_default LIKE 'nextval%'
            """
        )
    ).fetchall()
    for table, column in rows:
        table_ident = quote_ident(table)
        column_ident = quote_ident(column)
        session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence(:table, :column), "
                f"COALESCE((SELECT MAX({column_ident}) FROM {table_ident}), 1), true)"
            ),
            {"table": table, "column": column},
        )


def restore(session: Session, dump_sql: str) -> None:
    with session.begin_nested():
        for index, stmt in enumerate(split_sql_statements(dump_sql), start=1):
            try:
                session.execute(text(stmt))
            except Exception as exc:
                raise RuntimeError(f"exec statement {index}: {exc}\n{stmt}") from exc
        reset_sequences(session)


def table_row_counts(session: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in list_tables(session):
        counts[table] = session.execute(
            text(f"SELECT COUNT(*) FROM {quote_ident(table)}")
        ).scalar_one()
    return counts


def compare_databases(source_url: str, target_url: str) -> list[str]:
    from scripts.database import session as db_session

    diffs: list[str] = []
    with db_session(source_url) as source, db_session(target_url) as target:
        source_tables = order_tables(list_tables(source))
        target_tables = order_tables(list_tables(target))
        if source_tables != target_tables:
            diffs.append(f"tables differ: {source_tables} vs {target_tables}")
            return diffs

        for table in source_tables:
            source_cols, source_rows = dump_table(source, table)
            target_cols, target_rows = dump_table(target, table)
            if source_cols != target_cols:
                diffs.append(f"{table}: column mismatch")
                continue
            if len(source_rows) != len(target_rows):
                diffs.append(f"{table}: row count {len(source_rows)} vs {len(target_rows)}")
                continue
            for index, (left, right) in enumerate(zip(source_rows, target_rows, strict=True)):
                if left != right:
                    diffs.append(f"{table}: row {index} differs")
                    break
    return diffs


def decode_bytea_literal(value: str) -> bytes:
    if value.startswith("\\x"):
        return bytes.fromhex(value[2:])
    return base64.b64decode(value)
