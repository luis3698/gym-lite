"""Acceso a SQLite con SQL directo.

Todas las consultas del proyecto pasan por aquí y usan siempre parámetros ligados
(`?`), nunca interpolación de cadenas: es lo que evita la inyección de SQL.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

import click
from flask import Flask, current_app, g

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_db() -> sqlite3.Connection:
    """Conexión de la petición actual, creada la primera vez que se pide."""
    if "db" not in g:
        conn = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
            # Espera si otra conexión tiene la base bloqueada, en vez de fallar al
            # instante con "database is locked".
            timeout=10.0,
        )
        # Filas accesibles por nombre de columna (row["first_name"]) y utilizables
        # directamente desde las plantillas.
        conn.row_factory = sqlite3.Row
        # SQLite no aplica las claves foráneas salvo que se active en cada conexión.
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL permite leer mientras se escribe: la app abre varias pestañas y sin esto
        # una escritura larga bloquea las lecturas.
        conn.execute("PRAGMA journal_mode = WAL")
        g.db = conn
    return g.db


def close_db(exc: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


# --- Atajos de consulta ------------------------------------------------------


def query_all(sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()


def query_one(sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    return get_db().execute(sql, params).fetchone()


def query_value(sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
    """Primera columna de la primera fila (para COUNT, SUM, MAX…)."""
    row = query_one(sql, params)
    if row is None or row[0] is None:
        return default
    return row[0]


def execute(sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
    """Ejecuta una sentencia de escritura y confirma la transacción."""
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur


def executemany(sql: str, seq_params: Iterable[Sequence[Any]]) -> None:
    db = get_db()
    db.executemany(sql, seq_params)
    db.commit()


def insert(sql: str, params: Sequence[Any] = ()) -> int:
    """Ejecuta un INSERT y devuelve el id generado."""
    return int(execute(sql, params).lastrowid or 0)


class transaction:
    """Bloque de escrituras todo-o-nada.

        with transaction() as db:
            db.execute(...)
            db.execute(...)

    Al salir sin excepción hace COMMIT; si algo falla, ROLLBACK. Sirve para las
    operaciones que tocan varias tablas (registrar una venta y descontar stock,
    guardar todas las tarifas de golpe) y que a medias dejarían datos incoherentes.
    """

    def __enter__(self) -> sqlite3.Connection:
        self.db = get_db()
        # BEGIN IMMEDIATE toma el bloqueo de escritura ya mismo, en vez de esperar a
        # la primera escritura. Así dos ventas simultáneas se serializan desde el
        # principio y ninguna puede leer un stock que la otra está a punto de cambiar.
        self.db.execute("BEGIN IMMEDIATE")
        return self.db

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self.db.commit()
        else:
            self.db.rollback()
        return False  # nunca silencia la excepción


# --- Inicialización ----------------------------------------------------------


def init_db(app: Flask) -> bool:
    """Crea el esquema si falta. Devuelve True si la base estaba vacía."""
    db_path = Path(app.config["DATABASE"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not db_path.exists() or db_path.stat().st_size == 0

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    return is_new


@click.command("init-db")
def init_db_command() -> None:
    """Reaplica el esquema (no borra datos existentes)."""
    init_db(current_app)
    click.echo("Esquema aplicado.")


@click.command("seed")
def seed_command() -> None:
    """Carga los datos iniciales (idempotente)."""
    from .seed import seed_database

    created = seed_database(current_app)
    for line in created:
        click.echo(line)
    click.echo("Datos iniciales listos.")


@click.command("reset-db")
@click.confirmation_option(prompt="Esto BORRA todos los datos. ¿Continuar?")
def reset_db_command() -> None:
    """Borra la base de datos y la vuelve a crear con los datos iniciales."""
    from .seed import seed_database

    db_path = Path(current_app.config["DATABASE"])
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()
    init_db(current_app)
    for line in seed_database(current_app):
        click.echo(line)
    click.echo("Base de datos reiniciada.")


def register(app: Flask) -> None:
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_command)
    app.cli.add_command(reset_db_command)
