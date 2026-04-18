import * as THREE from 'three';
import { createSubjectCrystal, createParticleField, createBurst, updateParticleObject } from '../objects.js';
import { createDissolveMaterial } from '../shaders.js';

export function createPracticeScene(runtime) {
  const { scene, camera, profile } = runtime;
  camera.position.set(0, 1.2, 7.1);
  camera.lookAt(0, 0.2, 0);

  const root = new THREE.Group();
  root.position.set(profile.mobile ? 0 : 1.05, -0.05, 0);
  scene.add(root);

  const palette = [0x67d8ff, 0xffd66b, 0xff8eb3, 0xb088ff, 0x79dac8];
  const crystals = [];
  for (let i = 0; i < 5; i += 1) {
    const angle = (i / 5) * Math.PI * 2;
    const crystal = createSubjectCrystal({ color: palette[i], accent: i % 2 ? 0x67d8ff : 0xffd66b, label: String(i) });
    crystal.position.set(Math.cos(angle) * 1.55, Math.sin(i * 1.1) * 0.18, Math.sin(angle) * 0.72);
    crystal.rotation.y = angle;
    crystal.userData.base = crystal.position.clone();
    crystal.userData.speed = 0.72 + i * 0.09;
    crystals.push(crystal);
    root.add(crystal);
  }

  const seal = new THREE.Mesh(
    new THREE.TorusKnotGeometry(0.48, 0.045, 96, 10),
    new THREE.MeshPhysicalMaterial({ color: 0xe14d3d, metalness: 0.42, roughness: 0.2, emissive: 0xe14d3d, emissiveIntensity: 0.22 }),
  );
  seal.position.set(0, -0.2, 0.4);
  root.add(seal);

  const dissolveMaterial = createDissolveMaterial(THREE, { color: 0xffd66b, base: 0x19213a });
  const dissolveSeal = new THREE.Mesh(new THREE.PlaneGeometry(1.15, 1.15, 32, 32), dissolveMaterial);
  dissolveSeal.position.set(0, 0.15, 0.88);
  dissolveSeal.rotation.z = Math.PI / 4;
  root.add(dissolveSeal);

  const platform = new THREE.Mesh(
    new THREE.CylinderGeometry(2.2, 2.35, 0.08, 96),
    new THREE.MeshStandardMaterial({ color: 0x10182f, metalness: 0.48, roughness: 0.34, emissive: 0x0d2b38, emissiveIntensity: 0.12 }),
  );
  platform.position.y = -1.04;
  platform.receiveShadow = true;
  root.add(platform);

  const particles = createParticleField({ count: Math.round(profile.mobile ? 140 : 540), radius: 5.8, color: 0x67d8ff, size: profile.mobile ? 0.052 : 0.038 });
  particles.position.set(root.position.x, 0.2, 0);
  scene.add(particles);

  const bursts = [];
  const spawn = (color = 0x67d8ff) => {
    const burst = createBurst({ count: profile.mobile ? 70 : 160, color, origin: new THREE.Vector3(root.position.x, 0, 0.4) });
    scene.add(burst);
    bursts.push(burst);
  };

  return {
    update({ time, delta, pointer }) {
      root.rotation.y = pointer.x * 0.18 + Math.sin(time * 0.2) * 0.1;
      root.rotation.x = -pointer.y * 0.05;
      crystals.forEach((crystal, index) => {
        crystal.rotation.y += delta * crystal.userData.speed;
        crystal.rotation.x = Math.sin(time * 0.8 + index) * 0.18;
        crystal.position.y = crystal.userData.base.y + Math.sin(time * 1.2 + index) * 0.14;
        crystal.userData.ring.rotation.z += delta * (0.55 + index * 0.06);
      });
      seal.rotation.x += delta * 0.5;
      seal.rotation.y -= delta * 0.65;
      seal.scale.setScalar(1 + Math.sin(time * 1.6) * 0.04);
      dissolveMaterial.uniforms.uTime.value = time;
      dissolveMaterial.uniforms.uThreshold.value = 0.28 + (Math.sin(time * 0.95) + 1) * 0.16;
      dissolveSeal.rotation.z += delta * 0.18;
      updateParticleObject(particles, delta, time);
      for (let i = bursts.length - 1; i >= 0; i -= 1) {
        if (!updateParticleObject(bursts[i], delta, time)) {
          scene.remove(bursts[i]);
          bursts.splice(i, 1);
        }
      }
    },
    onClick({ event }) {
      const card = event.target.closest('[data-three-click-burst], .practice-lane-card, .home-action-card, .answer-option, .option-card');
      if (!card) return;
      spawn(card.dataset.vfxColor ? Number(card.dataset.vfxColor) : 0xffd66b);
    },
  };
}
