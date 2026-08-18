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

function buildHeadGeometry(params) {
  const width = Math.max(params.proximalWidth, params.distalWidth) + params.clearance * 2;
  const depth = Math.max(params.proximalDepth, params.distalDepth) + params.clearance * 2;
  const skull = { ...params, proximalWidth: width, distalWidth: width, proximalDepth: depth, distalDepth: depth, bulge: 0, clearance: 0, asymmetry: 0, shape: Math.max(2.05, params.shape) };
  const skullProfile = (axial, angle) => {
    const curve = Math.sin(Math.PI * axial);
    const widthFactor = .16 + Math.pow(Math.max(0, curve), .43) * (.87 + .13 * axial);
    const depthFactor = .2 + Math.pow(Math.max(0, curve), .46) * (.82 + .18 * axial);
    const front = Math.pow(Math.max(0, Math.sin(angle)), 8);
    const nose = Math.exp(-Math.pow((axial - .47) / .075, 2)) * depth * .105 * front;
    const brow = Math.exp(-Math.pow((axial - .61) / .07, 2)) * depth * .025 * front;
    const jaw = axial < .28 ? (1 - axial / .28) * width * .018 * Math.cos(angle) : 0;
    return { width: widthFactor, depth: depthFactor, x: jaw, z: nose + brow };
  };
  const pieces = [buildParametricShell(skull, { rings: 38, segments: 64, profile: skullProfile })];
  const earParams = { ...skull, length: params.length * .2, proximalWidth: width * .12, distalWidth: width * .1, proximalDepth: depth * .15, distalDepth: depth * .12, thickness: Math.min(params.thickness, width * .035), shape: 2.15 };
  pieces.push(organicPart(earParams, { position: [-width * .49, params.length * .07, 0], rotation: [0, 0, -.08] }, { rings: 14, segments: 24 }));
  pieces.push(organicPart(earParams, { position: [width * .49, params.length * .07, 0], rotation: [0, 0, .08] }, { rings: 14, segments: 24 }));
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
  return buildParametricShell(shoulder, { rings: 30, segments: 48, profile: shoulderProfile });
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
  const color = joint ? 0x10171c : (saved ? 0xf7fbfa : 0xdde4e5);
  const material = createRobotMaterial(color, joint
    ? { emissive: 0x020709, metalness: .5, roughness: .3, clearcoat: .48 }
    : { emissive: saved ? 0x061516 : 0x030708, metalness: .74, roughness: .17, clearcoat: 1 });
  material.userData.baseColor = color; material.userData.baseEmissive = joint ? 0x020709 : (saved ? 0x061516 : 0x030708);
  return material;
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
    const geometry = buildRegionGeometry(this.region, this.parameters);
    const joint = DARK_JOINT_REGIONS.has(this.region); this.shellMaterial.color.setHex(joint ? 0x10171c : 0xf1f7f6); this.shellMaterial.emissive.setHex(joint ? 0x020709 : 0x030809);
    this.shellMaterial.wireframe = this.layers.wireframe; this.shell = new THREE.Mesh(geometry, this.shellMaterial); this.group.add(this.shell);
    this.reference = new THREE.Mesh(geometry.clone(), this.referenceMaterial); this.reference.scale.set(.92, .985, .92); this.reference.visible = this.layers.reference; this.group.add(this.reference);
    this.frontGuides = createFrontGuides(this.region, this.parameters, .62); this.group.add(this.frontGuides);
    this.chestEmblem = this.region === 'chest' ? createChestEmblem(this.parameters) : null; if (this.chestEmblem) this.group.add(this.chestEmblem);
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
      if (region === 'chest') group.add(createChestEmblem(parameters[region]));
      const points = active.get(region)?.technicalPoints || [];
      if (points.length) {
        const vertices = [];
        points.slice(0, 128).forEach((point) => { const position = surfaceSample(parameters[region], finiteNumber(point.axial, .5, 0, 1), THREE.MathUtils.degToRad(finiteNumber(point.angle, 0, -180, 180))); vertices.push(position.x, position.y, position.z); });
        const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)); group.add(new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0xffc975, size: 7, sizeAttenuation: false })));
      }
      this.body.add(group);
    });
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
    canvas.addEventListener('pointerdown', (event) => { dragging = true; moved = 0; lastX = event.clientX; lastY = event.clientY; canvas.setPointerCapture(event.pointerId); });
    canvas.addEventListener('pointermove', (event) => { if (!dragging) return; const dx = event.clientX - lastX; const dy = event.clientY - lastY; moved += Math.abs(dx) + Math.abs(dy); this.yaw -= dx * .007; this.pitch = Math.max(-.85, Math.min(.85, this.pitch - dy * .005)); lastX = event.clientX; lastY = event.clientY; this.render(); });
    canvas.addEventListener('pointerup', (event) => {
      dragging = false; if (moved > 6) return; const rect = canvas.getBoundingClientRect(); const pointer = new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
      const raycaster = new THREE.Raycaster(); raycaster.setFromCamera(pointer, this.camera); const hit = raycaster.intersectObjects(this.meshes, false)[0]; if (hit?.object?.userData?.region) this.onPick?.(hit.object.userData.region);
    });
    canvas.addEventListener('wheel', (event) => { event.preventDefault(); this.distance = Math.max(1800, Math.min(7000, this.distance * Math.exp(event.deltaY * .001))); this.render(); }, { passive: false });
  }

  resize() { const width = Math.max(1, this.host.clientWidth); const height = Math.max(1, this.host.clientHeight); this.renderer.setSize(width, height, false); this.camera.aspect = width / height; this.camera.updateProjectionMatrix(); this.render(); }
  render() { const cp = Math.cos(this.pitch); this.camera.position.set(Math.sin(this.yaw) * cp * this.distance, this.target.y + Math.sin(this.pitch) * this.distance, Math.cos(this.yaw) * cp * this.distance); this.camera.lookAt(this.target); this.renderer.render(this.scene, this.camera); }
}

export { defaultsFor };
