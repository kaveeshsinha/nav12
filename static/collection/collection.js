/* Progressive enhancement only: navigation and GET filtering remain server-rendered. */
(() => {
  'use strict';
  const rows = [...document.querySelectorAll('[data-brand-row]')];
  const menus = [...document.querySelectorAll('[data-explore-menu]')];
  let active = null, openTimer, closeTimer, restoringFocus = false, keyboardNavigation = false;
  document.addEventListener('keydown', event => { if (event.key === 'Tab') keyboardNavigation = true; }, true);
  document.addEventListener('pointerdown', () => { keyboardNavigation = false; }, true);
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
  const panelFor = row => row.querySelector('.nv-brand-preview');
  const toggleFor = row => row.querySelector('.nv-preview-toggle');
  function clearTimers() { clearTimeout(openTimer); clearTimeout(closeTimer); }
  function closePreview(restore = false) {
    clearTimers();
    if (!active) return;
    const row = active;
    panelFor(row).hidden = true;
    toggleFor(row).setAttribute('aria-expanded', 'false');
    active = null;
    if (restore) {
      restoringFocus = true;
      toggleFor(row).focus({preventScroll: true});
      restoringFocus = false;
    }
  }
  function position(row) {
    const panel = panelFor(row), anchor = row.getBoundingClientRect();
    const margin = 16, gap = 10;
    const width = panel.offsetWidth, height = panel.offsetHeight;
    let left = anchor.right + gap;
    if (left + width > innerWidth - margin) left = anchor.left - width - gap;
    left = Math.max(margin, Math.min(left, innerWidth - width - margin));
    const top = Math.max(margin, Math.min(anchor.top, innerHeight - height - margin));
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
  }
  function openPreview(row) {
    clearTimers();
    if (active !== row) closePreview();
    active = row;
    const panel = panelFor(row);
    panel.hidden = false;
    toggleFor(row).setAttribute('aria-expanded', 'true');
    position(row);
  }
  rows.forEach(row => {
    const toggle = toggleFor(row), panel = panelFor(row);
    toggle.hidden = false;
    row.addEventListener('pointerenter', event => {
      if (!finePointer.matches || event.pointerType === 'touch') return;
      clearTimers();
      openTimer = setTimeout(() => openPreview(row), 100);
    });
    row.addEventListener('pointerleave', () => {
      clearTimers();
      if (!row.contains(document.activeElement)) closeTimer = setTimeout(() => { if (active === row && !row.contains(document.activeElement)) closePreview(); }, 200);
    });
    row.addEventListener('focusin', event => {
      if (restoringFocus || event.target === toggle || panel.contains(event.target)) return;
      // Touch focus precedes click: do not put a panel over a direct navigation target.
      if (!finePointer.matches && !keyboardNavigation) return;
      openPreview(row);
    });
    row.addEventListener('focusout', () => {
      setTimeout(() => { if (active === row && !row.contains(document.activeElement)) closePreview(); }, 0);
    });
    toggle.addEventListener('click', () => active === row ? closePreview() : openPreview(row));
    panel.querySelector('.nv-preview-close').addEventListener('click', () => closePreview(true));
    panel.addEventListener('pointerenter', clearTimers);
  });
  document.addEventListener('pointerdown', event => {
    if (active && !active.contains(event.target)) closePreview();
    menus.filter(menu => menu.open).forEach(menu => {
      if (!menu.contains(event.target)) menu.open = false;
    });
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    if (active) { event.preventDefault(); closePreview(true); return; }
    const menu = menus.find(menu => menu.open);
    if (menu) { event.preventDefault(); menu.open = false; menu.querySelector('summary').focus({preventScroll: true}); }
  });
  function positionMenu(menu) {
    const panel = menu.querySelector('[data-explore-panel]');
    const anchor = menu.querySelector('summary').getBoundingClientRect();
    const margin = 16;
    const top = Math.max(margin, Math.min(anchor.bottom + 10, innerHeight - 220));
    const left = Math.max(margin, Math.min(anchor.left, innerWidth - panel.offsetWidth - margin));
    panel.style.setProperty('--nv-menu-left', `${left}px`);
    panel.style.setProperty('--nv-menu-top', `${top}px`);
    panel.style.setProperty('--nv-menu-height', `${Math.max(0, innerHeight - top - margin)}px`);
  }
  menus.forEach(menu => {
    menu.addEventListener('toggle', () => {
      if (menu.open) {
        menus.forEach(other => { if (other !== menu) other.open = false; });
        closePreview();
        positionMenu(menu);
      }
      if (!menu.open && active && menu.contains(active)) closePreview();
    });
    menu.addEventListener('focusout', () => {
      setTimeout(() => { if (menu.open && !menu.contains(document.activeElement)) menu.open = false; }, 0);
    });
  });
  addEventListener('resize', () => {
    menus.filter(menu => menu.open).forEach(positionMenu);
    if (active) position(active);
  });
  addEventListener('scroll', event => {
    menus.filter(menu => menu.open).forEach(menu => {
      if (menu.querySelector('[data-explore-panel]').contains(event.target)) return;
      const anchor = menu.querySelector('summary').getBoundingClientRect();
      if (anchor.bottom < 0 || anchor.top > innerHeight || anchor.right < 0 || anchor.left > innerWidth) menu.open = false;
      else positionMenu(menu);
    });
    // Scrolling the preview itself must not dismiss it.
    if (active && !panelFor(active).contains(event.target)) {
      if (active.contains(document.activeElement)) position(active);
      else closePreview();
    }
  }, true);
  document.querySelectorAll('.nv-photo img').forEach(img => {
    const fail = () => {
      const frame = img.closest('.nv-photo');
      frame.querySelector('.nv-photo-error').hidden = false;
      img.closest('picture').hidden = true;
    };
    img.addEventListener('error', fail);
    if (img.complete && img.naturalWidth === 0) fail();
  });

  const dialog = document.querySelector('.nv-lightbox');
  const links = [...document.querySelectorAll('[data-gallery-image]')];
  if (!dialog || typeof dialog.showModal !== 'function' || !links.length) return;
  const image = dialog.querySelector('img');
  const caption = dialog.querySelector('[data-gallery-caption]');
  let current = 0, returnFocus = null;
  function display(index) {
    current = (index + links.length) % links.length;
    const link = links[current];
    image.src = link.href;
    image.alt = link.dataset.caption;
    caption.textContent = link.dataset.caption;
    dialog.querySelector('[data-gallery-counter]').textContent = `${current + 1} / ${links.length}`;
  }
  image.addEventListener('error', () => { caption.textContent = 'This photograph could not load. Close the viewer to continue browsing.'; });
  links.forEach((link, index) => link.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    returnFocus = link;
    display(index);
    dialog.showModal();
    dialog.querySelector('[data-gallery-close]').focus();
  }));
  dialog.querySelector('[data-gallery-close]').addEventListener('click', () => dialog.close());
  dialog.querySelector('[data-gallery-prev]').addEventListener('click', () => display(current - 1));
  dialog.querySelector('[data-gallery-next]').addEventListener('click', () => display(current + 1));
  dialog.querySelector('.nv-lightbox-controls').hidden = links.length < 2;
  dialog.addEventListener('keydown', event => {
    if (event.key === 'ArrowRight') { event.preventDefault(); display(current + 1); }
    if (event.key === 'ArrowLeft') { event.preventDefault(); display(current - 1); }
    if (event.key === 'Escape') event.stopPropagation();
  });
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
  dialog.addEventListener('close', () => returnFocus?.focus({preventScroll: true}));
})();
