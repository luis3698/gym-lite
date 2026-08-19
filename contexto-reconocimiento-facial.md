# Contexto: Mejoras al reconocimiento facial

> Bitácora de esta sesión de trabajo, mismo formato que `contexto.md` y
> `contexto-copias-y-auditoria.md`. El usuario pidió mejorar el algoritmo del
> kiosco de acceso facial en tres frentes —robustez, eficiencia y
> velocidad/"enfoque automático"— y, tras revisar a fondo el código, se le
> presentó un menú de 8 mejoras concretas encontradas en `app/faces.py`,
> `app/static/kiosk.js` y `app/static/face-enroll.js`. Las eligió todas.

## Decisiones tomadas

- **"Enfoque automático más rápido" tenía dos lecturas posibles** (el
  autofocus físico de la cámara, o que el algoritmo reconozca más rápido) y
  se resolvió ofreciendo ambas como opciones separadas en vez de adivinar.
- **Verificación empírica antes de prometer nada**: se confirmó cargando
  `/acceso/` en un navegador real que la librería vendida (`face-api.js`)
  expone `faceapi.tf.setBackend`/`getBackend`, y que **ya elegía `webgl` por
  defecto** en este entorno. Eso cambió el alcance de esa mejora: de
  "forzar" WebGL (que sonaba a garantía de velocidad) a "confirmarlo y
  avisar si cae a algo más lento" — lo real que se puede prometer.
- **Fusionar la doble detección** (antes: `detectAllFaces` + luego
  `detectSingleFace().withFaceLandmarks().withFaceDescriptor()`, corriendo
  el detector dos veces) en una sola pasada
  (`detectAllFaces().withFaceLandmarks().withFaceDescriptors()`, plural) fue
  la mejora de mayor impacto real: reduce a la mitad el costo de cómputo
  por fotograma, sin cambiar ningún umbral ni comportamiento.
- **NumPy en `app/faces.py`**: se agregó como dependencia nueva
  (`requirements.txt`) para vectorizar `best_match()`/`duplicate_owner()`.
  Se perdió el "corte anticipado" que tenía el bucle Python original
  (`_squared_distance`, abandonaba en cuanto la suma parcial ya no podía
  ganar), pero una operación vectorizada sobre toda la galería de una vez es
  varios órdenes de magnitud más rápida que un bucle Python puro incluso sin
  ese corte, así que sigue siendo una mejora neta. Costo aceptado: aumenta
  el tamaño del instalador.
- **Anti-suplantación "básica", con alcance explícito y limitado**: se
  decidió NO implementar detección de parpadeo ni de vídeo-replay en
  pantalla, porque ambas exigen observar varios segundos y chocan
  directamente con el pedido de "más rápido". Se implementó en cambio una
  comprobación de que los landmarks tengan algo de movimiento natural entre
  los fotogramas de confirmación (una foto impresa sostenida con la mano
  apenas se mueve; una cara real siempre tiene algo de movimiento
  involuntario) — cero latencia extra en el caso normal, reutiliza
  fotogramas que ya se estaban capturando. Documentado en el propio código
  qué SÍ cubre (fotos impresas) y qué NO (vídeo en una pantalla, parpadeo).
- **Los umbrales nuevos son puntos de partida sin calibrar con cámara
  real** (`MIN_LIVENESS_MOVEMENT`, `MIN_BRIGHTNESS`, `MIN_SHARPNESS`,
  `LUMA_LOW`/`LUMA_HIGH`): se verificaron con datos sintéticos (ver más
  abajo), pero solo el uso real con un kiosco físico puede decir si hacen
  falta ajustes. Es una limitación conocida y aceptada, no un olvido.

## Estado actual

**Fase: COMPLETO, verificado sin cámara real (el entorno de pruebas de este
proyecto bloquea el acceso a cámara). Pendiente de ajuste fino con hardware
real si hiciera falta.**

- [x] `app/faces.py`: galería vectorizada con NumPy
      (`_gallery()` devuelve `(ids: ndarray, matrix: ndarray de forma
      (N, 128))` en vez de una lista de tuplas). `best_match()` y
      `duplicate_owner()` reescritos para comparar contra toda la matriz de
      una vez. `requirements.txt` con `numpy>=1.26,<3.0`.
- [x] `app/static/kiosk.js`:
      - Detección + landmarks + descriptor en una sola pasada
        (`detectAllFaces().withFaceLandmarks().withFaceDescriptors()`).
        `pickSubject`, `drawBoxes`, `boxArea` adaptados a leer
        `.detection.box` de forma consistente.
      - `confirmBackend()`: confirma WebGL tras cargar los modelos, avisa
        por consola si cae a otro backend. No bloquea el arranque si la API
        cambiara de forma.
      - `advanced: [{ focusMode: 'continuous' }]` al pedir la cámara y al
        aplicar restricciones sobre el track ya abierto (mejor esfuerzo,
        extensión no estándar).
      - `CONFIRM_DISTANCE` (0.45) y `LINGER_DISTANCE` (0.50) separados,
        donde antes había un solo `SAME_PERSON_DISTANCE`.
      - `detectionSource()`: normaliza iluminación (estiramiento de niveles)
        solo cuando la luminancia media sale de la banda 60-190/255; con luz
        normal usa el `<video>` directamente, sin costo extra.
      - Vida básica: `landmarkMovement()` + `MIN_LIVENESS_MOVEMENT` (0.35) +
        `LIVENESS_MAX_EXTRA_FRAMES` (6) — nunca bloquea para siempre a
        alguien muy quieto, solo pide algún fotograma extra.
- [x] `app/static/face-enroll.js`: mismos cambios 1/2/3/7 que kiosk.js
      (detección fusionada, confirmación de WebGL, enfoque de cámara,
      normalización de luz), más `sampleQuality()` — rechaza una muestra
      demasiado oscura (`MIN_BRIGHTNESS`, 40/255) o borrosa (`MIN_SHARPNESS`,
      variancia de gradiente < 40) ANTES de aceptarla, porque una muestra de
      referencia mala arrastra reconocimientos malos para siempre.
- [x] Verificación:
      - `app/faces.py`: `best_match()`/`duplicate_owner()` vectorizados
        comparados contra un oráculo en Python puro (reimplementación de la
        lógica anterior) sobre 300 muestras y 30 casos — coinciden exacto,
        incluida la distancia con tolerancia de punto flotante. Casos límite
        (galería vacía, excluir a todos) sin reventar.
      - `kiosk.js`/`face-enroll.js`: `node --check` (sintaxis), y un script
        Node aparte con las mismas fórmulas (movimiento de landmarks,
        brillo/nitidez, estiramiento de niveles) contra datos sintéticos —
        **encontró y corrigió un error real de calibración**: el punto de
        partida de `MIN_SHARPNESS` (15) era tan bajo que ni siquiera una
        imagen claramente movida (borde difuminado en 20 px) lo disparaba;
        se subió a 40 tras medir con el propio caso sintético de prueba.
      - Navegador real (sin cámara, bloqueada por el entorno): se cargó
        `/acceso/` y la pantalla de alta de rostro de un cliente de prueba,
        se disparó `boot()`/`start()` de verdad (carga de modelos,
        `confirmBackend()`, intento de abrir cámara) y se confirmó por
        consola y por `faceapi.tf.getBackend()` que no hay errores nuevos y
        que el backend queda en `webgl`. El fallo de cámara (esperado, la
        bloquea el entorno) se mostró con el mensaje de error ya existente,
        sin romper nada.
      - Instalador recompilado con NumPy incluido (ver tamaño final en el
        registro de abajo).

## Pendiente del usuario

Nada bloqueante. Cuando haya un kiosco con cámara real, conviene observar
unos días y ajustar si hace falta:

- `MIN_LIVENESS_MOVEMENT`, `LIVENESS_MAX_EXTRA_FRAMES` (vida básica).
- `MIN_BRIGHTNESS`, `MIN_SHARPNESS` (calidad de las muestras al registrar
  un rostro).
- `LUMA_LOW`/`LUMA_HIGH` (cuándo se considera que la luz es mala).

Todos estos valores están documentados con su razón en el propio código
(`kiosk.js`, `face-enroll.js`), así que ajustarlos no exige entender de
nuevo el porqué.

## Registro

- 2026-08-19: pedido del usuario: reconocimiento facial más robusto,
  eficiente y con "enfoque automático más rápido". Presentado un menú de 8
  mejoras concretas encontradas al revisar `app/faces.py`, `kiosk.js` y
  `face-enroll.js`; el usuario las eligió todas. Implementadas y verificadas
  las 8 (ver "Estado actual"). Durante la verificación con datos sintéticos
  se encontró y corrigió un error de calibración real (`MIN_SHARPNESS`
  demasiado bajo para detectar una imagen claramente movida). Instalador
  recompilado con NumPy como nueva dependencia.
