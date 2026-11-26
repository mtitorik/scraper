// State management
let appSettings = {};
let inputMode = "file";
let statusFilter = "all";
let lastUpdatedProductName = null;
let expandedProducts = new Set(); // product_name strings with expanded variant dropdowns
let productsMap = new Map(); // product_name -> summary dict
let isScrapingRunning = false;
let isScrapingPaused = false;
let activeDrawerDetail = null;
let runStartedAtMs = 0;
let isBulkEditMode = false;

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
  sidebar: document.getElementById("sidebar"),
  btnToggleSidebar: document.getElementById("btn-toggle-sidebar"),
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

  btnOpenCmdk: document.getElementById("btn-open-cmdk"),
  cmdkDialog: document.getElementById("cmdk-dialog"),
  cmdkInput: document.getElementById("cmdk-input"),
  cmdkList: document.getElementById("cmdk-list"),

  // Input mode & manual entry composer
  btnModeFile: document.getElementById("btn-mode-file"),
  btnModeManual: document.getElementById("btn-mode-manual"),
  configModeHint: document.getElementById("config-mode-hint"),
  fileInputGroup: document.getElementById("file-input-group"),
  manualInputGroup: document.getElementById("manual-input-group"),
  manualQuickInput: document.getElementById("manual-quick-input"),
  btnManualQuickAdd: document.getElementById("btn-manual-quick-add"),
  manualQueueWrap: document.getElementById("manual-queue-wrap"),
  manualProductList: document.getElementById("manual-product-list"),
  manualQueueEmpty: document.getElementById("manual-queue-empty"),
  manualBulkWrap: document.getElementById("manual-bulk-wrap"),
  manualProductsInput: document.getElementById("manual-products-input"),
  manualProductCount: document.getElementById("manual-product-count"),
  btnPasteClipboard: document.getElementById("btn-paste-clipboard"),
  btnToggleBulkMode: document.getElementById("btn-toggle-bulk-mode"),
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

  // Table
  btnRetryNotFound: document.getElementById("btn-retry-not-found"),
  tableSheet1Elem: document.getElementById("table-sheet-1-elem"),
  tbodySheet1: document.getElementById("tbody-sheet-1"),
  tableSearch: document.getElementById("table-search"),
  tableRowCount: document.getElementById("table-row-count"),

  // Websites & Matching/Filtering Rules
  websiteList: document.getElementById("website-list"),
  newWebsiteUrl: document.getElementById("new-website-url"),
  btnAddWebsite: document.getElementById("btn-add-website"),
  chkMissingOfficialPair: document.getElementById("chk-missing-official-pair"),
  chkSkipPreowned: document.getElementById("chk-skip-preowned"),
  chkSkipAccessories: document.getElementById("chk-skip-accessories"),
  chkStrictModel: document.getElementById("chk-strict-model"),
  chkFallbackSku: document.getElementById("chk-fallback-sku"),
  chkScrapeVariants: document.getElementById("chk-scrape-variants"),
  chkDownloadImages: document.getElementById("chk-download-images"),
  rangeMaxImages: document.getElementById("range-max-images"),
  valMaxImages: document.getElementById("val-max-images"),
  txtCustomExcludes: document.getElementById("txt-custom-excludes"),

  // Browser, Speed & Resources
  badgeChrome: document.getElementById("badge-chrome"),
  badgeMsedge: document.getElementById("badge-msedge"),
  badgeBrave: document.getElementById("badge-brave"),
  selBrowserMode: document.getElementById("sel-browser-mode"),
  customBrowserGroup: document.getElementById("custom-browser-group"),
  customBrowserPath: document.getElementById("custom-browser-path"),
  btnInstallChromium: document.getElementById("btn-install-chromium"),
  installProgressBox: document.getElementById("install-progress-box"),
  installLog: document.getElementById("install-log"),
  rangeParallelWebsites: document.getElementById("range-parallel-websites"),
  numParallelWebsites: document.getElementById("num-parallel-websites"),
  rangeTabsPerWebsite: document.getElementById("range-tabs-per-website"),
  numTabsPerWebsite: document.getElementById("num-tabs-per-website"),
  parallelTotalTitle: document.getElementById("parallel-total-title"),
  parallelTotalDesc: document.getElementById("parallel-total-desc"),
  chkBlockTrackers: document.getElementById("chk-block-trackers"),
  rangeRequestDelay: document.getElementById("range-request-delay"),
  valRequestDelay: document.getElementById("val-request-delay"),
  rangePageTimeout: document.getElementById("range-page-timeout"),
  valPageTimeout: document.getElementById("val-page-timeout"),
  chkSoundComplete: document.getElementById("chk-sound-complete"),
  chkAutoOpenExcel: document.getElementById("chk-auto-open-excel"),
  btnResetSettings: document.getElementById("btn-reset-settings"),
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
  miniCpuBar: document.getElementById("mini-cpu-bar"),
  miniRam: document.getElementById("mini-ram"),
  miniRamBar: document.getElementById("mini-ram-bar"),
  miniRamFree: document.getElementById("mini-ram-free"),
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
    renderSheet1();
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
    ? (inputMode === "manual" ? `${parseManualProducts().length} products` : "Excel ready")
    : "Products";

  elements.pillReadyWebsites.classList.toggle("ready", websiteCount > 0);
  elements.pillReadyWebsitesText.textContent = websiteCount > 0
    ? `${websiteCount} website${websiteCount === 1 ? "" : "s"}`
    : "Websites";

  elements.pillReadyFolder.classList.toggle("ready", hasFolder);
  elements.pillReadyFolderText.textContent = hasFolder ? "Image folder ready" : "Image folder";
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
    renderSheet1();
  });
});

// Collapsible Sidebar
const setSidebarCollapsed = (collapsed, persist = true) => {
  elements.sidebar.classList.toggle("collapsed", Boolean(collapsed));
  if (persist) {
    appSettings.sidebar_collapsed = Boolean(collapsed);
    callApi("save_settings", appSettings);
  }
};

elements.btnToggleSidebar.addEventListener("click", () => {
  setSidebarCollapsed(!elements.sidebar.classList.contains("collapsed"), true);
});

// Keyboard Shortcuts (Esc, Cmd/Ctrl+1..6, Cmd/Ctrl+K Quick Jump, Cmd/Ctrl+B Sidebar)
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
      openCmdK();
    } else if (e.key.toLowerCase() === "b") {
      e.preventDefault();
      setSidebarCollapsed(!elements.sidebar.classList.contains("collapsed"), true);
    }
  }
});

// Quick Jump Command Palette (Cmd/Ctrl+K)
let cmdkSelectedIdx = 0;
let cmdkFiltered = [];

const getCmdkItems = () => [
  { label: "Run", cat: "Workspace", run: () => switchTab("tab-run") },
  { label: "Results Table", cat: "Workspace", run: () => switchTab("tab-results") },
  { label: "Activity Logs", cat: "Workspace", run: () => switchTab("tab-logs") },
  { label: "Websites & Matching Rules", cat: "Settings", run: () => switchTab("tab-websites") },
  { label: "Browser, Speed & Limits", cat: "Settings", run: () => switchTab("tab-resources") },
  { label: "AI & Store Brand", cat: "Settings", run: () => switchTab("tab-gemini") },
  { label: "Switch to Manual Product List", cat: "Run", run: () => { switchTab("tab-run"); setInputMode("manual", true); elements.manualQuickInput.focus(); } },
  { label: "Switch to Excel File Mode", cat: "Run", run: () => { switchTab("tab-run"); setInputMode("file", true); } },
  { label: "Websites at Once & Tabs per Website", cat: "Speed", run: () => { switchTab("tab-resources"); elements.numParallelWebsites.focus(); } },
  { label: "Politeness Delay (Rate-Limit Pacing)", cat: "Speed", run: () => { switchTab("tab-resources"); elements.rangeRequestDelay.focus(); } },
  { label: "Page Timeout", cat: "Speed", run: () => { switchTab("tab-resources"); elements.rangePageTimeout.focus(); } },
  { label: "Block 3rd-Party Trackers & Ads", cat: "Speed", run: () => { switchTab("tab-resources"); elements.chkBlockTrackers.focus(); } },
  { label: "Max Images Per Product", cat: "Rules", run: () => { switchTab("tab-websites"); elements.rangeMaxImages.focus(); } },
  { label: "Custom Exclude Keywords", cat: "Rules", run: () => { switchTab("tab-websites"); elements.txtCustomExcludes.focus(); } },
  { label: "Gemini API Key", cat: "AI", run: () => { switchTab("tab-gemini"); elements.geminiApiKey.focus(); } },
  { label: "Open Output Excel (.xlsx)", cat: "Action", run: () => elements.btnOpenExcelTop.click() },
  { label: "Open Image Folder", cat: "Action", run: () => elements.btnOpenFolderTop.click() },
  { label: "Retry Not Found Products", cat: "Action", run: () => retryNotFoundProducts() },
  { label: "Toggle Dark / Light Appearance", cat: "Appearance", run: () => applyTheme(appSettings.theme === "light" ? "dark" : "light", true) },
  { label: "Toggle Sidebar (⌘B)", cat: "Appearance", run: () => setSidebarCollapsed(!elements.sidebar.classList.contains("collapsed"), true) },
  { label: "Reset All Settings to Defaults", cat: "Settings", run: () => elements.btnResetSettings.click() },
];

const renderCmdkList = () => {
  const q = (elements.cmdkInput.value || "").trim().toLowerCase();
  const all = getCmdkItems();
  cmdkFiltered = q
    ? all.filter((it) => `${it.label} ${it.cat}`.toLowerCase().includes(q))
    : all;
  if (cmdkSelectedIdx >= cmdkFiltered.length) cmdkSelectedIdx = 0;

  if (cmdkFiltered.length === 0) {
    elements.cmdkList.innerHTML = `<li class="cmdk-empty">No matching commands</li>`;
    return;
  }
  elements.cmdkList.innerHTML = cmdkFiltered
    .map((it, idx) => `<li class="cmdk-item${idx === cmdkSelectedIdx ? " active" : ""}" data-cmdk-idx="${idx}">
      <span>${escapeHtml(it.label)}</span>
      <span class="cmdk-item-cat">${escapeHtml(it.cat)}</span>
    </li>`)
    .join("");
};

const openCmdK = () => {
  if (!elements.cmdkDialog) return;
  elements.cmdkInput.value = "";
  cmdkSelectedIdx = 0;
  renderCmdkList();
  if (!elements.cmdkDialog.open) elements.cmdkDialog.showModal();
  elements.cmdkInput.focus();
};

const runCmdkIndex = (idx) => {
  const item = cmdkFiltered[idx];
  if (elements.cmdkDialog.open) elements.cmdkDialog.close();
  if (item) item.run();
};

if (elements.btnOpenCmdk) elements.btnOpenCmdk.addEventListener("click", openCmdK);
if (elements.cmdkInput) {
  elements.cmdkInput.addEventListener("input", () => {
    cmdkSelectedIdx = 0;
    renderCmdkList();
  });
  elements.cmdkInput.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (cmdkFiltered.length) {
        cmdkSelectedIdx = (cmdkSelectedIdx + 1) % cmdkFiltered.length;
        renderCmdkList();
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (cmdkFiltered.length) {
        cmdkSelectedIdx = (cmdkSelectedIdx - 1 + cmdkFiltered.length) % cmdkFiltered.length;
        renderCmdkList();
      }
    } else if (e.key === "Enter") {
      e.preventDefault();
      runCmdkIndex(cmdkSelectedIdx);
    }
  });
}
if (elements.cmdkList) {
  elements.cmdkList.addEventListener("click", (e) => {
    const li = e.target.closest(".cmdk-item");
    if (li) runCmdkIndex(parseInt(li.getAttribute("data-cmdk-idx"), 10));
  });
}
if (elements.cmdkDialog) {
  elements.cmdkDialog.addEventListener("click", (e) => {
    if (e.target === elements.cmdkDialog) elements.cmdkDialog.close();
  });
}

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

// Input Mode Switcher & Things 3-Style Manual Product Composer
const parseManualProducts = () => {
  const rawText = (elements.manualProductsInput.value || "").trim();
  if (!rawText) return [];
  return rawText
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean);
};

const setManualProductsList = (items, persist = true) => {
  elements.manualProductsInput.value = items.join("\n");
  updateManualCountBadge();
  renderManualQueue();
  if (persist) saveCurrentSettings();
};

const renderManualQueue = () => {
  if (!elements.manualProductList) return;
  const items = parseManualProducts();
  elements.manualQueueEmpty.classList.toggle("hidden", items.length > 0);
  elements.manualProductList.innerHTML = items
    .map((name, idx) => `<li class="composer-item" data-idx="${idx}">
      <span class="composer-item-idx">${idx + 1}</span>
      <span class="composer-item-name" title="Double-click to edit" ondblclick="editManualProduct(${idx})">${escapeHtml(name)}</span>
      <button class="composer-item-remove" type="button" title="Remove" onclick="removeManualProduct(${idx})">&times;</button>
    </li>`)
    .join("");
};

window.removeManualProduct = (idx) => {
  const items = parseManualProducts();
  if (idx < 0 || idx >= items.length) return;
  items.splice(idx, 1);
  setManualProductsList(items, true);
};

window.editManualProduct = (idx) => {
  const li = elements.manualProductList.querySelector(`li[data-idx="${idx}"]`);
  if (!li) return;
  const items = parseManualProducts();
  const cur = items[idx] || "";
  const span = li.querySelector(".composer-item-name");
  if (!span) return;
  const inp = document.createElement("input");
  inp.type = "text";
  inp.className = "composer-item-edit";
  inp.value = cur;
  span.replaceWith(inp);
  inp.focus();
  inp.select();

  const commit = () => {
    const next = inp.value.trim();
    if (next) items[idx] = next;
    else items.splice(idx, 1);
    setManualProductsList(items, true);
  };
  inp.addEventListener("blur", commit);
  inp.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); inp.blur(); }
    if (e.key === "Escape") { renderManualQueue(); }
  });
};

const addManualProducts = (rawText) => {
  const incoming = (rawText || "")
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (incoming.length === 0) return 0;

  const existing = parseManualProducts();
  const seen = new Set(existing.map((s) => s.toLowerCase()));
  let added = 0;
  for (const name of incoming) {
    if (!seen.has(name.toLowerCase())) {
      seen.add(name.toLowerCase());
      existing.push(name);
      added++;
    }
  }
  setManualProductsList(existing, true);
  if (added === 0) showToast("Already in list", "info");
  else if (incoming.length > 1) showToast(`Added ${added} product${added === 1 ? "" : "s"}`, "success");
  return added;
};

const updateManualCountBadge = () => {
  const count = parseManualProducts().length;
  elements.manualProductCount.textContent = `${count} product${count === 1 ? "" : "s"}`;
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
    ? "No input .xlsx file needed"
    : "Column A of your .xlsx file";
  updateManualCountBadge();
  renderManualQueue();
  if (persist) saveCurrentSettings();
};

elements.btnModeFile.addEventListener("click", () => setInputMode("file", true));
elements.btnModeManual.addEventListener("click", () => setInputMode("manual", true));

const appendQuickProduct = () => {
  const val = (elements.manualQuickInput.value || "").trim();
  if (!val) return;
  addManualProducts(val);
  elements.manualQuickInput.value = "";
};

elements.btnManualQuickAdd.addEventListener("click", appendQuickProduct);
elements.manualQuickInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    appendQuickProduct();
  }
});
elements.manualQuickInput.addEventListener("paste", (e) => {
  const pasted = (e.clipboardData || window.clipboardData)?.getData("text") || "";
  if (pasted.includes("\n") || pasted.includes(",")) {
    e.preventDefault();
    addManualProducts(pasted);
    elements.manualQuickInput.value = "";
  }
});

if (elements.btnPasteClipboard) {
  elements.btnPasteClipboard.addEventListener("click", async () => {
    try {
      const txt = await navigator.clipboard.readText();
      if (!txt.trim()) return showToast("Clipboard is empty", "warning");
      addManualProducts(txt);
    } catch {
      showToast("Press ⌘V inside the add bar to paste", "info");
      elements.manualQuickInput.focus();
    }
  });
}

if (elements.btnToggleBulkMode) {
  elements.btnToggleBulkMode.addEventListener("click", () => {
    isBulkEditMode = !isBulkEditMode;
    elements.manualQueueWrap.classList.toggle("hidden", isBulkEditMode);
    elements.manualBulkWrap.classList.toggle("hidden", !isBulkEditMode);
    elements.btnToggleBulkMode.textContent = isBulkEditMode ? "List View" : "Bulk Edit";
    if (!isBulkEditMode) {
      renderManualQueue();
      saveCurrentSettings();
    } else {
      elements.manualProductsInput.focus();
    }
  });
}

elements.manualProductsInput.addEventListener("input", () => {
  updateManualCountBadge();
  renderManualQueue();
});

elements.btnClearManual.addEventListener("click", () => {
  elements.manualQuickInput.value = "";
  setManualProductsList([], true);
  showToast("Product list cleared", "info");
});

// Progress, Live Pace/ETA & KPIs
const formatEta = (sec) => {
  if (!isFinite(sec) || sec <= 0) return "";
  if (sec < 60) return `${Math.ceil(sec)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s}s`;
};

const updateProgressUI = ({ current, total, product_name, stage }) => {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  let etaPart = "";
  if (runStartedAtMs > 0 && current > 0 && current < total) {
    const elapsedSec = (Date.now() - runStartedAtMs) / 1000;
    const perItem = elapsedSec / current;
    const remSec = perItem * (total - current);
    etaPart = ` · ~${perItem.toFixed(1)}s/item · ETA ${formatEta(remSec)}`;
  }
  elements.progressStatusLabel.textContent = `${current} / ${total} (${pct}%)${etaPart}`;
  elements.progressSiteLabel.textContent = product_name ? `${product_name} · ${stage}` : "Idle";
  elements.mainProgressBar.style.width = `${pct}%`;
  elements.headerMiniProgress.textContent = `${current} / ${total}`;
};

const retryNotFoundProducts = () => {
  const missed = Array.from(productsMap.values())
    .filter((r) => r.status === "Not Found")
    .map((r) => r.product_name);
  if (missed.length === 0) return showToast("No Not Found products to retry", "info");
  setManualProductsList(missed, true);
  setInputMode("manual", true);
  switchTab("tab-run");
  showToast(`Loaded ${missed.length} Not Found product${missed.length === 1 ? "" : "s"} into Manual List`, "success");
};
if (elements.btnRetryNotFound) elements.btnRetryNotFound.addEventListener("click", retryNotFoundProducts);

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
  if (elements.btnRetryNotFound) {
    elements.btnRetryNotFound.classList.toggle("hidden", notFound === 0 || isScrapingRunning);
  }
};

// Update Row in Table
const updateRowInTable = (record) => {
  productsMap.set(record.product_name, record);
  lastUpdatedProductName = record.product_name;
  updateKpiStrip();
  renderSheet1();
};

// Toggle Inline Variant Dropdown for a Product Row
window.toggleVariantDropdown = (productName, evt) => {
  if (evt) evt.stopPropagation();
  if (expandedProducts.has(productName)) {
    expandedProducts.delete(productName);
  } else {
    expandedProducts.add(productName);
  }
  renderSheet1();
};

// Render Products Table (with inline expandable Variant Dropdowns)
const renderSheet1 = () => {
  const filter = (elements.tableSearch.value || "").toLowerCase();
  const records = Array.from(productsMap.values()).filter((r) => {
    const matchesSearch = r.product_name.toLowerCase().includes(filter);
    const matchesStatus = statusFilter === "all" || r.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  elements.tableRowCount.textContent = `${records.length}`;

  if (records.length === 0) {
    elements.tbodySheet1.innerHTML = `<tr>
      <td colspan="9" class="empty-state-cell">
        <div class="empty-state-box">
          <div class="empty-state-title">${productsMap.size === 0 ? "No products yet" : "No matching products"}</div>
          <div class="empty-state-sub">${productsMap.size === 0 ? "Add products in Run, configure a store in Websites, and press Start." : "Try clearing your search or status filter."}</div>
        </div>
      </td>
    </tr>`;
    return;
  }

  const externalSvg = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;
  const folderSvg = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;
  const chevronSvg = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>`;

  let html = "";
  for (const r of records) {
    const statusCls = (r.status || "pending").toLowerCase().replace(/\s+/g, "-");
    const regPrice = r.default_price ? r.default_price.regular_display : "-";
    const discPrice = r.default_price ? r.default_price.discounted_display || "-" : "-";
    const safeNameArg = escapeHtml(JSON.stringify(r.product_name));

    // Build flat variant rows from attribute_options
    const attrOpts = r.attribute_options || {};
    const flatVariants = [];
    for (const [cat, entries] of Object.entries(attrOpts)) {
      if (Array.isArray(entries)) {
        for (const e of entries) {
          flatVariants.push({
            category: cat,
            label: e.label,
            reg: e.prices ? e.prices.regular_display : "not found",
            disc: e.prices ? (e.prices.discounted_display || "-") : "-",
          });
        }
      }
    }

    const isExpanded = expandedProducts.has(r.product_name);
    const catNames = Object.keys(attrOpts);
    const variantBtnLabel = catNames.length === 1
      ? `${catNames[0].charAt(0).toUpperCase() + catNames[0].slice(1)} (${flatVariants.length})`
      : `${flatVariants.length} variants`;

    const variantCell = flatVariants.length > 0
      ? `<button class="variant-dropdown-btn${isExpanded ? " open" : ""}" type="button" onclick="toggleVariantDropdown(${safeNameArg}, event)">${chevronSvg}<span>${escapeHtml(variantBtnLabel)}</span></button>`
      : `<span class="desc-snippet">-</span>`;

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
      <td>${variantCell}</td>
      <td>${folderCell}</td>
      <td>${linkCell}</td>
      <td><span class="specs-snippet" title="${escapeHtml(r.specifications || "")}">${escapeHtml(r.specifications || "-")}</span></td>
      <td>${descCell}</td>
    </tr>`;

    // Inline Expanded Variant Sub-Row
    if (isExpanded && flatVariants.length > 0) {
      const subRows = flatVariants.map((v) => `<tr>
        <td><span class="variant-cat-pill">${escapeHtml(v.category)}</span></td>
        <td><strong>${escapeHtml(v.label)}</strong></td>
        <td><span class="price-val">${escapeHtml(v.reg)}</span></td>
        <td><span class="price-val ${v.disc !== "-" ? "discount" : ""}">${escapeHtml(v.disc)}</span></td>
      </tr>`).join("");

      html += `<tr class="variant-expand-row">
        <td colspan="9">
          <div class="variant-expand-panel">
            <table class="variant-subtable">
              <thead>
                <tr>
                  <th>Attribute</th>
                  <th>Variant Option</th>
                  <th>Regular Price</th>
                  <th>Discounted Price</th>
                </tr>
              </thead>
              <tbody>${subRows}</tbody>
            </table>
          </div>
        </td>
      </tr>`;
    }
  }
  elements.tbodySheet1.innerHTML = html;
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
    if (!isScrapingRunning) runStartedAtMs = Date.now();
    isScrapingRunning = true;
    isScrapingPaused = false;
    elements.btnStart.disabled = true;
    elements.btnPause.disabled = false;
    elements.btnPause.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg><span>Pause</span>`;
    elements.btnStop.disabled = false;
    elements.headerLiveControls.classList.remove("hidden");
    elements.btnHeaderPause.textContent = "Pause";
    elements.statusDescription.textContent = "Running in visible Incognito browser";
  } else if (status === "Paused") {
    isScrapingPaused = true;
    elements.btnPause.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 4 20 12 6 20 6 4"/></svg><span>Resume</span>`;
    elements.headerLiveControls.classList.remove("hidden");
    elements.btnHeaderPause.textContent = "Resume";
    elements.statusDescription.textContent = "Paused";
  } else {
    isScrapingRunning = false;
    isScrapingPaused = false;
    runStartedAtMs = 0;
    elements.btnStart.disabled = false;
    elements.btnPause.disabled = true;
    elements.btnStop.disabled = true;
    elements.headerLiveControls.classList.add("hidden");
    elements.captchaBanner.classList.add("hidden");
    elements.statusDescription.textContent = status === "Finished" ? "Done — all rows saved" : "Ready";
    updateKpiStrip();
    if (status === "Finished") {
      if (appSettings.sound_on_complete !== false) playAlertChime();
      showToast("Done — all rows saved to Excel", "success");
    }
  }
};

elements.btnHeaderPause.addEventListener("click", () => elements.btnPause.click());
elements.btnHeaderStop.addEventListener("click", () => elements.btnStop.click());

// Website List Rendering
const renderWebsites = () => {
  const websites = appSettings.websites || [];
  elements.navWebsitesCount.textContent = String(websites.length);
  updateParallelSplitHint();
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

const updateParallelSplitHint = () => {
  if (!elements.parallelTotalTitle || !elements.parallelTotalDesc) return;
  const w = Math.max(1, parseInt(elements.numParallelWebsites.value, 10) || 1);
  const t = Math.max(1, parseInt(elements.numTabsPerWebsite.value, 10) || 1);
  const siteCount = (appSettings.websites || []).length;
  const effectiveSites = siteCount > 0 ? Math.min(w, siteCount) : w;
  const totalTabs = effectiveSites * t;

  elements.parallelTotalTitle.textContent = `Opens ${totalTabs} tab${totalTabs === 1 ? "" : "s"} total`;
  let desc = `${t} product${t === 1 ? "" : "s"} at once on ${effectiveSites === 1 ? "1 website at a time" : `each of ${effectiveSites} websites`}.`;
  if (siteCount > 0 && w > siteCount) {
    desc += ` (You have ${siteCount} website${siteCount === 1 ? "" : "s"} added.)`;
  }
  elements.parallelTotalDesc.textContent = desc;
};

const setParallelWebsites = (val, persist = true) => {
  const clean = Math.max(1, parseInt(val, 10) || 1);
  elements.numParallelWebsites.value = String(clean);
  elements.rangeParallelWebsites.value = String(Math.min(10, clean));
  appSettings.parallel_websites = clean;
  updateParallelSplitHint();
  if (persist) saveCurrentSettings();
};

const setTabsPerWebsite = (val, persist = true) => {
  const clean = Math.max(1, parseInt(val, 10) || 1);
  elements.numTabsPerWebsite.value = String(clean);
  elements.rangeTabsPerWebsite.value = String(Math.min(10, clean));
  appSettings.tabs_per_website = clean;
  updateParallelSplitHint();
  if (persist) saveCurrentSettings();
};

elements.rangeParallelWebsites.addEventListener("input", (e) => setParallelWebsites(e.target.value, true));
elements.numParallelWebsites.addEventListener("change", (e) => setParallelWebsites(e.target.value, true));
elements.rangeTabsPerWebsite.addEventListener("input", (e) => setTabsPerWebsite(e.target.value, true));
elements.numTabsPerWebsite.addEventListener("change", (e) => setTabsPerWebsite(e.target.value, true));

elements.rangeMaxImages.addEventListener("input", (e) => {
  const v = parseInt(e.target.value, 10);
  elements.valMaxImages.textContent = v === 0 ? "Unlimited" : `${v} max`;
  appSettings.max_images_per_product = v;
  saveCurrentSettings();
});

elements.rangeRequestDelay.addEventListener("input", (e) => {
  const v = parseFloat(e.target.value);
  elements.valRequestDelay.textContent = `${v.toFixed(1)}s`;
  appSettings.request_delay_sec = v;
  saveCurrentSettings();
});

elements.rangePageTimeout.addEventListener("input", (e) => {
  const v = parseInt(e.target.value, 10);
  elements.valPageTimeout.textContent = `${v}s`;
  appSettings.page_timeout_sec = v;
  saveCurrentSettings();
});

elements.btnResetSettings.addEventListener("click", async () => {
  const ok = await showConfirmDialog(
    "Reset All Settings?",
    "Restores matching rules, limits, browser preferences, and store profile to factory defaults."
  );
  if (!ok) return;
  const fresh = await callApi("reset_settings");
  if (fresh) {
    loadSettingsIntoUI(fresh);
    showToast("Settings reset to defaults", "info");
  }
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
  elements.sidebarBrandSubtitle.textContent = name;
};
elements.brandName.addEventListener("input", syncSidebarSubtitle);

// Table search filter
elements.tableSearch.addEventListener("input", () => {
  renderSheet1();
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
  appSettings.parallel_websites = Math.max(1, parseInt(elements.numParallelWebsites.value, 10) || 1);
  appSettings.tabs_per_website = Math.max(1, parseInt(elements.numTabsPerWebsite.value, 10) || 3);
  appSettings.block_trackers = elements.chkBlockTrackers.checked;
  appSettings.request_delay_sec = parseFloat(elements.rangeRequestDelay.value);
  appSettings.page_timeout_sec = parseInt(elements.rangePageTimeout.value, 10);
  appSettings.sound_on_complete = elements.chkSoundComplete.checked;
  appSettings.auto_open_excel = elements.chkAutoOpenExcel.checked;
  appSettings.search_missing_official_unofficial_pair = elements.chkMissingOfficialPair.checked;
  appSettings.skip_preowned_devices = elements.chkSkipPreowned.checked;
  appSettings.skip_accessories = elements.chkSkipAccessories.checked;
  appSettings.strict_model_matching = elements.chkStrictModel.checked;
  appSettings.enable_fallback_sku_search = elements.chkFallbackSku.checked;
  appSettings.scrape_variants = elements.chkScrapeVariants.checked;
  appSettings.download_images = elements.chkDownloadImages.checked;
  appSettings.max_images_per_product = parseInt(elements.rangeMaxImages.value, 10);
  appSettings.custom_exclude_keywords = elements.txtCustomExcludes.value;
  appSettings.sidebar_collapsed = elements.sidebar.classList.contains("collapsed");
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
  elements.chkBlockTrackers,
  elements.chkSoundComplete,
  elements.chkAutoOpenExcel,
  elements.chkMissingOfficialPair,
  elements.chkSkipPreowned,
  elements.chkSkipAccessories,
  elements.chkStrictModel,
  elements.chkFallbackSku,
  elements.chkScrapeVariants,
  elements.chkDownloadImages,
  elements.txtCustomExcludes,
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
  elements.chkSkipAccessories.checked = s.skip_accessories ?? true;
  elements.chkStrictModel.checked = s.strict_model_matching ?? true;
  elements.chkFallbackSku.checked = s.enable_fallback_sku_search ?? true;
  elements.chkScrapeVariants.checked = s.scrape_variants ?? true;
  elements.chkDownloadImages.checked = s.download_images ?? true;
  const maxImgs = Number(s.max_images_per_product ?? 0);
  elements.rangeMaxImages.value = maxImgs;
  elements.valMaxImages.textContent = maxImgs === 0 ? "Unlimited" : `${maxImgs} max`;
  elements.txtCustomExcludes.value = s.custom_exclude_keywords || "";

  setParallelWebsites(s.parallel_websites ?? 1, false);
  setTabsPerWebsite(s.tabs_per_website ?? 3, false);
  elements.chkBlockTrackers.checked = s.block_trackers ?? true;
  const reqDelay = Number(s.request_delay_sec ?? 0.5);
  elements.rangeRequestDelay.value = reqDelay;
  elements.valRequestDelay.textContent = `${reqDelay.toFixed(1)}s`;
  const pageTo = Number(s.page_timeout_sec ?? 25);
  elements.rangePageTimeout.value = pageTo;
  elements.valPageTimeout.textContent = `${pageTo}s`;
  elements.chkSoundComplete.checked = s.sound_on_complete ?? true;
  elements.chkAutoOpenExcel.checked = s.auto_open_excel ?? false;
  setSidebarCollapsed(Boolean(s.sidebar_collapsed), false);

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

// Resource Poller (updates always-visible sidebar CPU/RAM widget + full gauges)
const pollResources = async () => {
  const res = await callApi("get_live_resources");
  if (!res) return;

  const cpuPct = Math.min(res.cpu_percent, 100);
  const ramDisplay = res.memory_mb >= 1024
    ? `${(res.memory_mb / 1024).toFixed(1)} GB`
    : `${Math.round(res.memory_mb)} MB`;

  elements.miniCpu.textContent = `${res.cpu_percent}%`;
  if (elements.miniCpuBar) elements.miniCpuBar.style.width = `${cpuPct}%`;
  elements.miniRam.textContent = ramDisplay;
  elements.miniRamBar.style.width = `${res.memory_percent_of_cap}%`;
  if (elements.miniRamFree && res.system_ram_free_gb > 0) {
    elements.miniRamFree.textContent = `${res.system_ram_free_gb} GB free of ${res.system_ram_total_gb} GB`;
  }

  elements.gaugeCpuText.textContent = `${res.cpu_percent}% (Cap: ${res.max_cpu_percent}%)`;
  elements.gaugeCpuBar.style.width = `${cpuPct}%`;

  elements.gaugeRamText.textContent = `${res.memory_mb} MB / ${res.max_ram_gb} GB`;
  elements.gaugeRamBar.style.width = `${res.memory_percent_of_cap}%`;

  const cpuColor = res.cpu_percent > res.max_cpu_percent ? "var(--warning)" : "var(--accent-primary)";
  const ramColor = res.memory_percent_of_cap > 85 ? "var(--danger)" : "var(--accent-primary)";
  if (elements.miniCpuBar) elements.miniCpuBar.style.background = cpuColor;
  elements.miniRamBar.style.background = ramColor;
  elements.gaugeRamBar.style.background = ramColor;
  elements.gaugeCpuBar.style.background = cpuColor;
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
