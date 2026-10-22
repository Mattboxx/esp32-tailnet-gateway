// Apply a remembered colour theme before first paint. Storage is optional:
// without it the site follows the operating-system preference.
(function () {
  try {
    var t = localStorage.getItem('theme');
    if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
  } catch (e) { /* private mode or blocked storage */ }
})();
