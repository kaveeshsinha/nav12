import * as THREE from './vendor/three.module.min.js';
import { createEngine } from './engine-model.js';

// One scene follows native document scrolling. The 3D exhibit is illustrative.
export function createScene(canvas, { onReady, onError }) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'low-power' });
  renderer.setClearColor(0x08090a, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.45;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(34, 1, .1, 100);
  const engine = createEngine(THREE);
  scene.add(engine.group);

  // A locally generated studio reflection rig: no remote textures or requests.
  const studio = new THREE.Scene();
  studio.background = new THREE.Color(0x24282e);
  const cards = [
    [[-7, 8, 3], [5, 8], 0xffffff, 6],
    [[6, 5, -5], [3, 9], 0xdce7ff, 8],
    [[1, 9, 0], [9, 4], 0xffffff, 5],
    [[0, 1, 10], [7, 3], 0xffffff, 2],
  ];
  for (const [position, size, color, intensity] of cards) {
    const panel = new THREE.Mesh(new THREE.PlaneGeometry(...size), new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide }));
    panel.material.color.multiplyScalar(intensity);
    panel.position.set(...position); panel.lookAt(0, 0, 0); studio.add(panel);
  }
  const pmrem = new THREE.PMREMGenerator(renderer);
  const environment = pmrem.fromScene(studio, .12, .1, 40);
  scene.environment = environment.texture;
  pmrem.dispose();
  studio.traverse(object => { object.geometry?.dispose(); object.material?.dispose(); });
  scene.add(new THREE.HemisphereLight(0xe1edff, 0x19120e, 2.2));
  const key = new THREE.DirectionalLight(0xfff4e7, 4.5);
  key.position.set(-4, 8, 9); scene.add(key);
  const rim = new THREE.DirectionalLight(0xb4ceff, 3);
  rim.position.set(5, 4, -7); scene.add(rim);
  const fill = new THREE.DirectionalLight(0xffffff, 1.8);
  fill.position.set(7, 1, 5); scene.add(fill);

  const poses = [
    { position: [11.5, 7.5, 13], target: [0, .1, 0], shift: .205 },
    { position: [11, 10, 10], target: [0, .25, 0], shift: .20 },
    { position: [7, 13, 8], target: [0, .9, 0], shift: .21 },
    { position: [13, 2.5, 8], target: [0, -.3, 0], shift: .20 },
    { position: [11.5, 7.5, 13], target: [0, .1, 0], shift: .20 },
  ];
  let progress = 0, visible = true, paused = false, disposed = false, raf = 0;
  let exploring = false, breath = false, rotation = 0, tilt = 0, zoom = 1;
  let currentRotation = 0, currentTilt = 0, pointer = [0, 0];
  let width = 1, height = 1, mobile = false, rendered = false, lastFrame = 0;
  let target = new THREE.Vector3(), position = new THREE.Vector3();
  let pointerStart = null;
  const signal = new AbortController();
  const listen = (el, type, fn, options = {}) => el.addEventListener(type, fn, { ...options, signal: signal.signal });
  function resize() {
    width = window.innerWidth; height = window.innerHeight; mobile = width <= 760;
    const pixelBudget = mobile ? 1.25 : 1.7;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, pixelBudget));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix(); invalidate();
  }
  function draw(now = 0) {
    raf = 0;
    if (disposed || !visible || paused) return;
    const chapter = Math.min(3, Math.floor(progress));
    const mix = THREE.MathUtils.smoothstep(progress - chapter, 0, 1);
    const a = poses[chapter], b = poses[chapter + 1];
    position.fromArray(a.position).lerp(new THREE.Vector3(...b.position), mix);
    target.fromArray(a.target).lerp(new THREE.Vector3(...b.target), mix);
    // Preserve the composition on portrait phones/tablets as well as wide screens.
    const aspect = width / height;
    if (mobile) { position.multiplyScalar(Math.max(1.65, .76 / aspect)); camera.fov = 39; }
    else { position.multiplyScalar(Math.max(1, 1.45 / aspect)); camera.fov = 34; }
    position.multiplyScalar(zoom);
    camera.position.copy(position); camera.lookAt(target);
    const shift = mobile ? 0 : THREE.MathUtils.lerp(a.shift, b.shift, mix);
    camera.setViewOffset(width, height, -width * shift, mobile ? -height * .18 : 0, width, height);
    camera.updateProjectionMatrix();
    const desiredRotation = exploring ? rotation : pointer[0] * .035;
    const desiredTilt = exploring ? tilt : pointer[1] * .018;
    currentRotation = THREE.MathUtils.lerp(currentRotation, desiredRotation, .14);
    currentTilt = THREE.MathUtils.lerp(currentTilt, desiredTilt, .14);
    engine.group.rotation.y = currentRotation;
    engine.group.rotation.x = currentTilt;
    engine.update?.(now / 1000, { breath, running: breath });
    renderer.render(scene, camera);
    if (!rendered) { rendered = true; onReady?.(); }
    const unsettled = Math.abs(currentRotation - desiredRotation) + Math.abs(currentTilt - desiredTilt) > .001;
    // Idle exhibits stop rendering; airflow is deliberately capped at 30 fps.
    if (breath || unsettled) raf = requestAnimationFrame(t => {
      if (breath && t - lastFrame < 32) { raf = requestAnimationFrame(draw); return; }
      lastFrame = t; draw(t);
    });
  }
  function invalidate() { if (!raf && !disposed) raf = requestAnimationFrame(draw); }
  listen(window, 'resize', resize, { passive: true });
  listen(canvas, 'webglcontextlost', event => { event.preventDefault(); paused = true; onError?.(); });
  listen(canvas, 'pointerdown', event => {
    if (!exploring) return;
    pointerStart = [event.clientX, event.clientY, rotation, tilt];
    canvas.setPointerCapture(event.pointerId);
  });
  listen(canvas, 'pointermove', event => {
    if (!exploring || !pointerStart) return;
    rotation = pointerStart[2] + (event.clientX - pointerStart[0]) * .008;
    tilt = THREE.MathUtils.clamp(pointerStart[3] + (event.clientY - pointerStart[1]) * .004, -.45, .55);
    invalidate();
  });
  const endDrag = () => { pointerStart = null; };
  listen(canvas, 'pointerup', endDrag); listen(canvas, 'pointercancel', endDrag);
  listen(window, 'pointermove', event => {
    if (exploring || mobile || event.pointerType === 'touch') return;
    pointer = [event.clientX / width - .5, event.clientY / height - .5]; invalidate();
  }, { passive: true });
  resize();
  return {
    setProgress(value) { progress = THREE.MathUtils.clamp(value, 0, 4); invalidate(); },
    setVisible(value) { visible = value; if (visible) invalidate(); else { cancelAnimationFrame(raf); raf = 0; } },
    setPaused(value) { paused = value; if (!paused) invalidate(); },
    setExploring(value) { exploring = value; if (!value) { rotation = 0; tilt = 0; zoom = 1; } invalidate(); },
    setBreath(value) { breath = value; invalidate(); },
    rotate(direction) { rotation += direction * .3; invalidate(); },
    reset() { rotation = 0; tilt = 0; zoom = 1; invalidate(); },
    dispose() {
      disposed = true; cancelAnimationFrame(raf); signal.abort(); environment.dispose();
      engine.dispose?.(); renderer.dispose();
    },
  };
}
