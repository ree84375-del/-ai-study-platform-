import { ThreeVfxRuntime, canRunWebGL } from './core.js';
import { createHomeScene } from './scenes/home-scene.js';
import { createAchievementScene } from './scenes/achievement-scene.js';
import { createPracticeScene } from './scenes/practice-scene.js';
import { initLocalThreeStages } from './local-scenes.js';

const sceneFactories = {
  home: createHomeScene,
  achievement: createAchievementScene,
  practice: createPracticeScene,
};

function detectScene() {
  const signal = document.querySelector('[data-three-scene]');
  if (signal?.dataset.threeScene) return signal.dataset.threeScene;
  if (document.body.classList.contains('three-scene-home')) return 'home';
  if (document.body.classList.contains('three-scene-achievement')) return 'achievement';
  if (document.body.classList.contains('three-scene-practice')) return 'practice';
  return null;
}

function setupScrollReveal() {
  const nodes = document.querySelectorAll('.washi-card, .home-action-card, .practice-lane-card, .achievement-card, [data-three-reveal]');
  nodes.forEach((node) => node.classList.add('three-scroll-reveal'));
  if (!('IntersectionObserver' in window)) {
    nodes.forEach((node) => node.classList.add('is-visible'));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
  nodes.forEach((node) => observer.observe(node));
}

function setupClickInk() {
  const ink = document.createElement('span');
  ink.className = 'three-ink-transition';
  document.body.appendChild(ink);
  document.addEventListener('click', (event) => {
    const target = event.target.closest('[data-three-click-burst], .home-action-card, .practice-lane-card, .achievement-card, .answer-option, .option-card');
    if (!target) return;
    ink.style.setProperty('--x', `${event.clientX}px`);
    ink.style.setProperty('--y', `${event.clientY}px`);
    ink.classList.add('is-active');
    window.setTimeout(() => ink.classList.remove('is-active'), 360);
  }, { passive: true });
}

function setupTiltCards() {
  const cards = document.querySelectorAll('.home-action-card, .practice-lane-card, .achievement-card, [data-three-tilt]');
  cards.forEach((card) => {
    card.addEventListener('pointermove', (event) => {
      const rect = card.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / Math.max(1, rect.width)) - 0.5;
      const y = ((event.clientY - rect.top) / Math.max(1, rect.height)) - 0.5;
      card.style.setProperty('--tilt-x', `${(-y * 7).toFixed(2)}deg`);
      card.style.setProperty('--tilt-y', `${(x * 7).toFixed(2)}deg`);
      card.style.transform = `translateY(-7px) rotateX(${(-y * 7).toFixed(2)}deg) rotateY(${(x * 7).toFixed(2)}deg)`;
    }, { passive: true });
    card.addEventListener('pointerleave', () => {
      card.style.transform = '';
    }, { passive: true });
  });
}

function initThreeRedesign() {
  const sceneKey = detectScene();
  if (!sceneKey || !sceneFactories[sceneKey]) return;
  document.body.classList.add('three-redesign-page', `three-scene-${sceneKey}`);
  setupScrollReveal();
  setupClickInk();
  setupTiltCards();

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const webglReady = !reduceMotion && canRunWebGL();
  if (!webglReady) {
    document.body.classList.add('three-webgl-fallback');
    return;
  }

  try {
    const localStages = initLocalThreeStages();
    window.__threeLocalStages = localStages;
  } catch (error) {
    console.error('[three-vfx] Local Three.js scenes failed.', error);
  }

  const stage = document.querySelector('[data-three-stage]');
  const canvas = document.querySelector('[data-three-canvas]');
  if (!stage || !canvas) {
    if (!window.__threeLocalStages?.length) document.body.classList.add('three-webgl-fallback');
    return;
  }

  try {
    const runtime = new ThreeVfxRuntime({ canvas, sceneKey });
    runtime.init(sceneFactories[sceneKey]);
    window.__threeVfxRuntime = runtime;
  } catch (error) {
    console.error('[three-vfx] WebGL runtime failed; fallback kept visible.', error);
    document.body.classList.add('three-webgl-fallback');
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initThreeRedesign, { once: true });
} else {
  initThreeRedesign();
}
