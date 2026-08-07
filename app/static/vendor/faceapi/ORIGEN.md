# face-api (copia local)

Motor de reconocimiento facial que usa el kiosco de acceso. Se guarda dentro del
proyecto a propósito: el programa tiene que funcionar **sin internet**, así que ni la
librería ni los pesos pueden venir de un CDN.

| Dato | Valor |
|---|---|
| Paquete | `@vladmandic/face-api` |
| Versión | 1.7.15 |
| Origen | <https://cdn.jsdelivr.net/npm/@vladmandic/face-api@1.7.15> |
| Licencia | MIT (ver `LICENSE`) |

## Qué hay aquí

| Archivo | Tamaño | Para qué |
|---|---|---|
| `face-api.js` | 1,3 MB | Librería completa (incluye TensorFlow.js). Expone `window.faceapi`. |
| `models/tiny_face_detector_model.*` | 193 KB | Detecta *dónde* hay caras. Rápido, sirve para vídeo en vivo. |
| `models/face_landmark_68_model.*` | 357 KB | 68 puntos del rostro; alinea la cara antes de describirla. |
| `models/face_recognition_model.*` | 6,4 MB | Convierte el rostro en 128 números (el «descriptor»). |

Cada modelo son dos archivos: el `.bin` con los pesos y el
`-weights_manifest.json` que los describe. El manifiesto nombra al `.bin` por ruta
relativa, así que **los dos tienen que estar en la misma carpeta**.

Los modelos de edad, expresión y `ssd_mobilenetv1` que trae el paquete no se
descargaron: no se usan y sumaban unos 20 MB al instalador.

## Actualizar

Descargar de nuevo esos ocho archivos de la misma ruta del CDN cambiando la versión.
No hay que tocar código salvo que cambie la API.
