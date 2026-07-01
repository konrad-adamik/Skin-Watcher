if (typeof importScripts === "function" && !globalThis.SkinWatcherCommon) {
  importScripts("common.js");
}

const C = globalThis.SkinWatcherCommon;
const ALARM_NAME = "skin-watcher-check";
const MAX_LOG_LINES = 250;
const MAX_SEEN_PER_SITE = 5000;
const DEFAULT_SETTINGS = {
  sites: ["pirateswap"],
  discordWebhookUrl: "",
  checkIntervalSeconds: 300,
  skins: []
};
const DEFAULT_RUNTIME = {
  watching: false,
  startedAt: null,
  nextCheckAt: null,
  logs: [],
  siteStatuses: {},
  managedTabs: {},
  managedWindows: {},
  watchWindowId: null
};

let checkInProgress = false;

async function getStoredState() {
  const stored = await chrome.storage.local.get(["settings", "runtime", "watchState"]);
  return {
    settings: { ...DEFAULT_SETTINGS, ...(stored.settings || {}) },
    runtime: { ...DEFAULT_RUNTIME, ...(stored.runtime || {}) },
    watchState: stored.watchState || { sites: {} }
  };
}

async function setRuntime(patch) {
  const { runtime } = await getStoredState();
  const updated = { ...runtime, ...patch };
  await chrome.storage.local.set({ runtime: updated });
  return updated;
}

async function log(message) {
  const { runtime } = await getStoredState();
  const line = `[${new Date().toLocaleString()}] ${message}`;
  const logs = [...(runtime.logs || []), line].slice(-MAX_LOG_LINES);
  await chrome.storage.local.set({ runtime: { ...runtime, logs } });
}

function validateSettings(settings, requireRunnable = false) {
  if (!Array.isArray(settings.sites)) throw new Error("Invalid site selection.");
  if (settings.sites.some((site) => !C.SITE_URLS[site])) throw new Error("Unsupported site selected.");
  if (!Number.isInteger(Number(settings.checkIntervalSeconds)) || Number(settings.checkIntervalSeconds) < 30) {
    throw new Error("The extension check interval must be at least 30 seconds.");
  }
  if (!Array.isArray(settings.skins) || settings.skins.length > C.MAX_WATCHED_SKINS) {
    throw new Error(`You can watch at most ${C.MAX_WATCHED_SKINS} skins.`);
  }
  if (requireRunnable && !settings.sites.length) throw new Error("Select at least one site before starting.");
  if (requireRunnable && !settings.skins.length) throw new Error("Add at least one skin before starting.");
  if (requireRunnable && !String(settings.discordWebhookUrl || "").trim()) {
    throw new Error("Set a Discord webhook URL before starting.");
  }
  for (const rule of settings.skins) {
    C.fullSkinName(rule);
    for (const value of [rule.float_min, rule.float_max]) {
      if (value != null && (!Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 1)) {
        throw new Error("Float limits must be between 0 and 1.");
      }
    }
    if (rule.float_min != null && rule.float_max != null && Number(rule.float_min) > Number(rule.float_max)) {
      throw new Error("Minimum float cannot be greater than maximum float.");
    }
  }
}

async function openDashboard() {
  const dashboardUrl = chrome.runtime.getURL("dashboard.html");
  const tabs = await chrome.tabs.query({});
  const dashboardTab = tabs.find((tab) => tab.url === dashboardUrl);
  if (dashboardTab) {
    await chrome.tabs.update(dashboardTab.id, { active: true });
    if (dashboardTab.windowId != null) await chrome.windows.update(dashboardTab.windowId, { focused: true });
  } else {
    await chrome.tabs.create({ url: dashboardUrl, active: true });
  }
}

async function waitForTabReady(tabId, timeout = 30000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") return tab;
    await C.sleep(250);
  }
  throw new Error("The site tab did not finish loading.");
}

async function captureFocusedLocation() {
  try {
    const window = await chrome.windows.getLastFocused();
    if (window.id == null) return null;
    const [tab] = await chrome.tabs.query({ active: true, windowId: window.id });
    return { windowId: window.id, tabId: tab?.id ?? null };
  } catch (_error) {
    return null;
  }
}

async function resolveWatchWindowId(preferredWindowId, fallbackWindowId) {
  if (preferredWindowId != null) {
    try {
      const window = await chrome.windows.get(preferredWindowId);
      if (window.type === "normal") return window.id;
    } catch (_error) {
      // The selected watcher window was closed; discover a fallback below.
    }
  }
  const dashboardUrl = chrome.runtime.getURL("dashboard.html");
  const dashboardTabs = await chrome.tabs.query({ url: dashboardUrl });
  const dashboardTab = dashboardTabs[0];
  return dashboardTab?.windowId ?? fallbackWindowId ?? null;
}

async function restoreDashboardTab(windowId) {
  if (windowId == null) return;
  const dashboardUrl = chrome.runtime.getURL("dashboard.html");
  const dashboardTabs = await chrome.tabs.query({ url: dashboardUrl });
  const dashboardTab = dashboardTabs.find((tab) => tab.windowId === windowId);
  if (dashboardTab) {
    await chrome.tabs.update(dashboardTab.id, { active: true });
  } else {
    await chrome.tabs.create({ url: dashboardUrl, windowId, active: true });
  }
}

async function ensureSiteTab(site, options = {}) {
  const activate = Boolean(options.activate);
  const focusWindow = options.focusWindow !== false;
  const targetWindowId = options.windowId;
  const url = C.SITE_URLS[site];
  const { runtime } = await getStoredState();
  const managedId = runtime.managedTabs?.[site];
  if (managedId != null) {
    try {
      const tab = await chrome.tabs.get(managedId);
      if (runtime.managedWindows?.[site] != null) {
        await chrome.tabs.remove(managedId);
        throw new Error("The old helper window needs migration.");
      }
      if (targetWindowId != null && tab.windowId !== targetWindowId) {
        await chrome.tabs.remove(managedId);
        throw new Error("The site tab needs to move to the active window.");
      }
      if (activate) {
        if (!tab.active) await chrome.tabs.update(managedId, { active: true });
        if (focusWindow) await chrome.windows.update(tab.windowId, { focused: true });
      }
      if (tab.discarded) await chrome.tabs.reload(managedId);
      return waitForTabReady(managedId);
    } catch (_error) {
      // The managed tab was closed; discover or create a replacement below.
    }
  }

  const createOptions = { url, active: activate };
  if (targetWindowId != null) createOptions.windowId = targetWindowId;
  const tab = await chrome.tabs.create(createOptions);
  await log(`${C.SITE_LABELS[site]} opened in a managed browser tab.`);
  const updatedManagedTabs = { ...(runtime.managedTabs || {}), [site]: tab.id };
  const updatedManagedWindows = { ...(runtime.managedWindows || {}) };
  delete updatedManagedWindows[site];
  await setRuntime({
    managedTabs: updatedManagedTabs,
    managedWindows: updatedManagedWindows
  });
  return waitForTabReady(tab.id);
}

async function sendToSiteTab(tabId, message) {
  let lastError;
  let reloaded = false;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      return await chrome.tabs.sendMessage(tabId, message);
    } catch (error) {
      lastError = error;
      if (
        !reloaded &&
        /receiving end does not exist|could not establish connection/i.test(error.message || "")
      ) {
        reloaded = true;
        await chrome.tabs.reload(tabId);
        await waitForTabReady(tabId);
      }
      await C.sleep(250);
    }
  }
  throw new Error(lastError?.message || "The site helper did not connect.");
}

async function sendCheckToSiteTab(tabId, message, site) {
  const expectedVersion = chrome.runtime.getManifest().version;
  let result = await sendToSiteTab(tabId, message);
  if (result?.helperVersion === expectedVersion) return result;

  const reportedVersion = result?.helperVersion || "unknown";
  await log(
    `${C.SITE_LABELS[site]} helper is outdated (${reportedVersion}); ` +
    `reloading it for extension v${expectedVersion}.`
  );
  await chrome.tabs.reload(tabId);
  await waitForTabReady(tabId);
  result = await sendToSiteTab(tabId, message);
  if (result?.helperVersion !== expectedVersion) {
    throw new Error(
      `Site helper version mismatch after reload ` +
      `(expected ${expectedVersion}, received ${result?.helperVersion || "none"}).`
    );
  }
  return result;
}

async function updateSiteStatus(site, text, level) {
  const { runtime } = await getStoredState();
  await setRuntime({
    siteStatuses: {
      ...(runtime.siteStatuses || {}),
      [site]: { text, level, updatedAt: Date.now() }
    }
  });
}

function siteSignature(settings, site) {
  return JSON.stringify({ site, skins: settings.skins });
}

function trimSeen(seen) {
  const entries = Object.entries(seen);
  if (entries.length <= MAX_SEEN_PER_SITE) return seen;
  return Object.fromEntries(
    entries.sort((left, right) => Number(right[1]) - Number(left[1])).slice(0, MAX_SEEN_PER_SITE)
  );
}

async function postDiscord(webhookUrl, embed) {
  if (!webhookUrl) return false;
  if (!/^https:\/\/(?:canary\.|ptb\.)?discord(?:app)?\.com\/api\/webhooks\//i.test(webhookUrl)) {
    throw new Error("The Discord webhook URL is not valid.");
  }
  const response = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "Skin Watcher", embeds: [embed] })
  });
  if (!response.ok) throw new Error(`Discord returned HTTP ${response.status}.`);
  return true;
}

async function notifyMatch(settings, site, match) {
  const source = C.SITE_LABELS[site];
  return postDiscord(settings.discordWebhookUrl, {
    title: `[${source}] ${match.title}`.slice(0, 256),
    description: String(match.message || "").slice(0, 4096),
    color: 16753205,
    timestamp: new Date().toISOString(),
    thumbnail: match.imageUrl ? { url: match.imageUrl } : undefined,
    fields: [{ name: "Site", value: `[${source}](${C.SITE_URLS[site]})`, inline: true }]
  });
}

async function processMatches(settings, site, matches) {
  const state = await getStoredState();
  const allSites = state.watchState.sites || {};
  const signature = siteSignature(settings, site);
  let siteState = allSites[site] || {};
  if (siteState.signature !== signature) {
    siteState = { signature, baselineDone: false, seen: {} };
  }
  const baselineDone = Boolean(siteState.baselineDone);
  const seen = { ...(siteState.seen || {}) };
  let newCount = 0;
  let notifiedCount = 0;

  for (const match of matches) {
    const identity = `${match.ruleKey}::${match.identityText}`;
    if (seen[identity]) continue;
    seen[identity] = Date.now();
    newCount += 1;
    if (baselineDone) {
      const { runtime } = await getStoredState();
      if (!runtime.watching) break;
      if (await notifyMatch(settings, site, match)) notifiedCount += 1;
    }
  }

  allSites[site] = {
    signature,
    baselineDone: true,
    seen: trimSeen(seen),
    lastChecked: Date.now()
  };
  await chrome.storage.local.set({ watchState: { sites: allSites } });
  if (!baselineDone) {
    await log(`${C.SITE_LABELS[site]} initial scan saved ${matches.length} listing(s) as its baseline.`);
  }
  else await log(`${C.SITE_LABELS[site]} found ${newCount} new listing(s); Discord notifications sent: ${notifiedCount}.`);
}

async function runChecks(reason = "scheduled") {
  if (checkInProgress) {
    await log("A check is already running.");
    return;
  }
  checkInProgress = true;
  try {
    const initial = await getStoredState();
    if (!initial.runtime.watching) return;
    validateSettings(initial.settings, true);
    await log(`Starting ${reason} availability check.`);

    for (const site of initial.settings.sites) {
      const current = await getStoredState();
      if (!current.runtime.watching) break;
      const previousLocation = await captureFocusedLocation();
      try {
        const watchWindowId = await resolveWatchWindowId(
          current.runtime.watchWindowId,
          previousLocation?.windowId
        );
        if (watchWindowId !== current.runtime.watchWindowId) {
          await setRuntime({ watchWindowId });
        }
        await updateSiteStatus(site, "connecting", "working");
        const tab = await ensureSiteTab(site, {
          activate: true,
          focusWindow: false,
          windowId: watchWindowId
        });
        await C.sleep(750);
        await updateSiteStatus(site, "checking", "working");
        const result = await sendCheckToSiteTab(tab.id, {
          type: "CHECK_SKINS",
          skins: initial.settings.skins
        }, site);
        if (!result?.ok) throw new Error(result?.error || "The site check failed.");
        await processMatches(initial.settings, site, result.matches || []);
        await updateSiteStatus(site, `${result.matches?.length || 0} match(es)`, "connected");
      } catch (error) {
        await updateSiteStatus(site, error.message, "error");
        await log(`${C.SITE_LABELS[site]} check failed: ${error.message}`);
      }
    }

    try {
      const { runtime } = await getStoredState();
      await restoreDashboardTab(runtime.watchWindowId);
    } catch (error) {
      await log(`Could not restore the Skin Watcher dashboard tab: ${error.message}`);
    }

    const latest = await getStoredState();
    if (latest.runtime.watching) {
      const nextCheckAt = Date.now() + Number(latest.settings.checkIntervalSeconds) * 1000;
      await setRuntime({ nextCheckAt });
      await log(`Check complete. Next check in ${latest.settings.checkIntervalSeconds} seconds.`);
    }
  } finally {
    checkInProgress = false;
  }
}

async function scheduleAlarm(settings) {
  await chrome.alarms.clear(ALARM_NAME);
  const periodInMinutes = Math.max(0.5, Number(settings.checkIntervalSeconds) / 60);
  await chrome.alarms.create(ALARM_NAME, {
    delayInMinutes: periodInMinutes,
    periodInMinutes
  });
}

async function startWatching(watchWindowId) {
  const { settings, runtime } = await getStoredState();
  validateSettings(settings, true);
  if (runtime.watching) return;
  const startedAt = Date.now();
  await chrome.storage.local.set({
    runtime: {
      ...runtime,
      watching: true,
      startedAt,
      nextCheckAt: Date.now(),
      logs: [],
      siteStatuses: {},
      watchWindowId
    },
    watchState: { sites: {} }
  });
  await scheduleAlarm(settings);
  await log(`Watcher started (extension v${chrome.runtime.getManifest().version}).`);
  runChecks("initial").catch((error) => log(`Check failed: ${error.message}`));
}

async function stopWatching() {
  await chrome.alarms.clear(ALARM_NAME);
  const { runtime } = await getStoredState();
  const managedTabs = runtime.managedTabs || {};
  await setRuntime({
    watching: false,
    startedAt: null,
    nextCheckAt: null,
    siteStatuses: {},
    managedTabs: {},
    managedWindows: {},
    watchWindowId: null
  });
  for (const tabId of Object.values(managedTabs)) {
    try { await chrome.tabs.remove(tabId); } catch (_error) { /* Already closed. */ }
  }
  await log("Watcher stopped.");
}

async function testDiscord() {
  const { settings } = await getStoredState();
  if (!settings.discordWebhookUrl) throw new Error("Paste a Discord webhook URL first.");
  await postDiscord(settings.discordWebhookUrl, {
    title: "Skin Watcher Test",
    description: "If you see this, extension notifications are configured correctly.",
    color: 16753205,
    timestamp: new Date().toISOString()
  });
  await log("Discord test message sent.");
}

async function handleMessage(message, sender) {
  switch (message?.type) {
    case "GET_STATE": {
      const state = await getStoredState();
      return { ok: true, settings: state.settings, runtime: state.runtime };
    }
    case "SAVE_SETTINGS": {
      const state = await getStoredState();
      if (state.runtime.watching) throw new Error("Stop watching before changing settings.");
      const settings = { ...DEFAULT_SETTINGS, ...(message.settings || {}) };
      validateSettings(settings, false);
      await chrome.storage.local.set({ settings });
      return { ok: true };
    }
    case "START":
      await startWatching(sender?.tab?.windowId ?? null);
      return { ok: true };
    case "STOP":
      await stopWatching();
      return { ok: true };
    case "TEST_DISCORD":
      await testDiscord();
      return { ok: true };
    default:
      throw new Error("Unknown extension message.");
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender)
    .then(sendResponse)
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});

chrome.action.onClicked.addListener(() => {
  openDashboard().catch((error) => log(`Could not open dashboard: ${error.message}`));
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) {
    runChecks("scheduled").catch((error) => log(`Check failed: ${error.message}`));
  }
});

chrome.runtime.onInstalled.addListener(async () => {
  await chrome.alarms.clear(ALARM_NAME);
  const stored = await chrome.storage.local.get(["settings", "runtime", "watchState"]);
  await chrome.storage.local.set({
    settings: { ...DEFAULT_SETTINGS, ...(stored.settings || {}) },
    runtime: { ...DEFAULT_RUNTIME, ...(stored.runtime || {}), watching: false },
    watchState: stored.watchState || { sites: {} }
  });
  await openDashboard();
});

chrome.runtime.onStartup.addListener(async () => {
  const { settings, runtime } = await getStoredState();
  if (runtime.watching) await scheduleAlarm(settings);
});
