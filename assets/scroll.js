/* Keep your place when a selector changes the view.
 *
 * Every control on this dashboard is a link that rewrites the query string,
 * and Dash replaces the page body wholesale in response. The browser has no
 * reason to think that is anything but a new page, so it jumps to the top —
 * which meant picking a comparison cycle threw you back to the header and you
 * had to scroll down again to see what you had just changed.
 *
 * So: remember the scroll position when an in-page link is clicked, and put it
 * back once the new body has rendered. Sidebar navigation is deliberately
 * excluded — moving to a different page SHOULD start at the top.
 */
(function () {
  var KEY = 'me-scroll-y';
  var pending = false;

  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a') : null;
    if (!a) return;
    // A real page change starts at the top; a selector does not.
    if (a.classList.contains('sidebar-link')) return;
    if (!a.getAttribute('href')) return;
    try {
      sessionStorage.setItem(KEY, String(window.scrollY || window.pageYOffset || 0));
      pending = true;
    } catch (_) { /* private mode — fall back to the jump */ }
  }, true);

  function restore() {
    if (!pending) return;
    var v = null;
    try { v = sessionStorage.getItem(KEY); } catch (_) { return; }
    if (v === null) return;
    pending = false;
    // Two frames: the first lets Dash paint the new body so the document is
    // tall enough to scroll to, the second survives late-loading web fonts
    // reflowing it underneath us.
    requestAnimationFrame(function () {
      window.scrollTo(0, parseFloat(v));
      requestAnimationFrame(function () { window.scrollTo(0, parseFloat(v)); });
    });
  }

  function watch() {
    var body = document.getElementById('page-body');
    if (!body) { setTimeout(watch, 200); return; }
    new MutationObserver(restore).observe(body, { childList: true, subtree: false });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', watch);
  } else {
    watch();
  }
})();
