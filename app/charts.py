"""Gráficas del panel como SVG generado en Python.

La versión original usaba Recharts (JavaScript). Aquí el servidor devuelve el SVG
ya dibujado: sin librerías de gráficas, sin JavaScript y se ve igual al imprimir.
"""

from __future__ import annotations

import math

from markupsafe import Markup, escape

from .helpers import format_money

# Divisiones horizontales del eje Y (marcas = GRID_STEPS + 1, contando el cero).
GRID_STEPS = 4


def _nice_max(value: float) -> float:
    """Redondea el máximo del eje hacia arriba a 1, 2 o 5 x 10^n.

    Un eje que termina justo en el valor máximo deja la barra más alta pegada al
    borde y produce etiquetas como «$137.428».
    """
    if value <= 0:
        return 1.0
    magnitude = 10 ** (len(str(int(value))) - 1)
    for factor in (1, 2, 2.5, 5, 10):
        candidate = magnitude * factor
        if candidate >= value:
            return float(candidate)
    return float(magnitude * 10)


def _axis_label(value: float, money: bool) -> str:
    if not money:
        return str(int(value))
    if value >= 1_000_000:
        return f"${value / 1_000_000:g}M".replace(".", ",")
    if value >= 1000:
        return f"${value / 1000:g}k".replace(".", ",")
    return f"${value:g}"


def bar_chart(
    points: list[tuple[str, float]],
    *,
    money: bool = False,
    color: str = "#22c55e",
    height: int = 260,
) -> Markup:
    """Gráfica de barras. `points` es una lista de (etiqueta, valor)."""
    return _render(points, money=money, color=color, height=height, kind="bar")


def line_chart(
    points: list[tuple[str, float]],
    *,
    money: bool = False,
    color: str = "#6366f1",
    height: int = 260,
) -> Markup:
    """Gráfica de líneas. `points` es una lista de (etiqueta, valor)."""
    return _render(points, money=money, color=color, height=height, kind="line")


def _render(
    points: list[tuple[str, float]],
    *,
    money: bool,
    color: str,
    height: int,
    kind: str,
) -> Markup:
    if not points:
        return Markup('<p class="chart-empty">Sin datos para mostrar.</p>')

    width = 720
    pad_left, pad_right, pad_top, pad_bottom = 62, 14, 16, 34
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    values = [max(0.0, float(v)) for _, v in points]
    top = _nice_max(max(values) if values else 0)
    if not money:
        # Los recuentos (clientes por mes) son enteros. Con un máximo de 1, dividir el
        # eje en cuatro daba 0,25 / 0,5 / 0,75, que al truncarse mostraba «0, 0, 0, 1».
        # Se redondea el tope al siguiente múltiplo del número de divisiones.
        top = float(max(GRID_STEPS, math.ceil(top / GRID_STEPS) * GRID_STEPS))

    def y_of(value: float) -> float:
        return pad_top + plot_h - (value / top) * plot_h

    parts: list[str] = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">'
    ]

    # Rejilla horizontal y etiquetas del eje Y.
    for i in range(GRID_STEPS + 1):
        value = top * i / GRID_STEPS
        y = y_of(value)
        parts.append(
            f'<line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" y2="{y:.1f}" '
            f'stroke="#e2e8f0" stroke-width="1" stroke-dasharray="3 3" />'
        )
        parts.append(
            f'<text x="{pad_left - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="#94a3b8">{escape(_axis_label(value, money))}</text>'
        )

    count = len(points)
    slot = plot_w / count
    # Con 12 meses no caben todas las etiquetas del eje X sin solaparse.
    label_step = max(1, count // 7)

    if kind == "bar":
        bar_w = min(38.0, slot * 0.6)
        for i, (label, value) in enumerate(points):
            value = max(0.0, float(value))
            cx = pad_left + slot * i + slot / 2
            y = y_of(value)
            bar_h = max(0.0, pad_top + plot_h - y)
            parts.append(
                f'<rect x="{cx - bar_w / 2:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                f'height="{bar_h:.1f}" rx="4" fill="{color}">'
                f"<title>{escape(label)}: "
                f"{escape(format_money(value) if money else str(int(value)))}</title></rect>"
            )
            if i % label_step == 0:
                parts.append(
                    f'<text x="{cx:.1f}" y="{height - 12}" text-anchor="middle" '
                    f'font-size="11" fill="#94a3b8">{escape(label)}</text>'
                )
    else:
        coords = [
            (pad_left + slot * i + slot / 2, y_of(max(0.0, float(v))))
            for i, (_, v) in enumerate(points)
        ]
        path = " ".join(
            ("M" if i == 0 else "L") + f"{x:.1f} {y:.1f}" for i, (x, y) in enumerate(coords)
        )
        # Relleno suave bajo la línea, para que no quede un trazo solitario.
        area = (
            f"{path} L{coords[-1][0]:.1f} {pad_top + plot_h:.1f} "
            f"L{coords[0][0]:.1f} {pad_top + plot_h:.1f} Z"
        )
        parts.append(f'<path d="{area}" fill="{color}" fill-opacity="0.10" />')
        parts.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5" '
            f'stroke-linejoin="round" stroke-linecap="round" />'
        )
        for i, ((label, value), (x, y)) in enumerate(zip(points, coords)):
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#fff" '
                f'stroke="{color}" stroke-width="2">'
                f"<title>{escape(label)}: "
                f"{escape(format_money(value) if money else str(int(value)))}</title></circle>"
            )
            if i % label_step == 0:
                parts.append(
                    f'<text x="{x:.1f}" y="{height - 12}" text-anchor="middle" '
                    f'font-size="11" fill="#94a3b8">{escape(label)}</text>'
                )

    # Eje X.
    parts.append(
        f'<line x1="{pad_left}" y1="{pad_top + plot_h}" x2="{width - pad_right}" '
        f'y2="{pad_top + plot_h}" stroke="#cbd5e1" stroke-width="1" />'
    )
    parts.append("</svg>")
    return Markup("".join(parts))
