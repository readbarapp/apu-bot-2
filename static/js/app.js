(() => {
  const LIVE_CONFIRM =
    "警告：您目前未開啟測試模式，系統啟動後若偵測到有貨將會進行真實的信用卡扣款與下單！請問是否確定要啟動？";

  const STORAGE_PROFILES = "hkIphoneBot.profiles";
  const STORAGE_SKUS = "hkIphoneBot.extraSkus";
  const STORAGE_MODE = "hkIphoneBot.testMode";

  const els = {
    testMode: document.getElementById("test-mode"),
    modeHint: document.getElementById("mode-hint"),
    start: document.getElementById("btn-start"),
    stop: document.getElementById("btn-stop"),
    add: document.getElementById("btn-add"),
    list: document.getElementById("worker-list"),
    logs: document.getElementById("log-stream"),
    pill: document.getElementById("run-pill"),
    clearLogs: document.getElementById("btn-clear-logs"),
  };

  const state = {
    catalog: { stores: [], products: [], pickup_windows: [] },
    extraSkus: loadJson(STORAGE_SKUS, []),
    workers: [],
    running: false,
    stickLogs: true,
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

  function persist() {
    saveJson(STORAGE_PROFILES, state.workers.map(({ id, name, session_dir, sku, stores, pickup_window, max_qty }) => ({
      id, name, session_dir, sku, stores, pickup_window, max_qty,
    })));
    saveJson(STORAGE_SKUS, state.extraSkus);
    localStorage.setItem(STORAGE_MODE, els.testMode.checked ? "1" : "0");
  }

  function readCardsIntoState() {
    const cards = [...els.list.querySelectorAll(".worker-card")];
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
    persist();
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
    } else {
      els.pill.className = "pill idle";
      els.pill.textContent = "未啟動 · 等待前端指令";
    }
  }

  function productOptions(selected) {
    const options = allProducts().map((item) => (
      `<option value="${esc(item.sku)}" ${item.sku === selected ? "selected" : ""}>${esc(item.label)} (${esc(item.sku)})</option>`
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
    els.list.innerHTML = state.workers.map((worker) => `
      <article class="worker-card" data-id="${esc(worker.id)}" data-status="${esc(worker.status || "idle")}" data-message="${esc(worker.last_message || "")}" data-purchased="${esc(worker.purchased || 0)}">
        <div class="worker-top">
          <strong>${esc(worker.name)}</strong>
          <span class="badge ${esc(worker.status || "idle")}">${esc(worker.status || "idle")}${worker.purchased ? ` · ${worker.purchased}/${worker.max_qty}` : ""}</span>
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
          <div class="field full">
            <span>目標機型 / SKU</span>
            <div class="sku-row">
              <select class="sku">${productOptions(worker.sku)}</select>
              <input class="sku-custom" type="text" placeholder="輸入 Apple 產品 SKU" />
              <button type="button" class="btn tiny add-sku">新增型號</button>
            </div>
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
          <button type="button" class="btn tiny focus" ${state.running ? "" : "disabled"}>顯示此 Worker 視窗 (Bring to Front)</button>
          <button type="button" class="btn tiny remove">刪除</button>
        </div>
      </article>
    `).join("");
    setRunning(state.running, els.testMode.checked);
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

  async function start() {
    readCardsIntoState();
    if (!els.testMode.checked && !window.confirm(LIVE_CONFIRM)) {
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "warn", message: "使用者取消真實下單啟動" });
      return;
    }
    if (!state.workers.length) {
      window.alert("請至少新增一個 Worker Profile");
      return;
    }
    els.start.disabled = true;
    try {
      const data = await api("/api/start", {
        method: "POST",
        body: JSON.stringify({
          test_mode: els.testMode.checked,
          workers: state.workers.map(({ id, name, session_dir, sku, stores, pickup_window, max_qty }) => ({
            id, name, session_dir, sku, stores, pickup_window, max_qty,
          })),
        }),
      });
      applyStatus(data);
    } catch (err) {
      els.start.disabled = false;
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "error", message: err.message });
    }
  }

  async function stop() {
    try {
      const data = await api("/api/stop", { method: "POST" });
      applyStatus(data);
    } catch (err) {
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "error", message: err.message });
    }
  }

  async function focusWorker(id) {
    try {
      await api(`/api/workers/${encodeURIComponent(id)}/focus`, { method: "POST" });
    } catch (err) {
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "error", message: err.message });
    }
  }

  function connectLogs() {
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
      persist();
      renderWorkers();
    }
    if (event.target.closest(".focus")) {
      focusWorker(card.dataset.id);
    }
    if (event.target.closest(".add-sku")) {
      const raw = card.querySelector(".sku-custom").value.trim().toUpperCase();
      if (!raw) return;
      if (!state.extraSkus.includes(raw)) state.extraSkus.push(raw);
      const worker = state.workers.find((item) => item.id === card.dataset.id);
      if (worker) worker.sku = raw;
      persist();
      renderWorkers();
    }
  });

  els.start.addEventListener("click", start);
  els.stop.addEventListener("click", stop);
  els.add.addEventListener("click", () => {
    if (state.running) return;
    readCardsIntoState();
    state.workers.push(defaultWorker(state.workers.length));
    persist();
    renderWorkers();
  });
  els.testMode.addEventListener("change", () => {
    modeHint();
    persist();
    if (!state.running) {
      els.pill.textContent = els.testMode.checked ? "未啟動 · 測試模式待命" : "未啟動 · 真實下單模式（需確認）";
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
    state.catalog = await api("/api/catalog");
    const saved = loadJson(STORAGE_PROFILES, []);
    state.workers = saved.length ? saved : [defaultWorker(0)];
    els.testMode.checked = localStorage.getItem(STORAGE_MODE) !== "0";
    modeHint();
    renderWorkers();
    connectLogs();
    const status = await api("/api/status");
    applyStatus(status);
    setInterval(async () => {
      try {
        applyStatus(await api("/api/status"));
      } catch {
        /* keep UI alive if a single poll fails */
      }
    }, 1500);
  }

  boot().catch((err) => {
    appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "error", message: err.message });
  });
})();
