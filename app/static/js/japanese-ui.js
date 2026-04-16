/**
 * Japanese learning hall interactions.
 * Lightweight, dependency-free animations so deployment stays small.
 */

(function () {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  document.addEventListener("DOMContentLoaded", () => {
    document.body.classList.add("jp-loaded");
    mountAmbience();
    initReveal();
    initCountUp();
    initInkRipple();
    initPointerGlow();
    initStepFocus();
  });

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

  function initReveal() {
    const selectors = [
      ".entry-stat",
      ".entry-lane",
      ".entry-preview",
      ".entry-step-card",
      ".cap-stat",
      ".cap-year-card",
      ".cap-subject-card",
      ".cap-mode-option",
      ".cap-preview",
      ".mockroom-stat",
      ".mockroom-card",
      ".mockroom-question",
      ".mistake-stat",
      ".mistake-filter",
      ".mistake-subject",
      ".mistake-card",
      ".guide-stat",
      ".guide-card",
      ".guide-summary",
      ".reader-stat",
      ".reader-card",
      ".reader-panel",
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

    numericNodes.forEach(({ node }) => observer.observe(node));
  }

  function initInkRipple() {
    document.addEventListener("click", (event) => {
      const target = event.target.closest(
        ".entry-cta, .entry-ghost, .cap-primary, .cap-ghost, .mockroom-btn, .mockroom-link, .mistake-btn, .mistake-link, .guide-action, .guide-link, .reader-action, .btn, button"
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
      ".entry-lane, .cap-year-card, .cap-subject-card, .cap-mode-option, .mockroom-card, .mistake-card, .guide-card"
    );

    glowTargets.forEach((target) => {
      target.addEventListener("pointermove", (event) => {
        const rect = target.getBoundingClientRect();
        target.style.setProperty("--jp-ripple-x", `${event.clientX - rect.left}px`);
        target.style.setProperty("--jp-ripple-y", `${event.clientY - rect.top}px`);
      });
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
})();
