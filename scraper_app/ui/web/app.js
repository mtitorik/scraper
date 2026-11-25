// State management
let appSettings = {};
let activeSheet = "sheet1";
let inputMode = "file";
let statusFilter = "all";
let lastUpdatedProductName = null;
let productsMap = new Map(); // product_name -> summary dict
let variantsList = [];
let isScrapingRunning = false;
let isScrapingPaused = false;
let activeDrawerDetail = null;

// Audio chime for CAPTCHA and completion
const playAlertChime = () => {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sine";
    osc.frequency.setValueAtTime(587.33, ctx.currentTime);
    osc.frequency.setValueAtTime(880, ctx.currentTime + 0.15);
    gain.gain.setValueAtTime(0.18, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    osc.start();
    osc.stop(ctx.currentTime + 0.5);
  } catch (e) {
    // Ignore audio context restriction
  }
};

// DOM Elements
const elements = {
  sidebarBrandSubtitle: document.getElementById("sidebar-brand-subtitle"),
  navResultsCount: document.getElementById("nav-results-count"),
  navWebsitesCount: document.getElementById("nav-websites-count"),
  statusBadge: document.getElementById("status-badge"),
  statusBadgeText: document.getElementById("status-badge-text"),
  statusDescription: document.getElementById("status-description"),
  headerLiveControls: document.getElementById("header-live-controls"),
  headerMiniProgress: document.getElementById("header-mini-progress"),
  btnHeaderPause: document.getElementById("btn-header-pause"),
  btnHeaderStop: document.getElementById("btn-header-stop"),
  captchaBanner: document.getElementById("captcha-banner"),
  captchaSiteText: document.getElementById("captcha-site-text"),
  btnCaptchaDone: document.getElementById("btn-captcha-done"),

  // Readiness pills
  pillReadyProducts: document.getElementById("pill-ready-products"),
  pillReadyProductsText: document.getElementById("pill-ready-products-text"),
  pillReadyWebsites: document.getElementById("pill-ready-websites"),
  pillReadyWebsitesText: document.getElementById("pill-ready-websites-text"),
  pillReadyFolder: document.getElementById("pill-ready-folder"),
  pillReadyFolderText: document.getElementById("pill-ready-folder-text"),
  btnJumpResults: document.getElementById("btn-jump-results"),

  // Input mode & manual entry
  btnModeFile: document.getElementById("btn-mode-file"),
  btnModeManual: document.getElementById("btn-mode-manual"),
  configModeHint: document.getElementById("config-mode-hint"),
  fileInputGroup: document.getElementById("file-input-group"),
  manualInputGroup: document.getElementById("manual-input-group"),
  manualQuickInput: document.getElementById("manual-quick-input"),
  btnManualQuickAdd: document.getElementById("btn-manual-quick-add"),
  manualProductsInput: document.getElementById("manual-products-input"),
  manualProductCount: document.getElementById("manual-product-count"),
  btnClearManual: document.getElementById("btn-clear-manual"),

  // File pickers
  inputXlsxPath: document.getElementById("input-xlsx-path"),
  outputXlsxPath: document.getElementById("output-xlsx-path"),
  rootFolderPath: document.getElementById("root-folder-path"),
  resumeXlsxPath: document.getElementById("resume-xlsx-path"),
  btnBrowseInput: document.getElementById("btn-browse-input"),
  btnBrowseOutput: document.getElementById("btn-browse-output"),
  btnBrowseFolder: document.getElementById("btn-browse-folder"),
  btnBrowseResume: document.getElementById("btn-browse-resume"),
  btnClearResume: document.getElementById("btn-clear-resume"),

  // Playback controls
  btnStart: document.getElementById("btn-start"),
  btnPause: document.getElementById("btn-pause"),
  btnStop: document.getElementById("btn-stop"),
  btnOpenExcelTop: document.getElementById("btn-open-excel-top"),
  btnOpenFolderTop: document.getElementById("btn-open-folder-top"),

  // Progress & KPIs
  progressStatusLabel: document.getElementById("progress-status-label"),
  progressSiteLabel: document.getElementById("progress-site-label"),
  mainProgressBar: document.getElementById("main-progress-bar"),
  kpiTotal: document.getElementById("kpi-total"),
  kpiDone: document.getElementById("kpi-done"),
  kpiNotFound: document.getElementById("kpi-not-found"),
  kpiVariants: document.getElementById("kpi-variants"),

  // Tables
  tabSheet1: document.getElementById("tab-sheet-1"),
  tabSheet2: document.getElementById("tab-sheet-2"),
  tableSheet1Elem: document.getElementById("table-sheet-1-elem"),
  tableSheet2Elem: document.getElementById("table-sheet-2-elem"),
  tbodySheet1: document.getElementById("tbody-sheet-1"),
  tbodySheet2: document.getElementById("tbody-sheet-2"),
  tableSearch: document.getElementById("table-search"),
  tableRowCount: document.getElementById("table-row-count"),

  // Websites
  websiteList: document.getElementById("website-list"),
  newWebsiteUrl: document.getElementById("new-website-url"),
  btnAddWebsite: document.getElementById("btn-add-website"),
  chkMissingOfficialPair: document.getElementById("chk-missing-official-pair"),
  chkSkipPreowned: document.getElementById("chk-skip-preowned"),

  // Browser & Resources
  badgeChrome: document.getElementById("badge-chrome"),
  badgeMsedge: document.getElementById("badge-msedge"),
  badgeBrave: document.getElementById("badge-brave"),
  selBrowserMode: document.getElementById("sel-browser-mode"),
  customBrowserGroup: document.getElementById("custom-browser-group"),
  customBrowserPath: document.getElementById("custom-browser-path"),
  btnInstallChromium: document.getElementById("btn-install-chromium"),
  installProgressBox: document.getElementById("install-progress-box"),
  installLog: document.getElementById("install-log"),
  gaugeCpuText: document.getElementById("gauge-cpu-text"),
  gaugeCpuBar: document.getElementById("gauge-cpu-bar"),
  gaugeRamText: document.getElementById("gauge-ram-text"),
  gaugeRamBar: document.getElementById("gauge-ram-bar"),
  rangeCpuCores: document.getElementById("range-cpu-cores"),
  rangeCpuPercent: document.getElementById("range-cpu-percent"),
  rangeRamGb: document.getElementById("range-ram-gb"),
  valCpuCores: document.getElementById("val-cpu-cores"),
  valCpuPercent: document.getElementById("val-cpu-percent"),
  valRamGb: document.getElementById("val-ram-gb"),

  // Gemini & Brand
  chkEnableGemini: document.getElementById("chk-enable-gemini"),
  geminiSettingsContainer: document.getElementById("gemini-settings-container"),
  btnOpenAiStudio: document.getElementById("btn-open-aistudio"),
  geminiApiKey: document.getElementById("gemini-api-key"),
  btnToggleKeyVisibility: document.getElementById("btn-toggle-key-visibility"),
  selGeminiModel: document.getElementById("sel-gemini-model"),
  selStructurePreset: document.getElementById("sel-structure-preset"),
  presetCardsGrid: document.getElementById("preset-cards-grid"),
  customStructureGroup: document.getElementById("custom-structure-group"),
  txtCustomStructure: document.getElementById("txt-custom-structure"),
  brandName: document.getElementById("brand-name"),
  brandUrl: document.getElementById("brand-url"),
  storeAddress: document.getElementById("store-address"),
  sellingPoints: document.getElementById("selling-points"),
  customRules: document.getElementById("custom-rules"),

  // Log & Sidebar Footer
  logTerminal: document.getElementById("log-terminal"),
  btnCopyLog: document.getElementById("btn-copy-log"),
  btnClearLog: document.getElementById("btn-clear-log"),
  miniCpu: document.getElementById("mini-cpu"),
  miniRam: document.getElementById("mini-ram"),
  miniRamBar: document.getElementById("mini-ram-bar"),
  btnThemeDark: document.getElementById("btn-theme-dark"),
  btnThemeLight: document.getElementById("btn-theme-light"),

  // Product Inspector Drawer
  drawerBackdrop: document.getElementById("drawer-backdrop"),
  productDrawer: document.getElementById("product-drawer"),
  btnDrawerPrev: document.getElementById("btn-drawer-prev"),
  btnDrawerNext: document.getElementById("btn-drawer-next"),
  btnCloseDrawer: document.getElementById("btn-close-drawer"),
  drawerProductName: document.getElementById("drawer-product-name"),
  drawerMeta: document.getElementById("drawer-meta"),
  drawerQuickActions: document.getElementById("drawer-quick-actions"),
  btnDescRendered: document.getElementById("btn-desc-rendered"),
  btnDescRaw: document.getElementById("btn-desc-raw"),
  btnCopyDescHtml: document.getElementById("btn-copy-desc-html"),
  drawerDescRendered: document.getElementById("drawer-desc-rendered"),
  drawerDescRaw: document.getElementById("drawer-desc-raw"),
  btnCopySpecs: document.getElementById("btn-copy-specs"),
  drawerSpecsContent: document.getElementById("drawer-specs-content"),
  drawerVariantsList: document.getElementById("drawer-variants-list"),

  // Dialog & Toasts
  confirmDialog: document.getElementById("confirm-dialog"),
  confirmDialogTitle: document.getElementById("confirm-dialog-title"),
  confirmDialogMessage: document.getElementById("confirm-dialog-message"),
  btnConfirmCancel: document.getElementById("btn-confirm-cancel"),
  btnConfirmOk: document.getElementById("btn-confirm-ok"),
  toastContainer: document.getElementById("toast-container"),
};

// Safe API Call Helper
const callApi = async (fnName, ...args) => {
  if (window.pywebview && window.pywebview.api && window.pywebview.api[fnName]) {
    try {
      return await window.pywebview.api[fnName](...args);
    } catch (e) {
      console.error(`API Error on ${fnName}:`, e);
      return null;
    }
  }
  return null;
};

// Toast Notifications (replaces native alert)
const showToast = (message, type = "info") => {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  elements.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(6px)";
    toast.style.transition = "all 0.2s ease";
    setTimeout(() => toast.remove(), 220);
  }, 3200);
};

// Native <dialog> Confirmation (replaces native confirm)
const showConfirmDialog = (title, message) => {
  return new Promise((resolve) => {
    elements.confirmDialogTitle.textContent = title;
    elements.confirmDialogMessage.textContent = message;

    const cleanup = (val) => {
      elements.btnConfirmCancel.onclick = null;
      elements.btnConfirmOk.onclick = null;
      if (elements.confirmDialog.open) elements.confirmDialog.close();
      resolve(val);
    };

    elements.btnConfirmCancel.onclick = () => cleanup(false);
    elements.btnConfirmOk.onclick = () => cleanup(true);
    elements.confirmDialog.oncancel = () => cleanup(false);
    elements.confirmDialog.showModal();
  });
};

// HTML Escape & Safe Sanitizer for Rendered Preview
const escapeHtml = (str) => {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
};

const sanitizeHtmlForPreview = (dirtyHtml) => {
  const doc = new DOMParser().parseFromString(dirtyHtml || "", "text/html");
  doc.querySelectorAll("script, style, iframe, object, embed").forEach((el) => el.remove());
  doc.querySelectorAll("*").forEach((el) => {
    for (const attr of Array.from(el.attributes)) {
      if (attr.name.toLowerCase().startsWith("on") || attr.value.trim().toLowerCase().startsWith("javascript:")) {
        el.removeAttribute(attr.name);
      }
    }
  });
  return doc.body.innerHTML;
};

const formatUrlLabel = (url) => {
  try {
    const parsed = new URL(url);
    const shortPath = parsed.pathname.length > 22 ? parsed.pathname.slice(0, 22) + "..." : parsed.pathname;
    return `${parsed.hostname.replace(/^www\./, "")}${shortPath === "/" ? "" : shortPath}`;
  } catch (e) {
    return url;
  }
};

// Global link/path openers
window.openPath = (p, evt) => {
  if (evt) evt.stopPropagation();
  if (!p) return;
  callApi("open_local_path", p);
};

window.openExternalUrl = (url, evt) => {
  if (evt) evt.stopPropagation();
  if (!url) return;
  callApi("open_external_url", url);
};

// Log entry helper
const addLogEntry = (msg, type = "info") => {
  const div = document.createElement("div");
  div.className = `log-entry ${type}`;
  const now = new Date().toLocaleTimeString();
  div.textContent = `[${now}] ${msg}`;
  elements.logTerminal.appendChild(div);
  elements.logTerminal.scrollTop = elements.logTerminal.scrollHeight;
};

// Global Event Handler called from Python JS Bridge
window.onBackendEvent = (event) => {
  const { type, payload } = event;

  switch (type) {
    case "log":
      addLogEntry(payload);
      break;

    case "progress":
      updateProgressUI(payload);
      break;

    case "row_updated":
      updateRowInTable(payload);
      break;

    case "captcha_alert":
      elements.captchaBanner.classList.remove("hidden");
      elements.captchaSiteText.textContent = `A verification challenge was detected on ${payload}. Please verify manually in the visible browser window.`;
      playAlertChime();
      addLogEntry(`CAPTCHA challenge detected on ${payload}. Paused for user verification.`, "warning");
      showToast("Human verification required in the browser window", "warning");
      break;

    case "status_change":
      updateAppStatus(payload);
      break;

    case "chromium_install_progress":
      elements.installProgressBox.classList.remove("hidden");
      elements.installLog.textContent += payload + "\n";
      elements.installProgressBox.scrollTop = elements.installProgressBox.scrollHeight;
      break;

    case "chromium_install_done":
      showToast(
        payload.success ? "Built-in Chromium installed successfully!" : "Chromium installation failed.",
        payload.success ? "success" : "error"
      );
      addLogEntry(payload.success ? "Chromium installed successfully!" : "Chromium installation failed.", payload.success ? "success" : "error");
      break;
  }
};

// Programmatic Tab Switching
const switchTab = (tabId) => {
  document.querySelectorAll(".nav-item").forEach((b) => {
    b.classList.toggle("active", b.getAttribute("data-tab") === tabId);
  });
  document.querySelectorAll(".tab-panel").forEach((p) => {
    p.classList.toggle("active", p.id === tabId);
  });
  if (tabId === "tab-results") {
    if (activeSheet === "sheet1") renderSheet1();
    else renderSheet2();
  }
};

document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.getAttribute("data-tab")));
});

// Pre-Flight Readiness Pills
const updateReadinessPills = () => {
  const hasProducts = inputMode === "manual"
    ? parseManualProducts().length > 0
    : Boolean(elements.inputXlsxPath.value || elements.resumeXlsxPath.value);
  const websiteCount = (appSettings.websites || []).length;
  const hasFolder = Boolean(elements.rootFolderPath.value);

  elements.pillReadyProducts.classList.toggle("ready", hasProducts);
  elements.pillReadyProductsText.textContent = hasProducts
    ? (inputMode === "manual" ? `${parseManualProducts().length} products ready` : "Input .xlsx ready")
    : "Add products";

  elements.pillReadyWebsites.classList.toggle("ready", websiteCount > 0);
  elements.pillReadyWebsitesText.textContent = websiteCount > 0
    ? `${websiteCount} website${websiteCount === 1 ? "" : "s"}`
    : "Add websites";

  elements.pillReadyFolder.classList.toggle("ready", hasFolder);
  elements.pillReadyFolderText.textContent = hasFolder ? "Image folder ready" : "Select image folder";
};

elements.pillReadyProducts.addEventListener("click", () => {
  if (inputMode === "manual") elements.manualQuickInput.focus();
  else elements.btnBrowseInput.click();
});
elements.pillReadyWebsites.addEventListener("click", () => switchTab("tab-websites"));
elements.pillReadyFolder.addEventListener("click", () => elements.btnBrowseFolder.click());
elements.btnJumpResults.addEventListener("click", () => switchTab("tab-results"));

// Clickable KPI Status Filter Cards
document.querySelectorAll(".kpi-card.clickable").forEach((card) => {
  card.addEventListener("click", () => {
    statusFilter = card.getAttribute("data-status-filter") || "all";
    document.querySelectorAll(".kpi-card.clickable").forEach((c) => {
      c.classList.toggle("active-filter", c === card);
    });
    if (activeSheet !== "sheet1") {
      elements.tabSheet1.click();
    } else {
      renderSheet1();
    }
  });
});

// Keyboard Shortcuts (Esc, Cmd/Ctrl+1..6, Cmd/Ctrl+K)
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !elements.productDrawer.classList.contains("hidden")) {
    closeProductDrawer();
    return;
  }
  if (e.metaKey || e.ctrlKey) {
    const tabOrder = ["tab-run", "tab-results", "tab-websites", "tab-resources", "tab-gemini", "tab-logs"];
    const num = parseInt(e.key, 10);
    if (num >= 1 && num <= 6) {
      e.preventDefault();
      switchTab(tabOrder[num - 1]);
    } else if (e.key.toLowerCase() === "k") {
      e.preventDefault();
      switchTab("tab-results");
      elements.tableSearch.focus();
    }
  }
});

// Sheet Tab Switching
elements.tabSheet1.addEventListener("click", () => {
  activeSheet = "sheet1";
  elements.tabSheet1.classList.add("active");
  elements.tabSheet2.classList.remove("active");
  elements.tableSheet1Elem.classList.remove("hidden");
  elements.tableSheet2Elem.classList.add("hidden");
  renderSheet1();
});

elements.tabSheet2.addEventListener("click", () => {
  activeSheet = "sheet2";
  elements.tabSheet2.classList.add("active");
  elements.tabSheet1.classList.remove("active");
  elements.tableSheet2Elem.classList.remove("hidden");
  elements.tableSheet1Elem.classList.add("hidden");
  renderSheet2();
});

// Theme Segmented Switcher
const applyTheme = (theme, persist = true) => {
  const next = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  elements.btnThemeDark.classList.toggle("active", next === "dark");
  elements.btnThemeLight.classList.toggle("active", next === "light");
  if (persist) {
    appSettings.theme = next;
    callApi("save_settings", appSettings);
  }
};

elements.btnThemeDark.addEventListener("click", () => applyTheme("dark", true));
elements.btnThemeLight.addEventListener("click", () => applyTheme("light", true));

// Input Mode Switcher & Manual Product Counter
const parseManualProducts = () => {
  const rawText = (elements.manualProductsInput.value || "").trim();
  if (!rawText) return [];
  return rawText
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean);
};

const updateManualCountBadge = () => {
  const count = parseManualProducts().length;
  elements.manualProductCount.textContent = `${count} product${count === 1 ? "" : "s"} ready`;
};

const setInputMode = (mode, persist = true) => {
  inputMode = mode === "manual" ? "manual" : "file";
  const isManual = inputMode === "manual";
  elements.btnModeManual.classList.toggle("active", isManual);
  elements.btnModeFile.classList.toggle("active", !isManual);
  elements.btnModeManual.setAttribute("aria-selected", String(isManual));
  elements.btnModeFile.setAttribute("aria-selected", String(!isManual));
  elements.manualInputGroup.classList.toggle("hidden", !isManual);
  elements.fileInputGroup.classList.toggle("hidden", isManual);
  elements.configModeHint.textContent = isManual
    ? "Type or paste one product per line — no input .xlsx file needed"
    : "Reads product names from Column A of your spreadsheet";
  updateManualCountBadge();
  if (persist) saveCurrentSettings();
};

elements.btnModeFile.addEventListener("click", () => setInputMode("file", true));
elements.btnModeManual.addEventListener("click", () => setInputMode("manual", true));

const appendQuickProduct = () => {
  const val = (elements.manualQuickInput.value || "").trim();
  if (!val) return;
  const current = (elements.manualProductsInput.value || "").trim();
  elements.manualProductsInput.value = current ? `${current}\n${val}` : val;
  elements.manualQuickInput.value = "";
  updateManualCountBadge();
  saveCurrentSettings();
};

elements.btnManualQuickAdd.addEventListener("click", appendQuickProduct);
elements.manualQuickInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    appendQuickProduct();
  }
});

elements.manualProductsInput.addEventListener("input", updateManualCountBadge);

elements.btnClearManual.addEventListener("click", () => {
  elements.manualProductsInput.value = "";
  elements.manualQuickInput.value = "";
  updateManualCountBadge();
  saveCurrentSettings();
  showToast("Manual product list cleared", "info");
});

// Progress & KPIs
const updateProgressUI = ({ current, total, product_name, stage }) => {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  elements.progressStatusLabel.textContent = `${current} / ${total} Products (${pct}%)`;
  elements.progressSiteLabel.textContent = product_name ? `${product_name} • ${stage}` : "Idle";
  elements.mainProgressBar.style.width = `${pct}%`;
  elements.headerMiniProgress.textContent = `${current} / ${total}`;
};

const updateKpiStrip = () => {
  const all = Array.from(productsMap.values());
  let done = 0;
  let notFound = 0;
  let totalVariants = 0;

  for (const r of all) {
    if (r.status === "Done") done++;
    else if (r.status === "Not Found") notFound++;
    totalVariants += Number(r.variant_count || 0);
  }

  elements.kpiTotal.textContent = String(all.length);
  elements.kpiDone.textContent = String(done);
  elements.kpiNotFound.textContent = String(notFound);
  elements.kpiVariants.textContent = String(totalVariants);
  elements.navResultsCount.textContent = String(all.length);
};

// Update Row in Table
const updateRowInTable = (record) => {
  productsMap.set(record.product_name, record);
  lastUpdatedProductName = record.product_name;
  updateKpiStrip();
  if (activeSheet === "sheet1") {
    renderSheet1();
  }
};

// Render Sheet 1 (Products)
const renderSheet1 = () => {
  const filter = (elements.tableSearch.value || "").toLowerCase();
  const records = Array.from(productsMap.values()).filter((r) => {
    const matchesSearch = r.product_name.toLowerCase().includes(filter);
    const matchesStatus = statusFilter === "all" || r.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  elements.tableRowCount.textContent = `${records.length} product${records.length === 1 ? "" : "s"}`;

  if (records.length === 0) {
    elements.tbodySheet1.innerHTML = `<tr>
      <td colspan="8" class="empty-state-cell">
        <div class="empty-state-box">
          <div class="empty-state-icon" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
          </div>
          <div class="empty-state-title">${productsMap.size === 0 ? "No products loaded yet" : "No matching products"}</div>
          <div class="empty-state-steps">
            <span>1. Upload .xlsx or enter products manually</span>
            <span class="step-arrow">&rarr;</span>
            <span>2. Add stores in Websites Waterfall</span>
            <span class="step-arrow">&rarr;</span>
            <span>3. Click Start Scraping</span>
          </div>
        </div>
      </td>
    </tr>`;
    return;
  }

  const externalSvg = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;
  const folderSvg = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;

  let html = "";
  for (const r of records) {
    const statusCls = (r.status || "pending").toLowerCase().replace(/\s+/g, "-");
    const regPrice = r.default_price ? r.default_price.regular_display : "-";
    const discPrice = r.default_price ? r.default_price.discounted_display || "-" : "-";
    const safeNameArg = escapeHtml(JSON.stringify(r.product_name));

    const folderCell = r.image_folder
      ? `<button class="cell-link-pill" type="button" onclick="openPath(${escapeHtml(JSON.stringify(r.image_folder))}, event)">${folderSvg}<span>Open Folder</span></button>`
      : `<span class="desc-snippet">-</span>`;

    const linksList = Array.isArray(r.page_links) ? r.page_links.filter(Boolean) : [];
    const linkCell = linksList.length > 0
      ? `<div class="cell-links-stack">${linksList.map((u) =>
          `<button class="cell-link-pill" type="button" title="${escapeHtml(u)}" onclick="openExternalUrl(${escapeHtml(JSON.stringify(u))}, event)">${externalSvg}<span>${escapeHtml(formatUrlLabel(u))}</span></button>`
        ).join("")}</div>`
      : `<span class="desc-snippet">-</span>`;

    const descPreview = r.description_preview && r.description_preview !== "not found"
      ? r.description_preview
      : (r.status === "Pending" ? "-" : "not found");

    const descCell = descPreview !== "-" && descPreview !== "not found"
      ? `<div class="desc-cell-wrap">
           <span class="desc-snippet" title="${escapeHtml(descPreview)}">${escapeHtml(descPreview)}</span>
           <button class="btn btn-secondary btn-xs" type="button" onclick="openProductDrawer(${safeNameArg}, event)">View</button>
         </div>`
      : `<span class="desc-snippet">${escapeHtml(descPreview)}</span>`;

    const flashCls = r.product_name === lastUpdatedProductName ? " row-flash" : "";
    html += `<tr class="clickable-row${flashCls}" onclick="openProductDrawer(${safeNameArg})">
      <td><strong>${escapeHtml(r.product_name)}</strong></td>
      <td><span class="status-cell ${statusCls}">${escapeHtml(r.status || "Pending")}</span></td>
      <td><span class="price-val">${escapeHtml(regPrice)}</span></td>
      <td><span class="price-val ${discPrice !== "-" ? "discount" : ""}">${escapeHtml(discPrice)}</span></td>
      <td>${folderCell}</td>
      <td>${linkCell}</td>
      <td><span class="specs-snippet" title="${escapeHtml(r.specifications || "")}">${escapeHtml(r.specifications || "-")}</span></td>
      <td>${descCell}</td>
    </tr>`;
  }
  elements.tbodySheet1.innerHTML = html;
};

// Render Sheet 2 (Variants)
const renderSheet2 = async () => {
  const filter = (elements.tableSearch.value || "").toLowerCase();
  const data = await callApi("get_current_table_data");
  if (data && data.variants) {
    variantsList = data.variants;
  }

  const filtered = variantsList.filter((v) =>
    (v["Product name"] || "").toLowerCase().includes(filter) ||
    (v["Colour"] || "").toLowerCase().includes(filter) ||
    (v["Region"] || "").toLowerCase().includes(filter)
  );

  elements.tableRowCount.textContent = `${filtered.length} variant row${filtered.length === 1 ? "" : "s"}`;

  if (filtered.length === 0) {
    elements.tbodySheet2.innerHTML = `<tr>
      <td colspan="10" class="empty-state-cell">
        <div class="empty-state-box">
          <div class="empty-state-title">No variant combinations captured yet</div>
          <div class="empty-state-sub">Every clicked color, storage, region, and official/unofficial price will appear here live.</div>
        </div>
      </td>
    </tr>`;
    return;
  }

  const externalSvg = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;

  let html = "";
  for (const v of filtered) {
    const pageUrl = v["Page Link"] || "";
    const linkHtml = pageUrl && pageUrl.startsWith("http")
      ? `<button class="cell-link-pill" type="button" title="${escapeHtml(pageUrl)}" onclick="openExternalUrl(${escapeHtml(JSON.stringify(pageUrl))}, event)">${externalSvg}<span>${escapeHtml(formatUrlLabel(pageUrl))}</span></button>`
      : `<span class="desc-snippet">-</span>`;

    html += `<tr>
      <td><strong>${escapeHtml(v["Product name"] || "")}</strong></td>
      <td>${escapeHtml(formatUrlLabel(v["Source Website"] || "-"))}</td>
      <td>${escapeHtml(v["Official/Unofficial"] || "-")}</td>
      <td>${escapeHtml(v["Region"] || "-")}</td>
      <td>${escapeHtml(v["Storage"] || "-")}</td>
      <td>${escapeHtml(v["Colour"] || "-")}</td>
      <td><span class="price-val">${escapeHtml(v["Regular Price"] || "-")}</span></td>
      <td><span class="price-val discount">${escapeHtml(v["Discounted Price"] || "-")}</span></td>
      <td>${escapeHtml(v["Stock Status"] || "-")}</td>
      <td>${linkHtml}</td>
    </tr>`;
  }
  elements.tbodySheet2.innerHTML = html;
};

// Slide-Over Product Inspector Drawer
window.openProductDrawer = async (productName, evt) => {
  if (evt) evt.stopPropagation();
  const detail = await callApi("get_product_detail", productName);
  const summary = productsMap.get(productName);
  activeDrawerDetail = detail || summary;
  if (!activeDrawerDetail) return;

  elements.drawerProductName.textContent = activeDrawerDetail.product_name || productName;

  const statusCls = (activeDrawerDetail.status || "pending").toLowerCase().replace(/\s+/g, "-");
  const regP = activeDrawerDetail.default_price ? activeDrawerDetail.default_price.regular_display : "not found";
  const discP = activeDrawerDetail.default_price ? activeDrawerDetail.default_price.discounted_display : "";
  elements.drawerMeta.innerHTML = `
    <span class="status-cell ${statusCls}">${escapeHtml(activeDrawerDetail.status || "Pending")}</span>
    <span class="count-pill">Regular: ${escapeHtml(regP)}</span>
    ${discP ? `<span class="count-pill" style="background: var(--success-soft); color: var(--success);">Discounted: ${escapeHtml(discP)}</span>` : ""}
  `;

  // Quick action buttons
  let actionsHtml = "";
  const links = activeDrawerDetail.page_links || [];
  links.forEach((u, idx) => {
    actionsHtml += `<button class="btn btn-secondary btn-xs" type="button" onclick="openExternalUrl(${escapeHtml(JSON.stringify(u))}, event)">Open Page ${links.length > 1 ? idx + 1 : ""} &nearr;</button>`;
  });
  if (activeDrawerDetail.image_folder) {
    actionsHtml += `<button class="btn btn-secondary btn-xs" type="button" onclick="openPath(${escapeHtml(JSON.stringify(activeDrawerDetail.image_folder))}, event)">Open Image Folder</button>`;
  }
  elements.drawerQuickActions.innerHTML = actionsHtml || `<span class="drawer-pane-hint">No external links or image folder yet.</span>`;

  // Description pane
  const rawDesc = activeDrawerDetail.description_html || activeDrawerDetail.description_preview || "not found";
  elements.drawerDescRendered.innerHTML = rawDesc === "not found"
    ? `<p style="color: var(--text-muted);">No description available for this product yet.</p>`
    : sanitizeHtmlForPreview(rawDesc);
  elements.drawerDescRaw.textContent = rawDesc;

  // Specs pane
  elements.drawerSpecsContent.textContent = activeDrawerDetail.specifications || "not found";

  // Variants pane
  const combos = activeDrawerDetail.variants || [];
  if (combos.length === 0) {
    elements.drawerVariantsList.innerHTML = `<div class="empty-state-sub">No variant combinations captured for this product yet.</div>`;
  } else {
    elements.drawerVariantsList.innerHTML = combos.map((v) => {
      const attrs = [v["Official/Unofficial"], v["Region"], v["Storage"], v["Colour"]]
        .filter((x) => x && x !== "not found" && x !== "-")
        .join(" • ") || "Default Variant";
      return `<div class="drawer-variant-card">
        <div>
          <strong>${escapeHtml(attrs)}</strong>
          <div style="font-size: 11.5px; color: var(--text-muted);">${escapeHtml(v["Stock Status"] || "")}</div>
        </div>
        <div style="text-align: right;">
          <div class="price-val">${escapeHtml(v["Regular Price"] || "not found")}</div>
          ${v["Discounted Price"] && v["Discounted Price"] !== "-" ? `<div class="price-val discount" style="font-size: 11.5px;">${escapeHtml(v["Discounted Price"])}</div>` : ""}
        </div>
      </div>`;
    }).join("");
  }

  const names = Array.from(productsMap.keys());
  const curIdx = names.indexOf(activeDrawerDetail.product_name || productName);
  elements.btnDrawerPrev.disabled = curIdx <= 0;
  elements.btnDrawerNext.disabled = curIdx === -1 || curIdx >= names.length - 1;

  elements.drawerBackdrop.classList.remove("hidden");
  elements.productDrawer.classList.remove("hidden");
};

const stepDrawerProduct = (delta) => {
  if (!activeDrawerDetail) return;
  const names = Array.from(productsMap.keys());
  const curIdx = names.indexOf(activeDrawerDetail.product_name);
  const nextIdx = curIdx + delta;
  if (nextIdx >= 0 && nextIdx < names.length) {
    openProductDrawer(names[nextIdx]);
  }
};

elements.btnDrawerPrev.addEventListener("click", () => stepDrawerProduct(-1));
elements.btnDrawerNext.addEventListener("click", () => stepDrawerProduct(1));

const closeProductDrawer = () => {
  elements.drawerBackdrop.classList.add("hidden");
  elements.productDrawer.classList.add("hidden");
};

elements.btnCloseDrawer.addEventListener("click", closeProductDrawer);
elements.drawerBackdrop.addEventListener("click", closeProductDrawer);

document.querySelectorAll(".drawer-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".drawer-tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".drawer-pane").forEach((p) => p.classList.add("hidden"));
    tab.classList.add("active");
    const target = tab.getAttribute("data-drawer-tab");
    document.getElementById(`drawer-pane-${target}`).classList.remove("hidden");
  });
});

elements.btnDescRendered.addEventListener("click", () => {
  elements.btnDescRendered.classList.add("active");
  elements.btnDescRaw.classList.remove("active");
  elements.drawerDescRendered.classList.remove("hidden");
  elements.drawerDescRaw.classList.add("hidden");
});

elements.btnDescRaw.addEventListener("click", () => {
  elements.btnDescRaw.classList.add("active");
  elements.btnDescRendered.classList.remove("active");
  elements.drawerDescRaw.classList.remove("hidden");
  elements.drawerDescRendered.classList.add("hidden");
});

elements.btnCopyDescHtml.addEventListener("click", () => {
  if (!activeDrawerDetail) return;
  navigator.clipboard.writeText(activeDrawerDetail.description_html || "");
  showToast("HTML description copied to clipboard", "success");
});

elements.btnCopySpecs.addEventListener("click", () => {
  if (!activeDrawerDetail) return;
  navigator.clipboard.writeText(activeDrawerDetail.specifications || "");
  showToast("Specifications copied to clipboard", "success");
});

// App Status Updates
const updateAppStatus = (status) => {
  elements.statusBadge.className = `status-pill ${status.toLowerCase()}`;
  elements.statusBadgeText.textContent = status;

  if (status === "Running") {
    isScrapingRunning = true;
    isScrapingPaused = false;
    elements.btnStart.disabled = true;
    elements.btnPause.disabled = false;
    elements.btnPause.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg><span>Pause</span>`;
    elements.btnStop.disabled = false;
    elements.headerLiveControls.classList.remove("hidden");
    elements.btnHeaderPause.textContent = "Pause";
    elements.mainProgressBar.classList.add("active-shimmer");
    elements.statusDescription.textContent = "Scraping active in visible Incognito browser...";
  } else if (status === "Paused") {
    isScrapingPaused = true;
    elements.btnPause.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>Resume</span>`;
    elements.headerLiveControls.classList.remove("hidden");
    elements.btnHeaderPause.textContent = "Resume";
    elements.mainProgressBar.classList.remove("active-shimmer");
    elements.statusDescription.textContent = "Paused cleanly at checkpoint.";
  } else {
    isScrapingRunning = false;
    isScrapingPaused = false;
    elements.btnStart.disabled = false;
    elements.btnPause.disabled = true;
    elements.btnStop.disabled = true;
    elements.headerLiveControls.classList.add("hidden");
    elements.mainProgressBar.classList.remove("active-shimmer");
    elements.captchaBanner.classList.add("hidden");
    elements.statusDescription.textContent = status === "Finished" ? "Scraping complete — all rows saved." : "Ready to scrape";
    if (status === "Finished") {
      playAlertChime();
      showToast("Scraping finished! All rows saved to Excel.", "success");
    }
  }
};

elements.btnHeaderPause.addEventListener("click", () => elements.btnPause.click());
elements.btnHeaderStop.addEventListener("click", () => elements.btnStop.click());

// Website List Rendering
const renderWebsites = () => {
  const websites = appSettings.websites || [];
  elements.navWebsitesCount.textContent = String(websites.length);
  elements.websiteList.innerHTML = "";

  if (websites.length === 0) {
    elements.websiteList.innerHTML = '<li class="empty-state-sub" style="padding: 18px; text-align: center;">No websites added yet. Add store URLs above to set the waterfall priority order.</li>';
    return;
  }

  websites.forEach((url, idx) => {
    const li = document.createElement("li");
    li.className = "website-item";
    li.innerHTML = `
      <div class="website-info">
        <span class="priority-badge">#${idx + 1}</span>
        <strong>${escapeHtml(url)}</strong>
      </div>
      <div class="website-actions">
        <button class="btn btn-secondary btn-xs" type="button" onclick="moveWebsite(${idx}, -1)" ${idx === 0 ? "disabled" : ""} title="Move up">&uarr;</button>
        <button class="btn btn-secondary btn-xs" type="button" onclick="moveWebsite(${idx}, 1)" ${idx === websites.length - 1 ? "disabled" : ""} title="Move down">&darr;</button>
        <button class="btn btn-ghost btn-xs" type="button" onclick="removeWebsite(${idx})" title="Remove website" style="color: var(--danger);">&times;</button>
      </div>
    `;
    elements.websiteList.appendChild(li);
  });
};

window.moveWebsite = (idx, dir) => {
  const list = appSettings.websites;
  const target = idx + dir;
  if (target < 0 || target >= list.length) return;
  [list[idx], list[target]] = [list[target], list[idx]];
  saveCurrentSettings();
  renderWebsites();
};

window.removeWebsite = (idx) => {
  appSettings.websites.splice(idx, 1);
  saveCurrentSettings();
  renderWebsites();
};

const addWebsiteFromInput = () => {
  let url = (elements.newWebsiteUrl.value || "").trim();
  if (!url) return;
  if (!/^https?:\/\//i.test(url)) url = `https://${url}`;
  if (!appSettings.websites) appSettings.websites = [];
  if (!appSettings.websites.includes(url)) {
    appSettings.websites.push(url);
    saveCurrentSettings();
    renderWebsites();
    showToast(`Added ${formatUrlLabel(url)}`, "success");
  }
  elements.newWebsiteUrl.value = "";
};

elements.btnAddWebsite.addEventListener("click", addWebsiteFromInput);
elements.newWebsiteUrl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    addWebsiteFromInput();
  }
});

// File Browsing Event Handlers
elements.btnBrowseInput.addEventListener("click", async () => {
  const path = await callApi("pick_input_file");
  if (path) {
    elements.inputXlsxPath.value = path;
    appSettings.last_input_xlsx = path;
    saveCurrentSettings();
  }
});

elements.btnBrowseOutput.addEventListener("click", async () => {
  const path = await callApi("pick_output_file");
  if (path) {
    elements.outputXlsxPath.value = path;
    appSettings.last_output_xlsx = path;
    saveCurrentSettings();
  }
});

elements.btnBrowseResume.addEventListener("click", async () => {
  const path = await callApi("pick_resume_file");
  if (path) elements.resumeXlsxPath.value = path;
});

elements.btnClearResume.addEventListener("click", () => {
  elements.resumeXlsxPath.value = "";
});

elements.btnBrowseFolder.addEventListener("click", async () => {
  const folder = await callApi("pick_folder");
  if (folder) {
    elements.rootFolderPath.value = folder;
    appSettings.root_image_folder = folder;
    saveCurrentSettings();
  }
});

elements.btnOpenExcelTop.addEventListener("click", () => {
  const path = elements.outputXlsxPath.value || elements.resumeXlsxPath.value;
  if (!path) return showToast("No output .xlsx file selected yet", "warning");
  callApi("open_local_path", path);
});

elements.btnOpenFolderTop.addEventListener("click", () => {
  const folder = elements.rootFolderPath.value;
  if (!folder) return showToast("No root image folder selected yet", "warning");
  callApi("open_local_path", folder);
});

// Playback Controls
elements.btnStart.addEventListener("click", async () => {
  const inputPath = elements.inputXlsxPath.value;
  let outputPath = elements.outputXlsxPath.value;
  const rootFolder = elements.rootFolderPath.value;
  const resumePath = elements.resumeXlsxPath.value;

  let manualProducts = null;

  if (inputMode === "manual") {
    manualProducts = parseManualProducts();
    if (manualProducts.length === 0) {
      showToast("Please enter at least one product name to search", "warning");
      return;
    }
    if (!outputPath) {
      outputPath = rootFolder
        ? rootFolder.replace(/[\\/]+$/, "") + "/manual_scraper_output.xlsx"
        : "manual_scraper_output.xlsx";
      elements.outputXlsxPath.value = outputPath;
    }
  } else {
    if (!inputPath && !resumePath) {
      showToast("Please select an Input .xlsx file or switch to Manual Entry", "warning");
      return;
    }
    if (!outputPath) {
      showToast("Please choose a destination for the Output .xlsx file", "warning");
      return;
    }
  }

  if (!rootFolder) {
    showToast("Please select a Root Image Folder", "warning");
    return;
  }

  if (!appSettings.websites || appSettings.websites.length === 0) {
    showToast("Please add at least one website in Websites Waterfall first", "warning");
    return;
  }

  saveCurrentSettings();
  productsMap.clear();
  statusFilter = "all";
  document.querySelectorAll(".kpi-card.clickable").forEach((c) => {
    c.classList.toggle("active-filter", c.getAttribute("data-status-filter") === "all");
  });
  updateKpiStrip();
  renderSheet1();
  switchTab("tab-results");
  addLogEntry(
    `Starting scraper queue (${inputMode === "manual" ? `${manualProducts.length} manual products` : "file mode"})...`,
    "info"
  );
  await callApi(
    "start_scraping",
    inputMode === "manual" ? null : inputPath,
    outputPath,
    rootFolder,
    resumePath || null,
    manualProducts
  );
});

elements.btnPause.addEventListener("click", () => {
  if (isScrapingPaused) callApi("resume_scraping");
  else callApi("pause_scraping");
});

elements.btnStop.addEventListener("click", async () => {
  const confirmed = await showConfirmDialog(
    "Stop Scraping?",
    "All completed rows and downloaded images are already saved to disk and can be resumed later."
  );
  if (confirmed) callApi("stop_scraping");
});

elements.btnCaptchaDone.addEventListener("click", () => {
  elements.captchaBanner.classList.add("hidden");
  callApi("verify_captcha_done");
});

// Sliders & Browser Controls
elements.rangeCpuCores.addEventListener("input", (e) => {
  elements.valCpuCores.textContent = `${e.target.value} core${e.target.value === "1" ? "" : "s"}`;
  appSettings.max_cpu_cores = parseInt(e.target.value, 10);
  saveCurrentSettings();
});

elements.rangeCpuPercent.addEventListener("input", (e) => {
  elements.valCpuPercent.textContent = `${e.target.value}%`;
  appSettings.max_cpu_percent = parseInt(e.target.value, 10);
  saveCurrentSettings();
});

elements.rangeRamGb.addEventListener("input", (e) => {
  elements.valRamGb.textContent = `${parseFloat(e.target.value).toFixed(1)} GB`;
  appSettings.max_ram_gb = parseFloat(e.target.value);
  saveCurrentSettings();
});

elements.selBrowserMode.addEventListener("change", (e) => {
  appSettings.browser_mode = e.target.value;
  elements.customBrowserGroup.classList.toggle("hidden", e.target.value !== "custom");
  saveCurrentSettings();
});

elements.btnInstallChromium.addEventListener("click", () => {
  elements.installProgressBox.classList.remove("hidden");
  elements.installLog.textContent = "Initiating bundled Chromium installation...\n";
  callApi("install_bundled_chromium");
});

// Gemini & Brand Controls
elements.btnOpenAiStudio.addEventListener("click", () => {
  callApi("open_external_url", "https://aistudio.google.com/");
});

elements.chkEnableGemini.addEventListener("change", () => {
  elements.geminiSettingsContainer.style.opacity = elements.chkEnableGemini.checked ? "1" : "0.5";
  saveCurrentSettings();
});

const selectStructurePreset = (preset, persist = true) => {
  const val = preset || "standard";
  elements.selStructurePreset.value = val;
  appSettings.gemini_structure_preset = val;
  document.querySelectorAll(".preset-card").forEach((card) => {
    card.classList.toggle("active", card.getAttribute("data-preset") === val);
  });
  elements.customStructureGroup.classList.toggle("hidden", val !== "custom");
  if (persist) saveCurrentSettings();
};

document.querySelectorAll(".preset-card").forEach((card) => {
  card.addEventListener("click", () => selectStructurePreset(card.getAttribute("data-preset"), true));
});

elements.btnToggleKeyVisibility.addEventListener("click", () => {
  const isPass = elements.geminiApiKey.type === "password";
  elements.geminiApiKey.type = isPass ? "text" : "password";
  elements.btnToggleKeyVisibility.textContent = isPass ? "Hide" : "Show";
});

const syncSidebarSubtitle = () => {
  const name = (elements.brandName.value || "").trim();
  elements.sidebarBrandSubtitle.textContent = name || "Catalog Intelligence";
};
elements.brandName.addEventListener("input", syncSidebarSubtitle);

// Table search filter
elements.tableSearch.addEventListener("input", () => {
  if (activeSheet === "sheet1") renderSheet1();
  else renderSheet2();
});

// Logs copy & clear
elements.btnCopyLog.addEventListener("click", () => {
  navigator.clipboard.writeText(elements.logTerminal.innerText);
  showToast("Activity log copied to clipboard", "success");
});

elements.btnClearLog.addEventListener("click", () => {
  elements.logTerminal.innerHTML = '<div class="log-entry info">[System] Log cleared.</div>';
});

// Save & Load Settings
const saveCurrentSettings = () => {
  appSettings.input_mode = inputMode;
  appSettings.manual_products_text = elements.manualProductsInput.value;
  appSettings.root_image_folder = elements.rootFolderPath.value;
  appSettings.last_input_xlsx = elements.inputXlsxPath.value;
  appSettings.last_output_xlsx = elements.outputXlsxPath.value;
  appSettings.browser_mode = elements.selBrowserMode.value;
  appSettings.custom_browser_path = elements.customBrowserPath.value;
  appSettings.search_missing_official_unofficial_pair = elements.chkMissingOfficialPair.checked;
  appSettings.skip_preowned_devices = elements.chkSkipPreowned.checked;
  appSettings.enable_gemini = elements.chkEnableGemini.checked;
  appSettings.gemini_api_key = elements.geminiApiKey.value;
  appSettings.gemini_model = elements.selGeminiModel.value;
  appSettings.gemini_structure_preset = elements.selStructurePreset.value;
  appSettings.gemini_custom_structure = elements.txtCustomStructure.value;
  appSettings.brand_name = elements.brandName.value;
  appSettings.brand_url = elements.brandUrl.value;
  appSettings.store_address = elements.storeAddress.value;
  appSettings.selling_points = elements.sellingPoints.value;
  appSettings.custom_rules = elements.customRules.value;

  callApi("save_settings", appSettings);
  updateReadinessPills();
};

[
  elements.manualProductsInput,
  elements.customBrowserPath,
  elements.chkMissingOfficialPair,
  elements.chkSkipPreowned,
  elements.geminiApiKey,
  elements.selGeminiModel,
  elements.txtCustomStructure,
  elements.brandName,
  elements.brandUrl,
  elements.storeAddress,
  elements.sellingPoints,
  elements.customRules,
].forEach((el) => {
  el.addEventListener("change", saveCurrentSettings);
});

const loadSettingsIntoUI = (s) => {
  appSettings = s || {};
  elements.manualProductsInput.value = s.manual_products_text || "";
  setInputMode(s.input_mode || "file", false);

  elements.inputXlsxPath.value = s.last_input_xlsx || "";
  elements.outputXlsxPath.value = s.last_output_xlsx || "";
  elements.rootFolderPath.value = s.root_image_folder || "";

  elements.selBrowserMode.value = s.browser_mode || "auto";
  elements.customBrowserPath.value = s.custom_browser_path || "";
  elements.customBrowserGroup.classList.toggle("hidden", s.browser_mode !== "custom");

  elements.rangeCpuCores.value = s.max_cpu_cores || 2;
  elements.valCpuCores.textContent = `${elements.rangeCpuCores.value} cores`;

  elements.rangeCpuPercent.value = s.max_cpu_percent || 40;
  elements.valCpuPercent.textContent = `${elements.rangeCpuPercent.value}%`;

  elements.rangeRamGb.value = s.max_ram_gb || 2.0;
  elements.valRamGb.textContent = `${parseFloat(elements.rangeRamGb.value).toFixed(1)} GB`;

  elements.chkMissingOfficialPair.checked = s.search_missing_official_unofficial_pair ?? true;
  elements.chkSkipPreowned.checked = s.skip_preowned_devices ?? true;

  elements.chkEnableGemini.checked = s.enable_gemini ?? true;
  elements.geminiSettingsContainer.style.opacity = elements.chkEnableGemini.checked ? "1" : "0.5";
  elements.geminiApiKey.value = s.gemini_api_key || "";
  elements.selGeminiModel.value = s.gemini_model || "gemini-2.5-flash";
  selectStructurePreset(s.gemini_structure_preset || "standard", false);
  elements.txtCustomStructure.value = s.gemini_custom_structure || "";

  elements.brandName.value = s.brand_name || "";
  elements.brandUrl.value = s.brand_url || "";
  elements.storeAddress.value = s.store_address || "";
  elements.sellingPoints.value = s.selling_points || "";
  elements.customRules.value = s.custom_rules || "";
  syncSidebarSubtitle();

  applyTheme(s.theme || "dark", false);
  renderWebsites();
  updateReadinessPills();
};

// Browser Auto-Detection Badges
const refreshBrowserBadges = async () => {
  const detected = await callApi("detect_browsers");
  if (!detected) return;
  const setBadge = (el, found) => {
    el.className = `detect-badge ${found ? "found" : "missing"}`;
    el.textContent = found ? "Detected" : "Not Installed";
  };
  setBadge(elements.badgeChrome, Boolean(detected.chrome));
  setBadge(elements.badgeMsedge, Boolean(detected.msedge));
  setBadge(elements.badgeBrave, Boolean(detected.brave));
};

// Resource Poller (updates sidebar mini meter + full gauges)
const pollResources = async () => {
  const res = await callApi("get_live_resources");
  if (!res) return;

  elements.miniCpu.textContent = `${res.cpu_percent}%`;
  elements.miniRam.textContent = `${res.memory_mb} MB`;
  elements.miniRamBar.style.width = `${res.memory_percent_of_cap}%`;

  const cpuPct = Math.min(res.cpu_percent, 100);
  elements.gaugeCpuText.textContent = `${res.cpu_percent}% (Cap: ${res.max_cpu_percent}%)`;
  elements.gaugeCpuBar.style.width = `${cpuPct}%`;

  elements.gaugeRamText.textContent = `${res.memory_mb} MB / ${res.max_ram_gb} GB`;
  elements.gaugeRamBar.style.width = `${res.memory_percent_of_cap}%`;

  const barColor = res.memory_percent_of_cap > 85
    ? "var(--danger)"
    : (res.cpu_percent > res.max_cpu_percent ? "var(--warning)" : "linear-gradient(90deg, var(--accent-primary), var(--accent-primary-2))");
  elements.miniRamBar.style.background = barColor;
  elements.gaugeRamBar.style.background = res.memory_percent_of_cap > 85 ? "var(--danger)" : "linear-gradient(90deg, var(--accent-primary), var(--accent-primary-2))";
  elements.gaugeCpuBar.style.background = res.cpu_percent > res.max_cpu_percent ? "var(--warning)" : "linear-gradient(90deg, var(--accent-primary), var(--accent-primary-2))";
};

// Initialization
window.addEventListener("pywebviewready", async () => {
  const settings = await callApi("get_settings");
  if (settings) {
    loadSettingsIntoUI(settings);
  }
  refreshBrowserBadges();
  pollResources();
  setInterval(pollResources, 1500);
});
