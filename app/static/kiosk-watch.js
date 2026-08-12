/* Aviso de las entradas del kiosco, en las pantallas del programa.
 *
 * Quien atiende el mostrador trabaja en esta pestaña, no en la del kiosco. Sin esto
 * tendría que cambiar de pestaña para saber si a quien acaba de pasar se le permitió
 * la entrada, que es justo cuando hay que reaccionar.
 *
 * Aparece SOLO cuando alguien acaba de ser detectado —lo dejen entrar o no— y se
 * desvanece a los diez segundos: el resto del tiempo no debe tapar nada de la pantalla.
 *
 * ## El tiempo se cuenta por reloj, no con temporizadores
 *
 * El navegador frena `setTimeout` en las pestañas que no se están mirando: a los pocos
 * minutos en segundo plano pasan a dispararse como mucho una vez por minuto. Con
 * temporizadores, cambiar de pestaña dejaba avisos congelados en pantalla durante
 * minutos y hacía que la cola se descolgara de la realidad.
 *
 * Por eso cada aviso guarda el INSTANTE en que debe desaparecer (`expiraEn`) y un único
 * latido recalcula la situación comparando con `Date.now()`. Que al navegador le dé por
 * frenar el latido solo retrasa la reacción: en cuanto vuelve a correr, un solo tic
 * pone todo en su sitio. La cuenta atrás sale igual mires la pestaña que mires.
 *
 * Cada pestaña lleva su propia marca de «hasta aquí ya lo enseñé» (en sessionStorage,
 * que es por pestaña): así el aviso sale en la pestaña que se esté mirando, sin que una
 * se lo coma para las demás.
 */
(function () {
  'use strict';

  var box = document.querySelector('[data-kiosk-watch]');
  if (!box) return;

  var CFG = {
    // Cada cuánto se pregunta al servidor por entradas nuevas.
    POLL_MS: 4000,
    // Cada cuánto se revisa si toca mostrar u ocultar algo.
    TICK_MS: 200,
    // Lo que dura un aviso en pantalla.
    DURACION_MS: 10000,
    // Lo que dura cuando hay más esperando detrás: si no, cinco personas seguidas
    // significarían casi un minuto de avisos arrastrándose por detrás de la realidad.
    DURACION_EN_COLA_MS: 3500,
    // Duración del desvanecido. Debe coincidir con la transición de styles.css.
    FADE_MS: 900,
    // Un paso más viejo que esto ya no se anuncia: interesa avisar de lo que acaba de
    // ocurrir, no de lo que pasó hace rato.
    MAX_EDAD_S: 12,
    // Mínimo que se deja ver un aviso al que ya le quedaba poco, para que no parpadee.
    MINIMO_VISIBLE_MS: 1500
  };

  var CLAVE_VISTO = 'gymlite.kioskWatch.ultimoVisto';

  var el = {
    close: box.querySelector('[data-kw-close]'),
    event: box.querySelector('[data-kw-event]'),
    photo: box.querySelector('[data-kw-photo]'),
    name: box.querySelector('[data-kw-name]'),
    reason: box.querySelector('[data-kw-reason]'),
    when: box.querySelector('[data-kw-when]'),
    verdict: box.querySelector('[data-kw-verdict]'),
    pending: box.querySelector('[data-kw-pending]'),
    timer: box.querySelector('[data-kw-timer] span')
  };

  // Estado, todo en marcas de tiempo absolutas para que nada dependa de temporizadores.
  var cola = [];          // pendientes de mostrar, del más viejo al más nuevo
  var actual = null;      // { evento, expiraEn, duracion }
  var ocultandoHasta = 0; // instante en que termina el desvanecido (0 = no se está yendo)

  // --- Marca de lo ya anunciado --------------------------------------------

  function ultimoVisto() {
    try { return sessionStorage.getItem(CLAVE_VISTO); } catch (e) { return null; }
  }

  function marcarVisto(id) {
    try { sessionStorage.setItem(CLAVE_VISTO, String(id)); } catch (e) { /* modo privado */ }
  }

  // --- Pintado --------------------------------------------------------------

  function hace(segundos) {
    if (segundos < 5) return 'ahora mismo';
    if (segundos < 60) return 'hace ' + segundos + ' s';
    if (segundos < 3600) return 'hace ' + Math.round(segundos / 60) + ' min';
    return 'hace ' + Math.round(segundos / 3600) + ' h';
  }

  function pintar(evento, pendientes) {
    el.photo.textContent = '';
    if (evento.photo_url) {
      var img = document.createElement('img');
      img.src = evento.photo_url;
      img.alt = '';
      // Una foto que no carga no debe dejar el hueco vacío.
      img.addEventListener('error', function () {
        el.photo.textContent = evento.initial || '?';
      });
      el.photo.appendChild(img);
    } else {
      el.photo.textContent = evento.initial || '?';
    }

    el.name.textContent = evento.name;
    el.reason.textContent = evento.reason_label;
    el.when.textContent = evento.at + ' · ' + hace(evento.ago);
    el.verdict.textContent = evento.allowed ? 'PERMITIDO' : 'DENEGADO';

    box.dataset.state = evento.allowed ? 'allowed' : 'denied';
    if (evento.url) {
      el.event.href = evento.url;
    } else {
      el.event.removeAttribute('href');
    }

    if (pendientes > 0) {
      el.pending.textContent = '+' + pendientes;
      el.pending.hidden = false;
    } else {
      el.pending.hidden = true;
    }
  }

  // --- Mostrar y ocultar ----------------------------------------------------

  function mostrar(entrada) {
    actual = entrada;
    ocultandoHasta = 0;

    pintar(entrada.evento, cola.length);
    box.hidden = false;
    // Forzar el cálculo de estilos entre quitar [hidden] y añadir la clase: sin esto
    // el navegador agrupa ambos cambios y no hay transición de entrada.
    void box.offsetWidth;
    box.classList.add('is-visible');
    latido();   // pinta la barra ya, sin esperar al siguiente tic
  }

  function empezarAOcultar() {
    if (!actual) return;
    actual = null;
    ocultandoHasta = Date.now() + CFG.FADE_MS;
    box.classList.remove('is-visible');
  }

  function retirar() {
    ocultandoHasta = 0;
    box.hidden = true;
    el.timer.style.width = '0%';
  }

  // Cerrar a mano descarta también lo que quede en cola: quien lo cierra quiere la
  // pantalla despejada, no el siguiente aviso acto seguido.
  el.close.addEventListener('click', function () {
    cola = [];
    empezarAOcultar();
  });

  // --- Latido: única fuente de verdad ---------------------------------------

  function latido() {
    var ahora = Date.now();

    // 1. ¿Terminó de desvanecerse lo anterior?
    if (ocultandoHasta && ahora >= ocultandoHasta) retirar();

    // 2. ¿Se le acabó el tiempo a lo que hay en pantalla?
    if (actual) {
      var restante = actual.expiraEn - ahora;
      if (restante <= 0) {
        empezarAOcultar();
      } else {
        // La barra se pinta a partir del tiempo real que queda, no con una transición
        // de CSS: así coincide con la realidad aunque la pestaña haya estado parada.
        el.timer.style.width = Math.max(0, Math.min(100, (restante / actual.duracion) * 100)) + '%';
      }
    }

    // 3. Se descarta lo que haya caducado esperando turno.
    while (cola.length && cola[0].expiraEn <= ahora) cola.shift();

    // 4. ¿Toca sacar el siguiente?
    //    En una pestaña que no se está mirando no se saca nada: gastaría su tiempo en
    //    pantalla sin que nadie lo vea. Se queda en cola y, si al volver sigue vigente,
    //    se muestra con lo que le reste.
    if (!actual && !ocultandoHasta && cola.length && !document.hidden) {
      var entrada = cola.shift();
      // Con gente en fila cada aviso dura menos, para que la cola no se descuelgue.
      var tope = cola.length > 0 ? CFG.DURACION_EN_COLA_MS : CFG.DURACION_MS;
      entrada.expiraEn = Math.min(entrada.expiraEn, ahora + tope);
      // Si le quedaba un suspiro, se le da un mínimo para que no parpadee.
      entrada.expiraEn = Math.max(entrada.expiraEn, ahora + CFG.MINIMO_VISIBLE_MS);
      entrada.duracion = entrada.expiraEn - ahora;
      mostrar(entrada);
    }
  }

  // --- Consulta al servidor -------------------------------------------------

  function consultar() {
    if (document.hidden) return;

    var visto = ultimoVisto();
    var url = box.dataset.url + (visto ? '?desde=' + encodeURIComponent(visto) : '');

    fetch(url, { headers: { 'Accept': 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (datos) {
        if (!datos.enabled) {
          // Lo apagaron desde otra pestaña: ya no hay nada que anunciar. Se sigue
          // preguntando igualmente (la consulta es barata) para notar en cuanto lo
          // vuelvan a activar, en vez de quedarse callado hasta recargar la página.
          cola = [];
          actual = null;
          retirar();
          return;
        }

        var eventos = datos.events || [];
        if (!eventos.length) return;

        // Se marca lo visto aunque algún paso sea demasiado viejo para anunciarlo: si
        // no, volvería en cada consulta.
        marcarVisto(eventos[eventos.length - 1].id);

        var ahora = Date.now();
        eventos.forEach(function (evento) {
          var edad = evento.ago || 0;
          if (edad > CFG.MAX_EDAD_S) return;
          // El instante de caducidad se calcula desde cuándo ocurrió DE VERDAD, no
          // desde cuándo llegó a esta pestaña. Por eso da igual en qué momento se abra
          // o se cambie de pestaña: el aviso dura lo que le queda, ni más ni menos.
          cola.push({
            evento: evento,
            expiraEn: ahora - edad * 1000 + CFG.DURACION_MS,
            duracion: CFG.DURACION_MS
          });
        });

        latido();
      })
      .catch(function () {
        // El programa puede estar reiniciándose. No se avisa de nada: un error de red
        // no es información que el mostrador necesite, y taparía la pantalla por algo
        // que se arregla solo en el siguiente ciclo.
      });
  }

  // Al volver a la pestaña se mira ya, sin esperar al siguiente ciclo, y se recalcula
  // todo: puede haber caducado lo que estaba en pantalla mientras no se miraba.
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) return;
    latido();
    consultar();
  });

  consultar();
  setInterval(latido, CFG.TICK_MS);
  setInterval(consultar, CFG.POLL_MS);
})();
