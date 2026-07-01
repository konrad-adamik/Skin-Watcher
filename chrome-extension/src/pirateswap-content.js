(function () {
  "use strict";

  const C = globalThis.SkinWatcherCommon;
  const MAX_SCROLL_STEPS = 140;

  function isVisible(element) {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  }

  function isEffectivelyVisible(element) {
    if (!isVisible(element)) return false;
    let current = element;
    while (current && current !== document.body) {
      const style = getComputedStyle(current);
      if (
        style.display === "none" ||
        style.visibility === "hidden" ||
        Number(style.opacity) <= 0.05 ||
        style.pointerEvents === "none"
      ) return false;
      current = current.parentElement;
    }
    return true;
  }

  function findSearchBox() {
    const primary = document.querySelector(
      "input[data-testid='search-autocomplete-input']"
    );
    if (primary && !primary.disabled) return primary;

    const selectors = [
      "input[placeholder='Search']",
      "input[placeholder='SEARCH']",
      "input[type='search']",
      "input[type='text']"
    ];
    for (const selector of selectors) {
      const match = Array.from(document.querySelectorAll(selector)).find(
        (element) => isVisible(element) && !element.disabled
      );
      if (match) return match;
    }
    throw new Error("Could not find the PirateSwap search box.");
  }

  function expectedOptionText(rule) {
    const name = C.fullSkinName(rule);
    if (C.isGlove(rule)) return name;
    return rule.stattrak ? `StatTrak ${name}` : name;
  }

  function setSearchQueryInPage(query) {
    return new Promise((resolve, reject) => {
      const finish = () => {
        clearTimeout(timeout);
        document.removeEventListener("skinwatcher:pirateswap-query-ready", finish);
        const result = document.documentElement.getAttribute(
          "data-skinwatcher-pirateswap-query-result"
        );
        if (result?.startsWith("ok:")) resolve();
        else reject(new Error(`PirateSwap query bridge failed: ${result || "no result"}.`));
      };
      const timeout = setTimeout(() => {
        document.removeEventListener("skinwatcher:pirateswap-query-ready", finish);
        reject(new Error("PirateSwap query bridge did not respond."));
      }, 3000);
      document.addEventListener("skinwatcher:pirateswap-query-ready", finish, { once: true });
      document.documentElement.setAttribute(
        "data-skinwatcher-pirateswap-query",
        query
      );
      document.dispatchEvent(new Event("skinwatcher:pirateswap-set-query"));
    });
  }

  function optionMatchesRule(rule, normalizedOption) {
    const skin = C.normalizeMatchText(rule.skin || C.skinNamePart(rule));
    const weapon = C.normalizeMatchText(rule.weapon || "");
    if (skin && !normalizedOption.includes(skin)) return false;
    if (weapon && !normalizedOption.includes(weapon)) return false;
    if (rule.stattrak && !normalizedOption.includes("stattrak")) return false;
    if (!rule.stattrak && normalizedOption.includes("stattrak") && !C.isGlove(rule)) return false;
    return true;
  }

  async function selectAutocompleteOption(rule) {
    const expected = C.normalizeMatchText(expectedOptionText(rule));
    const skin = C.skinNamePart(rule).toLowerCase();
    const started = Date.now();
    const seenOptions = new Set();
    while (Date.now() - started < 10000) {
      const options = Array.from(document.querySelectorAll("li")).filter((option) => {
        const text = C.normalizeText(option.textContent);
        if (text.toLowerCase().includes(skin)) seenOptions.add(text);
        return text.toLowerCase().includes(skin);
      });
      for (const option of options) {
        const text = C.normalizeText(option.textContent);
        const normalized = C.normalizeMatchText(text);
        if (normalized === expected || optionMatchesRule(rule, normalized)) {
          option.click();
          return text;
        }
      }
      await C.sleep(250);
    }
    const details = seenOptions.size
      ? ` Candidates: ${[...seenOptions].slice(0, 10).join(" | ")}`
      : " No matching autocomplete candidates were rendered.";
    const bridgeResult = document.documentElement.getAttribute(
      "data-skinwatcher-pirateswap-query-result"
    ) || "unknown";
    const inputValue = document.querySelector(
      "input[data-testid='search-autocomplete-input']"
    )?.value || "";
    const input = document.querySelector(
      "input[data-testid='search-autocomplete-input']"
    );
    const reactMarkerCount = input
      ? Object.keys(input).filter((key) =>
        key.startsWith("__reactProps$") ||
        key.startsWith("__reactFiber$") ||
        key.startsWith("__reactInternalInstance$")
      ).length
      : 0;
    const diagnostics = [
      `ready=${document.readyState}`,
      `visibility=${document.visibilityState}`,
      `focused=${document.hasFocus()}`,
      `input-active=${document.activeElement === input}`,
      `react-markers=${reactMarkerCount}`,
      `li=${document.querySelectorAll("li").length}`
    ].join(", ");
    throw new Error(
      `Could not find the PirateSwap option: ${expectedOptionText(rule)}.${details} ` +
      `Query bridge: ${bridgeResult}; input value: ${inputValue || "empty"}. ` +
      `Page diagnostics: ${diagnostics}.`
    );
  }

  function isInventoryLoading() {
    return Array.from(document.querySelectorAll("body *")).some((element) =>
      /\bitems\s+loading\b/i.test(C.normalizeText(
        Array.from(element.childNodes)
          .filter((node) => node.nodeType === Node.TEXT_NODE)
          .map((node) => node.textContent)
          .join(" ")
      )) &&
      isEffectivelyVisible(element)
    );
  }

  function exchangerCards() {
    return Array.from(document.querySelectorAll("[data-testid='exchanger-card']"));
  }

  function isScrollable(element) {
    if (!element || element === document.body || element === document.documentElement) return false;
    const style = getComputedStyle(element);
    return (
      /(auto|scroll|overlay)/i.test(style.overflowY) &&
      element.scrollHeight > element.clientHeight + 20 &&
      isVisible(element)
    );
  }

  function findInventoryScroller() {
    const ancestorCandidates = new Set();
    for (const card of exchangerCards()) {
      let node = card.parentElement;
      while (node && node !== document.body) {
        if (isScrollable(node)) ancestorCandidates.add(node);
        node = node.parentElement;
      }
    }

    const candidates = ancestorCandidates.size
      ? [...ancestorCandidates]
      : Array.from(document.querySelectorAll("body *")).filter((element) =>
        isScrollable(element) && element.querySelector("[data-testid='exchanger-card']")
      );

    return candidates
      .sort((left, right) => {
        const leftRange = left.scrollHeight - left.clientHeight;
        const rightRange = right.scrollHeight - right.clientHeight;
        return rightRange - leftRange;
      })[0] || document.scrollingElement || document.documentElement;
  }

  async function scrollInventory(scroller, targetTop) {
    scroller.scrollTop = targetTop;
    scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
    await C.sleep(260);
  }

  async function waitForInventoryRender(selectedLabel, timeout = 45000) {
    const started = Date.now();
    let lastCardCount = -1;
    let lastLoading = null;
    let stableSince = started;
    let sawLoading = false;

    while (Date.now() - started < timeout) {
      const loading = isInventoryLoading();
      const cardCount = exchangerCards().length;
      if (loading) sawLoading = true;

      if (loading !== lastLoading || cardCount !== lastCardCount) {
        lastLoading = loading;
        lastCardCount = cardCount;
        stableSince = Date.now();
      }

      const elapsed = Date.now() - started;
      const stableFor = Date.now() - stableSince;
      const minimumWait = sawLoading ? 1200 : cardCount ? 1800 : 6500;
      if (!loading && cardCount > 0 && elapsed >= minimumWait && stableFor >= 700) return;
      if (!loading && elapsed >= minimumWait && stableFor >= 900) return;

      await C.sleep(250);
    }

    throw new Error(
      `PirateSwap inventory did not finish loading for ${selectedLabel}. ` +
      `loading=${isInventoryLoading()}, cards=${exchangerCards().length}.`
    );
  }

  function requestReactDetails() {
    return new Promise((resolve) => {
      const finish = () => {
        clearTimeout(timeout);
        document.removeEventListener("skinwatcher:pirateswap-details-ready", finish);
        try {
          resolve(JSON.parse(
            document.documentElement.getAttribute("data-skinwatcher-pirateswap-details") || "[]"
          ));
        } catch (_error) {
          resolve([]);
        }
      };
      const timeout = setTimeout(() => {
        document.removeEventListener("skinwatcher:pirateswap-details-ready", finish);
        resolve([]);
      }, 1500);
      document.addEventListener("skinwatcher:pirateswap-details-ready", finish, { once: true });
      document.dispatchEvent(new Event("skinwatcher:extract-pirateswap"));
    });
  }

  async function extractCards(selectedLabel) {
    const cards = Array.from(document.querySelectorAll("[data-testid='exchanger-card']"));
    const reactDetails = await requestReactDetails();
    return cards.map((card, index) => {
      const details = reactDetails[index];
      const nameNode = card.querySelector("[data-testid='skin-card-name']");
      const name = C.normalizeText(nameNode?.textContent) || details?.name || selectedLabel;
      const cardText = C.normalizeText(card.textContent).replace(/[\u2010-\u2015\u2212]/g, "-");
      const paragraphs = Array.from(card.querySelectorAll("p"))
        .map((element) => C.normalizeText(element.textContent))
        .filter(Boolean);
      const searchable = [nameNode?.parentElement?.textContent, ...paragraphs, cardText]
        .map(C.normalizeText)
        .join(" ")
        .replace(/[\u2010-\u2015\u2212]/g, "-");
      const floatMatch =
        searchable.match(/\b(FN|MW|FT|WW|BS)\b\s*(?:-|:)\s*(0?\.\d+|1(?:\.0+)?)/i) ||
        searchable.match(/\b(FN|MW|FT|WW|BS)\b\s+(0?\.\d+|1(?:\.0+)?)/i) ||
        searchable.match(/\bfloat\b\s*(?:-|:)?\s*\b(FN|MW|FT|WW|BS)\b\s*(?:-|:)?\s*(0?\.\d+|1(?:\.0+)?)/i);
      const rawFloat = searchable.match(/\bfloat\b\s*(?:-|:)?\s*(0?\.\d+|1(?:\.0+)?)/i);
      const floatValue = details?.float ?? (floatMatch ? Number(floatMatch[2]) : rawFloat ? Number(rawFloat[1]) : null);
      const exterior = details?.exterior || floatMatch?.[1]?.toUpperCase() || "";
      const image = card.querySelector("img[alt]");
      const imageSrc = image?.currentSrc || image?.getAttribute("src") || "";
      const imageUrl = /^https?:\/\//i.test(imageSrc)
        ? imageSrc
        : imageSrc
          ? new URL(imageSrc, location.href).href
          : "";
      return {
        name,
        floatValue,
        exterior,
        imageUrl,
        identityText: `${selectedLabel} | float=${floatValue ?? "no float"}`
      };
    });
  }

  function cardIdentity(card) {
    return [
      C.normalizeText(card.name),
      card.floatValue ?? "no-float",
      C.normalizeText(card.exterior),
      card.imageUrl,
      C.normalizeText(card.identityText)
    ].join("|");
  }

  async function collectCards(selectedLabel) {
    const scroller = findInventoryScroller();
    const originalTop = scroller.scrollTop || 0;
    const cards = new Map();
    let stagnantSteps = 0;
    let previousCount = -1;

    await scrollInventory(scroller, 0);

    for (let step = 0; step < MAX_SCROLL_STEPS; step += 1) {
      for (const card of await extractCards(selectedLabel)) {
        cards.set(cardIdentity(card), card);
      }

      const noNewCards = cards.size === previousCount;
      stagnantSteps = noNewCards ? stagnantSteps + 1 : 0;
      previousCount = cards.size;
      if (stagnantSteps >= 3) break;

      const atBottom = scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 4;
      if (atBottom) break;

      const previousTop = scroller.scrollTop || 0;
      const nextTop = Math.min(
        scroller.scrollTop + Math.max(scroller.clientHeight * 0.75, 220),
        scroller.scrollHeight
      );
      await scrollInventory(scroller, nextTop);

      if (Math.abs((scroller.scrollTop || 0) - previousTop) < 2) break;
    }

    await scrollInventory(scroller, originalTop);
    return [...cards.values()];
  }

  function cardToMatch(card, rule, selectedLabel) {
    const floatLabel = card.floatValue == null
      ? "no float"
      : `${card.exterior ? `${card.exterior} - ` : ""}${Number(card.floatValue).toFixed(8).replace(/0+$/, "").replace(/\.$/, "")}`;
    return {
      ruleKey: C.ruleKey(rule),
      title: selectedLabel.replace(/™/g, ""),
      message: `### Float: ${floatLabel}`,
      identityText: card.identityText,
      imageUrl: card.imageUrl || null
    };
  }

  async function searchRule(rule) {
    const searchBox = findSearchBox();
    const query = rule.query || C.skinNamePart(rule) || C.fullSkinName(rule);
    try {
      await setSearchQueryInPage(query);
    } catch (_error) {
      // Retain an isolated-world fallback for pages where the main-world bridge
      // was not injected yet. A tab reload normally restores the bridge.
      C.setInputValue(searchBox, query);
    }
    await C.sleep(1500);
    const selectedLabel = await selectAutocompleteOption(rule);
    await waitForInventoryRender(selectedLabel);
    const cards = await collectCards(selectedLabel);
    return cards
      .filter((card) => C.stattrakMatches(rule, selectedLabel) && C.floatMatches(rule, card.floatValue))
      .map((card) => cardToMatch(card, rule, selectedLabel));
  }

  async function checkSkins(rules) {
    const matches = [];
    for (const rule of rules) matches.push(...await searchRule(rule));
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
