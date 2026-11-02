(() => {
  const LIVE_CONFIRM =
    "警告：您目前未開啟測試模式，系統啟動後若偵測到有貨將會進行真實的信用卡扣款與下單！請問是否確定要啟動？";

  const STORAGE_PROFILES = "hkIphoneBot.profiles";
  const STORAGE_SAVED = "hkIphoneBot.savedProfiles";
  const STORAGE_SKUS = "hkIphoneBot.extraSkus";
  const STORAGE_MODE = "hkIphoneBot.testMode";
  const STORAGE_COLLAPSED = "hkIphoneBot.collapsed";
  const PREVIEW_ALERT = "而家係預覽模式：新增／刪除 Worker、改機型、加／刪 SKU、儲存設定都可以試。真正開瀏覽器搶購，請用 Python 開後台後打開 http://127.0.0.1:8765";
  const STATUS_LABELS = {
    idle: "未登入 Apple ID",
    needs_login: "未登入 Apple ID",
    logging_in: "等待登入中",
    ready: "待命（已登入）",
    ready_guest: "待命（已填妥資料）",
    launching: "正在開啟瀏覽器",
    watching: "監控庫存中",
    checking_out: "正在結帳",
    dry_run_paused: "測試完成（已停在最後一步）",
    completed: "已達數量上限",
    stopped: "已停止",
    browser_closed: "瀏覽器已關閉（已停搶）",
    paused: "已自動暫停",
    error: "發生錯誤",
  };
  const GUEST_FIELDS = [
    ["last_name", "英文姓氏"],
    ["first_name", "英文名字"],
    ["email", "電郵地址"],
    ["phone", "香港聯絡電話"],
    ["address_street", "街道地址（區域、地區、街道名稱及號碼）"],
    ["address_building", "屋苑或大廈／座數／樓層／單位"],
    ["card_number", "信用卡號碼"],
    ["card_month", "有效月份"],
    ["card_year", "有效年份"],
    ["cvv", "CVV 安全碼"],
  ];
  const FALLBACK_CATALOG = {
    stores: [
      { id: "R428", name: "ifc mall", area: "中環" },
      { id: "R409", name: "Hysan Place", area: "銅鑼灣" },
      { id: "R499", name: "Canton Road", area: "尖沙咀" },
      { id: "R485", name: "Festival Walk", area: "九龍塘" },
      { id: "R673", name: "apm Hong Kong", area: "觀塘" },
      { id: "R610", name: "New Town Plaza", area: "沙田" },
    ],
    products: [
      { sku: "MK2D4ZA/A", label: "iPhone Duo 256GB 星光白色" },
      { sku: "MK2E4ZA/A", label: "iPhone Duo 256GB 夜空色" },
      { sku: "MK2F4ZA/A", label: "iPhone Duo 512GB 星光白色" },
      { sku: "MK2G4ZA/A", label: "iPhone Duo 512GB 夜空色" },
      { sku: "MK2H4ZA/A", label: "iPhone Duo 1TB 星光白色" },
      { sku: "MK2J4ZA/A", label: "iPhone Duo 1TB 夜空色" },
      { sku: "MK2K4ZA/A", label: "iPhone Duo 2TB 星光白色" },
      { sku: "MK2L4ZA/A", label: "iPhone Duo 2TB 夜空色" },
    ],
    pickup_windows: [
      { id: "1d", label: "一日內" },
      { id: "2d", label: "兩日內" },
      { id: "3d", label: "三日內" },
    ],
    delivery_windows: [
      { id: "3", label: "3 日內送到" },
      { id: "5", label: "5 日內送到" },
      { id: "7", label: "7 日內送到" },
      { id: "10", label: "10 日內送到" },
      { id: "14", label: "14 日內送到" },
    ],
  };

  const els = {
    testMode: document.getElementById("test-mode"),
    modeHint: document.getElementById("mode-hint"),
    start: document.getElementById("btn-start"),
    stop: document.getElementById("btn-stop"),
    add: document.getElementById("btn-add"),
    save: document.getElementById("btn-save"),
    saveHint: document.getElementById("save-hint"),
    list: document.getElementById("worker-list"),
    empty: document.getElementById("worker-empty"),
    logs: document.getElementById("log-stream"),
    pill: document.getElementById("run-pill"),
    clearLogs: document.getElementById("btn-clear-logs"),
    runLock: document.getElementById("run-lock"),
    startHint: document.getElementById("start-hint"),
    workersPanel: document.querySelector(".workers"),
  };

  const state = {
    catalog: { stores: [], products: [], pickup_windows: [] },
    extraSkus: [],
    workers: [],
    savedWorkers: loadJson(STORAGE_SAVED, []),
    running: false,
    stickLogs: true,
    previewMode: false,
    dirty: true,
  };

  function loadJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  }

  function normalizeExtraSkus(raw) {
    if (!Array.isArray(raw)) return [];
    const extras = [];
    const seen = new Set();
    for (const item of raw) {
      const sku = String(typeof item === "string" ? item : item && item.sku ? item.sku : "").trim().toUpperCase();
      if (!sku || seen.has(sku)) continue;
      seen.add(sku);
      const label = typeof item === "object" && item && item.label
        ? String(item.label).trim()
        : "";
      extras.push({ sku, label: label || `自訂 SKU ${sku}` });
    }
    return extras;
  }

  function confirmLiveStart() {
    if (els.testMode.checked) return true;
    if (!window.confirm(LIVE_CONFIRM)) {
      appendLog({
        ts: new Date().toISOString(),
        worker: "frontend",
        level: "warn",
        message: "使用者取消真實下單啟動，沒有開始搶貨。",
      });
      return false;
    }
    return true;
  }

  function saveJson(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
    ));
  }

  function uid() {
    return crypto.randomUUID ? crypto.randomUUID() : `w_${Date.now()}_${Math.random()}`;
  }

  const ACTIVE_STATUSES = new Set([
    "logging_in", "launching", "watching", "checking_out",
    "dry_run_paused", "completed", "stopped", "paused",
    "browser_closed", "error",
  ]);

  function cardDigits(value) {
    return String(value || "").replace(/\D/g, "");
  }

  function isMaskedCard(value) {
    return /[•*]/.test(String(value || ""));
  }

  function isMaskedCvv(value) {
    return /^[•*]{3,4}$/.test(String(value || "").trim());
  }

  function maskedCvvValue() {
    return "•••";
  }

  function statusLabel(status, worker) {
    if (worker && isGuestMode(worker) && !ACTIVE_STATUSES.has(status)) {
      return guestReady(worker) ? "待命（已填妥資料）" : "尚未填妥訪客資料";
    }
    return STATUS_LABELS[status] || STATUS_LABELS.idle;
  }

  function guestReady(worker) {
    return isGuestMode(worker) && !isDirty(worker) && guestMissing(worker).length === 0;
  }

  function displayStatus(worker) {
    const status = worker.status || "needs_login";
    if (ACTIVE_STATUSES.has(status)) return status;
    if (isGuestMode(worker)) return guestReady(worker) ? "ready" : "needs_login";
    return status;
  }

  function emptyGuest() {
    return {
      last_name: "",
      first_name: "",
      email: "",
      phone: "",
      address: "",
      address_street: "",
      address_building: "",
      card_number: "",
      card_month: "",
      card_year: "",
      cvv: "",
    };
  }

  function nextWorkerNumber() {
    const used = new Set(
      state.workers
        .map((worker) => String(worker.name || "").match(/^Worker_(\d+)$/i))
        .filter(Boolean)
        .map((match) => Number(match[1]))
    );
    let n = 1;
    while (used.has(n)) n += 1;
    return n;
  }

  function defaultWorker() {
    const id = uid();
    const n = nextWorkerNumber();
    const short = String(id).replace(/[^a-zA-Z0-9]/g, "").slice(0, 12) || String(Date.now());
    return {
      id,
      name: `Worker_${n}`,
      session_dir: `session_${short}`,
      sku: "MK2E4ZA/A",
      stores: ["R428"],
      pickup_window: "1d",
      max_qty: 1,
      checkout_mode: "apple_id",
      fulfillment: "pickup",
      delivery_max_days: 7,
      guest: emptyGuest(),
      status: "needs_login",
      last_message: "",
      purchased: 0,
      apple_id: "",
      logged_in: false,
      sniping: false,
    };
  }

  function isGuestMode(worker) {
    return (worker.checkout_mode || "apple_id") === "guest";
  }

  function isDelivery(worker) {
    return (worker.fulfillment || "pickup") === "delivery";
  }

  function redactGuest(guest) {
    const data = { ...emptyGuest(), ...(guest || {}) };
    const digits = String(data.card_number || "").replace(/\D/g, "");
    data.card_number = digits.length >= 4 ? `•••• ${digits.slice(-4)}` : "";
    data.cvv = "";
    return data;
  }

  function guestHasMaskedCard(guest) {
    const value = String((guest || {}).card_number || "").trim();
    return isMaskedCard(value) && cardDigits(value).length >= 4;
  }

  function guestHasStoredCard(worker) {
    return guestHasMaskedCard(worker?.guest) || guestHasMaskedCard(savedProfile(worker?.id)?.guest);
  }

  function guestCardStatusText(guest) {
    if (guestHasMaskedCard(guest)) {
      return `已儲存信用卡 ${String(guest.card_number).trim()}，CVV 已加密存放（畫面顯示圓點）。要換卡先至改 16 位同新 CVV。`;
    }
    return "未儲存信用卡。請填 16 位卡號同 CVV。";
  }

  function guestMissing(worker) {
    const guest = { ...emptyGuest(), ...(worker.guest || {}) };
    if (!guest.address_street && guest.address) guest.address_street = guest.address;
    const storedCard = guestHasStoredCard(worker);
    const replacingCard = !isMaskedCard(guest.card_number) && cardDigits(guest.card_number).length === 16;
    return GUEST_FIELDS.filter(([key]) => {
      const value = String(guest[key] || "").trim();
      if (key === "card_number") {
        if (guestHasMaskedCard(guest) || (storedCard && !value)) return false;
        return cardDigits(value).length !== 16;
      }
      if (key === "cvv") {
        if (isMaskedCvv(value) || !value) {
          return replacingCard || (!storedCard && !guestHasMaskedCard(guest));
        }
        const digits = cardDigits(value);
        return digits.length < 3 || digits.length > 4;
      }
      return !value;
    }).map(([, label]) => label);
  }

  function allProducts() {
    const extras = normalizeExtraSkus(state.extraSkus);
    const seen = new Set();
    return [...state.catalog.products, ...extras].filter((item) => {
      if (seen.has(item.sku)) return false;
      seen.add(item.sku);
      return true;
    });
  }

  function fallbackSku() {
    return (state.catalog.products[0] && state.catalog.products[0].sku) || "MK2E4ZA/A";
  }

  function extraSkuListHtml() {
    const extras = normalizeExtraSkus(state.extraSkus);
    if (!extras.length) return "";
    return `
      <p class="help extra-sku-caption">已加入嘅自訂 SKU（打錯可以刪；內建機型刪唔到）</p>
      <ul class="extra-sku-list">
        ${extras.map((item) => `
          <li>
            <span>${esc(item.label)} <code>${esc(item.sku)}</code></span>
            <button type="button" class="btn remove-sku" data-sku="${esc(item.sku)}">刪除</button>
          </li>
        `).join("")}
      </ul>
    `;
  }

  function serializeWorkers(workers, { redact = true } = {}) {
    return workers.map((worker) => ({
      id: worker.id,
      name: worker.name,
      session_dir: worker.session_dir || (isGuestMode(worker) ? `session_guest_${worker.id}` : ""),
      sku: worker.sku,
      stores: isDelivery(worker) ? [] : (worker.stores || []),
      pickup_window: worker.pickup_window || "1d",
      max_qty: worker.max_qty,
      checkout_mode: worker.checkout_mode || "apple_id",
      fulfillment: worker.fulfillment || "pickup",
      delivery_max_days: Number(worker.delivery_max_days || 7),
      guest: redact ? redactGuest(worker.guest) : { ...emptyGuest(), ...(worker.guest || {}) },
    }));
  }

  function profileOf(worker) {
    return serializeWorkers([worker], { redact: true })[0];
  }

  function apiProfile(worker) {
    return serializeWorkers([worker], { redact: false })[0];
  }

  function savedProfile(id) {
    return (state.savedWorkers || []).find((item) => item.id === id);
  }

  function isDirty(worker) {
    const saved = savedProfile(worker.id);
    if (!saved) return true;
    if (JSON.stringify(profileOf(worker)) !== JSON.stringify(saved)) return true;
    if (!isGuestMode(worker)) return false;
    const card = String(worker.guest?.card_number || "").trim();
    if (card && !isMaskedCard(card) && cardDigits(card).length === 16) return true;
    const cvv = cardDigits(worker.guest?.cvv);
    return cvv.length >= 3 && cvv.length <= 4;
  }

  function unsavedWorkers() {
    return state.workers.filter(isDirty);
  }

  function collapsedSet() {
    return new Set(loadJson(STORAGE_COLLAPSED, []));
  }

  function setCollapsed(id, collapsed) {
    const ids = collapsedSet();
    if (collapsed) ids.add(id);
    else ids.delete(id);
    saveJson(STORAGE_COLLAPSED, [...ids]);
  }

  function collapseWorkerCard(id) {
    setCollapsed(id, true);
    const card = els.list.querySelector(`[data-id="${CSS.escape(id)}"]`);
    if (!card) return;
    card.classList.add("is-collapsed");
    const toggle = card.querySelector(".collapse-toggle");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
  }

  function persistDraft() {
    saveJson(STORAGE_PROFILES, serializeWorkers(state.workers));
    saveJson(STORAGE_SKUS, state.extraSkus);
    localStorage.setItem(STORAGE_MODE, els.testMode.checked ? "1" : "0");
  }

  function updateCardSaveState(worker) {
    const card = els.list.querySelector(`[data-id="${CSS.escape(worker.id)}"]`);
    if (!card) return;
    const dirty = isDirty(worker);
    const sniping = Boolean(worker.sniping);
    const hint = card.querySelector(".save-hint-one");
    const button = card.querySelector(".save-one");
    if (button) button.disabled = sniping || !dirty;
    if (!hint) return;
    if (sniping) {
      hint.className = "save-hint-one locked";
      hint.textContent = "運作中已鎖定。請先「暫停運作」先至可以改同儲存。";
      return;
    }
    if (isGuestMode(worker)) {
      const missing = guestMissing(worker);
      if (missing.length) {
        if (button) button.disabled = true;
        hint.className = "save-hint-one dirty";
        hint.textContent = `訪客模式請填妥：${missing.join("、")}。填晒先可以儲存同開始運作。`;
        return;
      }
    }
    if (dirty) {
      hint.className = "save-hint-one dirty";
      hint.textContent = "此 Worker 有未儲存變更。";
      return;
    }
    hint.className = "save-hint-one saved";
    hint.textContent = "此 Worker 已儲存。";
  }

  function updateSaveHint() {
    const unsaved = unsavedWorkers();
    state.dirty = unsaved.length > 0;
    if (els.saveHint) {
      if (!state.workers.length) {
        els.saveHint.className = "save-hint dirty";
        els.saveHint.textContent = "而家未有 Worker。請撳「新增 Worker」加入搶購程序。";
      } else if (unsaved.length) {
        els.saveHint.className = "save-hint dirty";
        els.saveHint.textContent = `仲有 ${unsaved.length} 個未儲存：${unsaved.map((item) => item.name || "未命名").join("、")}。請喺該卡撳「儲存此 Worker」。`;
      } else {
        els.saveHint.className = "save-hint saved";
        els.saveHint.textContent = `全部 ${state.workers.length} 個 Worker 已各自儲存。`;
      }
    }
    state.workers.forEach(updateCardSaveState);
    updateStartGate();
  }

  function readCardsIntoState() {
    const cards = [...els.list.querySelectorAll(".worker-card")].filter((card) => card.dataset.removing !== "true");
    if (!cards.length) {
      if (![...els.list.querySelectorAll(".worker-card")].length) state.workers = [];
      return;
    }
    state.workers = cards.map((card) => {
      const prev = state.workers.find((item) => item.id === card.dataset.id) || {};
      const sniping = card.dataset.sniping === "true" || Boolean(prev.sniping);
      if (sniping) {
        return {
          ...prev,
          id: card.dataset.id,
          status: card.dataset.status || prev.status || "watching",
          last_message: card.dataset.message || prev.last_message || "",
          purchased: Number(card.dataset.purchased || prev.purchased || 0),
          sniping: true,
        };
      }
      const stores = [...card.querySelectorAll(".store:checked")].map((box) => box.value);
      const checkoutMode = card.querySelector(".checkout-mode")?.value || prev.checkout_mode || "apple_id";
      const fulfillment = card.querySelector(".fulfillment")?.value || prev.fulfillment || "pickup";
      const sessionDir = card.querySelector(".session")?.value.trim()
        || prev.session_dir
        || (checkoutMode === "guest" ? `session_guest_${card.dataset.id}` : "");
      return {
        id: card.dataset.id,
        name: card.querySelector(".name").value.trim(),
        session_dir: sessionDir,
        sku: card.querySelector(".sku").value.trim(),
        stores,
        pickup_window: card.querySelector(".pickup")?.value || prev.pickup_window || "1d",
        max_qty: Number(card.querySelector(".qty").value || 1),
        checkout_mode: checkoutMode,
        fulfillment,
        delivery_max_days: Number(card.querySelector(".delivery-days")?.value || prev.delivery_max_days || 7),
        guest: {
          last_name: card.querySelector(".guest-last")?.value.trim() || "",
          first_name: card.querySelector(".guest-first")?.value.trim() || "",
          email: card.querySelector(".guest-email")?.value.trim() || "",
          phone: card.querySelector(".guest-phone")?.value.trim() || "",
          address: card.querySelector(".guest-address-street")?.value.trim() || "",
          address_street: card.querySelector(".guest-address-street")?.value.trim() || "",
          address_building: card.querySelector(".guest-address-building")?.value.trim() || "",
          card_number: (() => {
            const typed = card.querySelector(".guest-card")?.value.trim() || "";
            if (typed) return typed;
            const previous = String((prev.guest || {}).card_number || "").trim();
            const savedCard = String((savedProfile(card.dataset.id)?.guest || {}).card_number || "").trim();
            if (guestHasMaskedCard({ card_number: previous })) return previous;
            if (guestHasMaskedCard({ card_number: savedCard })) return savedCard;
            return "";
          })(),
          card_month: card.querySelector(".guest-month")?.value.trim() || "",
          card_year: card.querySelector(".guest-year")?.value.trim() || "",
          cvv: (() => {
            const typed = card.querySelector(".guest-cvv")?.value.trim() || "";
            if (!typed || isMaskedCvv(typed)) return "";
            return typed;
          })(),
        },
        status: card.dataset.status || prev.status || "needs_login",
        last_message: card.dataset.message || prev.last_message || "",
        purchased: Number(card.dataset.purchased || prev.purchased || 0),
        apple_id: prev.apple_id || "",
        logged_in: Boolean(prev.logged_in || prev.apple_id),
        sniping: Boolean(prev.sniping),
        browser_open: Boolean(prev.browser_open),
      };
    });
    persistDraft();
    updateSaveHint();
    state.workers.forEach(patchWorkerStatus);
  }

  function modeHint() {
    els.modeHint.textContent = els.testMode.checked
      ? "開啟時偵測到貨源會停在最後一步，不會扣款。"
      : "關閉時只要偵測到貨就會真實結帳並可能信用卡扣款。";
  }

  function anyBrowserOpen() {
    return state.workers.some((worker) => (
      worker.sniping
      || worker.browser_open
      || worker.status === "logging_in"
      || worker.status === "launching"
      || worker.status === "ready"
      || worker.status === "watching"
      || worker.status === "checking_out"
    ));
  }

  function unloggedWorkers() {
    return state.workers.filter((worker) => !isGuestMode(worker) && !(worker.logged_in || worker.apple_id));
  }

  function incompleteGuestWorkers() {
    return state.workers.filter((worker) => isGuestMode(worker) && guestMissing(worker).length);
  }

  function canRun(worker) {
    if (worker.sniping || isDirty(worker)) return false;
    if (isGuestMode(worker)) return guestMissing(worker).length === 0;
    return Boolean(worker.logged_in || worker.apple_id);
  }

  function updateStartGate() {
    if (!els.start) return;
    const unsaved = unsavedWorkers();
    const unlogged = unloggedWorkers();
    const incompleteGuest = incompleteGuestWorkers();
    const allSniping = state.workers.length > 0 && state.workers.every((worker) => worker.sniping);
    const blocked = !state.workers.length || unsaved.length > 0 || unlogged.length > 0 || incompleteGuest.length > 0 || allSniping;
    els.start.disabled = blocked;
    if (!els.startHint) return;
    if (!state.workers.length) {
      els.startHint.className = "start-hint blocked";
      els.startHint.textContent = "而家未有 Worker。請撳「新增 Worker」加入搶購程序。";
      return;
    }
    if (unsaved.length) {
      els.startHint.className = "start-hint blocked";
      els.startHint.textContent = `請先喺未儲存嘅卡撳「儲存此 Worker」：${unsaved.map((item) => item.name || "未命名").join("、")}`;
      return;
    }
    if (unlogged.length) {
      els.startHint.className = "start-hint blocked";
      els.startHint.textContent = `仲有 ${unlogged.length} 個 Apple ID 模式未登入：${unlogged.map((item) => item.name || "未命名").join("、")}。請登入，或者刪除未登入嘅 Worker。`;
      return;
    }
    if (incompleteGuest.length) {
      els.startHint.className = "start-hint blocked";
      els.startHint.textContent = `訪客模式請填妥個人同信用卡資料：${incompleteGuest.map((item) => item.name || "未命名").join("、")}`;
      return;
    }
    if (allSniping) {
      els.startHint.className = "start-hint ok";
      els.startHint.textContent = "全部 Worker 已在搶機。要停某個請撳「暫停運作」。";
      return;
    }
    els.startHint.className = "start-hint ok";
    els.startHint.textContent = `已備好 ${state.workers.length} 個 Worker，可以全部開始搶機。單個用「開始運作／暫停運作」。`;
  }

  function setRunning(running, testMode) {
    state.running = running;
    updateStartGate();
    els.stop.disabled = !running && !anyBrowserOpen();
    els.add.disabled = false;
    els.testMode.disabled = false;
    if (els.workersPanel) els.workersPanel.classList.toggle("is-running", running);
    if (els.runLock) els.runLock.hidden = !running;
    els.list.querySelectorAll(".worker-card").forEach((card) => {
      const sniping = card.dataset.sniping === "true";
      const loggedIn = card.dataset.loggedIn === "true";
      const worker = state.workers.find((item) => item.id === card.dataset.id);
      card.classList.toggle("is-sniping", sniping);
      card.querySelectorAll("input, select, button.add-sku, button.remove-sku, button.remove").forEach((node) => {
        node.disabled = sniping;
      });
      if (worker) updateCardSaveState(worker);
      const runBtn = card.querySelector(".run-one");
      const pauseBtn = card.querySelector(".pause-one");
      const loginBtn = card.querySelector(".login");
      const focusBtn = card.querySelector(".focus");
      const saved = worker ? !isDirty(worker) : false;
      if (runBtn) runBtn.disabled = worker ? !canRun(worker) : (!loggedIn || sniping || !saved);
      if (pauseBtn) pauseBtn.disabled = !sniping;
      if (loginBtn) loginBtn.disabled = sniping;
      if (focusBtn) focusBtn.disabled = false;
    });
    if (running && testMode === false) {
      els.pill.className = "pill live";
      els.pill.textContent = "運行中 · 真實下單模式";
    } else if (running) {
      els.pill.className = "pill running";
      els.pill.textContent = "運行中 · 測試模式";
    } else if (state.previewMode) {
      els.pill.className = "pill idle";
      els.pill.textContent = "預覽 · 後台未啟動";
    } else {
      els.pill.className = "pill idle";
      els.pill.textContent = "待命 · 等待前端指令";
    }
  }

  function productOptions(selected) {
    const options = allProducts().map((item) => (
      `<option value="${esc(item.sku)}" ${item.sku === selected ? "selected" : ""}>${esc(item.label)}（${esc(item.sku)}）</option>`
    ));
    if (selected && !allProducts().some((item) => item.sku === selected)) {
      options.push(`<option value="${esc(selected)}" selected>自訂 SKU ${esc(selected)}</option>`);
    }
    return options.join("");
  }

  function storeBoxes(selected) {
    return state.catalog.stores.map((store) => `
      <label>
        <input type="checkbox" class="store" value="${esc(store.id)}" ${selected.includes(store.id) ? "checked" : ""} />
        <span>${esc(store.name)} · ${esc(store.area)}</span>
      </label>
    `).join("");
  }

  function pickupOptions(selected) {
    return state.catalog.pickup_windows.map((item) => (
      `<option value="${esc(item.id)}" ${item.id === selected ? "selected" : ""}>${esc(item.label)}</option>`
    )).join("");
  }

  function deliveryOptions(selected) {
    const windows = state.catalog.delivery_windows || FALLBACK_CATALOG.delivery_windows;
    const current = String(selected || 7);
    return windows.map((item) => (
      `<option value="${esc(item.id)}" ${String(item.id) === current || String(item.max_days) === current ? "selected" : ""}>${esc(item.label)}</option>`
    )).join("");
  }

  function yearOptions(selected) {
    const year = new Date().getFullYear();
    const years = Array.from({ length: 12 }, (_, index) => String(year + index));
    return [`<option value="">請選擇</option>`].concat(years.map((value) => {
      const yy = value.slice(-2);
      return `<option value="${esc(value)}" ${String(selected) === value ? "selected" : ""}>${esc(value)}（${esc(yy)}）</option>`;
    })).join("");
  }

  function monthOptions(selected) {
    const months = Array.from({ length: 12 }, (_, index) => String(index + 1).padStart(2, "0"));
    return [`<option value="">請選擇</option>`].concat(months.map((value) => (
      `<option value="${esc(value)}" ${String(selected).padStart(2, "0") === value ? "selected" : ""}>${esc(value)}</option>`
    ))).join("");
  }

  function workerCardHtml(worker, entering) {
    const status = displayStatus(worker);
    const sniping = Boolean(worker.sniping);
    const loggedIn = Boolean(worker.logged_in || worker.apple_id);
    const closed = status === "browser_closed";
    const collapsed = collapsedSet().has(worker.id);
    const email = worker.apple_id || "";
    const saved = !isDirty(worker);
    const guest = { ...emptyGuest(), ...(worker.guest || {}) };
    if (!guest.address_street && guest.address) guest.address_street = guest.address;
    const checkoutMode = worker.checkout_mode || "apple_id";
    const guestIncomplete = checkoutMode === "guest" ? guestMissing(worker) : [];
    const fulfillment = worker.fulfillment || "pickup";
    const note = worker.last_message || (checkoutMode === "guest"
      ? (guestReady(worker)
        ? "訪客資料已填妥並已儲存。可以撳「開始運作」或上面綠色「全部開始搶機」。"
        : "訪客模式：填妥個人同信用卡資料後，撳「儲存此 Worker」就可以開始運作。唔使登入 Apple ID。")
      : (loggedIn
        ? "已登入。可以撳「開始運作」或上面綠色「全部開始搶機」。"
        : "未登入。請先撳「登入 Apple ID」。"));
    const sessionHint = `會儲存在專案資料夾 sessions/${worker.session_dir || "session_worker_1"}。Chromium 把 Apple ID cookie 寫入呢度，下次開同一個資料夾就記得登入。`;
    const meta = `${worker.sku || "未揀 SKU"} · ${checkoutMode === "guest" ? "訪客" : (loggedIn ? (email || "已登入") : "未登入")} · ${fulfillment === "delivery" ? "送貨" : "自取"}`;
    return `
      <article class="worker-card${entering ? " enter" : ""}${sniping ? " is-sniping" : ""}${closed ? " is-closed" : ""}${collapsed ? " is-collapsed" : ""}" data-id="${esc(worker.id)}" data-status="${esc(status)}" data-message="${esc(worker.last_message || "")}" data-purchased="${esc(worker.purchased || 0)}" data-sniping="${sniping}" data-logged-in="${loggedIn}" data-checkout="${esc(checkoutMode)}" data-fulfillment="${esc(fulfillment)}">
        <div class="worker-top">
          <button type="button" class="collapse-toggle" aria-expanded="${collapsed ? "false" : "true"}" aria-label="展開或收合 Worker">▾</button>
          <div class="worker-heading">
            <strong class="worker-title">${esc(worker.name)}</strong>
            <p class="collapsed-meta">${esc(meta)}</p>
          </div>
          <span class="badge ${esc(status)}">${esc(statusLabel(status, worker))}${worker.purchased ? ` · ${worker.purchased}/${worker.max_qty}` : ""}</span>
          <div class="worker-top-actions">
            <button type="button" class="btn run-one" ${canRun(worker) ? "" : "disabled"}>開始運作</button>
            <button type="button" class="btn pause-one" ${sniping ? "" : "disabled"}>暫停運作</button>
          </div>
        </div>
        <div class="worker-body">
        <div class="account-bar ${loggedIn ? "is-in" : "is-out"}">
          <span>Apple ID</span>
          <strong class="account-email">${loggedIn ? esc(email || "已登入") : "未登入"}</strong>
          <button type="button" class="btn login">${closed ? "重新打開瀏覽器" : (loggedIn ? "帶到最前" : "登入 Apple ID")}</button>
        </div>
        <p class="worker-note${closed ? " warn" : ""}">${esc(note)}</p>
        <div class="grid">
          <label class="field">
            <span>Worker 名稱 / 編號</span>
            <input class="name" type="text" value="${esc(worker.name)}" />
          </label>
          <label class="field">
            <span>結帳模式 (Checkout Mode)</span>
            <select class="checkout-mode">
              <option value="apple_id" ${checkoutMode === "apple_id" ? "selected" : ""}>Apple ID 登入模式</option>
              <option value="guest" ${checkoutMode === "guest" ? "selected" : ""}>訪客 (Guest) 模式</option>
            </select>
          </label>
          <label class="field">
            <span>取貨方式 (Fulfillment)</span>
            <select class="fulfillment">
              <option value="pickup" ${fulfillment === "pickup" ? "selected" : ""}>門市自取 (Store Pickup)</option>
              <option value="delivery" ${fulfillment === "delivery" ? "selected" : ""}>送貨上門 (Home Delivery)</option>
            </select>
          </label>
          <label class="field session-field">
            <span>Apple ID Session 資料夾</span>
            <input class="session" type="text" value="${esc(worker.session_dir)}" placeholder="session_worker_1" />
            <p class="help session-path">${esc(sessionHint)}</p>
          </label>
          <div class="field full guest-fields">
            <span>訪客資料（只存在你呢部電腦，唔會上傳 GitHub，亦唔會寫入 Live Log）</span>
            <div class="grid">
              <label class="field"><span>英文姓氏</span><input class="guest-last" type="text" autocomplete="off" value="${esc(guest.last_name)}" /></label>
              <label class="field"><span>英文名字</span><input class="guest-first" type="text" autocomplete="off" value="${esc(guest.first_name)}" /></label>
              <label class="field"><span>電郵地址</span><input class="guest-email" type="email" autocomplete="off" value="${esc(guest.email)}" /></label>
              <label class="field"><span>香港聯絡電話</span><input class="guest-phone" type="tel" autocomplete="off" value="${esc(guest.phone)}" /></label>
              <label class="field full"><span>街道地址（區域、地區、街道名稱及號碼）</span><input class="guest-address-street" type="text" autocomplete="off" value="${esc(guest.address_street || guest.address)}" placeholder="例如 中環金融街 8 號" /></label>
              <label class="field full"><span>屋苑或大廈／座數／樓層／單位</span><input class="guest-address-building" type="text" autocomplete="off" value="${esc(guest.address_building)}" placeholder="例如 國際金融中心一期 15 樓 1501 室" /></label>
              <label class="field full"><span>信用卡號碼（16 個數字）</span><input class="guest-card" type="text" maxlength="19" autocomplete="off" value="${esc(guest.card_number)}" /></label>
              <label class="field"><span>有效月份</span><select class="guest-month">${monthOptions(guest.card_month)}</select></label>
              <label class="field"><span>有效年份</span><select class="guest-year">${yearOptions(guest.card_year)}</select></label>
              <label class="field"><span>CVV 安全碼</span><input class="guest-cvv" type="password" maxlength="4" autocomplete="new-password" value="${guestHasMaskedCard(guest) ? maskedCvvValue() : esc(guest.cvv)}" /></label>
            </div>
            <p class="help guest-card-status">${esc(guestCardStatusText(guest))}</p>
            <p class="help">第一次要填晒全部欄位先可以儲存。儲存後仍然睇到已填資料：卡號顯示 •••• 後四位，CVV 顯示成圓點，代表已經有資料。打錯姓名／地址可以再改再存。要換卡先至要填新嘅 16 位卡號同 CVV。官網帳單地址有兩欄：第一欄填區域／地區／街道名稱及號碼，第二欄填屋苑或大廈／座數／樓層／單位。控制台年份顯示 2028，填入 Apple 官網時會轉成 MM/YY（例如 12/28），唔會填 12/2028。卡號同 CVV 只會加密寫入本機 secrets 資料夾。</p>
          </div>
          <div class="field full sku-block">
            <span>1. 目標機型（每個 Worker 只搶一個 SKU）</span>
            <select class="sku" aria-label="目標機型 SKU">${productOptions(worker.sku)}</select>
            <span>2. 或者輸入任何 Apple 產品 SKU（唔限 iPhone）再加入選單</span>
            <div class="sku-add">
              <input class="sku-custom" type="text" placeholder="SKU，例如 MK2E4ZA/A" />
              <input class="sku-label" type="text" placeholder="產品名稱（可留空）" />
              <button type="button" class="btn add-sku">加入此 SKU</button>
            </div>
            <div class="extra-sku-wrap">${extraSkuListHtml()}</div>
            <p class="help">唔限 iPhone，AirPods / Mac 等只要香港門市取貨適用都得。名稱留空會顯示「自訂 SKU + 編號」。加入後會記住喺呢個瀏覽器嘅下拉選單（清瀏覽器資料就會消失）。打錯自訂 SKU 可以喺上面撳「刪除」；內建 Duo 機型刪唔到。每個 Worker 只搶一個 SKU。</p>
          </div>
          <div class="field full pickup-fields">
            <span>香港指定門市（可複選）</span>
            <div class="stores">${storeBoxes(worker.stores || [])}</div>
          </div>
          <label class="field pickup-fields">
            <span>取貨時間限制</span>
            <select class="pickup">${pickupOptions(worker.pickup_window)}</select>
          </label>
          <label class="field full delivery-fields">
            <span>送貨時效限制（最快必須在幾日內送達）</span>
            <select class="delivery-days">${deliveryOptions(worker.delivery_max_days)}</select>
            <p class="help">官網預計送達日如果超出呢個日數，呢次機會會放棄，繼續監察。</p>
          </label>
          <label class="field full">
            <span>購買數量上限（此 Worker 全部門市合計）</span>
            <input class="qty" type="number" min="1" max="99" value="${esc(worker.max_qty)}" />
            <p class="help">複選 ifc + 沙田、上限填 2：最多搶 2 部（例如購物袋一次揀 2，或分兩次）。唔係每間門市各 2 部。加車入袋後會喺數量下拉揀呢個剩餘數量。Apple 同一型號通常每人最多 2 部。同一個 Apple ID 開多個 Worker 會各自再計一次上限。</p>
          </label>
        </div>
        <div class="card-save">
          <button type="button" class="btn save save-one" ${sniping || saved || guestIncomplete.length ? "disabled" : ""}>儲存此 Worker</button>
          <p class="save-hint-one ${sniping ? "locked" : (guestIncomplete.length || !saved ? "dirty" : "saved")}">${sniping ? "運作中已鎖定。請先「暫停運作」先至可以改同儲存。" : (guestIncomplete.length ? `訪客模式請填妥：${guestIncomplete.join("、")}。填晒先可以儲存同開始運作。` : (saved ? "此 Worker 已儲存。" : "此 Worker 有未儲存變更。"))}</p>
        </div>
        <div class="card-actions">
          <button type="button" class="btn focus">顯示此 Worker 視窗</button>
          <button type="button" class="btn remove">刪除此 Worker</button>
        </div>
        </div>
      </article>
    `;
  }

  function syncEmptyState() {
    if (els.empty) els.empty.hidden = state.workers.length > 0;
  }

  function renderWorkers() {
    els.list.innerHTML = state.workers.map((worker) => workerCardHtml(worker, false)).join("");
    syncEmptyState();
    setRunning(state.running, els.testMode.checked);
    updateSaveHint();
  }

  function mountWorker(worker) {
    els.list.insertAdjacentHTML("beforeend", workerCardHtml(worker, true));
    const card = els.list.querySelector(`[data-id="${worker.id}"]`);
    if (card) {
      card.addEventListener("animationend", () => card.classList.remove("enter"), { once: true });
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    syncEmptyState();
    setRunning(state.running, els.testMode.checked);
    updateSaveHint();
  }

  function patchWorkerStatus(worker) {
    const card = els.list.querySelector(`[data-id="${CSS.escape(worker.id)}"]`);
    if (!card) return;
    const status = displayStatus(worker);
    const sniping = Boolean(worker.sniping);
    const loggedIn = Boolean(worker.logged_in || worker.apple_id);
    const closed = status === "browser_closed";
    card.dataset.status = status;
    card.dataset.purchased = String(worker.purchased || 0);
    card.dataset.sniping = String(sniping);
    card.dataset.loggedIn = String(loggedIn);
    card.dataset.message = worker.last_message || "";
    card.classList.toggle("is-sniping", sniping);
    card.classList.toggle("is-closed", closed);
    const badge = card.querySelector(".badge");
    if (badge) {
      badge.className = `badge ${status}`;
      badge.textContent = `${statusLabel(status, worker)}${worker.purchased ? ` · ${worker.purchased}/${worker.max_qty}` : ""}`;
    }
    const title = card.querySelector(".worker-title");
    if (title && worker.name) title.textContent = worker.name;
    const email = card.querySelector(".account-email");
    if (email) email.textContent = loggedIn ? (worker.apple_id || "已登入") : "未登入";
    const accountBar = card.querySelector(".account-bar");
    if (accountBar) {
      accountBar.classList.toggle("is-in", loggedIn);
      accountBar.classList.toggle("is-out", !loggedIn);
    }
    const loginBtn = card.querySelector(".login");
    if (loginBtn) {
      loginBtn.textContent = closed ? "重新打開瀏覽器" : (loggedIn ? "帶到最前" : "登入 Apple ID");
      loginBtn.disabled = sniping;
    }
    const note = card.querySelector(".worker-note");
    if (note) {
      note.classList.toggle("warn", closed);
      note.textContent = worker.last_message || (isGuestMode(worker)
        ? (guestReady(worker)
          ? "訪客資料已填妥並已儲存。可以撳「開始運作」或上面綠色「全部開始搶機」。"
          : "訪客模式：填妥個人同信用卡資料後，撳「儲存此 Worker」就可以開始運作。唔使登入 Apple ID。")
        : (loggedIn
          ? "已登入。可以撳「開始運作」或上面綠色「全部開始搶機」。"
          : "未登入。請先撳「登入 Apple ID」。"));
    }
    const cardStatus = card.querySelector(".guest-card-status");
    if (cardStatus) cardStatus.textContent = guestCardStatusText(worker.guest || {});
    const cardInput = card.querySelector(".guest-card");
    const cvvInput = card.querySelector(".guest-cvv");
    if (cardInput && guestHasMaskedCard(worker.guest) && (!cardInput.value || isMaskedCard(cardInput.value))) {
      cardInput.value = String(worker.guest.card_number || "").trim();
    }
    if (cvvInput && guestHasMaskedCard(worker.guest) && !cardDigits(cvvInput.value)) {
      cvvInput.value = maskedCvvValue();
    }
    const meta = card.querySelector(".collapsed-meta");
    if (meta) {
      const guestBit = isGuestMode(worker)
        ? (guestReady(worker) ? "訪客已填妥" : "訪客")
        : (loggedIn ? (worker.apple_id || "已登入") : "未登入");
      const fulfillBit = isDelivery(worker) ? "送貨" : "自取";
      meta.textContent = `${worker.sku || "未揀 SKU"} · ${guestBit} · ${fulfillBit}`;
    }
    const runBtn = card.querySelector(".run-one");
    const pauseBtn = card.querySelector(".pause-one");
    const saved = !isDirty(worker);
    if (runBtn) runBtn.disabled = !canRun(worker);
    if (pauseBtn) pauseBtn.disabled = !sniping;
    updateCardSaveState(worker);
  }

  function refreshSkuDropdowns(selectId, sku) {
    els.list.querySelectorAll("select.sku").forEach((select) => {
      const cardId = select.closest(".worker-card")?.dataset.id;
      const worker = state.workers.find((item) => item.id === cardId);
      const value = cardId === selectId ? sku : (worker?.sku || select.value);
      select.innerHTML = productOptions(value);
      select.value = value;
    });
    els.list.querySelectorAll(".extra-sku-wrap").forEach((wrap) => {
      wrap.innerHTML = extraSkuListHtml();
    });
  }

  function appendLog(item) {
    const line = document.createElement("p");
    line.className = `log-line ${esc(item.level || "info")}`;
    line.innerHTML = `<span class="meta">[${esc(item.ts || "")}] [${esc(item.worker || "system")}]</span> ${esc(item.message || "")}`;
    els.logs.appendChild(line);
    if (state.stickLogs) {
      els.logs.scrollTop = els.logs.scrollHeight;
    }
  }

  async function api(path, options) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail;
      if (typeof detail === "string") throw new Error(detail);
      if (Array.isArray(detail)) {
        throw new Error(detail.map((item) => item.msg || JSON.stringify(item)).join("；"));
      }
      throw new Error(data.message || `HTTP ${response.status}`);
    }
    return data;
  }

  function applyStatus(data) {
    if (!data) return;
    if (Array.isArray(data.workers) && data.workers.length) {
      const byId = new Map(data.workers.map((item) => [item.id, item]));
      state.workers = state.workers.map((worker) => {
        const incoming = byId.get(worker.id) || {};
        const guest = { ...(worker.guest || {}), ...(incoming.guest || {}) };
        if (!(incoming.guest && incoming.guest.cvv)) guest.cvv = (worker.guest || {}).cvv || "";
        const incomingCard = String((incoming.guest || {}).card_number || "");
        const localCard = String((worker.guest || {}).card_number || "");
        if (incomingCard.includes("•") && localCard.replace(/\D/g, "").length >= 12) {
          guest.card_number = localCard;
        }
        return { ...worker, ...incoming, guest };
      });
      data.workers.forEach((item) => {
        const local = state.workers.find((worker) => worker.id === item.id);
        if (!local) return;
        patchWorkerStatus({ ...item, ...local });
      });
    }
    setRunning(Boolean(data.running), data.test_mode);
  }

  function enterPreviewMode(reason) {
    state.previewMode = true;
    state.catalog = FALLBACK_CATALOG;
    const banner = document.getElementById("preview-banner");
    if (banner) banner.hidden = false;
    els.pill.className = "pill idle";
    els.pill.textContent = "預覽 · 後台未啟動";
    appendLog({
      ts: new Date().toISOString(),
      worker: "frontend",
      level: "warn",
      message: reason || "未連到後台，已切換為預覽模式。設定同儲存都可以試，但唔會開瀏覽器、唔會下單。",
    });
  }

  async function removeWorker(id) {
    readCardsIntoState();
    const worker = state.workers.find((item) => item.id === id);
    if (!worker) return;
    if (worker.sniping) {
      window.alert("呢個 Worker 運作中，請先「暫停運作」再刪除。");
      return;
    }
    const card = els.list.querySelector(`[data-id="${CSS.escape(id)}"]`);
    if (card) card.dataset.removing = "true";
    const sessionDir = worker.session_dir || "";
    const name = worker.name || id;
    state.workers = state.workers.filter((item) => item.id !== id);
    state.savedWorkers = state.savedWorkers.filter((item) => item.id !== id);
    saveJson(STORAGE_SAVED, state.savedWorkers);
    const collapsed = collapsedSet();
    collapsed.delete(id);
    saveJson(STORAGE_COLLAPSED, [...collapsed]);
    persistDraft();
    if (card && card.parentNode) card.remove();
    syncEmptyState();
    updateSaveHint();
    setRunning(state.running, els.testMode.checked);
    if (!state.previewMode) {
      try {
        const query = sessionDir ? `?session_dir=${encodeURIComponent(sessionDir)}` : "";
        await api(`/api/workers/${encodeURIComponent(id)}${query}`, { method: "DELETE" });
      } catch (err) {
        appendLog({ ts: new Date().toISOString(), worker: name, level: "error", message: err.message });
      }
    }
    appendLog({
      ts: new Date().toISOString(),
      worker: name,
      level: "success",
      message: `已刪除 ${name}，連本機 session／訪客加密資料都清咗。`,
    });
  }

  async function saveOne(id) {
    const card = els.list.querySelector(`[data-id="${CSS.escape(id)}"]`);
    if (card && card.dataset.sniping === "true") {
      window.alert("呢個 Worker 運作中，設定已鎖定。請先「暫停運作」再改同儲存。");
      return false;
    }
    readCardsIntoState();
    const worker = state.workers.find((item) => item.id === id);
    if (!worker) return false;
    if (worker.sniping) {
      window.alert("呢個 Worker 運作中，設定已鎖定。請先「暫停運作」再改同儲存。");
      return false;
    }
    if (!worker.name || !worker.sku) {
      window.alert("此 Worker 要有名稱同目標機型。");
      return false;
    }
    if (!isGuestMode(worker) && !worker.session_dir) {
      window.alert("Apple ID 模式必須填寫 Session 資料夾路徑。");
      return false;
    }
    if (isGuestMode(worker)) {
      const missing = guestMissing(worker);
      if (missing.length) {
        window.alert(`訪客模式請填妥：${missing.join("、")}`);
        return false;
      }
      if (!worker.session_dir) worker.session_dir = `session_guest_${worker.id}`;
    }
    if (!isDelivery(worker) && !(worker.stores || []).length) {
      window.alert("門市自取必須至少揀一間香港門市。");
      return false;
    }
    const clash = state.savedWorkers.find((item) => item.id !== worker.id && item.session_dir === worker.session_dir);
    const liveClash = state.workers.find((item) => item.id !== worker.id && item.session_dir === worker.session_dir);
    if (clash || liveClash) {
      window.alert("每個 Worker 要用唔同嘅 session 資料夾，唔好共用。");
      return false;
    }
    const secretPayload = isGuestMode(worker) && !state.previewMode ? apiProfile(worker) : null;
    const guestResave = isGuestMode(worker) && Boolean(savedProfile(worker.id));
    if (secretPayload) {
      try {
        await api("/api/workers/secrets", {
          method: "POST",
          body: JSON.stringify({ test_mode: els.testMode.checked, worker: secretPayload }),
        });
      } catch (err) {
        appendLog({ ts: new Date().toISOString(), worker: worker.name, level: "error", message: err.message });
        window.alert(`訪客信用卡儲存失敗：${err.message}`);
        return false;
      }
    }
    const profile = profileOf(worker);
    const index = state.savedWorkers.findIndex((item) => item.id === worker.id);
    if (index >= 0) state.savedWorkers[index] = profile;
    else state.savedWorkers.push(profile);
    state.savedWorkers = state.savedWorkers.filter((item) => state.workers.some((workerItem) => workerItem.id === item.id));
    saveJson(STORAGE_SAVED, state.savedWorkers);
    persistDraft();
    if (isGuestMode(worker)) {
      worker.guest = redactGuest(worker.guest);
      persistDraft();
      if (card) {
        const cardInput = card.querySelector(".guest-card");
        const cvvInput = card.querySelector(".guest-cvv");
        if (cardInput) cardInput.value = worker.guest.card_number;
        if (cvvInput) cvvInput.value = maskedCvvValue();
      }
      worker.status = "ready";
      worker.last_message = "訪客資料已填妥並已儲存。卡號同 CVV 已加密存放，畫面會顯示後四位同圓點。";
    }
    updateSaveHint();
    patchWorkerStatus(worker);
    collapseWorkerCard(worker.id);
    appendLog({
      ts: new Date().toISOString(),
      worker: worker.name,
      level: "success",
      message: guestResave ? `${worker.name} 訪客資料已修改成功` : "已儲存此 Worker 設定。",
    });
    return true;
  }

  async function start() {
    readCardsIntoState();
    const unsaved = unsavedWorkers();
    if (unsaved.length) {
      window.alert(`請先喺未儲存嘅卡撳「儲存此 Worker」：${unsaved.map((item) => item.name).join("、")}`);
      updateStartGate();
      return;
    }
    const unlogged = unloggedWorkers();
    if (unlogged.length) {
      window.alert(`仲有 Apple ID 模式 Worker 未登入：${unlogged.map((item) => item.name).join("、")}。請登入，或者刪除未登入嘅 Worker。`);
      updateStartGate();
      return;
    }
    const incompleteGuest = incompleteGuestWorkers();
    if (incompleteGuest.length) {
      window.alert(`訪客模式請填妥個人同信用卡資料：${incompleteGuest.map((item) => `${item.name}（${guestMissing(item).join("、")}）`).join("；")}`);
      updateStartGate();
      return;
    }
    if (!confirmLiveStart()) return;
    if (state.previewMode) {
      state.workers.forEach((worker) => {
        worker.sniping = true;
        worker.status = "watching";
        worker.last_message = "預覽模式：模擬全部開始搶機。真正搶機請用 python app.py。";
        patchWorkerStatus(worker);
      });
      setRunning(true, els.testMode.checked);
      appendLog({
        ts: new Date().toISOString(),
        worker: "frontend",
        level: "success",
        message: "預覽模式：已模擬全部開始搶機。真正開瀏覽器請用 python app.py。",
      });
      return;
    }
    els.start.disabled = true;
    try {
      const data = await api("/api/start", {
        method: "POST",
        body: JSON.stringify({
          test_mode: els.testMode.checked,
          workers: serializeWorkers(state.workers, { redact: false }),
        }),
      });
      applyStatus(data);
    } catch (err) {
      updateStartGate();
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "error", message: err.message });
    }
  }

  async function stop() {
    if (state.previewMode) {
      window.alert(PREVIEW_ALERT);
      return;
    }
    try {
      const data = await api("/api/stop", { method: "POST" });
      applyStatus(data);
    } catch (err) {
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "error", message: err.message });
    }
  }

  function currentWorkerPayload(id) {
    readCardsIntoState();
    const worker = state.workers.find((item) => item.id === id);
    if (!worker) throw new Error("找不到這個 Worker");
    return {
      test_mode: els.testMode.checked,
      worker: apiProfile(worker),
    };
  }

  async function loginWorker(id) {
    readCardsIntoState();
    const current = state.workers.find((item) => item.id === id);
    if (!current) return;
    if (current.sniping) {
      window.alert("呢個 Worker 運作中。請先「暫停運作」。");
      return;
    }
    if (isDirty(current)) {
      window.alert("請先撳「儲存此 Worker」，再登入 Apple ID。");
      return;
    }
    if (state.previewMode) {
      const worker = state.workers.find((item) => item.id === id);
      if (worker) {
        worker.apple_id = "preview.user@icloud.com";
        worker.logged_in = true;
        worker.status = "ready";
        worker.browser_open = true;
        patchWorkerStatus(worker);
        setRunning(state.workers.some((item) => item.sniping), els.testMode.checked);
      }
      appendLog({
        ts: new Date().toISOString(),
        worker: worker ? worker.name : "frontend",
        level: "success",
        message: "預覽模式：模擬已登入 preview.user@icloud.com。真正登入請用 python app.py。",
      });
      return;
    }
    try {
      applyStatus(await api("/api/workers/login", {
        method: "POST",
        body: JSON.stringify(currentWorkerPayload(id)),
      }));
    } catch (err) {
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "error", message: err.message });
    }
  }

  async function runOne(id) {
    readCardsIntoState();
    const worker = state.workers.find((item) => item.id === id);
    if (!worker) return;
    if (isDirty(worker)) {
      window.alert("請先撳「儲存此 Worker」，再開始運作。");
      return;
    }
    if (isGuestMode(worker)) {
      const missing = guestMissing(worker);
      if (missing.length) {
        window.alert(`訪客模式請填妥：${missing.join("、")}`);
        return;
      }
    } else if (!(worker.logged_in || worker.apple_id)) {
      window.alert("請先撳「登入 Apple ID」，登入成功後先可以開始運作。");
      return;
    }
    if (!confirmLiveStart()) return;
    if (state.previewMode) {
      worker.sniping = true;
      worker.status = "watching";
        worker.last_message = "預覽模式：已開始運作。真正搶機請用 python app.py。";
        patchWorkerStatus(worker);
        setRunning(true, els.testMode.checked);
        appendLog({
          ts: new Date().toISOString(),
          worker: worker.name,
          level: "success",
          message: "預覽模式：已模擬開始運作。",
        });
      return;
    }
    try {
      applyStatus(await api("/api/workers/run", {
        method: "POST",
        body: JSON.stringify(currentWorkerPayload(id)),
      }));
    } catch (err) {
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "error", message: err.message });
    }
  }

  async function pauseOne(id) {
    if (state.previewMode) {
      const worker = state.workers.find((item) => item.id === id);
      if (worker) {
        worker.sniping = false;
        worker.status = worker.logged_in || worker.apple_id ? "ready" : "needs_login";
        worker.last_message = "預覽模式：已暫停運作。撳「開始運作」即可再搶。";
        patchWorkerStatus(worker);
      }
      setRunning(state.workers.some((item) => item.sniping), els.testMode.checked);
      appendLog({
        ts: new Date().toISOString(),
        worker: worker ? worker.name : "frontend",
        level: "info",
        message: "預覽模式：已模擬暫停。登入狀態仍然保留，撳「開始運作」即可再搶。",
      });
      return;
    }
    try {
      applyStatus(await api(`/api/workers/${encodeURIComponent(id)}/pause`, { method: "POST" }));
    } catch (err) {
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "error", message: err.message });
    }
  }

  async function focusWorker(id) {
    if (state.previewMode) {
      window.alert(PREVIEW_ALERT);
      return;
    }
    try {
      await api(`/api/workers/${encodeURIComponent(id)}/focus`, { method: "POST" });
    } catch (err) {
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "error", message: err.message });
    }
  }

  function connectLogs() {
    if (state.previewMode || location.protocol === "file:") {
      return;
    }
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${location.host}/ws/logs`);
    socket.addEventListener("message", (event) => {
      try {
        appendLog(JSON.parse(event.data));
      } catch {
        appendLog({ message: event.data, level: "info" });
      }
    });
    socket.addEventListener("close", () => {
      setTimeout(connectLogs, 1200);
    });
  }

  els.list.addEventListener("input", (event) => {
    if (event.target.classList.contains("guest-card") && !isMaskedCard(event.target.value)) {
      const digits = cardDigits(event.target.value).slice(0, 16);
      if (event.target.value !== digits) event.target.value = digits;
    }
    readCardsIntoState();
  });
  els.list.addEventListener("change", (event) => {
    const card = event.target.closest(".worker-card");
    if (card && event.target.classList.contains("checkout-mode")) {
      card.dataset.checkout = event.target.value;
    }
    if (card && event.target.classList.contains("fulfillment")) {
      card.dataset.fulfillment = event.target.value;
    }
    readCardsIntoState();
  });
  els.list.addEventListener("click", (event) => {
    const card = event.target.closest(".worker-card");
    if (!card) return;
    if (event.target.closest(".collapse-toggle")) {
      const collapsed = !card.classList.contains("is-collapsed");
      card.classList.toggle("is-collapsed", collapsed);
      const toggle = card.querySelector(".collapse-toggle");
      if (toggle) toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      setCollapsed(card.dataset.id, collapsed);
      return;
    }
    if (event.target.closest(".login")) {
      loginWorker(card.dataset.id);
      return;
    }
    if (event.target.closest(".run-one")) {
      runOne(card.dataset.id);
      return;
    }
    if (event.target.closest(".pause-one")) {
      pauseOne(card.dataset.id);
      return;
    }
    if (event.target.closest(".save-one")) {
      saveOne(card.dataset.id);
      return;
    }
    if (event.target.closest(".remove")) {
      removeWorker(card.dataset.id);
      return;
    }
    if (event.target.closest(".focus")) {
      focusWorker(card.dataset.id);
    }
    if (event.target.closest(".remove-sku")) {
      if (card.dataset.sniping === "true") return;
      const sku = (event.target.closest(".remove-sku").dataset.sku || "").trim().toUpperCase();
      if (!sku) return;
      readCardsIntoState();
      const snipingUsers = state.workers.filter((worker) => worker.sku === sku && worker.sniping);
      if (snipingUsers.length) {
        window.alert(`有 Worker 正用呢個 SKU 搶機（${snipingUsers.map((item) => item.name || "未命名").join("、")}）。請先暫停運作再刪。`);
        return;
      }
      const extras = normalizeExtraSkus(state.extraSkus);
      if (!extras.some((item) => item.sku === sku)) return;
      state.extraSkus = extras.filter((item) => item.sku !== sku);
      const fallback = fallbackSku();
      const switched = [];
      state.workers.forEach((worker) => {
        if (worker.sku === sku) {
          worker.sku = fallback;
          switched.push(worker.name || "未命名");
        }
      });
      persistDraft();
      refreshSkuDropdowns();
      state.workers.forEach((worker) => {
        updateCardSaveState(worker);
        patchWorkerStatus(worker);
      });
      updateSaveHint();
      setRunning(state.running, els.testMode.checked);
      const switchedNote = switched.length
        ? ` 用緊呢個編號嘅 Worker（${switched.join("、")}）已改回預設機型，請記得撳「儲存此 Worker」。`
        : "";
      appendLog({
        ts: new Date().toISOString(),
        worker: "frontend",
        level: "success",
        message: `已從呢個瀏覽器嘅選單刪除自訂 SKU ${sku}。內建機型刪唔到。${switchedNote}`,
      });
      return;
    }
    if (event.target.closest(".add-sku")) {
      if (card.dataset.sniping === "true") return;
      const raw = card.querySelector(".sku-custom").value.trim().toUpperCase();
      if (!raw) {
        window.alert("請先輸入 SKU，例如 MK2E4ZA/A");
        return;
      }
      const name = (card.querySelector(".sku-label")?.value || "").trim();
      const extras = normalizeExtraSkus(state.extraSkus);
      const existing = extras.find((item) => item.sku === raw);
      if (existing) {
        if (name) existing.label = name;
      } else {
        extras.push({ sku: raw, label: name || `自訂 SKU ${raw}` });
      }
      state.extraSkus = extras;
      const worker = state.workers.find((item) => item.id === card.dataset.id);
      if (worker) worker.sku = raw;
      persistDraft();
      refreshSkuDropdowns(card.dataset.id, raw);
      card.querySelector(".sku-custom").value = "";
      if (card.querySelector(".sku-label")) card.querySelector(".sku-label").value = "";
      updateSaveHint();
      setRunning(state.running, els.testMode.checked);
      const shown = extras.find((item) => item.sku === raw)?.label || `自訂 SKU ${raw}`;
      appendLog({
        ts: new Date().toISOString(),
        worker: worker ? worker.name : "frontend",
        level: "success",
        message: `已加入 ${shown}（${raw}）到呢個瀏覽器嘅下拉選單，並設為呢個 Worker 嘅目標。請記得撳「儲存此 Worker」。`,
      });
    }
  });

  els.start.addEventListener("click", start);
  els.stop.addEventListener("click", stop);
  els.add.addEventListener("click", () => {
    readCardsIntoState();
    const worker = defaultWorker();
    state.workers.push(worker);
    persistDraft();
    mountWorker(worker);
  });
  els.testMode.addEventListener("change", () => {
    modeHint();
    persistDraft();
    if (!state.running && !state.previewMode) {
      els.pill.textContent = els.testMode.checked ? "待命 · 測試模式" : "待命 · 真實下單模式（需確認）";
    }
  });
  els.clearLogs.addEventListener("click", () => {
    els.logs.innerHTML = "";
  });
  els.logs.addEventListener("scroll", () => {
    const gap = els.logs.scrollHeight - els.logs.scrollTop - els.logs.clientHeight;
    state.stickLogs = gap < 36;
  });

  async function boot() {
    const saved = loadJson(STORAGE_SAVED, []);
    const draft = loadJson(STORAGE_PROFILES, []);
    state.extraSkus = normalizeExtraSkus(loadJson(STORAGE_SKUS, []));
    state.savedWorkers = saved;
    const loaded = draft.length ? draft : saved;
    state.workers = Array.isArray(loaded) ? loaded : [];
    els.testMode.checked = localStorage.getItem(STORAGE_MODE) !== "0";
    modeHint();

    if (location.protocol === "file:") {
      enterPreviewMode("你而家打開緊 preview.html。可以試新增／刪除 Worker、改機型、加／刪 SKU、儲存設定。");
      renderWorkers();
      return;
    }

    try {
      state.catalog = await api("/api/catalog");
    } catch {
      enterPreviewMode("連唔到後台 API，已切換為預覽模式。設定同儲存都可以試。");
      renderWorkers();
      return;
    }

    renderWorkers();
    connectLogs();
    try {
      applyStatus(await api("/api/status"));
    } catch {
      /* first status poll is optional */
    }
    setInterval(async () => {
      if (state.previewMode) return;
      try {
        applyStatus(await api("/api/status"));
      } catch {
        /* keep UI alive if a single poll fails */
      }
    }, 1500);
  }

  boot().catch((err) => {
    enterPreviewMode(err.message);
    renderWorkers();
  });
})();
