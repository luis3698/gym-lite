"""Tarifas de inscripción y servicios complementarios (solo Administrador)."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..config import VALID_DURATIONS
from ..db import execute, insert, query_all, query_one, transaction
from ..helpers import InvalidNumber, optional_string, parse_price
from ..security import audit, roles_required

bp = Blueprint("tariffs", __name__, url_prefix="/tarifas")


@bp.route("/")
@roles_required("ADMIN")
def index():
    tariffs = {r["duration"]: r["price"] for r in query_all("SELECT duration, price FROM inscription_tariffs")}
    extra = query_one("SELECT price FROM extra_month_tariff WHERE id = 1")
    return render_template(
        "tariffs/index.html",
        tariffs=tariffs,
        extra_month=extra["price"] if extra else "",
        services=query_all("SELECT * FROM services WHERE active = 1 ORDER BY name"),
    )


@bp.post("/inscripcion")
@roles_required("ADMIN")
def save_inscription():
    try:
        prices = {
            duration: parse_price(
                request.form.get(duration), field=f"El valor para «{duration}»"
            )
            for duration in VALID_DURATIONS
        }
        extra = parse_price(request.form.get("extra_month"), field="El valor por mes adicional")
    except (InvalidNumber, ValueError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("tariffs.index"))

    # Todas las tarifas se guardan de golpe: si una escritura fallara a mitad,
    # quedarían unas duraciones con el valor nuevo y otras con el viejo.
    with transaction() as db:
        for duration, price in prices.items():
            db.execute(
                """INSERT INTO inscription_tariffs (duration, price) VALUES (?, ?)
                   ON CONFLICT(duration) DO UPDATE SET price = excluded.price""",
                (duration, price),
            )
        db.execute(
            """INSERT INTO extra_month_tariff (id, price) VALUES (1, ?)
               ON CONFLICT(id) DO UPDATE SET price = excluded.price""",
            (extra,),
        )

    audit("TARIFFS_UPDATED", "tarifas de inscripción actualizadas")
    flash("Tarifas de inscripción actualizadas.", "success")
    return redirect(url_for("tariffs.index"))


@bp.post("/servicios")
@roles_required("ADMIN")
def create_service():
    try:
        name = optional_string(request.form.get("name"))
        if not name:
            raise ValueError("El servicio requiere un nombre.")
        price = parse_price(request.form.get("price"), field="El valor del servicio")
    except (InvalidNumber, ValueError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("tariffs.index"))

    existing = query_one("SELECT * FROM services WHERE name = ?", (name,))
    if existing:
        if existing["active"]:
            flash("Ya existe un servicio con ese nombre.", "error")
            return redirect(url_for("tariffs.index"))
        # Un servicio "eliminado" solo queda inactivo, para no romper el histórico de
        # inscripciones. Si se vuelve a crear con el mismo nombre, se reactiva.
        execute("UPDATE services SET price = ?, active = 1 WHERE id = ?", (price, existing["id"]))
    else:
        insert("INSERT INTO services (name, price) VALUES (?, ?)", (name, price))

    audit("SERVICE_CREATED", name)
    flash(f"Servicio «{name}» disponible para nuevas inscripciones.", "success")
    return redirect(url_for("tariffs.index"))


@bp.post("/servicios/<int:service_id>/editar")
@roles_required("ADMIN")
def edit_service(service_id: int):
    service = query_one("SELECT * FROM services WHERE id = ?", (service_id,))
    if service is None:
        flash("Servicio no encontrado.", "error")
        return redirect(url_for("tariffs.index"))

    try:
        name = optional_string(request.form.get("name"))
        if not name:
            raise ValueError("El nombre del servicio no puede quedar vacío.")
        price = parse_price(request.form.get("price"), field="El valor del servicio")
    except (InvalidNumber, ValueError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("tariffs.index"))

    duplicate = query_one("SELECT 1 FROM services WHERE name = ? AND id != ?", (name, service_id))
    if duplicate:
        flash("Ya existe otro servicio con ese nombre.", "error")
        return redirect(url_for("tariffs.index"))

    execute("UPDATE services SET name = ?, price = ? WHERE id = ?", (name, price, service_id))
    audit("SERVICE_UPDATED", name)
    flash(f"Servicio «{name}» actualizado.", "success")
    return redirect(url_for("tariffs.index"))


@bp.post("/servicios/<int:service_id>/eliminar")
@roles_required("ADMIN")
def delete_service(service_id: int):
    service = query_one("SELECT * FROM services WHERE id = ?", (service_id,))
    if service is None:
        flash("Servicio no encontrado.", "error")
        return redirect(url_for("tariffs.index"))

    execute("UPDATE services SET active = 0 WHERE id = ?", (service_id,))
    audit("SERVICE_DELETED", service["name"])
    flash(
        f"«{service['name']}» dejará de ofrecerse en nuevas inscripciones. "
        f"Las ya registradas con este servicio se conservan.",
        "success",
    )
    return redirect(url_for("tariffs.index"))
