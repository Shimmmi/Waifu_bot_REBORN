/**
 * Waifu REBORN — onboarding tutorial (spotlight + waifu narrator).
 * Loaded before app.js; integrates via WaifuApp.Tutorial.maybeRun().
 */
(function () {
  "use strict";

  const TUTORIAL_IMAGE_BASE = "/static/game/ui/tutorial/waifu-";
  const SESSION_SEEN_PREFIX = "waifu_tutorial_seen_";

  const TUTORIAL_FLOWS = {
    intro: {
      page: "profile",
      steps: [
        {
          id: "welcome",
          target: null,
          image: "greeting",
          text: "Привет! Я твоя проводница в мире Waifu REBORN. Сейчас покажу, где что находится — это займёт пару минут.",
        },
        {
          id: "portrait",
          target: "[data-tutorial='profile-portrait']",
          image: "explaining",
          text: "Здесь твоя основная вайфу: имя, уровень, здоровье и опыт. Следи за полосками HP и XP — они обновляются после боёв.",
        },
        {
          id: "stats",
          target: "[data-tutorial='profile-stats']",
          image: "thinking",
          text: "Основные характеристики влияют на урон, защиту и шансы в бою. Очки характеристик (ОХ) можно распределять при повышении уровня.",
        },
        {
          id: "equip",
          target: "[data-tutorial='profile-equipment']",
          image: "explaining",
          text: "Во вкладке «Инвентарь» — экипировка и сумка. Надевай предметы в слоты, продавай лишнее в магазине.",
          beforeShow: () => {
            if (window.WaifuApp && typeof window.WaifuApp.switchProfileTab === "function") {
              window.WaifuApp.switchProfileTab("inventory");
            }
          },
        },
        {
          id: "nav_dungeons",
          target: ".nav.basement [data-page='dungeons']",
          image: "excited",
          text: "Подземелья — главный источник золота, опыта и лута. Одиночные, экспедиции и групповые походы.",
        },
        {
          id: "nav_shop",
          target: ".nav.basement [data-page='shop']",
          image: "explaining",
          text: "Магазин: покупка снаряжения, продажа добычи и заточка у кузнеца.",
        },
        {
          id: "nav_tavern",
          target: ".nav.basement [data-page='tavern']",
          image: "excited",
          text: "Таверна — найми наёмниц в отряд, лечи раненых и усиливай состав.",
        },
        {
          id: "nav_caravan",
          target: ".nav.basement [data-page='caravan']",
          image: "explaining",
          text: "Караван перевозит тебя между актами. Новые акты — новые подземелья и более редкий лут.",
        },
        {
          id: "nav_guild",
          target: ".nav.basement [data-page='guild']",
          image: "explaining",
          text: "Гильдия — совместные рейды, вклад в развитие и общий чат с соклановцами.",
        },
        {
          id: "nav_training",
          target: ".nav.basement [data-page='training']",
          image: "thinking",
          text: "Тренировочный зал — дерево пассивных навыков. Очки навыков получаешь за уровни вайфу.",
        },
        {
          id: "nav_menu",
          target: ".nav.basement [data-page='menu']",
          image: "explaining",
          text: "Главное меню — настройки, информация и повторное прохождение обучения.",
        },
        {
          id: "finish",
          target: null,
          image: "waving",
          text: "Отлично! Теперь ты знаешь базу. За прохождение обучения получишь стартовое золото. Удачи в приключениях!",
        },
      ],
    },
    shop: {
      page: "shop",
      steps: [
        {
          id: "shop_welcome",
          target: null,
          image: "greeting",
          text: "Добро пожаловать в магазин! Здесь торгуешь с местным купцом текущего акта.",
        },
        {
          id: "shop_tabs",
          target: "[data-tutorial='shop-tabs']",
          image: "explaining",
          text: "Четыре вкладки: Купить — снаряжение, Продать — из инвентаря, Испытать удачу — случайный предмет за золото, Заточка — улучшение предметов.",
        },
        {
          id: "shop_merchant",
          target: "[data-tutorial='shop-merchant']",
          image: "excited",
          text: "Нажми на торговца — иногда он даёт совет или подсказку по акту. Ассортимент обновляется по мере прогресса.",
        },
      ],
    },
    tavern: {
      page: "tavern",
      steps: [
        {
          id: "tavern_welcome",
          target: null,
          image: "greeting",
          text: "Таверна — место отдыха и найма. Сильный отряд наёмниц помогает в экспедициях: больше силы отряда — выше шанс успеха в длительных походах.",
        },
        {
          id: "tavern_tabs",
          target: "[data-tutorial='tavern-tabs']",
          image: "explaining",
          text: "Вкладки: Найм — новые наёмницы, Отряд — состав, Лечение и Улучшения.",
        },
        {
          id: "tavern_hire",
          target: "[data-tutorial='tavern-hire-btn']",
          image: "excited",
          text: "Кнопка «Нанять» внизу экрана — за золото получишь случайную наёмницу со случайной редкостью. Раса, класс и перки определяются автоматически.",
        },
      ],
    },
    dungeons: {
      page: "dungeons",
      steps: [
        {
          id: "dungeons_welcome",
          target: null,
          image: "greeting",
          text: "Подземелья — сердце прогресса. Здесь ты фармишь золото, опыт и экипировку.",
        },
        {
          id: "dungeons_tabs",
          target: "[data-tutorial='dungeon-tabs']",
          image: "explaining",
          text: "Одиночные — соло-прогресс, Экспедиции — длительные походы с наградами, Групповые — кооп с другими игроками.",
        },
        {
          id: "dungeons_list",
          target: "[data-tutorial='dungeon-list']",
          image: "excited",
          text: "Выбери подходящий данж по уровню и тегам. Начни с простых — они быстрее и безопаснее для новичка.",
        },
      ],
    },
    caravan: {
      page: "caravan",
      steps: [
        {
          id: "caravan_welcome",
          target: null,
          image: "greeting",
          text: "Караван ведёт между актами мира. Каждый акт — новая локация, монстры и магазин.",
        },
        {
          id: "caravan_map",
          target: "[data-tutorial='caravan-map']",
          image: "explaining",
          text: "Нажми на точку на карте, чтобы увидеть стоимость переезда. Новые акты открываются по мере прохождения.",
        },
      ],
    },
    guild: {
      page: "guild",
      steps: [
        {
          id: "guild_welcome",
          target: null,
          image: "greeting",
          text: "Гильдия объединяет игроков. Вступи или создай свою — получишь доступ к рейдам и общим бонусам.",
        },
        {
          id: "guild_tabs",
          target: "[data-tutorial='guild-tabs']",
          image: "explaining",
          text: "Вкладки: участники, навыки, активность и рейды. Вклад в гильдию повышает её уровень.",
        },
      ],
    },
    training: {
      page: "training",
      steps: [
        {
          id: "training_welcome",
          target: null,
          image: "greeting",
          text: "Тренировочный зал — пассивные навыки. Они усиливают вайфу без смены экипировки.",
        },
        {
          id: "training_points",
          target: "[data-tutorial='training-points']",
          image: "thinking",
          text: "Свободные очки навыков тратятся на узлы дерева. Каждая ветка даёт разные бонусы.",
        },
        {
          id: "training_tree",
          target: "[data-tutorial='training-tree']",
          image: "explaining",
          text: "Нажми на узел, чтобы прокачать навык. Некоторые требуют предварительное изучение соседних.",
        },
      ],
    },
  };

  const state = {
    active: false,
    flowId: null,
    stepIndex: 0,
    steps: [],
    root: null,
    maskRect: null,
    ring: null,
    bubble: null,
    waifuImg: null,
    progressEl: null,
    textEl: null,
    hintEl: null,
    closeStepBtn: null,
    rewardModal: null,
    resizeObserver: null,
    onBackButton: null,
    tutorialState: null,
  };

  function tutorialApiFetch(path, options = {}) {
    const opts = { ...options, headers: { ...(options.headers || {}) } };
    if (opts.body && typeof opts.body === "object") {
      opts.body = JSON.stringify(opts.body);
      opts.headers["Content-Type"] = "application/json";
    }
    if (typeof window.apiFetch === "function") {
      return window.apiFetch(path, opts);
    }
    const initData =
      (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) ||
      new URLSearchParams(window.location.search).get("initData") ||
      "";
    if (initData) opts.headers["X-Telegram-Init-Data"] = initData;
    const devPid = new URLSearchParams(window.location.search).get("devPlayerId");
    if (devPid) opts.headers["X-Player-Id"] = devPid;
    return fetch(`/api${path}`, opts).then(async (res) => {
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || res.statusText);
      }
      return res.json();
    });
  }

  function showToast(message, type) {
    if (typeof window.showToast === "function") window.showToast(message, type);
    else if (window.WaifuApp && typeof window.WaifuApp.showToast === "function") {
      window.WaifuApp.showToast(message, type);
    }
  }

  function normalizeTutorialState(raw) {
    if (!raw || typeof raw !== "object") {
      return { version: 1, completed: {}, skipped: false, intro_reward_claimed: false };
    }
    return {
      version: Number(raw.version) || 1,
      completed: raw.completed && typeof raw.completed === "object" ? raw.completed : {},
      skipped: Boolean(raw.skipped),
      intro_reward_claimed: Boolean(raw.intro_reward_claimed),
    };
  }

  function isFlowCompleted(flowId, tutorialState) {
    const ts = normalizeTutorialState(tutorialState);
    if (ts.skipped) return true;
    return Boolean(ts.completed && ts.completed[flowId]);
  }

  function markSessionSeen(flowId) {
    try {
      sessionStorage.setItem(SESSION_SEEN_PREFIX + flowId, "1");
    } catch (e) {
      /* ignore */
    }
  }

  function wasSeenThisSession(flowId) {
    try {
      return sessionStorage.getItem(SESSION_SEEN_PREFIX + flowId) === "1";
    } catch (e) {
      return false;
    }
  }

  function ensureDom() {
    if (state.root) return;

    const root = document.createElement("div");
    root.className = "tutorial-root";
    root.hidden = true;
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-label", "Обучение");
    root.innerHTML = `
      <svg class="tutorial-overlay-svg" aria-hidden="true">
        <defs>
          <mask id="tutorial-spotlight-mask">
            <rect x="0" y="0" width="100%" height="100%" fill="white" />
            <rect class="tutorial-hole" x="0" y="0" width="0" height="0" rx="12" ry="12" fill="black" />
          </mask>
        </defs>
        <rect class="tutorial-dim" x="0" y="0" width="100%" height="100%" mask="url(#tutorial-spotlight-mask)" />
      </svg>
      <div class="tutorial-spotlight-ring" aria-hidden="true"></div>
      <div class="tutorial-bubble">
        <button type="button" class="tutorial-step-close" aria-label="Завершить обучение" title="Завершить обучение">×</button>
        <div class="tutorial-progress"></div>
        <div class="tutorial-row">
          <div class="tutorial-dialog">
            <p class="tutorial-text"></p>
          </div>
          <div class="tutorial-waifu-wrap">
            <img class="tutorial-waifu" src="" alt="" decoding="async" />
          </div>
        </div>
        <div class="tutorial-hint">Нажмите, чтобы продолжить</div>
      </div>
    `;

    const rewardModal = document.createElement("div");
    rewardModal.className = "tutorial-reward-modal";
    rewardModal.hidden = true;
    rewardModal.innerHTML = `
      <div class="tutorial-reward-panel">
        <h3>Обучение пройдено!</h3>
        <p class="tutorial-reward-text"></p>
        <button type="button" class="tutorial-btn tutorial-btn--primary tutorial-reward-ok">Отлично</button>
      </div>
    `;

    document.body.appendChild(root);
    document.body.appendChild(rewardModal);

    state.root = root;
    state.maskRect = root.querySelector(".tutorial-hole");
    state.ring = root.querySelector(".tutorial-spotlight-ring");
    state.bubble = root.querySelector(".tutorial-bubble");
    state.waifuImg = root.querySelector(".tutorial-waifu");
    state.progressEl = root.querySelector(".tutorial-progress");
    state.textEl = root.querySelector(".tutorial-text");
    state.hintEl = root.querySelector(".tutorial-hint");
    state.closeStepBtn = root.querySelector(".tutorial-step-close");
    state.rewardModal = rewardModal;

    state.closeStepBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      skipAll();
    });
    state.bubble.addEventListener("click", (e) => {
      if (e.target.closest(".tutorial-step-close")) return;
      advanceStep();
    });
    root.addEventListener("click", (e) => {
      if (e.target === root || e.target.classList.contains("tutorial-dim")) {
        advanceStep();
      }
    });
    rewardModal.querySelector(".tutorial-reward-ok").addEventListener("click", () => {
      rewardModal.hidden = true;
    });

    window.addEventListener("resize", scheduleLayout, { passive: true });
    window.addEventListener("scroll", scheduleLayout, { passive: true, capture: true });
  }

  let layoutRaf = 0;
  function scheduleLayout() {
    if (!state.active) return;
    cancelAnimationFrame(layoutRaf);
    layoutRaf = requestAnimationFrame(() => renderCurrentStep(false));
  }

  function getTargetEl(step) {
    if (!step || !step.target) return null;
    try {
      return document.querySelector(step.target);
    } catch (e) {
      return null;
    }
  }

  function layoutSpotlight(targetEl) {
    const pad = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    if (!targetEl) {
      state.root.classList.add("is-no-target");
      if (state.maskRect) {
        state.maskRect.setAttribute("width", "0");
        state.maskRect.setAttribute("height", "0");
      }
      state.ring.style.display = "none";
      state.bubble.classList.add("is-centered");
      state.bubble.style.left = "";
      state.bubble.style.top = "";
      return;
    }

    state.root.classList.remove("is-no-target");
    state.bubble.classList.remove("is-centered");

    const rect = targetEl.getBoundingClientRect();
    const x = Math.max(0, rect.left - pad);
    const y = Math.max(0, rect.top - pad);
    const w = Math.min(vw - x, rect.width + pad * 2);
    const h = Math.min(vh - y, rect.height + pad * 2);

    if (state.maskRect) {
      state.maskRect.setAttribute("x", String(x));
      state.maskRect.setAttribute("y", String(y));
      state.maskRect.setAttribute("width", String(w));
      state.maskRect.setAttribute("height", String(h));
    }

    state.ring.style.display = "block";
    state.ring.style.left = `${x}px`;
    state.ring.style.top = `${y}px`;
    state.ring.style.width = `${w}px`;
    state.ring.style.height = `${h}px`;

    const bubbleRect = state.bubble.getBoundingClientRect();
    const bubbleW = bubbleRect.width || 280;
    const bubbleH = bubbleRect.height || 160;
    const gap = 14;
    const margin = 8;

    const spaceBelow = vh - (y + h) - gap - margin;
    const spaceAbove = y - gap - margin;

    let bubbleTop;
    if (spaceBelow >= bubbleH && spaceBelow >= spaceAbove) {
      bubbleTop = y + h + gap;
    } else if (spaceAbove >= bubbleH) {
      bubbleTop = y - bubbleH - gap;
    } else {
      const targetCenterY = y + h / 2;
      if (targetCenterY > vh / 2) {
        bubbleTop = margin;
      } else {
        bubbleTop = vh - bubbleH - margin;
      }
    }

    const bubbleLeft = Math.max(
      margin,
      Math.min(x + w / 2 - bubbleW / 2, vw - bubbleW - margin),
    );

    state.bubble.style.left = `${bubbleLeft}px`;
    state.bubble.style.top = `${bubbleTop}px`;
    state.bubble.style.transform = "";

    try {
      targetEl.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    } catch (e) {
      /* ignore */
    }
  }

  function renderCurrentStep(scrollTarget) {
    const step = state.steps[state.stepIndex];
    if (!step) return;

    if (typeof step.beforeShow === "function") {
      try {
        step.beforeShow();
      } catch (e) {
        console.warn("tutorial beforeShow failed:", e);
      }
    }

    const imageKey = step.image || "explaining";
    state.waifuImg.src = `${TUTORIAL_IMAGE_BASE}${imageKey}.webp`;
    state.waifuImg.alt = "";
    state.progressEl.textContent = `${state.stepIndex + 1} / ${state.steps.length}`;
    state.textEl.textContent = step.text || "";

    const isLast = state.stepIndex >= state.steps.length - 1;
    if (state.hintEl) {
      state.hintEl.textContent = isLast
        ? "Нажмите, чтобы завершить"
        : "Нажмите, чтобы продолжить";
    }

    const targetEl = getTargetEl(step);
    if (scrollTarget !== false && targetEl) {
      try {
        targetEl.scrollIntoView({ block: "center", inline: "nearest", behavior: "auto" });
      } catch (e) {
        /* ignore */
      }
    }
    layoutSpotlight(targetEl);

    if (state.resizeObserver) {
      state.resizeObserver.disconnect();
    }
    if (targetEl && typeof ResizeObserver !== "undefined") {
      state.resizeObserver = new ResizeObserver(scheduleLayout);
      state.resizeObserver.observe(targetEl);
    }
  }

  function setupTelegramBackButton() {
    const tg = window.Telegram && window.Telegram.WebApp;
    if (!tg || !tg.BackButton) return;
    state.onBackButton = () => {
      if (state.stepIndex > 0) {
        state.stepIndex -= 1;
        renderCurrentStep();
      } else {
        skipAll();
      }
    };
    try {
      tg.BackButton.show();
      tg.BackButton.onClick(state.onBackButton);
    } catch (e) {
      /* ignore */
    }
  }

  function teardownTelegramBackButton() {
    const tg = window.Telegram && window.Telegram.WebApp;
    if (!tg || !tg.BackButton || !state.onBackButton) return;
    try {
      tg.BackButton.offClick(state.onBackButton);
      tg.BackButton.hide();
    } catch (e) {
      /* ignore */
    }
    state.onBackButton = null;
  }

  function open(flowId, tutorialState) {
    const flow = TUTORIAL_FLOWS[flowId];
    if (!flow || !Array.isArray(flow.steps) || !flow.steps.length) return false;

    ensureDom();
    state.active = true;
    state.flowId = flowId;
    state.stepIndex = 0;
    state.steps = flow.steps;
    state.tutorialState = normalizeTutorialState(tutorialState);
    markSessionSeen(flowId);

    state.root.hidden = false;
    document.body.classList.add("tutorial-active");
    setupTelegramBackButton();
    renderCurrentStep();
    return true;
  }

  function close() {
    if (!state.root) return;
    state.active = false;
    state.root.hidden = true;
    document.body.classList.remove("tutorial-active");
    teardownTelegramBackButton();
    if (state.resizeObserver) {
      state.resizeObserver.disconnect();
      state.resizeObserver = null;
    }
  }

  async function completeFlow(flowId) {
    try {
      const data = await tutorialApiFetch("/tutorial/complete", {
        method: "POST",
        body: { step_id: flowId },
      });
      if (data && data.tutorial) {
        state.tutorialState = normalizeTutorialState(data.tutorial);
      }
      if (flowId === "intro" && data && data.gold_reward) {
        showRewardModal(data.gold_reward);
        if (typeof window.loadProfile === "function") {
          window.loadProfile().catch(() => {});
        }
      }
      return data;
    } catch (e) {
      console.warn("tutorial complete failed:", e);
      return null;
    }
  }

  function showRewardModal(gold) {
    ensureDom();
    const textEl = state.rewardModal.querySelector(".tutorial-reward-text");
    if (textEl) {
      textEl.textContent = `Вы получили 🪙 ${gold} золота за прохождение обучения!`;
    }
    state.rewardModal.hidden = false;
  }

  async function finishFlow() {
    const flowId = state.flowId;
    close();
    if (flowId) await completeFlow(flowId);
  }

  function advanceStep() {
    if (!state.active) return;
    if (state.stepIndex >= state.steps.length - 1) {
      finishFlow();
      return;
    }
    state.stepIndex += 1;
    renderCurrentStep();
  }

  async function skipAll() {
    if (!confirm("Пропустить всё обучение? Подсказки больше не будут показываться автоматически.")) {
      return;
    }
    close();
    try {
      const data = await tutorialApiFetch("/tutorial/skip", { method: "POST" });
      if (data) state.tutorialState = normalizeTutorialState(data);
    } catch (e) {
      console.warn("tutorial skip failed:", e);
    }
  }

  function resolveFlowForPage(page, tutorialState, forced) {
    if (forced && TUTORIAL_FLOWS[forced]) {
      const flow = TUTORIAL_FLOWS[forced];
      if (flow.page === page) return forced;
      return null;
    }
    if (page === "index" || page === "settings" || page === "waifu_generator" || page === "battle" || page === "mail") {
      return null;
    }
    const ts = normalizeTutorialState(tutorialState);
    if (ts.skipped) return null;

    if (page === "profile" && !ts.completed.intro && !wasSeenThisSession("intro")) {
      return "intro";
    }

    for (const flowId of Object.keys(TUTORIAL_FLOWS)) {
      if (flowId === "intro") continue;
      const flow = TUTORIAL_FLOWS[flowId];
      if (flow.page !== page) continue;
      if (ts.completed[flowId]) continue;
      if (wasSeenThisSession(flowId)) continue;
      return flowId;
    }
    return null;
  }

  function maybeRun(page, tutorialState, forced) {
    if (state.active) return;
    const flowId = resolveFlowForPage(page, tutorialState, forced);
    if (!flowId) return;

    const start = () => {
      if (state.active) return;
      open(flowId, tutorialState);
    };

    const delay = flowId === "intro" ? 600 : 400;
    if (document.readyState === "complete") {
      setTimeout(start, delay);
    } else {
      window.addEventListener("load", () => setTimeout(start, delay), { once: true });
    }
  }

  async function replay() {
    if (!confirm("Сбросить прогресс обучения и пройти его заново?")) return;
    try {
      await tutorialApiFetch("/tutorial/reset", { method: "POST" });
      try {
        for (const flowId of Object.keys(TUTORIAL_FLOWS)) {
          sessionStorage.removeItem(SESSION_SEEN_PREFIX + flowId);
        }
      } catch (e) {
        /* ignore */
      }
      window.location.href = "./profile.html?tutorial=intro";
    } catch (e) {
      showToast("Не удалось сбросить обучение: " + (e && e.message ? e.message : e), "error");
    }
  }

  window.WaifuApp = window.WaifuApp || {};
  window.WaifuApp.Tutorial = {
    maybeRun,
    replay,
    open,
    close,
    skipAll,
    TUTORIAL_FLOWS,
  };
})();
