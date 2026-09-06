import * as THREE from '../vendor/three.module.min.js';
import { CondorBody3D } from './modeler-3d.js';

const COLORS = {
  shell: 0xdfe5e4,
  graphite: 0x121a20,
  carbon: 0x070c10,
  cyan: 0x58e4d3,
  amber: 0xe5b65e,
  critical: 0xe65d68,
  blue: 0x5f8fe8,
};

const CADX_BODY_Y_OFFSET = -935;

const DEFAULT_DESIGN_STATE = {
  concept: 'A', hypothesis: 'UNVALIDATED', mode: 'DESIGN', flightPoseDegrees: 0,
  pilotVisible: false, propulsionConcept: 'A',
  wing: { linked: true, spanScale: 1, rootChordScale: 1, tipChordScale: 1, sweepDegrees: 24, dihedralDegrees: 4, twistDegrees: -2, fold: 'DEPLOYED' },
  energyVolumes: [
    { id: 'CX-M01-ENERGY-CENTER', position: { x: 0, y: .56, z: -.12 }, status: 'DATA_REQUIRED' },
    { id: 'CX-M01-ENERGY-L', position: { x: -.26, y: .52, z: -.10 }, status: 'DATA_REQUIRED' },
    { id: 'CX-M01-ENERGY-R', position: { x: .26, y: .52, z: -.10 }, status: 'DATA_REQUIRED' },
  ],
  propulsionPods: [
    { id: 'CX-M01-PROP-DORSAL-L', position: { x: -.16, y: .91, z: -.30 }, role: 'DORSAL', status: 'DESIGN_CANDIDATE' },
    { id: 'CX-M01-PROP-DORSAL-R', position: { x: .16, y: .91, z: -.30 }, role: 'DORSAL', status: 'DESIGN_CANDIDATE' },
    { id: 'CX-M01-PROP-WROOT-L', position: { x: -.48, y: .99, z: -.22 }, role: 'WING_ROOT', status: 'DESIGN_CANDIDATE' },
    { id: 'CX-M01-PROP-WROOT-R', position: { x: .48, y: .99, z: -.22 }, role: 'WING_ROOT', status: 'DESIGN_CANDIDATE' },
  ],
};

function clone(value) { return JSON.parse(JSON.stringify(value)); }
function clamp(value, low, high) { return Math.max(low, Math.min(high, Number(value))); }

function mergeDesignState(raw = {}) {
  const state = clone(DEFAULT_DESIGN_STATE);
  const source = raw && typeof raw === 'object' ? raw : {};
  Object.assign(state, source);
  state.wing = { ...DEFAULT_DESIGN_STATE.wing, ...(source.wing || {}) };
  state.energyVolumes = Array.isArray(source.energyVolumes) && source.energyVolumes.length ? clone(source.energyVolumes) : clone(DEFAULT_DESIGN_STATE.energyVolumes);
  state.propulsionPods = Array.isArray(source.propulsionPods) && source.propulsionPods.length ? clone(source.propulsionPods) : clone(DEFAULT_DESIGN_STATE.propulsionPods);
  return state;
}

function disposeLayer(layer) {
  layer.traverse((item) => {
    item.geometry?.dispose?.();
    if (Array.isArray(item.material)) item.material.forEach((material) => material.dispose?.());
    else item.material?.dispose?.();
  });
  layer.clear();
}

function material(color, options = {}) {
  return new THREE.MeshPhysicalMaterial({
    color,
    emissive: options.emissive ?? 0x000000,
    emissiveIntensity: options.emissiveIntensity ?? .08,
    metalness: options.metalness ?? .15,
    roughness: options.roughness ?? .58,
    clearcoat: options.clearcoat ?? .22,
    clearcoatRoughness: options.clearcoatRoughness ?? .62,
    transparent: Boolean(options.transparent),
    opacity: options.opacity ?? 1,
    depthWrite: options.depthWrite ?? true,
    side: THREE.DoubleSide,
  });
}

function planformGeometry(points, thickness = 30) {
  const shape = new THREE.Shape();
  shape.moveTo(points[0][0], points[0][1]);
  points.slice(1).forEach(([x, y]) => shape.lineTo(x, y));
  shape.closePath();
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: thickness,
    steps: 1,
    bevelEnabled: true,
    bevelSegments: 3,
    bevelSize: Math.min(9, thickness * .24),
    bevelThickness: Math.min(7, thickness * .2),
    curveSegments: 2,
  });
  geometry.rotateX(-Math.PI / 2);
  geometry.translate(0, -thickness * .5, 0);
  geometry.computeVertexNormals();
  return geometry;
}

function lineFrom(points, color, opacity = .5) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  return new THREE.Line(geometry, new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false }));
}

const CADX_PART_STYLES = {
  neck: [COLORS.carbon, { metalness: .22, roughness: .66 }],
  chest: [0xf0f4f3, { metalness: .28, roughness: .24, clearcoat: .82, clearcoatRoughness: .15 }],
  abdomen: [COLORS.graphite, { metalness: .38, roughness: .42, clearcoat: .36, clearcoatRoughness: .3 }],
  pelvis: [0xe1e7e6, { metalness: .3, roughness: .3, clearcoat: .66, clearcoatRoughness: .2 }],
  shoulder: [0xf2f6f5, { metalness: .3, roughness: .22, clearcoat: .84, clearcoatRoughness: .14 }],
  upperArm: [0xdce3e2, { metalness: .3, roughness: .3, clearcoat: .58, clearcoatRoughness: .22 }],
  elbow: [COLORS.carbon, { metalness: .18, roughness: .7 }],
  forearm: [0xe8edec, { metalness: .32, roughness: .27, clearcoat: .68, clearcoatRoughness: .18 }],
  hand: [COLORS.carbon, { metalness: .24, roughness: .62 }],
  thigh: [0xe5eae9, { metalness: .3, roughness: .29, clearcoat: .62, clearcoatRoughness: .2 }],
  knee: [COLORS.carbon, { metalness: .2, roughness: .68 }],
  shin: [0xf0f4f3, { metalness: .32, roughness: .24, clearcoat: .74, clearcoatRoughness: .16 }],
  foot: [COLORS.carbon, { metalness: .26, roughness: .58 }],
};

function cadxRegionForTriangle(vertices) {
  const height = vertices.reduce((sum, vertex) => sum + vertex[2], 0) / vertices.length;
  if (height >= 1510) return null; // Replaced by the previous detailed Condor helmet.
  if (height < 900) return null; // The delivered OBJ has no usable limb surfaces below the torso.
  if (height >= 1435) return 'neck';
  if (height >= 1190) return 'chest';
  if (height >= 980) return 'abdomen';
  return 'pelvis';
}

function parseObjArmorParts(text) {
  const sourceVertices = [];
  const partsByRegion = new Map(Object.keys(CADX_PART_STYLES).map((region) => [region, {
    positions: [], indices: [], sourceToLocal: new Map(),
  }]));
  for (const rawLine of text.split(/\r?\n/)) {
    if (rawLine.startsWith('v ')) {
      const fields = rawLine.trim().split(/\s+/);
      sourceVertices.push([Number(fields[1]), Number(fields[2]), Number(fields[3])]);
      continue;
    }
    if (!rawLine.startsWith('f ')) continue;
    const indices = rawLine.trim().slice(2).split(/\s+/).map((reference) => {
      const index = Number(reference.split('/')[0]);
      return index < 0 ? sourceVertices.length + index : index - 1;
    });
    for (let index = 1; index < indices.length - 1; index += 1) {
      const vertices = [indices[0], indices[index], indices[index + 1]].map((vertexIndex) => sourceVertices[vertexIndex]);
      if (vertices.some((vertex) => !vertex || !vertex.every(Number.isFinite))) continue;
      const region = cadxRegionForTriangle(vertices);
      if (!region) continue;
      const part = partsByRegion.get(region);
      [indices[0], indices[index], indices[index + 1]].forEach((sourceIndex) => {
        if (!part.sourceToLocal.has(sourceIndex)) {
          const vertex = sourceVertices[sourceIndex];
          part.sourceToLocal.set(sourceIndex, part.positions.length / 3);
          part.positions.push(vertex[0], vertex[2], -vertex[1]);
        }
        part.indices.push(part.sourceToLocal.get(sourceIndex));
      });
    }
  }
  const geometries = new Map();
  partsByRegion.forEach((part, region) => {
    if (!part.indices.length) return;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(part.positions, 3));
    geometry.setIndex(part.indices);
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    geometries.set(region, geometry);
  });
  if (!geometries.size) throw new Error('OBJ sem faces utilizáveis');
  return geometries;
}

function addSelectable(target, root, id, role) {
  root.userData.unitId = id;
  root.userData.designRole = role;
  root.traverse((child) => { if (child.isMesh) { child.userData.unitId = id; child.userData.designRole = role; } });
  target.engineeringMeshes.push(root);
  target.designObjects.set(id, root);
}

export class CondorDesignStudio3D extends CondorBody3D {
  constructor(host, callbacks = {}) {
    super(host, callbacks.onBodyPick);
    this.onDesignSelect = callbacks.onDesignSelect || null;
    this.onDesignMove = callbacks.onDesignMove || null;
    this.onEngineeringSelect = (id) => { this.selectDesign(id); this.onDesignSelect?.(id); };
    this.onEngineeringMove = (id, position) => this.onDesignMove?.(id, position);
    this.engineeringEnabled = true;
    this.designState = mergeDesignState();
    this.analysis = null;
    this.selectedDesignId = 'CX-M01-WING-L';
    this.designObjects = new Map();
    this.designLayer = new THREE.Group();
    this.flowLayer = new THREE.Group();
    this.cadxReferenceLayer = new THREE.Group();
    this.scene.add(this.designLayer, this.flowLayer, this.cadxReferenceLayer);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = .84;
    this.yaw = -2.48;
    this.pitch = .11;
    this.rebuildStudio();
    this.fitStudioView();
    this.loadCadxReference();
  }

  setParts(parts = []) { super.setParts(parts); this.fitStudioView(); }
  applyPart(part) { super.applyPart(part); this.fitStudioView(); }

  setDesignState(state, analysis = this.analysis) {
    this.designState = mergeDesignState(state);
    this.analysis = analysis || null;
    this.rebuildStudio();
  }

  setMode(mode) {
    this.designState.mode = String(mode || 'DESIGN').toUpperCase();
    this.rebuildStudio();
  }

  setAnalysis(analysis) { this.analysis = analysis || null; this.rebuildStudio(); }

  async loadCadxReference() {
    try {
      const response = await fetch('./assets/cadx/Untitled-Project.obj', { cache: 'no-store' });
      if (!response.ok) throw new Error(`OBJ CADx indisponível (${response.status})`);
      const geometries = parseObjArmorParts(await response.text());
      const reference = new THREE.Group();
      reference.name = 'CADX-MANNEQUIN-OBJ-R1';
      geometries.forEach((geometry, region) => {
        const [color, options] = CADX_PART_STYLES[region];
        const part = new THREE.Mesh(geometry, material(color, options));
        part.name = `CADX-ARMOR-${region.toUpperCase()}`;
        part.userData.region = region;
        part.userData.referenceOnly = true;
        reference.add(part);
      });
      reference.position.y = CADX_BODY_Y_OFFSET;
      disposeLayer(this.cadxReferenceLayer);
      this.cadxReferenceLayer.add(reference);

      // Reuse the detailed helmet and all missing articulated limbs from the previous prototype.
      this.body.visible = true;
      this.body.children.forEach((bodyRegion) => {
        const region = bodyRegion.children?.find((child) => child.userData?.region)?.userData?.region;
        const suppliedByCadx = ['neck', 'chest', 'abdomen', 'pelvis', 'power'].includes(region);
        const isHead = region === 'head';
        bodyRegion.visible = bodyRegion === this.armorClosures || Boolean(region && !suppliedByCadx);
        if (isHead) bodyRegion.position.y = 765;
      });

      const emblemBack = new THREE.Mesh(
        new THREE.CircleGeometry(48, 36),
        material(0x05090c, { metalness: .42, roughness: .32, clearcoat: .65, clearcoatRoughness: .2 }),
      );
      emblemBack.name = 'CX-CHEST-EMBLEM-BACK';
      emblemBack.position.set(0, 400, 214);
      this.cadxReferenceLayer.add(emblemBack);
      const chestMark = new THREE.Mesh(
        new THREE.TorusGeometry(37, 7, 9, 30, Math.PI * 1.56),
        material(COLORS.amber, { emissive: 0x5a3505, emissiveIntensity: .55, metalness: .34, roughness: .28, clearcoat: .66, clearcoatRoughness: .17 }),
      );
      chestMark.name = 'CX-CHEST-MARK';
      chestMark.position.set(0, 400, 219);
      chestMark.rotation.z = Math.PI * .22;
      chestMark.userData.referenceOnly = true;
      this.cadxReferenceLayer.add(chestMark);
      this.fitStudioView();
      window.dispatchEvent(new CustomEvent('condor-cadx-reference-ready', { detail: { assetId: reference.name } }));
    } catch (error) {
      console.warn('Referência OBJ CADx não carregada', error);
    }
  }

  setView(view) {
    if (view === 'rear') { this.yaw = Math.PI; this.pitch = .04; }
    else if (view === 'front') { this.yaw = 0; this.pitch = .02; }
    else if (view === 'side') { this.yaw = -Math.PI / 2; this.pitch = .02; }
    else if (view === 'iso') { this.yaw = -2.48; this.pitch = .11; }
    this.fitStudioView();
  }

  selectDesign(id) {
    this.selectedDesignId = id;
    this.designObjects.forEach((object, objectId) => {
      object.traverse((item) => {
        if (!item.material?.emissive || item.userData.overlay) return;
        const selected = objectId === id || id.startsWith(`${objectId}:`);
        item.material.emissive.setHex(selected ? 0x123a36 : (item.userData.baseEmissive || 0x000000));
        item.material.emissiveIntensity = selected ? .32 : .08;
      });
    });
    this.render();
  }

  applyBodyPresentation() {
    const showPilot = this.designState.pilotVisible || this.designState.mode === 'SAFETY';
    this.meshes.forEach((mesh) => {
      const joint = !mesh.userData.armorClosure && ['neck', 'left-elbow', 'right-elbow', 'left-knee', 'right-knee', 'left-hand', 'right-hand'].includes(mesh.userData.region);
      const helmet = mesh.userData.region === 'head';
      mesh.material.metalness = helmet ? .3 : (joint ? .12 : .08);
      mesh.material.roughness = helmet ? .24 : (joint ? .72 : .58);
      mesh.material.clearcoat = helmet ? .96 : (joint ? .08 : .18);
      if (helmet) mesh.material.clearcoatRoughness = .12;
      mesh.material.transparent = showPilot;
      mesh.material.opacity = showPilot ? (joint ? .3 : .22) : 1;
      mesh.material.depthWrite = !showPilot;
      mesh.material.needsUpdate = true;
    });
    this.body.traverse((item) => {
      if (!item.userData.helmetDetail || !item.material) return;
      const baseOpacity = item.material.userData.baseOpacity ?? 1;
      item.material.transparent = showPilot || baseOpacity < 1;
      item.material.opacity = showPilot ? baseOpacity * .22 : baseOpacity;
      item.material.depthWrite = !showPilot;
      item.material.needsUpdate = true;
    });
  }

  buildDorsalStructure() {
    const group = new THREE.Group();
    const spine = new THREE.Mesh(new THREE.CapsuleGeometry(34, 580, 8, 16), material(COLORS.carbon, { metalness: .32, roughness: .48 }));
    spine.position.set(0, 235, -192); group.add(spine);
    const fairing = new THREE.Mesh(new THREE.CapsuleGeometry(54, 360, 8, 18), material(COLORS.graphite, { roughness: .5 }));
    fairing.position.set(0, 405, -174); fairing.scale.set(.72, 1, .48); group.add(fairing);
    const neck = new THREE.Mesh(new THREE.CylinderGeometry(54, 92, 150, 18, 1, false), material(COLORS.graphite, { roughness: .62 }));
    neck.position.set(0, 590, -110); neck.rotation.x = -.14; group.add(neck);
    group.userData.componentId = 'CX-M01-DORSAL-SPINE';
    this.designLayer.add(group);
    addSelectable(this, group, 'CX-M01-DORSAL-SPINE', 'STRUCTURE');
  }

  wingGeometry(side) {
    const wing = this.designState.wing;
    const span = 920 * clamp(wing.spanScale, .65, 1.65);
    const rootChord = 330 * clamp(wing.rootChordScale, .65, 1.5);
    const tipChord = 122 * clamp(wing.tipChordScale, .55, 1.5);
    const sweep = 160 + Math.tan(THREE.MathUtils.degToRad(clamp(wing.sweepDegrees, 5, 55))) * span * .32;
    return { span, rootChord, tipChord, sweep, points: [[0, 0], [side * span, sweep], [side * span, sweep + tipChord], [side * span * .16, rootChord * .96], [0, rootChord]] };
  }

  buildWing(side) {
    const id = side < 0 ? 'CX-M01-WING-L' : 'CX-M01-WING-R';
    const definition = this.wingGeometry(side);
    const group = new THREE.Group();
    group.position.set(side * 145, 515, -178);
    const shell = new THREE.Mesh(planformGeometry(definition.points, 34), material(COLORS.graphite, { metalness: .42, roughness: .34, clearcoat: .48, clearcoatRoughness: .24 }));
    shell.userData.baseEmissive = 0x000000; group.add(shell);

    const leadingEdge = lineFrom([
      new THREE.Vector3(0, 20, 0),
      new THREE.Vector3(side * definition.span, 20, -definition.sweep),
    ], COLORS.cyan, .88);
    leadingEdge.userData.overlay = true; group.add(leadingEdge);

    const rootFairing = new THREE.Mesh(new THREE.CapsuleGeometry(58, 220, 8, 18), material(COLORS.graphite, { roughness: .48 }));
    rootFairing.rotation.z = Math.PI / 2; rootFairing.position.set(side * 78, 0, -definition.rootChord * .28); rootFairing.scale.set(.7, 1, .62); group.add(rootFairing);

    const controlPoints = [
      [side * definition.span * .34, definition.rootChord * .78],
      [side * definition.span * .94, definition.sweep + definition.tipChord * .72],
      [side * definition.span * .94, definition.sweep + definition.tipChord],
      [side * definition.span * .34, definition.rootChord * .96],
    ];
    const control = new THREE.Mesh(planformGeometry(controlPoints, 12), material(0xe4e9e8, { metalness: .3, roughness: .32, clearcoat: .55, clearcoatRoughness: .22 }));
    control.position.y = -24; control.userData.overlay = true; group.add(control);

    const seamMaterial = new THREE.LineBasicMaterial({ color: 0x69777b, transparent: true, opacity: .52, depthWrite: false });
    [.2, .78].forEach((ratio) => {
      const x = side * definition.span * ratio;
      const leading = definition.sweep * ratio;
      const chord = THREE.MathUtils.lerp(definition.rootChord, definition.tipChord, ratio);
      const seam = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x, 21, -leading), new THREE.Vector3(x, 21, -(leading + chord))]), seamMaterial.clone());
      seam.userData.overlay = true; group.add(seam);
    });

    const fold = this.designState.wing.fold === 'STOWED' ? 68 : this.designState.wing.fold === 'PARTIAL' ? 32 : 0;
    group.rotation.z = side * THREE.MathUtils.degToRad(clamp(this.designState.wing.dihedralDegrees, -12, 22) + fold);
    group.rotation.x = THREE.MathUtils.degToRad(clamp(this.designState.wing.twistDegrees, -15, 15));
    this.designLayer.add(group);
    addSelectable(this, group, id, 'WING');

    const handle = new THREE.Mesh(new THREE.SphereGeometry(28, 14, 10), material(COLORS.amber, { emissive: 0x3b2608, emissiveIntensity: .22, roughness: .42 }));
    handle.position.set(side * definition.span, 0, -(definition.sweep + definition.tipChord * .5));
    handle.userData.unitId = `${id}:SPAN`; handle.userData.designRole = 'WING_HANDLE';
    group.add(handle); this.engineeringMeshes.push(handle); this.designObjects.set(`${id}:SPAN`, handle);
  }

  buildEnergyVolumes() {
    this.designState.energyVolumes.forEach((record, index) => {
      const group = new THREE.Group();
      const geometry = new THREE.SphereGeometry(index === 0 ? 88 : 66, 24, 16);
      const mesh = new THREE.Mesh(geometry, material(COLORS.cyan, { transparent: true, opacity: .2, depthWrite: false, emissive: 0x0b3b37, emissiveIntensity: .24, roughness: .38 }));
      mesh.scale.set(index === 0 ? 1.35 : 1, index === 0 ? 1.7 : 1.45, .64); group.add(mesh);
      const cage = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), new THREE.LineBasicMaterial({ color: COLORS.cyan, transparent: true, opacity: .34, depthWrite: false }));
      cage.scale.copy(mesh.scale); cage.userData.overlay = true; group.add(cage);
      group.position.set(Number(record.position?.x || 0) * 1000, Number(record.position?.y || 0) * 1000, Number(record.position?.z || 0) * 1000);
      this.designLayer.add(group); addSelectable(this, group, record.id, 'ENERGY');
    });
  }

  conceptPodPosition(record) {
    const position = { x: Number(record.position?.x || 0), y: Number(record.position?.y || 0), z: Number(record.position?.z || 0) };
    if (this.designState.propulsionConcept === 'B') return { x: position.x * .62, y: position.y - .04, z: position.z - .02 };
    if (this.designState.propulsionConcept === 'C') return { x: position.x * 1.32, y: position.y + (record.role === 'WING_ROOT' ? .02 : -.08), z: position.z + .05 };
    return position;
  }

  buildPropulsionPods() {
    this.designState.propulsionPods.forEach((record) => {
      const position = this.conceptPodPosition(record);
      const group = new THREE.Group();
      const rootRole = record.role === 'WING_ROOT';
      const geometry = new THREE.CapsuleGeometry(rootRole ? 42 : 48, rootRole ? 150 : 178, 7, 18);
      const outer = new THREE.Mesh(geometry, material(COLORS.graphite, { roughness: .52, metalness: .2, transparent: true, opacity: .28, depthWrite: false }));
      outer.rotation.z = rootRole ? Math.PI / 2 : 0; outer.scale.z = .68; outer.userData.baseEmissive = 0x000000; group.add(outer);
      const envelope = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: COLORS.amber, wireframe: true, transparent: true, opacity: .38, depthWrite: false }));
      envelope.rotation.copy(outer.rotation); envelope.scale.copy(outer.scale); envelope.userData.overlay = true; group.add(envelope);
      const aperture = new THREE.Mesh(new THREE.TorusGeometry(rootRole ? 36 : 41, 4, 8, 30), material(COLORS.amber, { transparent: true, opacity: .55, emissive: 0x3b2608, emissiveIntensity: .18, metalness: .18, roughness: .58 }));
      aperture.rotation.x = Math.PI / 2; aperture.position.y = rootRole ? 0 : -112; aperture.scale.set(1, .68, 1); group.add(aperture);
      group.position.set(position.x * 1000, position.y * 1000, position.z * 1000);
      group.userData.conceptEnvelope = true;
      this.designLayer.add(group); addSelectable(this, group, record.id, 'PROPULSION');
    });
  }

  buildPilot() {
    const pilot = new THREE.Group();
    const pilotMaterial = material(0x7aa8a5, { transparent: true, opacity: .22, depthWrite: false, emissive: 0x133b38, emissiveIntensity: .18, roughness: .8 });
    const head = new THREE.Mesh(new THREE.SphereGeometry(82, 20, 14), pilotMaterial); head.position.y = 1110; pilot.add(head);
    const torso = new THREE.Mesh(new THREE.CapsuleGeometry(92, 390, 6, 16), pilotMaterial); torso.position.y = 660; torso.scale.z = .55; pilot.add(torso);
    for (const side of [-1, 1]) {
      const arm = new THREE.Mesh(new THREE.CapsuleGeometry(38, 520, 5, 12), pilotMaterial); arm.position.set(side * 235, 550, 0); arm.rotation.z = side * -.08; pilot.add(arm);
      const leg = new THREE.Mesh(new THREE.CapsuleGeometry(52, 640, 5, 12), pilotMaterial); leg.position.set(side * 88, -150, 0); pilot.add(leg);
    }
    pilot.userData.componentId = 'CX-M01-PILOT-SURVIVAL-VOLUME'; this.designLayer.add(pilot);
  }

  buildCenters() {
    const cg = this.analysis?.massEngine?.vehicleCg;
    if (cg) {
      const marker = new THREE.Mesh(new THREE.SphereGeometry(24, 16, 12), material(COLORS.amber, { emissive: 0x3b2608, emissiveIntensity: .4, roughness: .45 }));
      marker.position.set(Number(cg.x) * 1000, Number(cg.y) * 1000, Number(cg.z) * 1000); marker.userData.overlay = true; this.designLayer.add(marker);
      const cross = new THREE.AxesHelper(90); cross.position.copy(marker.position); this.designLayer.add(cross);
    }
    const thrust = this.analysis?.propulsionEngine?.centerOfThrust;
    if (thrust && this.designState.mode === 'PROPULSION') {
      const marker = new THREE.Mesh(new THREE.OctahedronGeometry(28), material(COLORS.cyan, { emissive: 0x0c3c38, emissiveIntensity: .35 }));
      marker.position.set(Number(thrust.x) * 1000, Number(thrust.y) * 1000, Number(thrust.z) * 1000); marker.userData.overlay = true; this.designLayer.add(marker);
    }
  }

  buildPropulsionVectors() {
    if (this.designState.mode !== 'PROPULSION') return;
    const states = new Map((this.analysis?.propulsionEngine?.unitStates || []).map((item) => [item.unitId, item]));
    this.designState.propulsionPods.forEach((record) => {
      const position = this.conceptPodPosition(record); const state = states.get(record.id);
      if (!state?.direction || !(Number(state.thrust) > 0)) return;
      const direction = new THREE.Vector3(Number(state.direction.x), Number(state.direction.y), Number(state.direction.z)).normalize();
      const length = Math.max(120, Math.log1p(state.thrust) * 56);
      const arrow = new THREE.ArrowHelper(direction, new THREE.Vector3(position.x * 1000, position.y * 1000, position.z * 1000), length, COLORS.cyan, 34, 16);
      arrow.userData.overlay = true; this.designLayer.add(arrow);
    });
  }

  buildThermalOverlay() {
    if (!['THERMAL', 'SAFETY'].includes(this.designState.mode)) return;
    const stateById = new Map((this.analysis?.propulsionEngine?.unitStates || []).map((item) => [item.unitId, item]));
    this.designState.propulsionPods.forEach((record) => {
      const position = this.conceptPodPosition(record); const state = stateById.get(record.id);
      const hasResult = state?.thermalOutput != null;
      const radius = hasResult ? Math.max(74, Math.min(240, Math.log1p(state.thermalOutput) * 28)) : 92;
      const sphere = new THREE.Mesh(new THREE.SphereGeometry(radius, 18, 12), material(hasResult ? COLORS.critical : COLORS.amber, { transparent: true, opacity: hasResult ? .12 : .055, depthWrite: false, emissive: hasResult ? 0x471016 : 0x3b2608, emissiveIntensity: .2 }));
      sphere.position.set(position.x * 1000, position.y * 1000, position.z * 1000); sphere.userData.overlay = true; this.designLayer.add(sphere);
    });
  }

  buildFlowPreview() {
    disposeLayer(this.flowLayer);
    if (this.designState.mode !== 'AERO') return;
    const span = 760 * clamp(this.designState.wing.spanScale, .65, 1.65);
    const pose = THREE.MathUtils.degToRad(this.designState.flightPoseDegrees);
    const materialLine = new THREE.LineBasicMaterial({ color: COLORS.cyan, transparent: true, opacity: .34, depthWrite: false });
    [-.95, -.68, -.42, -.18, .18, .42, .68, .95].forEach((ratio, index) => {
      const x = ratio * span; const bodyDeflection = Math.exp(-Math.abs(ratio) * 2.2) * 150;
      const points = [
        new THREE.Vector3(x, 460 + index % 2 * 95, 1550),
        new THREE.Vector3(x * .92, 500 + Math.sin(pose) * 110, 720),
        new THREE.Vector3(x * .78, 540 + bodyDeflection * .2, 80),
        new THREE.Vector3(x, 520 - bodyDeflection * .14, -650),
        new THREE.Vector3(x * 1.06, 500, -1450),
      ];
      const curve = new THREE.CatmullRomCurve3(points); const geometry = new THREE.BufferGeometry().setFromPoints(curve.getPoints(64));
      const line = new THREE.Line(geometry, materialLine.clone()); line.userData.overlay = true; this.flowLayer.add(line);
    });
  }

  rebuildStudio() {
    if (!this.designLayer || !this.flowLayer) return;
    disposeLayer(this.designLayer); this.engineeringMeshes = []; this.designObjects.clear();
    this.applyBodyPresentation();
    this.buildDorsalStructure();
    this.buildWing(-1); this.buildWing(1);
    if (['PROPULSION', 'THERMAL'].includes(this.designState.mode)) this.buildPropulsionPods();
    if (['MASS_CG', 'ENERGY', 'THERMAL', 'SAFETY'].includes(this.designState.mode)) this.buildEnergyVolumes();
    if (this.designState.pilotVisible || this.designState.mode === 'SAFETY') this.buildPilot();
    if (['MASS_CG', 'ENERGY', 'PROPULSION', 'SAFETY'].includes(this.designState.mode)) this.buildCenters();
    this.buildPropulsionVectors(); this.buildThermalOverlay(); this.buildFlowPreview();
    const pose = THREE.MathUtils.degToRad(clamp(this.designState.flightPoseDegrees, 0, 90));
    this.body.rotation.x = -pose; this.designLayer.rotation.x = -pose; this.cadxReferenceLayer.rotation.x = -pose;
    this.selectDesign(this.selectedDesignId);
    this.render();
  }

  fitStudioView() {
    if (!this.designLayer) return;
    this.body.updateMatrixWorld(true); this.designLayer.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(this.body)
      .union(new THREE.Box3().setFromObject(this.designLayer))
      .union(new THREE.Box3().setFromObject(this.cadxReferenceLayer));
    if (bounds.isEmpty()) return;
    const center = bounds.getCenter(new THREE.Vector3()); const size = bounds.getSize(new THREE.Vector3());
    const vertical = THREE.MathUtils.degToRad(this.camera.fov); const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * Math.max(.2, this.camera.aspect));
    this.target.copy(center); this.distance = Math.max(size.y / (2 * Math.tan(vertical / 2)), size.x / (2 * Math.tan(horizontal / 2))) * 1.1 + size.z * .42;
    this.distance = Math.max(2300, Math.min(7600, this.distance)); this.render();
  }
}

export { DEFAULT_DESIGN_STATE };
