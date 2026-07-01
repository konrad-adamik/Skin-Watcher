(function () {
  "use strict";

  const C = globalThis.SkinWatcherCommon;
  const Catalog = globalThis.SkinWatcherCatalog;
  const DEFAULT_SETTINGS = {
    sites: ["pirateswap"],
    discordWebhookUrl: "",
    checkIntervalSeconds: 300,
    skins: []
  };

  let settings = structuredClone(DEFAULT_SETTINGS);
  let runtime = { watching: false, logs: [], siteStatuses: {} };
  let editingIndex = null;
  let settingsSaveTimer = null;
  let startInProgress = false;

  const $ = (id) => document.getElementById(id);
  const controls = [
    "sitePirateswap", "siteSkinsmonkey", "webhook", "interval",
    "skinType", "skinItem", "skinName", "stattrak",
    "floatMin", "floatMax", "addSkin", "cancelEdit"
  ];

  function send(message) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(message, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else if (!response?.ok) {
          reject(new Error(response?.error || "The extension did not respond."));
        } else {
          resolve(response);
        }
      });
    });
  }

  function storageGet(keys) {
    return new Promise((resolve, reject) => {
      chrome.storage.local.get(keys, (value) => {
        if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
        else resolve(value);
      });
    });
  }

  function storageSet(value) {
    return new Promise((resolve, reject) => {
      chrome.storage.local.set(value, () => {
        if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
        else resolve();
      });
    });
  }

  function showNotice(message, type = "") {
    const notice = $("notice");
    notice.textContent = message;
    notice.className = `notice ${type}`.trim();
    notice.hidden = false;
    clearTimeout(showNotice.timer);
    showNotice.timer = setTimeout(() => { notice.hidden = true; }, 5000);
  }

  function populateTypes() {
    for (const type of Catalog.ITEM_TYPES) {
      const option = document.createElement("option");
      option.value = type;
      option.textContent = type;
      $("skinType").append(option);
    }
  }

  function populateItems(selected = "") {
    const type = $("skinType").value;
    const select = $("skinItem");
    select.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = type ? "Select item" : "Select type first";
    select.append(placeholder);
    for (const item of Catalog.ITEMS_BY_TYPE[type] || []) {
      const option = document.createElement("option");
      option.value = item;
      option.textContent = item;
      select.append(option);
    }
    select.disabled = !type || runtime.watching;
    select.value = selected;
    const gloves = type === "Gloves";
    $("stattrak").disabled = gloves || runtime.watching;
    if (gloves) $("stattrak").checked = false;
  }

  function describeFloat(rule) {
    const minimum = rule.float_min;
    const maximum = rule.float_max;
    if (minimum == null && maximum == null) return "Any";
    if (minimum == null) return `≤ ${Number(maximum).toFixed(3)}`;
    if (maximum == null) return `≥ ${Number(minimum).toFixed(3)}`;
    return `${Number(minimum).toFixed(3)} – ${Number(maximum).toFixed(3)}`;
  }

  function renderSkins() {
    const tbody = $("skinRows");
    tbody.replaceChildren();
    settings.skins.forEach((rule, index) => {
      const row = document.createElement("tr");
      for (const value of [
        rule.type,
        rule.weapon,
        rule.skin,
        rule.stattrak ? "Yes" : "No",
        describeFloat(rule)
      ]) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      }
      const actionCell = document.createElement("td");
      actionCell.className = "row-actions";
      const edit = document.createElement("button");
      edit.className = "row-button";
      edit.textContent = "Edit";
      edit.disabled = runtime.watching;
      edit.addEventListener("click", () => editSkin(index));
      const remove = document.createElement("button");
      remove.className = "row-button remove";
      remove.textContent = "Remove";
      remove.disabled = runtime.watching;
      remove.addEventListener("click", () => removeSkin(index));
      actionCell.append(edit, remove);
      row.append(actionCell);
      tbody.append(row);
    });
    $("emptySkins").hidden = settings.skins.length > 0;
    $("skinsHeading").textContent = `Skins to watch (${settings.skins.length}/${C.MAX_WATCHED_SKINS})`;
  }

  function parseFloatField(id, label) {
    const raw = $(id).value.trim();
    if (!raw) return null;
    const normalized = raw.replace(",", ".");
    const decimals = normalized.includes(".") ? normalized.split(".", 2)[1] : "";
    if (decimals.length > 3) throw new Error(`${label} can have at most 3 decimal places.`);
    const value = Number(normalized);
    if (!Number.isFinite(value) || value < 0 || value > 1) {
      throw new Error(`${label} must be between 0 and 1.`);
    }
    return value;
  }

  function readSkinForm() {
    const type = $("skinType").value;
    const weapon = $("skinItem").value;
    const skin = $("skinName").value.trim();
    if (!type || !weapon || !skin) throw new Error("Select a type and item, then enter a skin name.");
    const floatMin = parseFloatField("floatMin", "Minimum float");
    const floatMax = parseFloatField("floatMax", "Maximum float");
    if (floatMin != null && floatMax != null && floatMin > floatMax) {
      throw new Error("Minimum float cannot be greater than maximum float.");
    }
    const rule = { type, weapon, skin, stattrak: type !== "Gloves" && $("stattrak").checked };
    if (floatMin != null) rule.float_min = floatMin;
    if (floatMax != null) rule.float_max = floatMax;
    return rule;
  }

  function resetSkinForm() {
    editingIndex = null;
    $("skinType").value = "";
    populateItems();
    $("skinName").value = "";
    $("stattrak").checked = false;
    $("floatMin").value = "";
    $("floatMax").value = "";
    $("addSkin").textContent = "Add skin";
    $("cancelEdit").hidden = true;
  }

  async function addOrSaveSkin() {
    try {
      if (editingIndex == null && settings.skins.length >= C.MAX_WATCHED_SKINS) {
        throw new Error(`You can watch at most ${C.MAX_WATCHED_SKINS} skins.`);
      }
      const rule = readSkinForm();
      if (editingIndex == null) settings.skins.push(rule);
      else settings.skins[editingIndex] = rule;
      resetSkinForm();
      renderSkins();
      await persistSettings(false);
    } catch (error) {
      showNotice(error.message, "error");
    }
  }

  function editSkin(index) {
    const rule = settings.skins[index];
    editingIndex = index;
    $("skinType").value = rule.type;
    populateItems(rule.weapon);
    $("skinName").value = rule.skin;
    $("stattrak").checked = Boolean(rule.stattrak);
    $("floatMin").value = rule.float_min ?? "";
    $("floatMax").value = rule.float_max ?? "";
    $("addSkin").textContent = "Save changes";
    $("cancelEdit").hidden = false;
  }

  async function removeSkin(index) {
    settings.skins.splice(index, 1);
    resetSkinForm();
    renderSkins();
    await persistSettings(false);
  }

  function readSettingsFields() {
    const sites = [];
    if ($("sitePirateswap").checked) sites.push("pirateswap");
    if ($("siteSkinsmonkey").checked) sites.push("skinsmonkey");
    const interval = Number($("interval").value);
    if (!Number.isInteger(interval) || interval < 30) {
      throw new Error("The extension check interval must be at least 30 seconds.");
    }
    return {
      ...settings,
      sites,
      discordWebhookUrl: $("webhook").value.trim(),
      checkIntervalSeconds: interval
    };
  }

  async function persistSettings(showConfirmation = true) {
    settings = readSettingsFields();
    await send({ type: "SAVE_SETTINGS", settings });
    if (showConfirmation) showNotice("Settings saved.", "success");
  }

  function scheduleSettingsSave() {
    clearTimeout(settingsSaveTimer);
    settingsSaveTimer = setTimeout(async () => {
      if (runtime.watching) return;
      try {
        await persistSettings(false);
      } catch (error) {
        showNotice(error.message, "error");
      }
    }, 400);
  }

  function renderStatus() {
    $("startWatching").hidden = runtime.watching;
    $("stopWatching").hidden = !runtime.watching;
    for (const id of controls) {
      const element = $(id);
      if (element) element.disabled = runtime.watching;
    }
    if (!runtime.watching) populateItems($("skinItem").value);
    renderSkins();

    for (const site of ["pirateswap", "skinsmonkey"]) {
      const element = $(`${site}Status`);
      const status = runtime.siteStatuses?.[site];
      const label = C.SITE_LABELS[site];
      const siteSelected = settings.sites.includes(site);
      const showWatching = runtime.watching && siteSelected && status?.level !== "error";
      element.textContent = `${label}: ${showWatching ? "watching" : status?.text || "idle"}`;
      element.classList.toggle("connected", showWatching || status?.level === "connected");
      element.classList.toggle("error", status?.level === "error");
    }
    $("activityLog").textContent = runtime.logs?.length
      ? runtime.logs.join("\n")
      : "No activity yet.";
    $("activityLog").scrollTop = $("activityLog").scrollHeight;
  }

  async function clearActivityLog() {
    runtime = { ...runtime, logs: [] };
    $("activityLog").textContent = "No activity yet.";
    $("activityLog").scrollTop = 0;
    const stored = await storageGet(["runtime"]);
    await storageSet({
      runtime: {
        ...(stored.runtime || {}),
        logs: []
      }
    });
  }

  function renderSettings() {
    $("sitePirateswap").checked = settings.sites.includes("pirateswap");
    $("siteSkinsmonkey").checked = settings.sites.includes("skinsmonkey");
    $("webhook").value = settings.discordWebhookUrl || "";
    $("interval").value = settings.checkIntervalSeconds || 300;
    renderSkins();
  }

  function bindCollapsiblePanels() {
    document.querySelectorAll(".collapse-toggle[data-collapse-target]").forEach((button) => {
      const target = $(button.dataset.collapseTarget);
      const panel = button.closest(".collapsible-panel");
      if (!target || !panel) return;
      button.addEventListener("click", () => {
        const collapsed = !target.hidden;
        target.hidden = collapsed;
        panel.classList.toggle("is-collapsed", collapsed);
        button.setAttribute("aria-expanded", String(!collapsed));
      });
    });
  }

  async function refreshState() {
    const response = await send({ type: "GET_STATE" });
    settings = { ...DEFAULT_SETTINGS, ...response.settings };
    settings.skins = Array.isArray(settings.skins) ? settings.skins : [];
    settings.sites = Array.isArray(settings.sites) ? settings.sites : ["pirateswap"];
    runtime = response.runtime || runtime;
    renderSettings();
    renderStatus();
  }

  async function startWatching() {
    try {
      startInProgress = true;
      await persistSettings(false);
      if (!settings.sites.length) throw new Error("Select at least one site before starting.");
      if (!settings.skins.length) throw new Error("Add at least one skin before starting.");
      await clearActivityLog();
      await send({ type: "START" });
      await refreshState();
    } catch (error) {
      showNotice(error.message, "error");
    } finally {
      startInProgress = false;
    }
  }

  async function stopWatching() {
    try {
      await send({ type: "STOP" });
      await refreshState();
    } catch (error) {
      showNotice(error.message, "error");
    }
  }

  async function testDiscord() {
    try {
      await persistSettings(false);
      if (!settings.discordWebhookUrl) throw new Error("Paste a Discord webhook URL first.");
      await send({ type: "TEST_DISCORD" });
      showNotice("Discord test sent.", "success");
    } catch (error) {
      showNotice(error.message, "error");
    }
  }

  function bindEvents() {
    bindCollapsiblePanels();
    $("skinType").addEventListener("change", () => populateItems());
    $("addSkin").addEventListener("click", addOrSaveSkin);
    $("cancelEdit").addEventListener("click", resetSkinForm);
    $("startWatching").addEventListener("click", startWatching);
    $("stopWatching").addEventListener("click", stopWatching);
    $("testDiscord").addEventListener("click", testDiscord);
    for (const id of ["sitePirateswap", "siteSkinsmonkey"]) {
      $(id).addEventListener("change", scheduleSettingsSave);
    }
    for (const id of ["webhook", "interval"]) {
      $(id).addEventListener("input", scheduleSettingsSave);
    }
    chrome.storage.onChanged.addListener((_changes, area) => {
      if (startInProgress) return;
      if (area === "local") refreshState().catch(() => {});
    });
  }

  async function initialize() {
    populateTypes();
    bindEvents();
    try {
      await refreshState();
    } catch (error) {
      showNotice(error.message, "error");
    }
  }

  initialize();
})();
