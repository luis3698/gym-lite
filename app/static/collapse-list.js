/* Listas plegables «ver más / ver menos».
 *
 * El servidor marca las tarjetas sobrantes con [data-extra] y [hidden], así que la
 * página ya carga plegada y no hay parpadeo. Aquí solo se alterna la visibilidad.
 *
 * Uso en la plantilla (macro `more_button` de _macros.html):
 *   <div id="mi-lista"> … <a data-extra hidden> … </div>
 *   <button data-toggle-more="mi-lista" data-more="Ver 10 más" data-less="Ver menos">
 */
(function () {
  'use strict';

  document.querySelectorAll('[data-toggle-more]').forEach(function (btn) {
    var box = document.getElementById(btn.dataset.toggleMore);
    if (!box) return;

    btn.addEventListener('click', function () {
      var open = btn.getAttribute('aria-expanded') === 'true';
      box.querySelectorAll('[data-extra]').forEach(function (item) {
        item.hidden = open;
      });
      btn.setAttribute('aria-expanded', String(!open));
      btn.textContent = open ? btn.dataset.more : btn.dataset.less;

      // Al plegar, la página se encoge de golpe y el botón puede quedar fuera de
      // la vista; se recoloca para no perder el punto de lectura.
      if (open) btn.scrollIntoView({ block: 'nearest' });
    });
  });
})();
