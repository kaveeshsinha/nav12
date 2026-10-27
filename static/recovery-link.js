/* A link's secret fragment is never sent in an HTTP URL or Referer header. */
(() => {
  const fragment = window.location.hash;
  if (!fragment) return;
  window.history.replaceState(null, '', window.location.pathname);
  const token = new URLSearchParams(fragment.slice(1)).get('token');
  const form = document.getElementById('recovery-link-form');
  if (!form || !token || !/^[A-Za-z0-9_-]{43}$/.test(token)) return;
  form.elements.namedItem('token').value = token;
  form.submit();
})();
