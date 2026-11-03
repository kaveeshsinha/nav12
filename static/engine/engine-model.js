/**
 * NaV12 original engine study — a purpose-built, procedural 65° V12 concept.
 * This is an illustrative assembly, not a manufacturer CAD model.
 * Coordinates: Y up, crankshaft along Z, timing / intake face toward +Z.
 * No network resources, textures, fonts, or third-party model assets are used.
 */
export function createEngine(THREE) {
  const group = new THREE.Group();
  group.name = 'NaV12 — naturally aspirated engine study';
  const parts = {};
  for (const name of ['intake', 'banks', 'headers', 'crank', 'flow']) {
    const part = new THREE.Group();
    part.name = name;
    parts[name] = part;
    group.add(part);
  }

  const materials = {
    aluminum: new THREE.MeshStandardMaterial({color: 0xa8adb0, metalness: .82, roughness: .3}),
    cast: new THREE.MeshStandardMaterial({color: 0x626b70, metalness: .76, roughness: .48}),
    polished: new THREE.MeshStandardMaterial({color: 0xd1d5d5, metalness: .94, roughness: .21}),
    graphite: new THREE.MeshStandardMaterial({color: 0x22272a, metalness: .68, roughness: .38}),
    dark: new THREE.MeshStandardMaterial({color: 0x0b0d0e, metalness: .25, roughness: .7}),
    rubber: new THREE.MeshStandardMaterial({color: 0x111314, metalness: .08, roughness: .84}),
    red: new THREE.MeshPhysicalMaterial({color: 0x8d171c, metalness: .35, roughness: .37, clearcoat: .35, clearcoatRoughness: .27}),
    titanium: new THREE.MeshStandardMaterial({color: 0xa69d8b, metalness: .88, roughness: .28}),
    brass: new THREE.MeshStandardMaterial({color: 0x9a8060, metalness: .88, roughness: .31}),
    // Deliberate illustrative overlay: the trace remains visible through opaque
    // castings, rather than pretending the concept is an operating cutaway.
    flow: new THREE.MeshBasicMaterial({color: 0xbddfe9, transparent: true, opacity: .85, depthTest: false, depthWrite: false, toneMapped: false}),
  };
  const geometries = new Map();
  const batches = new Map();
  const pulleys = [];
  const runnerPaths = [];
  const exhaustPaths = [];
  const dummy = new THREE.Object3D();
  const v = (x, y, z) => new THREE.Vector3(x, y, z);
  const angle = THREE.MathUtils.degToRad(32.5);

  function cached(key, create) {
    if (!geometries.has(key)) geometries.set(key, create());
    return geometries.get(key);
  }
  function box(w, h, d) { return cached(`box:${w}:${h}:${d}`, () => new THREE.BoxGeometry(w, h, d)); }
  function cylinder(top, bottom, h, sides = 24, open = false) {
    return cached(`cyl:${top}:${bottom}:${h}:${sides}:${open}`, () => new THREE.CylinderGeometry(top, bottom, h, sides, 1, open));
  }
  function torus(radius, tube, radial = 6, tubular = 32) {
    return cached(`tor:${radius}:${tube}:${radial}:${tubular}`, () => new THREE.TorusGeometry(radius, tube, radial, tubular));
  }
  function bevelBox(w, h, d, radius = .08) {
    return cached(`bevel:${w}:${h}:${d}:${radius}`, () => {
      const r = Math.min(radius, w / 5, h / 5, d / 5);
      const x = w / 2 - r * .42;
      const y = h / 2 - r * .42;
      const shape = new THREE.Shape();
      shape.moveTo(-x + r, -y);
      shape.lineTo(x - r, -y);
      shape.quadraticCurveTo(x, -y, x, -y + r);
      shape.lineTo(x, y - r);
      shape.quadraticCurveTo(x, y, x - r, y);
      shape.lineTo(-x + r, y);
      shape.quadraticCurveTo(-x, y, -x, y - r);
      shape.lineTo(-x, -y + r);
      shape.quadraticCurveTo(-x, -y, -x + r, -y);
      const geometry = new THREE.ExtrudeGeometry(shape, {
        depth: d - r * .84,
        bevelEnabled: true,
        bevelSegments: 2,
        steps: 1,
        bevelSize: r * .42,
        bevelThickness: r * .42,
        curveSegments: 4,
      });
      geometry.translate(0, 0, -d / 2 + r * .42);
      geometry.computeVertexNormals();
      return geometry;
    });
  }
  function mesh(parent, geometry, material, position = [0, 0, 0], rotation = [0, 0, 0]) {
    const object = new THREE.Mesh(geometry, material);
    object.position.set(...position);
    object.rotation.set(...rotation);
    object.castShadow = true;
    object.receiveShadow = true;
    parent.add(object);
    return object;
  }
  function instance(parent, geometry, material, position = [0, 0, 0], rotation = [0, 0, 0], scale = [1, 1, 1]) {
    const key = `${parent.uuid}:${geometry.uuid}:${material.uuid}`;
    if (!batches.has(key)) batches.set(key, {parent, geometry, material, matrices: []});
    dummy.position.set(...position);
    dummy.rotation.set(...rotation);
    dummy.scale.set(...scale);
    dummy.updateMatrix();
    batches.get(key).matrices.push(dummy.matrix.clone());
  }
  function pipe(parent, points, radius, material, segments = 32) {
    const path = new THREE.CatmullRomCurve3(points.map(p => v(...p)), false, 'centripetal');
    const geometry = new THREE.TubeGeometry(path, segments, radius, 9, false);
    geometries.set(geometry.uuid, geometry);
    mesh(parent, geometry, material);
    return path;
  }
  function bolt(parent, position, rotation = [Math.PI / 2, 0, 0], radius = .054) {
    instance(parent, cylinder(radius, radius, .055, 6), materials.polished, position, rotation);
  }

  // Deep crankcase, stepped sump, machined split-line and longitudinal casting ribs.
  mesh(parts.crank, bevelBox(1.8, 1.35, 5.5, .17), materials.cast, [0, -.68, 0]);
  mesh(parts.crank, bevelBox(1.87, .13, 5.62, .045), materials.aluminum, [0, -1.31, 0]);
  mesh(parts.crank, bevelBox(1.66, .54, 5.34, .15), materials.graphite, [0, -1.63, -.05]);
  mesh(parts.crank, bevelBox(1.5, .12, 5.06, .04), materials.aluminum, [0, -1.92, -.05]);
  for (let i = 0; i < 18; i++) {
    instance(parts.crank, bevelBox(1.72, .07, .072, .014), materials.cast, [0, -1.65, -2.46 + i * .29]);
    instance(parts.crank, box(.055, .42, .075), materials.aluminum, [-.835, -1.61, -2.46 + i * .29]);
    instance(parts.crank, box(.055, .42, .075), materials.aluminum, [.835, -1.61, -2.46 + i * .29]);
  }
  for (const sign of [-1, 1]) {
    mesh(parts.crank, bevelBox(.13, .11, 5.15, .025), materials.aluminum, [sign * .9, -.88, 0]);
    for (let i = 0; i < 9; i++) bolt(parts.crank, [sign * .95, -1.28, -2.47 + i * .61], [0, 0, Math.PI / 2]);
  }

  // Two visibly distinct banks, six cylinders each. Their axes form a 65° V.
  for (const sign of [-1, 1]) {
    const bank = new THREE.Group();
    bank.name = sign < 0 ? 'Left bank — six cylinders' : 'Right bank — six cylinders';
    bank.position.set(sign * .19, -.7, 0);
    bank.rotation.z = -sign * angle;
    parts.banks.add(bank);

    mesh(bank, bevelBox(1.15, 1.32, 5.32, .12), materials.cast, [0, .66, 0]);
    mesh(bank, bevelBox(1.27, .23, 5.46, .055), materials.aluminum, [0, 1.34, 0]);
    mesh(bank, bevelBox(1.16, .39, 5.4, .09), materials.aluminum, [0, 1.63, 0]);
    mesh(bank, bevelBox(1.13, .055, 5.42, .02), materials.dark, [0, 1.844, 0]);
    mesh(bank, bevelBox(1.13, .28, 5.35, .105), materials.red, [0, 1.995, 0]);
    // Raised metallic spine and fine ribs keep the covers mechanical, not toy-like.
    mesh(bank, bevelBox(.18, .045, 4.76, .018), materials.polished, [0, 2.155, 0]);
    for (const dx of [-.32, -.24, .24, .32]) {
      instance(bank, box(.023, .018, 4.76), materials.aluminum, [dx, 2.144, 0]);
    }
    for (let i = 0; i < 6; i++) {
      const z = -2.13 + i * .852;
      // Circular casting shoulders, plug wells, coil packs and side reinforcement.
      instance(bank, cylinder(.43, .43, .74, 18), materials.cast, [0, .7, z]);
      instance(bank, bevelBox(.18, .24, .27, .035), materials.graphite, [sign * .39, 2.17, z]);
      instance(bank, cylinder(.09, .09, .06, 16), materials.dark, [sign * .39, 2.315, z]);
      for (const side of [-1, 1]) {
        instance(bank, box(.055, .9, .09), materials.aluminum, [side * .584, .72, z]);
        bolt(bank, [side * .48, 2.14, z], [0, 0, 0]);
        bolt(bank, [side * .635, 1.35, z], [0, 0, Math.PI / 2]);
      }
    }
    // Long rail, rear breather, oil cap and compact lifting eye.
    mesh(bank, cylinder(.045, .045, 4.8, 12), materials.polished, [-sign * .67, 1.73, 0], [Math.PI / 2, 0, 0]);
    mesh(bank, cylinder(.2, .2, .09, 24), materials.graphite, [0, 2.2, -1.6]);
    mesh(bank, box(.24, .035, .05), materials.aluminum, [0, 2.26, -1.6]);
    mesh(bank, torus(.13, .043, 6, 20), materials.aluminum, [sign * .6, 1.75, -2.5]);
  }

  // Two sculpted intake plenums sit above the valley. Runners remain individually legible.
  for (const sign of [-1, 1]) {
    const x = sign * .55;
    mesh(parts.intake, bevelBox(.87, .61, 4.88, .22), materials.red, [x, 1.78, -.1]);
    mesh(parts.intake, bevelBox(.76, .07, 4.52, .025), materials.aluminum, [x, 1.49, -.1]);
    mesh(parts.intake, bevelBox(.075, .026, 4.18, .012), materials.polished, [x, 2.1, -.13]);
    for (const dx of [-.21, .21]) {
      mesh(parts.intake, bevelBox(.017, .018, 4.13, .006), materials.aluminum, [x + dx, 2.074, -.13]);
    }
    for (let i = 0; i < 6; i++) {
      const z = -2.12 + i * .85;
      const points = [
        [x, 1.55, z],
        [sign * .77, 1.39, z],
        [sign * 1.06, 1.13, z],
        [sign * 1.06, .85, z],
      ];
      runnerPaths.push(pipe(parts.intake, points, .135, materials.aluminum, 17));
      // Cast inlet flange and repeated mounting screws.
      instance(parts.intake, bevelBox(.4, .1, .42, .05), materials.graphite, [sign * .79, 1.36, z], [0, 0, -sign * .5]);
      bolt(parts.intake, [x - .29, 1.47, z], [0, 0, 0], .043);
      bolt(parts.intake, [x + .29, 1.47, z], [0, 0, 0], .043);
    }
    // Front throttle housing with a dark bore, silver lip and ribbed rubber coupling.
    mesh(parts.intake, cylinder(.305, .305, .48, 32), materials.aluminum, [x, 1.75, 2.62], [Math.PI / 2, 0, 0]);
    mesh(parts.intake, cylinder(.267, .267, .13, 32), materials.dark, [x, 1.75, 2.92], [Math.PI / 2, 0, 0]);
    mesh(parts.intake, torus(.276, .035), materials.polished, [x, 1.75, 2.99]);
    mesh(parts.intake, box(.52, .034, .035), materials.brass, [x, 1.75, 2.99]);
    for (let j = 0; j < 4; j++) {
      instance(parts.intake, torus(.305, .019), materials.graphite, [x, 1.75, 2.45 + j * .1]);
    }
    mesh(parts.intake, bevelBox(.23, .3, .34, .04), materials.graphite, [x + sign * .31, 1.76, 2.65]);
    bolt(parts.intake, [x, 2.1, -2.12], [0, 0, 0]);
  }
  // Central structural bridge and twelve narrow silver ribs emphasize the long V12.
  mesh(parts.intake, bevelBox(.15, .08, 4.76, .02), materials.graphite, [0, 1.53, -.1]);
  for (const z of [-1.85, 0, 1.85]) {
    mesh(parts.intake, bevelBox(1.93, .07, .13, .025), materials.graphite, [0, 1.45, z]);
  }

  // Twelve unequal visual routing curves form two six-branch exhaust assemblies.
  // They represent packaging, not a claim about a production engine's tuned lengths.
  for (const sign of [-1, 1]) {
    for (let i = 0; i < 6; i++) {
      const z = -2.12 + i * .85;
      const lane = i % 3;
      const reach = 2.12 + lane * .16;
      const endZ = -2.85 + (i < 3 ? -.12 : .12);
      const points = [
        [sign * 1.32, .47, z],
        [sign * 1.75, .4, z],
        [sign * reach, -.07 - lane * .07, z - .15],
        [sign * (reach + .05), -.72 - lane * .12, z - .47],
        [sign * (1.93 + lane * .08), -1.1 - lane * .09, Math.min(z - .9, -1.85)],
        [sign * 1.83, -1.18, endZ],
      ];
      exhaustPaths.push(pipe(parts.headers, points, .115, materials.titanium, 32));
      instance(parts.headers, bevelBox(.11, .36, .38, .055), materials.cast, [sign * 1.36, .46, z]);
      bolt(parts.headers, [sign * 1.43, .6, z - .13], [0, 0, Math.PI / 2], .04);
      bolt(parts.headers, [sign * 1.43, .32, z + .13], [0, 0, Math.PI / 2], .04);
      // Small machined collars distinguish each branch at the head.
      instance(parts.headers, cylinder(.145, .145, .08, 18), materials.polished, [sign * 1.55, .46, z], [0, 0, Math.PI / 2]);
    }
    mesh(parts.headers, cylinder(.29, .22, .57, 24), materials.titanium, [sign * 1.83, -1.18, -3.02], [Math.PI / 2, 0, 0]);
    mesh(parts.headers, torus(.225, .035), materials.polished, [sign * 1.83, -1.18, -3.34]);
    mesh(parts.headers, cylinder(.19, .19, .03, 24), materials.dark, [sign * 1.83, -1.18, -3.34], [Math.PI / 2, 0, 0]);
  }

  // Timing face: cast housing, actual belt loop, stepped pulley wheels and fasteners.
  mesh(parts.crank, bevelBox(1.91, 1.85, .23, .22), materials.aluminum, [0, -.37, 2.84]);
  mesh(parts.crank, bevelBox(1.63, 1.5, .07, .18), materials.graphite, [0, -.38, 2.99]);
  function pulley(x, y, radius, faceZ = 3.17) {
    const wheel = new THREE.Group();
    wheel.position.set(x, y, faceZ);
    parts.crank.add(wheel);
    mesh(wheel, cylinder(radius, radius, .17, 40), materials.graphite, [0, 0, 0], [Math.PI / 2, 0, 0]);
    mesh(wheel, cylinder(radius * .7, radius * .7, .19, 32), materials.aluminum, [0, 0, .01], [Math.PI / 2, 0, 0]);
    mesh(wheel, cylinder(radius * .49, radius * .49, .205, 32), materials.dark, [0, 0, .02], [Math.PI / 2, 0, 0]);
    mesh(wheel, torus(radius * .88, .018, 5, 40), materials.polished, [0, 0, .09]);
    mesh(wheel, cylinder(radius * .2, radius * .2, .24, 6), materials.polished, [0, 0, .04], [Math.PI / 2, 0, 0]);
    for (let j = 0; j < 6; j++) {
      const t = j / 6 * Math.PI * 2;
      instance(wheel, cylinder(radius * .055, radius * .055, .035, 6), materials.polished,
        [Math.sin(t) * radius * .59, Math.cos(t) * radius * .59, .13], [Math.PI / 2, 0, 0]);
    }
    pulleys.push(wheel);
  }
  pulley(0, -.82, .56);
  pulley(-.78, .23, .29);
  pulley(.78, .23, .29);
  pulley(-1.24, -.48, .27);
  pulley(1.17, -.63, .24);
  // Follow the outer tangents of all five pulleys. This belt is visually continuous.
  const beltPoints = [
    [-.78, .54, 3.16], [.78, .54, 3.16], [1.06, .3, 3.16],
    [1.41, -.62, 3.16], [1.29, -.85, 3.16], [.35, -1.33, 3.16],
    [0, -1.39, 3.16], [-.4, -1.23, 3.16], [-1.45, -.66, 3.16],
    [-1.51, -.43, 3.16], [-1.03, .36, 3.16], [-.78, .54, 3.16],
  ];
  pipe(parts.crank, beltPoints, .047, materials.rubber, 80);
  for (const [x, y] of [[-.8, -.9], [.8, -.9], [-.65, .43], [.65, .43], [0, .5]]) {
    bolt(parts.crank, [x, y, 3.01]);
  }

  // Alternator, oil filter, coolant rails and small fittings give the lower engine scale.
  mesh(parts.crank, cylinder(.31, .31, .52, 24), materials.cast, [-1.23, -.48, 2.68], [Math.PI / 2, 0, 0]);
  for (let i = 0; i < 12; i++) {
    const theta = i / 12 * Math.PI * 2;
    instance(parts.crank, box(.055, .065, .44), materials.aluminum,
      [-1.23 + Math.cos(theta) * .3, -.48 + Math.sin(theta) * .3, 2.68], [0, 0, theta]);
  }
  mesh(parts.crank, cylinder(.21, .21, .58, 28), materials.graphite, [1.25, -.92, 1.91], [0, 0, -.18]);
  mesh(parts.crank, cylinder(.225, .225, .075, 28), materials.aluminum, [1.3, -.61, 1.91], [0, 0, -.18]);
  mesh(parts.crank, cylinder(.24, .24, .22, 28), materials.aluminum, [1.07, -.22, 2.62], [Math.PI / 2, 0, 0]);
  for (const sign of [-1, 1]) {
    pipe(parts.banks, [[sign * 1.29, .87, -2.52], [sign * 1.45, .78, -2.65], [sign * 1.49, -.23, -2.69], [sign * .65, -.45, -2.81]], .065, materials.rubber, 20);
    mesh(parts.crank, bevelBox(.46, .17, .55, .04), materials.cast, [sign * 1.13, -1.03, -.8]);
    bolt(parts.crank, [sign * 1.27, -.92, -.8], [0, 0, 0], .09);
  }
  mesh(parts.crank, cylinder(.71, .65, .32, 40), materials.aluminum, [0, -.56, -2.94], [Math.PI / 2, 0, 0]);
  mesh(parts.crank, cylinder(.51, .51, .35, 32), materials.graphite, [0, -.56, -2.96], [Math.PI / 2, 0, 0]);
  for (let j = 0; j < 8; j++) {
    const t = j / 8 * Math.PI * 2;
    bolt(parts.crank, [Math.sin(t) * .59, -.56 + Math.cos(t) * .59, -3.12]);
  }

  // Batch repeated ribs, screws, collars and small castings to keep draw calls bounded.
  for (const batch of batches.values()) {
    const instanced = new THREE.InstancedMesh(batch.geometry, batch.material, batch.matrices.length);
    for (let i = 0; i < batch.matrices.length; i++) instanced.setMatrixAt(i, batch.matrices[i]);
    instanced.instanceMatrix.needsUpdate = true;
    instanced.castShadow = true;
    instanced.receiveShadow = true;
    batch.parent.add(instanced);
  }

  // Optional slow airflow illustration; never implies a simulated firing order.
  const flowPaths = runnerPaths.map((runner, i) => {
    const points = [];
    for (let j = 0; j < 6; j++) points.push(runner.getPoint(j / 5));
    const exhaust = exhaustPaths[i];
    points.push(exhaust.getPoint(0));
    for (let j = 1; j <= 12; j++) points.push(exhaust.getPoint(j / 12));
    return new THREE.CatmullRomCurve3(points);
  });
  const flowGeo = cached('flow-sphere', () => new THREE.SphereGeometry(.045, 8, 6));
  const particles = new THREE.InstancedMesh(flowGeo, materials.flow, flowPaths.length * 3);
  particles.renderOrder = 10;
  particles.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  particles.frustumCulled = false;
  parts.flow.add(particles);
  parts.flow.visible = false;

  group.userData = {
    kind: 'Original NaV12 concept engine',
    bankAngleDegrees: 65,
    cylinders: 12,
    illustrative: true,
    longitudinalAxis: 'Z',
  };

  function update(time = 0, mode = {}) {
    const breath = mode === 'breath' || mode.breath === true;
    const running = mode === 'running' || mode.running === true;
    parts.flow.visible = breath;
    if (breath) {
      dummy.rotation.set(0, 0, 0);
      dummy.scale.set(1, 1, 1);
      for (let i = 0; i < flowPaths.length; i++) {
        for (let j = 0; j < 3; j++) {
          const progress = (time * .17 + j / 3 + i * .035) % 1;
          dummy.position.copy(flowPaths[i].getPoint(progress));
          dummy.updateMatrix();
          particles.setMatrixAt(i * 3 + j, dummy.matrix);
        }
      }
      particles.instanceMatrix.needsUpdate = true;
    }
    for (let i = 0; i < pulleys.length; i++) {
      pulleys[i].rotation.z = running ? -time * (i === 0 ? .65 : 1.12) : 0;
    }
  }
  function dispose() {
    for (const geometry of new Set(geometries.values())) geometry.dispose();
    for (const material of Object.values(materials)) material.dispose();
  }

  return {group, parts, materials, update, dispose};
}
