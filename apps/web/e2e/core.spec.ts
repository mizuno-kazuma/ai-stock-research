import { expect, test } from "@playwright/test";

test.describe("主要フロー", () => {
  test("推奨カードに弱気論拠が常に可視", async ({ page }) => {
    await page.goto("/recommendations");
    const heading = page.getByRole("heading", { name: "弱気の論拠" }).first();
    await expect(heading).toBeVisible();
    const panel = page.locator(".argument-panel--bear").first();
    await expect(panel).toBeVisible();
    await expect(panel).not.toHaveText(/^$/);
    await expect(page.getByRole("button", { name: /もっと見る|開く|折りたた/ })).toHaveCount(0);
  });

  test("方向色を米国式に切り替えると上昇が緑になる", async ({ page }) => {
    await page.goto("/settings");
    await page.getByRole("button", { name: /米国式/ }).click();
    await expect(page.locator("html")).toHaveAttribute("data-direction-colors", "us");
    const preview = page.getByTestId("direction-preview").first().locator(".text-dir-up").first();
    await expect(preview).toBeVisible();
    const color = await preview.evaluate((el) => getComputedStyle(el).color);
    expect(color).toMatch(/63,\s*191,\s*127|rgb\(63,\s*191,\s*127\)/);
  });

  test("エージェントの実行履歴をクリアできる", async ({ page }) => {
    await page.goto("/agent");
    await expect(page.getByRole("heading", { name: "実行履歴" })).toBeVisible();
    const history = page.getByRole("list", { name: "実行履歴" });
    await expect(history).toBeVisible();
    await page.getByRole("button", { name: "クリア" }).click();
    await page.getByRole("button", { name: "削除する" }).click();
    await expect(page.getByText("ジョブの実行履歴がありません")).toBeVisible();
  });

  test("部分データ時にセクション単位の警告が出て他は表示される", async ({ page }) => {
    await page.goto("/recommendations?mock_state=partial");
    await expect(page.getByText("資料読解が3件スキップされました")).toBeVisible();
    await expect(page.getByRole("heading", { name: "弱気の論拠" }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "推奨銘柄" })).toBeVisible();
  });

  test("決算資料の開示一覧に会社名が出る", async ({ page }) => {
    await page.goto("/filings");
    await expect(page.getByRole("heading", { name: "決算資料" })).toBeVisible();
    await expect(page.getByRole("link", { name: /7203.*トヨタ自動車/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /6758.*ソニーグループ/ })).toBeVisible();
  });

  test("スクロールしてもヘッダーと左ペインが残る", async ({ page }) => {
    await page.goto("/screener");
    const header = page.locator("header.app-header");
    const sidebar = page.getByRole("navigation", { name: "メインナビゲーション" });
    await expect(header).toBeVisible();
    await expect(sidebar).toBeVisible();
    const headerBefore = await header.boundingBox();
    const sidebarBefore = await sidebar.boundingBox();
    expect(headerBefore).not.toBeNull();
    expect(sidebarBefore).not.toBeNull();

    await page.locator("#main").evaluate((el) => {
      el.scrollTop = el.scrollHeight;
    });
    await page.evaluate(() => window.scrollTo(0, 2000));

    await expect(header).toBeInViewport();
    await expect(sidebar).toBeInViewport();
    const headerAfter = await header.boundingBox();
    const sidebarAfter = await sidebar.boundingBox();
    expect(headerAfter?.y).toBe(headerBefore?.y);
    expect(sidebarAfter?.x).toBe(sidebarBefore?.x);
  });
});
