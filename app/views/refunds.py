"""Módulo de devoluciones.

Flujo pensado para el mostrador: se lee el código de barras del recibo (el lector teclea
la referencia y pulsa Enter), aparece la compra con su saldo devolvible, y se escribe
cuánto se devuelve. Puede ser todo o una parte, y se puede devolver varias veces hasta
agotar el saldo.

Nada se modifica del recibo original: cada devolución es una fila nueva. Así queda el
rastro completo de por qué la caja del día no coincide con lo vendido.
"""

from __future__ import annotations

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from ..barcode import parse_reference
from ..config import PAYMENT_METHODS, VALID_PAYMENT_METHODS
from ..db import query_all, query_one, query_value, transaction
from ..helpers import (
    DATE_FMT,
    InvalidNumber,
    optional_string,
    parse_date,
    parse_optional_decimal,
    now_str,
    today_str,
)
from ..refunds import RefundError, load_document, refunded_total, validate
from ..security import audit, roles_required

bp = Blueprint("refunds", __name__, url_prefix="/devoluciones")

MAX_ROWS = 500


# --- Buscar el recibo ---------------------------------------------------------


@bp.route("/")
@roles_required("ADMIN", "CAJA")
def index():
    codigo = optional_string(request.args.get("codigo")) or ""
    documento = None
    error = None

    if codigo:
        referencia = parse_reference(codigo)
        if referencia is None:
            error = (
                f"«{codigo}» no es una referencia de recibo de este programa. "
                "Los recibos empiezan por V (venta) o I (inscripción), como V000123."
            )
        else:
            documento = load_document(*referencia)
            if documento is None:
                error = f"No existe ningún recibo con la referencia {codigo.strip().upper()}."

    return render_template(
        "refunds/index.html",
        codigo=codigo,
        documento=documento,
        error=error,
        recientes=query_all(
            """SELECT r.*, u.first_name, u.last_name
                 FROM refunds r JOIN users u ON u.id = r.created_by_id
                ORDER BY r.created_at DESC, r.id DESC LIMIT 10"""
        ),
    )


@bp.get("/saldo/<code>")
@roles_required("ADMIN", "CAJA")
def balance(code: str):
    """Saldo devolvible de un recibo, para validar mientras se escribe el importe."""
    referencia = parse_reference(code)
    if referencia is None:
        return jsonify({"ok": False, "error": "Referencia inválida."}), 400

    documento = load_document(*referencia)
    if documento is None:
        return jsonify({"ok": False, "error": "Recibo no encontrado."}), 404

    return jsonify({
        "ok": True,
        "reference": documento["reference"],
        "total": documento["total"],
        "refunded": documento["refunded"],
        "available": documento["available"],
    })


# --- Registrar la devolución --------------------------------------------------


@bp.post("/registrar")
@roles_required("ADMIN", "CAJA")
def create():
    referencia = parse_reference(request.form.get("reference") or "")
    if referencia is None:
        flash("Referencia de recibo inválida.", "error")
        return redirect(url_for("refunds.index"))

    volver = redirect(url_for("refunds.index", codigo=request.form.get("reference")))

    documento = load_document(*referencia)
    if documento is None:
        flash("Ese recibo ya no existe.", "error")
        return redirect(url_for("refunds.index"))

    try:
        importe = parse_optional_decimal(
            request.form.get("amount"), field="El importe a devolver", minimum=0)
    except InvalidNumber as exc:
        flash(str(exc), "error")
        return volver
    if importe is None:
        flash("Escriba cuánto se va a devolver.", "error")
        return volver

    metodo = optional_string(request.form.get("payment_method")) or "EFECTIVO"
    if metodo not in VALID_PAYMENT_METHODS:
        flash("Método de devolución inválido.", "error")
        return volver

    motivo = optional_string(request.form.get("reason"))
    if not motivo:
        flash("Indique el motivo de la devolución: es lo que explica el descuadre después.", "error")
        return volver

    # Todo dentro de una transacción: se vuelve a comprobar el saldo con el bloqueo de
    # escritura tomado, de modo que dos cajas no puedan devolver a la vez el mismo saldo
    # y acabar sacando más dinero del que entró.
    try:
        with transaction() as db:
            disponible = db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM refunds WHERE doc_type = ? AND doc_id = ?",
                (documento["type"], documento["id"]),
            ).fetchone()[0]
            documento["refunded"] = round(float(disponible or 0), 2)
            validado = validate(documento, importe)

            db.execute(
                """INSERT INTO refunds (doc_type, doc_id, amount, reason, payment_method,
                                        created_by_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (documento["type"], documento["id"], validado, motivo, metodo,
                 g.user["id"], now_str()),
            )
    except RefundError as exc:
        audit("REFUND_FAILED", f"{documento['reference']}: {exc}", success=False)
        flash(str(exc), "error")
        return volver

    restante = round(documento["total"] - refunded_total(documento["type"], documento["id"]), 2)
    audit(
        "REFUND_CREATED",
        f"{documento['reference']} - {validado:.2f} ({motivo}) - queda {restante:.2f}",
    )
    flash(
        f"Devolución de {validado:,.2f} registrada sobre {documento['reference']}. "
        + (f"Quedan {restante:,.2f} por devolver." if restante > 0
           else "El recibo queda devuelto por completo."),
        "success",
    )
    if documento["type"] == "MEMBERSHIP" and restante <= 0:
        flash(
            "Ha devuelto el importe completo de una inscripción. Si además quiere que el "
            "socio deje de tener acceso, cancele la inscripción desde su ficha: devolver "
            "el dinero no la anula por sí solo.",
            "warning",
        )
    return volver


# --- Histórico ----------------------------------------------------------------


def _build_filters(args) -> tuple[str, list, dict, str | None]:
    tipo = optional_string(args.get("tipo")) or ""
    metodo = optional_string(args.get("metodo")) or ""
    busqueda = optional_string(args.get("q")) or ""
    desde = optional_string(args.get("from")) or ""
    hasta = optional_string(args.get("to")) or ""
    filtros = {"tipo": tipo, "metodo": metodo, "q": busqueda, "from": desde, "to": hasta}

    if tipo and tipo not in ("SALE", "MEMBERSHIP"):
        return "", [], filtros, "Tipo de recibo inválido."
    if metodo and metodo not in VALID_PAYMENT_METHODS:
        return "", [], filtros, "Método de pago inválido."

    where = ""
    params: list = []
    if tipo:
        where += " AND r.doc_type = ?"
        params.append(tipo)
    if metodo:
        where += " AND r.payment_method = ?"
        params.append(metodo)
    if busqueda:
        where += " AND (r.reason LIKE ? OR r.doc_id = ?)"
        params += [f"%{busqueda}%", busqueda if busqueda.isdigit() else -1]

    inicio = fin = None
    if desde:
        inicio = parse_date(desde)
        if inicio is None:
            return "", [], filtros, 'La fecha "desde" no es válida.'
        where += " AND r.created_at >= ?"
        params.append(f"{inicio.strftime(DATE_FMT)} 00:00:00")
    if hasta:
        fin = parse_date(hasta)
        if fin is None:
            return "", [], filtros, 'La fecha "hasta" no es válida.'
        where += " AND r.created_at <= ?"
        params.append(f"{fin.strftime(DATE_FMT)} 23:59:59")
    if inicio and fin and inicio > fin:
        return "", [], filtros, 'La fecha "desde" debe ser anterior o igual a la fecha "hasta".'

    return where, params, filtros, None


@bp.route("/historial")
@roles_required("ADMIN", "CAJA")
def history():
    where, params, filtros, error = _build_filters(request.args)
    if error:
        flash(error, "error")
        filas, totales = [], {}
    else:
        filas = query_all(
            f"""SELECT r.*, u.first_name, u.last_name
                  FROM refunds r JOIN users u ON u.id = r.created_by_id
                 WHERE 1 = 1 {where}
                 ORDER BY r.created_at DESC, r.id DESC LIMIT ?""",
            [*params, MAX_ROWS],
        )
        fila = query_one(
            f"""SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS total
                  FROM refunds r WHERE 1 = 1 {where}""",
            params,
        )
        totales = dict(fila) if fila else {}

    return render_template(
        "refunds/history.html",
        filas=filas,
        totales=totales,
        filtros=filtros,
        metodos=PAYMENT_METHODS,
        hoy=today_str(),
        max_rows=MAX_ROWS,
        devuelto_hoy=query_value(
            "SELECT COALESCE(SUM(amount), 0) FROM refunds WHERE created_at >= ?",
            (f"{today_str()} 00:00:00",), 0),
    )
