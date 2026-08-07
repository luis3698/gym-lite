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


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Ajusta bases creadas con una versión anterior del esquema.

    `CREATE TABLE IF NOT EXISTS` cubre las tablas nuevas, pero no las columnas nuevas
    de una tabla que ya existe ni los cambios de nombre. Cada paso comprueba primero
    si hace falta, así que se puede ejecutar en cada arranque sin efectos.

    No se usa una tabla de versiones a propósito: comprobar el estado real de las
    columnas funciona igual de bien aquí y no se rompe si alguien restaura una copia
    de seguridad antigua encima.
    """
    applied: list[str] = []

    # `months` solo valía para las mensualidades. Ahora cualquier duración admite
    # cantidad (3 días, 2 semanas…), así que el nombre pasa a ser `quantity`.
    membership_cols = _columns(conn, "memberships")
    if "months" in membership_cols and "quantity" not in membership_cols:
        conn.execute("ALTER TABLE memberships RENAME COLUMN months TO quantity")
        applied.append("memberships.months -> quantity")

    # Datos opcionales de gimnasio en la ficha del cliente.
    client_cols = _columns(conn, "clients")
    for column, ddl in (
        ("blood_type", "blood_type TEXT"),
        ("height_cm", "height_cm REAL"),
        ("weight_kg", "weight_kg REAL"),
        ("goal", "goal TEXT"),
        ("activity_level", "activity_level TEXT"),
        ("medical_conditions", "medical_conditions TEXT"),
        ("allergies", "allergies TEXT"),
        ("health_insurance", "health_insurance TEXT"),
        ("notes", "notes TEXT"),
    ):
        if column not in client_cols:
            conn.execute(f"ALTER TABLE clients ADD COLUMN {ddl}")
            applied.append(f"clients.{column}")

    conn.commit()
    return applied


def init_db(app: Flask) -> bool:
    """Crea el esquema si falta y migra el existente. True si la base estaba vacía."""
    db_path = Path(app.config["DATABASE"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not db_path.exists() or db_path.stat().st_size == 0

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
        for change in migrate(conn):
            print(f"[GymManager Lite] Base de datos actualizada: {change}")
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
