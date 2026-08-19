/* Kiosco de acceso por reconocimiento facial.
 *
 * Reparto de responsabilidades:
 *   - Aquí (navegador): ver la cámara, decidir A QUIÉN se está mirando y convertir
 *     ese rostro en 128 números.
 *   - En el servidor: decidir QUIÉN ES y si puede entrar. La galería de rostros del
 *     gimnasio no baja nunca al navegador.
 *
 * El grueso de este archivo no es «reconocer», que son cuatro líneas de face-api,
 * sino evitar los errores que aparecen en cuanto la cámara mira a la vida real:
 * gente de paso por detrás, alguien que se queda plantado, un parecido razonable
 * que no es la persona, la webcam que se desconecta.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-kiosk]');
  if (!root) return;

  // --- Ajustes -------------------------------------------------------------

  var CFG = {
    // Cada cuánto se mira la imagen. Más a menudo no mejora nada (nadie entra en
    // 100 ms) y calienta el equipo de recepción, que suele ser modesto.
    DETECT_MS: 300,

    // Tamaño de entrada del detector. 320 es el punto donde deja de ganarse
    // precisión apreciable y se empieza a pagar latencia.
    INPUT_SIZE: 320,
    SCORE_MIN: 0.5,

    // Un rostro que ocupa menos de este porcentaje del ancho da descriptores
    // pobres: mejor pedir que se acerque que arriesgar una identificación mala.
    MIN_FACE_RATIO: 0.13,

    // Cuando hay varias caras, si la más grande supera a la siguiente por este
    // factor se entiende que es quien está en la cámara y el resto va de paso.
    DOMINANT_RATIO: 1.8,

    // Fotogramas seguidos que deben coincidir antes de dar un resultado por bueno.
    // Sin esto la ficha parpadea entre «no reconocido» y el nombre correcto.
    CONFIRM_FRAMES: 2,

    // Dos umbrales que antes eran uno solo (SAME_PERSON_DISTANCE), separados porque
    // resuelven dos preguntas distintas: CONFIRM_DISTANCE decide si dos fotogramas
    // seguidos DEL MISMO INSTANTE son la misma persona (debe ser estricto, es la base
    // de la identificación); LINGER_DISTANCE decide si quien sigue delante de la
    // cámara un rato después sigue siendo esa persona (algo más laxo a propósito: la
    // pose y la luz cambian un poco mientras alguien espera o habla).
    CONFIRM_DISTANCE: 0.45,
    LINGER_DISTANCE: 0.50,

    // Mientras la misma persona siga delante, no se vuelve a preguntar al servidor.
    // Este es el antirrebote de verdad: sin él, quien se queda charlando genera una
    // petición cada 300 ms.
    LINGER_MS: 20000,

    // La ficha se queda en pantalla un rato después de que la persona se aparte,
    // para que le dé tiempo a leerla mientras cruza la puerta.
    CARD_HOLD_MS: 8000,

    // Tras un fallo de red se espera más entre intentos, para no machacar un
    // servidor que ya está teniendo problemas.
    ERROR_BACKOFF_MS: 3000,

    // -- Iluminación ----------------------------------------------------------
    // Luminancia media (0-255) fuera de la cual se considera «luz difícil» y se
    // corrige antes de detectar. Con luz normal no se calcula nada de esto.
    LUMA_LOW: 60,
    LUMA_HIGH: 190,

    // -- Vida básica (anti-suplantación) ---------------------------------------
    // Distancia media entre puntos de referencia (landmarks) de dos fotogramas de
    // confirmación. Una foto impresa sostenida con la mano apenas se mueve entre dos
    // fotogramas de 300 ms; una cara real siempre tiene algo de movimiento
    // involuntario. No es detección de parpadeo ni de vídeo en una pantalla —eso
    // exigiría observar varios segundos, y chocaría con que el kiosco sea rápido—,
    // solo descarta el caso más barato y común de suplantación.
    MIN_LIVENESS_MOVEMENT: 0.35,
    // Tope de fotogramas extra esperando ese movimiento: si alguien se queda
    // realmente inmóvil, no debe quedar bloqueado para siempre por esta comprobación.
    LIVENESS_MAX_EXTRA_FRAMES: 6
  };

  var MODELS_URL = root.dataset.modelsUrl;
  var IDENTIFY_URL = root.dataset.identifyUrl;
  var CSRF = root.dataset.csrf;

  // --- Elementos -----------------------------------------------------------

  var el = {
    video: root.querySelector('[data-video]'),
    overlay: root.querySelector('[data-overlay]'),
    stage: root.querySelector('[data-stage]'),
    veil: root.querySelector('[data-veil]'),
    veilText: root.querySelector('[data-veil-text]'),
    veilHint: root.querySelector('[data-veil-hint]'),
    veilSpinner: root.querySelector('[data-veil-spinner]'),
    engine: root.querySelector('[data-engine-state]'),
    clock: root.querySelector('[data-clock]'),
    banner: root.querySelector('[data-banner]'),
    bannerIcon: root.querySelector('[data-banner-icon]'),
    bannerText: root.querySelector('[data-banner-text]'),
    panel: root.querySelector('[data-panel]'),
    slots: {
      idle: root.querySelector('[data-slot="idle"]'),
      message: root.querySelector('[data-slot="message"]'),
      card: root.querySelector('[data-slot="card"]')
    },
    msgIcon: root.querySelector('[data-msg-icon]'),
    msgTitle: root.querySelector('[data-msg-title]'),
    msgText: root.querySelector('[data-msg-text]'),
    verdict: root.querySelector('[data-verdict]'),
    verdictIcon: root.querySelector('[data-verdict-icon]'),
    verdictText: root.querySelector('[data-verdict-text]'),
    photo: root.querySelector('[data-photo]'),
    name: root.querySelector('[data-name]'),
    document: root.querySelector('[data-document]'),
    statusBadge: root.querySelector('[data-status-badge]'),
    facts: root.querySelector('[data-facts]'),
    repeat: root.querySelector('[data-repeat]')
  };

  // --- Estado --------------------------------------------------------------

  var state = {
    ready: false,       // modelos y cámara en marcha
    busy: false,        // hay una detección en curso
    inFlight: false,    // hay una petición al servidor en curso
    stream: null,
    options: null,
    timer: null,

    // Confirmación temporal: qué se vio y cuántas veces seguidas.
    pending: null,
    pendingLandmarks: null,
    pendingCount: 0,
    bestMovement: 0,
    livenessExtra: 0,

    // Última persona identificada, para no repetir la consulta mientras siga ahí.
    last: null,         // { descriptor, payload, at }
    shownUntil: 0,
    nextAllowedAt: 0
  };

  // --- Utilidades ----------------------------------------------------------

  function distance(a, b) {
    var total = 0;
    for (var i = 0; i < a.length; i++) {
      var d = a[i] - b[i];
      total += d * d;
    }
    return Math.sqrt(total);
  }

  function boxArea(box) {
    return Math.max(0, box.width) * Math.max(0, box.height);
  }

  function landmarkMovement(a, b) {
    // Distancia media entre los mismos 68 puntos de referencia en dos fotogramas.
    // null si no hay con qué comparar (primer fotograma de una confirmación nueva).
    if (!a || !b || !a.positions || !b.positions || a.positions.length !== b.positions.length) return null;
    var total = 0;
    for (var i = 0; i < a.positions.length; i++) {
      var dx = a.positions[i].x - b.positions[i].x;
      var dy = a.positions[i].y - b.positions[i].y;
      total += Math.sqrt(dx * dx + dy * dy);
    }
    return total / a.positions.length;
  }

  // --- Normalización de iluminación -----------------------------------------
  // Con luz normal esto cuesta casi nada (un lienzo de 80x45). El estiramiento de
  // niveles, que sí tiene un costo real, solo se paga cuando la luz de verdad es
  // mala —que es justo cuando más ayuda—.

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

  function tickClock() {
    var now = new Date();
    el.clock.textContent =
      String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');
  }

  function setEngine(text, kind) {
    el.engine.textContent = text;
    el.engine.dataset.kind = kind || '';
  }

  function showVeil(text, hint, spinning) {
    el.veilText.textContent = text;
    el.veilHint.textContent = hint || '';
    el.veilSpinner.hidden = !spinning;
    el.veil.hidden = false;
  }

  function hideVeil() {
    el.veil.hidden = true;
  }

  function setBanner(icon, text) {
    if (!text) {
      el.banner.hidden = true;
      return;
    }
    el.bannerIcon.textContent = icon;
    el.bannerText.textContent = text;
    el.banner.hidden = false;
  }

  // --- Pintado del panel derecho -------------------------------------------

  function showSlot(name) {
    Object.keys(el.slots).forEach(function (key) {
      el.slots[key].hidden = key !== name;
    });
  }

  function renderIdle() {
    el.panel.dataset.state = 'idle';
    setBanner(null);
    showSlot('idle');
  }

  function renderMessage(kind, icon, title, text) {
    el.panel.dataset.state = kind;
    el.msgIcon.textContent = icon;
    el.msgTitle.textContent = title;
    el.msgText.textContent = text || '';
    showSlot('message');
  }

  function fact(label, value) {
    if (value === null || value === undefined || value === '') return '';
    var dt = document.createElement('dt');
    var dd = document.createElement('dd');
    dt.textContent = label;
    dd.textContent = value;
    el.facts.appendChild(dt);
    el.facts.appendChild(dd);
    return '';
  }

  function renderCard(payload) {
    var c = payload.client || {};
    var m = c.membership;

    el.panel.dataset.state = payload.allowed ? 'allowed' : 'denied';
    el.verdictIcon.textContent = payload.allowed ? '✅' : '⛔';
    el.verdictText.textContent = payload.allowed ? 'ACCESO PERMITIDO' : 'ACCESO DENEGADO';

    // La foto se pinta como <img> o, si el cliente no tiene, con su inicial.
    el.photo.textContent = '';
    if (c.photo_url) {
      var img = document.createElement('img');
      img.src = c.photo_url;
      img.alt = '';
      el.photo.appendChild(img);
    } else {
      el.photo.textContent = c.initial || '?';
    }

    el.name.textContent = c.name || '';
    el.document.textContent = 'Documento: ' + (c.document_id || '—');

    el.statusBadge.textContent = payload.reason_label;
    el.statusBadge.className =
      'badge ' + (payload.reason === 'ACTIVE' ? 'active' : payload.reason === 'EXPIRED' ? 'expired' : 'none');

    el.facts.textContent = '';
    if (m) {
      fact('Vence el', m.end_label);
      if (m.days_left !== null && m.days_left !== undefined) {
        fact('Días restantes', m.days_left > 0 ? m.days_left + ' día(s)' : 'vencida hace ' + Math.abs(m.days_left) + ' día(s)');
      }
      fact('Última inscripción', m.duration);
    } else {
      fact('Inscripción', 'No tiene ninguna registrada');
    }
    if (c.phone) fact('Teléfono', c.phone);
    if (c.emergency_phone) fact('Emergencia', (c.emergency_name ? c.emergency_name + ' · ' : '') + c.emergency_phone);
    if (payload.visits_today) fact('Entradas de hoy', payload.visits_today);

    if (payload.repeat) {
      var secs = payload.seconds_since || 0;
      el.repeat.textContent =
        'Ya se registró su entrada hace ' +
        (secs < 60 ? secs + ' segundo(s)' : Math.round(secs / 60) + ' minuto(s)') + '.';
      el.repeat.hidden = false;
    } else {
      el.repeat.hidden = true;
    }

    showSlot('card');
    state.shownUntil = Date.now() + CFG.CARD_HOLD_MS;
  }

  // --- Traducción de la respuesta del servidor -----------------------------

  function present(payload) {
    if (payload.status === 'match') {
      renderCard(payload);
      return;
    }
    if (payload.status === 'uncertain') {
      renderMessage('uncertain', '🔍', 'Acérquese un poco más',
        'Se le parece a alguien registrado, pero no lo suficiente para confirmarlo.');
    } else {
      renderMessage('unknown', '🚫', 'Rostro no reconocido',
        'Diríjase a recepción para registrar su acceso.');
    }
    state.shownUntil = Date.now() + CFG.CARD_HOLD_MS;
  }

  // --- Consulta al servidor ------------------------------------------------

  function identify(descriptor) {
    if (state.inFlight || Date.now() < state.nextAllowedAt) return;
    state.inFlight = true;

    var body = new URLSearchParams();
    body.set('csrf_token', CSRF);
    body.set('descriptor', JSON.stringify(Array.from(descriptor)));

    fetch(IDENTIFY_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString()
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (payload) {
        if (!payload.ok) throw new Error(payload.error || 'respuesta inválida');

        // Un administrador apagó el reconocimiento con esta pestaña abierta: se para
        // la cámara en vez de seguir consultando en balde.
        if (payload.status === 'disabled') {
          shutdown('Reconocimiento facial desactivado',
            'Un administrador lo apagó. Recargue esta pestaña cuando vuelva a activarse.');
          return;
        }

        state.nextAllowedAt = 0;
        setEngine('En servicio', 'ok');

        // Se recuerda a quién corresponde este descriptor para no volver a
        // preguntar mientras la misma persona siga delante de la cámara.
        state.last = { descriptor: descriptor, payload: payload, at: Date.now() };
        present(payload);
      })
      .catch(function (err) {
        // Un fallo aquí es del servidor o del token de la página, no de la cámara.
        state.nextAllowedAt = Date.now() + CFG.ERROR_BACKOFF_MS;
        setEngine('Sin conexión con el programa', 'error');
        renderMessage('error', '⚠️', 'No se pudo consultar',
          'Revise que el programa siga abierto y recargue esta pestaña. (' + err.message + ')');
      })
      .then(function () {
        state.inFlight = false;
      });
  }

  // --- Dibujo del recuadro -------------------------------------------------

  function drawBoxes(results, subject) {
    var ctx = el.overlay.getContext('2d');
    ctx.clearRect(0, 0, el.overlay.width, el.overlay.height);

    results.forEach(function (r) {
      var box = r.detection.box;
      var isSubject = subject && box === subject.detection.box;
      ctx.lineWidth = isSubject ? 4 : 2;
      ctx.strokeStyle = isSubject ? '#22c55e' : 'rgba(255,255,255,.45)';
      ctx.strokeRect(box.x, box.y, box.width, box.height);
    });
  }

  function syncOverlay() {
    if (!el.video.videoWidth) return;
    el.overlay.width = el.video.videoWidth;
    el.overlay.height = el.video.videoHeight;
  }

  // --- Bucle de detección --------------------------------------------------

  function pickSubject(results) {
    /* Devuelve el resultado (detección + landmarks + descriptor) de la persona a
       identificar, o null si es ambiguo. Que haya dos caras no significa que haya
       dos personas entrando: lo normal es que alguien cruce por detrás. Si una
       domina claramente en tamaño, es la que está en la cámara. */
    if (results.length === 1) return results[0];

    var sorted = results.slice().sort(function (a, b) {
      return boxArea(b.detection.box) - boxArea(a.detection.box);
    });
    if (boxArea(sorted[0].detection.box) >= boxArea(sorted[1].detection.box) * CFG.DOMINANT_RATIO) {
      return sorted[0];
    }
    return null;
  }

  function resetPending() {
    state.pending = null;
    state.pendingLandmarks = null;
    state.pendingCount = 0;
    state.bestMovement = 0;
    state.livenessExtra = 0;
  }

  function loop() {
    if (state.busy || !state.ready || document.hidden) return;
    state.busy = true;

    // Detección, puntos de referencia y descriptor en UNA sola pasada por la red
    // (antes eran dos: detectAllFaces para contar caras y detectSingleFace para
    // sacar el descriptor, que volvía a correr el mismo detector desde cero).
    faceapi
      .detectAllFaces(detectionSource(), state.options)
      .withFaceLandmarks()
      .withFaceDescriptors()
      .then(function (results) {
        syncOverlay();

        // -- Nadie delante ---------------------------------------------------
        if (results.length === 0) {
          drawBoxes([], null);
          setBanner(null);
          resetPending();
          if (Date.now() > state.shownUntil) renderIdle();
          return;
        }

        // -- Varias personas sin una clara ------------------------------------
        var subject = pickSubject(results);
        if (!subject) {
          drawBoxes(results, null);
          setBanner('👥', 'Hay ' + results.length + ' personas frente a la cámara. Pasen de uno en uno.');
          renderMessage('multiple', '👥', 'Pasen de uno en uno',
            'Para registrar la entrada solo puede haber una persona frente a la cámara.');
          resetPending();
          return;
        }

        drawBoxes(results, subject);
        setBanner(
          results.length > 1 ? '👥' : null,
          results.length > 1 ? 'Se está registrando a la persona más cercana a la cámara.' : null
        );

        // -- Demasiado lejos ---------------------------------------------------
        if (subject.detection.box.width < el.video.videoWidth * CFG.MIN_FACE_RATIO) {
          renderMessage('far', '📏', 'Acérquese a la cámara',
            'Su rostro se ve demasiado pequeño para reconocerlo.');
          resetPending();
          return;
        }

        if (!subject.descriptor) return;
        var descriptor = subject.descriptor;

        // -- ¿Sigue siendo la misma persona de hace un momento? ---------------
        // Se resuelve en el navegador comparando con el último descriptor: así
        // quien se queda parado delante no genera ni una sola petición extra.
        if (state.last && Date.now() - state.last.at < CFG.LINGER_MS &&
            distance(descriptor, state.last.descriptor) <= CFG.LINGER_DISTANCE) {
          state.last.at = Date.now();
          state.shownUntil = Date.now() + CFG.CARD_HOLD_MS;
          return;
        }

        // -- Confirmación en varios fotogramas ---------------------------------
        if (state.pending && distance(descriptor, state.pending) <= CFG.CONFIRM_DISTANCE) {
          state.pendingCount += 1;
          var movimiento = landmarkMovement(subject.landmarks, state.pendingLandmarks);
          if (movimiento !== null && movimiento > state.bestMovement) state.bestMovement = movimiento;
          state.pendingLandmarks = subject.landmarks;
        } else {
          state.pending = descriptor;
          state.pendingLandmarks = subject.landmarks;
          state.pendingCount = 1;
          state.bestMovement = 0;
          state.livenessExtra = 0;
        }
        if (state.pendingCount < CFG.CONFIRM_FRAMES) return;

        // -- Vida básica: ¿hubo algo de movimiento natural entre fotogramas? ---
        // Una foto impresa sostenida con la mano apenas se mueve; una cara real,
        // sí. No bloquea para siempre a quien esté muy quieto: pasado el tope de
        // fotogramas extra, se deja pasar de todas formas (ver CFG).
        if (state.bestMovement < CFG.MIN_LIVENESS_MOVEMENT &&
            state.livenessExtra < CFG.LIVENESS_MAX_EXTRA_FRAMES) {
          state.livenessExtra += 1;
          return;
        }

        resetPending();
        identify(descriptor);
      })
      .catch(function (err) {
        // Un fallo de la red neuronal no puede dejar el kiosco colgado: se anota y
        // el siguiente ciclo lo vuelve a intentar.
        console.error('[kiosco] fallo al analizar el fotograma', err);
      })
      .then(function () {
        state.busy = false;
      });
  }

  // --- Arranque ------------------------------------------------------------

  function startCamera() {
    return navigator.mediaDevices
      .getUserMedia({
        video: {
          width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user',
          // Enfoque automático continuo, si la cámara y el navegador lo exponen
          // (extensión no estándar, sobre todo en Chromium). Es «mejor esfuerzo»:
          // una clave desconocida dentro de `advanced` se ignora sin error según el
          // propio algoritmo de restricciones de getUserMedia, así que no hace falta
          // detectar soporte de antemano ni hay riesgo de que falle el arranque.
          advanced: [{ focusMode: 'continuous' }]
        }
      })
      .then(function (stream) {
        state.stream = stream;
        el.video.srcObject = stream;

        // Segundo intento por si el navegador solo acepta el foco continuo aplicado
        // sobre el track ya abierto, en vez de al pedir la cámara. Mismo criterio de
        // «mejor esfuerzo»: si no lo soporta, esto no hace nada y no interrumpe nada.
        var videoTrack = stream.getVideoTracks()[0];
        if (videoTrack && videoTrack.applyConstraints) {
          videoTrack.applyConstraints({ advanced: [{ focusMode: 'continuous' }] }).catch(function () {});
        }

        // Si alguien desconecta la webcam, el track termina y el vídeo se queda
        // congelado sin avisar. Hay que decirlo en pantalla.
        stream.getVideoTracks().forEach(function (track) {
          track.addEventListener('ended', function () {
            state.ready = false;
            setEngine('Cámara desconectada', 'error');
            showVeil('Se perdió la señal de la cámara',
              'Vuelva a conectarla y recargue esta pestaña.', false);
          });
        });

        return el.video.play();
      });
  }

  function shutdown(title, hint) {
    /* Para el kiosco del todo: sin bucle, sin cámara y sin luz encendida en la
       webcam, que si no parece que sigue grabando. */
    state.ready = false;
    if (state.timer) clearInterval(state.timer);
    if (state.stream) state.stream.getTracks().forEach(function (t) { t.stop(); });
    setEngine(title, 'error');
    showVeil(title, hint, false);
    renderIdle();
  }

  function cameraError(err) {
    var message = 'No se pudo abrir la cámara.';
    var hint = err && err.message ? err.message : '';
    if (err && (err.name === 'NotAllowedError' || err.name === 'SecurityError')) {
      message = 'El navegador bloqueó el acceso a la cámara';
      hint = 'Permita el uso de la cámara para este sitio y recargue la pestaña.';
    } else if (err && err.name === 'NotFoundError') {
      message = 'No se encontró ninguna cámara';
      hint = 'Conecte una webcam y recargue la pestaña.';
    } else if (err && err.name === 'NotReadableError') {
      message = 'Otro programa está usando la cámara';
      hint = 'Ciérrelo (videollamadas, otra pestaña con el kiosco) y recargue.';
    }
    setEngine('Cámara no disponible', 'error');
    showVeil(message, hint, false);
  }

  function confirmBackend() {
    // Confirma que tfjs use WebGL (GPU) en vez de caer a un modo más lento (CPU/WASM)
    // sin que nadie lo note. Todo detrás de comprobaciones de existencia: si la
    // librería cambiara de forma, esto simplemente no hace nada, nunca bloquea el
    // arranque del kiosco.
    if (!faceapi.tf || !faceapi.tf.setBackend) return null;
    return faceapi.tf.setBackend('webgl')
      .catch(function () {})
      .then(function () {
        return faceapi.tf.ready ? faceapi.tf.ready() : null;
      })
      .then(function () {
        if (faceapi.tf.getBackend && faceapi.tf.getBackend() !== 'webgl') {
          console.warn('[kiosco] usando backend "' + faceapi.tf.getBackend() + '" (más lento que webgl)');
        }
      })
      .catch(function () {});
  }

  function boot() {
    tickClock();
    setInterval(tickClock, 20000);

    if (typeof faceapi === 'undefined') {
      setEngine('Motor no disponible', 'error');
      showVeil('No se pudo cargar el motor de reconocimiento',
        'Falta app/static/vendor/faceapi. Reinstale el programa.', false);
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      cameraError({ name: 'NotFoundError' });
      return;
    }

    setEngine('Cargando modelos…', '');
    Promise.all([
      faceapi.nets.tinyFaceDetector.loadFromUri(MODELS_URL),
      faceapi.nets.faceLandmark68Net.loadFromUri(MODELS_URL),
      faceapi.nets.faceRecognitionNet.loadFromUri(MODELS_URL)
    ])
      .then(confirmBackend)
      .then(function () {
        state.options = new faceapi.TinyFaceDetectorOptions({
          inputSize: CFG.INPUT_SIZE,
          scoreThreshold: CFG.SCORE_MIN
        });
        setEngine('Abriendo la cámara…', '');
        showVeil('Abriendo la cámara…', 'Permita el acceso si el navegador lo pide.', true);
        return startCamera();
      })
      .then(function () {
        syncOverlay();
        hideVeil();
        setEngine('En servicio', 'ok');
        state.ready = true;
        renderIdle();
        state.timer = setInterval(loop, CFG.DETECT_MS);
      })
      .catch(function (err) {
        // `state.options` solo existe si los modelos llegaron a cargar, así que
        // distingue entre «falló el motor» y «falló la cámara».
        if (state.options) {
          cameraError(err);
          return;
        }
        console.error('[kiosco] no se pudieron cargar los modelos', err);
        setEngine('Motor no disponible', 'error');
        showVeil('No se pudieron cargar los modelos de reconocimiento',
          'Compruebe que existe la carpeta app/static/vendor/faceapi/models.', false);
      });
  }

  // Con la pestaña en segundo plano el navegador estrangula los temporizadores y
  // las detecciones se encolan. Es más limpio parar y reanudar.
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      state.pending = null;
      state.pendingCount = 0;
    }
  });

  window.addEventListener('resize', syncOverlay);
  el.video.addEventListener('loadedmetadata', syncOverlay);

  boot();
})();
