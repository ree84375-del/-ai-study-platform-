/**
 * Japanese learning hall interactions.
 * Lightweight, dependency-free animations so deployment stays small.
 */

(function () {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  document.addEventListener("DOMContentLoaded", () => {
    document.body.classList.add("jp-loaded");
    initPageTheme();
    mountAmbience();
    initReveal();
    initCountUp();
    initInkRipple();
    initPointerGlow();
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
    const themes = [
      { test: /^\/$/, name: "jp-page-home" },
      { test: /^\/study\/practice\/cap/, name: "jp-page-cap" },
      { test: /^\/study\/practice/, name: "jp-page-practice" },
      { test: /mistakes|wrong/i, name: "jp-page-mistakes" },
      { test: /guide|lecture|library/i, name: "jp-page-guides" },
      { test: /chat/i, name: "jp-page-chat" },
      { test: /admin/i, name: "jp-page-admin" },
      { test: /achievements/i, name: "jp-page-achievements" }
    ];

    const matched = themes.find((theme) => theme.test.test(path));
    document.body.classList.add(matched ? matched.name : "jp-page-default");
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
      ".guide-stat",
      ".guide-card",
      ".guide-summary",
      ".reader-stat",
      ".reader-card",
      ".reader-panel",
      ".reader-section",
      ".reader-page-card",
      ".reader-outline a",
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
          + ", .achievement-stat strong, .admin-achievement-stat strong, .cap-score-card strong, .jp-dashboard-card strong, .jp-radar-card strong, .cap-sidebar-item strong"
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
        ".entry-cta, .entry-ghost, .cap-primary, .cap-ghost, .mockroom-btn, .mockroom-link, .mistake-btn, .mistake-link, .guide-action, .guide-link, .reader-action, .reader-outline a, .achievement-primary, .achievement-filter, .admin-action-btn, .btn, button, .session-item, .command-item, .cap-jump-chip"
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
      ".entry-lane, .cap-year-card, .cap-subject-card, .cap-mode-option, .cap-run-card, .mockroom-card, .mistake-card, .guide-card, .reader-card, .reader-chapter, .reader-page-card, .chat-bubble, .achievement-card, .achievement-home-card, .admin-achievement-card, .jp-dashboard-card"
    );

    glowTargets.forEach((target) => {
      target.addEventListener("pointermove", (event) => {
        const rect = target.getBoundingClientRect();
        target.style.setProperty("--jp-ripple-x", `${event.clientX - rect.left}px`);
        target.style.setProperty("--jp-ripple-y", `${event.clientY - rect.top}px`);
      });
    });
  }

  function initPaperUnfold() {
    if (reduceMotion) return;

    document.addEventListener("click", (event) => {
      const target = event.target.closest(
        ".entry-lane, .cap-year-card, .cap-subject-card, .cap-mode-option, .mistake-filter, .mistake-subject, .reader-outline a, details > summary, .achievement-filter"
      );
      if (!target) return;

      const card = target.closest("details, .entry-lane, .cap-year-card, .cap-subject-card, .cap-mode-option, .mistake-filter, .mistake-subject, .reader-panel, .achievement-card") || target;
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
      trophy.style.animationDelay = `${(index % 8) * -180}ms`;
      trophy.classList.add("is-trophy-ready");
    });
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
