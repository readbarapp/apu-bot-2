(() => {
  const LIVE_CONFIRM =
    "警告：您目前未開啟測試模式，系統啟動後若偵測到有貨將會進行真實的信用卡扣款與下單！請問是否確定要啟動？";

  const STORAGE_PROFILES = "hkIphoneBot.profiles";
  const STORAGE_SAVED = "hkIphoneBot.savedProfiles";
  const STORAGE_SKUS = "hkIphoneBot.extraSkus";
  const STORAGE_MODE = "hkIphoneBot.testMode";
  const STORAGE_COLLAPSED = "hkIphoneBot.collapsed";
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
    browser_closed: "瀏覽器已關閉（已停搶）",
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
    startHint: document.getElementById("start-hint"),
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

  function profileOf(worker) {
    return {
      id: worker.id,
      name: worker.name,
      session_dir: worker.session_dir,
      sku: worker.sku,
      stores: worker.stores,
      pickup_window: worker.pickup_window,
      max_qty: worker.max_qty,
    };
  }

  function savedProfile(id) {
    return (state.savedWorkers || []).find((item) => item.id === id);
  }

  function isDirty(worker) {
    const saved = savedProfile(worker.id);
    if (!saved) return true;
    return JSON.stringify(profileOf(worker)) !== JSON.stringify(saved);
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
        els.saveHint.textContent = "請新增 Worker，並喺該卡撳「儲存此 Worker」。";
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
    const cards = [...els.list.querySelectorAll(".worker-card")];
    if (!cards.length) return;
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
        browser_open: Boolean(prev.browser_open),
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
      || worker.browser_open
      || worker.status === "logging_in"
      || worker.status === "launching"
      || worker.status === "ready"
      || worker.status === "watching"
      || worker.status === "checking_out"
    ));
  }

  function unloggedWorkers() {
    return state.workers.filter((worker) => !(worker.logged_in || worker.apple_id));
  }

  function updateStartGate() {
    if (!els.start) return;
    const unsaved = unsavedWorkers();
    const unlogged = unloggedWorkers();
    const allSniping = state.workers.length > 0 && state.workers.every((worker) => worker.sniping);
    const blocked = !state.workers.length || unsaved.length > 0 || unlogged.length > 0 || allSniping;
    els.start.disabled = blocked;
    if (!els.startHint) return;
    if (!state.workers.length) {
      els.startHint.className = "start-hint blocked";
      els.startHint.textContent = "請先新增並儲存 Worker。";
      return;
    }
    if (unsaved.length) {
      els.startHint.className = "start-hint blocked";
      els.startHint.textContent = `請先喺未儲存嘅卡撳「儲存此 Worker」：${unsaved.map((item) => item.name || "未命名").join("、")}`;
      return;
    }
    if (unlogged.length) {
      els.startHint.className = "start-hint blocked";
      els.startHint.textContent = `仲有 ${unlogged.length} 個未登入：${unlogged.map((item) => item.name || "未命名").join("、")}。請登入，或者刪除未登入嘅 Worker。`;
      return;
    }
    if (allSniping) {
      els.startHint.className = "start-hint ok";
      els.startHint.textContent = "全部 Worker 已在搶機。要停某個請撳「暫停運作」。";
      return;
    }
    els.startHint.className = "start-hint ok";
    els.startHint.textContent = `已登入 ${state.workers.length} 個 Worker，可以全部開始搶機。單個用「開始運作／暫停運作」。`;
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
      card.querySelectorAll("input, select, button.add-sku, button.remove").forEach((node) => {
        node.disabled = sniping;
      });
      if (worker) updateCardSaveState(worker);
      const runBtn = card.querySelector(".run-one");
      const pauseBtn = card.querySelector(".pause-one");
      const loginBtn = card.querySelector(".login");
      const focusBtn = card.querySelector(".focus");
      const saved = worker ? !isDirty(worker) : false;
      if (runBtn) runBtn.disabled = !loggedIn || sniping || !saved;
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

  function workerCardHtml(worker, entering) {
    const status = worker.status || (worker.logged_in ? "ready" : "needs_login");
    const sniping = Boolean(worker.sniping);
    const loggedIn = Boolean(worker.logged_in || worker.apple_id);
    const closed = status === "browser_closed";
    const collapsed = collapsedSet().has(worker.id);
    const email = worker.apple_id || "";
    const saved = !isDirty(worker);
    const note = worker.last_message || (loggedIn
      ? "已登入。可以撳「開始運作」或上面綠色「全部開始搶機」。"
      : "未登入。請先撳「登入 Apple ID」。");
    const sessionHint = `會儲存在專案資料夾 sessions/${worker.session_dir || "session_worker_1"}。Chromium 把 Apple ID cookie 寫入呢度，下次開同一個資料夾就記得登入。`;
    const meta = `${worker.sku || "未揀 SKU"} · ${loggedIn ? (email || "已登入") : "未登入"}`;
    return `
      <article class="worker-card${entering ? " enter" : ""}${sniping ? " is-sniping" : ""}${closed ? " is-closed" : ""}${collapsed ? " is-collapsed" : ""}" data-id="${esc(worker.id)}" data-status="${esc(status)}" data-message="${esc(worker.last_message || "")}" data-purchased="${esc(worker.purchased || 0)}" data-sniping="${sniping}" data-logged-in="${loggedIn}">
        <div class="worker-top">
          <button type="button" class="collapse-toggle" aria-expanded="${collapsed ? "false" : "true"}" aria-label="展開或收合 Worker">▾</button>
          <div class="worker-heading">
            <strong class="worker-title">${esc(worker.name)}</strong>
            <p class="collapsed-meta">${esc(meta)}</p>
          </div>
          <span class="badge ${esc(status)}">${esc(statusLabel(status))}${worker.purchased ? ` · ${worker.purchased}/${worker.max_qty}` : ""}</span>
          <div class="worker-top-actions">
            <button type="button" class="btn run-one" ${loggedIn && !sniping && saved ? "" : "disabled"}>開始運作</button>
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
            <span>Apple ID Session 資料夾</span>
            <input class="session" type="text" value="${esc(worker.session_dir)}" placeholder="session_worker_1" />
            <p class="help session-path">${esc(sessionHint)}</p>
          </label>
          <div class="field full sku-block">
            <span>1. 目標機型（每個 Worker 只搶一個 SKU）</span>
            <select class="sku" aria-label="目標機型 SKU">${productOptions(worker.sku)}</select>
            <span>2. 或者輸入任何 Apple 產品 SKU 再加入選單</span>
            <div class="sku-add">
              <input class="sku-custom" type="text" placeholder="例如 MK2E4ZA/A" />
              <button type="button" class="btn add-sku">加入此 SKU</button>
            </div>
            <p class="help">一個 Worker 同一時間只會監控同搶呢一個 SKU。要搶第二款，請新增另一個 Worker。</p>
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
        <div class="card-save">
          <button type="button" class="btn save save-one" ${sniping || saved ? "disabled" : ""}>儲存此 Worker</button>
          <p class="save-hint-one ${sniping ? "locked" : (saved ? "saved" : "dirty")}">${sniping ? "運作中已鎖定。請先「暫停運作」先至可以改同儲存。" : (saved ? "此 Worker 已儲存。" : "此 Worker 有未儲存變更。")}</p>
        </div>
        <div class="card-actions">
          <button type="button" class="btn focus">顯示此 Worker 視窗</button>
          <button type="button" class="btn remove">刪除此 Worker</button>
        </div>
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
    if (loginBtn) {
      loginBtn.textContent = closed ? "重新打開瀏覽器" : (loggedIn ? "帶到最前" : "登入 Apple ID");
      loginBtn.disabled = sniping;
    }
    const note = card.querySelector(".worker-note");
    if (note) {
      note.classList.toggle("warn", closed);
      note.textContent = worker.last_message || (loggedIn
        ? "已登入。可以撳「開始運作」或上面綠色「全部開始搶機」。"
        : "未登入。請先撳「登入 Apple ID」。");
    }
    const meta = card.querySelector(".collapsed-meta");
    if (meta) meta.textContent = `${worker.sku || "未揀 SKU"} · ${loggedIn ? (worker.apple_id || "已登入") : "未登入"}`;
    const runBtn = card.querySelector(".run-one");
    const pauseBtn = card.querySelector(".pause-one");
    const saved = !isDirty(worker);
    if (runBtn) runBtn.disabled = !loggedIn || sniping || !saved;
    if (pauseBtn) pauseBtn.disabled = !sniping;
    updateCardSaveState(worker);
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

  function saveOne(id) {
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
    if (!worker.name || !worker.session_dir || !worker.sku || !worker.stores.length) {
      window.alert("此 Worker 要有名稱、session 資料夾、目標機型，同至少一間香港門市。");
      return false;
    }
    const clash = state.savedWorkers.find((item) => item.id !== worker.id && item.session_dir === worker.session_dir);
    const liveClash = state.workers.find((item) => item.id !== worker.id && item.session_dir === worker.session_dir);
    if (clash || liveClash) {
      window.alert("每個 Worker 要用唔同嘅 session 資料夾（一個資料夾 = 一個 Apple ID）。");
      return false;
    }
    const profile = profileOf(worker);
    const index = state.savedWorkers.findIndex((item) => item.id === worker.id);
    if (index >= 0) state.savedWorkers[index] = profile;
    else state.savedWorkers.push(profile);
    state.savedWorkers = state.savedWorkers.filter((item) => state.workers.some((workerItem) => workerItem.id === item.id));
    saveJson(STORAGE_SAVED, state.savedWorkers);
    persistDraft();
    updateSaveHint();
    appendLog({
      ts: new Date().toISOString(),
      worker: worker.name,
      level: "success",
      message: "已儲存此 Worker 設定。",
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
      window.alert(`仲有 Worker 未登入 Apple ID：${unlogged.map((item) => item.name).join("、")}。請登入，或者刪除未登入嘅 Worker。`);
      updateStartGate();
      return;
    }
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
          workers: serializeWorkers(state.workers),
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
    if (!(worker.logged_in || worker.apple_id)) {
      window.alert("請先撳「登入 Apple ID」，登入成功後先可以開始運作。");
      return;
    }
    if (!els.testMode.checked && !window.confirm(LIVE_CONFIRM)) {
      appendLog({ ts: new Date().toISOString(), worker: "frontend", level: "warn", message: "使用者取消真實下單啟動" });
      return;
    }
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

  els.list.addEventListener("input", () => {
    readCardsIntoState();
  });
  els.list.addEventListener("change", () => {
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
      if (card.dataset.sniping === "true") return;
      const remaining = state.workers.filter((worker) => worker.id !== card.dataset.id);
      let closed = false;
      const finish = () => {
        if (closed) return;
        closed = true;
        if (card.parentNode) card.remove();
        state.workers = remaining.length ? remaining : [defaultWorker(0)];
        state.savedWorkers = state.savedWorkers.filter((item) => state.workers.some((worker) => worker.id === item.id));
        saveJson(STORAGE_SAVED, state.savedWorkers);
        persistDraft();
        if (!remaining.length) mountWorker(state.workers[0]);
        updateSaveHint();
        setRunning(state.running, els.testMode.checked);
      };
      card.classList.add("leave");
      card.addEventListener("animationend", finish, { once: true });
      window.setTimeout(finish, 280);
    }
    if (event.target.closest(".focus")) {
      focusWorker(card.dataset.id);
    }
    if (event.target.closest(".add-sku")) {
      if (card.dataset.sniping === "true") return;
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
        message: `已加入 SKU ${raw}，並設為呢個 Worker 嘅目標機型。請記得撳「儲存此 Worker」。`,
      });
    }
  });

  els.start.addEventListener("click", start);
  els.stop.addEventListener("click", stop);
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
