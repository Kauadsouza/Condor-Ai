import * as THREE from '../vendor/three.module.min.js';

const viewport = document.getElementById('condorXViewport');

if (viewport && !viewport.dataset.ready) {
  viewport.dataset.ready = 'true';

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x040912, 0.13);

  const camera = new THREE.PerspectiveCamera(27, 1, 0.1, 30);
  camera.position.set(0, 0.96, 3.75);
  camera.lookAt(0, 0.95, 0);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.8));
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.18;
  viewport.appendChild(renderer.domElement);

  scene.add(new THREE.HemisphereLight(0x9cf5ff, 0x050811, 2.3));
  const key = new THREE.DirectionalLight(0xe5fbff, 4.2);
  key.position.set(2.8, 4.2, 4.5);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x5eead4, 3.4);
  rim.position.set(-3.2, 2.1, -2.4);
  scene.add(rim);
  const violet = new THREE.PointLight(0x8b7cff, 18, 5.5, 2);
  violet.position.set(-1.7, 1.2, 1.7);
  scene.add(violet);

  const materials = {
    body: new THREE.MeshPhysicalMaterial({
      color: 0x7fa6a8, emissive: 0x092f36, emissiveIntensity: 0.16,
      metalness: 0, roughness: 0.63, clearcoat: 0.08, clearcoatRoughness: 0.68,
      transparent: true, opacity: 0.96,
    }),
    panel: new THREE.MeshPhysicalMaterial({
      color: 0x9ab6b6, emissive: 0x10383d, emissiveIntensity: 0.12,
      metalness: 0, roughness: 0.58, clearcoat: 0.1, clearcoatRoughness: 0.6,
      transparent: true, opacity: 0.9,
    }),
    under: new THREE.MeshStandardMaterial({
      color: 0x183238, emissive: 0x06252d, emissiveIntensity: 0.17,
      metalness: 0.01, roughness: 0.7,
    }),
    detail: new THREE.MeshStandardMaterial({
      color: 0x63bac0, emissive: 0x116472, emissiveIntensity: 0.3,
      metalness: 0, roughness: 0.62, transparent: true, opacity: 0.54,
    }),
    seam: new THREE.MeshBasicMaterial({ color: 0x65efff, transparent: true, opacity: 0.55, depthWrite: false }),
    eye: new THREE.MeshPhysicalMaterial({ color: 0xcafcff, emissive: 0x5eead4, emissiveIntensity: 1.8, roughness: 0.16 }),
    darkEye: new THREE.MeshStandardMaterial({ color: 0x02070b, emissive: 0x063946, emissiveIntensity: 0.45, roughness: 0.25 }),
    core: new THREE.MeshPhysicalMaterial({ color: 0xffb34f, emissive: 0xff7c18, emissiveIntensity: 2.8, metalness: 0.22, roughness: 0.18 }),
    coreSelected: new THREE.MeshPhysicalMaterial({ color: 0xffe3a7, emissive: 0xff9b2f, emissiveIntensity: 3.5, metalness: 0.12, roughness: 0.14 }),
    coreBack: new THREE.MeshPhysicalMaterial({ color: 0x193b40, emissive: 0x0b4a54, emissiveIntensity: 0.35, metalness: 0, roughness: 0.58, transparent: true, opacity: 0.92 }),
  };

  const rig = new THREE.Group();
  scene.add(rig);
  const body = new THREE.Group();
  rig.add(body);

  const interactive = [];
  const moduleMeshes = new Map();
  const addToModule = (mesh, module, highlight = true) => {
    mesh.userData.module = module;
    mesh.userData.baseMaterial = mesh.material;
    mesh.userData.highlight = highlight;
    if (!moduleMeshes.has(module)) moduleMeshes.set(module, []);
    moduleMeshes.get(module).push(mesh);
    if (highlight) interactive.push(mesh);
    return mesh;
  };

  function surface(geometry, position, scale, module, options = {}) {
    const mesh = new THREE.Mesh(geometry, options.material || materials.body);
    mesh.position.set(...position);
    mesh.scale.set(...scale);
    mesh.rotation.set(...(options.rotation || [0, 0, 0]));
    mesh.castShadow = false;
    body.add(mesh);
    addToModule(mesh, module, options.highlight !== false);
    if (options.edge) {
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 28), materials.seam);
      edges.position.copy(mesh.position);
      edges.scale.copy(mesh.scale).multiplyScalar(1.004);
      edges.rotation.copy(mesh.rotation);
      body.add(edges);
    }
    return mesh;
  }

  function joint(position, scale, module) {
    return surface(new THREE.SphereGeometry(1, 36, 24), position, scale, module, { material: materials.body });
  }

  function between(start, end, profile, module, material = materials.body) {
    const direction = end.clone().sub(start);
    const length = direction.length();
    const center = start.clone().add(end).multiplyScalar(0.5);
    const mapped = profile.map(([t, rx, rz]) => [(t - 0.5) * length, rx, rz]);
    const mesh = surface(organic(mapped, 56), [center.x, center.y, center.z], [1, 1, 1], module, { material });
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
    return mesh;
  }

  function organic(profile, radialSegments = 64) {
    const vertices = [];
    const indices = [];
    for (const [y, rx, rz] of profile) {
      for (let segment = 0; segment < radialSegments; segment += 1) {
        const angle = segment / radialSegments * Math.PI * 2;
        vertices.push(Math.cos(angle) * rx, y, Math.sin(angle) * rz);
      }
    }
    for (let ringIndex = 0; ringIndex < profile.length - 1; ringIndex += 1) {
      for (let segment = 0; segment < radialSegments; segment += 1) {
        const next = (segment + 1) % radialSegments;
        const currentRing = ringIndex * radialSegments;
        const nextRing = (ringIndex + 1) * radialSegments;
        indices.push(currentRing + segment, nextRing + segment, nextRing + next);
        indices.push(currentRing + segment, nextRing + next, currentRing + next);
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    return geometry;
  }

  function detailCapsule(position, radius, length, module, rotation = [0, 0, 0], material = materials.detail) {
    return surface(new THREE.CapsuleGeometry(radius, length, 8, 20), position, [1, 1, 1], module, { material, rotation, highlight: false });
  }

  // Cabeça humana: o volume segue crânio, face e mandíbula em vez de um bloco único.
  surface(new THREE.SphereGeometry(1, 64, 44), [0, 1.71, -0.004], [0.108, 0.137, 0.105], 'head', { material: materials.body });
  surface(new THREE.SphereGeometry(1, 56, 38), [0, 1.646, 0.021], [0.094, 0.098, 0.091], 'head');
  surface(new THREE.SphereGeometry(1, 44, 30), [0, 1.586, 0.044], [0.063, 0.052, 0.069], 'head', { material: materials.body });
  surface(new THREE.CapsuleGeometry(0.056, 0.085, 12, 28), [0, 1.52, 0], [1, 1, 0.92], 'chest', { material: materials.body });
  for (const side of [-1, 1]) {
    surface(new THREE.SphereGeometry(1, 28, 20), [side * 0.109, 1.687, 0.005], [0.016, 0.033, 0.011], 'head', { material: materials.panel });
    const earLine = new THREE.Mesh(new THREE.TorusGeometry(0.011, 0.0016, 8, 28), materials.seam);
    earLine.position.set(side * 0.111, 1.687, 0.014);
    earLine.scale.set(0.8, 1.45, 1);
    body.add(earLine);
    const eye = surface(new THREE.SphereGeometry(1, 28, 18), [side * 0.039, 1.684, 0.104], [0.014, 0.0085, 0.005], 'head', { material: materials.eye, highlight: false });
    eye.rotation.y = side * 0.03;
    surface(new THREE.SphereGeometry(1, 22, 16), [side * 0.039, 1.684, 0.109], [0.0045, 0.0045, 0.002], 'head', { material: materials.darkEye, highlight: false });
    const upperLid = new THREE.Mesh(new THREE.TorusGeometry(0.0132, 0.00125, 7, 30, Math.PI), materials.detail);
    upperLid.position.set(side * 0.039, 1.685, 0.109);
    upperLid.rotation.z = Math.PI;
    upperLid.scale.y = 0.6;
    body.add(upperLid);
    const lowerLid = upperLid.clone();
    lowerLid.position.y -= 0.0025;
    lowerLid.rotation.z = 0;
    body.add(lowerLid);
    detailCapsule([side * 0.039, 1.706, 0.102], 0.003, 0.038, 'head', [0, 0, Math.PI / 2 + side * 0.1]);
    surface(new THREE.SphereGeometry(1, 24, 18), [side * 0.059, 1.644, 0.09], [0.027, 0.018, 0.008], 'head', { material: materials.body, highlight: false });
  }
  detailCapsule([0, 1.673, 0.105], 0.005, 0.045, 'head');
  surface(new THREE.ConeGeometry(0.017, 0.048, 24), [0, 1.653, 0.111], [1, 1, 1], 'head', { material: materials.body, rotation: [Math.PI / 2, 0, 0], highlight: false });
  surface(new THREE.SphereGeometry(1, 20, 14), [0, 1.645, 0.119], [0.015, 0.01, 0.009], 'head', { material: materials.panel, highlight: false });
  detailCapsule([0, 1.615, 0.104], 0.0016, 0.039, 'head', [0, 0, Math.PI / 2], materials.seam);
  surface(new THREE.SphereGeometry(1, 24, 18), [0, 1.58, 0.079], [0.043, 0.019, 0.014], 'head', { material: materials.body, highlight: false });
  // Linhas temporais acompanham a face sem formar máscara ou placa de armadura.
  for (const side of [-1, 1]) {
    detailCapsule([side * 0.078, 1.718, 0.086], 0.0022, 0.052, 'head', [0.06, 0, side * 0.2]);
    detailCapsule([side * 0.079, 1.665, 0.087], 0.0018, 0.038, 'head', [0.05, 0, -side * 0.32]);
  }

  // Tronco contínuo com V anatômico, caixa torácica, cintura e quadril.
  const torsoProfile = [
    [0.91, 0.205, 0.145], [0.96, 0.225, 0.153], [1.02, 0.20, 0.137],
    [1.09, 0.17, 0.122], [1.16, 0.178, 0.126], [1.24, 0.205, 0.142],
    [1.33, 0.252, 0.165], [1.42, 0.294, 0.174], [1.48, 0.255, 0.15], [1.505, 0.128, 0.095],
  ];
  surface(organic(torsoProfile, 80), [0, 0, 0], [1, 1, 1], 'chest', { material: materials.body });
  surface(new THREE.SphereGeometry(1, 52, 34), [0, 0.96, 0], [0.225, 0.125, 0.15], 'legs', { material: materials.body });
  detailCapsule([0, 1.255, -0.124], 0.027, 0.43, 'chest', [0, 0, 0], materials.under);
  for (const side of [-1, 1]) {
    detailCapsule([side * 0.098, 1.455, 0.151], 0.0055, 0.18, 'chest', [0, 0, Math.PI / 2 - side * 0.12]);
    surface(new THREE.SphereGeometry(1, 36, 24), [side * 0.1, 1.345, 0.155], [0.103, 0.059, 0.015], 'chest', { material: materials.panel });
    detailCapsule([side * 0.11, 1.39, 0.169], 0.0028, 0.135, 'chest', [0.04, 0, Math.PI / 2 - side * 0.1]);
    detailCapsule([side * 0.11, 1.325, 0.172], 0.0022, 0.11, 'chest', [0.03, 0, Math.PI / 2 + side * 0.08]);
    const oblique = detailCapsule([side * 0.095, 1.12, 0.134], 0.003, 0.17, 'chest', [0, 0, side * 0.32]);
    oblique.scale.z = 0.7;
  }
  detailCapsule([0, 1.29, 0.158], 0.004, 0.24, 'chest');
  detailCapsule([0, 1.12, 0.137], 0.0026, 0.22, 'chest');
  const navel = new THREE.Mesh(new THREE.TorusGeometry(0.006, 0.0012, 8, 24), materials.under);
  navel.position.set(0, 1.075, 0.142);
  body.add(navel);

  // Braços: ombros largos, músculos contínuos, punhos e mãos humanas.
  const armData = [
    { side: -1, module: 'left-arm' },
    { side: 1, module: 'right-arm' },
  ];
  for (const { side, module } of armData) {
    const shoulder = new THREE.Vector3(side * 0.276, 1.43, 0.005);
    const elbow = new THREE.Vector3(side * 0.382, 1.145, 0.02);
    const wrist = new THREE.Vector3(side * 0.414, 0.87, 0.035);
    joint([shoulder.x, shoulder.y, shoulder.z], [0.076, 0.092, 0.082], module);
    surface(new THREE.SphereGeometry(1, 40, 28), [shoulder.x, shoulder.y + 0.005, 0.01], [0.082, 0.094, 0.088], module, { material: materials.body });
    between(new THREE.Vector3(side * 0.27, 1.405, 0), elbow, [[0, .066, .071], [.24, .079, .079], [.56, .074, .074], [1, .051, .054]], module);
    joint([elbow.x, elbow.y, elbow.z], [0.052, 0.057, 0.054], module);
    between(elbow, wrist, [[0, .054, .056], [.25, .064, .061], [.58, .059, .055], [.82, .045, .043], [1, .034, .034]], module);
    joint([wrist.x, wrist.y, wrist.z], [0.035, 0.039, 0.035], module);
    surface(new THREE.CapsuleGeometry(0.043, 0.1, 10, 24), [side * 0.416, 0.79, 0.044], [0.92, 1, 0.62], module, { material: materials.body });
    // Linhas musculares acompanham o volume do braço, sem carenagem.
    detailCapsule([side * 0.355, 1.305, 0.068], 0.004, 0.14, module, [0.12, 0, side * 0.2]);
    detailCapsule([side * 0.423, 1.015, 0.083], 0.0035, 0.15, module, [0.08, 0, side * 0.08]);
    // Polegar e quatro dedos, cada um com base e falange distal.
    const thumb = surface(new THREE.CapsuleGeometry(0.012, 0.062, 7, 16), [side * 0.456, 0.81, 0.047], [1, 1, 0.72], module, { rotation: [0, 0, side * 0.55] });
    thumb.rotation.y = side * 0.1;
    const lengths = [0.058, 0.067, 0.063, 0.053];
    lengths.forEach((length, index) => {
      const spread = (index - 1.5) * 0.014;
      const x = side * 0.416 + spread;
      surface(new THREE.SphereGeometry(1, 18, 12), [x, 0.742, 0.047], [0.008, 0.007, 0.006], module, { material: materials.detail, highlight: false });
      surface(new THREE.CapsuleGeometry(0.0065, length, 6, 14), [x, 0.708 - Math.abs(index - 1.5) * 0.003, 0.047], [1, 1, 0.75], module, { rotation: [0, 0, spread * 0.9] });
    });
  }

  // Pernas: quadril orgânico, coxas fortes, joelhos naturais e pés completos.
  for (const side of [-1, 1]) {
    const hip = new THREE.Vector3(side * 0.112, 0.93, 0);
    const knee = new THREE.Vector3(side * 0.118, 0.55, 0.018);
    const ankle = new THREE.Vector3(side * 0.11, 0.15, 0.008);
    joint([hip.x, hip.y, hip.z], [0.092, 0.098, 0.087], 'legs');
    between(hip, knee, [[0, .096, .094], [.18, .112, .108], [.48, .103, .099], [.76, .085, .083], [1, .063, .064]], 'legs');
    joint([knee.x, knee.y, knee.z], [0.063, 0.062, 0.064], 'legs');
    surface(new THREE.SphereGeometry(1, 32, 22), [side * 0.118, 0.55, 0.079], [0.034, 0.041, 0.013], 'legs', { material: materials.body });
    between(knee, ankle, [[0, .063, .064], [.16, .071, .069], [.42, .079, .074], [.66, .065, .061], [.84, .05, .048], [1, .038, .04]], 'legs');
    joint([ankle.x, ankle.y, ankle.z], [0.036, 0.039, 0.037], 'legs');
    surface(new THREE.CapsuleGeometry(0.055, 0.155, 10, 26), [side * 0.11, 0.07, 0.084], [1, 1, 0.78], 'legs', { rotation: [Math.PI / 2, 0, 0] });
    detailCapsule([side * 0.118, 0.73, 0.09], 0.004, 0.17, 'legs', [0.08, 0, side * 0.05]);
    detailCapsule([side * 0.112, 0.345, 0.076], 0.0035, 0.18, 'legs', [0.08, 0, side * 0.03]);
    detailCapsule([side * 0.11, 0.135, -0.036], 0.0045, 0.075, 'legs');
    const toeLengths = [0.032, 0.039, 0.044, 0.04, 0.033];
    toeLengths.forEach((length, index) => {
      surface(new THREE.CapsuleGeometry(0.007, length, 5, 12), [side * (0.11 + (index - 2) * 0.014), 0.042, 0.171 + length * 0.22], [1, 1, 0.8], 'legs', { material: materials.detail, rotation: [Math.PI / 2, 0, 0], highlight: false });
    });
  }

  // Assinatura C: marca aberta, não um disco genérico.
  const core = new THREE.Group();
  core.position.set(0, 1.355, 0.183);
  const cArc = Math.PI * 1.62;
  const cMark = new THREE.Mesh(new THREE.TorusGeometry(0.07, 0.0145, 20, 96, cArc), materials.core);
  cMark.rotation.z = Math.PI - cArc / 2;
  core.add(cMark);
  addToModule(cMark, 'power');
  const cHalo = new THREE.Mesh(new THREE.TorusGeometry(0.095, 0.0025, 8, 96, cArc), materials.seam);
  cHalo.rotation.z = Math.PI - cArc / 2;
  core.add(cHalo);
  const coreBack = new THREE.Mesh(new THREE.CylinderGeometry(0.087, 0.087, 0.008, 64), materials.coreBack);
  coreBack.rotation.x = Math.PI / 2;
  coreBack.position.z = -0.012;
  core.add(coreBack);
  addToModule(coreBack, 'power');
  body.add(core);

  // Escala antropométrica exata: 1,80 m do piso ao topo do crânio.
  const bounds = new THREE.Box3().setFromObject(body);
  const naturalHeight = bounds.max.y - bounds.min.y;
  const exactScale = 1.8 / naturalHeight;
  body.scale.setScalar(exactScale);
  body.position.y = -bounds.min.y * exactScale;

  // Plataforma de leitura espacial.
  const floor = new THREE.GridHelper(2.4, 24, 0x2e9caf, 0x132936);
  floor.material.transparent = true;
  floor.material.opacity = 0.28;
  rig.add(floor);
  for (let index = 0; index < 4; index += 1) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.43 + index * 0.12, 0.0028, 5, 128), index % 2 ? materials.seam : materials.detail);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.008;
    rig.add(ring);
  }
  const scanMaterial = new THREE.MeshBasicMaterial({ color: 0x8ff7ff, transparent: true, opacity: 0.18, side: THREE.DoubleSide, depthWrite: false });
  const scan = new THREE.Mesh(new THREE.PlaneGeometry(1.35, 0.006), scanMaterial);
  scan.position.set(0, 0.1, 0.34);
  rig.add(scan);

  const particlesGeometry = new THREE.BufferGeometry();
  const particlePositions = new Float32Array(160 * 3);
  for (let index = 0; index < particlePositions.length / 3; index += 1) {
    particlePositions[index * 3] = (Math.random() - 0.5) * 1.7;
    particlePositions[index * 3 + 1] = Math.random() * 1.95;
    particlePositions[index * 3 + 2] = (Math.random() - 0.5) * 0.75;
  }
  particlesGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
  scene.add(new THREE.Points(particlesGeometry, new THREE.PointsMaterial({ color: 0x5eead4, size: 0.006, transparent: true, opacity: 0.42 })));

  let selected = 'chest';
  function selectModule(id, notify = false) {
    selected = moduleMeshes.has(id) ? id : 'chest';
    for (const [module, meshes] of moduleMeshes) {
      for (const mesh of meshes) {
        if (!mesh.userData.highlight) continue;
        if (module === selected && module === 'power') {
          mesh.material = materials.coreSelected;
        } else if (module === selected) {
          if (!mesh.userData.selectedMaterial) {
            const selectedMaterial = mesh.userData.baseMaterial.clone();
            if (selectedMaterial.color) selectedMaterial.color.lerp(new THREE.Color(0x8fd8d6), 0.18);
            if (selectedMaterial.emissive) {
              selectedMaterial.emissive.lerp(new THREE.Color(0x1c7f87), 0.34);
              selectedMaterial.emissiveIntensity = Math.max(selectedMaterial.emissiveIntensity || 0, 0.28);
            }
            mesh.userData.selectedMaterial = selectedMaterial;
          }
          mesh.material = mesh.userData.selectedMaterial;
        } else {
          mesh.material = mesh.userData.baseMaterial;
        }
      }
    }
    if (notify) window.dispatchEvent(new CustomEvent('condor-x-picked', { detail: { id: selected } }));
  }
  window.addEventListener('condor-x-select', (event) => selectModule(event.detail.id));
  selectModule('chest');

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let dragging = false;
  let moved = false;
  let lastX = 0;
  let rotation = 0;
  renderer.domElement.addEventListener('pointerdown', (event) => {
    dragging = true;
    moved = false;
    lastX = event.clientX;
    renderer.domElement.setPointerCapture(event.pointerId);
  });
  renderer.domElement.addEventListener('pointermove', (event) => {
    if (!dragging) return;
    const delta = event.clientX - lastX;
    if (Math.abs(delta) > 1) moved = true;
    rotation += delta * 0.008;
    lastX = event.clientX;
  });
  renderer.domElement.addEventListener('pointerup', (event) => {
    if (!dragging) return;
    dragging = false;
    if (moved) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = (event.clientX - rect.left) / rect.width * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height * 2 - 1);
    raycaster.setFromCamera(pointer, camera);
    const id = raycaster.intersectObjects(interactive, false)[0]?.object.userData.module;
    if (id) selectModule(id, true);
  });

  function resize() {
    const width = Math.max(viewport.clientWidth, 320);
    const height = Math.max(viewport.clientHeight, 520);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(viewport);
  window.addEventListener('condor-x-resize', resize);
  resize();

  const started = performance.now();
  const animate = (now) => {
    const time = (now - started) / 1000;
    rig.rotation.y = rotation + Math.sin(time * 0.24) * 0.08;
    scan.position.y = 0.08 + (time * 0.31) % 1.72;
    scanMaterial.opacity = 0.14 + Math.sin(time * 3) * 0.06;
    core.scale.setScalar(1 + Math.sin(time * 2.3) * 0.035);
    renderer.render(scene, camera);
  };

  function setActive(active) {
    renderer.setAnimationLoop(active ? animate : null);
    if (active) {
      resize();
      renderer.render(scene, camera);
    }
  }
  window.addEventListener('condor-x-visibility', (event) => setActive(Boolean(event.detail?.active)));
  setActive(!document.getElementById('projectDetail')?.hidden);
}
