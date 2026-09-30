// Regression suite for search/index.html. Run with:
//   node --test tests/
//
// Requires the page to be served over http(s) already (fetch() of
// versions/*.txt is blocked on file://) — e.g. from the search/ directory:
//   python3 -m http.server 8935
// Override the URL with SEARCH_URL if it's served elsewhere.

import { test } from "node:test";
import assert from "node:assert/strict";
import { withPage } from "./cdp.mjs";

const URL = process.env.SEARCH_URL || "http://localhost:8935/index.html";

async function freshSearch(page, { adjacent, wholeWords, caseSensitive, words }) {
  return page.eval(`
    (function() {
      document.getElementById('adjacent').checked = ${!!adjacent};
      document.getElementById('wholeWords').checked = ${!!wholeWords};
      document.getElementById('caseSensitive').checked = ${!!caseSensitive};
      document.getElementById('words').value = ${JSON.stringify(words)};
      search();
    })()
  `, false);
}

test("basic search returns results and no console/page errors", async () => {
  await withPage(URL, async (page) => {
    await page.sleep(1000); // initial NASB load
    await freshSearch(page, { wholeWords: true, words: "love" });
    await page.sleep(300);
    const title = await page.eval(`document.getElementById('resultsTitle').textContent`);
    assert.match(title, /^\d+ results? for "love" in NASB$/);
    assert.deepEqual(page.consoleErrors, []);
    assert.deepEqual(page.pageErrors, []);
  });
});

test("Exact Phrase highlights the whole matched phrase as one span, not disjoint words", async () => {
  await withPage(URL, async (page) => {
    await page.sleep(1000);
    await freshSearch(page, { adjacent: true, wholeWords: true, words: "god so loved" });
    await page.sleep(300);
    const marks = await page.eval(`Array.from(document.querySelectorAll('.result mark')).map(m => m.textContent)`);
    assert.ok(marks.length > 0, "expected at least one highlighted match");
    for (const m of marks) {
      // every mark should be the full 3-word phrase, never a lone word
      assert.match(m.toLowerCase(), /^god\s+so\s+loved$/);
    }
  });
});

test("non-adjacent (default) search still highlights each matched word individually", async () => {
  await withPage(URL, async (page) => {
    await page.sleep(1000);
    await freshSearch(page, { adjacent: false, wholeWords: true, words: "god loved" });
    await page.sleep(300);
    const marks = await page.eval(`Array.from(document.querySelectorAll('.result mark')).map(m => m.textContent.toLowerCase())`);
    assert.ok(marks.includes("god") || marks.includes("loved"), "expected individual-word marks, not a joined phrase");
  });
});

test("Whole Words excludes superset matches (e.g. 'man' does not highlight inside 'mankind')", async () => {
  await withPage(URL, async (page) => {
    await page.sleep(1000);
    await freshSearch(page, { wholeWords: true, words: "man" });
    await page.sleep(300);
    const wrongMarks = await page.eval(`
      Array.from(document.querySelectorAll('.result mark')).filter(m => m.textContent.toLowerCase() !== 'man').length
    `);
    assert.equal(wrongMarks, 0);
  });
});

test("Match Capitals (case-sensitive) excludes different-case matches", async () => {
  await withPage(URL, async (page) => {
    await page.sleep(1000);
    await freshSearch(page, { wholeWords: true, caseSensitive: true, words: "Faith" });
    await page.sleep(300);
    const marks = await page.eval(`Array.from(document.querySelectorAll('.result mark')).map(m => m.textContent)`);
    for (const m of marks) {
      assert.ok(m === "Faith" || m === "FAITH", `unexpected case-insensitive match: "${m}"`);
    }
  });
});

test("search-as-you-type is debounced (rapid keystrokes collapse to one actual search)", async () => {
  await withPage(URL, async (page) => {
    await page.sleep(1000);
    const result = await page.eval(`
      (async function() {
        let count = 0;
        const original = window.search;
        window.search = function(...a) { count++; return original.apply(this, a); };
        const input = document.getElementById('words');
        input.value = '';
        for (const ch of 'light') {
          input.value += ch;
          input.dispatchEvent(new Event('input', { bubbles: true }));
          await new Promise(r => setTimeout(r, 30));
        }
        await new Promise(r => setTimeout(r, 300));
        window.search = original;
        return count;
      })()
    `);
    assert.equal(result, 1, "5 rapid keystrokes should collapse into exactly 1 search() call");
  });
});

test("filter by testament narrows results, Clear All restores them, button disables/enables correctly", async () => {
  await withPage(URL, async (page) => {
    await page.sleep(1000);
    await freshSearch(page, { wholeWords: true, words: "love" });
    await page.sleep(300);
    const r = await page.eval(`
      (function() {
        const totalTitle = document.getElementById('resultsTitle').textContent;
        const clearDisabledBefore = document.querySelector('.clear-all').disabled;
        const otItem = Array.from(document.querySelectorAll('.filter-item')).find(d => d.textContent.startsWith('Old Testament'));
        otItem.click();
        const filteredTitle = document.getElementById('resultsTitle').textContent;
        const clearDisabledAfterFilter = document.querySelector('.clear-all').disabled;
        document.querySelector('.clear-all').click();
        const restoredTitle = document.getElementById('resultsTitle').textContent;
        const clearDisabledAfterClear = document.querySelector('.clear-all').disabled;
        return { totalTitle, clearDisabledBefore, filteredTitle, clearDisabledAfterFilter, restoredTitle, clearDisabledAfterClear };
      })()
    `);
    assert.equal(r.clearDisabledBefore, true);
    assert.equal(r.clearDisabledAfterFilter, false);
    assert.equal(r.clearDisabledAfterClear, true);
    assert.equal(r.totalTitle, r.restoredTitle, "clearing the filter should restore the original total");
    assert.notEqual(r.totalTitle, r.filteredTitle, "filtering by testament should change the displayed count");
  });
});

test("filter items are keyboard-accessible (focusable, Enter activates)", async () => {
  await withPage(URL, async (page) => {
    await page.sleep(1000);
    await freshSearch(page, { wholeWords: true, words: "god" });
    await page.sleep(300);
    const r = await page.eval(`
      (function() {
        const item = document.querySelector('.filter-item[role="button"]');
        item.focus();
        const focused = document.activeElement === item;
        const activeBefore = item.classList.contains('active');
        item.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        const activeAfter = document.querySelector('.filter-item.active') !== null;
        return { focused, activeBefore, activeAfter };
      })()
    `);
    assert.equal(r.focused, true);
    assert.equal(r.activeBefore, false);
    assert.equal(r.activeAfter, true);
  });
});

test("pagination changes visible results and restores on Prev; filter sidebar DOM is reused, not rebuilt", async () => {
  await withPage(URL, async (page) => {
    await page.sleep(1000);
    await freshSearch(page, { wholeWords: true, words: "the" });
    await page.sleep(300);
    const r = await page.eval(`
      (function() {
        document.getElementById('perPage').value = '25';
        document.getElementById('perPage').dispatchEvent(new Event('change'));
        const firstItem = document.querySelector('.filter-item');
        firstItem.__marker = "tag";
        const page1Ref = document.querySelector('.result .ref')?.textContent;
        const nextBtn = Array.from(document.querySelectorAll('#pager button')).find(b => b.textContent.includes('Next'));
        nextBtn.click();
        const page2Ref = document.querySelector('.result .ref')?.textContent;
        const filterItemReused = document.querySelector('.filter-item').__marker === "tag";
        const prevBtn = Array.from(document.querySelectorAll('#pager button')).find(b => b.textContent.includes('Prev'));
        prevBtn.click();
        const page1RefAgain = document.querySelector('.result .ref')?.textContent;
        return { page1Ref, page2Ref, filterItemReused, page1RefAgain };
      })()
    `);
    assert.notEqual(r.page1Ref, r.page2Ref);
    assert.equal(r.page1Ref, r.page1RefAgain);
    assert.equal(r.filterItemReused, true, "filter sidebar should not be rebuilt on a pagination-only change");
  });
});

test("no results shows a message and hides the layout", async () => {
  await withPage(URL, async (page) => {
    await page.sleep(1000);
    await freshSearch(page, { words: "zzzznonexistentwordzzzz" });
    await page.sleep(300);
    const r = await page.eval(`
      ({ countText: document.getElementById('count').textContent, layoutHidden: document.getElementById('layout').classList.contains('empty') })
    `);
    assert.match(r.countText, /No results for/);
    assert.equal(r.layoutHidden, true);
  });
});

test("switching Bible version shows a loading message, then resolves to the new version's results", async () => {
  await withPage(URL, async (page) => {
    await page.sleep(1000);
    await freshSearch(page, { wholeWords: true, words: "faith" });
    await page.sleep(300);
    const r = await page.eval(`
      (async function() {
        const sel = document.getElementById('version');
        sel.value = 'Living';
        sel.dispatchEvent(new Event('change'));
        const loadingText = document.getElementById('count').textContent;
        await new Promise(res => setTimeout(res, 500));
        const afterText = document.getElementById('resultsTitle').textContent;
        return { loadingText, afterText };
      })()
    `);
    assert.match(r.loadingText, /^Loading Living/);
    assert.match(r.afterText, /in TLB$/);
  });
});
