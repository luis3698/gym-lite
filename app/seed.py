"""Datos iniciales de GymManager Lite.

La base arranca limpia: solo se crea la cuenta de administrador. Tarifas,
servicios, productos y clientes se cargan desde la propia aplicación.

Es idempotente: se puede ejecutar las veces que haga falta sin duplicar nada ni
pisar cambios hechos desde la aplicación.
"""

from __future__ import annotations

import sqlite3

from flask import Flask

from .helpers import now_str
from .security import hash_password

ADMIN_USERNAME = "Admin"
ADMIN_PASSWORD = "Admin.123"


def seed_database(app: Flask) -> list[str]:
    """Crea el administrador si falta. Devuelve las líneas a mostrar por consola."""
    messages: list[str] = []
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        admin = conn.execute("SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,)).fetchone()
        if admin is None:
            now = now_str()
            conn.execute(
                """INSERT INTO users (username, password_hash, role, first_name, last_name,
                                      document_id, sex, age, phone, email, blood_type,
                                      created_at, updated_at)
                   VALUES (?, ?, 'ADMIN', 'Administrador', 'General', 'ADMIN-0001',
                           NULL, 30, '3000000000', 'admin@gymlite.local', 'O+', ?, ?)""",
                (ADMIN_USERNAME, hash_password(ADMIN_PASSWORD), now, now),
            )
            messages.append(
                f"Usuario administrador creado -> usuario: {ADMIN_USERNAME} / contraseña: {ADMIN_PASSWORD}"
            )
        conn.commit()
    finally:
        conn.close()

    if not messages:
        messages.append("El usuario administrador ya existía, no se recreó.")
    return messages
