const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

const baseUrl = process.env.CARBONLAB_DEMO_URL || "http://127.0.0.1:5174";
const password = process.env.CARBONLAB_DEMO_PASSWORD;
if (!password) throw new Error("CARBONLAB_DEMO_PASSWORD is required");

const outputDir = path.resolve(__dirname, "raw");
fs.mkdirSync(outputDir, { recursive: true });

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: chromium.executablePath(),
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: outputDir, size: { width: 1440, height: 900 } },
    colorScheme: "light",
  });
  const page = await context.newPage();

  await page.goto(`${baseUrl}/login`, { waitUntil: "networkidle" });
  await pause(1500);
  const inputs = page.locator("input");
  await inputs.nth(0).fill("demo@huasheng-steel.com");
  await pause(500);
  await inputs.nth(1).fill(password);
  await pause(800);
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL("**/upload");
  await page.waitForLoadState("networkidle");
  await pause(2500);

  await page.getByText("用电量", { exact: true }).hover();
  await pause(900);
  await page.getByText("期间", { exact: true }).hover();
  await pause(900);
  await page.getByText("所属设施", { exact: true }).hover();
  await pause(1500);

  await page.getByRole("button", { name: "锁定候选并确认写入" }).click();
  await page.getByText("确认指纹：").waitFor({ state: "visible" });
  await pause(3500);
  await page.getByText("已计算 ·", { exact: false }).hover();
  await pause(1800);

  await page.getByRole("link", { name: "进入护照归集" }).click();
  await page.waitForURL("**/passports?**");
  await page.getByText("数据已从收件箱带入。", { exact: false }).waitFor({ state: "visible" });
  await pause(3000);

  const incoming = page.getByText("刚刚确认的数据 · 请核对后归集");
  await incoming.scrollIntoViewIfNeeded();
  await incoming.hover();
  await pause(2500);
  const card = incoming.locator("../..");
  await card.getByRole("button", { name: "100% 归集到本工序" }).click();
  await page.getByText("活动排放已完整归集到当前工序。").waitFor({ state: "visible" });
  await pause(3500);
  await page.getByText("已归集", { exact: true }).hover();
  await pause(2500);

  await page.close();
  await context.close();
  await browser.close();
})();
