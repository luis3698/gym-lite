"""Genera assets/gymlite.ico sin dependencias externas.

Se dibuja a mano (PNG + ICO escritos con zlib y struct) para no obligar a instalar
Pillow solo por el icono. El dibujo es una mancuerna blanca sobre un cuadrado
redondeado con el degradado índigo de la aplicación.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICON_PATH = ASSETS_DIR / "gymlite.ico"

SIZES = (16, 24, 32, 48, 64, 128, 256)
SUPERSAMPLE = 3  # 3x3 muestras por píxel: suficiente para un borde limpio

INDIGO = (79, 70, 229)
INDIGO_DARK = (49, 46, 129)
WHITE = (255, 255, 255)


# --- Geometría ---------------------------------------------------------------
# Todas las formas se describen en coordenadas 0..1 para poder rasterizarlas a
# cualquier tamaño.


def _rounded_rect(x: float, y: float, x0: float, y0: float, x1: float, y1: float, r: float) -> bool:
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    # Esquinas: fuera del círculo de radio r centrado en la esquina interior.
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _background(x: float, y: float) -> bool:
    return _rounded_rect(x, y, 0.02, 0.02, 0.98, 0.98, 0.22)


def _dumbbell(x: float, y: float) -> bool:
    # Barra central.
    if _rounded_rect(x, y, 0.30, 0.455, 0.70, 0.545, 0.03):
        return True
    # Discos interiores (los grandes).
    if _rounded_rect(x, y, 0.215, 0.325, 0.325, 0.675, 0.045):
        return True
    if _rounded_rect(x, y, 0.675, 0.325, 0.785, 0.675, 0.045):
        return True
    # Discos exteriores (los pequeños).
    if _rounded_rect(x, y, 0.125, 0.395, 0.205, 0.605, 0.035):
        return True
    if _rounded_rect(x, y, 0.795, 0.395, 0.875, 0.605, 0.035):
        return True
    return False


def _gradient(t: float) -> tuple[int, int, int]:
    """Índigo arriba, índigo oscuro abajo."""
    return tuple(round(a + (b - a) * t) for a, b in zip(INDIGO, INDIGO_DARK))  # type: ignore[return-value]


def _render(size: int) -> bytes:
    """Devuelve los píxeles RGBA de un icono de `size` x `size`."""
    out = bytearray()
    step = 1.0 / (size * SUPERSAMPLE)
    samples = SUPERSAMPLE * SUPERSAMPLE

    for py in range(size):
        for px in range(size):
            inside_bg = 0
            inside_fg = 0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    x = (px * SUPERSAMPLE + sx + 0.5) * step
                    y = (py * SUPERSAMPLE + sy + 0.5) * step
                    if _background(x, y):
                        inside_bg += 1
                        if _dumbbell(x, y):
                            inside_fg += 1

            if inside_bg == 0:
                out += b"\x00\x00\x00\x00"
                continue

            base = _gradient((py + 0.5) / size)
            fg_ratio = inside_fg / samples
            bg_ratio = inside_bg / samples
            # Mezcla del blanco de la mancuerna sobre el fondo, ponderada por la
            # cobertura de cada forma dentro del píxel.
            colour = tuple(
                round(c + (w - c) * (fg_ratio / bg_ratio)) for c, w in zip(base, WHITE)
            )
            out += bytes(colour) + bytes((round(255 * bg_ratio),))
    return bytes(out)


# --- Codificación ------------------------------------------------------------


def _png(size: int, pixels: bytes) -> bytes:
    stride = size * 4
    raw = b"".join(b"\x00" + pixels[y * stride:(y + 1) * stride] for y in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def build_png(size: int, path: Path) -> Path:
    """PNG suelto del mismo dibujo, para mostrarlo dentro del asistente (Tk)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png(size, _render(size)))
    return path


def build_icon(path: Path = ICON_PATH) -> Path:
    frames = [(size, _png(size, _render(size))) for size in SIZES]

    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(header) + 16 * len(frames)
    entries = bytearray()
    payload = bytearray()
    for size, data in frames:
        # En el formato ICO, 0 significa 256.
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + bytes(entries) + bytes(payload))
    return path


if __name__ == "__main__":
    print(f"Icono generado: {build_icon()}")
    print(f"Logo generado:  {build_png(96, ASSETS_DIR / 'gymlite-96.png')}")
