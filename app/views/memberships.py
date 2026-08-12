"""Inscripción de gym: tablero por estado, alta de mensualidades y recibo."""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..config import (
    MAX_FACES_PER_CLIENT,
    MAX_MEMBERSHIP_QUANTITY,
    VALID_DURATIONS,
    VALID_PAYMENT_METHODS,
)
from ..db import execute, query_all, query_one, query_value, transaction
from ..faces import client_face_count
from ..helpers import (
    DATE_FMT,
    active_membership_sql,
    compute_end_date,
    duration_label,
    format_date,
    membership_status,
    now_str,
    optional_string,
    parse_date,
    today,
    today_str,
)
from ..security import audit, roles_required
from ..receipts import receipt_barcode
from ..settings import business_info

bp = Blueprint("memberships", __name__, url_prefix="/inscripciones")


def compute_base_price(duration: str, quantity: int, tariffs: dict) -> float:
    """Precio de la inscripción antes de los servicios complementarios.

    Las mensualidades conservan su descuento: el primer mes va a la tarifa de «Por mes»
    y los siguientes a la de «mes adicional». Las duraciones que se cuentan en días se
    multiplican tal cual, porque no existe una tarifa de «día adicional» que aplicar y
    inventarse un descuento cambiaría lo que el gimnasio cobra hoy.
    """
    price = tariffs["inscription"].get(duration)
    if price is None:
        raise ValueError(
            "No hay tarifa configurada para esta duración. Configúrela en «Crear tarifas»."
        )
    if duration == "MONTH":
        return price + tariffs["extra_month"] * (quantity - 1)
    return price * quantity


def _load_tariffs() -> dict:
    tariffs = {r["duration"]: r["price"] for r in query_all("SELECT duration, price FROM inscription_tariffs")}
    extra = query_one("SELECT price FROM extra_month_tariff WHERE id = 1")
    services = query_all("SELECT * FROM services WHERE active = 1 ORDER BY name")
    return {
        "inscription": tariffs,
        "extra_month": extra["price"] if extra else 0,
        "services": services,
    }


# Opciones del filtro por estado de inscripción.
STATUS_FILTERS = {
    "": "Todos los estados",
    "active": "Solo inscripciones vigentes",
    "paused": "Solo inscripciones en pausa",
    "expired": "Solo inscripciones vencidas",
    "none": "Sin inscripción",
}


@bp.route("/")
@roles_required("ADMIN", "CAJA")
def index():
    search = optional_string(request.args.get("q")) or ""
    status_filter = optional_string(request.args.get("status")) or ""
    if status_filter not in STATUS_FILTERS:
        status_filter = ""

    sql = """
        SELECT c.*,
               m.id            AS membership_id,
               m.duration_type AS membership_duration,
               m.quantity      AS membership_quantity,
               m.paused_at     AS membership_paused,
               m.end_date      AS membership_end,
               m.total         AS membership_total
          FROM clients c
          -- Inscripción más reciente por fecha de vencimiento. La subconsulta evita
          -- traer todo el histórico solo para quedarse con una fila por cliente.
          LEFT JOIN memberships m
                 ON m.id = (SELECT id FROM memberships
                             WHERE client_id = c.id
                             ORDER BY end_date DESC, id DESC LIMIT 1)
         WHERE 1 = 1
    """
    params: list = []
    if search:
        sql += " AND (c.document_id LIKE ? OR c.first_name LIKE ? OR c.last_name LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]

    # El filtro se aplica en SQL y no después en Python, para que el conteo y el orden
    # correspondan al conjunto realmente filtrado.
    if status_filter == "active":
        sql += f" AND m.id IS NOT NULL AND {active_membership_sql('m')}"
        params.append(today_str())
    elif status_filter == "expired":
        sql += " AND m.id IS NOT NULL AND m.end_date <= ? AND m.paused_at IS NULL"
        params.append(today_str())
    elif status_filter == "paused":
        sql += " AND m.paused_at IS NOT NULL"
    elif status_filter == "none":
        sql += " AND m.id IS NULL"

    # Al filtrar por vencidas interesa primero la que lleva más tiempo caducada.
    sql += " ORDER BY m.end_date ASC" if status_filter == "expired" else " ORDER BY c.created_at DESC, c.id DESC"

    board = []
    for row in query_all(sql, params):
        status, days_left = membership_status(row["membership_end"], row["membership_paused"])
        board.append({"client": row, "status": status, "days_left": days_left})

    # Contadores para las pestañas del filtro, sobre el total (no sobre lo filtrado).
    today_iso = today_str()
    vigente = active_membership_sql()
    counts = {
        "active": query_value(
            f"""SELECT COUNT(*) FROM clients c WHERE EXISTS
                  (SELECT 1 FROM memberships WHERE client_id = c.id AND {vigente})""",
            (today_iso,), 0),
        "paused": query_value(
            """SELECT COUNT(*) FROM clients c WHERE EXISTS
                 (SELECT 1 FROM memberships WHERE client_id = c.id AND paused_at IS NOT NULL)""",
            (), 0),
        "expired": query_value(
            f"""SELECT COUNT(*) FROM clients c
                 WHERE EXISTS (SELECT 1 FROM memberships WHERE client_id = c.id)
                   AND NOT EXISTS (SELECT 1 FROM memberships WHERE client_id = c.id
                                    AND ({vigente} OR paused_at IS NOT NULL))""",
            (today_iso,), 0),
        "none": query_value(
            "SELECT COUNT(*) FROM clients c WHERE NOT EXISTS (SELECT 1 FROM memberships WHERE client_id = c.id)",
            (), 0),
    }
    # Las pausadas sí se suman: un cliente en pausa no está en ninguna de las otras
    # categorías (no está vigente, pero tampoco vencido ni sin inscripción).
    counts[""] = counts["active"] + counts["expired"] + counts["none"] + counts["paused"]

    return render_template(
        "memberships/index.html",
        board=board,
        search=search,
        status_filter=status_filter,
        status_filters=STATUS_FILTERS,
        counts=counts,
    )


@bp.route("/cliente/<int:client_id>", methods=("GET", "POST"))
@roles_required("ADMIN", "CAJA")
def manage(client_id: int):
    client = query_one("SELECT * FROM clients WHERE id = ?", (client_id,))
    if client is None:
        flash("Cliente no encontrado.", "error")
        return redirect(url_for("memberships.index"))

    tariffs = _load_tariffs()
    current = query_one(
        "SELECT * FROM memberships WHERE client_id = ? ORDER BY end_date DESC, id DESC LIMIT 1",
        (client_id,),
    )
    status, days_left = membership_status(
        current["end_date"] if current else None,
        current["paused_at"] if current else None,
    )

    if request.method == "POST":
        try:
            membership_id = _create_membership(client, request.form, tariffs)
            flash("Inscripción registrada correctamente.", "success")
            return redirect(url_for("memberships.receipt", membership_id=membership_id))
        except ValueError as exc:
            flash(str(exc), "error")

    history = query_all(
        """SELECT m.*, u.first_name AS seller_first, u.last_name AS seller_last
             FROM memberships m JOIN users u ON u.id = m.sold_by_id
            WHERE m.client_id = ? ORDER BY m.created_at DESC""",
        (client_id,),
    )

    # La renovación arranca donde termina la inscripción vigente; si está vencida o no
    # hay ninguna, arranca hoy.
    default_start = current["end_date"] if (current and status == "active") else today_str()

    return render_template(
        "memberships/manage.html",
        client=client,
        tariffs=tariffs,
        current=current,
        status=status,
        days_left=days_left,
        history=history,
        default_start=default_start,
        form=request.form if request.method == "POST" else {},
        max_quantity=MAX_MEMBERSHIP_QUANTITY,
        face_count=client_face_count(client_id),
        max_faces=MAX_FACES_PER_CLIENT,
    )


def _create_membership(client, form, tariffs) -> int:
    duration = optional_string(form.get("duration_type"))
    if duration not in VALID_DURATIONS:
        raise ValueError("Tipo de inscripción inválido.")

    # La cantidad vale para cualquier duración: 3 días, 2 semanas, 6 meses.
    raw = (form.get("quantity") or "1").strip()
    if not raw.isdigit() or int(raw) < 1:
        raise ValueError("La cantidad debe ser un número entero mayor o igual a 1.")
    quantity = int(raw)
    if quantity > MAX_MEMBERSHIP_QUANTITY:
        raise ValueError(f"La cantidad no puede superar {MAX_MEMBERSHIP_QUANTITY}.")

    payment_method = optional_string(form.get("payment_method")) or "EFECTIVO"
    if payment_method not in VALID_PAYMENT_METHODS:
        raise ValueError("Método de pago inválido.")

    start = parse_date(form.get("start_date"))
    if start is None:
        raise ValueError("La fecha de inicio no es válida (formato esperado: AAAA-MM-DD).")

    base_price = compute_base_price(duration, quantity, tariffs)

    # Los precios de los servicios se releen de la base, nunca se toman del formulario:
    # si no, bastaría con manipular el POST para cobrarse un servicio a cero.
    selected_ids = {
        int(v) for v in form.getlist("service_ids") if str(v).isdigit()
    }
    chosen = [s for s in tariffs["services"] if s["id"] in selected_ids]
    services_total = sum(s["price"] for s in chosen)

    end = compute_end_date(start, duration, quantity)
    total = round(base_price + services_total, 2)
    now = now_str()

    with transaction() as db:
        cur = db.execute(
            """INSERT INTO memberships (client_id, sold_by_id, duration_type, quantity, start_date,
                                        end_date, base_price, services_total, total,
                                        payment_method, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                client["id"], g.user["id"], duration, quantity, start.strftime(DATE_FMT),
                end.strftime(DATE_FMT), round(base_price, 2), round(services_total, 2),
                total, payment_method, now,
            ),
        )
        membership_id = int(cur.lastrowid or 0)
        for service in chosen:
            db.execute(
                "INSERT INTO membership_services (membership_id, service_id, price) VALUES (?, ?, ?)",
                (membership_id, service["id"], service["price"]),
            )

    audit(
        "MEMBERSHIP_CREATED",
        f"cliente {client['document_id']} - {duration_label(duration, quantity)} - {total}",
    )
    return membership_id


@bp.post("/<int:membership_id>/pausar")
@roles_required("ADMIN", "CAJA")
def pause(membership_id: int):
    """Congela la inscripción guardando los días que le quedaban.

    No se toca `end_date`: mientras está pausada esa fecha ya no significa nada (la
    regla de vigencia exige además `paused_at IS NULL`), y conservarla permite deshacer
    la pausa el mismo día dejándolo todo exactamente como estaba.
    """
    membership = query_one("SELECT * FROM memberships WHERE id = ?", (membership_id,))
    if membership is None:
        flash("Inscripción no encontrada.", "error")
        return redirect(url_for("memberships.index"))

    back = redirect(url_for("memberships.manage", client_id=membership["client_id"]))

    if membership["paused_at"]:
        flash("Esa inscripción ya está en pausa.", "warning")
        return back

    end = parse_date(membership["end_date"])
    days_left = (end - today()).days if end else 0
    if days_left <= 0:
        flash(
            "No se puede pausar una inscripción vencida: no le quedan días que guardar. "
            "Registre una nueva.",
            "error",
        )
        return back

    execute(
        "UPDATE memberships SET paused_at = ?, paused_days = ? WHERE id = ?",
        (today_str(), days_left, membership_id),
    )
    audit("MEMBERSHIP_PAUSED", f"inscripción id={membership_id} con {days_left} día(s) guardados")
    flash(
        f"Inscripción pausada. Se guardaron {days_left} día(s); al reanudarla volverá a "
        "contar desde ese momento.",
        "success",
    )
    return back


@bp.post("/<int:membership_id>/reanudar")
@roles_required("ADMIN", "CAJA")
def resume(membership_id: int):
    """Reanuda la inscripción: vence dentro de los días que se guardaron al pausarla."""
    membership = query_one("SELECT * FROM memberships WHERE id = ?", (membership_id,))
    if membership is None:
        flash("Inscripción no encontrada.", "error")
        return redirect(url_for("memberships.index"))

    back = redirect(url_for("memberships.manage", client_id=membership["client_id"]))

    if not membership["paused_at"]:
        flash("Esa inscripción no está en pausa.", "warning")
        return back

    # Si la fila quedara sin días guardados (base editada a mano), se recalcula desde
    # la fecha de pausa en vez de dejar al cliente sin vigencia.
    days_left = membership["paused_days"]
    if not days_left or days_left < 1:
        paused_on = parse_date(membership["paused_at"])
        end = parse_date(membership["end_date"])
        days_left = max(1, (end - paused_on).days) if (paused_on and end) else 1

    new_end = today() + timedelta(days=days_left)
    execute(
        "UPDATE memberships SET end_date = ?, paused_at = NULL, paused_days = NULL WHERE id = ?",
        (new_end.strftime(DATE_FMT), membership_id),
    )
    audit(
        "MEMBERSHIP_RESUMED",
        f"inscripción id={membership_id}, {days_left} día(s), vence {new_end.strftime(DATE_FMT)}",
    )
    flash(
        f"Inscripción reanudada con los {days_left} día(s) que le quedaban. "
        f"Nuevo vencimiento: {format_date(new_end)}.",
        "success",
    )
    return back


@bp.post("/<int:membership_id>/cancelar")
@roles_required("ADMIN", "CAJA")
def cancel(membership_id: int):
    """Cancelar elimina la inscripción por completo.

    Mientras el registro exista, la clave foránea impide eliminar al cliente. Se
    permite cancelar tanto las vigentes como las vencidas: si solo se pudiera con las
    vigentes, un cliente con inscripción vencida quedaría imposible de borrar.
    """
    membership = query_one("SELECT * FROM memberships WHERE id = ?", (membership_id,))
    if membership is None:
        flash("Inscripción no encontrada.", "error")
        return redirect(url_for("memberships.index"))

    with transaction() as db:
        # membership_services tiene ON DELETE CASCADE, pero se borra explícitamente
        # para no depender de que el PRAGMA esté activo en esta conexión.
        db.execute("DELETE FROM membership_services WHERE membership_id = ?", (membership_id,))
        db.execute("DELETE FROM memberships WHERE id = ?", (membership_id,))

    audit(
        "MEMBERSHIP_CANCELLED",
        f"inscripción id={membership_id}, cliente id={membership['client_id']}",
    )
    flash("Inscripción cancelada.", "success")
    return redirect(url_for("memberships.manage", client_id=membership["client_id"]))


@bp.route("/recibo/<int:membership_id>")
@roles_required("ADMIN", "CAJA")
def receipt(membership_id: int):
    membership = query_one(
        """SELECT m.*, c.first_name AS client_first, c.last_name AS client_last,
                  c.document_id AS client_document,
                  u.first_name AS seller_first, u.last_name AS seller_last
             FROM memberships m
             JOIN clients c ON c.id = m.client_id
             JOIN users   u ON u.id = m.sold_by_id
            WHERE m.id = ?""",
        (membership_id,),
    )
    if membership is None:
        flash("Inscripción no encontrada.", "error")
        return redirect(url_for("memberships.index"))

    services = query_all(
        """SELECT ms.price, s.name
             FROM membership_services ms JOIN services s ON s.id = ms.service_id
            WHERE ms.membership_id = ?""",
        (membership_id,),
    )
    return render_template(
        "memberships/receipt.html",
        membership=membership,
        services=services,
        negocio=business_info(),
        codigo=receipt_barcode("MEMBERSHIP", membership_id),
    )
