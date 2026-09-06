import * as THREE from '../vendor/three.module.min.js';

const PRESETS = {
  head: [270, 180, 165, 215, 195, 14, 0, 2.2], neck: [115, 104, 96, 120, 110, 8, 0, 2.05],
  chest: [370, 285, 180, 430, 240, 24, 0, 2.75], abdomen: [250, 245, 170, 292, 195, 15, 0, 2.55],
  pelvis: [210, 315, 195, 340, 215, 14, 0, 2.8], power: [120, 120, 76, 120, 76, 4, 0, 2.3],
  shoulder: [160, 120, 110, 170, 150, 18, 8, 2.15], upperArm: [290, 88, 82, 124, 112, 12, 4, 2.08],
  elbow: [105, 92, 86, 98, 92, 8, 0, 2.0], forearm: [270, 76, 66, 108, 94, 13, 5, 2.05],
  hand: [190, 98, 44, 86, 36, 8, 0, 2.8], thigh: [440, 126, 120, 174, 158, 17, 4, 2.1],
  knee: [130, 108, 104, 122, 116, 9, 0, 2.05], shin: [395, 82, 74, 120, 106, 12, 3, 2.08],
  foot: [270, 112, 76, 94, 64, 10, 0, 2.65],
};

const REGION_KIND = {
  head: 'head', neck: 'neck', chest: 'chest', abdomen: 'abdomen', pelvis: 'pelvis', power: 'power',
  'left-shoulder': 'shoulder', 'right-shoulder': 'shoulder',
  'left-upper-arm': 'upperArm', 'right-upper-arm': 'upperArm',
  'left-elbow': 'elbow', 'right-elbow': 'elbow',
  'left-forearm': 'forearm', 'right-forearm': 'forearm',
  'left-hand': 'hand', 'right-hand': 'hand',
  'left-thigh': 'thigh', 'right-thigh': 'thigh',
  'left-knee': 'knee', 'right-knee': 'knee',
  'left-shin': 'shin', 'right-shin': 'shin',
  'left-foot': 'foot', 'right-foot': 'foot',
};

const PARAMETER_DEFS = [
  ['length', 'COMPRIMENTO', 60, 700, 'mm'], ['proximalWidth', 'LARGURA PROXIMAL', 30, 480, 'mm'],
  ['distalWidth', 'LARGURA DISTAL', 30, 480, 'mm'], ['proximalDepth', 'PROFUNDIDADE PROXIMAL', 20, 320, 'mm'],
  ['distalDepth', 'PROFUNDIDADE DISTAL', 20, 320, 'mm'], ['bulge', 'VOLUME CENTRAL', -40, 90, 'mm'],
  ['thickness', 'ESPESSURA DA CASCA', 1, 30, 'mm'], ['clearance', 'FOLGA INTERNA', 0, 45, 'mm'],
  ['asymmetry', 'ASSIMETRIA LATERAL', -45, 45, 'mm'], ['twist', 'TORÇÃO DO PERFIL', -90, 90, '°'],
  ['shape', 'FORMA DO PERFIL', 1.5, 4.5, ''],
];

function defaultsFor(region) {
  const kind = REGION_KIND[region] || (region.includes('arm') ? 'upperArm' : region.includes('leg') || region === 'legs' ? 'thigh' : 'chest');
  const [length, distalWidth, distalDepth, proximalWidth, proximalDepth, bulge, asymmetry, shape] = PRESETS[kind];
  return { length, proximalWidth, distalWidth, proximalDepth, distalDepth, bulge, thickness: 4, clearance: 8, asymmetry, twist: 0, shape };
}

function finiteNumber(value, fallback, min, max) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(max, Math.max(min, number)) : fallback;
}

function normalizedParameters(region, raw = {}) {
  const base = defaultsFor(region);
  const result = {};
  PARAMETER_DEFS.forEach(([key, , min, max]) => { result[key] = finiteNumber(raw[key], base[key], min, max); });
  const maxWall = Math.max(1, Math.min(result.distalWidth, result.proximalWidth, result.distalDepth, result.proximalDepth) * .42);
  result.thickness = Math.min(result.thickness, maxWall);
  return result;
}

function superellipse(angle, exponent) {
  const c = Math.cos(angle); const s = Math.sin(angle); const power = 2 / exponent;
  return [Math.sign(c) * Math.pow(Math.abs(c), power), Math.sign(s) * Math.pow(Math.abs(s), power)];
}

function surfaceSample(params, axial, angle, inner = false, profile = null) {
  const smooth = axial * axial * (3 - 2 * axial);
  const flare = Math.sin(Math.PI * axial);
  const clearance = params.clearance;
  let rx = THREE.MathUtils.lerp(params.distalWidth, params.proximalWidth, smooth) * .5 + clearance + params.bulge * flare;
  let rz = THREE.MathUtils.lerp(params.distalDepth, params.proximalDepth, smooth) * .5 + clearance + params.bulge * flare * .55;
  if (inner) { rx = Math.max(2, rx - params.thickness); rz = Math.max(2, rz - params.thickness); }
  const form = profile ? profile(axial, angle) : null;
  if (form) { rx *= form.width ?? 1; rz *= form.depth ?? 1; }
  const [sx, sz] = superellipse(angle, params.shape);
  const twist = THREE.MathUtils.degToRad(params.twist) * (axial - .5);
  const x0 = sx * rx; const z0 = sz * rz;
  return new THREE.Vector3(
    x0 * Math.cos(twist) - z0 * Math.sin(twist) + params.asymmetry * flare + (form?.x || 0),
    (axial - .5) * params.length + (form?.y || 0),
    x0 * Math.sin(twist) + z0 * Math.cos(twist) + (form?.z || 0),
  );
}

function buildParametricShell(params, options = {}) {
  const rings = options.rings || 36; const segments = options.segments || 64; const profile = options.profile || null;
  const vertices = []; const indices = [];
  const stride = segments;
  for (const inner of [false, true]) {
    for (let ring = 0; ring <= rings; ring += 1) {
      const axial = ring / rings;
      for (let segment = 0; segment < segments; segment += 1) {
        const point = surfaceSample(params, axial, segment / segments * Math.PI * 2, inner, profile);
        vertices.push(point.x, point.y, point.z);
      }
    }
  }
  const innerOffset = (rings + 1) * segments;
  for (let ring = 0; ring < rings; ring += 1) {
    for (let segment = 0; segment < segments; segment += 1) {
      const next = (segment + 1) % segments;
      const a = ring * stride + segment; const b = ring * stride + next;
      const c = (ring + 1) * stride + segment; const d = (ring + 1) * stride + next;
      indices.push(a, c, b, b, c, d);
      const ia = innerOffset + a; const ib = innerOffset + b; const ic = innerOffset + c; const id = innerOffset + d;
      indices.push(ia, ib, ic, ib, id, ic);
    }
  }
  for (const ring of [0, rings]) {
    const outer = ring * stride; const inner = innerOffset + outer;
    for (let segment = 0; segment < segments; segment += 1) {
      const next = (segment + 1) % segments;
      if (ring === 0) indices.push(outer + segment, outer + next, inner + segment, outer + next, inner + next, inner + segment);
      else indices.push(outer + segment, inner + segment, outer + next, outer + next, inner + segment, inner + next);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setIndex(indices); geometry.computeVertexNormals(); geometry.computeBoundingSphere();
  return geometry;
}

function buildShellEndCap(params, axial, profile = null, options = {}) {
  const segments = options.segments || 48; const radialRings = options.radialRings || 5;
  const endY = (axial - .5) * params.length; const direction = axial >= .5 ? 1 : -1;
  const domeHeight = options.domeHeight || Math.max(8, Math.min(params.proximalWidth, params.proximalDepth) * .1);
  const edge = [];
  for (let segment = 0; segment < segments; segment += 1) {
    edge.push(surfaceSample(params, axial, segment / segments * Math.PI * 2, false, profile));
  }
  const centerX = edge.reduce((sum, point) => sum + point.x, 0) / edge.length;
  const centerZ = edge.reduce((sum, point) => sum + point.z, 0) / edge.length;
  const vertices = [centerX, endY + direction * domeHeight, centerZ]; const indices = [];
  for (let ring = 1; ring <= radialRings; ring += 1) {
    const radial = ring / radialRings; const crown = 1 - radial * radial;
    edge.forEach((point) => {
      vertices.push(
        THREE.MathUtils.lerp(centerX, point.x, radial),
        endY + direction * domeHeight * crown,
        THREE.MathUtils.lerp(centerZ, point.z, radial),
      );
    });
  }
  for (let segment = 0; segment < segments; segment += 1) {
    const next = (segment + 1) % segments;
    if (direction > 0) indices.push(0, 1 + next, 1 + segment);
    else indices.push(0, 1 + segment, 1 + next);
  }
  for (let ring = 1; ring < radialRings; ring += 1) {
    const inner = 1 + (ring - 1) * segments; const outer = inner + segments;
    for (let segment = 0; segment < segments; segment += 1) {
      const next = (segment + 1) % segments;
      if (direction > 0) indices.push(inner + segment, outer + next, outer + segment, inner + segment, inner + next, outer + next);
      else indices.push(inner + segment, outer + segment, outer + next, inner + segment, outer + next, inner + next);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)); geometry.setIndex(indices);
  geometry.computeVertexNormals(); geometry.computeBoundingBox(); geometry.computeBoundingSphere(); return geometry;
}

function transformGeometry(geometry, transform = {}) {
  if (transform.scale) geometry.scale(...transform.scale);
  if (transform.rotation) {
    geometry.rotateX(transform.rotation[0] || 0); geometry.rotateY(transform.rotation[1] || 0); geometry.rotateZ(transform.rotation[2] || 0);
  }
  if (transform.position) geometry.translate(...transform.position);
  return geometry;
}

function mergeGeometryParts(parts) {
  const arrays = []; let length = 0;
  parts.forEach((part) => {
    const flat = part.index ? part.toNonIndexed() : part;
    const positions = flat.getAttribute('position').array; arrays.push(positions); length += positions.length;
    if (flat !== part) flat.dispose(); part.dispose();
  });
  const positions = new Float32Array(length); let offset = 0;
  arrays.forEach((array) => { positions.set(array, offset); offset += array.length; });
  const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.computeVertexNormals(); geometry.computeBoundingBox(); geometry.computeBoundingSphere(); return geometry;
}

function organicPart(parameters, transform = {}, options = {}) {
  return transformGeometry(buildParametricShell(parameters, options), transform);
}

function helmetDefinition(params) {
  const width = Math.max(params.proximalWidth, params.distalWidth) + params.clearance * 2;
  const depth = Math.max(params.proximalDepth, params.distalDepth) + params.clearance * 2;
  const skull = { ...params, proximalWidth: width, distalWidth: width, proximalDepth: depth, distalDepth: depth, bulge: 0, clearance: 0, asymmetry: 0, shape: Math.max(2.05, params.shape) };
  const profile = (axial, angle) => {
    const curve = Math.sin(Math.PI * axial);
    const jawTaper = .6 + .4 * Math.min(1, axial / .36);
    const widthFactor = (.025 + Math.pow(Math.max(0, curve), .48) * (.8 + .08 * axial)) * jawTaper;
    const depthFactor = .04 + Math.pow(Math.max(0, curve), .48) * (.82 + .1 * axial);
    const front = Math.pow(Math.max(0, Math.sin(angle)), 6);
    const rear = Math.pow(Math.max(0, -Math.sin(angle)), 6);
    const faceKeel = Math.exp(-Math.pow((axial - .43) / .2, 2)) * depth * .075 * front;
    const commandBrow = Math.exp(-Math.pow((axial - .64) / .075, 2)) * depth * .055 * front;
    const mandible = Math.exp(-Math.pow((axial - .22) / .13, 2)) * depth * .045 * front;
    const sweptCrown = Math.exp(-Math.pow((axial - .78) / .18, 2)) * depth * .035 * rear;
    return { width: widthFactor, depth: depthFactor, z: faceKeel + commandBrow + mandible + sweptCrown };
  };
  return { width, depth, length: params.length, skull, profile };
}

function helmetSurfacePoint(definition, axial, angle, offset = 0) {
  const point = surfaceSample(definition.skull, axial, angle, false, definition.profile);
  if (offset) {
    const axialDelta = .002; const angleDelta = .002;
    const axialBefore = surfaceSample(definition.skull, Math.max(0, axial - axialDelta), angle, false, definition.profile);
    const axialAfter = surfaceSample(definition.skull, Math.min(1, axial + axialDelta), angle, false, definition.profile);
    const angleBefore = surfaceSample(definition.skull, axial, angle - angleDelta, false, definition.profile);
    const angleAfter = surfaceSample(definition.skull, axial, angle + angleDelta, false, definition.profile);
    const axialTangent = axialAfter.sub(axialBefore); const angleTangent = angleAfter.sub(angleBefore);
    const outward = axialTangent.cross(angleTangent).normalize();
    if (outward.lengthSq() > 0) point.addScaledVector(outward, offset);
  }
  return point;
}

function helmetFrontPoint(definition, axial, lateral, offset = 0) {
  const angle = Math.acos(Math.max(-.96, Math.min(.96, lateral)));
  return helmetSurfacePoint(definition, axial, angle, offset);
}

function buildPanelGeometry(points) {
  const vertices = [];
  points.forEach((point) => vertices.push(point.x, point.y, point.z));
  const indices = [];
  for (let index = 1; index < points.length - 1; index += 1) indices.push(0, index, index + 1);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)); geometry.setIndex(indices);
  geometry.computeVertexNormals(); geometry.computeBoundingBox(); geometry.computeBoundingSphere(); return geometry;
}

function buildCurvedHelmetVisor(definition, side) {
  const segments = 22; const vertices = []; const indices = [];
  for (let step = 0; step <= segments; step += 1) {
    const lateral = side * (.08 + step / segments * .92); const outward = Math.abs(lateral);
    const angle = Math.PI / 2 - lateral * 1.03;
    const topAxial = .625 + outward * .05; const bottomAxial = .55 + outward * .065;
    const outerTop = helmetSurfacePoint(definition, topAxial, angle, 5.2);
    const outerBottom = helmetSurfacePoint(definition, bottomAxial, angle, 5.2);
    const innerTop = helmetSurfacePoint(definition, topAxial, angle, 2.4);
    const innerBottom = helmetSurfacePoint(definition, bottomAxial, angle, 2.4);
    vertices.push(
      outerTop.x, outerTop.y, outerTop.z, outerBottom.x, outerBottom.y, outerBottom.z,
      innerTop.x, innerTop.y, innerTop.z, innerBottom.x, innerBottom.y, innerBottom.z,
    );
    if (step < segments) {
      const outerTopNow = step * 4; const outerBottomNow = outerTopNow + 1; const innerTopNow = outerTopNow + 2; const innerBottomNow = outerTopNow + 3;
      const outerTopNext = outerTopNow + 4; const outerBottomNext = outerTopNow + 5; const innerTopNext = outerTopNow + 6; const innerBottomNext = outerTopNow + 7;
      indices.push(
        outerTopNow, outerBottomNow, outerTopNext, outerTopNext, outerBottomNow, outerBottomNext,
        innerTopNow, innerTopNext, innerBottomNow, innerTopNext, innerBottomNext, innerBottomNow,
        outerTopNow, outerTopNext, innerTopNow, outerTopNext, innerTopNext, innerTopNow,
        outerBottomNow, innerBottomNow, outerBottomNext, outerBottomNext, innerBottomNow, innerBottomNext,
      );
    }
  }
  for (const step of [0, segments]) {
    const outerTop = step * 4; const outerBottom = outerTop + 1; const innerTop = outerTop + 2; const innerBottom = outerTop + 3;
    if (step === 0) indices.push(outerTop, innerTop, outerBottom, outerBottom, innerTop, innerBottom);
    else indices.push(outerTop, outerBottom, innerTop, outerBottom, innerBottom, innerTop);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)); geometry.setIndex(indices);
  geometry.computeVertexNormals(); geometry.computeBoundingBox(); geometry.computeBoundingSphere(); return geometry;
}

function buildHelmetKeel(definition, records) {
  const vertices = []; const indices = [];
  records.forEach(([axial, halfWidth]) => {
    const left = helmetFrontPoint(definition, axial, -halfWidth, 8);
    const right = helmetFrontPoint(definition, axial, halfWidth, 8);
    vertices.push(left.x, left.y, left.z, right.x, right.y, right.z);
  });
  for (let row = 0; row < records.length - 1; row += 1) {
    const left = row * 2; const right = left + 1; const nextLeft = left + 2; const nextRight = left + 3;
    indices.push(left, right, nextLeft, right, nextRight, nextLeft);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)); geometry.setIndex(indices);
  geometry.computeVertexNormals(); geometry.computeBoundingBox(); geometry.computeBoundingSphere(); return geometry;
}

function buildHelmetPatch(definition, records, offset = 3.2) {
  return buildPanelGeometry(records.map(([axial, angle]) => helmetSurfacePoint(definition, axial, angle, offset)));
}

function helmetDetailMaterial(color, options = {}) {
  const material = createRobotMaterial(color, options);
  material.userData.baseOpacity = options.opacity ?? 1;
  material.userData.helmetDetail = true;
  return material;
}

function createHelmetLine(points, color = 0x65737a, opacity = .52) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false }));
  line.userData.helmetDetail = true; line.material.userData.baseOpacity = opacity; return line;
}

function createHelmetDetails(params) {
  const definition = helmetDefinition(params); const group = new THREE.Group();
  group.name = 'CX-H01-SENTINEL'; group.userData.region = 'head'; group.userData.helmetDesign = 'CX-H01-SENTINEL';

  const visorMaterial = helmetDetailMaterial(0x02080d, { emissive: 0x06191c, metalness: .48, roughness: .08, clearcoat: 1, clearcoatRoughness: .06 });
  for (const side of [-1, 1]) {
    const visor = new THREE.Mesh(buildCurvedHelmetVisor(definition, side), side < 0 ? visorMaterial : visorMaterial.clone());
    visor.name = side < 0 ? 'FLIGHT-VISOR-L' : 'FLIGHT-VISOR-R'; visor.userData.helmetDetail = true; group.add(visor);
  }

  const pearl = helmetDetailMaterial(0xdfe6e4, { emissive: 0x020708, metalness: .26, roughness: .25, clearcoat: .94, clearcoatRoughness: .13 });
  const keelRecords = [[.58, .025], [.5, .05], [.38, .11], [.18, .012]];
  const keel = new THREE.Mesh(buildHelmetKeel(definition, keelRecords), pearl);
  keel.name = 'CONDOR-CENTRAL-KEEL'; keel.userData.helmetDetail = true; group.add(keel);
  for (const side of [-1, 1]) {
    group.add(createHelmetLine(keelRecords.map(([axial, halfWidth]) => helmetFrontPoint(definition, axial, side * halfWidth, 8.6)), 0x65737a, .38));
  }

  for (const side of [-1, 1]) {
    const mirror = side < 0 ? (angle) => Math.PI - angle : (angle) => angle;
    const temple = new THREE.Mesh(buildHelmetPatch(definition, [
      [.62, mirror(.12)], [.6, mirror(.39)], [.43, mirror(.41)], [.42, mirror(.1)],
    ], 5), helmetDetailMaterial(0x101820, { emissive: 0x020608, metalness: .5, roughness: .27, clearcoat: .68, clearcoatRoughness: .2 }));
    temple.name = side < 0 ? 'TEMPLE-MODULE-L' : 'TEMPLE-MODULE-R'; temple.userData.helmetDetail = true; group.add(temple);

    const browPoints = [];
    for (let step = 0; step <= 9; step += 1) {
      const lateral = side * (.08 + step / 9 * .78); const angle = Math.PI / 2 - lateral * 1.03;
      browPoints.push(helmetSurfacePoint(definition, .655 + step / 9 * .04, angle, 6));
    }
    group.add(createHelmetLine(browPoints, 0x17242a, .78));

    const crownSeam = [
      helmetFrontPoint(definition, .91, side * .14, 3.2),
      helmetFrontPoint(definition, .79, side * .34, 3.4),
      helmetFrontPoint(definition, .71, side * .48, 3.6),
    ];
    group.add(createHelmetLine(crownSeam, 0x617078, .48));

    for (let vent = 0; vent < 3; vent += 1) {
      const axial = .31 - vent * .04; const start = helmetFrontPoint(definition, axial + .018, side * (.47 + vent * .025), 4.5);
      const end = helmetFrontPoint(definition, axial - .012, side * (.64 + vent * .018), 4.5);
      group.add(createHelmetLine([start, end], 0x111a20, .82));
    }
  }

  group.traverse((item) => { if (item.isMesh || item.isLine) item.userData.helmetDetail = true; });
  return group;
}

function buildHeadGeometry(params) {
  const definition = helmetDefinition(params); const { skull, profile } = definition;
  const pieces = [buildParametricShell(skull, { rings: 42, segments: 72, profile })];
  return mergeGeometryParts(pieces);
}

function fingertipProfile(axial) {
  const distalRound = .18 + .82 * Math.min(1, axial / .18);
  const proximalTaper = 1 - Math.max(0, axial - .78) * .38;
  return { width: distalRound * proximalTaper, depth: distalRound * proximalTaper };
}

function buildHandGeometry(region, params) {
  const left = region.startsWith('left'); const outward = left ? -1 : 1;
  const length = params.length; const width = Math.max(params.proximalWidth, params.distalWidth) + params.clearance * 2;
  const depth = Math.max(params.proximalDepth, params.distalDepth) + params.clearance * 1.2;
  const palmLength = length * .53;
  const palm = { ...params, length: palmLength, proximalWidth: width * .8, distalWidth: width, proximalDepth: depth * .78, distalDepth: depth, bulge: Math.min(params.bulge, width * .06), clearance: 0, asymmetry: 0, shape: Math.max(2.4, params.shape) };
  const pieces = [organicPart(palm, { position: [0, length * .19, 0] }, { rings: 24, segments: 40 })];
  const fingerData = [
    [-.34, .37, .13], [-.115, .46, .145], [.115, .49, .15], [.34, .44, .135],
  ];
  fingerData.forEach(([x, lengthRatio, widthRatio], index) => {
    const fingerLength = length * lengthRatio;
    const finger = { ...params, length: fingerLength, proximalWidth: width * widthRatio, distalWidth: width * widthRatio * .88, proximalDepth: depth * .48, distalDepth: depth * .42, bulge: width * .008, clearance: 0, asymmetry: 0, thickness: Math.min(params.thickness, width * widthRatio * .22), shape: 2.08 };
    const stagger = [0, -.012, 0, .018][index] * length;
    pieces.push(organicPart(finger, { position: [x * width, -length * .075 - fingerLength * .5 + stagger, 0] }, { rings: 20, segments: 28, profile: fingertipProfile }));
  });
  const thumbLength = length * .34;
  const thumb = { ...params, length: thumbLength, proximalWidth: width * .2, distalWidth: width * .16, proximalDepth: depth * .55, distalDepth: depth * .45, bulge: width * .012, clearance: 0, asymmetry: 0, thickness: Math.min(params.thickness, width * .04), shape: 2.08 };
  pieces.push(organicPart(thumb, { position: [outward * width * .48, length * .075, 0], rotation: [0, 0, outward * .72] }, { rings: 20, segments: 28, profile: fingertipProfile }));
  return mergeGeometryParts(pieces);
}

function buildShoulderGeometry(region, params) {
  const left = region.startsWith('left'); const direction = left ? -1 : 1;
  const width = Math.max(params.proximalWidth, params.distalWidth) + params.clearance * 2;
  const depth = Math.max(params.proximalDepth, params.distalDepth) + params.clearance * 2;
  const shoulder = { ...params, proximalWidth: width, distalWidth: width, proximalDepth: depth, distalDepth: depth, bulge: 0, clearance: 0, asymmetry: 0, shape: Math.max(2.15, params.shape) };
  const shoulderProfile = (axial, angle) => {
    const deltoid = Math.sin(Math.PI * axial);
    const distal = .47 + axial * .18;
    const widthFactor = distal + deltoid * .45;
    const depthFactor = .62 + deltoid * .35;
    const innerLift = -direction * width * .04 * Math.pow(axial, 1.4);
    const frontCrown = Math.pow(Math.max(0, Math.sin(angle)), 4) * depth * .045 * deltoid;
    return { width: widthFactor, depth: depthFactor, x: innerLift, z: frontCrown };
  };
  const shell = buildParametricShell(shoulder, { rings: 30, segments: 48, profile: shoulderProfile });
  const crown = buildShellEndCap(shoulder, 1, shoulderProfile, { segments: 48, radialRings: 6, domeHeight: width * .075 });
  return mergeGeometryParts([shell, crown]);
}

function buildFootGeometry(region, params) {
  const left = region.startsWith('left'); const inner = left ? 1 : -1;
  const length = params.length; const clearance = params.clearance;
  const heelWidth = params.proximalWidth + clearance * 2; const forefootWidth = params.distalWidth + clearance * 2;
  const heelDepth = params.proximalDepth + clearance * 1.2; const toeDepth = params.distalDepth + clearance * 1.2;
  const rings = 44; const segments = 64; const vertices = []; const indices = [];

  const section = (axial, angle, inset = 0) => {
    const stride = axial * axial * (3 - 2 * axial); const middle = Math.sin(Math.PI * axial);
    const toeStart = .86; const toeProgress = Math.max(0, (axial - toeStart) / (1 - toeStart));
    const toeRound = Math.cos(Math.min(1, toeProgress) * Math.PI * .5);
    const baseWidth = THREE.MathUtils.lerp(heelWidth, forefootWidth, stride);
    const widthProfile = (.82 + middle * .2) * (toeProgress > 0 ? .12 + toeRound * .88 : 1);
    const halfWidth = Math.max(3, baseWidth * widthProfile * .5 - inset);
    const baseDepth = THREE.MathUtils.lerp(heelDepth, toeDepth, stride);
    const heelCounter = Math.exp(-Math.pow((axial - .06) / .16, 2)) * .36;
    const instepCrown = Math.exp(-Math.pow((axial - .34) / .24, 2)) * .62;
    const upperSlope = (1 - axial) * .08;
    const topHeight = Math.max(3, baseDepth * (.18 + heelCounter + instepCrown + upperSlope) * (toeProgress > 0 ? .42 + toeRound * .58 : 1) - inset);
    const toeRise = Math.pow(Math.max(0, (axial - .72) / .28), 1.65);
    const outsoleDepth = Math.max(2.5, baseDepth * (.13 - toeRise * .065) - inset * .35);
    const sine = Math.sin(angle); const cosine = Math.cos(angle);
    const z = sine < 0 ? sine * topHeight : outsoleDepth * Math.min(1, sine * 4.5);
    const lateralShape = inner * baseWidth * .022 * middle * Math.pow(Math.max(0, axial - .35) / .65, 1.2);
    return new THREE.Vector3(cosine * halfWidth + lateralShape, (axial - .5) * length, z);
  };

  for (const inset of [0, Math.min(params.thickness, Math.min(heelWidth, heelDepth) * .18)]) {
    for (let ring = 0; ring <= rings; ring += 1) {
      for (let segment = 0; segment < segments; segment += 1) {
        const point = section(ring / rings, segment / segments * Math.PI * 2, inset);
        vertices.push(point.x, point.y, point.z);
      }
    }
  }
  const innerOffset = (rings + 1) * segments;
  for (let ring = 0; ring < rings; ring += 1) {
    for (let segment = 0; segment < segments; segment += 1) {
      const next = (segment + 1) % segments;
      const a = ring * segments + segment; const b = ring * segments + next;
      const c = (ring + 1) * segments + segment; const d = (ring + 1) * segments + next;
      indices.push(a, c, b, b, c, d);
      const ia = innerOffset + a; const ib = innerOffset + b; const ic = innerOffset + c; const id = innerOffset + d;
      indices.push(ia, ib, ic, ib, id, ic);
    }
  }
  for (const ring of [0, rings]) {
    const outer = ring * segments; const inside = innerOffset + outer;
    for (let segment = 0; segment < segments; segment += 1) {
      const next = (segment + 1) % segments;
      if (ring === 0) indices.push(outer + segment, outer + next, inside + segment, outer + next, inside + next, inside + segment);
      else indices.push(outer + segment, inside + segment, outer + next, outer + next, inside + segment, inside + next);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)); geometry.setIndex(indices);
  geometry.computeVertexNormals(); geometry.computeBoundingBox(); geometry.computeBoundingSphere(); return geometry;
}

function buildTorsoGeometry(region, params) {
  const profile = region === 'chest'
    ? (axial) => ({ width: .82 + axial * .12 + Math.sin(Math.PI * axial) * .08, depth: .88 + Math.sin(Math.PI * axial) * .12 })
    : region === 'abdomen'
      ? (axial) => ({ width: .88 + Math.abs(axial - .5) * .24, depth: .9 + Math.abs(axial - .5) * .16 })
      : (axial) => ({ width: .8 + Math.sin(Math.PI * axial) * .2, depth: .9 + Math.sin(Math.PI * axial) * .1 });
  return buildParametricShell(params, { rings: 38, segments: 64, profile });
}

function buildRegionGeometry(region, params) {
  if (region === 'head') return buildHeadGeometry(params);
  if (region === 'left-hand' || region === 'right-hand') return buildHandGeometry(region, params);
  if (region === 'left-shoulder' || region === 'right-shoulder') return buildShoulderGeometry(region, params);
  if (region === 'left-foot' || region === 'right-foot') return buildFootGeometry(region, params);
  if (region === 'chest' || region === 'abdomen' || region === 'pelvis') return buildTorsoGeometry(region, params);
  return buildParametricShell(params);
}

function disposeObject3D(root) {
  root?.traverse((object) => {
    if (object.geometry) object.geometry.dispose();
    if (object.material) (Array.isArray(object.material) ? object.material : [object.material]).forEach((material) => material.dispose());
  });
}

function createFrontGuides(region, params, opacity = .5, color = 0x7efff3) {
  const group = new THREE.Group();
  const material = new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false });
  if (region.endsWith('-foot')) {
    const length = params.length; const clearance = params.clearance;
    const heelWidth = params.proximalWidth + clearance * 2; const forefootWidth = params.distalWidth + clearance * 2;
    const heelDepth = params.proximalDepth + clearance * 1.2; const toeDepth = params.distalDepth + clearance * 1.2;
    for (const side of [-1, 1]) {
      const sole = []; const upper = [];
      for (let step = 1; step <= 30; step += 1) {
        const axial = step / 32; const stride = axial * axial * (3 - 2 * axial); const middle = Math.sin(Math.PI * axial);
        const toeProgress = Math.max(0, (axial - .86) / .14); const toeRound = Math.cos(Math.min(1, toeProgress) * Math.PI * .5);
        const baseWidth = THREE.MathUtils.lerp(heelWidth, forefootWidth, stride);
        const halfWidth = baseWidth * (.82 + middle * .2) * (toeProgress > 0 ? .12 + toeRound * .88 : 1) * .505;
        const baseDepth = THREE.MathUtils.lerp(heelDepth, toeDepth, stride);
        const heelCounter = Math.exp(-Math.pow((axial - .06) / .16, 2)) * .36;
        const instepCrown = Math.exp(-Math.pow((axial - .34) / .24, 2)) * .62;
        const topHeight = baseDepth * (.18 + heelCounter + instepCrown + (1 - axial) * .08) * (toeProgress > 0 ? .42 + toeRound * .58 : 1);
        const toeRise = Math.pow(Math.max(0, (axial - .72) / .28), 1.65);
        const outsoleDepth = baseDepth * (.13 - toeRise * .065);
        sole.push(new THREE.Vector3(side * halfWidth, (axial - .5) * length, outsoleDepth * .72));
        if (axial > .12 && axial < .8) upper.push(new THREE.Vector3(side * halfWidth, (axial - .5) * length, -topHeight * .48));
      }
      group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(sole), material.clone()));
      group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(upper), material.clone()));
    }
    return group;
  }
  if (region === 'head' || region.endsWith('-hand')) return group;
  const centerPoints = [];
  for (let step = 0; step <= 18; step += 1) {
    const point = surfaceSample(params, .13 + step / 18 * .74, Math.PI / 2); point.z += 2.2; centerPoints.push(point);
  }
  const centerGeometry = new THREE.BufferGeometry().setFromPoints(centerPoints); group.add(new THREE.Line(centerGeometry, material));
  const bandPoints = [];
  for (let step = 0; step <= 20; step += 1) {
    const angle = Math.PI / 2 - .7 + step / 20 * 1.4;
    const point = surfaceSample(params, .58, angle); point.z += 2.2; bandPoints.push(point);
  }
  const bandGeometry = new THREE.BufferGeometry().setFromPoints(bandPoints);
  group.add(new THREE.Line(bandGeometry, material.clone()));
  return group;
}

function createChestEmblem(params) {
  const width = Math.max(params.proximalWidth, params.distalWidth) + params.clearance * 2;
  const depth = Math.max(params.proximalDepth, params.distalDepth) + params.clearance * 2;
  const radius = Math.min(width, params.length) * .105; const inner = radius * .57;
  const start = Math.PI * .24; const end = Math.PI * 1.76;
  const shape = new THREE.Shape(); shape.moveTo(Math.cos(start) * radius, Math.sin(start) * radius);
  shape.absarc(0, 0, radius, start, end, false);
  shape.lineTo(Math.cos(end) * inner, Math.sin(end) * inner);
  shape.absarc(0, 0, inner, end, start, true); shape.closePath();
  const front = depth * .5 + Math.max(0, params.bulge) * .5 + 7;
  const backingShape = new THREE.Shape(); backingShape.absarc(0, 0, radius * 1.18, 0, Math.PI * 2, false);
  const backingGeometry = new THREE.ExtrudeGeometry(backingShape, { depth: 4, bevelEnabled: true, bevelSegments: 2, steps: 1, bevelSize: 1.3, bevelThickness: 1.2, curveSegments: 36 });
  backingGeometry.translate(0, params.length * .08, front);
  const backing = new THREE.Mesh(backingGeometry, new THREE.MeshPhysicalMaterial({ color: 0x030910, emissive: 0x041b20, metalness: .62, roughness: .3, clearcoat: .75 }));
  const geometry = new THREE.ExtrudeGeometry(shape, { depth: 7, bevelEnabled: true, bevelSegments: 3, steps: 1, bevelSize: 1.8, bevelThickness: 1.6, curveSegments: 36 });
  geometry.translate(0, params.length * .08, front + 4.2);
  const emblem = new THREE.Mesh(geometry, new THREE.MeshPhysicalMaterial({ color: 0xf4ba64, emissive: 0x4b2508, metalness: .78, roughness: .24, clearcoat: .85, clearcoatRoughness: .18 }));
  const group = new THREE.Group(); group.add(backing, emblem); return group;
}

const DARK_JOINT_REGIONS = new Set(['neck', 'left-elbow', 'right-elbow', 'left-knee', 'right-knee', 'left-hand', 'right-hand']);

function createRobotMaterial(color, options = {}) {
  return new THREE.MeshPhysicalMaterial({
    color, emissive: options.emissive || 0x000000, metalness: options.metalness ?? .68,
    roughness: options.roughness ?? .2, clearcoat: options.clearcoat ?? .9,
    clearcoatRoughness: options.clearcoatRoughness ?? .16, transparent: Boolean(options.transparent),
    opacity: options.opacity ?? 1, side: THREE.DoubleSide,
  });
}

function createBodyMaterial(region, saved) {
  const joint = DARK_JOINT_REGIONS.has(region);
  const helmet = region === 'head';
  const color = joint ? 0x10171c : (saved ? 0xf7fbfa : 0xdde4e5);
  const material = createRobotMaterial(color, helmet
    ? { emissive: saved ? 0x061516 : 0x030708, metalness: .3, roughness: .24, clearcoat: .96, clearcoatRoughness: .12 }
    : joint
    ? { emissive: 0x020709, metalness: .5, roughness: .3, clearcoat: .48 }
    : { emissive: saved ? 0x061516 : 0x030708, metalness: .74, roughness: .17, clearcoat: 1 });
  material.userData.baseColor = color; material.userData.baseEmissive = joint ? 0x020709 : (saved ? 0x061516 : 0x030708);
  return material;
}

function createArmorClosureDetails(parameters, layout, savedRegions = new Map()) {
  const group = new THREE.Group();
  group.name = 'CX-BODY-CLOSED-CASING'; group.userData.bodyArmorDetail = true;

  const addClosure = (name, region, params, transform, profile = null, closureOptions = {}) => {
    const saved = savedRegions.has(region);
    const material = createRobotMaterial(saved ? 0xf7fbfa : 0xe7eeee, {
      emissive: saved ? 0x061516 : 0x030708, metalness: .68, roughness: .2,
      clearcoat: .98, clearcoatRoughness: .13,
    });
    material.userData.baseColor = saved ? 0xf7fbfa : 0xe7eeee;
    material.userData.baseEmissive = saved ? 0x061516 : 0x030708;
    const parts = [organicPart(params, transform, { rings: 28, segments: 48, profile })];
    if (Number.isFinite(closureOptions.capAxial)) {
      const cap = buildShellEndCap(params, closureOptions.capAxial, profile, {
        segments: 48, radialRings: 6, domeHeight: closureOptions.domeHeight,
      });
      parts.push(transformGeometry(cap, transform));
    }
    const mesh = new THREE.Mesh(parts.length > 1 ? mergeGeometryParts(parts) : parts[0], material);
    mesh.name = name; mesh.userData.region = region; mesh.userData.saved = saved;
    mesh.userData.armorClosure = true; mesh.userData.bodyArmorDetail = true; group.add(mesh);
  };

  const neck = parameters.neck;
  const neckWidth = Math.max(neck.proximalWidth, neck.distalWidth) + neck.clearance * 2;
  const neckDepth = Math.max(neck.proximalDepth, neck.distalDepth) + neck.clearance * 2;
  const collar = {
    ...neck, length: Math.max(82, neck.length * .78),
    proximalWidth: neckWidth + 22, distalWidth: neckWidth + 10,
    proximalDepth: neckDepth + 18, distalDepth: neckDepth + 8,
    bulge: 0, clearance: 0, asymmetry: 0, thickness: Math.max(5, neck.thickness), shape: 2.45,
  };
  addClosure('SEALED-COLLAR-COWL', 'neck', collar, { position: [0, layout.positions.neck[1] - 4, 0] },
    (axial) => ({ width: .94 + Math.sin(Math.PI * axial) * .06, depth: .95 + Math.sin(Math.PI * axial) * .05 }),
    { capAxial: 1, domeHeight: 10 });

  for (const side of ['left', 'right']) {
    const direction = side === 'left' ? -1 : 1;
    const shoulderRegion = `${side}-shoulder`; const upperRegion = `${side}-upper-arm`;
    const shoulder = parameters[shoulderRegion]; const upper = parameters[upperRegion];
    const bridgeWidth = Math.max(shoulder.proximalWidth, shoulder.distalWidth) * .66 + shoulder.clearance * 2;
    const bridgeDepth = Math.max(shoulder.proximalDepth, shoulder.distalDepth) * .72 + shoulder.clearance * 2;
    const bridge = {
      ...shoulder, length: Math.max(136, shoulder.length * .88),
      proximalWidth: bridgeWidth, distalWidth: Math.max(upper.proximalWidth, upper.distalWidth) + upper.clearance * 1.6,
      proximalDepth: bridgeDepth, distalDepth: Math.max(upper.proximalDepth, upper.distalDepth) + upper.clearance * 1.4,
      bulge: 7, clearance: 0, asymmetry: 0, thickness: Math.max(5, shoulder.thickness), shape: 2.32,
    };
    const shoulderPosition = layout.positions[shoulderRegion]; const upperPosition = layout.positions[upperRegion];
    const bridgePosition = [
      shoulderPosition[0] - direction * bridgeWidth * .19,
      THREE.MathUtils.lerp(upperPosition[1], shoulderPosition[1], .68),
      3,
    ];
    const closureName = side === 'left' ? 'LEFT-SHOULDER-ROOT-GUSSET' : 'RIGHT-SHOULDER-ROOT-GUSSET';
    addClosure(closureName, shoulderRegion, bridge,
      { position: bridgePosition, rotation: [0, 0, -direction * .16] },
      (axial) => ({ width: .86 + Math.sin(Math.PI * axial) * .14, depth: .9 + Math.sin(Math.PI * axial) * .1 }));
  }

  return group;
}

function stlText(geometry, name) {
  const source = geometry.index ? geometry.toNonIndexed() : geometry.clone();
  const positions = source.getAttribute('position'); const a = new THREE.Vector3(); const b = new THREE.Vector3();
  const c = new THREE.Vector3(); const normal = new THREE.Vector3(); const ab = new THREE.Vector3(); const ac = new THREE.Vector3();
  const lines = [`solid ${name}`];
  for (let i = 0; i < positions.count; i += 3) {
    a.fromBufferAttribute(positions, i); b.fromBufferAttribute(positions, i + 1); c.fromBufferAttribute(positions, i + 2);
    normal.crossVectors(ab.subVectors(b, a), ac.subVectors(c, a)).normalize();
    lines.push(` facet normal ${normal.x} ${normal.y} ${normal.z}`, '  outer loop',
      `   vertex ${a.x} ${a.y} ${a.z}`, `   vertex ${b.x} ${b.y} ${b.z}`, `   vertex ${c.x} ${c.y} ${c.z}`,
      '  endloop', ' endfacet');
  }
  lines.push(`endsolid ${name}`); source.dispose(); return lines.join('\n');
}

export class CondorModeler3D {
  constructor(host, controlsHost, pointsHost) {
    this.host = host; this.controlsHost = controlsHost; this.pointsHost = pointsHost;
    this.region = 'chest'; this.parameters = defaultsFor('chest'); this.points = [];
    this.layers = { reference: true, wireframe: false, technicalPoints: true };
    this.yaw = -.58; this.pitch = .22; this.distance = 820; this.target = new THREE.Vector3();
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(35, 1, 1, 5000);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.8));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.setClearColor(0x020812, 0);
    this.host.replaceChildren(this.renderer.domElement);
    this.group = new THREE.Group(); this.scene.add(this.group);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x11151c, 2.15));
    const key = new THREE.DirectionalLight(0xffffff, 3.8); key.position.set(380, 520, 480); this.scene.add(key);
    const fill = new THREE.DirectionalLight(0xbce9eb, 1.25); fill.position.set(-280, 180, 420); this.scene.add(fill);
    const rim = new THREE.DirectionalLight(0x8b7cff, 1.9); rim.position.set(-420, 120, -350); this.scene.add(rim);
    const grid = new THREE.GridHelper(1200, 24, 0x22535b, 0x10252e); grid.position.y = -360; grid.material.transparent = true; grid.material.opacity = .28; this.scene.add(grid);
    this.shellMaterial = new THREE.MeshPhysicalMaterial({ color: 0xf1f7f6, emissive: 0x030809, metalness: .72, roughness: .18, clearcoat: .95, clearcoatRoughness: .15, side: THREE.DoubleSide });
    this.referenceMaterial = new THREE.MeshBasicMaterial({ color: 0x74fff1, wireframe: true, transparent: true, opacity: .12, depthWrite: false });
    this.pointMaterial = new THREE.PointsMaterial({ color: 0xffc975, size: 12, sizeAttenuation: false, transparent: true, opacity: .95 });
    this.installPointerControls(); this.renderParameterControls();
    this.resizeObserver = new ResizeObserver(() => this.resize()); this.resizeObserver.observe(this.host);
    this.open('chest');
  }

  installPointerControls() {
    const canvas = this.renderer.domElement; let dragging = false; let lastX = 0; let lastY = 0;
    canvas.addEventListener('pointerdown', (event) => { dragging = true; lastX = event.clientX; lastY = event.clientY; canvas.setPointerCapture(event.pointerId); });
    canvas.addEventListener('pointermove', (event) => {
      if (!dragging) return; this.yaw -= (event.clientX - lastX) * .008; this.pitch = Math.max(-1.15, Math.min(1.15, this.pitch - (event.clientY - lastY) * .006));
      lastX = event.clientX; lastY = event.clientY; this.render();
    });
    canvas.addEventListener('pointerup', () => { dragging = false; });
    canvas.addEventListener('wheel', (event) => { event.preventDefault(); this.distance = Math.max(180, Math.min(2200, this.distance * Math.exp(event.deltaY * .001))); this.render(); }, { passive: false });
  }

  renderParameterControls() {
    this.controlsHost.innerHTML = PARAMETER_DEFS.map(([key, label, min, max, unit]) => `
      <label class="cx-param"><span>${label}<output data-value="${key}"></output></span>
        <input type="range" data-param="${key}" min="${min}" max="${max}" step="${key === 'shape' ? '.01' : '.1'}">
        <input class="cx-param-number" type="number" data-param-number="${key}" min="${min}" max="${max}" step="${key === 'shape' ? '.01' : '.1'}" aria-label="${label} exato"><small>${unit}</small>
      </label>`).join('');
    this.controlsHost.addEventListener('input', (event) => {
      const input = event.target.closest('[data-param],[data-param-number]'); if (!input) return;
      const key = input.dataset.param || input.dataset.paramNumber;
      this.parameters[key] = Number(input.value); this.syncParameterOutputs(); this.rebuild();
    });
  }

  syncParameterOutputs() {
    PARAMETER_DEFS.forEach(([key, , , , unit]) => {
      const input = this.controlsHost.querySelector(`[data-param="${key}"]`); const output = this.controlsHost.querySelector(`[data-value="${key}"]`);
      const numberInput = this.controlsHost.querySelector(`[data-param-number="${key}"]`);
      if (input) input.value = this.parameters[key]; if (numberInput) numberInput.value = this.parameters[key];
      if (output) output.textContent = `${Number(this.parameters[key]).toFixed(key === 'shape' ? 2 : 1)}${unit}`;
    });
  }

  open(region, snapshot = null) {
    this.region = region; const geometry = snapshot?.geometry?.schema === 'condor-parametric-surface-v1' ? snapshot.geometry : null;
    this.parameters = normalizedParameters(region, geometry?.parameters || {});
    this.points = Array.isArray(geometry?.technicalPoints) ? geometry.technicalPoints.slice(0, 128).map((point, index) => ({
      id: String(point.id || `point-${index}`), type: String(point.type || 'sensor').slice(0, 40), label: String(point.label || '').slice(0, 100),
      axial: finiteNumber(point.axial, .5, 0, 1), angle: finiteNumber(point.angle, 0, -180, 180),
    })) : [];
    this.layers = { reference: geometry?.layers?.reference !== false, wireframe: Boolean(geometry?.layers?.wireframe), technicalPoints: geometry?.layers?.technicalPoints !== false };
    this.group.rotation.set(region === 'left-foot' || region === 'right-foot' ? Math.PI / 2 : 0, 0, 0);
    this.syncParameterOutputs(); this.rebuild(); this.resetView(); this.renderPointsList();
  }

  rebuild() {
    this.parameters = normalizedParameters(this.region, this.parameters);
    if (this.shell) { this.group.remove(this.shell); this.shell.geometry.dispose(); }
    if (this.reference) { this.group.remove(this.reference); this.reference.geometry.dispose(); }
    if (this.pointCloud) { this.group.remove(this.pointCloud); this.pointCloud.geometry.dispose(); }
    if (this.frontGuides) { this.group.remove(this.frontGuides); disposeObject3D(this.frontGuides); }
    if (this.chestEmblem) { this.group.remove(this.chestEmblem); disposeObject3D(this.chestEmblem); }
    if (this.helmetDetails) { this.group.remove(this.helmetDetails); disposeObject3D(this.helmetDetails); }
    const geometry = buildRegionGeometry(this.region, this.parameters);
    const joint = DARK_JOINT_REGIONS.has(this.region); this.shellMaterial.color.setHex(joint ? 0x10171c : 0xf1f7f6); this.shellMaterial.emissive.setHex(joint ? 0x020709 : 0x030809);
    const helmet = this.region === 'head';
    this.shellMaterial.metalness = helmet ? .3 : (joint ? .5 : .72); this.shellMaterial.roughness = helmet ? .24 : (joint ? .3 : .18);
    this.shellMaterial.clearcoat = helmet ? .96 : (joint ? .48 : .95); this.shellMaterial.clearcoatRoughness = helmet ? .12 : (joint ? .24 : .15);
    this.shellMaterial.wireframe = this.layers.wireframe; this.shell = new THREE.Mesh(geometry, this.shellMaterial); this.group.add(this.shell);
    this.reference = new THREE.Mesh(geometry.clone(), this.referenceMaterial); this.reference.scale.set(.92, .985, .92); this.reference.visible = this.layers.reference; this.group.add(this.reference);
    this.frontGuides = createFrontGuides(this.region, this.parameters, .62); this.group.add(this.frontGuides);
    this.chestEmblem = this.region === 'chest' ? createChestEmblem(this.parameters) : null; if (this.chestEmblem) this.group.add(this.chestEmblem);
    this.helmetDetails = this.region === 'head' ? createHelmetDetails(this.parameters) : null; if (this.helmetDetails) this.group.add(this.helmetDetails);
    const pointGeometry = new THREE.BufferGeometry(); const positions = [];
    this.points.forEach((point) => { const position = surfaceSample(this.parameters, point.axial, THREE.MathUtils.degToRad(point.angle)); positions.push(position.x, position.y, position.z); });
    pointGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    this.pointCloud = new THREE.Points(pointGeometry, this.pointMaterial); this.pointCloud.visible = this.layers.technicalPoints; this.group.add(this.pointCloud);
    this.render();
  }

  renderPointsList() {
    this.pointsHost.replaceChildren();
    if (!this.points.length) { const empty = document.createElement('p'); empty.className = 'cx-point-empty'; empty.textContent = 'Nenhum ponto técnico adicionado.'; this.pointsHost.appendChild(empty); return; }
    this.points.forEach((point) => {
      const row = document.createElement('div'); row.className = 'cx-point-row';
      const text = document.createElement('span'); text.innerHTML = `<strong>${point.type.toUpperCase()}</strong><small></small>`; text.querySelector('small').textContent = point.label || 'Sem nome';
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '×'; remove.title = 'Remover ponto'; remove.addEventListener('click', () => { this.points = this.points.filter((item) => item.id !== point.id); this.rebuild(); this.renderPointsList(); });
      row.append(text, remove); this.pointsHost.appendChild(row);
    });
  }

  addTechnicalPoint(data) {
    if (this.points.length >= 128) throw new Error('Limite de 128 pontos técnicos por modelo.');
    this.points.push({ id: crypto.randomUUID(), type: String(data.type || 'sensor').slice(0, 40), label: String(data.label || '').slice(0, 100), axial: finiteNumber(data.axial, .5, 0, 1), angle: finiteNumber(data.angle, 0, -180, 180) });
    this.rebuild(); this.renderPointsList();
  }

  toggleWireframe() { this.layers.wireframe = !this.layers.wireframe; this.shellMaterial.wireframe = this.layers.wireframe; this.render(); return this.layers.wireframe; }
  toggleReference() { this.layers.reference = !this.layers.reference; if (this.reference) this.reference.visible = this.layers.reference; this.render(); return this.layers.reference; }
  togglePoints() { this.layers.technicalPoints = !this.layers.technicalPoints; if (this.pointCloud) this.pointCloud.visible = this.layers.technicalPoints; this.render(); return this.layers.technicalPoints; }

  resetView() {
    const foot = this.region === 'left-foot' || this.region === 'right-foot';
    this.yaw = foot ? -Math.PI / 2 : -.58; this.pitch = foot ? .08 : .22;
    this.target.set(0, 0, 0); this.distance = Math.max(300, this.parameters.length * 2.2);
    if (foot && this.shell) {
      this.group.updateMatrixWorld(true);
      const bounds = new THREE.Box3().setFromObject(this.shell); const center = bounds.getCenter(new THREE.Vector3()); const size = bounds.getSize(new THREE.Vector3());
      const vertical = THREE.MathUtils.degToRad(this.camera.fov); const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * Math.max(.2, this.camera.aspect));
      this.target.copy(center); this.target.y -= size.y * .72;
      const fitHeight = size.y / (2 * Math.tan(vertical / 2));
      const fitLength = Math.max(size.x, size.z) / (2 * Math.tan(horizontal / 2));
      this.distance = Math.max(fitHeight, fitLength) * 1.35 + Math.min(size.x, size.z) * .35;
    }
    this.render();
  }
  resize() { const width = Math.max(1, this.host.clientWidth); const height = Math.max(1, this.host.clientHeight); this.renderer.setSize(width, height, false); this.camera.aspect = width / height; this.camera.updateProjectionMatrix(); this.render(); }
  render() { const cp = Math.cos(this.pitch); this.camera.position.set(Math.sin(this.yaw) * cp * this.distance, Math.sin(this.pitch) * this.distance, Math.cos(this.yaw) * cp * this.distance); this.camera.lookAt(this.target); this.renderer.render(this.scene, this.camera); }

  snapshot() {
    return { geometry: { schema: 'condor-parametric-surface-v1', region: this.region, unit: 'mm', parameters: { ...this.parameters }, layers: { ...this.layers }, technicalPoints: this.points.map((point) => ({ ...point })) } };
  }

  exportSTL(name = this.region) {
    if (!this.shell?.geometry) throw new Error('Nenhuma malha disponível para exportação.');
    const safeName = String(name || this.region).normalize('NFKD').replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-|-$/g, '') || 'condor-model';
    const blob = new Blob([stlText(this.shell.geometry, safeName)], { type: 'model/stl' }); const url = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href = url; link.download = `${safeName}.stl`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

const BODY_REGIONS = [
  'head', 'neck', 'chest', 'abdomen', 'pelvis',
  'left-shoulder', 'left-upper-arm', 'left-elbow', 'left-forearm', 'left-hand',
  'right-shoulder', 'right-upper-arm', 'right-elbow', 'right-forearm', 'right-hand',
  'left-thigh', 'left-knee', 'left-shin', 'left-foot',
  'right-thigh', 'right-knee', 'right-shin', 'right-foot',
];

function bodyLayout(parameters) {
  const length = (id) => parameters[id].length;
  const width = (id) => Math.max(parameters[id].proximalWidth, parameters[id].distalWidth) + parameters[id].clearance * 2;
  const positions = {}; const rotations = {};
  positions.pelvis = [0, 0, 0];
  positions.abdomen = [0, length('pelvis') * .5 + length('abdomen') * .5 - 18, 0];
  positions.chest = [0, positions.abdomen[1] + length('abdomen') * .5 + length('chest') * .5 - 28, 0];
  positions.neck = [0, positions.chest[1] + length('chest') * .5 + length('neck') * .5 - 30, 0];
  positions.head = [0, positions.neck[1] + length('neck') * .5 + length('head') * .5 - 18, 0];
  for (const side of ['left', 'right']) {
    const direction = side === 'left' ? -1 : 1;
    const shoulder = `${side}-shoulder`; const upper = `${side}-upper-arm`; const elbow = `${side}-elbow`;
    const forearm = `${side}-forearm`; const hand = `${side}-hand`;
    const shoulderX = direction * (width('chest') * .5 + width(shoulder) * .18);
    const shoulderY = positions.chest[1] + length('chest') * .28;
    positions[shoulder] = [shoulderX, shoulderY, 0]; rotations[shoulder] = [0, 0, direction * -.12];
    const armX = shoulderX + direction * width(shoulder) * .09;
    positions[upper] = [armX, shoulderY - length(shoulder) * .42 - length(upper) * .48, 0]; rotations[upper] = [0, 0, direction * -.045];
    positions[elbow] = [armX + direction * 8, positions[upper][1] - length(upper) * .5 - length(elbow) * .45, 0];
    positions[forearm] = [armX + direction * 12, positions[elbow][1] - length(elbow) * .48 - length(forearm) * .5, 0]; rotations[forearm] = [0, 0, direction * .025];
    positions[hand] = [armX + direction * 16, positions[forearm][1] - length(forearm) * .5 - length(hand) * .48, 0];
    const thigh = `${side}-thigh`; const knee = `${side}-knee`; const shin = `${side}-shin`; const foot = `${side}-foot`;
    const legX = direction * Math.max(62, width('pelvis') * .23);
    positions[thigh] = [legX, -length('pelvis') * .45 - length(thigh) * .5, 0];
    positions[knee] = [legX, positions[thigh][1] - length(thigh) * .5 - length(knee) * .46, 0];
    positions[shin] = [legX, positions[knee][1] - length(knee) * .48 - length(shin) * .5, 0];
    positions[foot] = [legX, positions[shin][1] - length(shin) * .5 - 42, 72]; rotations[foot] = [Math.PI / 2, 0, 0];
  }
  return { positions, rotations };
}

export class CondorBody3D {
  constructor(host, onPick) {
    this.host = host; this.onPick = onPick; this.parts = []; this.meshes = []; this.selected = [];
    this.engineeringMeshes = []; this.engineeringEnabled = false; this.engineeringDrag = null;
    this.onEngineeringMove = null; this.onEngineeringSelect = null;
    this.scene = new THREE.Scene(); this.camera = new THREE.PerspectiveCamera(32, 1, 1, 9000);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.7)); this.renderer.outputColorSpace = THREE.SRGBColorSpace; this.renderer.setClearColor(0x020812, 0);
    this.host.replaceChildren(this.renderer.domElement); this.body = new THREE.Group(); this.scene.add(this.body);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x11151c, 2.35));
    const key = new THREE.DirectionalLight(0xffffff, 4.1); key.position.set(900, 1500, 1400); this.scene.add(key);
    const fill = new THREE.DirectionalLight(0xbce9eb, 1.7); fill.position.set(-700, 500, 900); this.scene.add(fill);
    const rim = new THREE.DirectionalLight(0x8b7cff, 2.1); rim.position.set(-1200, 300, -900); this.scene.add(rim);
    this.yaw = -.4; this.pitch = .045; this.distance = 4550; this.target = new THREE.Vector3(0, -100, 0);
    this.installControls(); this.resizeObserver = new ResizeObserver(() => this.resize()); this.resizeObserver.observe(this.host); this.resize(); this.rebuild();
  }

  activeGeometry() {
    const active = new Map();
    this.parts.filter((part) => part.integrated && part.type === 'parametric_3d_model' && BODY_REGIONS.includes(part.region)).forEach((part) => {
      if (!active.has(part.region) && part.current_snapshot?.geometry?.schema === 'condor-parametric-surface-v1') active.set(part.region, part.current_snapshot.geometry);
    });
    return active;
  }

  setParts(parts = []) { this.parts = Array.isArray(parts) ? parts : []; this.rebuild(); }
  applyPart(part) {
    this.parts = this.parts.filter((item) => item.id !== part.id && !(item.region === part.region && item.integrated && item.type === 'parametric_3d_model'));
    this.parts.unshift(part); this.rebuild();
  }

  rebuild() {
    disposeObject3D(this.body);
    this.body.clear(); this.meshes = []; const active = this.activeGeometry(); const parameters = {};
    BODY_REGIONS.forEach((region) => { parameters[region] = normalizedParameters(region, active.get(region)?.parameters || {}); });
    const layout = bodyLayout(parameters);
    BODY_REGIONS.forEach((region) => {
      const saved = active.has(region); const group = new THREE.Group(); group.position.fromArray(layout.positions[region]); group.rotation.fromArray(layout.rotations[region] || [0, 0, 0]);
      const material = createBodyMaterial(region, saved);
      const mesh = new THREE.Mesh(buildRegionGeometry(region, parameters[region]), material); mesh.userData.region = region; mesh.userData.saved = saved; group.add(mesh); this.meshes.push(mesh);
      group.add(createFrontGuides(region, parameters[region], saved ? .72 : .5, 0x25343b));
      if (region === 'head') group.add(createHelmetDetails(parameters[region]));
      if (region === 'chest') group.add(createChestEmblem(parameters[region]));
      const points = active.get(region)?.technicalPoints || [];
      if (points.length) {
        const vertices = [];
        points.slice(0, 128).forEach((point) => { const position = surfaceSample(parameters[region], finiteNumber(point.axial, .5, 0, 1), THREE.MathUtils.degToRad(finiteNumber(point.angle, 0, -180, 180))); vertices.push(position.x, position.y, position.z); });
        const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)); group.add(new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0xffc975, size: 7, sizeAttenuation: false })));
      }
      this.body.add(group);
    });
    this.armorClosures = createArmorClosureDetails(parameters, layout, active);
    this.armorClosures.traverse((item) => { if (item.isMesh) this.meshes.push(item); });
    this.body.add(this.armorClosures);
    this.fitView(); this.select(this.selected); this.render();
  }

  fitView() {
    this.body.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(this.body); if (bounds.isEmpty()) return;
    const center = bounds.getCenter(new THREE.Vector3()); const size = bounds.getSize(new THREE.Vector3());
    const vertical = THREE.MathUtils.degToRad(this.camera.fov); const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * Math.max(.2, this.camera.aspect));
    const fitHeight = size.y / (2 * Math.tan(vertical / 2)); const fitWidth = size.x / (2 * Math.tan(horizontal / 2));
    this.target.copy(center); this.distance = Math.max(fitHeight, fitWidth) * 1.16 + size.z * .5;
    this.distance = Math.max(1800, Math.min(7200, this.distance));
  }

  select(regions = []) {
    this.selected = regions;
    this.meshes.forEach((mesh) => {
      const selected = regions.includes(mesh.userData.region);
      if (mesh.material.emissive) mesh.material.emissive.setHex(selected ? 0x142321 : mesh.material.userData.baseEmissive);
      mesh.material.color.setHex(mesh.material.userData.baseColor);
    }); this.render();
  }

  installControls() {
    const canvas = this.renderer.domElement; let dragging = false; let moved = 0; let lastX = 0; let lastY = 0;
    const pick = (event, objects) => { const rect = canvas.getBoundingClientRect(); const pointer = new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1); const raycaster = new THREE.Raycaster(); raycaster.setFromCamera(pointer, this.camera); return raycaster.intersectObjects(objects, true)[0]; };
    canvas.addEventListener('pointerdown', (event) => {
      if (this.engineeringEnabled) {
        const hit = pick(event, this.engineeringMeshes);
        const root = hit?.object;
        const unitId = root?.userData?.unitId || root?.parent?.userData?.unitId;
        if (unitId) {
          const object = this.engineeringMeshes.find((item) => item.userData.unitId === unitId);
          this.engineeringDrag = { unitId, object, startX: event.clientX, startY: event.clientY, origin: object.position.clone(), moved: 0 };
          canvas.setPointerCapture(event.pointerId); this.onEngineeringSelect?.(unitId); return;
        }
      }
      dragging = true; moved = 0; lastX = event.clientX; lastY = event.clientY; canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', (event) => {
      if (this.engineeringDrag) {
        const dx = event.clientX - this.engineeringDrag.startX; const dy = event.clientY - this.engineeringDrag.startY;
        this.engineeringDrag.moved = Math.abs(dx) + Math.abs(dy);
        this.engineeringDrag.object.position.set(this.engineeringDrag.origin.x + dx * 2.2, this.engineeringDrag.origin.y - dy * 2.2, this.engineeringDrag.origin.z);
        this.render(); return;
      }
      if (!dragging) return; const dx = event.clientX - lastX; const dy = event.clientY - lastY; moved += Math.abs(dx) + Math.abs(dy); this.yaw -= dx * .007; this.pitch = Math.max(-.85, Math.min(.85, this.pitch - dy * .005)); lastX = event.clientX; lastY = event.clientY; this.render();
    });
    canvas.addEventListener('pointerup', (event) => {
      if (this.engineeringDrag) {
        const drag = this.engineeringDrag; this.engineeringDrag = null;
        if (drag.moved > 2) this.onEngineeringMove?.(drag.unitId, { x: drag.object.position.x / 1000, y: drag.object.position.y / 1000, z: drag.object.position.z / 1000 });
        return;
      }
      dragging = false; if (moved > 6) return; const rect = canvas.getBoundingClientRect(); const pointer = new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
      const raycaster = new THREE.Raycaster(); raycaster.setFromCamera(pointer, this.camera); const hit = raycaster.intersectObjects(this.meshes, false)[0]; if (hit?.object?.userData?.region) this.onPick?.(hit.object.userData.region);
    });
    canvas.addEventListener('wheel', (event) => { event.preventDefault(); this.distance = Math.max(1800, Math.min(7000, this.distance * Math.exp(event.deltaY * .001))); this.render(); }, { passive: false });
  }

  resize() { const width = Math.max(1, this.host.clientWidth); const height = Math.max(1, this.host.clientHeight); this.renderer.setSize(width, height, false); this.camera.aspect = width / height; this.camera.updateProjectionMatrix(); this.render(); }
  render() { const cp = Math.cos(this.pitch); this.camera.position.set(Math.sin(this.yaw) * cp * this.distance, this.target.y + Math.sin(this.pitch) * this.distance, Math.cos(this.yaw) * cp * this.distance); this.camera.lookAt(this.target); this.renderer.render(this.scene, this.camera); }
}

const PROPULSION_ZONE_COLORS = { FAVORABLE: 0x48df9b, COMPROMISES: 0xf5d76e, HIGH_RISK: 0xff9d45, REJECTED: 0xff566c, NOT_EVALUATED: 0x718096 };

function engineeringMaterial(color, opacity = .24, wireframe = false) {
  return new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthWrite: false, wireframe, side: THREE.DoubleSide });
}

function vectorFromRecord(value) { return new THREE.Vector3(Number(value?.x || 0), Number(value?.y || 0), Number(value?.z || 0)); }

/** Visualizador 3D exclusivo do Propulsion Placement Lab. */
export class CondorPropulsion3D extends CondorBody3D {
  constructor(host, callbacks = {}) {
    super(host, callbacks.onBodyPick);
    this.onEngineeringMove = callbacks.onUnitMove;
    this.onEngineeringSelect = callbacks.onUnitSelect;
    this.propulsionLayer = new THREE.Group(); this.scene.add(this.propulsionLayer);
    this.engineeringEnabled = true; this.engineeringState = null;
    this.engineeringToggles = { zones: true, vectors: true, flow: false, thermal: false, moments: true, loadPaths: false };
  }

  setState(layout, analysis, toggles = {}) {
    this.engineeringState = { layout, analysis };
    this.engineeringToggles = { ...this.engineeringToggles, ...toggles };
    this.rebuildEngineering();
  }

  rebuildEngineering() {
    disposeObject3D(this.propulsionLayer); this.propulsionLayer.clear(); this.engineeringMeshes = [];
    const layout = this.engineeringState?.layout; const analysis = this.engineeringState?.analysis;
    if (!layout) { this.render(); return; }
    const zoneRows = analysis?.candidateZones || [];
    if (this.engineeringToggles.zones) zoneRows.forEach((zone) => {
      const color = PROPULSION_ZONE_COLORS[zone.status] || PROPULSION_ZONE_COLORS.NOT_EVALUATED;
      const geometry = new THREE.BoxGeometry(180, 150, 180);
      const mesh = new THREE.Mesh(geometry, engineeringMaterial(color, .14, true));
      mesh.position.set(zone.position.x * 1000, zone.position.y * 1000, zone.position.z * 1000);
      mesh.userData.zoneId = zone.id; this.propulsionLayer.add(mesh);
    });
    const states = new Map((analysis?.propulsionEngine?.unitStates || []).map((state) => [state.unitId, state]));
    layout.units.forEach((unit) => {
      const state = states.get(unit.id); const failed = unit.status === 'FAILED';
      const color = failed ? 0xff566c : state?.saturated ? 0xff9d45 : 0x71fff0;
      const group = new THREE.Group(); group.userData.unitId = unit.id;
      group.position.set(unit.positionX * 1000, unit.positionY * 1000, unit.positionZ * 1000);
      const width = Math.max(42, Number(unit.installationEnvelope?.width || .09) * 1000);
      const height = Math.max(74, Number(unit.installationEnvelope?.height || .16) * 1000);
      const body = new THREE.Mesh(new THREE.CylinderGeometry(width * .42, width * .52, height, 20), new THREE.MeshPhysicalMaterial({ color, emissive: color, emissiveIntensity: .12, metalness: .72, roughness: .22, transparent: true, opacity: .92 }));
      body.userData.unitId = unit.id; group.add(body);
      const direction = vectorFromRecord(state?.direction || { y: 1 }).normalize();
      group.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction);
      this.propulsionLayer.add(group); this.engineeringMeshes.push(group);
      if (this.engineeringToggles.vectors && state?.thrust > 0) {
        const length = Math.max(90, Math.log1p(state.thrust) * 60); const arrow = new THREE.ArrowHelper(direction, group.position.clone(), length, color, 38, 18); this.propulsionLayer.add(arrow);
      }
      if (this.engineeringToggles.thermal && unit.thermalRadiusEstimate) {
        const sphere = new THREE.Mesh(new THREE.SphereGeometry(unit.thermalRadiusEstimate * 1000, 18, 12), engineeringMaterial(0xff6b4a, .075)); sphere.position.copy(group.position); this.propulsionLayer.add(sphere);
      }
      if (this.engineeringToggles.flow) {
        const cone = new THREE.Mesh(new THREE.ConeGeometry(width * .75, 260, 18, 1, true), engineeringMaterial(0x67e8f9, .10)); cone.position.copy(group.position).addScaledVector(direction, -150); cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, -1, 0), direction); this.propulsionLayer.add(cone);
      }
      if (this.engineeringToggles.loadPaths) {
        const points = [group.position.clone(), new THREE.Vector3(0, 650, 0)]; const geometry = new THREE.BufferGeometry().setFromPoints(points); this.propulsionLayer.add(new THREE.Line(geometry, new THREE.LineDashedMaterial({ color: 0xfac775, dashSize: 22, gapSize: 14, transparent: true, opacity: .55 })));
      }
    });
    const cg = analysis?.massEngine?.vehicleCg;
    if (cg) { const marker = new THREE.Mesh(new THREE.SphereGeometry(24, 16, 12), engineeringMaterial(0xfac775, .95)); marker.position.copy(vectorFromRecord(cg).multiplyScalar(1000)); this.propulsionLayer.add(marker); }
    const center = analysis?.propulsionEngine?.centerOfThrust;
    if (center) { const marker = new THREE.Mesh(new THREE.OctahedronGeometry(28), engineeringMaterial(0x9d8cff, .95)); marker.position.copy(vectorFromRecord(center).multiplyScalar(1000)); this.propulsionLayer.add(marker); }
    const resultant = analysis?.propulsionEngine?.totalForce;
    if (this.engineeringToggles.vectors && center && resultant) {
      const vector = vectorFromRecord(resultant); const force = vector.length(); if (force > 0) this.propulsionLayer.add(new THREE.ArrowHelper(vector.normalize(), vectorFromRecord(center).multiplyScalar(1000), Math.max(130, Math.log1p(force) * 75), 0xffffff, 48, 23));
    }
    if (this.engineeringToggles.moments && analysis?.propulsionEngine?.totalMoment) {
      const moment = analysis.propulsionEngine.totalMoment; const axes = [['x', 0xff9d45, [0, Math.PI / 2, 0]], ['y', 0x9d8cff, [Math.PI / 2, 0, 0]], ['z', 0x71fff0, [0, 0, 0]]];
      axes.forEach(([axis, color, rotation]) => { if (Math.abs(moment[axis]) < 1e-6) return; const torus = new THREE.Mesh(new THREE.TorusGeometry(95, 4, 10, 48, Math.PI * 1.55), engineeringMaterial(color, .8)); torus.rotation.set(...rotation); torus.position.copy(vectorFromRecord(cg || {}).multiplyScalar(1000)); this.propulsionLayer.add(torus); });
    }
    this.render();
  }
}

export { defaultsFor };
