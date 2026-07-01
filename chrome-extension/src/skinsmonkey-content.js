(function () {
  "use strict";

  const C = globalThis.SkinWatcherCommon;
  const MAX_SCROLL_STEPS = 140;

  function findSiteInventory() {
    // SITE is SkinsMonkey's right-side "You Receive" inventory. USER is the
    // left-side Steam inventory and is intentionally never touched.
    const inventory = document.querySelector(
      '[data-inventory="SITE"][data-scope="TRADE"]'
    );
    if (!inventory) throw new Error("Could not find the right-side SkinsMonkey inventory.");
    return inventory;
  }

  function inventoryError(inventory) {
    const text = C.normalizeText(inventory.textContent);
    if (/inventory could not be downloaded|something went wrong/i.test(text)) {
      return "SkinsMonkey could not load its right-side inventory.";
    }
    return "";
  }

  function isVisible(element) {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  }

  function isScrollable(element) {
    if (!element) return false;
    const style = getComputedStyle(element);
    return (
      /(auto|scroll|overlay)/i.test(style.overflowY) &&
      element.scrollHeight > element.clientHeight + 20 &&
      isVisible(element)
    );
  }

  function findInventoryScroller(inventory) {
    const primary = inventory.querySelector(".inventory-grid .vue-recycle-scroller");
    if (primary) return primary;
    return Array.from(inventory.querySelectorAll("*"))
      .filter(isScrollable)
      .sort((left, right) => {
        const leftRange = left.scrollHeight - left.clientHeight;
        const rightRange = right.scrollHeight - right.clientHeight;
        return rightRange - leftRange;
      })[0] || null;
  }

  async function scrollInventory(scroller, targetTop) {
    scroller.scrollTop = targetTop;
    scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
    await C.sleep(220);
  }

  async function waitForInventoryReady(inventory) {
    const input = inventory.querySelector(".inventory-toolbar-search input");
    if (!input) throw new Error("Could not find the SkinsMonkey inventory search box.");
    if (input.value) {
      C.setInputValue(input, "");
      await C.sleep(250);
    }
    const started = Date.now();
    while (Date.now() - started < 30000) {
      const siteError = inventoryError(inventory);
      if (siteError) throw new Error(siteError);
      if (
        findInventoryScroller(inventory) &&
        inventory.querySelector(".inventory-grid-row .item-card img.item-card__image[alt]")
      ) return;
      await C.sleep(500);
    }
    throw new Error("SkinsMonkey did not finish loading its right-side inventory.");
  }

  async function searchInventory(inventory, query) {
    const input = inventory.querySelector(".inventory-toolbar-search input");
    if (!input) throw new Error("Could not find the SkinsMonkey inventory search box.");

    const settle = C.waitForDomSettle(inventory, {
      timeout: 20000,
      minimum: 1200,
      quiet: 800
    });
    C.setInputValue(input, "");
    await C.sleep(120);
    C.setInputValue(input, query);
    try {
      await settle;
    } catch (error) {
      const siteError = inventoryError(inventory);
      throw new Error(siteError || `SkinsMonkey search timed out for ${query}.`);
    }
    await C.sleep(400);
    const siteError = inventoryError(inventory);
    if (siteError) throw new Error(siteError);
  }

  function extractRenderedAssets(inventory) {
    const assets = [];
    for (const row of inventory.querySelectorAll(".inventory-grid-row")) {
      const view = row.closest(".vue-recycle-scroller__item-view");
      if (view?.style?.transform?.includes("-9999px")) continue;

      const assetIds = (row.id || "").split("|");
      const cards = Array.from(row.children).filter((element) =>
        element.classList.contains("item-card")
      );
      cards.forEach((card, index) => {
        const image = card.querySelector("img.item-card__image");
        const marketName = C.normalizeText(image?.getAttribute("alt"));
        if (!marketName) return;
        const floatElement = card.querySelector(".item-card__float");
        const floatPercent = Number.parseFloat(
          floatElement?.style?.getPropertyValue("--float-value") || ""
        );
        const exterior = C.normalizeText(
          card.querySelector(".item-card-730-label__exterior")?.textContent
        );
        const stackCount = Number.parseInt(
          card.querySelector(".item-card-top__stack span")?.textContent || "1",
          10
        );
        assets.push({
          assetId: assetIds[index] || null,
          marketName,
          exterior,
          floatValue: Number.isFinite(floatPercent) ? floatPercent / 100 : null,
          imageUrl: image?.currentSrc || image?.getAttribute("src") || "",
          stackCount: Number.isFinite(stackCount) ? stackCount : 1
        });
      });
    }
    return assets;
  }

  async function collectAssets(inventory) {
    const scroller = findInventoryScroller(inventory);
    if (!scroller) return [];
    const originalTop = scroller.scrollTop || 0;
    await scrollInventory(scroller, 0);
    const assets = new Map();
    let stagnantSteps = 0;
    let previousTop = -1;
    let previousCount = -1;

    for (let step = 0; step < MAX_SCROLL_STEPS; step += 1) {
      for (const asset of extractRenderedAssets(inventory)) {
        const identity = asset.assetId || `${asset.marketName}|${asset.floatValue}|${asset.imageUrl}`;
        assets.set(identity, asset);
      }
      if (scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 2) break;
      previousTop = scroller.scrollTop;
      await scrollInventory(
        scroller,
        Math.min(scroller.scrollTop + Math.max(scroller.clientHeight * 0.8, 135), scroller.scrollHeight)
      );
      const samePosition = Math.abs((scroller.scrollTop || 0) - previousTop) < 2;
      const sameCount = assets.size === previousCount;
      stagnantSteps = samePosition && sameCount ? stagnantSteps + 1 : 0;
      previousCount = assets.size;
      if (stagnantSteps >= 3) break;
    }
    await scrollInventory(scroller, originalTop);
    return [...assets.values()];
  }

  async function collectAssetsWhenReady(inventory) {
    const started = Date.now();
    let assets = [];
    while (Date.now() - started < 5000) {
      assets = await collectAssets(inventory);
      if (assets.length) return assets;
      const siteError = inventoryError(inventory);
      if (siteError) throw new Error(siteError);
      await C.sleep(500);
    }
    return assets;
  }

  function exteriorFor(asset) {
    if (asset.exterior) return asset.exterior.toUpperCase();
    const match = asset.marketName.match(
      /\((Factory New|Minimal Wear|Field-Tested|Well-Worn|Battle-Scarred)\)\s*$/i
    );
    if (!match) return "";
    return {
      "factory new": "FN",
      "minimal wear": "MW",
      "field-tested": "FT",
      "well-worn": "WW",
      "battle-scarred": "BS"
    }[match[1].toLowerCase()] || "";
  }

  function assetToMatch(asset, rule) {
    const floatIdentity = asset.floatValue == null ? "no float" : String(asset.floatValue);
    let floatLabel = "no float";
    if (asset.floatValue != null) {
      floatLabel = asset.floatValue.toFixed(8).replace(/0+$/, "").replace(/\.$/, "");
      const exterior = exteriorFor(asset);
      if (exterior) floatLabel = `${exterior} - ${floatLabel}`;
    }
    return {
      ruleKey: C.ruleKey(rule),
      title: asset.marketName.replace(/™/g, ""),
      message: `### Float: ${floatLabel}`,
      identityText: `asset=${asset.assetId || asset.marketName} | float=${floatIdentity}`,
      imageUrl: asset.imageUrl || null
    };
  }

  async function checkSkins(rules) {
    const inventory = findSiteInventory();
    await waitForInventoryReady(inventory);
    const matches = [];
    for (const rule of rules) {
      const query = C.fullSkinName(rule);
      await searchInventory(inventory, query);
      const assets = await collectAssetsWhenReady(inventory);
      for (const asset of assets) {
        if (!C.assetNameMatchesRule(asset.marketName, rule)) continue;
        if (!C.floatMatches(rule, asset.floatValue)) continue;
        matches.push(assetToMatch(asset, rule));
      }
    }
    return matches;
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "CHECK_SKINS") return false;
    const helperVersion = chrome.runtime.getManifest().version;
    checkSkins(Array.isArray(message.skins) ? message.skins : [])
      .then((matches) => sendResponse({ ok: true, matches, helperVersion }))
      .catch((error) => sendResponse({
        ok: false,
        error: error.message,
        helperVersion
      }));
    return true;
  });
})();
