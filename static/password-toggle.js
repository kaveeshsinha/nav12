/* Progressive enhancement: passwords stay masked when JavaScript is unavailable. */
(() => {
  'use strict';
  document.querySelectorAll('[data-password-toggle]').forEach(button => {
    const input = document.getElementById(button.getAttribute('aria-controls'));
    if (!input || input.type !== 'password') return;
    const hide = () => {
      input.type = 'password';
      button.textContent = 'Show';
      button.setAttribute('aria-label', 'Show password');
      button.setAttribute('aria-pressed', 'false');
    };
    button.hidden = false;
    button.addEventListener('click', () => {
      if (input.type === 'text') { hide(); return; }
      input.type = 'text';
      button.textContent = 'Hide';
      button.setAttribute('aria-label', 'Hide password');
      button.setAttribute('aria-pressed', 'true');
    });
    input.form?.addEventListener('submit', hide);
    window.addEventListener('pageshow', hide);
  });
})();
