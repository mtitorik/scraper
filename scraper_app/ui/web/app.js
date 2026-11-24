// State management
let appSettings = {};
let activeSheet = "sheet1";
let inputMode = "file";
let productsMap = new Map(); // product_name -> summary dict
let variantsList = [];
let isScrapingRunning = false;
let isScrapingPaused = false;

// Audio chime for CAPTCHA and completion
const playAlertChime = () => {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sine";
    osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
    osc.frequency.setValueAtTime(880, ctx.currentTime + 0.15); // A5
    gain.gain.setValueAtTime(0.2, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    osc.start();
    osc.stop(ctx.currentTime + 0.5);
  } catch (e) {
    // AudioContext might be blocked until user gesture
  }
};

// DOM Elements
const elements = {
  statusBadge: document.getElementById("status-badge"),
  statusDescription: document.getElementById("status-description"),
  captchaBanner: document.getElementById("captcha-banner"),
  captchaSiteText: document.getElementById("captcha-site-text"),
  btnCaptchaDone: document.getElementById("btn-captcha-done"),

  // Pickers & inputs
  btnModeFile: document.getElementById("btn-mode-file"),
  btnModeManual: document.getElementById("btn-mode-manual"),
  fileInputGroup: document.getElementById("file-input-group"),
  manualInputGroup: document.getElementById("manual-input-group"),
  manualProductsInput: document.getElementById("manual-products-input"),
  inputXlsxPath: document.getElementById("input-xlsx-path"),
  outputXlsxPath: document.getElementById("output-xlsx-path"),
  rootFolderPath: document.getElementById("root-folder-path"),
  resumeXlsxPath: document.getElementById("resume-xlsx-path"),
  btnBrowseInput: document.getElementById("btn-browse-input"),
  btnBrowseOutput: document.getElementById("btn-browse-output"),
  btnBrowseFolder: document.getElementById("btn-browse-folder"),
  btnBrowseResume: document.getElementById("btn-browse-resume"),
  btnClearResume: document.getElementById("btn-clear-resume"),

  // Controls
  btnStart: document.getElementById("btn-start"),
  btnPause: document.getElementById("btn-pause"),
  btnStop: document.getElementById("btn-stop"),
  btnOpenExcelTop: document.getElementById("btn-open-excel-top"),
  btnOpenFolderTop: document.getElementById("btn-open-folder-top"),

  // Progress
  progressStatusLabel: document.getElementById("progress-status-label"),
  progressSiteLabel: document.getElementById("progress-site-label"),
  mainProgressBar: document.getElementById("main-progress-bar"),

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
  selBrowserMode: document.getElementById("sel-browser-mode"),
  customBrowserGroup: document.getElementById("custom-browser-group"),
  customBrowserPath: document.getElementById("custom-browser-path"),
  btnInstallChromium: document.getElementById("btn-install-chromium"),
  installProgressBox: document.getElementById("install-progress-box"),
  installLog: document.getElementById("install-log"),
  rangeCpuCores: document.getElementById("range-cpu-cores"),
  rangeCpuPercent: document.getElementById("range-cpu-percent"),
  rangeRamGb: document.getElementById("range-ram-gb"),
  valCpuCores: document.getElementById("val-cpu-cores"),
  valCpuPercent: document.getElementById("val-cpu-percent"),
  valRamGb: document.getElementById("val-ram-gb"),

  // Gemini & Brand
  chkEnableGemini: document.getElementById("chk-enable-gemini"),
  geminiApiKey: document.getElementById("gemini-api-key"),
  btnToggleKeyVisibility: document.getElementById("btn-toggle-key-visibility"),
  selGeminiModel: document.getElementById("sel-gemini-model"),
  selStructurePreset: document.getElementById("sel-structure-preset"),
  customStructureGroup: document.getElementById("custom-structure-group"),
  txtCustomStructure: document.getElementById("txt-custom-structure"),
  brandName: document.getElementById("brand-name"),
  brandUrl: document.getElementById("brand-url"),
  storeAddress: document.getElementById("store-address"),
  sellingPoints: document.getElementById("selling-points"),
  customRules: document.getElementById("custom-rules"),

  // Log & Mini Meter
  logTerminal: document.getElementById("log-terminal"),
  btnCopyLog: document.getElementById("btn-copy-log"),
  btnClearLog: document.getElementById("btn-clear-log"),
  miniCpu: document.getElementById("mini-cpu"),
  miniRam: document.getElementById("mini-ram"),
  miniRamBar: document.getElementById("mini-ram-bar"),
  btnThemeToggle: document.getElementById("btn-theme-toggle"),
  themeIcon: document.getElementById("theme-icon"),
  themeLabel: document.getElementById("theme-label"),
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

// Log entry helper
const addLogEntry = (msg, type = "info") => {
  const div = document.createElement("div");
  div.className = `log-entry ${type}`;
  const now = new Date().toLocaleTimeString();
  div.innerText = `[${now}] ${msg}`;
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
      elements.captchaSiteText.innerText = `A verification challenge was detected on ${payload}. Please complete it in the browser!`;
      playAlertChime();
      addLogEntry(`⚠️ CAPTCHA Challenge detected on ${payload}. Paused for user verification.`, "warning");
      break;

    case "status_change":
      updateAppStatus(payload);
      break;

    case "chromium_install_progress":
      elements.installProgressBox.classList.remove("hidden");
      elements.installLog.innerText += payload + "\n";
      elements.installProgressBox.scrollTop = elements.installProgressBox.scrollHeight;
      break;

    case "chromium_install_done":
      addLogEntry(payload.success ? "Chromium installed successfully!" : "Chromium installation failed.");
      break;
  }
};

// Navigation Tab Switching
document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    const targetId = btn.getAttribute("data-tab");
    document.getElementById(targetId).classList.add("active");
  });
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

// Theme Toggle
elements.btnThemeToggle.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  elements.themeIcon.innerText = next === "dark" ? "🌙" : "☀️";
  elements.themeLabel.innerText = next === "dark" ? "Dark Theme" : "Light Theme";
  appSettings.theme = next;
  callApi("save_settings", appSettings);
});

// Update Progress UI
const updateProgressUI = ({ current, total, product_name, site, stage }) => {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  elements.progressStatusLabel.innerText = `${current} / ${total} Products (${pct}%)`;
  elements.progressSiteLabel.innerText = product_name ? `${product_name} • ${stage}` : "-";
  elements.mainProgressBar.style.width = `${pct}%`;
};

// Update Row in Table
const updateRowInTable = (record) => {
  productsMap.set(record.product_name, record);
  if (activeSheet === "sheet1") {
    renderSheet1();
  }
};

// Render Sheet 1 (Products)
const renderSheet1 = () => {
  const filter = (elements.tableSearch.value || "").toLowerCase();
  const records = Array.from(productsMap.values()).filter((r) =>
    r.product_name.toLowerCase().includes(filter)
  );

  elements.tableRowCount.innerText = `${records.length} products`;

  if (records.length === 0) {
    elements.tbodySheet1.innerHTML =
      '<tr><td colspan="8" class="empty-state">No matching products found.</td></tr>';
    return;
  }

  let html = "";
  for (const r of records) {
    const statusCls = (r.status || "pending").toLowerCase().replace(" ", "-");
    const regPrice = r.default_price ? r.default_price.regular_display : "-";
    const discPrice = r.default_price ? r.default_price.discounted_display || "-" : "-";
    const links = (r.page_links || []).join(", ") || "-";

    const folderCell = r.image_folder
      ? `<button class="folder-link-btn" onclick="openPath('${r.image_folder.replace(/\\/g, "/")}')">Open Folder</button>`
      : "-";

    html += `<tr>
      <td><strong>${escapeHtml(r.product_name)}</strong></td>
      <td><span class="status-cell ${statusCls}">${escapeHtml(r.status || "Pending")}</span></td>
      <td>${escapeHtml(regPrice)}</td>
      <td>${escapeHtml(discPrice)}</td>
      <td>${folderCell}</td>
      <td title="${escapeHtml(links)}" style="max-width: 180px; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(links)}</td>
      <td title="${escapeHtml(r.specifications || '')}" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(r.specifications || '-')}</td>
      <td>${r.description_html_len ? `${r.description_html_len} chars` : "-"}</td>
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
    (v["Colour"] || "").toLowerCase().includes(filter)
  );

  elements.tableRowCount.innerText = `${filtered.length} variant rows`;

  if (filtered.length === 0) {
    elements.tbodySheet2.innerHTML =
      '<tr><td colspan="10" class="empty-state">No variant combinations recorded yet.</td></tr>';
    return;
  }

  let html = "";
  for (const v of filtered) {
    html += `<tr>
      <td><strong>${escapeHtml(v["Product name"] || "")}</strong></td>
      <td>${escapeHtml(v["Source Website"] || "-")}</td>
      <td>${escapeHtml(v["Official/Unofficial"] || "-")}</td>
      <td>${escapeHtml(v["Region"] || "-")}</td>
      <td>${escapeHtml(v["Storage"] || "-")}</td>
      <td>${escapeHtml(v["Colour"] || "-")}</td>
      <td>${escapeHtml(v["Regular Price"] || "-")}</td>
      <td>${escapeHtml(v["Discounted Price"] || "-")}</td>
      <td>${escapeHtml(v["Stock Status"] || "-")}</td>
      <td title="${escapeHtml(v["Page Link"] || '')}" style="max-width: 150px; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(v["Page Link"] || '-')}</td>
    </tr>`;
  }
  elements.tbodySheet2.innerHTML = html;
};

const escapeHtml = (str) => {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
};

window.openPath = (p) => {
  callApi("open_local_path", p);
};

// App Status Updates
const updateAppStatus = (status) => {
  elements.statusBadge.className = `status-pill ${status.toLowerCase()}`;
  elements.statusBadge.innerText = status;

  if (status === "Running") {
    isScrapingRunning = true;
    isScrapingPaused = false;
    elements.btnStart.disabled = true;
    elements.btnPause.disabled = false;
    elements.btnPause.innerText = "⏸ Pause";
    elements.btnStop.disabled = false;
    elements.statusDescription.innerText = "Scraping active in visible Incognito browser...";
  } else if (status === "Paused") {
    isScrapingPaused = true;
    elements.btnPause.innerText = "▶ Resume";
    elements.statusDescription.innerText = "Paused cleanly at checkpoint.";
  } else if (status === "Stopping" || status === "Finished" || status === "Idle" || status === "Error") {
    isScrapingRunning = false;
    isScrapingPaused = false;
    elements.btnStart.disabled = false;
    elements.btnPause.disabled = true;
    elements.btnStop.disabled = true;
    elements.captchaBanner.classList.add("hidden");
    elements.statusDescription.innerText = status === "Finished" ? "Scraping completed! All data saved." : "Ready to scrape";
    if (status === "Finished") playAlertChime();
  }
};

// Website List Rendering
const renderWebsites = () => {
  const websites = appSettings.websites || [];
  elements.websiteList.innerHTML = "";

  if (websites.length === 0) {
    elements.websiteList.innerHTML = '<li class="empty-state">No websites added yet. Add URLs above to set the priority order!</li>';
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
        <button class="btn btn-secondary btn-sm" onclick="moveWebsite(${idx}, -1)" ${idx === 0 ? "disabled" : ""}>↑</button>
        <button class="btn btn-secondary btn-sm" onclick="moveWebsite(${idx}, 1)" ${idx === websites.length - 1 ? "disabled" : ""}>↓</button>
        <button class="btn btn-danger btn-sm" onclick="removeWebsite(${idx})">✕</button>
      </div>
    `;
    elements.websiteList.appendChild(li);
  });
};

window.moveWebsite = (idx, dir) => {
  const list = appSettings.websites;
  const target = idx + dir;
  if (target < 0 || target >= list.length) return;
  const temp = list[idx];
  list[idx] = list[target];
  list[target] = temp;
  saveCurrentSettings();
  renderWebsites();
};

window.removeWebsite = (idx) => {
  appSettings.websites.splice(idx, 1);
  saveCurrentSettings();
  renderWebsites();
};

elements.btnAddWebsite.addEventListener("click", () => {
  const url = (elements.newWebsiteUrl.value || "").trim();
  if (!url) return;
  if (!appSettings.websites) appSettings.websites = [];
  if (!appSettings.websites.includes(url)) {
    appSettings.websites.push(url);
    saveCurrentSettings();
    renderWebsites();
  }
  elements.newWebsiteUrl.value = "";
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
  if (path) {
    elements.resumeXlsxPath.value = path;
  }
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
  if (path) callApi("open_local_path", path);
});

elements.btnOpenFolderTop.addEventListener("click", () => {
  const folder = elements.rootFolderPath.value;
  if (folder) callApi("open_local_path", folder);
});

// Mode Switcher (File vs Manual)
elements.btnModeFile.addEventListener("click", () => {
  inputMode = "file";
  elements.btnModeFile.classList.add("active");
  elements.btnModeManual.classList.remove("active");
  elements.fileInputGroup.classList.remove("hidden");
  elements.manualInputGroup.classList.add("hidden");
  saveCurrentSettings();
});

elements.btnModeManual.addEventListener("click", () => {
  inputMode = "manual";
  elements.btnModeManual.classList.add("active");
  elements.btnModeFile.classList.remove("active");
  elements.manualInputGroup.classList.remove("hidden");
  elements.fileInputGroup.classList.add("hidden");
  saveCurrentSettings();
});

// Playback Controls
elements.btnStart.addEventListener("click", async () => {
  const inputPath = elements.inputXlsxPath.value;
  let outputPath = elements.outputXlsxPath.value;
  const rootFolder = elements.rootFolderPath.value;
  const resumePath = elements.resumeXlsxPath.value;

  let manualProducts = null;

  if (inputMode === "manual") {
    const rawText = (elements.manualProductsInput.value || "").trim();
    manualProducts = rawText
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);

    if (manualProducts.length === 0) {
      alert("Please enter at least one product name to search!");
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
      alert("Please select an Input .xlsx file (or switch to Manual Entry, or pick a Resume file)!");
      return;
    }
    if (!outputPath) {
      alert("Please choose a destination for the New Output .xlsx file!");
      return;
    }
  }

  if (!rootFolder) {
    alert("Please select a Root Image Folder!");
    return;
  }

  saveCurrentSettings();
  productsMap.clear();
  renderSheet1();
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
  if (isScrapingPaused) {
    callApi("resume_scraping");
  } else {
    callApi("pause_scraping");
  }
});

elements.btnStop.addEventListener("click", () => {
  if (confirm("Are you sure you want to stop scraping? All completed rows are preserved.")) {
    callApi("stop_scraping");
  }
});

elements.btnCaptchaDone.addEventListener("click", () => {
  elements.captchaBanner.classList.add("hidden");
  callApi("verify_captcha_done");
});

// Sliders and Inputs Auto-Save
elements.rangeCpuCores.addEventListener("input", (e) => {
  elements.valCpuCores.innerText = `${e.target.value} cores`;
  appSettings.max_cpu_cores = parseInt(e.target.value);
  saveCurrentSettings();
});

elements.rangeCpuPercent.addEventListener("input", (e) => {
  elements.valCpuPercent.innerText = `${e.target.value}%`;
  appSettings.max_cpu_percent = parseInt(e.target.value);
  saveCurrentSettings();
});

elements.rangeRamGb.addEventListener("input", (e) => {
  elements.valRamGb.innerText = `${parseFloat(e.target.value).toFixed(1)} GB`;
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
  elements.installLog.innerText = "Initiating bundled Chromium installation...\n";
  callApi("install_bundled_chromium");
});

elements.selStructurePreset.addEventListener("change", (e) => {
  appSettings.gemini_structure_preset = e.target.value;
  elements.customStructureGroup.classList.toggle("hidden", e.target.value !== "custom");
  saveCurrentSettings();
});

elements.btnToggleKeyVisibility.addEventListener("click", () => {
  const isPass = elements.geminiApiKey.type === "password";
  elements.geminiApiKey.type = isPass ? "text" : "password";
  elements.btnToggleKeyVisibility.innerText = isPass ? "Hide" : "Show";
});

// Table search filter
elements.tableSearch.addEventListener("input", () => {
  if (activeSheet === "sheet1") renderSheet1();
  else renderSheet2();
});

// Logs copy & clear
elements.btnCopyLog.addEventListener("click", () => {
  navigator.clipboard.writeText(elements.logTerminal.innerText);
  alert("Log copied to clipboard!");
});

elements.btnClearLog.addEventListener("click", () => {
  elements.logTerminal.innerHTML = '<div class="log-entry info">[System] Log cleared.</div>';
});

// Save current form state to settings
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
};

// Auto-save listeners on text inputs
[
  elements.manualProductsInput,
  elements.customBrowserPath,
  elements.chkMissingOfficialPair,
  elements.chkSkipPreowned,
  elements.chkEnableGemini,
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

// Load settings into UI
const loadSettingsIntoUI = (s) => {
  appSettings = s || {};

  inputMode = s.input_mode || "file";
  if (inputMode === "manual") {
    elements.btnModeManual.classList.add("active");
    elements.btnModeFile.classList.remove("active");
    elements.manualInputGroup.classList.remove("hidden");
    elements.fileInputGroup.classList.add("hidden");
  } else {
    elements.btnModeFile.classList.add("active");
    elements.btnModeManual.classList.remove("active");
    elements.fileInputGroup.classList.remove("hidden");
    elements.manualInputGroup.classList.add("hidden");
  }
  elements.manualProductsInput.value = s.manual_products_text || "";

  elements.inputXlsxPath.value = s.last_input_xlsx || "";
  elements.outputXlsxPath.value = s.last_output_xlsx || "";
  elements.rootFolderPath.value = s.root_image_folder || "";

  elements.selBrowserMode.value = s.browser_mode || "auto";
  elements.customBrowserPath.value = s.custom_browser_path || "";
  elements.customBrowserGroup.classList.toggle("hidden", s.browser_mode !== "custom");

  elements.rangeCpuCores.value = s.max_cpu_cores || 2;
  elements.valCpuCores.innerText = `${elements.rangeCpuCores.value} cores`;

  elements.rangeCpuPercent.value = s.max_cpu_percent || 40;
  elements.valCpuPercent.innerText = `${elements.rangeCpuPercent.value}%`;

  elements.rangeRamGb.value = s.max_ram_gb || 2.0;
  elements.valRamGb.innerText = `${parseFloat(elements.rangeRamGb.value).toFixed(1)} GB`;

  elements.chkMissingOfficialPair.checked = s.search_missing_official_unofficial_pair ?? true;
  elements.chkSkipPreowned.checked = s.skip_preowned_devices ?? true;

  elements.chkEnableGemini.checked = s.enable_gemini ?? true;
  elements.geminiApiKey.value = s.gemini_api_key || "";
  elements.selGeminiModel.value = s.gemini_model || "gemini-2.5-flash";
  elements.selStructurePreset.value = s.gemini_structure_preset || "standard";
  elements.txtCustomStructure.value = s.gemini_custom_structure || "";
  elements.customStructureGroup.classList.toggle("hidden", s.gemini_structure_preset !== "custom");

  elements.brandName.value = s.brand_name || "";
  elements.brandUrl.value = s.brand_url || "";
  elements.storeAddress.value = s.store_address || "";
  elements.sellingPoints.value = s.selling_points || "";
  elements.customRules.value = s.custom_rules || "";

  if (s.theme) {
    document.documentElement.setAttribute("data-theme", s.theme);
    elements.themeIcon.innerText = s.theme === "dark" ? "🌙" : "☀️";
    elements.themeLabel.innerText = s.theme === "dark" ? "Dark Theme" : "Light Theme";
  }

  renderWebsites();
};

// Resource Poller
const pollResources = async () => {
  const res = await callApi("get_live_resources");
  if (res) {
    elements.miniCpu.innerText = `${res.cpu_percent}%`;
    elements.miniRam.innerText = `${res.memory_mb} MB`;
    elements.miniRamBar.style.width = `${res.memory_percent_of_cap}%`;

    if (res.memory_percent_of_cap > 85) {
      elements.miniRamBar.style.background = "var(--accent-danger)";
    } else if (res.cpu_percent > res.max_cpu_percent) {
      elements.miniRamBar.style.background = "var(--accent-warning)";
    } else {
      elements.miniRamBar.style.background = "var(--accent-primary)";
    }
  }
};

// Initialization
window.addEventListener("pywebviewready", async () => {
  const settings = await callApi("get_settings");
  if (settings) {
    loadSettingsIntoUI(settings);
  }
  setInterval(pollResources, 1500);
});
