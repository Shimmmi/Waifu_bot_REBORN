/**
 * Waifu REBORN — onboarding tutorial (spotlight + soft-lock + waifu narrator).
 * Loaded before app.js; integrates via WaifuApp.Tutorial.maybeRun().
 */
(function () {
  "use strict";

  const TUTORIAL_IMAGE_BASE = "/static/game/ui/tutorial/waifu-";
  const SESSION_SEEN_PREFIX = "waifu_tutorial_seen_";
  const PAD = 8;

  /** @type {Record<string, any>} */
  const flowCtx = {
    shop: null,
    boughtItemId: null,
  };

  function switchShop(tab) {
    if (window.WaifuApp && typeof window.WaifuApp.switchShopTab === "function") {
      window.WaifuApp.switchShopTab(tab);
    } else if (window.ShopPage && typeof window.ShopPage.switchTab === "function") {
      window.ShopPage.switchTab(tab);
    }
  }

  function switchSmith(sub) {
    if (window.ShopPage && typeof window.ShopPage.switchSmithSubTab === "function") {
      window.ShopPage.switchSmithSubTab(sub);
    }
  }

  function markTarget(selectorOrEl, attrValue) {
    clearMarkedTargets(attrValue);
    const el =
      typeof selectorOrEl === "string" ? document.querySelector(selectorOrEl) : selectorOrEl;
    if (el) el.setAttribute("data-tutorial-target", attrValue || "active");
    return el;
  }

  function clearMarkedTargets(attrValue) {
    const sel = attrValue
      ? `[data-tutorial-target="${attrValue}"]`
      : "[data-tutorial-target]";
    document.querySelectorAll(sel).forEach((el) => el.removeAttribute("data-tutorial-target"));
  }

  async function provisionShopKit() {
    if (flowCtx.shop) return flowCtx.shop;
    try {
      const data = await tutorialApiFetch("/tutorial/provision", {
        method: "POST",
        body: { kit_id: "shop_loop" },
      });
      flowCtx.shop = data || {};
      if (data && data.tutorial) {
        state.tutorialState = normalizeTutorialState(data.tutorial);
      }
      if (typeof window.loadProfile === "function") {
        await window.loadProfile({ lite: true }).catch(() => {});
      }
      if (typeof window.loadShop === "function") {
        const act = window.shopState?.act || 1;
        await window.loadShop(act).catch(() => {});
      }
      return flowCtx.shop;
    } catch (e) {
      console.warn("tutorial provision failed:", e);
      flowCtx.shop = {};
      return flowCtx.shop;
    }
  }

  function waitForShopBuyCards(timeoutMs) {
    const limit = typeof timeoutMs === "number" ? timeoutMs : 800;
    return new Promise((resolve) => {
      const start = Date.now();
      const tick = () => {
        const cards = document.querySelectorAll("#shop-buy-grid .shop-item-card:not(.empty)");
        if (cards.length) {
          resolve(true);
          return;
        }
        if (Date.now() - start >= limit) {
          resolve(false);
          return;
        }
        setTimeout(tick, 50);
      };
      tick();
    });
  }

  function markCheapestBuyOffer() {
    clearMarkedTargets("shop-buy");
    const hintSlot = flowCtx.shop?.buy_hint?.slot;
    let card = null;
    if (hintSlot != null) {
      card = document.querySelector(
        `#shop-buy-grid .shop-item-card[data-shop-slot="${hintSlot}"]:not(.empty)`,
      );
      // Sold or missing hint card → fall through to cheapest unsold.
      if (card) {
        const slot = Number(card.dataset.shopSlot);
        const offers = window.shopState?.offers || [];
        const offer = offers.find((o, idx) => {
          const s = Number(o.slot || o.offer_slot || o.shop_slot || idx + 1);
          return s === slot;
        });
        if (offer && offer.sold) card = null;
      }
    }
    if (!card) {
      const cards = Array.from(
        document.querySelectorAll("#shop-buy-grid .shop-item-card:not(.empty)"),
      );
      let best = null;
      let bestPrice = Infinity;
      for (const c of cards) {
        const slot = Number(c.dataset.shopSlot);
        const offers = window.shopState?.offers || [];
        const offer = offers.find((o, idx) => {
          const s = Number(o.slot || o.offer_slot || o.shop_slot || idx + 1);
          return s === slot && !o.sold;
        });
        const price = Number(offer?.price);
        if (offer && Number.isFinite(price) && price < bestPrice) {
          bestPrice = price;
          best = c;
        }
      }
      card = best;
    }
    if (card) card.setAttribute("data-tutorial-target", "shop-buy");
    return card;
  }

  async function provisionPaperdollKit() {
    try {
      const data = await tutorialApiFetch("/tutorial/provision", {
        method: "POST",
        body: { kit_id: "paperdoll" },
      });
      if (data && data.tutorial) {
        state.tutorialState = normalizeTutorialState(data.tutorial);
      }
      if (typeof window.loadProfile === "function") {
        await window.loadProfile({ lite: true }).catch(() => {});
      }
      return data || {};
    } catch (e) {
      console.warn("tutorial paperdoll provision failed:", e);
      return {};
    }
  }

  function ensureProfileExpandedGear() {
    const gear = document.getElementById("profile-gear");
    if (gear && gear.classList.contains("is-expanded")) return;
    if (window.WaifuApp && typeof window.WaifuApp.toggleProfileInventoryMode === "function") {
      window.WaifuApp.toggleProfileInventoryMode();
    } else if (typeof window.toggleProfileInventoryMode === "function") {
      window.toggleProfileInventoryMode();
    }
  }

  function guildTabsVisible() {
    const tabs = document.querySelector("[data-tutorial='guild-tabs']");
    if (!tabs) return false;
    try {
      return window.getComputedStyle(tabs).display !== "none";
    } catch (e) {
      return tabs.style.display !== "none";
    }
  }

  function switchGuildTutorialTab(name) {
    if (window.WaifuApp && typeof window.WaifuApp.switchGuildTab === "function") {
      window.WaifuApp.switchGuildTab(name);
      return;
    }
    const btn = document.querySelector(`[data-guild-tab-btn="${name}"]`);
    if (btn) btn.click();
  }

  function switchTrainingTutorialTab(key) {
    const tab = document.querySelector(`.passive-tab[data-training-tab="${key}"]`);
    if (tab) {
      tab.click();
      return;
    }
    if (window.WaifuApp && typeof window.WaifuApp.switchTrainingTab === "function") {
      window.WaifuApp.switchTrainingTab(key);
    }
  }

  function clearHiddenCaravanPins() {
    const list = state.hiddenCaravanPins || [];
    list.forEach((entry) => {
      if (!entry || !entry.el) return;
      try {
        if (entry.visibility != null && entry.visibility !== "") {
          entry.el.style.visibility = entry.visibility;
        } else {
          entry.el.style.removeProperty("visibility");
        }
      } catch (e) {
        /* ignore */
      }
    });
    state.hiddenCaravanPins = [];
  }

  function hideOtherCaravanPins(targetEl) {
    clearHiddenCaravanPins();
    const keep = targetEl && targetEl.closest ? targetEl.closest(".caravan-pin") : null;
    document.querySelectorAll(".caravan-pin").forEach((pin) => {
      if (keep && pin === keep) return;
      state.hiddenCaravanPins.push({
        el: pin,
        visibility: pin.style.visibility || "",
      });
      pin.style.visibility = "hidden";
    });
  }

  function elevateTutorialRoot() {
    if (!state.root) return;
    try {
      document.body.appendChild(state.root);
    } catch (e) {
      /* ignore */
    }
    state.root.style.zIndex = "100000";
  }

  function resetTutorialRootZ() {
    if (!state.root) return;
    state.root.style.removeProperty("z-index");
  }

  function waitForLibTabsReady(timeoutMs) {
    const limit = typeof timeoutMs === "number" ? timeoutMs : 1500;
    return new Promise((resolve) => {
      const start = Date.now();
      const tick = () => {
        const tab = document.querySelector("#lib-tabs .lib-tab");
        if (tab) {
          try {
            const r = tab.getBoundingClientRect();
            if (r.height > 0 && r.width > 0) {
              resolve(true);
              return;
            }
          } catch (e) {
            /* ignore */
          }
        }
        if (Date.now() - start >= limit) {
          resolve(false);
          return;
        }
        setTimeout(tick, 40);
      };
      tick();
    });
  }

  function applyLibraryModalTutorialZ() {
    const modal = document.getElementById("library-modal");
    if (!modal) return;
    if (!modal.dataset.tutorialPrevZ) {
      modal.dataset.tutorialPrevZ = modal.style.zIndex || "";
    }
    modal.style.zIndex = "98900";
    modal.classList.add("lib-overlay--tutorial-lock");
  }

  function clearLibraryModalTutorialZ() {
    const modal = document.getElementById("library-modal");
    if (!modal) return;
    modal.classList.remove("lib-overlay--tutorial-lock");
    if (Object.prototype.hasOwnProperty.call(modal.dataset, "tutorialPrevZ")) {
      const prev = modal.dataset.tutorialPrevZ;
      delete modal.dataset.tutorialPrevZ;
      if (prev) modal.style.zIndex = prev;
      else modal.style.removeProperty("z-index");
    }
  }

  async function ensureLibraryOpenForTutorial(tab) {
    const tabId = tab || "bestiary";
    try {
      if (window.WaifuApp && typeof window.WaifuApp.openLibrary === "function") {
        await window.WaifuApp.openLibrary({ tab: tabId });
      }
    } catch (e) {
      console.warn("tutorial openLibrary failed:", e);
    }
    await waitForLibTabsReady(1500);
    applyLibraryModalTutorialZ();
    if (window.WaifuApp && typeof window.WaifuApp.librarySwitchTab === "function") {
      try {
        await window.WaifuApp.librarySwitchTab(tabId);
      } catch (e) {
        /* ignore */
      }
    }
    scheduleLayout();
  }

  function forceCloseLibrary() {
    clearLibraryModalTutorialZ();
    try {
      if (window.WaifuApp && typeof window.WaifuApp.closeLibrary === "function") {
        window.WaifuApp.closeLibrary({ force: true });
      }
    } catch (e) {
      /* ignore */
    }
  }

  function openPaperdollMenuForTutorial() {
    ensureProfileExpandedGear();
    try {
      const menu = document.getElementById("profile-paperdoll-menu");
      if (menu) menu.style.display = "block";
    } catch (e) {
      /* ignore */
    }
  }

  function markBoughtSmithItem() {
    clearMarkedTargets("shop-smith-item");
    const id = flowCtx.boughtItemId || flowCtx.shop?.bought_item_id;
    if (!id) {
      const first = document.querySelector("#shop-smith-pick-grid .shop-smith-pick-card[data-id]");
      if (first) first.setAttribute("data-tutorial-target", "shop-smith-item");
      return first;
    }
    const card = document.querySelector(
      `#shop-smith-pick-grid .shop-smith-pick-card[data-id="${id}"]`,
    );
    if (card) card.setAttribute("data-tutorial-target", "shop-smith-item");
    return card;
  }

  function markSellJunk() {
    clearMarkedTargets("shop-sell-junk");
    const id = flowCtx.shop?.sell_item_id;
    if (!id) return null;
    const card = document.querySelector(`#shop-sell-grid .shop-sell-card[data-id="${id}"]`);
    if (card) card.setAttribute("data-tutorial-target", "shop-sell-junk");
    return card;
  }

  function markEquipBagItem() {
    clearMarkedTargets("equip-item");
    const btn = document.querySelector(
      "#profile-inventory .profile-inv-item:not(.empty):not(.profile-inv-placeholder)",
    );
    if (btn) btn.setAttribute("data-tutorial-target", "equip-item");
    return btn;
  }

  const TUTORIAL_FLOWS = {
    waifu_gen: {
      page: "waifu_generator",
      steps: [
        {
          id: "wg_welcome",
          target: null,
          image: "greeting",
          text: "Создадим твою основную вайфу. Сначала имя, затем раса и класс — это определит стартовые характеристики и пассивные навыки.",
        },
        {
          id: "wg_name",
          target: "[data-tutorial='waifu-gen-name']",
          image: "explaining",
          text: "Введи имя — оно отобразится в профиле и сообщениях боёв.",
        },
        {
          id: "wg_race",
          target: "[data-tutorial='waifu-gen-race']",
          image: "excited",
          text: "Раса задаёт стартовые бонусы характеристик и уникальный расовый пассив. Иконки слева направо: Человек, Эльф, Зверолюд, Ангел, Вампир, Демон, Фея.",
        },
        {
          id: "wg_class",
          target: "[data-tutorial='waifu-gen-class']",
          image: "explaining",
          text: "Класс — боевой стиль и второй уникальный пассив. От класса зависят бонусы к ключевым характеристикам.",
        },
        {
          id: "wg_stats",
          target: "[data-tutorial='waifu-gen-stats']",
          image: "thinking",
          text: "Радар-диаграмма показывает баланс шести характеристик: СИЛ, ЛОВ, ИНТ, ВЫН, ОБА, УДЧ. Они влияют на урон, защиту и шансы в бою.",
        },
        {
          id: "wg_passives",
          target: "[data-tutorial='waifu-gen-passives']",
          image: "excited",
          text: "Здесь — твои уникальные пассивы. Нажми на карточку, чтобы прочитать формулы и условия срабатывания.",
        },
        {
          id: "wg_next",
          target: "#waifu-next-btn",
          image: "waving",
          mode: "action",
          hint: "Нажми «Далее»",
          text: "Готов? Жми «Далее» — настроим внешность и сгенерируем портрет.",
        },
      ],
    },
    waifu_gen_step2: {
      page: "waifu_generator",
      steps: [
        {
          id: "wgs2_welcome",
          target: null,
          image: "greeting",
          text: "Шаг 2 — внешность и портрет. Настрой облик и сгенерируй до трёх вариантов.",
        },
        {
          id: "wgs2_cos",
          target: "[data-tutorial='waifu-gen-cos-bar']",
          image: "explaining",
          text: "Волосы, глаза, одежда и аксессуары — открываются модалками. Выбор отражается в промте генерации.",
        },
        {
          id: "wgs2_portrait",
          target: "#waifu-portrait-frame",
          image: "thinking",
          text: "Здесь появится сгенерированный портрет. Можно выбрать один из вариантов внизу.",
        },
        {
          id: "wgs2_generate",
          target: "#waifu-generate-btn",
          image: "excited",
          mode: "action",
          hint: "Нажми «Сгенерировать»",
          text: "«Сгенерировать» — создаёт новый вариант. Доступно до 3 попыток.",
        },
        {
          id: "wgs2_create",
          target: "#waifu-create-btn",
          image: "waving",
          mode: "action",
          hint: "Нажми «В игру»",
          text: "Когда вариант понравится — «В игру». Вайфу будет создана и появится в профиле.",
        },
      ],
    },
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
          id: "player_avatar",
          target: "[data-tutorial='attic-player-avatar']",
          image: "explaining",
          text: "Кружок слева вверху — профиль игрока. Внутри можно выбрать аватар (не из Telegram), почту, прогресс кампании и бездну. Красная точка — новые письма.",
        },
        {
          id: "portrait",
          target: "[data-tutorial='profile-portrait']",
          image: "explaining",
          text: "Ниже — профиль основной вайфу: имя, уровень, здоровье и опыт. Следи за полосками HP и XP — они обновляются после боёв.",
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
    equip: {
      page: "profile",
      steps: [
        {
          id: "equip_welcome",
          target: null,
          image: "greeting",
          text: "Стартовый набор уже надет. Покажу, где менять экипировку, когда появится новый лут.",
        },
        {
          id: "equip_tab",
          target: "[data-tutorial='profile-inventory-tab']",
          image: "explaining",
          mode: "action",
          hint: "Открой «Инвентарь»",
          text: "Открой вкладку «Инвентарь».",
        },
        {
          id: "equip_slots",
          target: "[data-tutorial='profile-equipment']",
          image: "excited",
          text: "Слоты слева и справа — надетая экипировка. Предмет из сумки можно надеть или заменить уже надетый через карточку предмета.",
          beforeShow: () => {
            if (window.WaifuApp && typeof window.WaifuApp.switchProfileTab === "function") {
              window.WaifuApp.switchProfileTab("inventory");
            }
          },
        },
        {
          id: "equip_bag",
          target: "#profile-inventory",
          image: "waving",
          text: "Сумка внизу — добыча и покупки. Открой предмет и нажми «Надеть», когда появится улучшение.",
          beforeShow: () => {
            if (window.WaifuApp && typeof window.WaifuApp.switchProfileTab === "function") {
              window.WaifuApp.switchProfileTab("inventory");
            }
          },
        },
      ],
    },
    paperdoll: {
      page: "profile",
      steps: [
        {
          id: "paperdoll_welcome",
          target: null,
          image: "greeting",
          text: "Образ с экипировкой — paperdoll. Покажу, где сгенерировать картинку вайфу в надетых вещах.",
          beforeShow: () => {
            provisionPaperdollKit();
          },
        },
        {
          id: "paperdoll_tab",
          target: "[data-tutorial='profile-inventory-tab']",
          image: "explaining",
          mode: "action",
          hint: "Открой «Инвентарь»",
          text: "Открой вкладку «Инвентарь».",
          beforeShow: async () => {
            await provisionPaperdollKit();
          },
        },
        {
          id: "paperdoll_expand",
          target: "#profile-view-toggle",
          image: "thinking",
          mode: "action",
          hint: "Включи расширенный вид",
          text: "В расширенном виде по центру — образ вайфу. Если уже расширенный — просто нажми кнопку ещё раз или продолжим дальше.",
          beforeShow: () => {
            if (window.WaifuApp && typeof window.WaifuApp.switchProfileTab === "function") {
              window.WaifuApp.switchProfileTab("inventory");
            }
          },
          skipIf: () => {
            const gear = document.getElementById("profile-gear");
            return Boolean(gear && gear.classList.contains("is-expanded"));
          },
        },
        {
          id: "paperdoll_menu",
          target: ".profile-paperdoll-menu-btn[data-tutorial='profile-paperdoll-menu']",
          image: "excited",
          text: "Кнопка «⋯» на образе открывает меню действий. Дальше покажу пункт генерации.",
          beforeShow: () => {
            if (window.WaifuApp && typeof window.WaifuApp.switchProfileTab === "function") {
              window.WaifuApp.switchProfileTab("inventory");
            }
            ensureProfileExpandedGear();
            try {
              const menu = document.getElementById("profile-paperdoll-menu");
              if (menu) menu.style.display = "none";
            } catch (e) {
              /* ignore */
            }
          },
        },
        {
          id: "paperdoll_generate",
          target: "[data-tutorial='profile-paperdoll-generate']",
          image: "waving",
          text: "«Сгенерировать изображение» — первая генерация бесплатна. Можешь нажать позже, когда захочешь; сейчас просто запомни, где это.",
          beforeShow: () => {
            openPaperdollMenuForTutorial();
          },
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
          text: "Магазин: купим вещь, заточим, зачаруем и продадим лишнее. Ресурсы для обучения я уже подложила.",
          beforeShow: () => {
            provisionShopKit();
          },
        },
        {
          id: "shop_tab_buy",
          target: "#shop-btab-buy",
          image: "explaining",
          mode: "action",
          hint: "Открой «Покупка»",
          text: "Открой вкладку «Покупка».",
          beforeShow: async () => {
            await provisionShopKit();
          },
        },
        {
          id: "shop_pick_offer",
          target: "[data-tutorial-target='shop-buy']",
          image: "excited",
          mode: "action",
          bubblePlacement: "top",
          hint: "Выбери самый дешёвый товар",
          text: "Выделила самый дешёвый предмет — нажми на него.",
          beforeShow: async () => {
            await provisionShopKit();
            switchShop("buy");
            await waitForShopBuyCards(800);
            markCheapestBuyOffer();
            scheduleLayout();
          },
        },
        {
          id: "shop_confirm_buy",
          target: "#shop-modal-buy",
          image: "excited",
          mode: "action",
          advanceOn: "event",
          waitEvent: "shop:bought",
          hint: "Нажми «Купить»",
          text: "Подтверди покупку — вещь попадёт в инвентарь.",
        },
        {
          id: "shop_tab_smith",
          target: "#shop-btab-smith",
          image: "explaining",
          mode: "action",
          hint: "Открой «Кузнец»",
          text: "Теперь к кузнецу — заточка и зачарование.",
        },
        {
          id: "shop_pick_smith",
          target: "[data-tutorial-target='shop-smith-item']",
          image: "thinking",
          mode: "action",
          hint: "Выбери купленный предмет",
          text: "Выбери купленный предмет в списке кузнеца.",
          beforeShow: () => {
            switchShop("smith");
            switchSmith("sharpen");
            const run = async () => {
              try {
                if (window.WaifuApp && typeof window.WaifuApp.openSmithPickModal === "function") {
                  await window.WaifuApp.openSmithPickModal();
                }
              } catch (e) {
                console.warn("openSmithPickModal failed:", e);
              }
              markBoughtSmithItem();
              scheduleLayout();
            };
            setTimeout(() => {
              run().catch(() => {});
            }, 200);
          },
        },
        {
          id: "shop_sharpen",
          target: "#shop-smith-enchant-btn",
          image: "excited",
          mode: "action",
          advanceOn: "event",
          waitEvent: "shop:enchanted",
          hint: "Нажми «Заточить»",
          text: "Заточи на +1 — в безопасной зоне риск поломки нет.",
          beforeShow: () => {
            switchSmith("sharpen");
            try {
              const modal = document.getElementById("shop-smith-pick-modal");
              if (modal) {
                modal.style.display = "none";
                modal.setAttribute("aria-hidden", "true");
              }
            } catch (e) {
              /* ignore */
            }
          },
        },
        {
          id: "shop_craft_tab",
          target: "#shop-smith-subtab-craft",
          image: "thinking",
          mode: "action",
          hint: "Открой «Зачарование»",
          text: "Перейди на зачарование пылью.",
        },
        {
          id: "shop_craft_add",
          target: "#shop-smith-craft-add",
          image: "thinking",
          mode: "action",
          advanceOn: "event",
          waitEvent: "shop:crafted",
          hint: "Нажми «Выдать бонус»",
          text: "Выдай случайный бонус за пыль зачарования.",
          beforeShow: () => {
            switchSmith("craft");
          },
        },
        {
          id: "shop_tab_sell",
          target: "#shop-btab-sell",
          image: "explaining",
          mode: "action",
          hint: "Открой «Продажа»",
          text: "Купленную вещь оставь себе. Продадим учебный хлам из сумки.",
        },
        {
          id: "shop_sell_junk",
          target: "[data-tutorial-target='shop-sell-junk']",
          image: "excited",
          mode: "action",
          hint: "Выбери учебный предмет",
          text: "Нажми на учебный хлам в списке продажи.",
          beforeShow: () => {
            switchShop("sell");
            setTimeout(() => {
              markSellJunk();
              scheduleLayout();
            }, 400);
          },
        },
        {
          id: "shop_sell_btn",
          target: "#item-modal-sell",
          image: "explaining",
          mode: "action",
          hint: "Нажми «Продать»",
          text: "В карточке предмета нажми «Продать».",
        },
        {
          id: "shop_sell_confirm",
          target: "#item-modal-sell-confirm",
          image: "waving",
          mode: "action",
          advanceOn: "event",
          waitEvent: "shop:sold",
          hint: "Подтверди продажу",
          text: "Подтверди продажу — получишь золото.",
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
          text: "Таверна — место отдыха и найма. Сильный отряд наёмниц помогает в экспедициях.",
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
          mode: "action",
          hint: "Нажми «Нанять»",
          text: "Первый найм бесплатный. Нажми «Нанять» — получишь случайную наёмницу.",
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
          text: "Одиночные — соло-прогресс, Операции — IDLE-контракты наёмниц, Групповые — кооп, Бездна — эндгейм.",
        },
        {
          id: "dungeons_list",
          target: "[data-tutorial='dungeon-list'] .dungeon-tile, [data-tutorial='dungeon-list'] .solo-dungeon-card, #solo-dungeons .dungeon-tile, [data-tutorial='dungeon-list']",
          image: "excited",
          mode: "action",
          hint: "Выбери подземелье",
          text: "Выбери подходящий данж по уровню — начни с простых.",
          beforeShow: () => {
            if (window.WaifuApp && typeof window.WaifuApp.showTab === "function") {
              window.WaifuApp.showTab("solo");
            }
          },
        },
      ],
    },
    expeditions: {
      page: "dungeons",
      tab: "expedition",
      steps: [
        {
          id: "exp_welcome",
          target: null,
          image: "greeting",
          text: "Операции — контракты с отрядом наёмниц. Награды по таймеру + merc coins.",
          beforeShow: () => {
            if (window.WaifuApp && typeof window.WaifuApp.showTab === "function") {
              window.WaifuApp.showTab("expedition");
            }
          },
        },
        {
          id: "exp_tab",
          target: "#dungeon-tabs .tab[data-tab='expedition']",
          image: "explaining",
          mode: "action",
          hint: "Открой «Операции»",
          text: "Вкладка «Операции» — активные контракты и свободные слоты.",
        },
        {
          id: "exp_slot",
          target: "[data-tutorial='exp-free-slot'], #exp-free-slots .exp-free-slot, #exp-bottom-zone",
          image: "excited",
          mode: "action",
          hint: "Открой отправку",
          text: "Нажми свободный слот «Отправить экспедицию», чтобы собрать отряд. Старт не обязателен — просто посмотри интерфейс.",
          beforeShow: () => {
            if (window.WaifuApp && typeof window.WaifuApp.showTab === "function") {
              window.WaifuApp.showTab("expedition");
            }
          },
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
          target: ".caravan-pin-hit, [data-tutorial='caravan-map']",
          image: "explaining",
          mode: "action",
          bubblePlacement: "top",
          raiseAncestors: true,
          hideSiblingPins: true,
          hint: "Нажми точку на карте",
          text: "Нажми на точку на карте, чтобы переместиться в соответствующий акт. Новые акты открываются по мере прохождения.",
        },
        {
          id: "caravan_library_pin",
          target: ".caravan-pin--library .caravan-pin-ico-btn, [data-tutorial='caravan-library']",
          image: "excited",
          mode: "action",
          bubblePlacement: "bottom",
          raiseAncestors: true,
          hideSiblingPins: true,
          hint: "Открой библиотеку",
          text: "Здесь же вход в библиотеку — бестиарий, механики и предметы.",
        },
        {
          id: "library_tabs",
          target: "#lib-tabs",
          image: "thinking",
          bubblePlacement: "bottom",
          raiseAncestors: false,
          text: "Вкладки библиотеки: бестиарий, механики и предметы. Покажу каждую.",
          beforeShow: async () => {
            await ensureLibraryOpenForTutorial("bestiary");
          },
        },
        {
          id: "library_bestiary",
          target: "[data-tutorial='lib-tab-bestiary'], #lib-tabs [data-lib-tab='bestiary']",
          image: "explaining",
          bubblePlacement: "bottom",
          raiseAncestors: false,
          text: "Бестиарий — карточки монстров текущего акта.",
          beforeShow: async () => {
            await ensureLibraryOpenForTutorial("bestiary");
          },
        },
        {
          id: "library_mechanics",
          target: "[data-tutorial='lib-tab-mechanics'], #lib-tabs [data-lib-tab='mechanics']",
          image: "thinking",
          bubblePlacement: "bottom",
          raiseAncestors: false,
          text: "Механики — краткий справочник правил боя и прогресса.",
          beforeShow: async () => {
            await ensureLibraryOpenForTutorial("mechanics");
          },
        },
        {
          id: "library_items",
          target: "[data-tutorial='lib-tab-items'], #lib-tabs [data-lib-tab='items']",
          image: "excited",
          bubblePlacement: "bottom",
          raiseAncestors: false,
          text: "Предметы — каталог экипировки и аффиксов.",
          beforeShow: async () => {
            await ensureLibraryOpenForTutorial("items");
          },
        },
        {
          id: "caravan_farewell",
          target: null,
          image: "waving",
          text: "Караван и библиотека под рукой — возвращайся, когда понадобится справка или смена акта.",
          beforeShow: () => {
            forceCloseLibrary();
          },
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
          id: "guild_noguild",
          target: "#guild-create-section, #guild-search-section, [data-tutorial='guild-tabs']",
          image: "explaining",
          text: "Пока ты не в гильдии — создай свою или найди подходящую в поиске. После вступления откроются вкладки зала.",
          skipIf: () => guildTabsVisible(),
        },
        {
          id: "guild_tab_main",
          target: "[data-guild-tab-btn='main']",
          image: "explaining",
          text: "«Гильдия» — обзор зала, участники и управление.",
          skipIf: () => !guildTabsVisible(),
          beforeShow: () => switchGuildTutorialTab("main"),
        },
        {
          id: "guild_tab_battles",
          target: "[data-guild-tab-btn='battles']",
          image: "excited",
          text: "«Битвы» — рейды, войны и квесты гильдии.",
          skipIf: () => !guildTabsVisible(),
          beforeShow: () => switchGuildTutorialTab("battles"),
        },
        {
          id: "guild_tab_skills",
          target: "[data-guild-tab-btn='skills']",
          image: "thinking",
          text: "«Навыки» — ветки бонусов гильдии для всего отряда.",
          skipIf: () => !guildTabsVisible(),
          beforeShow: () => switchGuildTutorialTab("skills"),
        },
        {
          id: "guild_tab_bank",
          target: "[data-guild-tab-btn='bank']",
          image: "explaining",
          text: "«Казна» — общий банк гильдии: золото и предметы.",
          skipIf: () => !guildTabsVisible(),
          beforeShow: () => switchGuildTutorialTab("bank"),
        },
        {
          id: "guild_tab_history",
          target: "[data-guild-tab-btn='history']",
          image: "waving",
          text: "«История» — события и активность гильдии.",
          skipIf: () => !guildTabsVisible(),
          beforeShow: () => switchGuildTutorialTab("history"),
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
          id: "training_warrior",
          target: "[data-training-tab='warrior']",
          image: "explaining",
          bubblePlacement: "bottom",
          text: "«Воин» — физический урон и живучесть.",
          beforeShow: () => switchTrainingTutorialTab("warrior"),
        },
        {
          id: "training_shadow",
          target: "[data-training-tab='shadow']",
          image: "excited",
          bubblePlacement: "bottom",
          text: "«Тень» — крит, уклонение и скорость.",
          beforeShow: () => switchTrainingTutorialTab("shadow"),
        },
        {
          id: "training_sage",
          target: "[data-training-tab='sage']",
          image: "thinking",
          bubblePlacement: "bottom",
          text: "«Мудрец» — магия, ресурсы и поддержка.",
          beforeShow: () => switchTrainingTutorialTab("sage"),
        },
        {
          id: "training_tree",
          target:
            "[data-tutorial='training-tree'] .passive-skill-cell, [data-tutorial='training-tree'] button, [data-tutorial='training-tree']",
          image: "explaining",
          mode: "action",
          bubblePlacement: "bottom",
          overflowVisible: "#passive-tree-root",
          hint: "Нажми на узел",
          text: "Нажми на узел дерева, чтобы открыть прокачку навыка.",
          beforeShow: () => switchTrainingTutorialTab("warrior"),
        },
        {
          id: "training_hidden_teaser",
          target: "[data-training-tab='hidden'], [data-training-tab='perfection']",
          image: "waving",
          bubblePlacement: "bottom",
          text: "Это ещё не всё: позже откроются скрытые навыки («?») и «Совершенствование» после 60 уровня. Загляни во вкладки, когда будут доступны.",
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
    blockers: [],
    holeHit: null,
    actionListener: null,
    eventListener: null,
    waitingEvent: null,
    holeRect: null,
    raisedTarget: null,
    raisedChain: [],
    raisedLeafOnly: false,
    hiddenCaravanPins: [],
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
      return {
        version: 1,
        completed: {},
        skipped: false,
        intro_reward_claimed: false,
        shop_kit_claimed: false,
        paperdoll_kit_claimed: false,
      };
    }
    return {
      version: Number(raw.version) || 1,
      completed: raw.completed && typeof raw.completed === "object" ? raw.completed : {},
      skipped: Boolean(raw.skipped),
      intro_reward_claimed: Boolean(raw.intro_reward_claimed),
      shop_kit_claimed: Boolean(raw.shop_kit_claimed),
      paperdoll_kit_claimed: Boolean(raw.paperdoll_kit_claimed),
    };
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

  function currentStep() {
    return state.steps[state.stepIndex] || null;
  }

  function skipToNextValidStep() {
    while (state.stepIndex < state.steps.length) {
      const step = state.steps[state.stepIndex];
      if (!step) break;
      if (typeof step.skipIf === "function") {
        try {
          if (step.skipIf()) {
            state.stepIndex += 1;
            continue;
          }
        } catch (e) {
          console.warn("tutorial skipIf failed:", e);
        }
      }
      break;
    }
  }

  function stepMode(step) {
    return step && step.mode === "action" ? "action" : "narrate";
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
      <div class="tutorial-blocker tutorial-blocker-t" data-blocker="t"></div>
      <div class="tutorial-blocker tutorial-blocker-b" data-blocker="b"></div>
      <div class="tutorial-blocker tutorial-blocker-l" data-blocker="l"></div>
      <div class="tutorial-blocker tutorial-blocker-r" data-blocker="r"></div>
      <div class="tutorial-hole-hit" aria-hidden="true"></div>
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
        <button type="button" class="tutorial-step-close" aria-label="Пропустить раздел" title="Пропустить раздел">×</button>
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
    state.blockers = Array.from(root.querySelectorAll(".tutorial-blocker"));
    state.holeHit = root.querySelector(".tutorial-hole-hit");

    state.closeStepBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      skipFlow();
    });
    state.bubble.addEventListener("click", (e) => {
      if (e.target.closest(".tutorial-step-close")) return;
      const step = currentStep();
      if (stepMode(step) === "action") return;
      advanceStep();
    });
    state.blockers.forEach((panel) => {
      panel.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const step = currentStep();
        if (stepMode(step) === "narrate") advanceStep();
      });
    });
    if (state.holeHit) {
      state.holeHit.addEventListener("pointerdown", onHoleHitPointer, true);
      state.holeHit.addEventListener("click", onHoleHitClick, true);
    }
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
    layoutRaf = requestAnimationFrame(() => {
      if (!state.active) return;
      const step = currentStep();
      const targetEl = getTargetEl(step) || state.raisedTarget;
      layoutSpotlight(targetEl, { skipScroll: true });
    });
  }

  function getTargetEl(step) {
    if (!step || !step.target) return null;
    if (typeof step.target === "function") {
      try {
        return step.target();
      } catch (e) {
        return null;
      }
    }
    try {
      return document.querySelector(step.target);
    } catch (e) {
      return null;
    }
  }

  function createsStackingContext(el, cs) {
    if (!el || !cs) return false;
    const pos = cs.position;
    const z = cs.zIndex;
    if (pos === "fixed" || pos === "sticky") return true;
    if ((pos === "relative" || pos === "absolute") && z !== "auto") return true;
    if (cs.transform && cs.transform !== "none") return true;
    if (cs.filter && cs.filter !== "none") return true;
    if (cs.backdropFilter && cs.backdropFilter !== "none") return true;
    if (cs.webkitBackdropFilter && cs.webkitBackdropFilter !== "none") return true;
    if (cs.isolation === "isolate") return true;
    if (cs.opacity !== "" && Number(cs.opacity) < 1) return true;
    if (cs.willChange && /transform|opacity|filter|backdrop-filter/.test(cs.willChange)) return true;
    if (cs.contain && /layout|paint|strict|content/.test(cs.contain)) return true;
    return false;
  }

  function clearRaisedTarget() {
    const chain = state.raisedChain || [];
    for (let i = chain.length - 1; i >= 0; i -= 1) {
      const entry = chain[i];
      const el = entry && entry.el;
      if (!el) continue;
      try {
        el.classList.remove("tutorial-target-raised");
        if (entry.position != null && entry.position !== "") el.style.position = entry.position;
        else el.style.removeProperty("position");
        if (entry.zIndex != null && entry.zIndex !== "") el.style.zIndex = entry.zIndex;
        else el.style.removeProperty("z-index");
        if (entry.pointerEvents != null && entry.pointerEvents !== "") {
          el.style.pointerEvents = entry.pointerEvents;
        } else {
          el.style.removeProperty("pointer-events");
        }
        if (entry.overflow != null && entry.overflow !== "") el.style.overflow = entry.overflow;
        else if (Object.prototype.hasOwnProperty.call(entry, "overflow")) {
          el.style.removeProperty("overflow");
        }
      } catch (e) {
        /* ignore */
      }
    }
    state.raisedChain = [];
    state.raisedTarget = null;
    state.raisedLeafOnly = false;
  }

  function raiseTarget(el, options) {
    if (!el) return;
    const opts = options || {};
    const raiseAncestors = opts.raiseAncestors !== false;
    if (
      state.raisedTarget === el &&
      state.raisedChain &&
      state.raisedChain.length &&
      Boolean(state.raisedLeafOnly) === !raiseAncestors
    ) {
      return;
    }
    clearRaisedTarget();

    const chain = [];
    let node = el;
    while (node && node !== document.documentElement && node !== document.body) {
      let cs;
      try {
        cs = window.getComputedStyle(node);
      } catch (e) {
        cs = null;
      }
      const isLeaf = node === el;
      if (isLeaf || (raiseAncestors && cs && createsStackingContext(node, cs))) {
        chain.push({
          el: node,
          position: node.style.position || "",
          zIndex: node.style.zIndex || "",
          pointerEvents: node.style.pointerEvents || "",
          overflow: node.style.overflow || "",
        });
        node.classList.add("tutorial-target-raised");
        if (isLeaf && cs && cs.position === "static") {
          node.style.position = "relative";
        }
        node.style.zIndex = "99150";
        if (isLeaf) node.style.pointerEvents = "auto";
      }
      if (!raiseAncestors) break;
      node = node.parentElement;
    }

    if (opts.overflowVisible) {
      const overflowRoots = Array.isArray(opts.overflowVisible)
        ? opts.overflowVisible
        : [opts.overflowVisible];
      overflowRoots.forEach((sel) => {
        const root =
          typeof sel === "string" ? document.querySelector(sel) : sel;
        if (!root) return;
        const already = chain.some((entry) => entry.el === root);
        if (!already) {
          chain.push({
            el: root,
            position: root.style.position || "",
            zIndex: root.style.zIndex || "",
            pointerEvents: root.style.pointerEvents || "",
            overflow: root.style.overflow || "",
          });
          root.classList.add("tutorial-target-raised");
          root.style.zIndex = "99150";
        } else {
          const entry = chain.find((e) => e.el === root);
          if (entry && !Object.prototype.hasOwnProperty.call(entry, "overflowSaved")) {
            entry.overflow = root.style.overflow || "";
            entry.overflowSaved = true;
          }
        }
        root.style.overflow = "visible";
      });
    }

    state.raisedChain = chain;
    state.raisedTarget = el;
    state.raisedLeafOnly = !raiseAncestors;
  }

  function layoutHoleHit(x, y, w, h, enabled) {
    const hit = state.holeHit;
    if (!hit) return;
    if (!enabled || w <= 0 || h <= 0) {
      hit.style.display = "none";
      hit.style.width = "0";
      hit.style.height = "0";
      return;
    }
    hit.style.display = "block";
    hit.style.left = `${x}px`;
    hit.style.top = `${y}px`;
    hit.style.width = `${w}px`;
    hit.style.height = `${h}px`;
  }

  function invokeTargetClick(targetEl, clientX, clientY) {
    if (!targetEl) return false;
    try {
      if (typeof targetEl.click === "function") {
        targetEl.click();
        return true;
      }
      targetEl.dispatchEvent(
        new MouseEvent("click", {
          bubbles: true,
          cancelable: true,
          view: window,
          clientX: clientX || 0,
          clientY: clientY || 0,
        }),
      );
      return true;
    } catch (e) {
      console.warn("tutorial target click failed:", e);
      return false;
    }
  }

  function forwardHoleClick(clientX, clientY) {
    if (!state.root || !state.active) return false;
    const step = currentStep();
    if (stepMode(step) !== "action") return false;
    const targetEl = getTargetEl(step) || state.raisedTarget;
    if (!targetEl) return false;

    // Primary path: always activate the known tutorial target.
    let clicked = invokeTargetClick(targetEl, clientX, clientY);

    // Optional fallback for nested controls if direct click did nothing useful
    // (e.g. target is a wrapper). Prefer pointer-events:none over visibility:hidden.
    if (!clicked) {
      const prevPe = state.root.style.pointerEvents;
      state.root.style.pointerEvents = "none";
      let under = null;
      try {
        under = document.elementFromPoint(clientX, clientY);
      } catch (e) {
        under = null;
      }
      state.root.style.pointerEvents = prevPe;
      if (under && (targetEl.contains(under) || under === targetEl)) {
        let clickEl = under;
        if (under !== targetEl && typeof under.closest === "function") {
          const btn = under.closest("button, a, [role='button'], input, select, label");
          if (btn && targetEl.contains(btn)) clickEl = btn;
        }
        clicked = invokeTargetClick(clickEl, clientX, clientY);
      }
    }

    if (!clicked) return false;

    if (typeof step.onTargetClick === "function") {
      try {
        step.onTargetClick({ target: targetEl }, targetEl);
      } catch (err) {
        console.warn("tutorial onTargetClick failed:", err);
      }
    }

    if ((step.advanceOn || "click") === "click") {
      detachActionListeners();
      setTimeout(() => advanceStep(), 0);
    }
    return true;
  }

  let holeForwarding = false;
  function onHoleHitPointer(e) {
    if (holeForwarding) return;
    if (stepMode(currentStep()) !== "action") return;
    e.preventDefault();
    e.stopPropagation();
  }

  function onHoleHitClick(e) {
    if (holeForwarding) return;
    if (stepMode(currentStep()) !== "action") return;
    e.preventDefault();
    e.stopPropagation();
    holeForwarding = true;
    try {
      forwardHoleClick(e.clientX, e.clientY);
    } finally {
      holeForwarding = false;
    }
  }

  function layoutBlockers(x, y, w, h) {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const [top, bottom, left, right] = state.blockers;
    if (!top) return;

    if (w <= 0 || h <= 0) {
      state.blockers.forEach((b) => {
        b.style.display = "block";
        b.style.left = "0";
        b.style.top = "0";
        b.style.width = "100%";
        b.style.height = "100%";
      });
      bottom.style.display = "none";
      left.style.display = "none";
      right.style.display = "none";
      layoutHoleHit(0, 0, 0, 0, false);
      return;
    }

    top.style.display = "block";
    bottom.style.display = "block";
    left.style.display = "block";
    right.style.display = "block";

    top.style.left = "0";
    top.style.top = "0";
    top.style.width = "100%";
    top.style.height = `${Math.max(0, y)}px`;

    bottom.style.left = "0";
    bottom.style.top = `${y + h}px`;
    bottom.style.width = "100%";
    bottom.style.height = `${Math.max(0, vh - (y + h))}px`;

    left.style.left = "0";
    left.style.top = `${y}px`;
    left.style.width = `${Math.max(0, x)}px`;
    left.style.height = `${h}px`;

    right.style.left = `${x + w}px`;
    right.style.top = `${y}px`;
    right.style.width = `${Math.max(0, vw - (x + w))}px`;
    right.style.height = `${h}px`;
  }

  function layoutSpotlight(targetEl, options) {
    const opts = options || {};
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const mode = stepMode(currentStep());
    const actionMode = mode === "action";

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
      state.holeRect = null;
      layoutBlockers(0, 0, 0, 0);
      layoutHoleHit(0, 0, 0, 0, false);
      return;
    }

    state.root.classList.remove("is-no-target");
    state.bubble.classList.remove("is-centered");

    const rect = targetEl.getBoundingClientRect();
    const x = Math.max(0, rect.left - PAD);
    const y = Math.max(0, rect.top - PAD);
    const w = Math.min(vw - x, rect.width + PAD * 2);
    const h = Math.min(vh - y, rect.height + PAD * 2);
    state.holeRect = { x, y, w, h };

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

    layoutBlockers(x, y, w, h);
    // Hole-hit is the reliable click path in Telegram WebView (pass-through is flaky).
    layoutHoleHit(x, y, w, h, actionMode);

    const bubbleRect = state.bubble.getBoundingClientRect();
    const bubbleW = bubbleRect.width || 280;
    const bubbleH = bubbleRect.height || 160;
    const gap = 14;
    const margin = 8;

    const step = currentStep();
    const placement = step && step.bubblePlacement;
    const forceTop = placement === "top";
    const forceBottom = placement === "bottom";

    let bubbleTop;
    if (forceTop) {
      bubbleTop = margin;
    } else if (forceBottom) {
      bubbleTop = Math.min(y + h + gap, vh - bubbleH - margin);
      if (bubbleTop < margin) bubbleTop = margin;
    } else {
      const spaceBelow = vh - (y + h) - gap - margin;
      const spaceAbove = y - gap - margin;
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
    }

    const bubbleLeft = Math.max(
      margin,
      Math.min(x + w / 2 - bubbleW / 2, vw - bubbleW - margin),
    );

    state.bubble.style.left = `${bubbleLeft}px`;
    state.bubble.style.top = `${bubbleTop}px`;
    state.bubble.style.transform = "";

    if (!opts.skipScroll) {
      try {
        targetEl.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "auto" });
      } catch (e) {
        /* ignore */
      }
    }
  }

  function detachActionListeners() {
    if (state.actionListener) {
      document.removeEventListener("pointerdown", state.actionListener, true);
      document.removeEventListener("click", state.actionListener, true);
      state.actionListener = null;
    }
    if (state.eventListener && state.waitingEvent) {
      window.removeEventListener(state.waitingEvent, state.eventListener);
      state.eventListener = null;
      state.waitingEvent = null;
    }
  }

  function attachActionListeners(step, targetEl) {
    detachActionListeners();
    if (stepMode(step) !== "action") return;

    const advanceOn = step.advanceOn || "click";
    if (advanceOn === "event" && step.waitEvent) {
      state.waitingEvent = step.waitEvent;
      state.eventListener = () => {
        detachActionListeners();
        advanceStep();
      };
      window.addEventListener(step.waitEvent, state.eventListener, { once: true });
    }

    state.actionListener = (e) => {
      if (!state.active) return;
      const cur = currentStep();
      if (stepMode(cur) !== "action") return;
      const el = getTargetEl(cur) || targetEl;
      if (!el) return;
      const path = typeof e.composedPath === "function" ? e.composedPath() : [];
      const hit = path.includes(el) || el.contains(e.target);
      if (!hit) return;

      if (typeof cur.onTargetClick === "function") {
        try {
          cur.onTargetClick(e, el);
        } catch (err) {
          console.warn("tutorial onTargetClick failed:", err);
        }
      }

      if ((cur.advanceOn || "click") === "click") {
        // Let the real click proceed; advance after microtask so UI handlers run.
        detachActionListeners();
        setTimeout(() => advanceStep(), 0);
      }
      // For event mode: real click runs game code; wait for notify().
    };
    document.addEventListener("pointerdown", state.actionListener, true);
  }

  function renderCurrentStep(scrollTarget) {
    const step = state.steps[state.stepIndex];
    if (!step) return;

    detachActionListeners();
    clearRaisedTarget();
    clearHiddenCaravanPins();
    layoutHoleHit(0, 0, 0, 0, false);

    if (state.flowId === "caravan") {
      elevateTutorialRoot();
    }

    const imageKey = step.image || "explaining";
    state.waifuImg.src = `${TUTORIAL_IMAGE_BASE}${imageKey}.webp`;
    state.waifuImg.alt = "";
    state.progressEl.textContent = `${state.stepIndex + 1} / ${state.steps.length}`;
    state.textEl.textContent = step.text || "";

    const mode = stepMode(step);
    state.root.classList.toggle("is-action-mode", mode === "action");

    const isLast = state.stepIndex >= state.steps.length - 1;
    if (state.hintEl) {
      if (mode === "action") {
        state.hintEl.textContent = step.hint || "Нажми выделенное";
      } else {
        state.hintEl.textContent = isLast
          ? "Нажмите, чтобы завершить"
          : "Нажмите, чтобы продолжить";
      }
    }

    const applyTarget = () => {
      if (!state.active || currentStep() !== step) return;
      let targetEl = getTargetEl(step);
      let effectiveMode = mode;
      if (mode === "action" && !targetEl) {
        console.warn("tutorial action target missing, falling back to narrate:", step.id);
        state.root.classList.remove("is-action-mode");
        effectiveMode = "narrate";
        if (state.hintEl) {
          state.hintEl.textContent = "Нажмите, чтобы продолжить";
        }
      }
      if (
        mode === "action" &&
        effectiveMode === "action" &&
        targetEl &&
        (targetEl.disabled || targetEl.getAttribute("disabled") != null)
      ) {
        console.warn("tutorial action target disabled, falling back to narrate:", step.id);
        state.root.classList.remove("is-action-mode");
        effectiveMode = "narrate";
        if (state.hintEl) {
          state.hintEl.textContent = isLast
            ? "Нажмите, чтобы завершить"
            : "Нажмите, чтобы продолжить";
        }
      }
      if (scrollTarget !== false && targetEl) {
        try {
          targetEl.scrollIntoView({ block: "center", inline: "nearest", behavior: "auto" });
        } catch (e) {
          /* ignore */
        }
      }
      if (effectiveMode === "action" && targetEl) {
        raiseTarget(targetEl, {
          raiseAncestors: step.raiseAncestors !== false,
          overflowVisible: step.overflowVisible || null,
        });
        if (step.hideSiblingPins) hideOtherCaravanPins(targetEl);
      } else {
        clearRaisedTarget();
      }
      layoutSpotlight(targetEl, { skipScroll: true });

      if (state.resizeObserver) {
        state.resizeObserver.disconnect();
      }
      if (targetEl && typeof ResizeObserver !== "undefined") {
        state.resizeObserver = new ResizeObserver(scheduleLayout);
        state.resizeObserver.observe(targetEl);
      }

      if (effectiveMode === "action" && targetEl) {
        attachActionListeners(step, targetEl);
      }
    };

    const runBeforeShow = () => {
      if (typeof step.beforeShow !== "function") {
        requestAnimationFrame(() => setTimeout(applyTarget, 50));
        return;
      }
      let ret;
      try {
        ret = step.beforeShow();
      } catch (e) {
        console.warn("tutorial beforeShow failed:", e);
        requestAnimationFrame(() => setTimeout(applyTarget, 50));
        return;
      }
      if (ret && typeof ret.then === "function") {
        ret
          .then(() => {
            if (!state.active || currentStep() !== step) return;
            requestAnimationFrame(() => setTimeout(applyTarget, 50));
          })
          .catch((e) => {
            console.warn("tutorial beforeShow failed:", e);
            if (!state.active || currentStep() !== step) return;
            requestAnimationFrame(() => setTimeout(applyTarget, 50));
          });
      } else {
        requestAnimationFrame(() => setTimeout(applyTarget, 50));
      }
    };

    runBeforeShow();
  }

  function setupTelegramBackButton() {
    const tg = window.Telegram && window.Telegram.WebApp;
    if (!tg || !tg.BackButton) return;
    state.onBackButton = () => {
      if (state.stepIndex > 0) {
        state.stepIndex -= 1;
        renderCurrentStep();
      } else {
        skipFlow();
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
    // session seen only on complete/skip — incomplete can retry next visit

    state.root.hidden = false;
    document.body.classList.add("tutorial-active");
    if (flowId === "caravan" || (flow && flow.page === "caravan")) {
      elevateTutorialRoot();
    }
    setupTelegramBackButton();
    skipToNextValidStep();
    if (state.stepIndex >= state.steps.length) {
      finishFlow();
      return true;
    }
    renderCurrentStep();
    return true;
  }

  function close() {
    if (!state.root) return;
    detachActionListeners();
    clearRaisedTarget();
    clearHiddenCaravanPins();
    clearLibraryModalTutorialZ();
    clearMarkedTargets();
    layoutHoleHit(0, 0, 0, 0, false);
    state.active = false;
    state.root.hidden = true;
    resetTutorialRootZ();
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
      markSessionSeen(flowId);
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
    if (flowId === "waifu_gen") {
      // Step 2 may already be visible after action click on «Далее».
      const step2 = document.getElementById("waifu-step-2");
      const visible = step2 && !step2.hidden;
      if (visible) {
        setTimeout(() => {
          maybeRun("waifu_generator", state.tutorialState, "waifu_gen_step2");
        }, 400);
      }
    }
  }

  function advanceStep() {
    if (!state.active) return;
    if (state.stepIndex >= state.steps.length - 1) {
      finishFlow();
      return;
    }
    state.stepIndex += 1;
    skipToNextValidStep();
    if (state.stepIndex >= state.steps.length) {
      finishFlow();
      return;
    }
    renderCurrentStep();
  }

  async function skipFlow() {
    if (
      !confirm(
        "Пропустить этот раздел обучения? Остальные подсказки при посещении страниц останутся.",
      )
    ) {
      return;
    }
    const flowId = state.flowId;
    close();
    if (!flowId) return;
    try {
      const data = await tutorialApiFetch("/tutorial/complete", {
        method: "POST",
        body: { step_id: flowId },
      });
      if (data && data.tutorial) {
        state.tutorialState = normalizeTutorialState(data.tutorial);
      }
      markSessionSeen(flowId);
    } catch (e) {
      console.warn("tutorial skipFlow failed:", e);
    }
  }

  async function skipAll() {
    if (
      !confirm("Пропустить всё обучение? Подсказки больше не будут показываться автоматически.")
    ) {
      return;
    }
    close();
    try {
      const data = await tutorialApiFetch("/tutorial/skip", { method: "POST" });
      if (data) state.tutorialState = normalizeTutorialState(data);
      for (const flowId of Object.keys(TUTORIAL_FLOWS)) {
        markSessionSeen(flowId);
      }
    } catch (e) {
      console.warn("tutorial skip failed:", e);
    }
  }

  function isWaifuGenStep2Visible() {
    const step2 = document.getElementById("waifu-step-2");
    return Boolean(step2 && !step2.hidden);
  }

  function resolveFlowForPage(page, tutorialState, forced, options) {
    const opts = options || {};
    if (forced && TUTORIAL_FLOWS[forced]) {
      const flow = TUTORIAL_FLOWS[forced];
      if (flow.page === page) return forced;
      return null;
    }
    if (
      page === "index" ||
      page === "settings" ||
      page === "battle" ||
      page === "mail" ||
      page === "player"
    ) {
      return null;
    }
    const ts = normalizeTutorialState(tutorialState);
    if (ts.skipped) return null;

    if (page === "waifu_generator") {
      if (!ts.completed.waifu_gen && !wasSeenThisSession("waifu_gen") && !isWaifuGenStep2Visible()) {
        return "waifu_gen";
      }
      if (
        ts.completed.waifu_gen &&
        !ts.completed.waifu_gen_step2 &&
        !wasSeenThisSession("waifu_gen_step2") &&
        isWaifuGenStep2Visible()
      ) {
        return "waifu_gen_step2";
      }
      return null;
    }

    if (page === "profile" && !ts.completed.intro && !wasSeenThisSession("intro")) {
      return "intro";
    }

    const activeTab = opts.tab || null;

    for (const flowId of Object.keys(TUTORIAL_FLOWS)) {
      if (flowId === "intro" || flowId === "waifu_gen" || flowId === "waifu_gen_step2") continue;
      const flow = TUTORIAL_FLOWS[flowId];
      if (flow.page !== page) continue;
      if (flow.tab) {
        if (activeTab !== flow.tab) continue;
      } else if (page === "dungeons" && flowId === "dungeons") {
        // default dungeons flow only when not on expedition tab (or tab unknown)
        if (activeTab && activeTab !== "solo") continue;
      }
      if (ts.completed[flowId]) continue;
      if (wasSeenThisSession(flowId)) continue;
      return flowId;
    }
    return null;
  }

  let pendingStartTimer = 0;

  function maybeRun(page, tutorialState, forced, options) {
    if (state.active) return;
    const flowId = resolveFlowForPage(page, tutorialState, forced, options);
    if (!flowId) return;

    const start = () => {
      pendingStartTimer = 0;
      if (state.active) return;
      open(flowId, tutorialState);
    };

    const delay = flowId === "intro" ? 600 : 400;
    if (pendingStartTimer) clearTimeout(pendingStartTimer);
    const arm = () => {
      pendingStartTimer = setTimeout(start, delay);
    };
    if (document.readyState === "complete") {
      arm();
    } else {
      window.addEventListener("load", arm, { once: true });
    }
  }

  function notify(eventName, detail) {
    if (eventName === "shop:bought" && detail && detail.inventory_item_id) {
      flowCtx.boughtItemId = detail.inventory_item_id;
    }
    try {
      window.dispatchEvent(new CustomEvent(eventName, { detail: detail || {} }));
    } catch (e) {
      /* ignore */
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
      flowCtx.shop = null;
      flowCtx.boughtItemId = null;
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
    skipFlow,
    notify,
    markTarget,
    clearMarkedTargets,
    isActive: () => Boolean(state.active),
    getFlowId: () => state.flowId,
    TUTORIAL_FLOWS,
  };
})();
