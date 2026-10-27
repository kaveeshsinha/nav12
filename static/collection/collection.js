/* Progressive enhancement only: navigation and GET filtering remain server-rendered. */
(() => {
  'use strict';
  const rows = [...document.querySelectorAll('[data-brand-row]')];
  document.addEventListener('nv:close-preview', () => closePreview());
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
    if (row.closest('[inert]')) return;
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
      openTimer = setTimeout(() => {
        if (row.closest('[data-explore-menu]')?.open !== false) openPreview(row);
      }, 100);
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
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    if (active) { event.preventDefault(); closePreview(true); return; }
  });
  addEventListener('resize', () => { if (active) position(active); });
  addEventListener('scroll', event => {
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


/* Shared navigation panel: stays in document flow while its contents change. */
(() => {
  'use strict';
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)');

  document.querySelectorAll('.nv-explore-nav').forEach((nav, navIndex) => {
    const items = [...nav.querySelectorAll('[data-explore-menu]')];
    if (!items.length || nav.querySelector('.nv-shared-menu')) return;

    const shell = document.createElement('div');
    shell.className = 'nv-shared-menu';
    nav.append(shell);
    let current = -1, closeTimer;
    const resetPreview = () => document.dispatchEvent(new Event('nv:close-preview'));
    const cancelClose = () => clearTimeout(closeTimer);

    const entries = items.map((item, index) => {
      const trigger = item.querySelector('summary');
      const panel = item.querySelector('[data-explore-panel]');
      const content = document.createElement('div');
      content.className = 'nv-shared-content';
      content.append(...panel.childNodes);
      panel.append(content);
      shell.append(panel);
      item.removeAttribute('name');
      item.open = false;
      panel.id ||= `nv-panel-${navIndex}-${index}`;
      trigger.id ||= `nv-trigger-${navIndex}-${index}`;
      trigger.setAttribute('aria-controls', panel.id);
      trigger.setAttribute('aria-expanded', 'false');
      panel.setAttribute('role', 'region');
      panel.setAttribute('aria-labelledby', trigger.id);
      panel.setAttribute('aria-hidden', 'true');
      panel.inert = true;
      return { item, trigger, panel, content };
    });

    function fitPanel() {
      if (current < 0) return;

      const { panel, content } = entries[current];
      const style = getComputedStyle(panel);
      const wanted = Math.ceil(
        content.scrollHeight
        + parseFloat(style.paddingTop)
        + parseFloat(style.paddingBottom)
      );
      const maxHeight = Math.floor(
        document.documentElement.clientHeight * 0.65
      );

      shell.style.height = `${Math.min(wanted, maxHeight)}px`;
    }

    function show(index) {
      cancelClose();
      if (current === index) return;
      const moveFocus = current >= 0 && entries[current].panel.contains(document.activeElement);
      resetPreview();
      current = index;
      entries.forEach(({ item, trigger, panel }, i) => {
        const selected = i === index;
        item.open = selected;
        trigger.setAttribute('aria-expanded', String(selected));
        panel.setAttribute('aria-hidden', String(!selected));
        panel.inert = !selected;
        panel.classList.toggle('is-active', selected);
      });
      if (moveFocus) entries[index].trigger.focus({ preventScroll: true });
      entries[index].panel.scrollTop = 0;
      fitPanel();
      nav.classList.add('nv-nav-open');
      shell.classList.add('is-open');
    }

    function close(restoreFocus = false) {
      cancelClose();
      if (current < 0) return;
      const trigger = entries[current].trigger;
      resetPreview();
      current = -1;
      entries.forEach(({ item, trigger, panel }) => {
        item.open = false;
        trigger.setAttribute('aria-expanded', 'false');
        panel.setAttribute('aria-hidden', 'true');
        panel.inert = true;
        panel.classList.remove('is-active');
      });
      shell.classList.remove('is-open');
      nav.classList.remove('nv-nav-open');
      shell.style.height = '0px';
      if (restoreFocus) trigger.focus({ preventScroll: true });
    }

    const focusable = panel => [...panel.querySelectorAll('input:not([disabled]), a[href], button:not([disabled])')]
      .filter(element => !element.closest('[inert], [hidden]') && element.getClientRects().length);

    entries.forEach(({ item, trigger, panel }, index) => {
      const clickOnly = item.hasAttribute('data-click-only');
      trigger.addEventListener('pointerenter', event => {
        if (!clickOnly && finePointer.matches && event.pointerType !== 'touch') show(index);
      });
      trigger.addEventListener('click', event => {
        event.preventDefault();
        const toggle = clickOnly || event.detail === 0 || event.pointerType === 'touch' || !finePointer.matches;
        if (current === index && toggle) close();
        else {
          show(index);
          if (clickOnly) focusable(panel)[0]?.focus({ preventScroll: true });
        }
      });
      trigger.addEventListener('keydown', event => {
        if (event.key === 'ArrowDown' ||
            (event.key === 'Tab' && !event.shiftKey && current === index)) {
          event.preventDefault();
          show(index);
          focusable(panel)[0]?.focus({ preventScroll: true });
        }
      });
      // Panels live in the shared shell, after the triggers in the DOM. Preserve
      // the expected trigger -> contents -> next trigger keyboard sequence.
      panel.addEventListener('keydown', event => {
        if (event.key !== 'Tab') return;
        const links = focusable(panel);
        if (event.shiftKey && event.target === links[0]) {
          event.preventDefault();
          trigger.focus({ preventScroll: true });
        } else if (!event.shiftKey && event.target === links[links.length - 1]) {
          const next = entries[index + 1]?.trigger || nav.querySelector('.nv-all-cars');
          if (next) {
            event.preventDefault();
            close();
            next.focus({ preventScroll: true });
          }
        }
      });
    });

    nav.addEventListener('pointerenter', cancelClose);
    nav.addEventListener('pointerleave', event => {
      if (!finePointer.matches || event.pointerType === 'touch') return;
      cancelClose();
      closeTimer = setTimeout(() => {
        if (!nav.matches(':hover') && !nav.contains(document.activeElement)) close();
      }, 260);
    });
    nav.addEventListener('focusout', () => {
      setTimeout(() => { if (!nav.contains(document.activeElement)) close(); }, 0);
    });
    document.addEventListener('pointerdown', event => {
      if (!nav.contains(event.target)) close();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !event.defaultPrevented && current >= 0) {
        event.preventDefault();
        close(true);
      }
    });
    addEventListener('resize', fitPanel);
    if ('ResizeObserver' in window) {
      const observer = new ResizeObserver(fitPanel);
      entries.forEach(({ content }) => observer.observe(content));
    }
  });
})();
