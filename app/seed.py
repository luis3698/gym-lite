"""Datos iniciales de GymManager Lite.

Es idempotente: se puede ejecutar las veces que haga falta sin duplicar nada ni
pisar cambios hechos desde la aplicación.
"""

from __future__ import annotations

import sqlite3

from flask import Flask

from .helpers import DATE_FMT, add_months, now_str, today
from .security import hash_password

ADMIN_USERNAME = "Admin"
ADMIN_PASSWORD = "Admin.123"

TARIFFS = (("DAY_1", 15000), ("DAY_7", 60000), ("DAY_15", 100000), ("MONTH", 150000))
EXTRA_MONTH_PRICE = 130000

SERVICES = (
    ("Casillero", 10000),
    ("Clases grupales", 30000),
    ("Nutricionista", 50000),
    ("Entrenador personal", 80000),
)

PRODUCTS = (
    ("Proteína Whey 1kg", 120000, 20, "Suplementos"),
    ("Creatina 300g", 65000, 25, "Suplementos"),
    ("Shaker", 18000, 40, "Accesorios"),
    ("Guantes de entrenamiento", 35000, 15, "Accesorios"),
    ("Agua 600ml", 3000, 100, "Bebidas"),
    ("Bebida hidratante", 6000, 60, "Bebidas"),
    ("Toalla deportiva", 22000, 30, "Accesorios"),
    ("Barra energética", 8000, 50, "Suplementos"),
)

DEMO_CLIENT = {
    "first_name": "Cliente",
    "last_name": "Demo",
    "document_id": "1000000001",
    "sex": "Masculino",
    "age": 27,
    "phone": "3009998877",
    "email": "cliente.demo@gymlite.local",
    "emergency_contact_name": "Contacto Demo",
    "emergency_contact_phone": "3001112233",
}


def seed_database(app: Flask) -> list[str]:
    """Inserta lo que falte. Devuelve las líneas a mostrar por consola."""
    messages: list[str] = []
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        now = now_str()

        # --- Administrador --------------------------------------------------
        admin = conn.execute("SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,)).fetchone()
        if admin is None:
            cur = conn.execute(
                """INSERT INTO users (username, password_hash, role, first_name, last_name,
                                      document_id, sex, age, phone, email, blood_type,
                                      created_at, updated_at)
                   VALUES (?, ?, 'ADMIN', 'Administrador', 'General', 'ADMIN-0001',
                           'No especifica', 30, '3000000000', 'admin@gymlite.local', 'O+', ?, ?)""",
                (ADMIN_USERNAME, hash_password(ADMIN_PASSWORD), now, now),
            )
            admin_id = int(cur.lastrowid or 0)
            messages.append(
                f"Usuario administrador creado -> usuario: {ADMIN_USERNAME} / contraseña: {ADMIN_PASSWORD}"
            )
        else:
            admin_id = admin["id"]

        # --- Tarifas y servicios --------------------------------------------
        for duration, price in TARIFFS:
            conn.execute(
                "INSERT OR IGNORE INTO inscription_tariffs (duration, price) VALUES (?, ?)",
                (duration, price),
            )
        conn.execute(
            "INSERT OR IGNORE INTO extra_month_tariff (id, price) VALUES (1, ?)",
            (EXTRA_MONTH_PRICE,),
        )
        for name, price in SERVICES:
            conn.execute("INSERT OR IGNORE INTO services (name, price) VALUES (?, ?)", (name, price))

        # --- Productos ------------------------------------------------------
        for name, price, stock, category in PRODUCTS:
            exists = conn.execute("SELECT 1 FROM products WHERE name = ?", (name,)).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO products (name, price, stock, category, created_at) VALUES (?, ?, ?, ?, ?)",
                    (name, price, stock, category, now),
                )

        # --- Cliente de ejemplo con una inscripción vigente ------------------
        client = conn.execute(
            "SELECT id FROM clients WHERE document_id = ?", (DEMO_CLIENT["document_id"],)
        ).fetchone()
        if client is None:
            cur = conn.execute(
                """INSERT INTO clients (first_name, last_name, document_id, sex, age, phone, email,
                                        emergency_contact_name, emergency_contact_phone,
                                        created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    DEMO_CLIENT["first_name"], DEMO_CLIENT["last_name"], DEMO_CLIENT["document_id"],
                    DEMO_CLIENT["sex"], DEMO_CLIENT["age"], DEMO_CLIENT["phone"], DEMO_CLIENT["email"],
                    DEMO_CLIENT["emergency_contact_name"], DEMO_CLIENT["emergency_contact_phone"],
                    now, now,
                ),
            )
            client_id = int(cur.lastrowid or 0)
            messages.append(
                f"Cliente de ejemplo creado -> {DEMO_CLIENT['first_name']} "
                f"{DEMO_CLIENT['last_name']} ({DEMO_CLIENT['document_id']})"
            )

            start = today()
            end = add_months(start, 1)
            price = dict(TARIFFS)["MONTH"]
            conn.execute(
                """INSERT INTO memberships (client_id, sold_by_id, duration_type, months,
                                            start_date, end_date, base_price, services_total,
                                            total, payment_method, created_at)
                   VALUES (?, ?, 'MONTH', 1, ?, ?, ?, 0, ?, 'EFECTIVO', ?)""",
                (client_id, admin_id, start.strftime(DATE_FMT), end.strftime(DATE_FMT), price, price, now),
            )

        conn.commit()
    finally:
        conn.close()

    if not messages:
        messages.append("Los datos iniciales ya existían, no se recrearon.")
    return messages
