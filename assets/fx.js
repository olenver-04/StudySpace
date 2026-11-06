// StudySpace interactive effects. Loaded through components.html (a same-origin iframe)
// and copied into the main page once, so listeners survive Streamlit reruns.
(function () {
  try {
    var doc = window.parent.document;
    if (doc.getElementById('ss-fx')) return;
    var s = doc.createElement('script');
    s.id = 'ss-fx';
    s.textContent = '(' + main.toString() + ')();';
    doc.head.appendChild(s);
  } catch (e) { /* parent not reachable: the site simply runs without effects */ }

  function main() {
    var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    var fine = matchMedia('(pointer: fine)').matches;
    var CARD = ':scope > [data-testid="stElementContainer"] :is(.language-card, .course-card-body, .material-card-body)';

    // Reading progress bar for the main scroll area.
    var bar = document.createElement('div');
    bar.id = 'ss-progress';
    document.body.appendChild(bar);
    document.addEventListener('scroll', function (e) {
      var el = e.target === document ? document.scrollingElement : e.target;
      if (!el || !el.querySelector || !(el === document.scrollingElement || el.querySelector('[data-testid="stMainBlockContainer"]'))) return;
      var max = el.scrollHeight - el.clientHeight;
      bar.style.transform = 'scaleX(' + (max > 0 ? el.scrollTop / max : 0) + ')';
    }, true);

    // Streamlit keeps the scroll position between "pages"; jump to the top when the address changes.
    var lastSearch = location.search;
    setInterval(function () {
      if (location.search === lastSearch) return;
      lastSearch = location.search;
      // Instant, and once more after the rerun redraws (a smooth scroll gets cut off by the redraw).
      var toTop = function () {
        [document.scrollingElement, document.querySelector('[data-testid="stMain"]'), document.querySelector('[data-testid="stAppViewContainer"]')]
          .forEach(function (el) { if (el) el.scrollTop = 0; });
      };
      toTop();
      setTimeout(toTop, 600);
    }, 250);

    // Count-up for statistics; new nodes appear after every navigation.
    function countUp() {
      document.querySelectorAll('[data-count]:not([data-counted])').forEach(function (el) {
        el.setAttribute('data-counted', '1');
        var end = parseInt(el.getAttribute('data-count'), 10) || 0;
        if (reduce || !end) return;
        var t0 = performance.now();
        (function step(now) {
          var p = Math.min(1, (now - t0) / 1200);
          el.textContent = String(Math.round(end * (1 - Math.pow(1 - p, 3)))).padStart(2, '0');
          if (p < 1) requestAnimationFrame(step);
        })(t0);
      });
    }
    new MutationObserver(countUp).observe(document.body, {childList: true, subtree: true});
    countUp();

    if (reduce || !fine) return;

    // Soft light that trails the cursor.
    var glow = document.createElement('div');
    glow.id = 'ss-glow';
    document.body.appendChild(glow);
    var x = -999, y = -999, gx = x, gy = y;
    addEventListener('pointermove', function (e) { x = e.clientX; y = e.clientY; }, {passive: true});
    (function loop() {
      gx += (x - gx) * 0.12; gy += (y - gy) * 0.12;
      glow.style.transform = 'translate(' + gx + 'px,' + gy + 'px)';
      requestAnimationFrame(loop);
    })();

    // 3D tilt + spotlight on cards.
    var current = null;
    function findCard(t) {
      for (var el = t; el && el !== document.body; el = el.parentElement) {
        if (el.getAttribute && el.getAttribute('data-testid') === 'stVerticalBlock' && el.querySelector(CARD)) return el;
      }
      return null;
    }
    function reset(c) {
      c.classList.remove('ss-tilt');
      c.style.transform = '';
      c.style.removeProperty('--mx');
      c.style.removeProperty('--my');
    }
    document.addEventListener('pointermove', function (e) {
      var card = findCard(e.target);
      if (current && current !== card) reset(current);
      current = card;
      if (!card) return;
      var r = card.getBoundingClientRect();
      var px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
      card.classList.add('ss-tilt');
      card.style.setProperty('--mx', (px * 100) + '%');
      card.style.setProperty('--my', (py * 100) + '%');
      card.style.transform = 'perspective(1000px) rotateX(' + ((0.5 - py) * 6) + 'deg) rotateY(' + ((px - 0.5) * 8) + 'deg) translateY(-6px)';
    }, {passive: true});
    document.addEventListener('pointerleave', function () { if (current) { reset(current); current = null; } });
  }
})();
