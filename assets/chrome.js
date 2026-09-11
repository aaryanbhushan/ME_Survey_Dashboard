/* Shell behaviour, ported from the unified dashboard's base.html.

   Dash renders the layout after this file runs, so the listeners are attached
   by delegation on document rather than bound to elements that do not exist
   yet, and the theme is re-stamped whenever the DOM changes. */

(function () {
  var THEME_KEY = 'unified-theme';
  var SIDEBAR_KEY = 'sidebar-collapsed';

  function readTheme() {
    try {
      return localStorage.getItem(THEME_KEY) || 'light';
    } catch (e) {
      return 'light';                       // private windows throw on access
    }
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    var btn = document.getElementById('themeToggle');
    if (btn) btn.innerHTML = theme === 'dark' ? '☀' : '☾';
  }

  // Stamp before first paint so the page does not flash the light theme.
  applyTheme(readTheme());

  function applySidebar(collapsed) {
    var sidebar = document.getElementById('sidebar');
    var wrapper = document.getElementById('mainWrapper');
    if (sidebar) sidebar.classList.toggle('collapsed', collapsed);
    if (wrapper) wrapper.classList.toggle('sidebar-collapsed', collapsed);
  }

  function readSidebar() {
    try {
      return localStorage.getItem(SIDEBAR_KEY) === 'true';
    } catch (e) {
      return false;
    }
  }

  document.addEventListener('click', function (event) {
    var themeBtn = event.target.closest('#themeToggle');
    if (themeBtn) {
      var next = document.documentElement.getAttribute('data-theme') === 'dark'
        ? 'light' : 'dark';
      applyTheme(next);
      try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* ignore */ }
      return;
    }

    var toggle = event.target.closest('#topHamburger, #sidebarCollapseBtn');
    if (toggle) {
      var collapsed = !readSidebar();
      applySidebar(collapsed);
      try { localStorage.setItem(SIDEBAR_KEY, String(collapsed)); } catch (e) { /* ignore */ }
    }
  });

  // Dash mounts the shell asynchronously, so the sidebar's stored collapsed
  // state has to be re-applied once #sidebar exists.
  //
  // Deliberately NOT a MutationObserver on document.documentElement: this page
  // renders around a thousand table rows, and a subtree observer wakes on
  // every one of those mutations while the main thread is already saturated.
  // A handful of short polls costs nothing and stops as soon as the shell is
  // there (or after ~5s, if the page never mounts).
  var tries = 0;
  (function waitForShell() {
    if (document.getElementById('sidebar')) {
      applyTheme(document.documentElement.getAttribute('data-theme') || 'light');
      applySidebar(readSidebar());
      return;
    }
    if (++tries < 50) setTimeout(waitForShell, 100);
  })();
})();
