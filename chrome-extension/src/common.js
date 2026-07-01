(function () {
  "use strict";

  if (globalThis.SkinWatcherCommon) return;

  function normalizeText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function normalizeMatchText(value) {
    let normalized = normalizeText(value).toLowerCase();
    normalized = normalized.replace(/[★™�]/g, "");
    normalized = normalized.replace(/\bst\s+/g, "stattrak ");
    normalized = normalized.replace(/\bstat\s+trak\b/g, "stattrak");
    normalized = normalized.replace(/\bstattrak\s*/g, "stattrak ");
    return normalizeText(normalized);
  }

  function fullSkinName(rule) {
    if (rule.name) return normalizeText(rule.name);
    if (rule.weapon && rule.skin) return `${normalizeText(rule.weapon)} | ${normalizeText(rule.skin)}`;
    throw new Error("A watched skin needs an item and skin name.");
  }

  function skinNamePart(rule) {
    if (rule.skin) return normalizeText(rule.skin);
    return fullSkinName(rule).split("|").at(-1).trim();
  }

  function isGlove(rule) {
    const weapon = rule.weapon || fullSkinName(rule).split("|")[0];
    return weapon.toLowerCase().includes("gloves");
  }

  function stattrakMatches(rule, text) {
    if (isGlove(rule)) return true;
    const normalized = normalizeMatchText(text);
    const hasStatTrak = normalized.includes("stattrak") || normalized.includes("stat trak");
    return rule.stattrak ? hasStatTrak : !hasStatTrak;
  }

  function floatMatches(rule, rawValue) {
    if (rule.float_min == null && rule.float_max == null) return true;
    if (rawValue == null || rawValue === "") return false;
    const value = Number(rawValue);
    if (!Number.isFinite(value)) return false;
    if (rule.float_min != null && value < Number(rule.float_min)) return false;
    if (rule.float_max != null && value > Number(rule.float_max)) return false;
    return true;
  }

  function ruleKey(rule) {
    return JSON.stringify({
      type: rule.type || "",
      weapon: rule.weapon || "",
      skin: rule.skin || "",
      stattrak: Boolean(rule.stattrak),
      float_min: rule.float_min ?? null,
      float_max: rule.float_max ?? null
    });
  }

  function sleep(milliseconds) {
    return new Promise((resolve) => setTimeout(resolve, milliseconds));
  }

  function setInputValue(input, value) {
    const descriptor = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value"
    );
    descriptor.set.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function waitForDomSettle(root, options = {}) {
    const timeout = options.timeout || 15000;
    const quiet = options.quiet || 700;
    const minimum = options.minimum || 800;
    return new Promise((resolve, reject) => {
      const started = Date.now();
      let lastMutation = started;
      let mutationSeen = false;
      const observer = new MutationObserver(() => {
        mutationSeen = true;
        lastMutation = Date.now();
      });
      observer.observe(root, {
        attributes: true,
        childList: true,
        characterData: true,
        subtree: true
      });
      const interval = setInterval(() => {
        const elapsed = Date.now() - started;
        if (mutationSeen && elapsed >= minimum && Date.now() - lastMutation >= quiet) {
          clearInterval(interval);
          observer.disconnect();
          resolve();
        } else if (elapsed >= timeout) {
          clearInterval(interval);
          observer.disconnect();
          reject(new Error("The site did not finish updating its inventory."));
        }
      }, 100);
    });
  }

  function assetNameMatchesRule(marketName, rule) {
    if (!stattrakMatches(rule, marketName)) return false;
    const withoutExterior = normalizeText(marketName).replace(
      /\s*\((?:Factory New|Minimal Wear|Field-Tested|Well-Worn|Battle-Scarred)\)\s*$/i,
      ""
    );
    const actual = normalizeMatchText(withoutExterior).replace(/^stattrak\s+/, "");
    return actual === normalizeMatchText(fullSkinName(rule));
  }

  globalThis.SkinWatcherCommon = Object.freeze({
    MAX_WATCHED_SKINS: 3,
    SITE_LABELS: Object.freeze({ pirateswap: "PirateSwap", skinsmonkey: "SkinsMonkey" }),
    SITE_URLS: Object.freeze({
      pirateswap: "https://pirateswap.com/exchanger",
      skinsmonkey: "https://skinsmonkey.com/trade"
    }),
    normalizeText,
    normalizeMatchText,
    fullSkinName,
    skinNamePart,
    isGlove,
    stattrakMatches,
    floatMatches,
    ruleKey,
    sleep,
    setInputValue,
    waitForDomSettle,
    assetNameMatchesRule
  });
})();
