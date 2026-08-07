"""Panel de inicio: indicadores y gráficas del gimnasio."""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, render_template

from ..charts import bar_chart, line_chart
from ..config import STAFF_ROLES
from ..db import query_all, query_value
from ..helpers import DATE_FMT, active_membership_sql, month_label, today
from ..security import roles_required

bp = Blueprint("dashboard", __name__)


def _last_12_months() -> list[tuple[str, str]]:
    """[(clave 'YYYY-MM', etiqueta 'ago 26')] del mes actual hacia atrás."""
    current = today().replace(day=1)
    months: list[tuple[str, str]] = []
    for _ in range(12):
        months.append((current.strftime("%Y-%m"), month_label(current.year, current.month)))
        # Retroceder un mes: el día 1 del mes anterior es el día anterior al día 1 actual.
        current = (current - timedelta(days=1)).replace(day=1)
    months.reverse()
    return months


@bp.route("/")
@roles_required(*STAFF_ROLES)
def index():
    now = today()
    today_iso = now.strftime(DATE_FMT)
    in_7_days = (now + timedelta(days=7)).strftime(DATE_FMT)
    day_start = f"{today_iso} 00:00:00"
    day_end = f"{today_iso} 23:59:59"

    months = _last_12_months()
    since = f"{months[0][0]}-01"

    # "Usuarios activos" cuenta clientes distintos con inscripción vigente;
    # "Inscripciones vigentes" cuenta inscripciones. Son cifras distintas cuando un
    # cliente tiene más de una.
    vigente = active_membership_sql()
    active_clients = query_value(
        f"SELECT COUNT(DISTINCT client_id) FROM memberships WHERE {vigente}", (today_iso,), 0
    )
    active_memberships = query_value(
        f"SELECT COUNT(*) FROM memberships WHERE {vigente}", (today_iso,), 0
    )
    paused_memberships = query_value(
        "SELECT COUNT(*) FROM memberships WHERE paused_at IS NOT NULL", (), 0
    )
    sales_today = query_value(
        "SELECT COALESCE(SUM(total), 0) FROM sales WHERE created_at BETWEEN ? AND ?",
        (day_start, day_end),
        0,
    )
    memberships_today = query_value(
        "SELECT COALESCE(SUM(total), 0) FROM memberships WHERE created_at BETWEEN ? AND ?",
        (day_start, day_end),
        0,
    )

    # Agrupación por mes en SQL con strftime, en vez de traer todas las filas y
    # agruparlas en Python.
    clients_rows = query_all(
        """SELECT strftime('%Y-%m', created_at) AS mes, COUNT(*) AS total
             FROM clients WHERE created_at >= ? GROUP BY mes""",
        (since,),
    )
    membership_rows = query_all(
        """SELECT strftime('%Y-%m', created_at) AS mes, COALESCE(SUM(total), 0) AS total
             FROM memberships WHERE created_at >= ? GROUP BY mes""",
        (since,),
    )
    sales_rows = query_all(
        """SELECT strftime('%Y-%m', created_at) AS mes, COALESCE(SUM(total), 0) AS total
             FROM sales WHERE created_at >= ? GROUP BY mes""",
        (since,),
    )

    # --- Clientes con la inscripción vencida -----------------------------
    # Solo los que NO tienen ninguna inscripción vigente: si renovaron, su
    # inscripción anterior está vencida pero el cliente está al día.
    # Quien tiene la inscripción en pausa no es un moroso: no aparece aquí, porque la
    # congeló a propósito y esos días se le devuelven al reanudar.
    expired_clients = query_all(
        f"""SELECT c.id, c.first_name, c.last_name, c.document_id, c.phone, c.email, c.photo,
                   m.end_date, m.duration_type, m.quantity, m.total,
                   CAST(julianday(?) - julianday(m.end_date) AS INTEGER) AS days_expired
              FROM clients c
              JOIN memberships m
                ON m.id = (SELECT id FROM memberships
                            WHERE client_id = c.id ORDER BY end_date DESC, id DESC LIMIT 1)
             WHERE m.end_date <= ? AND m.paused_at IS NULL
               AND NOT EXISTS (SELECT 1 FROM memberships
                                WHERE client_id = c.id
                                  AND ({vigente} OR paused_at IS NOT NULL))
             ORDER BY m.end_date DESC""",
        (today_iso, today_iso, today_iso),
    )

    # --- Inscripciones que vencen en los próximos 7 días ------------------
    expiring_clients = query_all(
        """SELECT c.id, c.first_name, c.last_name, c.document_id, c.phone, c.photo,
                  m.end_date,
                  CAST(julianday(m.end_date) - julianday(?) AS INTEGER) AS days_left
             FROM clients c
             JOIN memberships m
               ON m.id = (SELECT id FROM memberships
                           WHERE client_id = c.id ORDER BY end_date DESC, id DESC LIMIT 1)
            WHERE m.end_date > ? AND m.end_date <= ? AND m.paused_at IS NULL
            ORDER BY m.end_date ASC""",
        (today_iso, today_iso, in_7_days),
    )

    # --- Indicadores adicionales ------------------------------------------
    total_clients = query_value("SELECT COUNT(*) FROM clients", (), 0)
    clients_without_membership = query_value(
        "SELECT COUNT(*) FROM clients c WHERE NOT EXISTS (SELECT 1 FROM memberships WHERE client_id = c.id)",
        (), 0,
    )
    month_start = f"{months[-1][0]}-01"
    new_clients_month = query_value(
        "SELECT COUNT(*) FROM clients WHERE created_at >= ?", (month_start,), 0
    )
    month_membership_income = query_value(
        "SELECT COALESCE(SUM(total), 0) FROM memberships WHERE created_at >= ?", (month_start,), 0
    )
    month_sales_income = query_value(
        "SELECT COALESCE(SUM(total), 0) FROM sales WHERE created_at >= ?", (month_start,), 0
    )
    low_stock = query_all(
        "SELECT id, name, stock FROM products WHERE active = 1 AND stock <= 5 ORDER BY stock, name"
    )
    top_products = query_all(
        """SELECT p.name, SUM(si.quantity) AS unidades,
                  SUM(si.quantity * si.unit_price) AS ingresos
             FROM sale_items si
             JOIN products p ON p.id = si.product_id
             JOIN sales s    ON s.id = si.sale_id
            WHERE s.created_at >= ?
            GROUP BY p.id ORDER BY unidades DESC, ingresos DESC LIMIT 5""",
        (since,),
    )

    clients_by_month = {r["mes"]: r["total"] for r in clients_rows}
    income_by_month: dict[str, float] = {}
    for row in membership_rows:
        income_by_month[row["mes"]] = income_by_month.get(row["mes"], 0) + row["total"]
    for row in sales_rows:
        income_by_month[row["mes"]] = income_by_month.get(row["mes"], 0) + row["total"]

    users_points = [(label, clients_by_month.get(key, 0)) for key, label in months]
    income_points = [(label, income_by_month.get(key, 0)) for key, label in months]

    return render_template(
        "dashboard.html",
        kpis={
            "active_users": active_clients,
            "active_memberships": active_memberships,
            # Se cuenta la lista que se muestra debajo, no las filas de memberships:
            # si un cliente tuviera dos inscripciones venciendo, el indicador y el
            # listado mostrarían cifras distintas.
            "expiring_soon": len(expiring_clients),
            "paused": paused_memberships,
            "today_income": (sales_today or 0) + (memberships_today or 0),
            "total_clients": total_clients,
            "expired_count": len(expired_clients),
            "without_membership": clients_without_membership,
            "new_clients_month": new_clients_month,
        },
        expired_clients=expired_clients,
        expiring_clients=expiring_clients,
        month_membership_income=month_membership_income,
        month_sales_income=month_sales_income,
        low_stock=low_stock,
        top_products=top_products,
        users_chart=line_chart(users_points, color="#6366f1"),
        income_chart=bar_chart(income_points, money=True, color="#22c55e"),
        current_month_income=income_by_month.get(months[-1][0], 0),
    )
