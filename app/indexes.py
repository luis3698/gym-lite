"""Índices corporales de la ficha deportiva.

Reparto deliberado entre código y base de datos:

* **La fórmula de cada índice vive aquí**, en Python. Se planteó dejarla configurable
  y se descartó: un paréntesis mal puesto daría un dato de salud erróneo sin que nada
  avisara, y estos números se le enseñan al socio.
* **La interpretación vive en la base** (`index_ranges`), porque ahí sí hay criterio:
  los rangos cambian según el sexo, la edad y la escuela que siga cada gimnasio, y
  tienen que poder ajustarse sin tocar el programa.

Cada índice declara qué datos necesita. Si falta alguno no se calcula y se dice cuál
falta, en vez de enseñar un número calculado con huecos.
"""

from __future__ import annotations

import math
from typing import Any, Callable, NamedTuple

from .db import query_all, query_one

# --- Definición de los índices ------------------------------------------------


class BodyIndex(NamedTuple):
    code: str
    name: str
    unit: str
    # Campos del cliente que hacen falta, con su nombre legible para el aviso.
    requires: tuple[tuple[str, str], ...]
    needs_sex: bool
    compute: Callable[[dict], float | None]
    help_text: str


def _height_m(c: dict) -> float:
    return float(c["height_cm"]) / 100


def _bmi(c: dict) -> float | None:
    height = _height_m(c)
    if height <= 0:
        return None
    return float(c["weight_kg"]) / (height * height)


def _body_fat(c: dict) -> float | None:
    """Porcentaje de grasa por el método de la Marina de EE. UU. (perímetros, en cm).

    Es la estimación más fiable que se puede hacer con una cinta métrica. No sustituye
    a una báscula de bioimpedancia ni a un plicómetro, pero no necesita aparatos y su
    error habitual (±3-4 puntos) sirve de sobra para seguir la evolución de alguien.
    """
    height = float(c["height_cm"])
    neck = float(c["m_neck"])
    waist = float(c["m_waist"])
    sexo = (c.get("sex") or "").lower()

    if sexo.startswith("masc"):
        base = waist - neck
        if base <= 0 or height <= 0:
            return None
        valor = 495 / (1.0324 - 0.19077 * math.log10(base) + 0.15456 * math.log10(height)) - 450
    else:
        hip = float(c["m_hip"] or 0)
        base = waist + hip - neck
        if base <= 0 or height <= 0 or hip <= 0:
            return None
        valor = 495 / (1.29579 - 0.35004 * math.log10(base) + 0.22100 * math.log10(height)) - 450

    # Fuera de este rango la fórmula ya no describe a nadie real: casi siempre significa
    # que una medida está mal tomada, y es mejor no mostrar nada que un dato absurdo.
    return valor if 2 <= valor <= 70 else None


def _waist_hip(c: dict) -> float | None:
    hip = float(c["m_hip"])
    return float(c["m_waist"]) / hip if hip > 0 else None


def _waist_height(c: dict) -> float | None:
    height = float(c["height_cm"])
    return float(c["m_waist"]) / height if height > 0 else None


INDEXES: tuple[BodyIndex, ...] = (
    BodyIndex(
        "IMC", "Índice de masa corporal", "",
        (("height_cm", "altura"), ("weight_kg", "peso")),
        False, _bmi,
        "Relaciona peso y altura. No distingue músculo de grasa: un socio muy "
        "musculado puede salir como «sobrepeso» estando perfectamente.",
    ),
    BodyIndex(
        "GRASA", "Porcentaje de grasa corporal", "%",
        (("height_cm", "altura"), ("m_neck", "perímetro de cuello"),
         ("m_waist", "perímetro de cintura")),
        True, _body_fat,
        "Estimación por perímetros (método de la Marina de EE. UU.). En mujeres "
        "necesita además el perímetro de cadera.",
    ),
    BodyIndex(
        "ICC", "Índice cintura/cadera", "",
        (("m_waist", "perímetro de cintura"), ("m_hip", "perímetro de cadera")),
        False, _waist_hip,
        "Indica dónde se acumula la grasa. La abdominal es la que más se asocia a "
        "riesgo cardiovascular.",
    ),
    BodyIndex(
        "ICE", "Índice cintura/estatura", "",
        (("m_waist", "perímetro de cintura"), ("height_cm", "altura")),
        False, _waist_height,
        "Regla sencilla: la cintura debería medir menos de la mitad que la estatura.",
    ),
)

INDEX_BY_CODE = {i.code: i for i in INDEXES}


# --- Rangos por defecto -------------------------------------------------------
# (sexo, edad_min, edad_max, min, max, etiqueta, gravedad)
# `None` en sexo o edades significa «vale para cualquiera». Los intervalos son
# [min, max), así que dos filas seguidas encajan sin huecos ni solapes.

DEFAULT_RANGES: dict[str, tuple[tuple, ...]] = {
    # Clasificación por sexo (fuente: Tabla_IMC_Sexo_Edad.xlsx, ficha de referencia
    # calculada sobre una estatura promedio de 1,75 m). La tabla trae la misma franja
    # de edad (18-59) en TODAS las filas sin excepción, así que no aporta ninguna
    # distinción real entre filas: codificarla habría dejado sin clasificar a
    # cualquier cliente fuera de ese rango (o sin edad registrada) en vez de sumar
    # precisión, así que se omite a propósito y los rangos quedan válidos para
    # cualquier edad, igual que antes.
    #
    # La columna "General" de la fuente coincide con el corte estándar de la OMS (el
    # valor por defecto que ya tenía este programa) y queda como fila sin sexo: cubre
    # a quien no tiene sexo registrado o lo tiene como "Otro". Las filas de
    # Masculino/Femenino son más específicas y ganan sobre esa por `_specificity()`.
    "IMC": (
        (None, None, None, None, 18.5, "Bajo peso", "warn"),
        (None, None, None, 18.5, 25.0, "Peso normal", "ok"),
        (None, None, None, 25.0, 30.0, "Sobrepeso", "warn"),
        (None, None, None, 30.0, 35.0, "Obesidad grado I", "bad"),
        (None, None, None, 35.0, 40.0, "Obesidad grado II", "bad"),
        (None, None, None, 40.0, None, "Obesidad grado III", "bad"),
        ("Masculino", None, None, None, 20.0, "Bajo peso", "warn"),
        ("Masculino", None, None, 20.0, 25.0, "Peso normal", "ok"),
        ("Masculino", None, None, 25.0, 30.0, "Sobrepeso", "warn"),
        ("Masculino", None, None, 30.0, 35.0, "Obesidad grado I", "bad"),
        ("Masculino", None, None, 35.0, 40.0, "Obesidad grado II", "bad"),
        ("Masculino", None, None, 40.0, None, "Obesidad grado III", "bad"),
        ("Femenino", None, None, None, 18.5, "Bajo peso", "warn"),
        ("Femenino", None, None, 18.5, 24.0, "Peso normal", "ok"),
        ("Femenino", None, None, 24.0, 29.0, "Sobrepeso", "warn"),
        ("Femenino", None, None, 29.0, 34.0, "Obesidad grado I", "bad"),
        ("Femenino", None, None, 34.0, 39.0, "Obesidad grado II", "bad"),
        ("Femenino", None, None, 39.0, None, "Obesidad grado III", "bad"),
    ),
    "GRASA": (
        ("Masculino", None, None, None, 6.0, "Grasa esencial", "warn"),
        ("Masculino", None, None, 6.0, 14.0, "Atlético", "ok"),
        ("Masculino", None, None, 14.0, 18.0, "En forma", "ok"),
        ("Masculino", None, None, 18.0, 25.0, "Aceptable", "ok"),
        ("Masculino", None, None, 25.0, None, "Obesidad", "bad"),
        ("Femenino", None, None, None, 14.0, "Grasa esencial", "warn"),
        ("Femenino", None, None, 14.0, 21.0, "Atlético", "ok"),
        ("Femenino", None, None, 21.0, 25.0, "En forma", "ok"),
        ("Femenino", None, None, 25.0, 32.0, "Aceptable", "ok"),
        ("Femenino", None, None, 32.0, None, "Obesidad", "bad"),
    ),
    "ICC": (
        ("Masculino", None, None, None, 0.90, "Riesgo bajo", "ok"),
        ("Masculino", None, None, 0.90, 1.00, "Riesgo moderado", "warn"),
        ("Masculino", None, None, 1.00, None, "Riesgo alto", "bad"),
        ("Femenino", None, None, None, 0.80, "Riesgo bajo", "ok"),
        ("Femenino", None, None, 0.80, 0.85, "Riesgo moderado", "warn"),
        ("Femenino", None, None, 0.85, None, "Riesgo alto", "bad"),
    ),
    "ICE": (
        (None, None, None, None, 0.40, "Por debajo de lo habitual", "warn"),
        (None, None, None, 0.40, 0.50, "Saludable", "ok"),
        (None, None, None, 0.50, 0.60, "Riesgo aumentado", "warn"),
        (None, None, None, 0.60, None, "Riesgo alto", "bad"),
    ),
}


def ensure_defaults() -> None:
    """Carga índices y rangos si aún no existen. Idempotente.

    Se ejecuta al arrancar para que una base recién creada —o una que viene de una
    versión anterior— llegue con la matriz ya cargada y utilizable.
    """
    from .db import execute

    for order, definition in enumerate(INDEXES):
        existe = query_one("SELECT 1 FROM body_indexes WHERE code = ?", (definition.code,))
        if not existe:
            execute(
                "INSERT INTO body_indexes (code, name, enabled, sort_order) VALUES (?, ?, 1, ?)",
                (definition.code, definition.name, order),
            )
        # Los rangos solo se siembran si el índice no tiene ninguno: si el gimnasio los
        # borró todos a propósito, no deben reaparecer en el siguiente arranque.
        tiene = query_one("SELECT 1 FROM index_ranges WHERE index_code = ?", (definition.code,))
        if not tiene:
            restore_defaults(definition.code)


def restore_defaults(code: str) -> None:
    """Deja los rangos de un índice como vienen de fábrica."""
    from .db import execute, insert

    execute("DELETE FROM index_ranges WHERE index_code = ?", (code,))
    for order, fila in enumerate(DEFAULT_RANGES.get(code, ())):
        sexo, edad_min, edad_max, minimo, maximo, etiqueta, gravedad = fila
        insert(
            """INSERT INTO index_ranges (index_code, sex, age_min, age_max, min_value,
                                         max_value, label, severity, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, sexo, edad_min, edad_max, minimo, maximo, etiqueta, gravedad, order),
        )


# --- Clasificación ------------------------------------------------------------


def _specificity(row) -> int:
    """Cuánto acota una fila. Gana la más específica cuando varias encajan.

    Así se puede tener un rango general y poner excepciones encima para un sexo o una
    franja de edad, sin tener que repetir la tabla entera.
    """
    score = 0
    if row["sex"]:
        score += 2
    if row["age_min"] is not None or row["age_max"] is not None:
        score += 1
    return score


def classify(code: str, value: float, sex: str | None, age: int | None) -> tuple[str, str]:
    """Etiqueta y gravedad de un valor. ('', '') si ninguna fila lo cubre."""
    candidatas = []
    for row in query_all(
        "SELECT * FROM index_ranges WHERE index_code = ? ORDER BY sort_order, id", (code,)
    ):
        if row["sex"] and row["sex"] != sex:
            continue
        if row["age_min"] is not None and (age is None or age < row["age_min"]):
            continue
        if row["age_max"] is not None and (age is None or age > row["age_max"]):
            continue
        if row["min_value"] is not None and value < row["min_value"]:
            continue
        if row["max_value"] is not None and value >= row["max_value"]:
            continue
        candidatas.append(row)

    if not candidatas:
        return "", ""
    mejor = max(candidatas, key=_specificity)
    return mejor["label"], mejor["severity"]


# --- Cálculo para una ficha ---------------------------------------------------


def _missing(definition: BodyIndex, client: dict) -> list[str]:
    faltan = [
        etiqueta for campo, etiqueta in definition.requires
        if not client.get(campo)
    ]
    sexo = (client.get("sex") or "").lower()
    if definition.needs_sex and not sexo.startswith(("masc", "feme")):
        faltan.append("sexo (masculino o femenino)")
    # La fórmula femenina necesita además la cadera.
    if definition.code == "GRASA" and sexo.startswith("feme") and not client.get("m_hip"):
        faltan.append("perímetro de cadera")
    return faltan


def compute_for_client(client: Any) -> list[dict]:
    """Índices activos calculados para un cliente.

    Devuelve también los que no se pudieron calcular, indicando qué falta: así la ficha
    puede invitar a completar el dato en vez de callarse.
    """
    datos = dict(client)
    sexo = datos.get("sex")
    edad = datos.get("age")

    resultados: list[dict] = []
    for row in query_all("SELECT * FROM body_indexes WHERE enabled = 1 ORDER BY sort_order, code"):
        definition = INDEX_BY_CODE.get(row["code"])
        if definition is None:
            continue

        faltan = _missing(definition, datos)
        if faltan:
            resultados.append({
                "code": definition.code, "name": row["name"], "unit": definition.unit,
                "value": None, "label": "", "severity": "", "missing": faltan,
                "help": definition.help_text,
            })
            continue

        try:
            valor = definition.compute(datos)
        except (TypeError, ValueError, ZeroDivisionError):
            valor = None

        if valor is None or valor != valor or math.isinf(valor):
            resultados.append({
                "code": definition.code, "name": row["name"], "unit": definition.unit,
                "value": None, "label": "", "severity": "",
                "missing": ["medidas coherentes (revise los perímetros)"],
                "help": definition.help_text,
            })
            continue

        valor = round(valor, 2)
        etiqueta, gravedad = classify(definition.code, valor, sexo, edad)
        resultados.append({
            "code": definition.code, "name": row["name"], "unit": definition.unit,
            "value": valor, "label": etiqueta, "severity": gravedad, "missing": [],
            "help": definition.help_text,
        })
    return resultados
