// In real browsers (Chromium and WebKit, Safari's engine), against a running server:
//   MONITOR_BASE=http://localhost:3000 PLAYWRIGHT_DIR=/path/to/node_modules/playwright node --test tests/monitor/rows.e2e.test.ts
// Clicking outside the table, on the nav, or on another row must not open the last row's dossier.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const base = process.env.MONITOR_BASE;
const dir = process.env.PLAYWRIGHT_DIR;
const skip = !base || !dir ? "set MONITOR_BASE and PLAYWRIGHT_DIR to run" : false;

for (const engine of ["chromium", "webkit"] as const) {
  test(`candidates: clicks land where they are made (${engine})`, { skip }, async () => {
    const pw = createRequire(import.meta.url)(dir!);
    const browser = await pw[engine].launch();
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    // Click where a person would: at the element's position, on whatever is on top there (no actionability
    // checks), so a covering overlay gets the click exactly as it would for a real user.
    const clickAt = async (loc: { boundingBox: () => Promise<{ x: number; y: number; width: number; height: number } | null> }) => {
      const b = await loc.boundingBox();
      assert.ok(b, "element is on screen");
      await page.mouse.click(b.x + Math.min(8, b.width / 2), b.y + Math.min(8, b.height / 2));
    };
    const open = async () => {
      await page.goto(`${base}/candidates`, { waitUntil: "networkidle" });
      await page.locator("tbody tr").first().waitFor();
    };
    try {
      await open();
      const rows = page.locator("tbody tr");
      const hrefs: string[] = await rows.evaluateAll((trs: Element[]) => trs.map((t) => t.querySelector("a")?.getAttribute("href") ?? ""));
      const last = hrefs[hrefs.length - 1];
      assert.ok(hrefs.length >= 2 && last);

      // outside the table: the page head, the funnel, the empty space below the table
      for (const sel of ["h1", "ol[class*=funnelRow] li", "[class*=afterRow]"]) {
        await clickAt(page.locator(sel).first());
        await page.waitForTimeout(400);
        assert.equal(new URL(page.url()).pathname, "/candidates", `click on ${sel} stayed on /candidates`);
      }
      await page.mouse.click(1400, 880);
      await page.waitForTimeout(400);
      assert.equal(new URL(page.url()).pathname, "/candidates", "click on bare page stayed");

      // the nav goes where it says
      await clickAt(page.getByRole("link", { name: "Log" }));
      await page.waitForTimeout(800);
      assert.equal(new URL(page.url()).pathname, "/log");

      // another row opens its own dossier, not the last one's
      await open();
      await clickAt(rows.first().locator("td").nth(2));
      await page.waitForTimeout(800);
      assert.equal(new URL(page.url()).pathname, hrefs[0]);
      assert.notEqual(hrefs[0], last);

      // the last row itself still works
      await open();
      await clickAt(rows.last().locator("td").nth(1));
      await page.waitForTimeout(800);
      assert.equal(new URL(page.url()).pathname, last);
    } finally {
      await browser.close();
    }
  });
}
