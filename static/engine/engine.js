const body = document.body;
const reducedPreference = matchMedia('(prefers-reduced-motion: reduce)');
const byId = id => document.getElementById(id);
const readSetting = key => { try { return sessionStorage.getItem(key); } catch { return null; } };
const writeSetting = (key, value) => { try { sessionStorage.setItem(key, value); } catch { /* Storage is optional. */ } };
let reduced = reducedPreference.matches || readSetting('nav12-motion') === 'reduced';
let scene = null, scenePromise = null, sceneFailed = false, exploring = false, breath = false, chapter = -1, scrollFrame = 0;
let audioContext = null, audioGain = null, audioNodes = [], soundEnabled = false, soundStarting = false;
const sections = [...document.querySelectorAll('[data-chapter]')];
const labels = ['Ignition', 'Architecture', 'The breath', 'The rhythm', 'The machines'];
const canvas = byId('engine-canvas');
const menu = byId('engine-menu');
const status = byId('scene-status');

function setStatus(text) { if (status) status.textContent = text; }
function setExplore(value) {
  exploring = value && Boolean(scene) && !sceneFailed && !reduced;
  body.classList.toggle('is-exploring', exploring);
  byId('explore-toggle')?.setAttribute('aria-pressed', String(exploring));
  const text = byId('explore-toggle')?.querySelector('[data-button-label]');
  if (text) text.textContent = exploring ? 'Return to story' : 'Explore freely';
  if (canvas) { canvas.tabIndex = exploring ? 0 : -1; canvas.setAttribute('role', exploring ? 'application' : 'img'); }
  scene?.setExploring(exploring);
  if (byId('view-control-note')) byId('view-control-note').textContent = exploring ? 'Drag to rotate. Arrow keys turn the view. Escape returns to the story.' : 'Enter the studio to rotate the engine.';
  if (exploring) setStatus('Free inspection · drag or use arrow keys');
  else setStatus(scene ? 'Interactive engine study' : 'Engine study');
}
function setBreath(value) {
  breath = value && Boolean(scene) && !sceneFailed && !reduced;
  byId('cycle-toggle')?.setAttribute('aria-pressed', String(breath));
  body.classList.toggle('is-breathing', breath);
  scene?.setBreath(breath);
  if (breath) setStatus('Air path · a slow illustrative sequence');
  else if (scene && !sceneFailed && !reduced) setStatus('Interactive engine study');
}
function updateScroll() {
  scrollFrame = 0;
  const viewport = window.innerHeight;
  const offsets = sections.map(section => section.getBoundingClientRect().top + window.scrollY);
  const position = window.scrollY;
  let active = 0;
  for (let i = 0; i < offsets.length; i++) if (position >= offsets[i] - viewport * .4) active = i;
  let segment = 0;
  for (let i = 0; i < offsets.length - 1; i++) if (position >= offsets[i]) segment = i;
  const distance = offsets[segment + 1] - offsets[segment] || viewport;
  const progress = Math.max(0, Math.min(4, segment + (position - offsets[segment]) / distance));
  if (chapter !== active) {
    if (exploring) setExplore(false);
    if (breath && active !== 2) setBreath(false);
    chapter = active;
    body.dataset.activeChapter = String(active);
    if (byId('chapter-number')) byId('chapter-number').textContent = String(active + 1).padStart(2, '0');
    if (byId('chapter-name')) byId('chapter-name').textContent = labels[active];
    document.querySelectorAll('.chapter-link').forEach(link => {
      const selected = link.getAttribute('href') === '#' + sections[active]?.id;
      if (selected) link.setAttribute('aria-current', 'step'); else link.removeAttribute('aria-current');
    });
  }
  const total = Math.max(1, document.documentElement.scrollHeight - viewport);
  if (byId('scroll-progress')) byId('scroll-progress').style.transform = `scaleX(${Math.min(1, position / total)})`;
  scene?.setProgress(progress);
  scene?.setVisible(!document.hidden && active < 4 && !menu?.open);
}
function scheduleScroll() { if (!scrollFrame) scrollFrame = requestAnimationFrame(updateScroll); }
async function loadScene() {
  if (scene || scenePromise || reduced || sceneFailed) return scenePromise;
  setStatus('Preparing the engine study…');
  scenePromise = import('./engine-scene.js').then(({ createScene }) => {
    if (reduced) return;
    scene = createScene(canvas, {
      onReady() {
        sceneFailed = false;
        body.classList.add('scene-ready');
        byId('explore-toggle')?.removeAttribute('disabled');
        byId('cycle-toggle')?.removeAttribute('disabled');
        byId('reset-view')?.removeAttribute('disabled');
        setStatus('Interactive engine study');
      },
      onError() { failScene(); },
    });
    updateScroll();
  }).catch(() => {
    failScene();
  }).finally(() => { scenePromise = null; });
  return scenePromise;
}
function failScene() {
  sceneFailed = true; body.classList.remove('scene-ready');
  setExplore(false); setBreath(false);
  for (const id of ['explore-toggle', 'cycle-toggle', 'reset-view']) byId(id)?.setAttribute('disabled', '');
  setStatus('Still study · 3D is unavailable on this device');
}
function applyMotion() {
  body.classList.toggle('is-reduced', reduced);
  document.documentElement.classList.toggle('reduced-motion', reduced);
  byId('motion-toggle')?.setAttribute('aria-pressed', String(reduced));
  const label = byId('motion-toggle')?.querySelector('[data-button-label]');
  if (label) label.textContent = reduced ? 'Motion off' : 'Motion on';
  if (reduced) {
    setExplore(false); setBreath(false); scene?.setPaused(true);
    body.classList.remove('scene-ready'); setStatus('Still study · reduced motion');
    for (const id of ['explore-toggle', 'cycle-toggle', 'reset-view']) byId(id)?.setAttribute('disabled', '');
  } else {
    if (sceneFailed) { failScene(); return; }
    scene?.setPaused(false);
    if (scene) {
      body.classList.add('scene-ready');
      for (const id of ['explore-toggle', 'cycle-toggle', 'reset-view']) byId(id)?.removeAttribute('disabled');
      setStatus('Interactive engine study');
    } else loadScene();
  }
}

// A quiet, synthetic ignition tone. No recording is presented as a real Ferrari.
async function toggleSound() {
  if (soundStarting) return;
  if (soundEnabled) { stopSound(); return; }
  soundStarting = true;
  try {
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio) throw new Error('Audio unavailable');
    audioContext ||= new Audio();
    await audioContext.resume();
    audioGain = audioContext.createGain();
    audioGain.gain.setValueAtTime(0, audioContext.currentTime);
    audioGain.gain.linearRampToValueAtTime(.025, audioContext.currentTime + .8);
    audioGain.connect(audioContext.destination);
    for (const frequency of [55, 82.5, 110]) {
      const oscillator = audioContext.createOscillator();
      oscillator.type = 'sine';
      oscillator.frequency.setValueAtTime(frequency * .65, audioContext.currentTime);
      oscillator.frequency.exponentialRampToValueAtTime(frequency, audioContext.currentTime + .7);
      oscillator.connect(audioGain); oscillator.start(); audioNodes.push(oscillator);
    }
    soundEnabled = true; updateSoundButton();
  } catch { setStatus('Sound is unavailable. The visual experience is ready.'); }
  finally { soundStarting = false; }
}
function updateSoundButton() {
  byId('sound-toggle')?.setAttribute('aria-pressed', String(soundEnabled));
  byId('sound-toggle')?.setAttribute('aria-label', soundEnabled ? 'Mute synthesized engine sound' : 'Enable synthesized engine sound');
  const label = byId('sound-toggle')?.querySelector('[data-button-label]');
  if (label) label.textContent = soundEnabled ? 'Sound on' : 'Sound off';
}
function stopSound() {
  audioNodes.forEach(node => { try { node.stop(); node.disconnect(); } catch { /* Already stopped. */ } });
  audioNodes = []; audioGain?.disconnect(); soundEnabled = false; updateSoundButton();
}

byId('menu-open')?.addEventListener('click', () => { menu.showModal(); body.classList.add('menu-open'); byId('menu-open').setAttribute('aria-expanded', 'true'); scene?.setVisible(false); });
function closeMenu() { menu?.close(); body.classList.remove('menu-open'); updateScroll(); }
byId('menu-close')?.addEventListener('click', closeMenu);
menu?.addEventListener('close', () => { body.classList.remove('menu-open'); byId('menu-open')?.setAttribute('aria-expanded', 'false'); byId('menu-open')?.focus(); updateScroll(); });
menu?.querySelectorAll('a').forEach(link => link.addEventListener('click', () => { if (link.getAttribute('href')?.startsWith('#')) closeMenu(); }));
byId('sound-toggle')?.addEventListener('click', toggleSound);
byId('motion-toggle')?.addEventListener('click', () => { reduced = !reduced; writeSetting('nav12-motion', reduced ? 'reduced' : 'full'); applyMotion(); });
reducedPreference.addEventListener('change', event => { reduced = event.matches; applyMotion(); });
byId('explore-toggle')?.addEventListener('click', () => { setExplore(!exploring); if (exploring) canvas.focus({ preventScroll: true }); });
byId('reset-view')?.addEventListener('click', () => scene?.reset());
byId('exit-explore')?.addEventListener('click', () => { setExplore(false); byId('explore-toggle')?.focus({ preventScroll: true }); });
byId('rotate-left')?.addEventListener('click', () => scene?.rotate(-1));
byId('rotate-right')?.addEventListener('click', () => scene?.rotate(1));
byId('cycle-toggle')?.addEventListener('click', () => setBreath(!breath));
canvas?.addEventListener('keydown', event => {
  if (!exploring) return;
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); scene.rotate(event.key === 'ArrowLeft' ? -.8 : .8); }
  if (event.key === 'Escape') { setExplore(false); byId('explore-toggle')?.focus({ preventScroll: true }); }
  if (event.key === 'Home') { event.preventDefault(); scene.reset(); }
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && exploring) { setExplore(false); byId('explore-toggle')?.focus({ preventScroll: true }); }
});
document.addEventListener('visibilitychange', () => { if (document.hidden) stopSound(); updateScroll(); });
window.addEventListener('scroll', scheduleScroll, { passive: true });
window.addEventListener('resize', scheduleScroll, { passive: true });
window.addEventListener('pagehide', () => { stopSound(); scene?.setVisible(false); });
window.addEventListener('pageshow', updateScroll);

// Subtle magnetism only on precise pointers; focus and reduced motion stay still.
if (matchMedia('(pointer: fine)').matches) {
  document.querySelectorAll('[data-magnetic]').forEach(element => {
    element.addEventListener('pointermove', event => {
      if (reduced) return;
      const rect = element.getBoundingClientRect();
      element.style.transform = `translate(${(event.clientX - rect.left - rect.width / 2) * .075}px, ${(event.clientY - rect.top - rect.height / 2) * .075}px)`;
    });
    element.addEventListener('pointerleave', () => { element.style.transform = ''; });
  });
}
const returned = readSetting('nav12-engine-seen');
body.classList.add(returned || reduced ? 'has-entered' : 'is-entering');
if (!returned && !reduced) setTimeout(() => { body.classList.remove('is-entering'); body.classList.add('has-entered'); }, 1500);
writeSetting('nav12-engine-seen', '1');
applyMotion(); updateScroll();
