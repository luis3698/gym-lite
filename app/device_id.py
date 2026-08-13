"""Huella del equipo, para atar una licencia a la máquina donde se activó.

Combina tres señales de Windows en un único hash: el MachineGuid (identificador
estable que Windows genera al instalarse), el número de serie del disco donde vive
el sistema y el nombre del equipo. Ninguna por separado basta —el MachineGuid se
puede editar a mano en el registro, el nombre de equipo se cambia desde el panel de
control—, pero las tres juntas hacen que clonar una licencia a otra máquina exija
falsificar deliberadamente varias señales distintas, no solo copiar un archivo.

Solo el HASH sale de aquí: los valores crudos no se guardan en disco ni se envían a
ningún sitio, así que un archivo de licencia filtrado no revela hardware real.

Reformatear el disco del sistema cambia el número de serie y por tanto la huella:
es la contrapartida de incluirlo. El camino de vuelta para ese caso legítimo es
`vendor_tools/licensing_cli.py unbind`, no un mecanismo automático aquí.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import winreg

_cached: str | None = None


def _machine_guid() -> str:
    """MachineGuid de Windows: se genera una vez al instalar el sistema operativo."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except OSError:
        # No debería faltar en un Windows real, pero si falla no puede tumbar el
        # programa: la huella sigue siendo útil con las otras dos señales.
        return ""


def _volume_serial(drive: str = "C:\\") -> str:
    """Número de serie del volumen del sistema. Cambia si se reformatea el disco."""
    try:
        serial = ctypes.c_uint32(0)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(drive), None, 0,
            ctypes.byref(serial), None, None, None, 0,
        )
        return f"{serial.value:08X}" if ok else ""
    except OSError:
        return ""


def _computer_name() -> str:
    return os.environ.get("COMPUTERNAME", "")


def compute_device_fingerprint() -> str:
    """Huella cruda (sin cachear), para pruebas y para invalidar la caché a mano."""
    partes = "|".join((_machine_guid(), _volume_serial(), _computer_name()))
    return hashlib.sha256(partes.encode("utf-8")).hexdigest()


def device_fingerprint_hash() -> str:
    """Huella del equipo, cacheada en memoria durante la vida del proceso.

    Leer el registro y consultar el volumen no cambia mientras el programa está
    corriendo, así que no tiene sentido repetir el trabajo en cada petición.
    """
    global _cached
    if _cached is None:
        _cached = compute_device_fingerprint()
    return _cached
