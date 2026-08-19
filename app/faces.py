"""Emparejamiento de rostros para el kiosco de acceso.

Quien ve la cámara es el navegador: allí se detecta el rostro y se convierte en un
vector de 128 números en coma flotante, el «descriptor». Aquí solo se comparan
números. La galería de rostros del gimnasio **nunca** se envía al navegador, ni
siquiera al del propio kiosco: lo único que viaja de vuelta son los datos de la
persona que se acaba de identificar.

Comparar dos rostros es medir la distancia euclídea entre sus descriptores: cuanto
menor, más se parecen. No hay nada que entrenar; el modelo ya viene entrenado y estos
128 números son su salida.
"""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from .config import (
    FACE_DESCRIPTOR_LENGTH,
    FACE_MATCH_THRESHOLD,
    FACE_UNCERTAIN_THRESHOLD,
)
from .db import query_all, query_one


class InvalidDescriptor(ValueError):
    """El descriptor recibido no tiene la forma esperada."""


# El descriptor sale de una red neuronal y sus valores se mueven en torno a [-1, 1].
# El tope no busca precisión, solo descartar payloads absurdos: este endpoint se
# atiende sin sesión iniciada y no debe fiarse de nada que llegue por la red.
_MAX_ABS_VALUE = 10.0


def parse_descriptor(raw: Any) -> list[float]:
    """Valida un descriptor recibido del navegador y lo devuelve como lista de float."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise InvalidDescriptor("El descriptor no es JSON válido.") from None

    if not isinstance(raw, (list, tuple)):
        raise InvalidDescriptor("El descriptor debe ser una lista de números.")
    if len(raw) != FACE_DESCRIPTOR_LENGTH:
        raise InvalidDescriptor(
            f"El descriptor debe tener {FACE_DESCRIPTOR_LENGTH} valores, llegaron {len(raw)}."
        )

    values: list[float] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise InvalidDescriptor("El descriptor contiene valores que no son números.")
        number = float(item)
        # NaN e infinito envenenarían la comparación: NaN hace que todas las
        # desigualdades sean falsas y la persona nunca emparejaría con nadie.
        if math.isnan(number) or math.isinf(number) or abs(number) > _MAX_ABS_VALUE:
            raise InvalidDescriptor("El descriptor contiene valores fuera de rango.")
        values.append(number)
    return values


def serialize_descriptor(values: list[float]) -> str:
    """Guarda con 6 decimales: más precisión no cambia el resultado y triplica el texto."""
    return json.dumps([round(v, 6) for v in values])


# --- Galería en memoria -------------------------------------------------------
# Releer y volver a interpretar el JSON de cada rostro en cada fotograma es el coste
# dominante del kiosco. Se guarda ya interpretada —y ya apilada en una matriz de
# NumPy— y se comprueba con una consulta barata si cambió (alta o baja de rostros)
# antes de reutilizarla.
#
# El servidor atiende varias peticiones a la vez; en el peor caso dos hilos
# reconstruyen la misma galería y uno pisa al otro con un valor idéntico. Es
# inofensivo, así que no hace falta un cerrojo.

# (ids: vector de client_id, shape (N,)) y (matrix: una fila de 128 valores por
# muestra, shape (N, FACE_DESCRIPTOR_LENGTH)) — mismo orden en ambos.
_Gallery = tuple["np.ndarray", "np.ndarray"]
_gallery_cache: tuple[tuple[int, int], _Gallery] | None = None


def invalidate_gallery() -> None:
    """Fuerza la recarga. Se llama al registrar o borrar un rostro."""
    global _gallery_cache
    _gallery_cache = None


def _gallery() -> _Gallery:
    global _gallery_cache

    stamp_row = query_one("SELECT COUNT(*) AS total, COALESCE(MAX(id), 0) AS last_id FROM client_faces")
    stamp = (stamp_row["total"], stamp_row["last_id"]) if stamp_row else (0, 0)

    cached = _gallery_cache
    if cached is not None and cached[0] == stamp:
        return cached[1]

    ids: list[int] = []
    vectors: list[list[float]] = []
    for row in query_all("SELECT client_id, descriptor FROM client_faces"):
        try:
            values = parse_descriptor(row["descriptor"])
        except InvalidDescriptor:
            # Una fila corrupta no puede tumbar el kiosco entero: se ignora y el
            # resto de la galería sigue sirviendo.
            continue
        ids.append(row["client_id"])
        vectors.append(values)

    id_array = np.asarray(ids, dtype=np.int64)
    # Forma explícita (N, 128) incluso con N=0: dejar que NumPy infiera la forma de
    # una lista vacía da (0,), no (0, 128), y entonces las comparaciones de más
    # abajo fallarían por incompatibilidad de dimensiones.
    matrix = (
        np.asarray(vectors, dtype=np.float64)
        if vectors
        else np.empty((0, FACE_DESCRIPTOR_LENGTH), dtype=np.float64)
    )

    data = (id_array, matrix)
    _gallery_cache = (stamp, data)
    return data


# --- Comparación --------------------------------------------------------------
# Comparar contra la galería entera es una resta y una suma vectorizadas sobre
# toda la matriz de una vez (NumPy), no un bucle en Python muestra por muestra:
# con cientos o miles de rostros registrados, es varios órdenes de magnitud más
# rápido que compararlos uno por uno, que es como funcionaba antes.


def best_match(descriptor: list[float]) -> tuple[int | None, float | None]:
    """Cliente más parecido de toda la galería y su distancia (None si no hay rostros)."""
    ids, matrix = _gallery()
    if matrix.shape[0] == 0:
        return None, None

    diffs = matrix - np.asarray(descriptor, dtype=np.float64)
    squared = np.sum(diffs * diffs, axis=1)
    idx = int(np.argmin(squared))
    return int(ids[idx]), float(math.sqrt(squared[idx]))


def classify(distance: float | None) -> str:
    """'match' | 'uncertain' | 'unknown' a partir de la distancia.

    La franja intermedia existe a propósito: un parecido «casi bueno» no se resuelve
    adivinando, se le pide a la persona que se acerque. Enseñar la ficha de otro
    cliente es un error mucho más caro que pedir un segundo intento.
    """
    if distance is None:
        return "unknown"
    if distance <= FACE_MATCH_THRESHOLD:
        return "match"
    if distance <= FACE_UNCERTAIN_THRESHOLD:
        return "uncertain"
    return "unknown"


# --- Altas y bajas ------------------------------------------------------------


def client_face_count(client_id: int) -> int:
    return int(query_one(
        "SELECT COUNT(*) AS total FROM client_faces WHERE client_id = ?", (client_id,)
    )["total"])


def duplicate_owner(descriptor: list[float], *, exclude_client_id: int) -> int | None:
    """Otro cliente cuyo rostro ya se parece demasiado a este.

    Sin esta comprobación, registrar por error el rostro de Ana en la ficha de Beatriz
    deja el sistema dando entrada a la persona equivocada, y el fallo solo se
    descubre cuando alguien mira el histórico.
    """
    ids, matrix = _gallery()
    mask = ids != exclude_client_id
    if not mask.any():
        return None

    other_ids = ids[mask]
    diffs = matrix[mask] - np.asarray(descriptor, dtype=np.float64)
    squared = np.sum(diffs * diffs, axis=1)
    idx = int(np.argmin(squared))
    if squared[idx] <= FACE_MATCH_THRESHOLD ** 2:
        return int(other_ids[idx])
    return None
