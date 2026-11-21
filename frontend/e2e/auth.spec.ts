import { accountFor, expect, test } from "./fixtures";

async function signIn(
  page: import("@playwright/test").Page,
  role: "genomics" | "admin",
): Promise<void> {
  const account = accountFor(role);
  await page.goto("/login");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("signs in and lands on the role's home", async ({ page }) => {
  await signIn(page, "genomics");

  await expect(page).toHaveURL(/\/dashboard\?view=genomics$/);
  await expect(page.getByText("genomics E2E")).toBeVisible();
  await expect(page.getByRole("link", { name: "Register sample" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Metrics" })).toHaveCount(0);
});

test("signs out and protects routes again", async ({ page }) => {
  await signIn(page, "admin");
  await expect(page).toHaveURL(/\/dashboard/);

  await page.getByRole("button", { name: "Sign out" }).click();

  await expect(page).toHaveURL(/\/login$/);

  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login\?next=/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});
