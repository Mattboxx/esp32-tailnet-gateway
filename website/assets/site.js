// Navigation, theme toggle, copy buttons and client-side search.
// No network requests: the search index ships as search-index.js.
(function () {
  var doc = document.documentElement;

  var menu = document.querySelector('.menu'), nav = document.getElementById('site-nav');
  if (menu && nav) menu.addEventListener('click', function () {
    var open = nav.classList.toggle('open');
    menu.setAttribute('aria-expanded', open ? 'true' : 'false');
  });

  var theme = document.querySelector('.theme');
  if (theme) theme.addEventListener('click', function () {
    var current = doc.getAttribute('data-theme') ||
      (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    var next = current === 'light' ? 'dark' : 'light';
    doc.setAttribute('data-theme', next);
    try { localStorage.setItem('theme', next); } catch (e) { /* optional */ }
  });

  document.querySelectorAll('pre > code').forEach(function (code) {
    var button = document.createElement('button');
    button.type = 'button'; button.className = 'copy'; button.textContent = 'Copy';
    button.addEventListener('click', function () {
      var done = function (ok) { button.textContent = ok ? 'Copied' : 'Select and copy'; setTimeout(function () { button.textContent = 'Copy'; }, 1800); };
      if (navigator.clipboard) navigator.clipboard.writeText(code.innerText).then(function () { done(true); }, function () { done(false); });
      else done(false);
    });
    code.parentNode.appendChild(button);
  });

  var panel = document.querySelector('.search-panel'), input = document.getElementById('search-input'),
      results = document.getElementById('search-results'), opener = document.querySelector('.search-open');
  var root = (document.querySelector('.brand') || {}).getAttribute ? document.querySelector('.brand').getAttribute('href') : './';
  function openSearch() { panel.hidden = false; input.focus(); }
  function closeSearch() { panel.hidden = true; if (opener) opener.focus(); }
  function escapeHtml(s) { return s.replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  function search(q) {
    var words = q.toLowerCase().split(/\s+/).filter(Boolean), index = window.SEARCH_INDEX || [];
    if (!words.length) { results.innerHTML = ''; return; }
    var hits = index.map(function (p) {
      var t = p.t.toLowerCase(), d = p.d.toLowerCase(), x = p.x.toLowerCase(), score = 0;
      for (var i = 0; i < words.length; i++) {
        var w = words[i], s = (t.indexOf(w) >= 0 ? 8 : 0) + (d.indexOf(w) >= 0 ? 4 : 0) + (x.indexOf(w) >= 0 ? 1 : 0);
        if (!s) return null; score += s;
      }
      return {p: p, s: score};
    }).filter(Boolean).sort(function (a, b) { return b.s - a.s; }).slice(0, 8);
    results.innerHTML = hits.length ? hits.map(function (h) {
      return '<li><a href="' + root + h.p.u + '">' + escapeHtml(h.p.t) + '</a><small>' + escapeHtml(h.p.d) + '</small></li>';
    }).join('') : '<li>No results. Try a different word.</li>';
  }
  if (panel && input) {
    if (opener) opener.addEventListener('click', openSearch);
    panel.querySelector('.search-close').addEventListener('click', closeSearch);
    input.addEventListener('input', function () { search(input.value); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !panel.hidden) closeSearch();
      if (e.key === '/' && panel.hidden && !/input|textarea/i.test((e.target || {}).tagName || '')) { e.preventDefault(); openSearch(); }
    });
  }
})();
