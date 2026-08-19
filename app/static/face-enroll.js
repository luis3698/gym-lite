/* Registro del rostro de un cliente durante la inscripción.
 *
 * Un solo botón toma las muestras que falten, seguidas, guiando al cliente entre una
 * y otra. No se pide un clic por muestra: quien atiende el mostrador está a la vez
 * cobrando, y una tarea de cinco clics acaba haciéndose a medias —con lo que el
 * kiosco reconoce mal y nadie sabe por qué—.
 *
 * La calidad de lo que se guarda aquí decide si el kiosco acierta después, así que
 * ninguna muestra se acepta hasta que la imagen cumple unos mínimos, y en pantalla se
 * dice en cada momento qué falta para llegar a ellos.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-face-enroll]');
  if (!root) return;

  var CFG = {
    CHECK_MS: 200,
    INPUT_SIZE: 320,
    SCORE_MIN: 0.5,

    // Para dar de alta se exige más cerca que para reconocer: estas muestras son la
    // referencia de todas las comparaciones futuras.
    MIN_FACE_RATIO: 0.22,

    // Fotogramas seguidos que deben cumplir todo antes de aceptar una muestra.
    STABLE_FRAMES: 3,

    // Dos muestras casi idénticas no aportan nada: la segunda no cubre ningún caso
    // que la primera no cubriera ya. Se exige una diferencia mínima.
    MIN_VARIATION: 0.06,

    // Si el cliente se queda quieto, se acepta igualmente pasado este tiempo en vez
    // de esperar indefinidamente a una variación que no va a llegar.
    VARIATION_TIMEOUT_MS: 4000,

    // Pausa entre muestras, para que dé tiempo a leer la indicación y moverse.
    BETWEEN_MS: 900,

    // -- Calidad de la muestra -------------------------------------------------
    // Una muestra de referencia mala arrastra reconocimientos malos para siempre:
    // es contra lo que se compara todo el futuro de ese cliente. Se mide sobre un
    // recorte pequeño (60x60) de la cara, así que es barato y se calcula solo sobre
    // fotogramas que ya pasaron los demás filtros.
    // Luminancia media (0-255) mínima aceptable.
    MIN_BRIGHTNESS: 40,
    // Varianza de un gradiente simple; valores bajos indican imagen movida o
    // desenfocada. Con un borde nítido de prueba (transición abrupta) esta fórmula
    // da varianzas del orden de cientos; el mismo borde difuminado en ~20 píxeles
    // (una foto claramente movida) cae a apenas unas decenas — por eso el punto de
    // partida se deja bajo respecto a lo que da una imagen nítida real, para no
    // rechazar de más antes de calibrarlo con cámaras reales.
    MIN_SHARPNESS: 40,

    // Luminancia (0-255) fuera de la cual se corrige el fotograma antes de detectar.
    LUMA_LOW: 60,
    LUMA_HIGH: 190
  };

  /* Cada muestra pide una pose distinta. La red reconoce mejor de frente, así que las
     variaciones son suaves: lo que se busca es cubrir la luz y el ángulo del día a
     día, no rostros de perfil que después no casarían. */
  var POSES = [
    { texto: 'Mire de frente a la cámara.', maxYaw: 1.8 },
    { texto: 'Gire la cabeza un poco a su derecha.', maxYaw: 2.6 },
    { texto: 'Gire la cabeza un poco a su izquierda.', maxYaw: 2.6 },
    { texto: 'Levante ligeramente la barbilla.', maxYaw: 2.2 },
    { texto: 'Otra vez de frente, con expresión neutra.', maxYaw: 1.8 }
  ];

  var el = {
    form: root.querySelector('[data-face-form]'),
    input: root.querySelector('[data-face-input]'),
    video: root.querySelector('[data-face-video]'),
    overlay: root.querySelector('[data-face-overlay]'),
    hint: root.querySelector('[data-face-hint]'),
    pose: root.querySelector('[data-face-pose]'),
    progress: root.querySelector('[data-face-progress]'),
    bar: root.querySelector('[data-face-bar]'),
    error: root.querySelector('[data-face-error]'),
    start: root.querySelector('[data-face-action="start"]'),
    steps: {
      idle: root.querySelector('[data-face-step="idle"]'),
      camera: root.querySelector('[data-face-step="camera"]')
    }
  };

  var objetivo = parseInt(root.dataset.pending, 10) || 0;

  var state = {
    stream: null,
    timer: null,
    busy: false,
    options: null,
    loaded: false,
    stable: 0,
    capturadas: [],
    indice: 0,
    esperandoDesde: 0,
    pausa: false
  };

  // --- Presentación --------------------------------------------------------

  function showStep(name) {
    Object.keys(el.steps).forEach(function (key) {
      el.steps[key].hidden = key !== name;
    });
  }

  function fail(mensaje) {
    el.error.textContent = mensaje;
    el.error.hidden = false;
  }

  function hint(texto, listo) {
    el.hint.textContent = texto;
    el.hint.className = listo ? 'flash success' : 'notice';
  }

  function progreso() {
    var hechas = state.capturadas.length;
    el.progress.textContent = 'Muestra ' + Math.min(hechas + 1, objetivo) + ' de ' + objetivo;
    el.bar.style.width = Math.round((hechas / objetivo) * 100) + '%';
    el.pose.textContent = POSES[state.indice % POSES.length].texto;
  }

  // --- Cámara --------------------------------------------------------------

  function stopCamera() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    if (state.stream) {
      state.stream.getTracks().forEach(function (t) { t.stop(); });
      state.stream = null;
    }
    el.video.srcObject = null;
    state.stable = 0;
  }

  function confirmBackend() {
    // Confirma que tfjs use WebGL (GPU) en vez de caer a un modo más lento (CPU/WASM)
    // sin que nadie lo note. Todo detrás de comprobaciones de existencia: si la
    // librería cambiara de forma, esto simplemente no hace nada.
    if (!faceapi.tf || !faceapi.tf.setBackend) return null;
    return faceapi.tf.setBackend('webgl')
      .catch(function () {})
      .then(function () {
        return faceapi.tf.ready ? faceapi.tf.ready() : null;
      })
      .then(function () {
        if (faceapi.tf.getBackend && faceapi.tf.getBackend() !== 'webgl') {
          console.warn('[rostro] usando backend "' + faceapi.tf.getBackend() + '" (más lento que webgl)');
        }
      })
      .catch(function () {});
  }

  function loadModels() {
    if (state.loaded) return Promise.resolve();
    hint('Cargando el motor de reconocimiento…', false);
    return Promise.all([
      faceapi.nets.tinyFaceDetector.loadFromUri(root.dataset.modelsUrl),
      faceapi.nets.faceLandmark68Net.loadFromUri(root.dataset.modelsUrl),
      faceapi.nets.faceRecognitionNet.loadFromUri(root.dataset.modelsUrl)
    ]).then(confirmBackend).then(function () {
      state.options = new faceapi.TinyFaceDetectorOptions({
        inputSize: CFG.INPUT_SIZE,
        scoreThreshold: CFG.SCORE_MIN
      });
      state.loaded = true;
    });
  }

  function start() {
    el.error.hidden = true;
    state.capturadas = [];
    state.indice = 0;
    state.stable = 0;
    state.pausa = false;
    state.esperandoDesde = Date.now();
    showStep('camera');
    progreso();
    hint('Iniciando la cámara…', false);

    loadModels()
      .then(function () {
        return navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 720 }, height: { ideal: 720 }, facingMode: 'user',
            // Enfoque automático continuo, mejor esfuerzo (ver kiosk.js): una clave
            // no reconocida dentro de `advanced` se ignora sin error.
            advanced: [{ focusMode: 'continuous' }]
          }
        });
      })
      .then(function (stream) {
        state.stream = stream;
        el.video.srcObject = stream;

        var videoTrack = stream.getVideoTracks()[0];
        if (videoTrack && videoTrack.applyConstraints) {
          videoTrack.applyConstraints({ advanced: [{ focusMode: 'continuous' }] }).catch(function () {});
        }

        return el.video.play();
      })
      .then(function () {
        state.timer = setInterval(check, CFG.CHECK_MS);
      })
      .catch(function (err) {
        stopCamera();
        showStep('idle');
        if (err && err.name === 'NotAllowedError') {
          fail('El navegador bloqueó la cámara. Permita el acceso y vuelva a intentarlo.');
        } else if (err && err.name === 'NotFoundError') {
          fail('No se encontró ninguna cámara conectada.');
        } else if (err && err.name === 'NotReadableError') {
          fail('Otro programa está usando la cámara. Ciérrelo e intente de nuevo.');
        } else {
          fail('No se pudo iniciar la cámara: ' + (err && err.message ? err.message : err));
        }
      });
  }

  function cancel() {
    stopCamera();
    showStep('idle');
    el.error.hidden = true;
  }

  // --- Comprobación de calidad ---------------------------------------------

  function distancia(a, b) {
    var total = 0;
    for (var i = 0; i < a.length; i++) { var d = a[i] - b[i]; total += d * d; }
    return Math.sqrt(total);
  }

  function centro(puntos) {
    var s = puntos.reduce(function (acc, p) { return { x: acc.x + p.x, y: acc.y + p.y }; }, { x: 0, y: 0 });
    return { x: s.x / puntos.length, y: s.y / puntos.length };
  }

  function desvioLateral(landmarks) {
    /* Cuánto está girada la cabeza, comparando la distancia de la nariz a cada ojo.
       1 es perfectamente de frente; cuanto mayor, más girada. */
    try {
      var izq = centro(landmarks.getLeftEye());
      var der = centro(landmarks.getRightEye());
      var nariz = centro(landmarks.getNose());
      var di = Math.abs(nariz.x - izq.x);
      var dd = Math.abs(nariz.x - der.x);
      if (di === 0 || dd === 0) return 1;
      return di > dd ? di / dd : dd / di;
    } catch (e) {
      return 1;  // si los puntos no vienen, no se bloquea por esto
    }
  }

  // --- Normalización de iluminación -----------------------------------------
  // Mismo criterio que en el kiosco (kiosk.js): con luz normal casi no cuesta nada;
  // el estiramiento de niveles solo se paga cuando la luz de verdad es mala.

  var lumaBuffer = document.createElement('canvas');
  lumaBuffer.width = 80;
  lumaBuffer.height = 45;
  var fullBuffer = document.createElement('canvas');

  function clampByte(v) {
    return v < 0 ? 0 : (v > 255 ? 255 : v);
  }

  function averageLuma(ctx, w, h) {
    var data = ctx.getImageData(0, 0, w, h).data;
    var total = 0;
    var count = data.length / 4;
    for (var i = 0; i < data.length; i += 4) {
      total += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    }
    return total / count;
  }

  function detectionSource() {
    if (!el.video.videoWidth) return el.video;

    var lumaCtx = lumaBuffer.getContext('2d');
    lumaCtx.drawImage(el.video, 0, 0, lumaBuffer.width, lumaBuffer.height);
    var luma = averageLuma(lumaCtx, lumaBuffer.width, lumaBuffer.height);
    if (luma >= CFG.LUMA_LOW && luma <= CFG.LUMA_HIGH) return el.video;

    var w = el.video.videoWidth, h = el.video.videoHeight;
    if (fullBuffer.width !== w || fullBuffer.height !== h) {
      fullBuffer.width = w;
      fullBuffer.height = h;
    }
    var ctx = fullBuffer.getContext('2d');
    ctx.drawImage(el.video, 0, 0, w, h);
    var img = ctx.getImageData(0, 0, w, h);
    var d = img.data;
    var lo = 255, hi = 0;
    for (var i = 0; i < d.length; i += 4) {
      var v = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    var range = Math.max(1, hi - lo);
    for (var j = 0; j < d.length; j += 4) {
      d[j] = clampByte((d[j] - lo) * 255 / range);
      d[j + 1] = clampByte((d[j + 1] - lo) * 255 / range);
      d[j + 2] = clampByte((d[j + 2] - lo) * 255 / range);
    }
    ctx.putImageData(img, 0, 0);
    return fullBuffer;
  }

  // --- Calidad de la muestra (brillo y nitidez) ------------------------------

  var qualityBuffer = document.createElement('canvas');
  var QUALITY_SIZE = 60;
  qualityBuffer.width = QUALITY_SIZE;
  qualityBuffer.height = QUALITY_SIZE;

  function sampleQuality(box) {
    var w = Math.max(1, Math.round(box.width));
    var h = Math.max(1, Math.round(box.height));
    var ctx = qualityBuffer.getContext('2d');
    ctx.drawImage(el.video, box.x, box.y, w, h, 0, 0, QUALITY_SIZE, QUALITY_SIZE);
    var data = ctx.getImageData(0, 0, QUALITY_SIZE, QUALITY_SIZE).data;

    var gray = new Float32Array(QUALITY_SIZE * QUALITY_SIZE);
    var total = 0;
    for (var i = 0, p = 0; i < data.length; i += 4, p++) {
      var v = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      gray[p] = v;
      total += v;
    }
    var brightness = total / gray.length;

    // Nitidez aproximada: varianza de un gradiente simple (diferencia entre
    // píxeles vecinos). Una imagen movida o desenfocada tiene bordes suaves, así
    // que el gradiente sale pequeño y poco variable.
    var sum = 0, sumSq = 0, count = 0;
    for (var y = 0; y < QUALITY_SIZE - 1; y++) {
      for (var x = 0; x < QUALITY_SIZE - 1; x++) {
        var idx = y * QUALITY_SIZE + x;
        var gx = gray[idx + 1] - gray[idx];
        var gy = gray[idx + QUALITY_SIZE] - gray[idx];
        var mag = Math.abs(gx) + Math.abs(gy);
        sum += mag;
        sumSq += mag * mag;
        count++;
      }
    }
    var mean = sum / count;
    var variance = (sumSq / count) - (mean * mean);

    return {
      tooDark: brightness < CFG.MIN_BRIGHTNESS,
      blurry: variance < CFG.MIN_SHARPNESS
    };
  }

  function drawBox(box, ok) {
    var ctx = el.overlay.getContext('2d');
    if (el.overlay.width !== el.video.videoWidth) {
      el.overlay.width = el.video.videoWidth;
      el.overlay.height = el.video.videoHeight;
    }
    ctx.clearRect(0, 0, el.overlay.width, el.overlay.height);
    if (!box) return;
    ctx.lineWidth = 3;
    ctx.strokeStyle = ok ? '#22c55e' : '#f59e0b';
    ctx.strokeRect(box.x, box.y, box.width, box.height);
  }

  function rechazar(mensaje) {
    state.stable = 0;
    hint(mensaje, false);
  }

  function aceptar(descriptor) {
    state.capturadas.push(Array.from(descriptor));
    state.stable = 0;
    state.indice += 1;
    progreso();

    if (state.capturadas.length >= objetivo) {
      enviar();
      return;
    }

    // Pausa breve: sin ella las cinco muestras salen del mismo instante y del mismo
    // gesto, que es justo lo que se quería evitar.
    state.pausa = true;
    hint('Muestra ' + state.capturadas.length + ' guardada. ' +
         POSES[state.indice % POSES.length].texto, true);
    setTimeout(function () {
      state.pausa = false;
      state.esperandoDesde = Date.now();
    }, CFG.BETWEEN_MS);
  }

  function check() {
    if (state.busy || state.pausa || !el.video.videoWidth) return;
    state.busy = true;

    // Detección, puntos de referencia y descriptor en UNA sola pasada por la red
    // (antes eran dos: detectAllFaces para contar rostros y detectSingleFace para
    // sacar el descriptor, que volvía a correr el mismo detector desde cero).
    faceapi
      .detectAllFaces(detectionSource(), state.options)
      .withFaceLandmarks()
      .withFaceDescriptors()
      .then(function (results) {
        if (results.length === 0) {
          drawBox(null);
          rechazar('No se detecta ningún rostro. Colóquese frente a la cámara.');
          return null;
        }
        if (results.length > 1) {
          drawBox(null);
          rechazar('Se ven ' + results.length + ' rostros. Debe quedar solo el del cliente.');
          return null;
        }
        var subject = results[0];
        var box = subject.detection.box;
        if (box.width < el.video.videoWidth * CFG.MIN_FACE_RATIO) {
          drawBox(box, false);
          rechazar('Acérquese más a la cámara: el rostro se ve pequeño.');
          return null;
        }
        drawBox(box, true);
        return subject;
      })
      .then(function (subject) {
        if (!subject || !subject.descriptor) return;

        var pose = POSES[state.indice % POSES.length];
        if (desvioLateral(subject.landmarks) > pose.maxYaw) {
          rechazar('Demasiado girado. ' + pose.texto);
          return;
        }

        // Calidad de la muestra: una de referencia mala arrastra reconocimientos
        // malos para siempre, así que se rechaza antes de aceptarla, no después.
        var calidad = sampleQuality(subject.detection.box);
        if (calidad.tooDark) {
          rechazar('Hay poca luz. Acérquese a una zona más iluminada.');
          return;
        }
        if (calidad.blurry) {
          rechazar('Imagen borrosa. Quédese quieto un momento.');
          return;
        }

        // Que la muestra aporte algo respecto a la anterior.
        var previa = state.capturadas[state.capturadas.length - 1];
        var esperando = Date.now() - state.esperandoDesde;
        if (previa && distancia(Array.from(subject.descriptor), previa) < CFG.MIN_VARIATION &&
            esperando < CFG.VARIATION_TIMEOUT_MS) {
          rechazar(pose.texto + ' (cambie un poco la postura)');
          return;
        }

        state.stable += 1;
        if (state.stable < CFG.STABLE_FRAMES) {
          hint('Quieto un momento… ' + pose.texto, false);
          return;
        }
        aceptar(subject.descriptor);
      })
      .catch(function (err) {
        console.error('[rostro] fallo al analizar', err);
      })
      .then(function () {
        state.busy = false;
      });
  }

  // --- Envío ---------------------------------------------------------------

  function enviar() {
    el.input.value = JSON.stringify(state.capturadas);
    hint('Guardando las ' + state.capturadas.length + ' muestras…', true);
    // La cámara se apaga antes de enviar: si no, el piloto de la webcam se queda
    // encendido durante toda la recarga de la página.
    stopCamera();
    el.form.submit();
  }

  // --- Enganches -----------------------------------------------------------

  root.addEventListener('click', function (event) {
    var accion = event.target.closest('[data-face-action]');
    if (!accion) return;
    if (accion.dataset.faceAction === 'start') start();
    if (accion.dataset.faceAction === 'cancel') cancel();
  });

  // Salir de la página con la cámara abierta deja el piloto encendido en algunos
  // equipos hasta que se cierra el navegador.
  window.addEventListener('pagehide', stopCamera);

  if (typeof faceapi === 'undefined') {
    if (el.start) el.start.disabled = true;
    fail('No se pudo cargar el motor de reconocimiento facial. Reinstale el programa.');
  }
})();
