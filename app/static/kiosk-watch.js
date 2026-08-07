/* Aviso de la última entrada del kiosco, en las pantallas del programa.
 *
 * Quien atiende el mostrador trabaja en esta pestaña, no en la del kiosco. Sin esto
 * tendría que cambiar de pestaña para saber si a quien acaba de pasar se le permitió
 * la entrada, que es justo cuando hay que reaccionar.
 *
 * Aparece SOLO cuando alguien acaba de ser detectado —lo dejen entrar o no— y se
 * desvanece a los diez segundos: el resto del tiempo no debe tapar nada de la pantalla.
 *
 * En hora punta la gente entra en fila, más deprisa de lo que dura un aviso. Por eso
 * hay una COLA: el servidor devuelve todas las entradas que este navegador aún no ha
 * anunciado y se muestran una a una. Mientras queden pendientes cada una dura menos,
 * porque si no cinco personas seguidas significarían casi un minuto de avisos
 * arrastrándose por detrás de la realidad.
 *
 * Cada paso se anuncia una sola vez por sesión del navegador. Sin esa marca, cambiar
 * de página dentro de la misma ventana volvería a mostrar el aviso de alguien que ya
 * entró hace rato, que es peor que no mostrarlo.
 */
(function () {
  'use strict';

  var box = document.querySelector('[data-kiosk-watch]');
  if (!box) return;

  var CFG = {
    // Cada cuánto se pregunta al servidor. Con 4 s el aviso sale casi a la vez que la
    // persona cruza la puerta, sin cargar el equipo.
    POLL_MS: 4000,
    // Cuánto se queda en pantalla antes de empezar a irse.
    SHOW_MS: 10000,
    // Lo que dura cada aviso cuando hay más esperando detrás. Suficiente para leer
    // nombre y veredicto sin que la cola se descuelgue de lo que pasa en la puerta.
    SHOW_EN_COLA_MS: 3500,
    // Duración del desvanecido. Debe coincidir con la transición de styles.css.
    FADE_MS: 900,
    // Un paso más viejo que esto ya no se anuncia al cargar una página: interesa
    // avisar de lo que acaba de ocurrir, no de lo que pasó hace media hora.
    MAX_EDAD_S: 12
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

  var temporizadorOcultar = null;
  var temporizadorQuitar = null;
  var timerConsulta = null;

  var cola = [];            // entradas pendientes de anunciar, de la más vieja a la más nueva
  var mostrando = false;    // hay un aviso en pantalla ahora mismo
  // Verdadero mientras uno se está desvaneciendo. Sin este estado intermedio, la
  // consulta periódica puede sacar el siguiente de la cola durante el desvanecido y
  // el temporizador del anterior lo oculta nada más aparecer: la cola se vacía sola
  // sin que nadie llegue a verla.
  var cerrando = false;

  // --- Marca de lo ya anunciado --------------------------------------------

  function ultimoVisto() {
    try { return sessionStorage.getItem(CLAVE_VISTO); } catch (e) { return null; }
  }

  function marcarVisto(id) {
    try { sessionStorage.setItem(CLAVE_VISTO, String(id)); } catch (e) { /* modo privado */ }
  }

  // --- Aparecer y desaparecer ----------------------------------------------

  function ocultar(inmediato) {
    clearTimeout(temporizadorOcultar);
    clearTimeout(temporizadorQuitar);
    box.classList.remove('is-visible');
    mostrando = false;
    cerrando = true;

    var terminar = function () {
      box.hidden = true;
      cerrando = false;
      // Al acabar de irse, si alguien más pasó mientras tanto, le toca a él.
      siguiente();
    };

    if (inmediato) {
      terminar();
      return;
    }
    // Se espera al final del desvanecido para retirarlo del todo; si no, [hidden]
    // lo haría desaparecer de golpe y no se vería la transición.
    temporizadorQuitar = setTimeout(terminar, CFG.FADE_MS);
  }

  function mostrar(restanteMs) {
    clearTimeout(temporizadorOcultar);
    clearTimeout(temporizadorQuitar);
    mostrando = true;
    cerrando = false;

    box.hidden = false;
    // Forzar el cálculo de estilos entre quitar [hidden] y añadir la clase: sin esto
    // el navegador agrupa ambos cambios y no hay transición de entrada.
    void box.offsetWidth;
    box.classList.add('is-visible');

    // La barra se vacía en el tiempo que le quede al aviso.
    el.timer.style.transition = 'none';
    el.timer.style.width = '100%';
    void el.timer.offsetWidth;
    el.timer.style.transition = 'width ' + restanteMs + 'ms linear';
    el.timer.style.width = '0%';

    temporizadorOcultar = setTimeout(ocultar, restanteMs);
  }

  // Cerrar a mano descarta también lo que quede en cola: quien lo cierra quiere la
  // pantalla despejada, no el siguiente aviso acto seguido.
  el.close.addEventListener('click', function () {
    cola = [];
    ocultar(false);
  });

  // --- Cola -----------------------------------------------------------------

  function siguiente() {
    if (mostrando || cerrando || cola.length === 0) return;

    var evento = cola.shift();
    var quedan = cola.length;

    // El último de la tanda se queda el tiempo completo; los anteriores, lo justo
    // para leerlos, de modo que la cola no se descuelgue de lo que pasa en la puerta.
    var duracion = quedan > 0 ? CFG.SHOW_EN_COLA_MS : CFG.SHOW_MS;
    // Si la página se abrió con el aviso ya empezado, dura lo que le quedaba.
    duracion = Math.max(2000, duracion - (evento.ago || 0) * 1000);

    pintar(evento, quedan);
    mostrar(duracion);
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

    // Con gente en fila, decir cuántos faltan evita que parezca que el aviso
    // parpadea sin motivo.
    if (pendientes > 0) {
      el.pending.textContent = '+' + pendientes;
      el.pending.hidden = false;
    } else {
      el.pending.hidden = true;
    }
  }

  // --- Consulta -------------------------------------------------------------

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
          // Lo apagaron desde otra pestaña: ya no hay nada que anunciar.
          cola = [];
          ocultar(true);
          clearInterval(timerConsulta);
          return;
        }

        var eventos = datos.events || [];
        if (eventos.length === 0) return;

        // Se marca lo visto antes de decidir si se enseña: aunque un paso sea
        // demasiado viejo para anunciarlo, no debe volver a aparecer en la siguiente
        // consulta.
        marcarVisto(eventos[eventos.length - 1].id);

        // Sin `desde` el servidor manda solo la última: es una pantalla recién
        // abierta fijando su punto de partida. Si ese paso ya es viejo no se anuncia,
        // para no saltar por alguien que entró hace rato.
        eventos.forEach(function (evento) {
          if ((evento.ago || 0) <= CFG.MAX_EDAD_S) cola.push(evento);
        });

        siguiente();
      })
      .catch(function () {
        // El programa puede estar reiniciándose. No se avisa de nada: un error de red
        // no es información que el mostrador necesite, y taparía la pantalla por algo
        // que se arregla solo en el siguiente ciclo.
      });
  }

  // Al volver a la pestaña conviene mirar ya, sin esperar al siguiente ciclo.
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) consultar();
  });

  consultar();
  timerConsulta = setInterval(consultar, CFG.POLL_MS);
})();
