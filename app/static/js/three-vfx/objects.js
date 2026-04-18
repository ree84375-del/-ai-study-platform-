import * as THREE from 'three';
import { createEnergyFlowMaterial, createParticleMaterial, createDistortionMaterial } from './shaders.js';

const rarityPalette = {
  common: { main: 0xb87542, glow: 0xffb56b, accent: 0xf7d9a8 },
  rare: { main: 0x75d6ff, glow: 0x67d8ff, accent: 0xe6fbff },
  epic: { main: 0xa66bff, glow: 0xb088ff, accent: 0xffc7ff },
  legendary: { main: 0xffc34d, glow: 0xffd66b, accent: 0xfff0ad },
  ssr: { main: 0xffd66b, glow: 0xff8eb3, accent: 0x67d8ff },
};

export function getRarityPalette(rarity = 'legendary') {
  return rarityPalette[rarity] || rarityPalette.legendary;
}

function enableShadows(object) {
  object.traverse((child) => {
    if (child.isMesh) {
      child.castShadow = true;
      child.receiveShadow = true;
    }
  });
  return object;
}

export function createTrophyGroup({ rarity = 'legendary', scale = 1 } = {}) {
  const palette = getRarityPalette(rarity);
  const group = new THREE.Group();
  group.name = 'PBR Trophy';
  group.scale.setScalar(scale);

  const gold = new THREE.MeshPhysicalMaterial({
    color: palette.main,
    metalness: rarity === 'common' ? 0.62 : 0.92,
    roughness: rarity === 'common' ? 0.32 : 0.18,
    clearcoat: 0.82,
    clearcoatRoughness: 0.16,
    emissive: palette.glow,
    emissiveIntensity: rarity === 'ssr' ? 0.22 : 0.12,
  });

  const darkGold = new THREE.MeshStandardMaterial({
    color: 0x7c4618,
    metalness: 0.78,
    roughness: 0.24,
    emissive: palette.main,
    emissiveIntensity: 0.06,
  });

  const points = [
    new THREE.Vector2(0.16, 0),
    new THREE.Vector2(0.44, 0.08),
    new THREE.Vector2(0.62, 0.35),
    new THREE.Vector2(0.68, 0.74),
    new THREE.Vector2(0.57, 0.96),
    new THREE.Vector2(0.36, 1.03),
    new THREE.Vector2(0.22, 1.05),
  ];
  const cup = new THREE.Mesh(new THREE.LatheGeometry(points, 72), gold);
  cup.position.y = 0.42;
  cup.scale.set(1.12, 1.08, 1.12);
  group.add(cup);

  const handleGeometry = new THREE.TorusGeometry(0.38, 0.045, 16, 64, Math.PI * 1.22);
  const leftHandle = new THREE.Mesh(handleGeometry, gold);
  leftHandle.position.set(-0.63, 1.05, 0.02);
  leftHandle.rotation.set(Math.PI / 2, 0, Math.PI * 0.06);
  leftHandle.scale.set(0.86, 1.0, 1.0);
  group.add(leftHandle);

  const rightHandle = leftHandle.clone();
  rightHandle.position.x *= -1;
  rightHandle.rotation.z *= -1;
  group.add(rightHandle);

  const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.22, 0.42, 48), gold);
  stem.position.y = 0.12;
  group.add(stem);

  const base1 = new THREE.Mesh(new THREE.CylinderGeometry(0.56, 0.68, 0.18, 64), darkGold);
  base1.position.y = -0.18;
  group.add(base1);

  const base2 = new THREE.Mesh(new THREE.CylinderGeometry(0.72, 0.82, 0.16, 64), gold);
  base2.position.y = -0.36;
  group.add(base2);

  const shine = new THREE.Mesh(
    new THREE.PlaneGeometry(0.22, 1.18),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.34, blending: THREE.AdditiveBlending, depthWrite: false }),
  );
  shine.position.set(0.18, 1.12, 0.53);
  shine.rotation.z = -0.22;
  group.add(shine);

  const auraMat = createEnergyFlowMaterial(THREE, { color: palette.glow, accent: palette.accent, opacity: rarity === 'ssr' ? 0.92 : 0.74 });
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.82, 0.92, 96), auraMat);
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = -0.5;
  ring.name = 'Energy Flow Ring';
  group.add(ring);

  const orbit = new THREE.Mesh(new THREE.TorusGeometry(1.15, 0.012, 10, 120), new THREE.MeshBasicMaterial({ color: palette.glow, transparent: true, opacity: 0.62, blending: THREE.AdditiveBlending }));
  orbit.rotation.x = Math.PI / 2.7;
  orbit.rotation.y = Math.PI / 8;
  group.add(orbit);

  group.userData = { auraMat, ring, orbit, rarity, palette };
  return enableShadows(group);
}

export function createToriiGate({ scale = 1, color = 0xe14d3d } = {}) {
  const group = new THREE.Group();
  group.name = 'Neo Torii Gate';
  group.scale.setScalar(scale);
  const mat = new THREE.MeshPhysicalMaterial({
    color,
    metalness: 0.42,
    roughness: 0.28,
    clearcoat: 0.48,
    emissive: color,
    emissiveIntensity: 0.09,
  });
  const glow = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.2, blending: THREE.AdditiveBlending });
  const beamGeom = new THREE.BoxGeometry(3.4, 0.18, 0.22);
  const cap = new THREE.Mesh(beamGeom, mat);
  cap.position.y = 1.35;
  cap.scale.x = 1.12;
  group.add(cap);
  const beam = new THREE.Mesh(beamGeom, mat);
  beam.position.y = 1.05;
  group.add(beam);
  const pillarGeom = new THREE.BoxGeometry(0.18, 2.25, 0.18);
  const left = new THREE.Mesh(pillarGeom, mat);
  left.position.set(-1.18, -0.08, 0);
  const right = left.clone();
  right.position.x = 1.18;
  group.add(left, right);
  const glowPlane = new THREE.Mesh(new THREE.PlaneGeometry(3.2, 2.4), glow);
  glowPlane.position.set(0, 0.35, -0.05);
  group.add(glowPlane);
  return enableShadows(group);
}

export function createEnergyCore({ color = 0x67d8ff, accent = 0xffd66b, scale = 1 } = {}) {
  const group = new THREE.Group();
  group.name = 'Shader Energy Core';
  group.scale.setScalar(scale);
  const core = new THREE.Mesh(
    new THREE.IcosahedronGeometry(0.48, 3),
    new THREE.MeshPhysicalMaterial({
      color,
      metalness: 0.2,
      roughness: 0.12,
      transmission: 0.18,
      thickness: 0.4,
      emissive: color,
      emissiveIntensity: 0.38,
      clearcoat: 0.9,
    }),
  );
  group.add(core);
  const ringMat = createEnergyFlowMaterial(THREE, { color, accent, opacity: 0.78 });
  for (let i = 0; i < 3; i += 1) {
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.72 + i * 0.22, 0.735 + i * 0.22, 128), ringMat.clone());
    ring.rotation.set(Math.PI / 2 + i * 0.42, i * 0.7, 0);
    ring.userData.spin = 0.18 + i * 0.08;
    group.add(ring);
  }
  group.userData.core = core;
  return group;
}

export function createSubjectCrystal({ color = 0x67d8ff, accent = 0xffd66b, label = 'AI' } = {}) {
  const group = new THREE.Group();
  group.name = `Subject Crystal ${label}`;
  const mat = new THREE.MeshPhysicalMaterial({
    color,
    metalness: 0.15,
    roughness: 0.1,
    transmission: 0.18,
    clearcoat: 0.9,
    emissive: color,
    emissiveIntensity: 0.22,
  });
  const crystal = new THREE.Mesh(new THREE.OctahedronGeometry(0.46, 1), mat);
  group.add(crystal);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.72, 0.014, 8, 96), new THREE.MeshBasicMaterial({ color: accent, transparent: true, opacity: 0.72, blending: THREE.AdditiveBlending }));
  ring.rotation.x = Math.PI / 2;
  group.add(ring);
  group.userData = { crystal, ring, label };
  return enableShadows(group);
}

export function createParticleField({ count = 800, radius = 7, color = 0xffd66b, size = 0.045 } = {}) {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(count * 3);
  const seeds = new Float32Array(count);
  const velocities = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    const r = radius * Math.pow(Math.random(), 0.68);
    const theta = Math.random() * Math.PI * 2;
    const y = (Math.random() - 0.5) * radius * 1.15;
    positions[i * 3] = Math.cos(theta) * r;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = Math.sin(theta) * r * 0.55;
    velocities[i * 3] = (Math.random() - 0.5) * 0.04;
    velocities[i * 3 + 1] = 0.08 + Math.random() * 0.08;
    velocities[i * 3 + 2] = (Math.random() - 0.5) * 0.04;
    seeds[i] = Math.random();
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('aSeed', new THREE.BufferAttribute(seeds, 1));
  const material = createParticleMaterial(THREE, { color, size });
  const points = new THREE.Points(geometry, material);
  points.userData = { velocities, radius, material, burst: false, age: 0, maxAge: 2.2 };
  return points;
}

export function createBurst({ count = 180, color = 0xffd66b, size = 0.075, origin = new THREE.Vector3() } = {}) {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(count * 3);
  const seeds = new Float32Array(count);
  const velocities = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    positions[i * 3] = origin.x;
    positions[i * 3 + 1] = origin.y;
    positions[i * 3 + 2] = origin.z;
    const theta = Math.random() * Math.PI * 2;
    const speed = 1.6 + Math.random() * 2.8;
    velocities[i * 3] = Math.cos(theta) * speed;
    velocities[i * 3 + 1] = (Math.random() - 0.2) * speed;
    velocities[i * 3 + 2] = Math.sin(theta) * speed;
    seeds[i] = Math.random();
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('aSeed', new THREE.BufferAttribute(seeds, 1));
  const material = createParticleMaterial(THREE, { color, size });
  const points = new THREE.Points(geometry, material);
  points.userData = { velocities, material, burst: true, age: 0, maxAge: 1.35 };
  return points;
}

export function updateParticleObject(points, delta, time) {
  if (!points?.geometry?.attributes?.position) return false;
  const positions = points.geometry.attributes.position.array;
  const velocities = points.userData.velocities;
  const radius = points.userData.radius || 7;
  points.userData.material.uniforms.uTime.value = time;
  if (points.userData.burst) {
    points.userData.age += delta;
    const life = points.userData.age / points.userData.maxAge;
    for (let i = 0; i < positions.length / 3; i += 1) {
      positions[i * 3] += velocities[i * 3] * delta;
      positions[i * 3 + 1] += velocities[i * 3 + 1] * delta;
      positions[i * 3 + 2] += velocities[i * 3 + 2] * delta;
      velocities[i * 3 + 1] -= 1.8 * delta;
    }
    points.material.uniforms.uSize.value *= Math.max(0.965, 1 - life * 0.01);
    points.geometry.attributes.position.needsUpdate = true;
    return life < 1;
  }
  for (let i = 0; i < positions.length / 3; i += 1) {
    positions[i * 3] += velocities[i * 3] * delta;
    positions[i * 3 + 1] += velocities[i * 3 + 1] * delta;
    positions[i * 3 + 2] += velocities[i * 3 + 2] * delta;
    if (positions[i * 3 + 1] > radius * 0.62) positions[i * 3 + 1] = -radius * 0.62;
  }
  points.geometry.attributes.position.needsUpdate = true;
  return true;
}

export function createDistortionPortal({ color = 0x67d8ff, scale = 1 } = {}) {
  const portal = new THREE.Mesh(new THREE.PlaneGeometry(3.2, 3.2, 48, 48), createDistortionMaterial(THREE, { color }));
  portal.scale.setScalar(scale);
  portal.name = 'Distortion Portal';
  return portal;
}
