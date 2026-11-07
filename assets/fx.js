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

    // Reading progress bar and a back-to-top button for the main scroll area.
    var bar = document.createElement('div');
    bar.id = 'ss-progress';
    document.body.appendChild(bar);
    var top = document.createElement('button');
    top.id = 'ss-top';
    top.type = 'button';
    top.textContent = '↑';
    document.body.appendChild(top);
    var scroller = null;
    document.addEventListener('scroll', function (e) {
      var el = e.target === document ? document.scrollingElement : e.target;
      if (!el || !el.querySelector || !(el === document.scrollingElement || el.querySelector('[data-testid="stMainBlockContainer"]'))) return;
      scroller = el;
      var max = el.scrollHeight - el.clientHeight;
      bar.style.transform = 'scaleX(' + (max > 0 ? el.scrollTop / max : 0) + ')';
      top.classList.toggle('show', el.scrollTop > 900);
    }, true);
    top.addEventListener('click', function () {
      if (scroller) scroller.scrollTo({top: 0, behavior: reduce ? 'auto' : 'smooth'});
      top.blur();
    });
    setInterval(function () {  // label follows the page language
      var idx = document.getElementById('ss-index');
      var text = idx && idx.getAttribute('data-top');
      if (text && top.getAttribute('aria-label') !== text) { top.setAttribute('aria-label', text); top.title = text; }
    }, 1000);

    // Theme: the server already applied a saved choice; this flips it instantly and saves it for next time.
    document.addEventListener('click', function (e) {
      if (!(e.target.closest && e.target.closest('.ss-theme'))) return;
      var root = document.documentElement;
      var dark = getComputedStyle(root).getPropertyValue('--paper').trim().toLowerCase() === '#0f0f0e';
      root.classList.remove('ss-dark', 'ss-light');
      root.classList.add(dark ? 'ss-light' : 'ss-dark');
      document.cookie = 'ss_theme=' + (dark ? 'light' : 'dark') + '; path=/; max-age=63072000; SameSite=Lax';
    });

    // ---------- Slide viewer (markup comes from deck() in app.py) ----------
    function current(deck) { return +(deck.dataset.i || deck.dataset.start || 1); }
    function show(deck, i) {
      var n = +deck.dataset.total, base = deck.dataset.base;
      i = Math.max(1, Math.min(n, i));
      if (i === current(deck) && deck.dataset.i) return;
      deck.dataset.i = i;
      deck.querySelector('.deck-img').src = base + i + '.webp';
      deck.querySelector('.deck-count b').textContent = String(i).padStart(2, '0');
      deck.querySelector('.deck-progress i').style.width = (100 * i / n) + '%';
      deck.querySelectorAll('.deck-thumb').forEach(function (t) {
        var on = +t.dataset.i === i;
        t.classList.toggle('on', on);
        if (on) {  // keep the active preview visible without moving the page
          var strip = t.parentElement;
          strip.scrollTo({left: t.offsetLeft - strip.clientWidth / 2 + t.clientWidth / 2, behavior: reduce ? 'auto' : 'smooth'});
        }
      });
      if (i < n) { var next = new Image(); next.src = base + (i + 1) + '.webp'; }  // preload
    }
    function fullscreen(deck) {
      if (document.fullscreenElement) { document.exitFullscreen(); return; }
      if (deck.requestFullscreen) deck.requestFullscreen().catch(function () { deck.classList.toggle('pseudo-full'); });
      else deck.classList.toggle('pseudo-full');  // iPhone Safari has no element fullscreen
    }
    document.addEventListener('click', function (e) {
      var deck = e.target.closest && e.target.closest('.deck');
      if (!deck) return;
      var thumb = e.target.closest('.deck-thumb');
      if (thumb) show(deck, +thumb.dataset.i);
      else if (e.target.closest('.deck-prev')) show(deck, current(deck) - 1);
      else if (e.target.closest('.deck-next')) show(deck, current(deck) + 1);
      else if (e.target.closest('.deck-full')) fullscreen(deck);
      else if (e.target.closest('.deck-img')) {  // click on the slide: left third back, rest forward
        var r = e.target.getBoundingClientRect();
        show(deck, current(deck) + (e.clientX - r.left < r.width / 3 ? -1 : 1));
      }
    });
    document.addEventListener('keydown', function (e) {
      var deck = document.querySelector('.deck'), a = document.activeElement;
      if (!deck || (pal && pal.classList.contains('open')) || (a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName))) return;
      if (e.key === 'ArrowRight' || e.key === 'PageDown') { show(deck, current(deck) + 1); e.preventDefault(); }
      else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { show(deck, current(deck) - 1); e.preventDefault(); }
      else if (e.key === 'Home') { show(deck, 1); e.preventDefault(); }
      else if (e.key === 'End') { show(deck, +deck.dataset.total); e.preventDefault(); }
      else if (e.code === 'KeyF' && !e.ctrlKey && !e.metaKey) fullscreen(deck);
      else if (e.key === 'Escape') deck.classList.remove('pseudo-full');
    });
    var swipeX = null;
    document.addEventListener('pointerdown', function (e) {
      swipeX = e.target.closest && e.target.closest('.deck-stage') ? e.clientX : null;
    }, {passive: true});
    document.addEventListener('pointerup', function (e) {
      if (swipeX === null) return;
      var dx = e.clientX - swipeX, deck = e.target.closest && e.target.closest('.deck');
      swipeX = null;
      if (deck && Math.abs(dx) > 50) show(deck, current(deck) + (dx < 0 ? 1 : -1));
    }, {passive: true});

    // A click anywhere on an index row or a language panel acts like its button.
    document.addEventListener('click', function (e) {
      if (!e.target.closest) return;
      var row = e.target.closest('[class*="st-key-row_"], [class*="st-key-langpanel_"], [class*="st-key-card_"]');
      if (!row || e.target.closest('button, a, input, textarea, select, [role="button"]')) return;
      if (window.getSelection && String(window.getSelection())) return;  // let people select text
      var btn = row.querySelector('[data-testid="stButton"] button');
      if (btn) btn.click();
    });

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

    // Loading bar while Streamlit reruns (stale elements are marked until the new page arrives).
    var busy = document.createElement('div');
    busy.id = 'ss-busy';
    document.body.appendChild(busy);
    setInterval(function () {
      document.documentElement.classList.toggle('ss-busy', !!document.querySelector('[data-stale="true"]'));
    }, 120);

    // "Studied" marks: the server renders the current list into #ss-done; keep the cookie equal to it.
    var lastDone = null;
    setInterval(function () {
      var el = document.getElementById('ss-done');
      if (!el) return;
      var value = el.getAttribute('data-done') || '';
      if (value === lastDone) return;
      lastDone = value;
      document.cookie = 'ss_done=' + encodeURIComponent(value) + '; path=/; max-age=63072000; SameSite=Lax';
    }, 400);

    // ---------- Search palette: "/" or Ctrl/Cmd+K anywhere, or the search button in the top bar ----------
    var pal = null, results = [], active = 0;
    var fullText = null, fullTextNorm = {}, fullTextState = 'idle';
    function loadFullText(url) {
      // The server builds this index in the background; until it exists, titles alone are searched.
      if (fullTextState !== 'idle' || !url) return;
      fullTextState = 'loading';
      fetch(url + '?v=' + Date.now()).then(function (r) { return r.ok ? r.json() : null; }).then(function (data) {
        fullText = data && typeof data === 'object' ? data : null;
        fullTextState = fullText ? 'ready' : 'idle';
        if (fullText) Object.keys(fullText).forEach(function (u) { fullTextNorm[u] = norm(fullText[u]); });
        if (pal && pal.classList.contains('open')) render();
      }).catch(function () { fullTextState = 'idle'; });
    }
    function norm(x) { return (x || '').toLowerCase().replace(/ё/g, 'е'); }
    function indexData() {
      var el = document.getElementById('ss-index');
      if (!el) return null;
      try {
        return {lang: el.dataset.lang, ph: el.dataset.ph, empty: el.dataset.empty, ft: el.dataset.ft,
                inText: el.dataset.inText, slide: el.dataset.slide || 'slide', items: JSON.parse(el.dataset.items || '[]')};
      }
      catch (e) { return null; }
    }
    function build() {
      pal = document.createElement('div');
      pal.id = 'ss-palette';
      pal.setAttribute('role', 'dialog');
      pal.setAttribute('aria-modal', 'true');
      pal.innerHTML = '<div class="ss-pal-box"><div class="ss-pal-head"><span class="ss-pal-icon">⌕</span>' +
        '<input type="text" autocomplete="off" spellcheck="false" aria-label="Search"><kbd>Esc</kbd></div>' +
        '<ul class="ss-pal-list" role="listbox"></ul>' +
        '<div class="ss-pal-foot"><span><kbd>↑</kbd><kbd>↓</kbd></span><span><kbd>Enter</kbd></span><span><kbd>Esc</kbd></span></div></div>';
      document.body.appendChild(pal);
      pal.addEventListener('mousedown', function (e) { if (e.target === pal) close(); });
      var input = pal.querySelector('input');
      input.addEventListener('input', render);
      input.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowDown') { active = Math.min(active + 1, results.length - 1); paint(); e.preventDefault(); }
        else if (e.key === 'ArrowUp') { active = Math.max(active - 1, 0); paint(); e.preventDefault(); }
        else if (e.key === 'Enter') { go(results[active]); e.preventDefault(); }
        else if (e.key === 'Escape') { close(); e.preventDefault(); }
      });
    }
    function open() {
      var data = indexData();
      if (!data) return;
      if (!pal) build();
      pal.data = data;
      var input = pal.querySelector('input');
      input.placeholder = data.ph;
      input.value = '';
      pal.classList.add('open');
      loadFullText(data.ft);
      render();
      setTimeout(function () { input.focus(); }, 0);
    }
    function close() { if (pal) pal.classList.remove('open'); }
    function go(item) { if (item) { close(); location.search = item.u; } }
    function render() {
      var data = pal.data, q = norm(pal.querySelector('input').value.trim());
      var words = q.split(/\s+/).filter(Boolean), scored = [];
      data.items.forEach(function (it, order) {
        var hay = norm(it.t + ' ' + it.s + ' ' + it.k);
        if (!words.every(function (w) { return hay.indexOf(w) >= 0; })) return;
        // Current language first, then title prefix matches, then courses before files when nothing is typed.
        var score = (it.l === data.lang ? 0 : 100) + (q && norm(it.t).indexOf(q) === 0 ? 0 : 10) + (!q && !it.c ? 1 : 0);
        scored.push([score, order, it]);
      });
      // Then files whose text (not title) contains every word, with a snippet around the first hit.
      if (fullText && q.length >= 3) {
        var seen = {};
        scored.forEach(function (x) { seen[x[2].u] = 1; });
        data.items.forEach(function (it, order) {
          var body = fullTextNorm[it.u];
          if (seen[it.u] || !body || !words.every(function (w) { return body.indexOf(w) >= 0; })) return;
          var at = body.indexOf(words[0]), text = fullText[it.u];
          var from = Math.max(0, at - 50), snippet = (from ? '…' : '') + text.slice(from, at + 110).replace(/\f/g, ' ').trim() + '…';
          // Pages are separated by \f in the index: the number of breaks before the hit is the slide.
          var page = text.slice(0, at).split('\f').length, multi = text.indexOf('\f') >= 0;
          scored.push([(it.l === data.lang ? 50 : 150), order, {
            t: it.t, s: it.s, l: it.l, snip: snippet,
            k: data.inText + ' · ' + (multi ? data.slide + ' ' + page : it.k),
            u: it.u + (multi ? '&slide=' + page : '')}]);
        });
      }
      scored.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
      results = scored.slice(0, 9).map(function (x) { return x[2]; });
      active = 0;
      var ul = pal.querySelector('ul');
      ul.innerHTML = '';
      if (!results.length) {
        var none = document.createElement('li');
        none.className = 'ss-pal-empty';
        none.textContent = data.empty;
        ul.appendChild(none);
        return;
      }
      results.forEach(function (it, i) {
        var li = document.createElement('li');
        li.setAttribute('role', 'option');
        var kick = document.createElement('span');
        kick.className = 'k';
        kick.textContent = it.k + (it.s ? '  —  ' + it.s : '');
        var title = document.createElement('b');
        highlight(title, it.t, words);
        var lang = document.createElement('i');
        lang.textContent = it.l.toUpperCase();
        li.appendChild(kick); li.appendChild(title); li.appendChild(lang);
        if (it.snip) {
          var snip = document.createElement('span');
          snip.className = 'snip';
          highlight(snip, it.snip, words);
          li.appendChild(snip);
        }
        li.addEventListener('mousemove', function () { if (active !== i) { active = i; paint(); } });
        li.addEventListener('click', function () { go(it); });
        ul.appendChild(li);
      });
      paint();
    }
    function paint() {
      pal.querySelectorAll('li[role=option]').forEach(function (li, i) {
        li.classList.toggle('on', i === active);
        if (i === active) li.scrollIntoView({block: 'nearest'});
      });
    }
    function highlight(el, text, words) {
      // Text nodes only (titles come from file names); first matching word is marked.
      var n = norm(text), w = null;
      for (var j = 0; j < words.length; j++) if (n.indexOf(words[j]) >= 0) { w = words[j]; break; }
      if (!w || n.length !== text.length) { el.textContent = text; return; }
      var i = n.indexOf(w), m = document.createElement('mark');
      m.textContent = text.slice(i, i + w.length);
      el.appendChild(document.createTextNode(text.slice(0, i)));
      el.appendChild(m);
      el.appendChild(document.createTextNode(text.slice(i + w.length)));
    }
    document.addEventListener('click', function (e) {
      if (e.target.closest && e.target.closest('.ss-search')) { e.preventDefault(); open(); }
    });
    document.addEventListener('keydown', function (e) {
      var a = document.activeElement;
      var typing = a && (/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) || a.isContentEditable);
      // e.code is layout-independent: works with the Russian/Kazakh keyboard too.
      if ((e.ctrlKey || e.metaKey) && e.code === 'KeyK') { e.preventDefault(); open(); }
      else if (!typing && !e.ctrlKey && !e.metaKey && !e.altKey && (e.key === '/' || e.code === 'Slash')) { e.preventDefault(); open(); }
      else if (e.key === 'Escape') close();
    });
  }
})();
