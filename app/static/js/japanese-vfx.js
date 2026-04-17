
(function () {
  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduceMotion) return;

  function rand(min, max) {
    return Math.random() * (max - min) + min;
  }

  function makeLayer(scene) {
    let layer = scene.querySelector(':scope > .jp-vfx-layer');
    if (!layer) {
      layer = document.createElement('span');
      layer.className = 'jp-vfx-layer';
      layer.setAttribute('aria-hidden', 'true');
      scene.prepend(layer);
    }
    return layer;
  }

  function spawnPetals(scene, count) {
    const layer = makeLayer(scene);
    const limit = Number(scene.dataset.vfxPetals || count || 10);
    for (let i = 0; i < limit; i += 1) {
      const petal = document.createElement('span');
      petal.className = 'jp-vfx-petal';
      petal.style.setProperty('--x', `${rand(4, 96)}%`);
      petal.style.setProperty('--s', `${rand(7, 15)}px`);
      petal.style.setProperty('--d', `${rand(6, 12)}s`);
      petal.style.setProperty('--delay', `${rand(0, 5)}s`);
      petal.style.setProperty('--drift', `${rand(-90, 90)}px`);
      layer.appendChild(petal);
      petal.addEventListener('animationend', () => petal.remove(), { once: true });
    }
  }

  function spawnSparks(scene, count) {
    const layer = makeLayer(scene);
    const limit = Number(scene.dataset.vfxSparks || count || 14);
    for (let i = 0; i < limit; i += 1) {
      const spark = document.createElement('span');
      spark.className = 'jp-vfx-spark';
      spark.style.setProperty('--x', `${rand(18, 82)}%`);
      spark.style.setProperty('--y', `${rand(38, 82)}%`);
      spark.style.setProperty('--s', `${rand(2, 6)}px`);
      spark.style.setProperty('--d', `${rand(2.8, 5.5)}s`);
      spark.style.setProperty('--delay', `${rand(0, 2.5)}s`);
      spark.style.setProperty('--drift', `${rand(-28, 28)}px`);
      layer.appendChild(spark);
      spark.addEventListener('animationend', () => spark.remove(), { once: true });
    }
  }

  function setupScene(scene) {
    scene.classList.add('jp-vfx-scene');
    const mode = scene.dataset.vfx || 'petals';
    const once = scene.dataset.vfxOnce === 'true';
    const run = () => {
      if (mode.includes('petals')) spawnPetals(scene, Number(scene.dataset.vfxPetals || 10));
      if (mode.includes('sparks')) spawnSparks(scene, Number(scene.dataset.vfxSparks || 12));
    };
    run();
    if (!once) {
      const interval = Number(scene.dataset.vfxInterval || 7000);
      window.setInterval(run, Math.max(3500, interval));
    }
  }

  function revealOnView() {
    const nodes = document.querySelectorAll('[data-vfx-reveal]');
    if (!('IntersectionObserver' in window)) {
      nodes.forEach((node) => node.classList.add('jp-vfx-reveal'));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('jp-vfx-reveal');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.16 });
    nodes.forEach((node) => observer.observe(node));
  }

  function bindUnlockBursts() {
    document.querySelectorAll('[data-trophy-burst]').forEach((stage) => {
      const burst = () => spawnSparks(stage, Number(stage.dataset.vfxSparks || 28));
      stage.addEventListener('mouseenter', burst);
      stage.addEventListener('focusin', burst);
      if (stage.dataset.trophyBurst === 'auto') {
        window.setTimeout(burst, 450);
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-vfx]').forEach(setupScene);
    revealOnView();
    bindUnlockBursts();
    document.querySelectorAll('.practice-lane-card, .home-action-card, .achievement-card').forEach((node) => {
      node.classList.add('jp-vfx-hover-lift');
    });
  });
})();
