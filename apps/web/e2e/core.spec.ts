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
});
