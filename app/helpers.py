"""Validaciones, fechas y formato compartidos por todas las vistas."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Any

from .config import MAX_AGE

# --- Texto y números ---------------------------------------------------------


def optional_string(value: Any) -> str | None:
    """Normaliza un campo de texto opcional de un formulario.

    Los formularios envían cadena vacía cuando el usuario no escribe nada. Guardarla
    tal cual rompe los índices UNIQUE que admiten NULL (dos clientes sin correo
    chocarían entre sí con '' = ''), así que se convierte a None.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def required_string(value: Any) -> str | None:
    """Igual que optional_string; se usa donde el campo es obligatorio, para leerlo mejor."""
    return optional_string(value)


class InvalidNumber(ValueError):
    """El valor no es un entero válido dentro del rango pedido."""


def parse_optional_int(value: Any, *, minimum: int = 0, maximum: int | None = None) -> int | None:
    """Entero opcional de formulario. Devuelve None si viene vacío.

    Lanza InvalidNumber si hay algo escrito pero no es un entero dentro del rango,
    para poder responder con un mensaje claro en vez de dejar que falle la base.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = int(text)
    except ValueError:
        raise InvalidNumber(f"«{text}» no es un número entero.") from None
    if number < minimum or (maximum is not None and number > maximum):
        limit = f"entre {minimum} y {maximum}" if maximum is not None else f"mayor o igual a {minimum}"
        raise InvalidNumber(f"El valor debe ser un número entero {limit}.")
    return number


def parse_age(value: Any) -> int | None:
    try:
        return parse_optional_int(value, minimum=0, maximum=MAX_AGE)
    except InvalidNumber:
        raise InvalidNumber(f"La edad debe ser un número entero entre 0 y {MAX_AGE}.") from None


def parse_price(value: Any, *, field: str = "El valor") -> float:
    """Precio obligatorio: numérico y mayor que cero."""
    text = str(value or "").strip().replace(",", ".")
    try:
        price = float(text)
    except ValueError:
        raise InvalidNumber(f"{field} debe ser numérico.") from None
    if price <= 0 or price != price or price in (float("inf"), float("-inf")):
        raise InvalidNumber(f"{field} debe ser mayor a cero.")
    return round(price, 2)


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def is_valid_email(email: str | None) -> bool:
    return bool(email) and bool(EMAIL_RE.match(email))


# Misma política que la versión original: mínimo 8, mayúscula, minúscula, número y
# carácter especial.
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")


def is_strong_password(password: Any) -> bool:
    return isinstance(password, str) and bool(PASSWORD_RE.match(password))


TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def is_valid_time(value: Any) -> bool:
    return bool(value) and bool(TIME_RE.match(str(value)))


# --- Fechas ------------------------------------------------------------------

DATE_FMT = "%Y-%m-%d"
DATETIME_FMT = "%Y-%m-%d %H:%M:%S"

MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
MONTHS_ES_SHORT = (
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)


def now_str() -> str:
    return datetime.now().strftime(DATETIME_FMT)


def today() -> date:
    return date.today()


def today_str() -> str:
    return date.today().strftime(DATE_FMT)


def parse_date(value: Any) -> date | None:
    """'YYYY-MM-DD' -> date, o None si no es una fecha real.

    Rechaza cosas como '2026-02-30' antes de que lleguen a la base de datos.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, DATE_FMT).date()
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in (DATETIME_FMT, DATE_FMT):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def add_months(start: date, months: int) -> date:
    """Suma meses recortando al último día del mes destino.

    Sumar un mes al 31 de enero no puede dar «31 de febrero». Sin este recorte, el
    cálculo desborda al 3 de marzo y regala un mes entero de vigencia cobrada.
    """
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def compute_end_date(start: date, duration_type: str, months: int | None) -> date:
    if duration_type == "DAY_1":
        return start + timedelta(days=1)
    if duration_type == "DAY_7":
        return start + timedelta(days=7)
    if duration_type == "DAY_15":
        return start + timedelta(days=15)
    if duration_type == "MONTH":
        return add_months(start, max(1, months or 1))
    raise ValueError(f"Duración desconocida: {duration_type}")


def membership_status(end_date_str: str | None) -> tuple[str, int | None]:
    """Estado de vigencia -> ('none' | 'active' | 'expired', días restantes)."""
    if not end_date_str:
        return "none", None
    end = parse_date(end_date_str)
    if end is None:
        return "none", None
    days_left = (end - date.today()).days
    return ("active", days_left) if days_left > 0 else ("expired", days_left)


# --- Formato para las plantillas --------------------------------------------


def format_money(value: Any) -> str:
    """12345.0 -> '$12.345' (separador de miles con punto, como en es-CO)."""
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    if abs(number - round(number)) < 0.005:
        return "$" + f"{int(round(number)):,}".replace(",", ".")
    entero, _, decimales = f"{number:,.2f}".partition(".")
    return "$" + entero.replace(",", ".") + "," + decimales


def format_number_input(value: Any) -> str:
    """Valor para un <input type="number">.

    Los precios se guardan como REAL, así que Python los imprime como «15000.0» y ese
    «.0» acaba dentro del campo del formulario. Se muestra entero cuando no tiene
    decimales, y con dos decimales cuando sí los tiene.
    """
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number - round(number)) < 0.005:
        return str(int(round(number)))
    return f"{number:.2f}"


def format_date(value: Any) -> str:
    """'2026-08-05' -> '05 de agosto de 2026'."""
    parsed = value if isinstance(value, date) else parse_date(value)
    if parsed is None:
        parsed_dt = parse_datetime(value)
        if parsed_dt is None:
            return "—"
        parsed = parsed_dt.date()
    return f"{parsed.day:02d} de {MONTHS_ES[parsed.month - 1]} de {parsed.year}"


def format_datetime(value: Any) -> str:
    """'2026-08-05 14:30:00' -> '05/08/2026 14:30'."""
    parsed = value if isinstance(value, datetime) else parse_datetime(value)
    if parsed is None:
        return "—"
    return parsed.strftime("%d/%m/%Y %H:%M")


def format_datetime_seconds(value: Any) -> str:
    parsed = value if isinstance(value, datetime) else parse_datetime(value)
    if parsed is None:
        return "—"
    return parsed.strftime("%d/%m/%Y %H:%M:%S")


def month_key(value: Any) -> str:
    """Clave 'YYYY-MM' usada para agrupar las gráficas del panel."""
    parsed = parse_datetime(value)
    if parsed is None:
        return ""
    return parsed.strftime("%Y-%m")


def month_label(year: int, month: int) -> str:
    return f"{MONTHS_ES_SHORT[month - 1]} {str(year)[2:]}"


def register_filters(app) -> None:
    """Expone los formateadores como filtros de Jinja2."""
    app.jinja_env.filters["money"] = format_money
    app.jinja_env.filters["num"] = format_number_input
    app.jinja_env.filters["fecha"] = format_date
    app.jinja_env.filters["fechahora"] = format_datetime
    app.jinja_env.filters["fechahora_seg"] = format_datetime_seconds
