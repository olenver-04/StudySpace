// StudySpace page helpers. Loaded through st.iframe (a same-origin iframe)
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

    // "Recently opened": material ids kept in a cookie so the server can read them on the next visit.
    function rememberMaterial() {
      var id = new URLSearchParams(location.search).get('material');
      if (!id) return;
      var match = document.cookie.match(/(?:^|; )ss_recent=([^;]*)/);
      var list = match ? decodeURIComponent(match[1]).split('|').filter(Boolean) : [];
      list = [id].concat(list.filter(function (x) { return x !== id; })).slice(0, 8);
      var value = encodeURIComponent(list.join('|'));
      while (value.length > 3500 && list.length > 1) { list.pop(); value = encodeURIComponent(list.join('|')); }
      document.cookie = 'ss_recent=' + value + '; path=/; max-age=31536000; SameSite=Lax';
    }
    var lastRecent = location.search;
    rememberMaterial();
    setInterval(function () { if (location.search !== lastRecent) { lastRecent = location.search; rememberMaterial(); } }, 500);

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
  }
})();
