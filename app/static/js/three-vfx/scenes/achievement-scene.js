import * as THREE from 'three';
import { createTrophyGroup, createParticleField, createBurst, updateParticleObject, createDistortionPortal } from '../objects.js';

export function createAchievementScene(runtime) {
  const { scene, camera, profile } = runtime;
  camera.position.set(0, 1.25, 6.4);
  camera.lookAt(0, 0.2, 0);

  const root = new THREE.Group();
  root.position.set(profile.mobile ? 0 : 1.15, -0.05, 0);
  scene.add(root);

  const portal = createDistortionPortal({ color: 0xffd66b, scale: 1.65 });
  portal.position.set(0, 0.45, -1.1);
  root.add(portal);

  const trophy = createTrophyGroup({ rarity: 'ssr', scale: 1.32 });
  trophy.position.set(0, -0.15, 0.4);
  root.add(trophy);

  const trophyLight = new THREE.PointLight(0xffd66b, 2.6, 7.5);
  trophyLight.position.set(0, 1.1, 1.8);
  root.add(trophyLight);

  const particles = createParticleField({ count: Math.round(profile.mobile ? 180 : 760), radius: 5.2, color: 0xffd66b, size: profile.mobile ? 0.06 : 0.047 });
  particles.position.copy(root.position);
  scene.add(particles);

  const blueParticles = createParticleField({ count: Math.round(profile.mobile ? 90 : 330), radius: 4.8, color: 0x67d8ff, size: 0.04 });
  blueParticles.position.set(root.position.x, 0.1, -0.2);
  scene.add(blueParticles);

  const bursts = [];
  let dragY = 0;
  let dragX = 0;

  const spawn = (color = 0xffd66b) => {
    const burst = createBurst({ count: profile.mobile ? 120 : 260, color, size: 0.082, origin: new THREE.Vector3(root.position.x, 0.25, 0.55) });
    scene.add(burst);
    bursts.push(burst);
  };

  setTimeout(() => spawn(0xffd66b), 450);

  return {
    update({ time, delta, pointer }) {
      root.rotation.y = dragY + pointer.x * 0.14 + Math.sin(time * 0.24) * 0.05;
      root.rotation.x = dragX - pointer.y * 0.05;
      trophy.rotation.y += delta * 0.45;
      trophy.position.y = -0.15 + Math.sin(time * 1.1) * 0.08;
      trophy.userData.ring.rotation.z -= delta * 0.9;
      trophy.userData.orbit.rotation.z += delta * 0.48;
      trophy.userData.auraMat.uniforms.uTime.value = time;
      portal.material.uniforms.uTime.value = time;
      trophyLight.intensity = 2.15 + Math.sin(time * 2.4) * 0.5;
      updateParticleObject(particles, delta, time);
      updateParticleObject(blueParticles, delta * 0.8, time);
      for (let i = bursts.length - 1; i >= 0; i -= 1) {
        if (!updateParticleObject(bursts[i], delta, time)) {
          scene.remove(bursts[i]);
          bursts.splice(i, 1);
        }
      }
    },
    onDrag({ dx, dy }) {
      dragY += dx * 0.006;
      dragX += dy * 0.003;
      dragX = Math.max(-0.45, Math.min(0.45, dragX));
    },
    onClick({ event }) {
      if (event.target.closest('a, button, input, textarea, select')) return;
      spawn(Math.random() > 0.5 ? 0xffd66b : 0xff8eb3);
    },
  };
}
