(() => {
  const LIVE_CONFIRM =
    "警告：您目前未開啟測試模式，系統啟動後若偵測到有貨將會進行真實的信用卡扣款與下單！請問是否確定要啟動？";

  const STORAGE_PROFILES = "hkIphoneBot.profiles";
  const STORAGE_SAVED = "hkIphoneBot.savedProfiles";
  const STORAGE_SKUS = "hkIphoneBot.extraSkus";
  const STORAGE_MODE = "hkIphoneBot.testMode";
  const PREVIEW_ALERT = "而家係預覽模式：新增／刪除 Worker、改機型、加 SKU、儲存設定都可以試。真正開瀏覽器搶購，請用 Python 開後台後打開 http://127.0.0.1:8765";
  const STATUS_LABELS = {
    idle: "未登入 Apple ID",
    needs_login: "未登入 Apple ID",
    logging_in: "等待登入中",
    ready: "待命（已登入）",
    launching: "正在開啟瀏覽器",
    watching: "監控庫存中",
    checking_out: "正在結帳",
    dry_run_paused: "測試完成（已停在最後一步）",
    completed: "已達數量上限",
    stopped: "已停止",
    error: "發生錯誤",
  };
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
    logs: document.getElementById("log-stream"),
    pill: document.getElementById("run-pill"),
    clearLogs: document.getElementById("btn-clear-logs"),
    runLock: document.getElementById("run-lock"),
    workersPanel: document.querySelector(".workers"),
  };

  const state = {
    catalog: { stores: [], products: [], pickup_windows: [] },
    extraSkus: loadJson(STORAGE_SKUS, []),
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

  function statusLabel(status) {
    return STATUS_LABELS[status] || STATUS_LABELS.idle;
  }

  function defaultWorker(index) {
    const n = index + 1;
    return {
      id: uid(),
      name: `Worker_${n}`,
      session_dir: `session_worker_${n}`,
      sku: "MK2E4ZA/A",
      stores: ["R428"],
      pickup_window: "1d",
      max_qty: 1,
      status: "needs_login",
      last_message: "",
      purchased: 0,
      apple_id: "",
      logged_in: false,
      sniping: false,
    };
  }

  function allProducts() {
    const extras = state.extraSkus.map((sku) => ({ sku, label: `自訂 SKU ${sku}` }));
    const seen = new Set();
    return [...state.catalog.products, ...extras].filter((item) => {
      if (seen.has(item.sku)) return false;
      seen.add(item.sku);
      return true;
    });
  }

  function serializeWorkers(workers) {
    return workers.map(({ id, name, session_dir, sku, stores, pickup_window, max_qty }) => ({
      id, name, session_dir, sku, stores, pickup_window, max_qty,
    }));
  }

  function persistDraft() {
    saveJson(STORAGE_PROFILES, serializeWorkers(state.workers));
    saveJson(STORAGE_SKUS, state.extraSkus);
    localStorage.setItem(STORAGE_MODE, els.testMode.checked ? "1" : "0");
  }

  function updateSaveHint() {
    if (!els.saveHint) return;
    const current = JSON.stringify(serializeWorkers(state.workers));
    const saved = JSON.stringify(state.savedWorkers || []);
    state.dirty = current !== saved;
    if (!(state.savedWorkers && state.savedWorkers.length)) {
      els.saveHint.className = "save-hint dirty";
      els.saveHint.textContent = "尚未儲存。請先按綠色「儲存設定」，再按藍色「全域啟動」。啟動只會用已儲存嘅 Worker 設定。";
      return;
    }
    if (state.dirty) {
      els.saveHint.className = "save-hint dirty";
      els.saveHint.textContent = "有未儲存變更。請先按「儲存設定」，否則不能全域啟動。";
      return;
    }
    els.saveHint.className = "save-hint saved";
    els.saveHint.textContent = `已儲存 ${state.savedWorkers.length} 個 Worker。按全域啟動時會用呢份設定。`;
  }

  function readCardsIntoState() {
    const cards = [...els.list.querySelectorAll(".worker-card")];
    if (!cards.length) return;
    state.workers = cards.map((card) => {
      const stores = [...card.querySelectorAll(".store:checked")].map((box) => box.value);
      const prev = state.workers.find((item) => item.id === card.dataset.id) || {};
      return {
        id: card.dataset.id,
        name: card.querySelector(".name").value.trim(),
        session_dir: card.querySelector(".session").value.trim(),
        sku: card.querySelector(".sku").value.trim(),
        stores,
        pickup_window: card.querySelector(".pickup").value,
        max_qty: Number(card.querySelector(".qty").value || 1),
        status: card.dataset.status || prev.status || "needs_login",
        last_message: card.dataset.message || prev.last_message || "",
        purchased: Number(card.dataset.purchased || prev.purchased || 0),
        apple_id: prev.apple_id || "",
        logged_in: Boolean(prev.logged_in || prev.apple_id),
        sniping: Boolean(prev.sniping),
      };
    });
    persistDraft();
    updateSaveHint();
  }

  function modeHint() {
    els.modeHint.textContent = els.testMode.checked
      ? "開啟時偵測到貨源會停在最後一步，不會扣款。"
      : "關閉時只要偵測到貨就會真實結帳並可能信用卡扣款。";
  }

  function anyBrowserOpen() {
    return state.workers.some((worker) => (
      worker.sniping
      || worker.logged_in
      || worker.browser_open
      || worker.status === "logging_in"
      || worker.status === "launching"
      || worker.status === "ready"
      || worker.status === "watching"
      || worker.status === "checking_out"
    ));
  }

  function setRunning(running, testMode) {
    state.running = running;
    els.start.disabled = false;
    els.stop.disabled = !running && !anyBrowserOpen();
    els.add.disabled = false;
    if (els.save) els.save.disabled = false;
    els.testMode.disabled = false;
    if (els.workersPanel) els.workersPanel.classList.toggle("is-running", running);
    if (els.runLock) els.runLock.hidden = !running;
    els.list.querySelectorAll(".worker-card").forEach((card) => {
      const sniping = card.dataset.sniping === "true";
      card.classList.toggle("is-sniping", sniping);
      card.querySelectorAll("input, select, button.add-sku, button.remove, button.clone").forEach((node) => {
        node.disabled = sniping;
      });
      const loggedIn = card.dataset.loggedIn === "true";
      const runBtn = card.querySelector(".run-one");
      const pauseBtn = card.querySelector(".pause-one");
      const loginBtn = card.querySelector(".login");
      const focusBtn = card.querySelector(".focus");
      if (runBtn) runBtn.disabled = !loggedIn || sniping;
      if (pauseBtn) pauseBtn.disabled = !sniping;
      if (loginBtn) loginBtn.disabled = false;
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

  function workerCardHtml(worker, entering) {
    const status = worker.status || (worker.logged_in ? "ready" : "needs_login");
    const sniping = Boolean(worker.sniping);
    const loggedIn = Boolean(worker.logged_in || worker.apple_id);
    const email = worker.apple_id || "";
    return `
      <article class="worker-card${entering ? " enter" : ""}${sniping ? " is-sniping" : ""}" data-id="${esc(worker.id)}" data-status="${esc(status)}" data-message="${esc(worker.last_message || "")}" data-purchased="${esc(worker.purchased || 0)}" data-sniping="${sniping}" data-logged-in="${loggedIn}">
        <div class="worker-top">
          <strong class="worker-title">${esc(worker.name)}</strong>
          <span class="badge ${esc(status)}">${esc(statusLabel(status))}${worker.purchased ? ` · ${worker.purchased}/${worker.max_qty}` : ""}</span>
        </div>
        <div class="account-bar ${loggedIn ? "is-in" : "is-out"}">
          <span>Apple ID</span>
          <strong class="account-email">${loggedIn ? esc(email || "已登入") : "未登入"}</strong>
          <button type="button" class="btn login">${loggedIn ? "重新登入 / 帶到最前" : "登入 Apple ID"}</button>
        </div>
        <div class="grid">
          <label class="field">
            <span>Worker 名稱 / 編號</span>
            <input class="name" type="text" value="${esc(worker.name)}" />
          </label>
          <label class="field">
            <span>Apple ID Session 資料夾</span>
            <input class="session" type="text" value="${esc(worker.session_dir)}" placeholder="session_worker_1" />
          </label>
          <div class="field full sku-block">
            <span>1. 目標機型（下拉選單揀 Duo 型號）</span>
            <select class="sku" aria-label="目標機型 SKU">${productOptions(worker.sku)}</select>
            <span>2. 或者輸入任何 Apple 產品 SKU 再加入選單</span>
            <div class="sku-add">
              <input class="sku-custom" type="text" placeholder="例如 MK2E4ZA/A" />
              <button type="button" class="btn add-sku">加入此 SKU</button>
            </div>
            <p class="help">加入之後會出現喺上面嘅下拉選單，再揀佢做呢個 Worker 嘅目標機型。</p>
          </div>
          <div class="field full">
            <span>香港指定門市（可複選）</span>
            <div class="stores">${storeBoxes(worker.stores || [])}</div>
          </div>
          <label class="field">
            <span>取貨時間限制</span>
            <select class="pickup">${pickupOptions(worker.pickup_window)}</select>
          </label>
          <label class="field">
            <span>購買數量上限</span>
            <input class="qty" type="number" min="1" max="99" value="${esc(worker.max_qty)}" />
          </label>
        </div>
        <div class="card-actions">
          <button type="button" class="btn run-one" ${loggedIn && !sniping ? "" : "disabled"}>開始運作</button>
          <button type="button" class="btn pause-one" ${sniping ? "" : "disabled"}>停止運作</button>
          <button type="button" class="btn focus">顯示此 Worker 視窗</button>
          <button type="button" class="btn clone">複製做新 Apple ID</button>
          <button type="button" class="btn remove">刪除此 Worker</button>
        </div>
      </article>
    `;
  }

  function renderWorkers() {
    els.list.innerHTML = state.workers.map((worker) => workerCardHtml(worker, false)).join("");
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
    setRunning(state.running, els.testMode.checked);
    updateSaveHint();
  }

  function patchWorkerStatus(worker) {
    const card = els.list.querySelector(`[data-id="${CSS.escape(worker.id)}"]`);
    if (!card) return;
    const status = worker.status || "needs_login";
    const sniping = Boolean(worker.sniping);
    const loggedIn = Boolean(worker.logged_in || worker.apple_id);
    card.dataset.status = status;
    card.dataset.purchased = String(worker.purchased || 0);
    card.dataset.sniping = String(sniping);
    card.dataset.loggedIn = String(loggedIn);
    card.classList.toggle("is-sniping", sniping);
    const badge = card.querySelector(".badge");
    if (badge) {
      badge.className = `badge ${status}`;
      badge.textContent = `${statusLabel(status)}${worker.purchased ? ` · ${worker.purchased}/${worker.max_qty}` : ""}`;
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
    if (loginBtn) loginBtn.textContent = loggedIn ? "重新登入 / 帶到最前" : "登入 Apple ID";
    const runBtn = card.querySelector(".run-one");
    const pauseBtn = card.querySelector(".pause-one");
    if (runBtn) runBtn.disabled = !loggedIn || sniping;
    if (pauseBtn) pauseBtn.disabled = !sniping;
  }

  function refreshSkuDropdowns(selectId, sku) {
    els.list.querySelectorAll("select.sku").forEach((select) => {
      const cardId = select.closest(".worker-card")?.dataset.id;
      const value = cardId === selectId ? sku : select.value;
      select.innerHTML = productOptions(value);
      select.value = value;
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
      state.workers = state.workers.map((worker) => ({ ...worker, ...(byId.get(worker.id) || {}) }));
      data.workers.forEach((item) => {
        if (!state.workers.some((worker) => worker.id === item.id)) {
          state.workers.push(item);
          if (!els.list.querySelector(`[data-id="${CSS.escape(item.id)}"]`)) {
            mountWorker(item);
          }
        }
        patchWorkerStatus({ ...item, ...(state.workers.find((worker) => worker.id === item.id) || {}) });
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

  function saveSettings() {
    readCardsIntoState();
    for (const worker of state.workers) {
      if (!worker.name || !worker.session_dir || !worker.sku || !worker.stores.length) {
        window.alert("每個 Worker 都要有名稱、session 資料夾、目標機型，同至少一間香港門市。");
        return false;
      }
    }
    state.savedWorkers = serializeWorkers(state.workers);
    saveJson(STORAGE_SAVED, state.savedWorkers);
    persistDraft();
    updateSaveHint();
    appendLog({
      ts: new Date().toISOString(),
      worker: "frontend",
      level: "success",
      message: `已儲存 ${state.savedWorkers.length} 個 Worker 設定。全域啟動會用呢份設定。`,
    });
    return true;
  }

  async function start() {
    if (state.previewMode) {
      window.alert(PREVIEW_ALERT);
      return;
    }
    readCardsIntoState();
    if (!state.savedWorkers.length || state.dirty) {
      window.alert("請先喺 Worker Profiles 撳綠色「儲存設定」，再按全域啟動。系統只會用已儲存嘅 Worker 設定來跑。");
      return;
    }
    if (!els.testMode.checked && !window.confirm(LIVE_CONFIRM)) {
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "warn", message: "使用者取消真實下單啟動" });
      return;
    }
    els.start.disabled = true;
    try {
      const data = await api("/api/start", {
        method: "POST",
        body: JSON.stringify({
          test_mode: els.testMode.checked,
          workers: state.savedWorkers,
        }),
      });
      applyStatus(data);
    } catch (err) {
      els.start.disabled = false;
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
    const { apple_id, logged_in, sniping, status, last_message, purchased, ...profile } = worker;
    return {
      test_mode: els.testMode.checked,
      worker: {
        id: profile.id,
        name: profile.name,
        session_dir: profile.session_dir,
        sku: profile.sku,
        stores: profile.stores,
        pickup_window: profile.pickup_window,
        max_qty: profile.max_qty,
      },
    };
  }

  async function loginWorker(id) {
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
    const worker = state.workers.find((item) => item.id === id);
    if (!worker || !(worker.logged_in || worker.apple_id)) {
      window.alert("請先撳「登入 Apple ID」，登入成功變成待命後先可以開始運作。");
      return;
    }
    if (!els.testMode.checked && !window.confirm(LIVE_CONFIRM)) {
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "warn", message: "使用者取消真實下單啟動" });
      return;
    }
    if (state.previewMode) {
      worker.sniping = true;
      worker.status = "watching";
      worker.last_message = "預覽模式：模擬開始運作。真正搶機請用 python app.py。";
      patchWorkerStatus(worker);
      setRunning(true, els.testMode.checked);
      appendLog({
        ts: new Date().toISOString(),
        worker: worker.name,
        level: "success",
        message: "預覽模式：已模擬開始運作。真正開瀏覽器搶購請用 python app.py。",
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
        worker.last_message = "預覽模式：已停止運作。";
        patchWorkerStatus(worker);
      }
      setRunning(state.workers.some((item) => item.sniping), els.testMode.checked);
      appendLog({
        ts: new Date().toISOString(),
        worker: worker ? worker.name : "frontend",
        level: "info",
        message: "預覽模式：已模擬停止運作。登入狀態仍然保留。",
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

  els.list.addEventListener("input", () => {
    readCardsIntoState();
  });
  els.list.addEventListener("change", () => {
    readCardsIntoState();
  });
  els.list.addEventListener("click", (event) => {
    const card = event.target.closest(".worker-card");
    if (!card) return;
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
    if (event.target.closest(".remove")) {
      if (card.dataset.sniping === "true") return;
      const remaining = state.workers.filter((worker) => worker.id !== card.dataset.id);
      let closed = false;
      const finish = () => {
        if (closed) return;
        closed = true;
        if (card.parentNode) card.remove();
        state.workers = remaining.length ? remaining : [defaultWorker(0)];
        persistDraft();
        if (!remaining.length) mountWorker(state.workers[0]);
        updateSaveHint();
      };
      card.classList.add("leave");
      card.addEventListener("animationend", finish, { once: true });
      window.setTimeout(finish, 280);
    }
    if (event.target.closest(".clone")) {
      if (card.dataset.sniping === "true") return;
      readCardsIntoState();
      const source = state.workers.find((item) => item.id === card.dataset.id);
      if (!source) return;
      const copy = {
        ...source,
        id: uid(),
        name: `${source.name}_new`,
        session_dir: `session_${Date.now()}`,
        status: "needs_login",
        purchased: 0,
        last_message: "",
        apple_id: "",
        logged_in: false,
        sniping: false,
      };
      state.workers.push(copy);
      persistDraft();
      mountWorker(copy);
      appendLog({
        ts: new Date().toISOString(),
        worker: copy.name,
        level: "info",
        message: `已複製設定到新 session「${copy.session_dir}」。請儲存後再啟動，喺新視窗用另一個 Apple ID 登入。唔使刪舊 Worker 嘅瀏覽器資料。`,
      });
    }
    if (event.target.closest(".focus")) {
      focusWorker(card.dataset.id);
    }
    if (event.target.closest(".add-sku")) {
      const raw = card.querySelector(".sku-custom").value.trim().toUpperCase();
      if (!raw) {
        window.alert("請先輸入 SKU，例如 MK2E4ZA/A");
        return;
      }
      if (!state.extraSkus.includes(raw)) state.extraSkus.push(raw);
      const worker = state.workers.find((item) => item.id === card.dataset.id);
      if (worker) worker.sku = raw;
      persistDraft();
      refreshSkuDropdowns(card.dataset.id, raw);
      card.querySelector(".sku-custom").value = "";
      updateSaveHint();
      appendLog({
        ts: new Date().toISOString(),
        worker: worker ? worker.name : "frontend",
        level: "success",
        message: `已加入 SKU ${raw}，並設為呢個 Worker 嘅目標機型。請記得按「儲存設定」。`,
      });
    }
  });

  els.start.addEventListener("click", start);
  els.stop.addEventListener("click", stop);
  if (els.save) els.save.addEventListener("click", saveSettings);
  els.add.addEventListener("click", () => {
    readCardsIntoState();
    const worker = defaultWorker(state.workers.length);
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
    state.savedWorkers = saved;
    state.workers = (draft.length ? draft : saved).length ? (draft.length ? draft : saved) : [defaultWorker(0)];
    els.testMode.checked = localStorage.getItem(STORAGE_MODE) !== "0";
    modeHint();

    if (location.protocol === "file:") {
      enterPreviewMode("你而家打開緊 preview.html。可以試新增／刪除 Worker、改機型、加 SKU、儲存設定。");
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
