"""Registro de actividad: historial filtrable y exportación (solo Administrador)."""

from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, flash, render_template, request

from ..config import ACTION_LABELS, ROLES, STAFF_ROLES
from ..db import query_all
from ..helpers import (
    DATE_FMT,
    format_datetime_seconds,
    optional_string,
    parse_date,
    today_str,
)
from ..security import roles_required

bp = Blueprint("audit", __name__, url_prefix="/actividad")

MAX_ROWS = 1000


def _build_query(args) -> tuple[str, list, dict, str | None]:
    """Arma el WHERE a partir de los filtros. Devuelve (sql, params, filtros, error)."""
    role = optional_string(args.get("role")) or ""
    user_id = optional_string(args.get("user_id")) or ""
    date_from = optional_string(args.get("from")) or ""
    date_to = optional_string(args.get("to")) or ""

    filters = {"role": role, "user_id": user_id, "from": date_from, "to": date_to}

    if role and role not in STAFF_ROLES:
        return "", [], filters, "Rol inválido."
    if user_id and not user_id.isdigit():
        return "", [], filters, "Usuario inválido."

    sql = """
        SELECT a.*, u.username, u.role, u.first_name, u.last_name
          FROM audit_logs a LEFT JOIN users u ON u.id = a.user_id
         WHERE 1 = 1
    """
    params: list = []

    if role:
        sql += " AND u.role = ?"
        params.append(role)
    if user_id:
        sql += " AND a.user_id = ?"
        params.append(int(user_id))

    start = end = None
    if date_from:
        start = parse_date(date_from)
        if start is None:
            return "", [], filters, 'La fecha "desde" no es válida.'
        sql += " AND a.created_at >= ?"
        params.append(f"{start.strftime(DATE_FMT)} 00:00:00")
    if date_to:
        end = parse_date(date_to)
        if end is None:
            return "", [], filters, 'La fecha "hasta" no es válida.'
        # Filtro inclusivo: incluye todo el día indicado.
        sql += " AND a.created_at <= ?"
        params.append(f"{end.strftime(DATE_FMT)} 23:59:59")
    if start and end and start > end:
        return "", [], filters, 'La fecha "desde" debe ser anterior o igual a la fecha "hasta".'

    sql += " ORDER BY a.created_at DESC, a.id DESC LIMIT ?"
    params.append(MAX_ROWS)
    return sql, params, filters, None


@bp.route("/")
@roles_required("ADMIN")
def index():
    sql, params, filters, error = _build_query(request.args)
    if error:
        flash(error, "error")
        logs = []
    else:
        logs = query_all(sql, params)

    return render_template(
        "audit/index.html",
        logs=logs,
        filters=filters,
        users=query_all("SELECT id, username, first_name, last_name, role FROM users ORDER BY first_name"),
        staff_roles={k: v for k, v in ROLES.items() if k in STAFF_ROLES},
        max_rows=MAX_ROWS,
    )


@bp.route("/exportar.csv")
@roles_required("ADMIN")
def export_csv():
    sql, params, _filters, error = _build_query(request.args)
    logs = [] if error else query_all(sql, params)

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Fecha y hora", "Usuario", "Usuario del sistema", "Rol", "Acción", "Detalle", "Resultado"])
    for log in logs:
        writer.writerow([
            format_datetime_seconds(log["created_at"]),
            f"{log['first_name']} {log['last_name']}" if log["username"] else "—",
            log["username"] or "—",
            ROLES.get(log["role"], "—") if log["role"] else "—",
            ACTION_LABELS.get(log["action"], log["action"]),
            log["detail"] or "—",
            "Éxito" if log["success"] else "Fallido",
        ])

    # BOM para que Excel en Windows reconozca el UTF-8 y no rompa las tildes.
    data = "﻿" + buffer.getvalue()
    filename = f"registro-actividad-{today_str()}.csv"
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
