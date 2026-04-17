/**
 * Japanese learning hall interactions.
 * Lightweight, dependency-free animations so deployment stays small.
 */

(function () {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  document.addEventListener("DOMContentLoaded", () => {
    document.body.classList.add("jp-loaded");
    initPageTheme();
    initPerformanceBudget();
    mountAmbience();
    mountWebglGlow();
    mountParticleField();
    mountSvgConstellation();
    initReveal();
    initCountUp();
    initInkRipple();
    initPointerGlow();
    init3DTiltCards();
    initPaperUnfold();
    initStepFocus();
    initAchievementFilters();
    initScrollProgress();
    initQuestionTransitions();
    initScoreReveal();
    initAchievementTrophies();
    initLearningDashboard();
    initAiStatusUX();
    initAchievementToast();
  });

  function initPageTheme() {
    const path = window.location.pathname;
    const theme = document.documentElement.getAttribute("data-theme") || localStorage.getItem("app-theme") || "sakura";
    const themes = [
      { test: /^\/$/, name: "jp-page-home" },
      { test: /^\/(?:study\/)?practice\/cap/, name: "jp-page-cap" },
      { test: /mistakes|wrong/i, name: "jp-page-mistakes" },
      { test: /guide|lecture|library/i, name: "jp-page-guides" },
      { test: /^\/(?:study\/)?practice/, name: "jp-page-practice" },
      { test: /chat/i, name: "jp-page-chat" },
      { test: /admin/i, name: "jp-page-admin" },
      { test: /achievements/i, name: "jp-page-achievements" }
    ];

    const matched = themes.find((theme) => theme.test.test(path));
    document.body.classList.add(matched ? matched.name : "jp-page-default");
    document.body.classList.add(`jp-theme-${theme}`);
  }

  function initPerformanceBudget() {
    const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    const saveData = Boolean(connection && connection.saveData);
    const smallScreen = window.innerWidth < 760;
    const lowMemory = Number(navigator.deviceMemory || 8) <= 4;
    const coarsePointer = window.matchMedia("(pointer: coarse)").matches;
    const lowPower = reduceMotion || saveData || (smallScreen && (lowMemory || coarsePointer));

    document.body.classList.toggle("jp-low-power", lowPower);
    document.body.classList.toggle("jp-fx-ready", !lowPower);
  }

  function mountAmbience() {
    if (reduceMotion || document.querySelector(".jp-ambience")) return;

    const ambience = document.createElement("div");
    ambience.className = "jp-ambience";

    const count = window.innerWidth < 768 ? 8 : 18;
    for (let i = 0; i < count; i += 1) {
      const petal = document.createElement("span");
      const left = Math.round(Math.random() * 100);
      const delay = Math.round(Math.random() * -15000);
      const speed = 12000 + Math.round(Math.random() * 12000);
      const drift = Math.round((Math.random() - 0.5) * 180);

      petal.style.left = `${left}%`;
      petal.style.setProperty("--jp-float-delay", `${delay}ms`);
      petal.style.setProperty("--jp-float-speed", `${speed}ms`);
      petal.style.setProperty("--jp-drift", `${drift}px`);
      petal.style.opacity = `${0.3 + Math.random() * 0.45}`;
      ambience.appendChild(petal);
    }

    document.body.prepend(ambience);
  }

  function mountWebglGlow() {
    if (reduceMotion || document.body.classList.contains("jp-low-power") || document.querySelector(".jp-webgl-glow")) return;

    const canvas = document.createElement("canvas");
    canvas.className = "jp-webgl-glow";
    canvas.setAttribute("aria-hidden", "true");
    document.body.prepend(canvas);

    const gl = canvas.getContext("webgl", {
      alpha: true,
      antialias: false,
      depth: false,
      stencil: false,
      powerPreference: "low-power"
    });
    if (!gl) {
      canvas.remove();
      return;
    }

    const vertexSource = `
      attribute vec2 a_position;
      void main() {
        gl_Position = vec4(a_position, 0.0, 1.0);
      }
    `;
    const fragmentSource = `
      precision mediump float;
      uniform vec2 u_resolution;
      uniform float u_time;
      void main() {
        vec2 uv = gl_FragCoord.xy / max(u_resolution.xy, vec2(1.0));
        vec2 p = uv - 0.5;
        float wave = sin((p.x * 4.0 + p.y * 2.0 + u_time * 0.18) * 3.14159) * 0.5 + 0.5;
        float orbA = smoothstep(0.62, 0.02, distance(uv, vec2(0.18 + sin(u_time * 0.11) * 0.035, 0.22)));
        float orbB = smoothstep(0.56, 0.02, distance(uv, vec2(0.84, 0.16 + cos(u_time * 0.09) * 0.04)));
        float orbC = smoothstep(0.72, 0.03, distance(uv, vec2(0.74 + sin(u_time * 0.07) * 0.04, 0.82)));
        vec3 gold = vec3(0.95, 0.68, 0.25);
        vec3 indigo = vec3(0.08, 0.23, 0.38);
        vec3 sage = vec3(0.30, 0.48, 0.40);
        vec3 color = gold * orbA + indigo * orbB + sage * orbC;
        float alpha = (orbA + orbB + orbC) * 0.105 + wave * 0.014;
        gl_FragColor = vec4(color, min(alpha, 0.18));
      }
    `;

    const makeShader = (type, source) => {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        gl.deleteShader(shader);
        return null;
      }
      return shader;
    };

    const vertexShader = makeShader(gl.VERTEX_SHADER, vertexSource);
    const fragmentShader = makeShader(gl.FRAGMENT_SHADER, fragmentSource);
    if (!vertexShader || !fragmentShader) {
      canvas.remove();
      return;
    }

    const program = gl.createProgram();
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      canvas.remove();
      return;
    }

    const positions = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, positions);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);

    const positionLocation = gl.getAttribLocation(program, "a_position");
    const resolutionLocation = gl.getUniformLocation(program, "u_resolution");
    const timeLocation = gl.getUniformLocation(program, "u_time");

    let width = 0;
    let height = 0;
    let rafId = 0;
    let last = 0;

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 1.35);
      width = Math.max(1, Math.floor(window.innerWidth * ratio));
      height = Math.max(1, Math.floor(window.innerHeight * ratio));
      canvas.width = width;
      canvas.height = height;
      gl.viewport(0, 0, width, height);
    };

    const render = (time) => {
      if (document.hidden) {
        rafId = requestAnimationFrame(render);
        return;
      }
      if (time - last < 33) {
        rafId = requestAnimationFrame(render);
        return;
      }
      last = time;
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(program);
      gl.enableVertexAttribArray(positionLocation);
      gl.bindBuffer(gl.ARRAY_BUFFER, positions);
      gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);
      gl.uniform2f(resolutionLocation, width, height);
      gl.uniform1f(timeLocation, time * 0.001);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      rafId = requestAnimationFrame(render);
    };

    resize();
    window.addEventListener("resize", resize, { passive: true });
    rafId = requestAnimationFrame(render);

    window.addEventListener("beforeunload", () => cancelAnimationFrame(rafId), { once: true });
  }

  function mountParticleField() {
    if (reduceMotion || document.querySelector(".jp-particle-canvas")) return;

    const canvas = document.createElement("canvas");
    canvas.className = "jp-particle-canvas";
    canvas.setAttribute("aria-hidden", "true");
    document.body.prepend(canvas);

    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) {
      canvas.remove();
      return;
    }

    const lowPower = document.body.classList.contains("jp-low-power");
    const palette = getParticlePalette();
    const pointer = { x: -9999, y: -9999, active: false };
    const particles = [];
    let width = 0;
    let height = 0;
    let ratio = 1;
    let rafId = 0;
    let last = 0;

    const resize = () => {
      ratio = Math.min(window.devicePixelRatio || 1, lowPower ? 1 : 1.4);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.max(1, Math.floor(width * ratio));
      canvas.height = Math.max(1, Math.floor(height * ratio));
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      seedParticles();
    };

    const seedParticles = () => {
      const base = lowPower ? 12 : Math.min(54, Math.max(24, Math.round(width / 34)));
      particles.length = 0;
      for (let i = 0; i < base; i += 1) {
        particles.push({
          x: Math.random() * width,
          y: Math.random() * height,
          r: 1.2 + Math.random() * (lowPower ? 1.6 : 2.8),
          vx: -0.08 + Math.random() * 0.16,
          vy: 0.05 + Math.random() * 0.18,
          color: palette[i % palette.length],
          phase: Math.random() * Math.PI * 2
        });
      }
    };

    const draw = (time) => {
      if (document.hidden) {
        rafId = requestAnimationFrame(draw);
        return;
      }
      if (time - last < (lowPower ? 66 : 33)) {
        rafId = requestAnimationFrame(draw);
        return;
      }
      last = time;
      ctx.clearRect(0, 0, width, height);
      ctx.globalCompositeOperation = "source-over";

      particles.forEach((particle, index) => {
        particle.phase += 0.012;
        particle.x += particle.vx + Math.sin(particle.phase) * 0.045;
        particle.y += particle.vy;

        if (pointer.active) {
          const dx = particle.x - pointer.x;
          const dy = particle.y - pointer.y;
          const dist = Math.max(1, Math.hypot(dx, dy));
          if (dist < 120) {
            const force = (120 - dist) / 120;
            particle.x += (dx / dist) * force * 1.2;
            particle.y += (dy / dist) * force * 1.2;
          }
        }

        if (particle.y > height + 18) {
          particle.y = -18;
          particle.x = Math.random() * width;
        }
        if (particle.x < -18) particle.x = width + 18;
        if (particle.x > width + 18) particle.x = -18;

        ctx.beginPath();
        ctx.fillStyle = particle.color;
        ctx.globalAlpha = lowPower ? 0.22 : 0.34;
        ctx.arc(particle.x, particle.y, particle.r, 0, Math.PI * 2);
        ctx.fill();

        const next = particles[index + 1];
        if (next && index % 3 === 0) {
          const lineDistance = Math.hypot(particle.x - next.x, particle.y - next.y);
          if (lineDistance < 170) {
            ctx.beginPath();
            ctx.globalAlpha = (1 - lineDistance / 170) * 0.11;
            ctx.strokeStyle = particle.color;
            ctx.lineWidth = 1;
            ctx.moveTo(particle.x, particle.y);
            ctx.lineTo(next.x, next.y);
            ctx.stroke();
          }
        }
      });

      ctx.globalAlpha = 1;
      rafId = requestAnimationFrame(draw);
    };

    const onPointerMove = (event) => {
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      pointer.active = true;
    };

    const onPointerLeave = () => {
      pointer.active = false;
    };

    resize();
    window.addEventListener("resize", resize, { passive: true });
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("pointerleave", onPointerLeave, { passive: true });
    rafId = requestAnimationFrame(draw);

    window.addEventListener("beforeunload", () => cancelAnimationFrame(rafId), { once: true });
  }

  function mountSvgConstellation() {
    if (reduceMotion || document.body.classList.contains("jp-low-power") || document.querySelector(".jp-svg-constellation")) return;

    const wrap = document.createElement("div");
    wrap.className = "jp-svg-constellation";
    wrap.setAttribute("aria-hidden", "true");
    wrap.innerHTML = `
      <svg viewBox="0 0 1000 420" preserveAspectRatio="none">
        <path class="jp-line jp-line-a" d="M12 108 C 160 20, 252 196, 388 112 S 650 34, 812 118 S 946 122, 1000 74"></path>
        <path class="jp-line jp-line-b" d="M0 330 C 142 272, 224 404, 386 318 S 638 246, 796 310 S 934 358, 1000 294"></path>
        <path class="jp-line jp-line-c" d="M104 22 C 232 86, 194 204, 328 246 S 568 222, 642 326 S 812 408, 936 342"></path>
      </svg>
    `;
    document.body.prepend(wrap);
  }

  function getParticlePalette() {
    const theme = document.documentElement.getAttribute("data-theme") || "sakura";
    const themePalettes = {
      sakura: ["rgba(232,92,124,0.48)", "rgba(255,190,204,0.5)", "rgba(201,154,62,0.42)"],
      matcha: ["rgba(76,126,84,0.56)", "rgba(179,194,118,0.5)", "rgba(201,154,62,0.36)"],
      leaf: ["rgba(55,119,88,0.54)", "rgba(145,184,94,0.46)", "rgba(255,245,199,0.42)"],
      moon: ["rgba(45,76,128,0.52)", "rgba(229,192,105,0.5)", "rgba(226,235,255,0.42)"],
      midnight: ["rgba(92,112,180,0.48)", "rgba(185,150,230,0.38)", "rgba(255,255,255,0.28)"],
      sunset: ["rgba(224,96,64,0.5)", "rgba(242,165,78,0.5)", "rgba(57,72,110,0.34)"]
    };
    if (themePalettes[theme]) return themePalettes[theme];

    if (document.body.classList.contains("jp-page-cap")) {
      return ["rgba(23,58,94,0.72)", "rgba(201,154,62,0.64)", "rgba(80,125,168,0.52)"];
    }
    if (document.body.classList.contains("jp-page-mistakes")) {
      return ["rgba(138,49,68,0.62)", "rgba(185,79,53,0.46)", "rgba(23,58,94,0.38)"];
    }
    if (document.body.classList.contains("jp-page-guides")) {
      return ["rgba(85,120,102,0.62)", "rgba(201,154,62,0.48)", "rgba(64,112,92,0.42)"];
    }
    if (document.body.classList.contains("jp-page-chat")) {
      return ["rgba(61,108,154,0.58)", "rgba(201,154,62,0.45)", "rgba(255,255,255,0.5)"];
    }
    return ["rgba(185,79,53,0.45)", "rgba(201,154,62,0.58)", "rgba(85,120,102,0.42)"];
  }

  function initReveal() {
    const selectors = [
      ".entry-stat",
      ".entry-lane",
      ".entry-preview",
      ".entry-step-card",
      ".home-command-hero",
      ".home-action-card",
      ".home-mission-strip article",
      ".practice-gate-hero",
      ".practice-stepper",
      ".practice-lane-card",
      ".practice-choice-panel",
      ".practice-next-strip article",
      ".cap-stat",
      ".cap-year-card",
      ".cap-subject-card",
      ".cap-mode-option",
      ".cap-preview",
      ".cap-run-card",
      ".cap-score-card",
      ".cap-sidebar-item",
      ".review-card",
      ".review-question",
      ".mockroom-stat",
      ".mockroom-card",
      ".mockroom-question",
      ".mistake-stat",
      ".mistake-filter",
      ".mistake-subject",
      ".mistake-card",
      ".mistake-dojo-stat",
      ".mistake-filter-card",
      ".mistake-subject-card",
      ".mistake-yokai-card",
      ".mistake-action-panel",
      ".guide-stat",
      ".guide-card",
      ".guide-summary",
      ".guide-library-stat",
      ".guide-flow-step",
      ".guide-shelf-card",
      ".guide-series-card",
      ".guide-book-card",
      ".guide-library-aside",
      ".reader-stat",
      ".reader-card",
      ".reader-panel",
      ".reader-section",
      ".reader-page-card",
      ".reader-outline a",
      ".reader-book-stat",
      ".reader-summary-strip",
      ".reader-outline-card",
      ".reader-book-chapter",
      ".reader-book-section",
      ".chat-bubble",
      ".session-item",
      ".command-item",
      ".jp-learning-dashboard",
      ".jp-dashboard-card",
      ".jp-radar-card",
      ".jp-ai-status-panel",
      ".achievement-stat",
      ".achievement-focus",
      ".achievement-card",
      ".achievement-rank-card",
      ".achievement-sakura-card",
      ".achievement-event-card",
      ".achievement-collection-panel",
      ".omamori-card",
      ".seal-card",
      ".yokai-card",
      ".achievement-home-card",
      ".admin-achievement-stat",
      ".admin-achievement-card",
      ".admin-achievement-panel",
      ".washi-card",
      ".glass-panel"
    ];

    const nodes = Array.from(document.querySelectorAll(selectors.join(",")));
    if (!nodes.length) return;

    nodes.forEach((node, index) => {
      node.classList.add("jp-reveal");
      node.style.setProperty("--jp-delay", `${Math.min(index % 12, 10) * 44}ms`);
    });

    if (reduceMotion || !("IntersectionObserver" in window)) {
      nodes.forEach((node) => node.classList.add("is-visible"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );

    nodes.forEach((node) => observer.observe(node));
  }

  function initCountUp() {
    if (reduceMotion) return;

    const candidates = Array.from(
      document.querySelectorAll(
        ".entry-stat strong, .cap-stat strong, .mockroom-stat strong, .mistake-stat strong, .guide-stat strong, .reader-stat strong, .guide-summary-item strong"
          + ", .guide-library-stat strong, .reader-book-stat strong, .mistake-dojo-stat strong"
          + ", .achievement-stat strong, .admin-achievement-stat strong, .cap-score-card strong, .jp-dashboard-card strong, .jp-radar-card strong, .cap-sidebar-item strong"
          + ", [data-count-up], .practice-gate-stats strong, .home-mission-strip strong"
      )
    );

    const numericNodes = candidates
      .map((node) => {
        const raw = node.textContent.trim().replace(/,/g, "");
        if (!/^\d+(\.\d+)?$/.test(raw)) return null;
        return { node, target: Number(raw), decimals: raw.includes(".") ? raw.split(".")[1].length : 0 };
      })
      .filter(Boolean);

    if (!numericNodes.length) return;

    const run = ({ node, target, decimals }) => {
      const duration = 720;
      const start = performance.now();
      const formatter = new Intl.NumberFormat("zh-Hant", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
      });

      const frame = (now) => {
        const progress = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        node.textContent = formatter.format(target * eased);
        if (progress < 1) {
          requestAnimationFrame(frame);
        } else {
          node.textContent = formatter.format(target);
        }
      };

      requestAnimationFrame(frame);
    };

    if (!("IntersectionObserver" in window)) {
      numericNodes.forEach(run);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting || entry.target.dataset.jpCounted) return;
          entry.target.dataset.jpCounted = "true";
          const item = numericNodes.find((candidate) => candidate.node === entry.target);
          if (item) run(item);
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.35 }
    );

    numericNodes.forEach(({ node }) => {
      if (!node.dataset.jpCounted) observer.observe(node);
    });
  }

  function initInkRipple() {
    document.addEventListener("click", (event) => {
      const target = event.target.closest(
        ".entry-cta, .entry-ghost, .home-primary-action, .home-secondary-action, .home-action-card, .practice-primary-action, .practice-secondary-action, .practice-lane-card, .cap-primary, .cap-ghost, .mockroom-btn, .mockroom-link, .mistake-btn, .mistake-link, .mistake-filter-card, .mistake-subject-card, .guide-action, .guide-link, .guide-shelf-card, .guide-series-card, .guide-book-card, .reader-action, .reader-outline a, .reader-page-card, .achievement-primary, .achievement-filter, .admin-action-btn, .btn, button, .session-item, .command-item, .cap-jump-chip"
      );
      if (!target || target.disabled || reduceMotion) return;

      const rect = target.getBoundingClientRect();
      const ripple = document.createElement("span");
      ripple.className = "jp-ink-ripple";
      ripple.style.left = `${event.clientX - rect.left}px`;
      ripple.style.top = `${event.clientY - rect.top}px`;
      target.appendChild(ripple);
      ripple.addEventListener("animationend", () => ripple.remove(), { once: true });
    });
  }

  function initPointerGlow() {
    const glowTargets = document.querySelectorAll(
      ".entry-lane, .home-action-card, .practice-lane-card, .practice-choice-panel, .cap-year-card, .cap-subject-card, .cap-mode-option, .cap-run-card, .mockroom-card, .mistake-card, .mistake-filter-card, .mistake-subject-card, .mistake-yokai-card, .guide-card, .guide-shelf-card, .guide-series-card, .guide-book-card, .reader-card, .reader-chapter, .reader-book-chapter, .reader-book-section, .reader-page-card, .chat-bubble, .achievement-card, .achievement-home-card, .admin-achievement-card, .jp-dashboard-card"
    );

    glowTargets.forEach((target) => {
      target.addEventListener("pointermove", (event) => {
        const rect = target.getBoundingClientRect();
        target.style.setProperty("--jp-ripple-x", `${event.clientX - rect.left}px`);
        target.style.setProperty("--jp-ripple-y", `${event.clientY - rect.top}px`);
      });
    });
  }

  function init3DTiltCards() {
    if (reduceMotion || document.body.classList.contains("jp-low-power")) return;

    const cards = Array.from(
      document.querySelectorAll(
        ".entry-lane, .home-action-card, .practice-lane-card, .practice-choice-panel, .cap-year-card, .cap-subject-card, .cap-mode-option, .mockroom-card, .mistake-card, .mistake-filter-card, .mistake-subject-card, .mistake-yokai-card, .guide-card, .guide-shelf-card, .guide-series-card, .guide-book-card, .reader-card, .reader-book-chapter, .reader-book-section, .reader-page-card, .achievement-card, .achievement-home-card, .admin-achievement-card, .jp-dashboard-card, .jp-radar-card"
      )
    );
    if (!cards.length) return;

    cards.forEach((card) => {
      card.classList.add("jp-tilt-card");
      let raf = 0;

      const update = (event) => {
        if (raf) cancelAnimationFrame(raf);
        raf = requestAnimationFrame(() => {
          const rect = card.getBoundingClientRect();
          const px = (event.clientX - rect.left) / Math.max(1, rect.width);
          const py = (event.clientY - rect.top) / Math.max(1, rect.height);
          const rotateY = (px - 0.5) * 8;
          const rotateX = (0.5 - py) * 7;
          card.style.setProperty("--jp-tilt-x", `${rotateX.toFixed(2)}deg`);
          card.style.setProperty("--jp-tilt-y", `${rotateY.toFixed(2)}deg`);
          card.style.setProperty("--jp-tilt-glow-x", `${Math.round(px * 100)}%`);
          card.style.setProperty("--jp-tilt-glow-y", `${Math.round(py * 100)}%`);
          card.classList.add("is-tilting");
        });
      };

      const reset = () => {
        if (raf) cancelAnimationFrame(raf);
        card.classList.remove("is-tilting");
        card.style.setProperty("--jp-tilt-x", "0deg");
        card.style.setProperty("--jp-tilt-y", "0deg");
      };

      card.addEventListener("pointermove", update, { passive: true });
      card.addEventListener("pointerleave", reset, { passive: true });
    });
  }

  function initPaperUnfold() {
    if (reduceMotion) return;

    document.addEventListener("click", (event) => {
      const target = event.target.closest(
        ".entry-lane, .practice-lane-card, .home-action-card, .cap-year-card, .cap-subject-card, .cap-mode-option, .mistake-filter, .mistake-subject, .mistake-filter-card, .mistake-subject-card, .guide-shelf-card, .guide-series-card, .guide-book-card, .reader-outline a, .reader-page-card, details > summary, .achievement-filter"
      );
      if (!target) return;

      const card = target.closest("details, .entry-lane, .practice-lane-card, .home-action-card, .cap-year-card, .cap-subject-card, .cap-mode-option, .mistake-filter, .mistake-subject, .mistake-filter-card, .mistake-subject-card, .guide-shelf-card, .guide-series-card, .guide-book-card, .reader-panel, .reader-book-section, .achievement-card") || target;
      card.classList.remove("is-paper-opening");
      void card.offsetWidth;
      card.classList.add("is-paper-opening");
    });
  }

  function initStepFocus() {
    const activeStep = document.querySelector(".cap-progress-pill.is-active");
    if (!activeStep || reduceMotion) return;

    activeStep.animate(
      [
        { transform: "translateY(0)", boxShadow: "0 10px 22px rgba(23,58,94,0.06)" },
        { transform: "translateY(-2px)", boxShadow: "0 16px 34px rgba(23,58,94,0.18)" },
        { transform: "translateY(0)", boxShadow: "0 10px 22px rgba(23,58,94,0.06)" }
      ],
      { duration: 1100, easing: "ease-in-out" }
    );
  }

  function initAchievementFilters() {
    const filters = Array.from(document.querySelectorAll("[data-achievement-filter]"));
    const cards = Array.from(document.querySelectorAll("[data-achievement-card]"));
    if (!filters.length || !cards.length) return;

    filters.forEach((filter) => {
      filter.addEventListener("click", () => {
        const key = filter.dataset.achievementFilter;
        filters.forEach((item) => item.classList.toggle("is-active", item === filter));

        cards.forEach((card, index) => {
          const shouldShow = key === "all" || card.dataset.category === key;
          card.classList.toggle("is-hidden", !shouldShow);
          if (shouldShow && !reduceMotion) {
            card.animate(
              [
                { opacity: 0, transform: "translateY(8px) scale(0.985)" },
                { opacity: 1, transform: "translateY(0) scale(1)" }
              ],
              { duration: 260, delay: Math.min(index, 8) * 22, easing: "cubic-bezier(0.22, 1, 0.36, 1)" }
            );
          }
        });
      });
    });
  }

  function initScrollProgress() {
    const needsProgress = document.querySelector(
      ".practice-question-card, .cap-question-card, .cap-run-card, .mockroom-question, .cap-preview, .achievement-stage"
    );
    if (!needsProgress || document.querySelector(".jp-scroll-progress")) return;

    const progress = document.createElement("div");
    progress.className = "jp-scroll-progress";
    progress.setAttribute("role", "status");
    progress.setAttribute("aria-live", "polite");
    progress.innerHTML = '<small class="jp-scroll-label">卷軸進度</small><span></span>';
    document.body.appendChild(progress);

    const bar = progress.querySelector("span");
    const label = progress.querySelector(".jp-scroll-label");
    const update = () => {
      const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      const value = Math.min(100, Math.max(0, (window.scrollY / max) * 100));
      bar.style.width = `${value}%`;

      const activeRun = document.querySelector(".cap-run-card.is-active, .practice-question-card.is-active, .mockroom-question.is-active");
      const capCards = document.querySelectorAll(".cap-run-card");
      const inlineLabel = document.querySelector("#progress-label");
      if (activeRun && capCards.length) {
        const index = Number(activeRun.dataset.questionIndex || Array.from(capCards).indexOf(activeRun));
        label.textContent = `第 ${index + 1} / ${capCards.length} 題`;
      } else if (inlineLabel && inlineLabel.textContent.trim()) {
        label.textContent = inlineLabel.textContent.trim();
      } else {
        label.textContent = `卷軸 ${Math.round(value)}%`;
      }
    };

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);

    if ("MutationObserver" in window) {
      const observer = new MutationObserver(update);
      observer.observe(document.body, { attributes: true, subtree: true, attributeFilter: ["class"] });
    }
  }

  function initQuestionTransitions() {
    const findActiveQuestion = () =>
      document.querySelector(".cap-run-card.is-active, .practice-question-card.is-active, .mockroom-question.is-active")
      || document.querySelector(".practice-question-card, .cap-question-card, .cap-run-card, .mockroom-question");

    const question = findActiveQuestion();
    if (!question || reduceMotion) return;

    question.classList.add("jp-question-transition");
    document.addEventListener("click", (event) => {
      const control = event.target.closest("a, button");
      if (!control) return;
      const text = (control.textContent || "").trim();
      if (!/(下一題|上一題|交卷|送出|開始|預覽|練習|重練|Next|Previous|Submit)/i.test(text)) return;
      const active = findActiveQuestion();
      if (!active) return;
      active.classList.remove("jp-question-transition");
      void active.offsetWidth;
      active.classList.add("jp-question-transition");
    });

    if ("MutationObserver" in window) {
      const observer = new MutationObserver(() => {
        const active = findActiveQuestion();
        if (!active || active.dataset.jpAnimatedActive === "true") return;
        active.dataset.jpAnimatedActive = "true";
        active.classList.remove("jp-question-transition");
        void active.offsetWidth;
        active.classList.add("jp-question-transition");
      });
      observer.observe(document.body, { subtree: true, attributes: true, attributeFilter: ["class"] });
    }
  }

  function initScoreReveal() {
    if (reduceMotion) return;
    const nodes = document.querySelectorAll(
      ".cap-score-card strong, .mockroom-score, .cap-score, .result-score, .score-number, .review-score strong"
    );
    nodes.forEach((node, index) => {
      node.classList.add("score-reveal");
      node.style.animationDelay = `${Math.min(index, 8) * 70}ms`;
    });
  }

  function initAchievementTrophies() {
    const trophies = Array.from(document.querySelectorAll(".achievement-trophy"));
    if (!trophies.length || reduceMotion) return;

    trophies.forEach((trophy, index) => {
      const card = trophy.closest(".achievement-card");
      const category = card ? card.dataset.category || "daily" : "daily";
      const unlocked = card ? card.classList.contains("is-unlocked") : false;
      const rarity = pickAchievementRarity(category, unlocked, index);

      trophy.dataset.rarity = rarity;
      trophy.classList.add(`achievement-rarity-${rarity}`);
      if (card) card.classList.add(`achievement-rarity-${rarity}`);

      if (!trophy.querySelector(".trophy-orbit")) {
        const orbit = document.createElement("span");
        orbit.className = "trophy-orbit";
        trophy.appendChild(orbit);
      }

      if (!trophy.querySelector(".trophy-stars")) {
        const stars = document.createElement("span");
        stars.className = "trophy-stars";
        for (let i = 0; i < 5; i += 1) {
          const star = document.createElement("em");
          star.style.setProperty("--star-i", i);
          stars.appendChild(star);
        }
        trophy.appendChild(stars);
      }

      trophy.style.animationDelay = `${(index % 8) * -180}ms`;
      trophy.classList.add("is-trophy-ready");
    });
  }

  function pickAchievementRarity(category, unlocked, index) {
    if (!unlocked) return "dormant";
    if (category === "rank" || index % 17 === 0) return "legendary";
    if (category === "seasonal" || category === "companion") return "epic";
    if (category === "shrine" || category === "study") return "rare";
    return "common";
  }

  function initLearningDashboard() {
    if (!document.body.classList.contains("jp-page-home") || document.querySelector(".jp-learning-dashboard")) return;

    const anchor = document.querySelector(".achievement-home-card") || document.querySelector(".home-section") || document.querySelector("main .container > section");
    if (!anchor) return;

    const dashboard = document.createElement("section");
    dashboard.className = "jp-learning-dashboard";
    dashboard.innerHTML = `
      <div class="jp-dashboard-copy">
        <span class="achievement-section-kicker">今日學習儀表板</span>
        <h2>把練習、錯題、講義和 AI 助教收成一張地圖。</h2>
        <p>這裡會先用現有資料做即時摘要，之後可以接成真正的個人化弱點分析與會考衝刺推薦。</p>
        <div class="jp-dashboard-grid">
          <article class="jp-dashboard-card"><span>今日任務</span><strong>3</strong><small>練習、錯題、講義</small></article>
          <article class="jp-dashboard-card"><span>連續修行</span><strong>7</strong><small>天</small></article>
          <article class="jp-dashboard-card"><span>AI 助教</span><strong>3</strong><small>層回答架構</small></article>
        </div>
      </div>
      <div class="jp-radar-card" aria-label="弱點雷達圖示意">
        <strong>弱點雷達</strong>
        <svg viewBox="0 0 220 220" role="img" aria-label="國文、英文、數學、社會、自然的學習雷達">
          <polygon class="radar-grid" points="110,16 197,66 197,154 110,204 23,154 23,66"></polygon>
          <polygon class="radar-grid radar-grid-inner" points="110,52 166,84 166,136 110,168 54,136 54,84"></polygon>
          <polygon class="radar-fill" points="110,34 176,83 161,145 110,182 58,140 46,73"></polygon>
          <text x="110" y="12">國文</text><text x="202" y="70">英文</text><text x="202" y="158">數學</text>
          <text x="110" y="218">社會</text><text x="5" y="158">自然</text><text x="5" y="70">錯題</text>
        </svg>
      </div>
    `;

    anchor.insertAdjacentElement("afterend", dashboard);
    initCountUp();
  }

  function initAiStatusUX() {
    if (!document.body.classList.contains("jp-page-chat")) return;

    const input = document.querySelector("#chat-input, textarea[name='message'], input[name='message']");
    const sendButton = document.querySelector("#send-chat-btn, button[type='submit']");
    const messageList = document.querySelector("#messages, .chat-messages, .messages");
    if (!input || !sendButton || document.querySelector(".jp-ai-status-panel")) return;

    const panel = document.createElement("div");
    panel.className = "jp-ai-status-panel";
    panel.innerHTML = `
      <span class="jp-ai-status-dot"></span>
      <strong>AI 助教待命</strong>
      <small>固定格式：重點、步驟、常見錯誤、小練習。</small>
    `;

    const inputWrap = input.closest("form, .chat-input-area, .input-row, .chat-controls") || input.parentElement;
    if (!inputWrap || !inputWrap.parentElement) return;
    inputWrap.parentElement.insertBefore(panel, inputWrap);

    let slowTimer = null;
    let failTimer = null;

    const setStatus = (state, title, detail) => {
      panel.dataset.state = state;
      panel.querySelector("strong").textContent = title;
      panel.querySelector("small").textContent = detail;
    };

    const armTimers = () => {
      window.clearTimeout(slowTimer);
      window.clearTimeout(failTimer);
      setStatus("thinking", "AI 正在查資料與組織回答", "如果題目有詳解或講義，會先優先參考站內資料。");
      slowTimer = window.setTimeout(() => {
        setStatus("slow", "連線較慢，仍在等待回覆", "若超過太久，可以重試；系統不會讓畫面空白。");
      }, 12000);
      failTimer = window.setTimeout(() => {
        setStatus("fallback", "目前回覆逾時，可重試或改用固定解題模板", "建議稍後再送一次，或改問更短的一題。");
      }, 32000);
    };

    sendButton.addEventListener("click", () => {
      if ((input.value || "").trim()) armTimers();
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && (input.value || "").trim()) armTimers();
    });

    if (messageList && "MutationObserver" in window) {
      const observer = new MutationObserver(() => {
        const newest = messageList.lastElementChild;
        const text = newest ? newest.textContent || "" : "";
        if (/連線錯誤|錯誤|失敗|400|429|500/.test(text)) {
          window.clearTimeout(slowTimer);
          window.clearTimeout(failTimer);
          setStatus("fallback", "AI 連線遇到問題", "已切換成可重試狀態，避免一直卡住。");
        } else if (newest && !newest.matches(".user-message, .message-user")) {
          window.clearTimeout(slowTimer);
          window.clearTimeout(failTimer);
          setStatus("ready", "AI 助教已回覆", "可以追問為什麼錯、要點整理或同類題練習。");
        }
      });
      observer.observe(messageList, { childList: true, subtree: true });
    }
  }

  function initAchievementToast() {
    if (!document.querySelector(".achievement-stage") || reduceMotion) return;
    const unlocked = document.querySelectorAll(".achievement-card.is-unlocked").length;
    if (!unlocked) return;

    const toast = document.createElement("div");
    toast.className = "jp-achievement-toast";
    toast.innerHTML = `<i class="fa-solid fa-trophy"></i><span>已解鎖 ${unlocked} 枚成就，朱印帳正在發光。</span>`;
    document.body.appendChild(toast);
    window.setTimeout(() => toast.classList.add("is-visible"), 420);
    window.setTimeout(() => toast.classList.remove("is-visible"), 5200);
  }
})();
