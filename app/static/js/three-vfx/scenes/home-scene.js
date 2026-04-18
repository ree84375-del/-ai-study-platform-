import * as THREE from 'three';
import {
  createToriiGate,
  createEnergyCore,
  createParticleField,
  createBurst,
  updateParticleObject,
  createDistortionPortal,
} from '../objects.js';

export function createHomeScene(runtime) {
  const { scene, camera, profile } = runtime;
  camera.position.set(0, 1.45, 7.2);
  camera.lookAt(0, 0.35, 0);

  const root = new THREE.Group();
  root.position.set(1.2, 0, -0.4);
  scene.add(root);

  const portal = createDistortionPortal({ color: 0x67d8ff, scale: 1.5 });
  portal.position.set(0, 0.52, -1.05);
  root.add(portal);

  const torii = createToriiGate({ scale: 1.15, color: 0xe14d3d });
  torii.position.set(0, 0.2, -0.2);
  root.add(torii);

  const core = createEnergyCore({ color: 0x67d8ff, accent: 0xffd66b, scale: 1.05 });
  core.position.set(0, 0.32, 0.8);
  root.add(core);

  const platform = new THREE.Mesh(
    new THREE.CylinderGeometry(1.95, 2.15, 0.12, 96),
    new THREE.MeshPhysicalMaterial({ color: 0x10182f, metalness: 0.48, roughness: 0.32, emissive: 0x112244, emissiveIntensity: 0.08 }),
  );
  platform.position.y = -1.18;
  platform.receiveShadow = true;
  root.add(platform);

  const lanternMat = new THREE.MeshBasicMaterial({ color: 0xffb15d, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending });
  const lanterns = [];
  [-1, 1].forEach((side) => {
    const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.13, 24, 16), lanternMat);
    lamp.position.set(side * 1.7, 0.75, 0.25);
    const light = new THREE.PointLight(0xffa45f, 1.45, 4.6);
    light.position.copy(lamp.position);
    root.add(lamp, light);
    lanterns.push({ lamp, light, side });
  });

  const particleCount = Math.round((profile.mobile ? 260 : 920) * profile.particleScale);
  const particles = createParticleField({ count: particleCount, radius: 8, color: 0xffd66b, size: profile.mobile ? 0.055 : 0.044 });
  particles.position.set(0, 0.6, -1.4);
  scene.add(particles);

  const sakura = createParticleField({ count: Math.round(profile.mobile ? 120 : 360), radius: 7.5, color: 0xff8eb3, size: profile.mobile ? 0.045 : 0.035 });
  sakura.position.set(-1.2, 1.2, 0.4);
  scene.add(sakura);

  const emaGroup = new THREE.Group();
  const emaMaterial = new THREE.MeshPhysicalMaterial({ color: 0xd99651, metalness: 0.1, roughness: 0.42, emissive: 0xffd66b, emissiveIntensity: 0.07 });
  for (let i = 0; i < 5; i += 1) {
    const ema = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.26, 0.035), emaMaterial);
    ema.position.set(-1.9 + i * 0.38, 1.55 + Math.sin(i) * 0.18, -0.08 + Math.cos(i) * 0.12);
    ema.rotation.set(0.2, -0.3 + i * 0.15, -0.12 + i * 0.05);
    emaGroup.add(ema);
  }
  root.add(emaGroup);

  const bursts = [];

  return {
    update({ time, delta, pointer, scroll }) {
      root.rotation.y = pointer.x * 0.18 + Math.sin(time * 0.12) * 0.05;
      root.rotation.x = -pointer.y * 0.045;
      root.position.y = Math.sin(time * 0.8) * 0.05 - scroll.progress * 0.3;
      torii.rotation.y = Math.sin(time * 0.35) * 0.05;
      core.rotation.y += delta * 0.55;
      core.rotation.x = Math.sin(time * 0.48) * 0.11;
      core.children.forEach((child) => {
        if (child.material?.uniforms?.uTime) child.material.uniforms.uTime.value = time;
        if (child.userData.spin) child.rotation.z += delta * child.userData.spin;
      });
      portal.material.uniforms.uTime.value = time;
      lanterns.forEach(({ lamp, light, side }, index) => {
        const pulse = 0.8 + Math.sin(time * 2.2 + index) * 0.2;
        lamp.position.y = 0.75 + Math.sin(time * 1.3 + side) * 0.08;
        light.position.copy(lamp.position);
        light.intensity = 1.2 + pulse * 0.5;
      });
      emaGroup.children.forEach((ema, index) => {
        ema.rotation.z = Math.sin(time * 1.2 + index) * 0.13;
        ema.position.y += Math.sin(time + index) * 0.0008;
      });
      updateParticleObject(particles, delta, time);
      updateParticleObject(sakura, delta * 0.64, time * 0.82);
      for (let i = bursts.length - 1; i >= 0; i -= 1) {
        if (!updateParticleObject(bursts[i], delta, time)) {
          scene.remove(bursts[i]);
          bursts.splice(i, 1);
        }
      }
    },
    onClick({ event }) {
      if (!event.target.closest('[data-three-click-burst], .home-primary-action, .home-secondary-action, .home-action-card')) return;
      const burst = createBurst({ count: profile.mobile ? 80 : 180, color: 0xffd66b, origin: new THREE.Vector3(root.position.x, 0.15, 0.5) });
      scene.add(burst);
      bursts.push(burst);
    },
  };
}
