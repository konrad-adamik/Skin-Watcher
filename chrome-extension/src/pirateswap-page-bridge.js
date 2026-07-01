(function () {
  "use strict";

  function compact(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  document.addEventListener("skinwatcher:pirateswap-set-query", () => {
    const query = document.documentElement.getAttribute(
      "data-skinwatcher-pirateswap-query"
    ) || "";
    const input = document.querySelector(
      "input[data-testid='search-autocomplete-input']"
    );
    if (!input) {
      document.documentElement.setAttribute(
        "data-skinwatcher-pirateswap-query-result",
        "missing-input"
      );
      document.dispatchEvent(new Event("skinwatcher:pirateswap-query-ready"));
      return;
    }

    input.focus();
    const propsKey = Object.keys(input).find((key) =>
      key.startsWith("__reactProps$")
    );
    let reactProps = propsKey ? input[propsKey] : null;
    let reactDepth = 0;
    if (!reactProps?.onChange && !reactProps?.onInput) {
      const fiberKey = Object.keys(input).find((key) =>
        key.startsWith("__reactFiber$") || key.startsWith("__reactInternalInstance$")
      );
      let fiber = fiberKey ? input[fiberKey] : null;
      for (let depth = 0; fiber && depth < 8; depth += 1) {
        if (fiber.memoizedProps?.onChange || fiber.memoizedProps?.onInput) {
          reactProps = fiber.memoizedProps;
          reactDepth = depth;
          break;
        }
        fiber = fiber.return;
      }
    }
    const reactHandler = reactProps?.onChange || reactProps?.onInput;
    let mode = "dom";
    if (typeof reactHandler === "function") {
      mode = `react-${reactDepth}`;
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value"
      )?.set;
      if (nativeSetter) nativeSetter.call(input, query);
      else input.value = query;
      const event = {
        type: "change",
        target: input,
        currentTarget: input,
        nativeEvent: { target: input, data: query, inputType: "insertText" },
        bubbles: true,
        cancelable: true,
        defaultPrevented: false,
        isDefaultPrevented: () => false,
        isPropagationStopped: () => false,
        persist() {},
        preventDefault() { this.defaultPrevented = true; },
        stopPropagation() {}
      };
      reactHandler(event);
    } else {
      input.select();
      let inserted = false;
      try {
        inserted = true;
        for (const character of query) {
          if (!document.execCommand("insertText", false, character)) {
            inserted = false;
            break;
          }
        }
      } catch (_error) {
        inserted = false;
      }
      if (inserted && input.value === query) {
        mode = "exec-command";
      } else {
        const nativeSetter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype,
          "value"
        )?.set;
        if (nativeSetter) nativeSetter.call(input, query);
        else input.value = query;
        input.dispatchEvent(new InputEvent("input", {
          bubbles: true,
          composed: true,
          data: query,
          inputType: "insertText"
        }));
        input.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
      }
    }
    document.documentElement.setAttribute(
      "data-skinwatcher-pirateswap-query-result",
      input.value === query ? `ok:${mode}` : `value=${input.value}`
    );
    document.dispatchEvent(new Event("skinwatcher:pirateswap-query-ready"));
  });

  function findReactItemDetails(card) {
    const roots = [];
    for (const key of Object.keys(card)) {
      if (key.startsWith("__reactProps$")) {
        roots.push(card[key]);
      } else if (key.startsWith("__reactFiber$") || key.startsWith("__reactInternalInstance$")) {
        roots.push(card[key]?.pendingProps, card[key]?.memoizedProps);
      }
    }

    const seen = new WeakSet();
    const deadline = performance.now() + 15;
    const queue = roots.map((value) => ({ value, depth: 0 }));
    const skippedKeys = new Set([
      "_owner", "alternate", "child", "return", "sibling", "stateNode"
    ]);

    for (let index = 0; index < queue.length && index < 1200; index += 1) {
      if (performance.now() > deadline) break;
      const { value, depth } = queue[index];
      if (!value || typeof value !== "object" || depth > 8 || seen.has(value)) continue;
      seen.add(value);

      let exterior;
      let rawFloat;
      try {
        exterior = compact(value.exterior).toUpperCase();
        rawFloat = value.float;
      } catch (_error) {
        continue;
      }
      const floatValue = Number(rawFloat);
      if (
        /^(FN|MW|FT|WW|BS)$/.test(exterior) &&
        rawFloat !== "" && rawFloat != null &&
        Number.isFinite(floatValue) && floatValue >= 0 && floatValue <= 1
      ) {
        return { exterior, float: floatValue, name: compact(value.name) };
      }

      const keys = Array.isArray(value)
        ? Array.from({ length: Math.min(value.length, 60) }, (_, itemIndex) => itemIndex)
        : Object.keys(value).filter((key) => !skippedKeys.has(key)).slice(0, 60);
      for (const key of keys) {
        try {
          const child = value[key];
          if (child && typeof child === "object") {
            queue.push({ value: child, depth: depth + 1 });
          }
        } catch (_error) {
          // Ignore getters that throw inside third-party component state.
        }
      }
    }
    return null;
  }

  document.addEventListener("skinwatcher:extract-pirateswap", () => {
    const details = Array.from(
      document.querySelectorAll("[data-testid='exchanger-card']")
    ).map(findReactItemDetails);
    document.documentElement.setAttribute(
      "data-skinwatcher-pirateswap-details",
      JSON.stringify(details)
    );
    document.dispatchEvent(new Event("skinwatcher:pirateswap-details-ready"));
  });
})();


