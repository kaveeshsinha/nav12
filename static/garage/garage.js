/* Progressive enhancement: the server also validates the comparison selection. */
(() => {
  'use strict';
  const form = document.querySelector('#garage-compare');
  if (!form) return;
  const picks = [...document.querySelectorAll('[data-compare-car]')];
  const status = form.querySelector('[data-compare-status]');
  const submit = form.querySelector('[data-compare-submit]');
  const update = () => {
    const count = picks.filter(input => input.checked).length;
    submit.disabled = count < 2 || count > 4;
    status.textContent = count > 4
      ? `${count} selected. Remove ${count - 4} to compare up to 4 cars.`
      : `${count} selected. Choose 2–4 cars to compare.`;
  };
  picks.forEach(input => input.addEventListener('change', update));
  window.addEventListener('pageshow', update);
  update();
})();
