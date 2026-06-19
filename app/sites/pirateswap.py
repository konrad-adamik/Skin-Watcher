from __future__ import annotations

import re
import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.models import SkinMatch, SkinRule
from app.cs2_resources.rules import is_glove, is_knife, stattrak_matches
from app.utils.text import (
    clean_display_text,
    full_skin_name,
    normalize_match_text,
    normalize_message_text,
    normalize_text,
    skin_name_part,
)
from app.utils.time_utils import timestamp


def find_search_box(page):
    candidates = [
        page.locator("input[data-testid='search-autocomplete-input']").first,
        page.locator("input[placeholder='Search']").first,
        page.locator("input[placeholder='SEARCH']").first,
        page.get_by_placeholder(re.compile("^search$", re.I)),
        page.locator("input[type='search']"),
        page.get_by_role("textbox"),
    ]

    for locator in candidates:
        try:
            count = min(locator.count(), 8)
            for index in range(count):
                item = locator.nth(index)
                if item.is_visible() and item.is_enabled():
                    return item
        except PlaywrightError:
            continue

    raise RuntimeError("Could not find a visible search input on the page.")


def expected_option_text(rule: SkinRule) -> str:
    name = full_skin_name(rule)
    if is_glove(rule):
        return name
    if is_knife(rule):
        return f"StatTrak {name}" if rule.stattrak else name
    return f"StatTrak {name}" if rule.stattrak else name


def search_query_for(rule: SkinRule) -> str:
    if rule.query:
        return rule.query

    return skin_name_part(rule) or full_skin_name(rule)


def select_autocomplete_option(page, rule: SkinRule) -> str:
    expected = normalize_match_text(expected_option_text(rule))
    search_term = skin_name_part(rule)
    options = page.locator("li").filter(has_text=re.compile(re.escape(search_term), re.I))
    seen_options: list[str] = []

    end_at = time.time() + 10
    while time.time() < end_at:
        count = options.count()
        for index in range(count):
            option = options.nth(index)
            if not option.is_visible():
                continue

            text = normalize_text(option.inner_text())
            if text not in seen_options:
                seen_options.append(text)
            normalized = normalize_match_text(text)
            if normalized == expected or option_matches_rule(rule, normalized):
                option.click()
                page.wait_for_timeout(4000)
                return text
        page.wait_for_timeout(250)

    if seen_options:
        print(f"[{timestamp()}] visible autocomplete options: {' | '.join(seen_options[:8])}")
    raise RuntimeError(f"Could not find matching autocomplete option: {expected_option_text(rule)}")


def option_matches_rule(rule: SkinRule, normalized_option: str) -> bool:
    skin = normalize_match_text(rule.skin or skin_name_part(rule))
    weapon = normalize_match_text(rule.weapon or "")
    if skin and skin not in normalized_option:
        return False
    if weapon and weapon not in normalized_option:
        return False
    if rule.stattrak and "stattrak" not in normalized_option:
        return False
    if not rule.stattrak and "stattrak" in normalized_option and not is_glove(rule):
        return False
    return True


def extract_cards(page, selected_label: str) -> list[dict]:
    cards = page.locator("[data-testid='exchanger-card']")
    try:
        cards.first.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeoutError:
        return []

    return cards.evaluate_all(
        """
        (els, selectedLabel) => {
          function compact(text) {
            return (text || "").replace(/\\s+/g, " ").trim();
          }

          return els.map((card, index) => {
            const nameNode = card.querySelector("[data-testid='skin-card-name']");
            const name = compact(nameNode?.innerText || nameNode?.textContent);
            const nameAreaText = compact(nameNode?.parentElement?.textContent);
            const cardText = compact(card.textContent || card.innerText);
            const normalizedCardText = cardText.replace(/[\\u2010-\\u2015\\u2212]/g, "-");
            const paragraphs = Array.from(card.querySelectorAll("p"))
              .map((p) => compact(p.textContent || p.innerText))
              .filter(Boolean);
            const price = paragraphs.find((text) => /^\\$/.test(text)) || "";
            const searchableText = [
              nameAreaText,
              ...paragraphs,
              normalizedCardText,
              Array.from(card.querySelectorAll("*"))
                .map((el) => compact(el.textContent))
                .filter(Boolean)
                .join(" "),
            ].join(" ").replace(/[\\u2010-\\u2015\\u2212]/g, "-");
            const floatMatch =
              searchableText.match(/\\b(FN|MW|FT|WW|BS)\\b\\s*(?:-|:)\\s*(0?\\.\\d+|1(?:\\.0+)?)/i) ||
              searchableText.match(/\\b(FN|MW|FT|WW|BS)\\b\\s+(0?\\.\\d+|1(?:\\.0+)?)/i) ||
              searchableText.match(/\\bfloat\\b\\s*(?:-|:)?\\s*\\b(FN|MW|FT|WW|BS)\\b\\s*(?:-|:)?\\s*(0?\\.\\d+|1(?:\\.0+)?)/i);
            const rawFloatMatch = searchableText.match(/\\bfloat\\b\\s*(?:-|:)?\\s*(0?\\.\\d+|1(?:\\.0+)?)/i);
            const details = floatMatch
              ? `${floatMatch[1].toUpperCase()} - ${floatMatch[2]}`
              : rawFloatMatch
                ? rawFloatMatch[1]
                : "";
            const lock = paragraphs.find((text) => /^\\d+D$/.test(text)) || "";
            const image = card.querySelector("img[alt]");
            const imageAlt = image?.getAttribute("alt") || "";
            const imageSrc = image?.currentSrc || image?.getAttribute("src") || "";
            const imageUrl = imageSrc ? new URL(imageSrc, window.location.origin).href : "";
            const debugText = !details ? normalizedCardText.slice(0, 180) : "";

            if (!name && !price && !details) return "";
            return {
              text: `${selectedLabel}\\n### Float: ${details || "no float"}`,
              identity_text: `${selectedLabel} | card=${index + 1} | lock=${lock || "no lock"} | float=${details || "no float"} | price=${price || "no price"} | image=${imageAlt}${debugText ? ` | raw=${debugText}` : ""}`,
              image_url: imageUrl,
              debug: {
                index: index + 1,
                name,
                details: details || "no float",
                price: price || "no price",
                text: normalizedCardText.slice(0, 220),
              },
            };
          }).filter(Boolean);
        }
        """,
        selected_label,
    )


def search_for_skin(page, rule: SkinRule) -> list[SkinMatch]:
    query = search_query_for(rule)
    print(f"[{timestamp()}] searching {full_skin_name(rule)} with query: {query}")
    search_box = find_search_box(page)
    search_box.click()
    search_box.press("Control+A")
    search_box.press("Backspace")
    search_box.type(query, delay=35)
    page.wait_for_timeout(1000)

    selected_label = select_autocomplete_option(page, rule)
    print(f"[{timestamp()}] selected PirateSwap option: {selected_label}")
    clean_label = clean_display_text(selected_label)
    cards = extract_cards(page, clean_label)
    print(f"[{timestamp()}] extracted {len(cards)} card(s) for {clean_label}")
    for card in cards:
        debug = card.get("debug", {})
        print(
            f"[{timestamp()}] card {debug.get('index')}: "
            f"name={debug.get('name') or 'unknown'} | "
            f"float={debug.get('details')} | "
            f"price={debug.get('price')}"
        )
        if debug.get("details") == "no float":
            print(f"[{timestamp()}] card {debug.get('index')} raw text: {debug.get('text')}")

    return [
        SkinMatch(
            text=normalize_message_text(card["text"]),
            identity_text=normalize_text(card["identity_text"]),
            image_url=card.get("image_url"),
        )
        for card in cards
        if stattrak_matches(rule, selected_label)
    ]
