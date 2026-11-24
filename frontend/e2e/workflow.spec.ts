import { expect, test } from "./fixtures";

test("registers a sample, completes consent, and advances to molecular", async ({
  authenticatedPage: page,
}) => {
  const caseId = `E2E-FLOW-${Date.now()}`;

  await page.goto("/samples/register");
  await page.getByLabel("Case identifier").fill(caseId);
  await page.getByRole("button", { name: "Register sample" }).click();

  await expect(page).toHaveURL(/\/samples\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: caseId })).toBeVisible();
  await expect(page.getByText("Sample received").first()).toBeVisible();

  for (const item of ["Signed consent", "Id verified", "Requisition received"]) {
    await page.getByLabel(item, { exact: false }).check();
  }
  await page.getByRole("button", { name: "Save consent" }).click();
  await expect(page.getByText("Molecular gate open")).toBeVisible();

  await page.getByRole("button", { name: "Advance sample" }).click();
  await expect(page.getByText("Consent & documentation").first()).toBeVisible();

  await page.getByRole("button", { name: "Advance sample" }).click();
  await expect(page.getByText("Molecular processing").first()).toBeVisible();
});
