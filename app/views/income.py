"""Registro de ventas e ingresos: histórico filtrable y exportación (solo Administrador).

Reúne en una sola lista las dos fuentes de dinero del gimnasio —inscripciones y venta
de productos—, que hasta ahora solo se veían por separado y cada una en su módulo.

Los totales se calculan aparte, con una consulta de agregación sobre TODO lo que cumple
el filtro, no sumando las filas que se muestran: la tabla está limitada a las 1000 más
recientes y, si se sumara eso, un mes con más movimientos daría un total menor que el
real sin que nada lo advirtiera.
"""

from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, flash, render_template, request

from ..config import PAYMENT_METHODS, VALID_PAYMENT_METHODS
from ..db import query_all, query_one
from ..helpers import (
    DATE_FMT,
    duration_label,
    format_datetime_seconds,
    optional_string,
    parse_date,
    today_str,
)
from ..security import roles_required

bp = Blueprint("income", __name__, url_prefix="/ingresos")

MAX_ROWS = 1000

KINDS = {
    "": "Inscripciones y ventas",
    "MEMBERSHIP": "Solo inscripciones",
    "SALE": "Solo venta de productos",
}

KIND_LABELS = {"MEMBERSHIP": "Inscripción", "SALE": "Venta de productos"}

# Las dos fuentes se normalizan a la misma forma para poder ordenarlas y filtrarlas
# juntas. `detail_*` guarda lo propio de cada una: la duración en las inscripciones,
# las unidades vendidas en las ventas.
BASE_QUERY = """
    SELECT 'MEMBERSHIP' AS kind, m.id AS id, m.created_at AS created_at,
           m.total AS total, m.payment_method AS payment_method,
           m.sold_by_id AS staff_id,
           u.first_name || ' ' || u.last_name AS staff_name,
           c.first_name || ' ' || c.last_name AS person_name,
           c.document_id AS person_document,
           c.id AS client_id,
           m.duration_type AS detail_duration, m.quantity AS detail_quantity,
           NULL AS detail_units
      FROM memberships m
      JOIN users   u ON u.id = m.sold_by_id
      JOIN clients c ON c.id = m.client_id
      -- Las migradas quedan fuera: existían antes del programa y no representan un
      -- cobro. Sumarlas mostraría un ingreso que nunca entró por caja.
     WHERE m.is_migrated = 0

    UNION ALL

    SELECT 'SALE', s.id, s.created_at,
           s.total, s.payment_method,
           s.seller_id,
           u.first_name || ' ' || u.last_name,
           s.buyer_name,
           s.buyer_document,
           s.client_id,
           NULL, NULL,
           (SELECT COALESCE(SUM(si.quantity), 0) FROM sale_items si WHERE si.sale_id = s.id)
      FROM sales s
      JOIN users u ON u.id = s.seller_id
"""


def _build_filters(args) -> tuple[str, list, dict, str | None]:
    """Arma el WHERE común. Devuelve (condiciones, params, filtros, error)."""
    kind = optional_string(args.get("kind")) or ""
    payment = optional_string(args.get("payment")) or ""
    staff_id = optional_string(args.get("staff_id")) or ""
    search = optional_string(args.get("q")) or ""
    date_from = optional_string(args.get("from")) or ""
    date_to = optional_string(args.get("to")) or ""

    filters = {
        "kind": kind, "payment": payment, "staff_id": staff_id,
        "q": search, "from": date_from, "to": date_to,
    }

    if kind and kind not in KINDS:
        return "", [], filters, "Tipo de movimiento inválido."
    if payment and payment not in VALID_PAYMENT_METHODS:
        return "", [], filters, "Método de pago inválido."
    if staff_id and not staff_id.isdigit():
        return "", [], filters, "Usuario inválido."

    where = ""
    params: list = []

    if kind:
        where += " AND kind = ?"
        params.append(kind)
    if payment:
        where += " AND payment_method = ?"
        params.append(payment)
    if staff_id:
        where += " AND staff_id = ?"
        params.append(int(staff_id))
    if search:
        where += " AND (person_name LIKE ? OR person_document LIKE ?)"
        like = f"%{search}%"
        params += [like, like]

    start = end = None
    if date_from:
        start = parse_date(date_from)
        if start is None:
            return "", [], filters, 'La fecha "desde" no es válida.'
        where += " AND created_at >= ?"
        params.append(f"{start.strftime(DATE_FMT)} 00:00:00")
    if date_to:
        end = parse_date(date_to)
        if end is None:
            return "", [], filters, 'La fecha "hasta" no es válida.'
        # Inclusivo: incluye todo el día indicado.
        where += " AND created_at <= ?"
        params.append(f"{end.strftime(DATE_FMT)} 23:59:59")
    if start and end and start > end:
        return "", [], filters, 'La fecha "desde" debe ser anterior o igual a la fecha "hasta".'

    return where, params, filters, None


def _rows(where: str, params: list) -> list:
    return query_all(
        f"SELECT * FROM ({BASE_QUERY}) WHERE 1 = 1 {where} "
        f"ORDER BY created_at DESC, kind, id DESC LIMIT ?",
        [*params, MAX_ROWS],
    )


def _totals(where: str, params: list) -> dict:
    """Totales sobre todo lo filtrado, no solo sobre lo que se muestra."""
    row = query_one(
        f"""SELECT COUNT(*) AS movimientos,
                   COALESCE(SUM(total), 0) AS total,
                   COALESCE(SUM(CASE WHEN kind = 'MEMBERSHIP' THEN total ELSE 0 END), 0) AS memberships,
                   COALESCE(SUM(CASE WHEN kind = 'SALE'       THEN total ELSE 0 END), 0) AS sales,
                   COUNT(CASE WHEN kind = 'MEMBERSHIP' THEN 1 END) AS n_memberships,
                   COUNT(CASE WHEN kind = 'SALE'       THEN 1 END) AS n_sales
              FROM ({BASE_QUERY}) WHERE 1 = 1 {where}""",
        params,
    )
    data = dict(row) if row else {}
    movimientos = data.get("movimientos") or 0
    data["promedio"] = (data.get("total") or 0) / movimientos if movimientos else 0
    return data


def _by_payment(where: str, params: list) -> list:
    return query_all(
        f"""SELECT payment_method, COUNT(*) AS movimientos, COALESCE(SUM(total), 0) AS total
              FROM ({BASE_QUERY}) WHERE 1 = 1 {where}
             GROUP BY payment_method ORDER BY total DESC""",
        params,
    )


def describe(row) -> str:
    """Texto de la columna «Detalle», propio de cada tipo de movimiento."""
    if row["kind"] == "MEMBERSHIP":
        return duration_label(row["detail_duration"], row["detail_quantity"])
    units = row["detail_units"] or 0
    return f"{units} unidad(es)"


@bp.route("/")
@roles_required("ADMIN")
def index():
    where, params, filters, error = _build_filters(request.args)
    if error:
        flash(error, "error")
        rows, totals, by_payment = [], {}, []
    else:
        rows = _rows(where, params)
        totals = _totals(where, params)
        by_payment = _by_payment(where, params)

    return render_template(
        "income/index.html",
        rows=rows,
        totals=totals,
        by_payment=by_payment,
        filters=filters,
        kinds=KINDS,
        kind_labels=KIND_LABELS,
        describe=describe,
        staff=query_all(
            """SELECT id, username, first_name, last_name FROM users
                WHERE role IN ('ADMIN', 'CAJA') ORDER BY first_name"""
        ),
        max_rows=MAX_ROWS,
    )


@bp.route("/exportar.csv")
@roles_required("ADMIN")
def export_csv():
    where, params, _filters, error = _build_filters(request.args)
    rows = [] if error else _rows(where, params)
    totals = {} if error else _totals(where, params)

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([
        "Fecha y hora", "Tipo", "Cliente", "Documento", "Detalle",
        "Método de pago", "Atendido por", "Total",
    ])
    for row in rows:
        writer.writerow([
            format_datetime_seconds(row["created_at"]),
            KIND_LABELS.get(row["kind"], row["kind"]),
            row["person_name"] or "—",
            row["person_document"] or "—",
            describe(row),
            PAYMENT_METHODS.get(row["payment_method"], row["payment_method"]),
            row["staff_name"],
            # Coma decimal y sin separador de miles: es lo que Excel en español espera
            # en una columna numérica, y así el total se puede sumar en la hoja.
            f"{row['total']:.2f}".replace(".", ","),
        ])

    if rows:
        writer.writerow([])
        writer.writerow(["", "", "", "", "", "", "TOTAL", f"{totals.get('total', 0):.2f}".replace(".", ",")])
        writer.writerow(["", "", "", "", "", "", "Inscripciones",
                         f"{totals.get('memberships', 0):.2f}".replace(".", ",")])
        writer.writerow(["", "", "", "", "", "", "Venta de productos",
                         f"{totals.get('sales', 0):.2f}".replace(".", ",")])

    # BOM para que Excel en Windows reconozca el UTF-8 y no rompa las tildes.
    data = "﻿" + buffer.getvalue()
    filename = f"ventas-e-ingresos-{today_str()}.csv"
    return Response(
        data,
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
