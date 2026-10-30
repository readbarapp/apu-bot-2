(() => {
  const LIVE_CONFIRM =
    "警告：您目前未開啟測試模式，系統啟動後若偵測到有貨將會進行真實的信用卡扣款與下單！請問是否確定要啟動？";

  const STORAGE_PROFILES = "hkIphoneBot.profiles";
  const STORAGE_SAVED = "hkIphoneBot.savedProfiles";
  const STORAGE_SKUS = "hkIphoneBot.extraSkus";
  const STORAGE_MODE = "hkIphoneBot.testMode";
  const PREVIEW_ALERT = "而家係預覽模式：新增／刪除 Worker、改機型、加 SKU、儲存設定都可以試。真正開瀏覽器搶購，請用 Python 開後台後打開 http://127.0.0.1:8765";
  const STATUS_LABELS = {
    idle: "待命（未啟動）",
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
      status: "idle",
      last_message: "",
      purchased: 0,
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
      return {
        id: card.dataset.id,
        name: card.querySelector(".name").value.trim(),
        session_dir: card.querySelector(".session").value.trim(),
        sku: card.querySelector(".sku").value.trim(),
        stores,
        pickup_window: card.querySelector(".pickup").value,
        max_qty: Number(card.querySelector(".qty").value || 1),
        status: card.dataset.status || "idle",
        last_message: card.dataset.message || "",
        purchased: Number(card.dataset.purchased || 0),
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

  function setRunning(running, testMode) {
    state.running = running;
    els.start.disabled = running;
    els.stop.disabled = !running;
    els.add.disabled = running;
    if (els.save) els.save.disabled = running;
    els.testMode.disabled = running;
    els.list.querySelectorAll("input, select, button.add-sku, button.remove").forEach((node) => {
      node.disabled = running;
    });
    els.list.querySelectorAll("button.focus").forEach((node) => {
      node.disabled = !running;
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

  function renderWorkers() {
    els.list.innerHTML = state.workers.map((worker) => {
      const status = worker.status || "idle";
      return `
      <article class="worker-card" data-id="${esc(worker.id)}" data-status="${esc(status)}" data-message="${esc(worker.last_message || "")}" data-purchased="${esc(worker.purchased || 0)}">
        <div class="worker-top">
          <strong>${esc(worker.name)}</strong>
          <span class="badge ${esc(status)}">${esc(statusLabel(status))}${worker.purchased ? ` · ${worker.purchased}/${worker.max_qty}` : ""}</span>
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
          <button type="button" class="btn focus" ${state.running ? "" : "disabled"}>顯示此 Worker 視窗</button>
          <button type="button" class="btn remove">刪除此 Worker</button>
        </div>
      </article>
    `;
    }).join("");
    setRunning(state.running, els.testMode.checked);
    updateSaveHint();
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
    setRunning(Boolean(data.running), data.test_mode);
    if (Array.isArray(data.workers) && data.workers.length) {
      const byId = new Map(data.workers.map((item) => [item.id, item]));
      state.workers = state.workers.map((worker) => ({ ...worker, ...(byId.get(worker.id) || {}) }));
      data.workers.forEach((item) => {
        if (!state.workers.some((worker) => worker.id === item.id)) {
          state.workers.push(item);
        }
      });
      renderWorkers();
    }
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
    if (state.running) return false;
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
    if (!state.running) readCardsIntoState();
  });
  els.list.addEventListener("change", () => {
    if (!state.running) readCardsIntoState();
  });
  els.list.addEventListener("click", (event) => {
    const card = event.target.closest(".worker-card");
    if (!card) return;
    if (event.target.closest(".remove")) {
      if (state.running) return;
      state.workers = state.workers.filter((worker) => worker.id !== card.dataset.id);
      if (!state.workers.length) state.workers.push(defaultWorker(0));
      persistDraft();
      renderWorkers();
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
      renderWorkers();
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
    if (state.running) return;
    readCardsIntoState();
    state.workers.push(defaultWorker(state.workers.length));
    persistDraft();
    renderWorkers();
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
