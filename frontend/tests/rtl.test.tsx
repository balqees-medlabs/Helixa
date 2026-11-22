import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BoardPage from "@/app/(app)/board/page";
import LoginPage from "@/app/(auth)/login/page";
import { RoleNav } from "@/components/RoleNav";
import { directionForLocale, getDirection, getLocale } from "@/lib/i18n/dir";

import { resetTestSession, seedSample, signInAs } from "./msw/handlers";
import { renderWithAuth } from "./render";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

/**
 * Physical (direction-locked) utility tokens. The app must use logical
 * utilities only (ms/me/ps/pe/start/end) so `dir="rtl"` mirrors nav, board,
 * and forms without per-layout overrides (SC-007 / quickstart 8).
 */
const PHYSICAL_PREFIXES = [
  "ml-",
  "mr-",
  "pl-",
  "pr-",
  "left-",
  "right-",
  "inset-left-",
  "inset-right-",
  "border-l-",
  "border-r-",
  "rounded-l-",
  "rounded-r-",
  "rounded-tl-",
  "rounded-tr-",
  "rounded-bl-",
  "rounded-br-",
  "scroll-ml-",
  "scroll-mr-",
  "scroll-pl-",
  "scroll-pr-",
  "float-left-",
  "float-right-",
  "-ml-",
  "-mr-",
  "-pl-",
  "-pr-",
  "-left-",
  "-right-",
];

const PHYSICAL_EXACT = new Set([
  "text-left",
  "text-right",
  "float-left",
  "float-right",
  "border-l",
  "border-r",
  "rounded-l",
  "rounded-r",
  "rounded-tl",
  "rounded-tr",
  "rounded-bl",
  "rounded-br",
]);

function physicalTokens(text: string): string[] {
  const tokens = text.split(/[^\w-]+/).filter(Boolean);
  return [
    ...new Set(
      tokens.filter(
        (token) =>
          PHYSICAL_EXACT.has(token) || PHYSICAL_PREFIXES.some((prefix) => token.startsWith(prefix)),
      ),
    ),
  ];
}

const SOURCE_ROOTS = ["app", "components", "lib", "styles"];

function sourceFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      files.push(...sourceFiles(full));
    } else if (/\.(ts|tsx|css)$/.test(entry) && !full.endsWith(path.join("api", "schema.d.ts"))) {
      files.push(full);
    }
  }
  return files;
}

describe("RTL mirroring (SC-007 / quickstart 8)", () => {
  beforeEach(() => {
    resetTestSession();
  });

  it("maps locales to directions", () => {
    expect(directionForLocale("ar")).toBe("rtl");
    expect(directionForLocale("fa-IR")).toBe("rtl");
    expect(directionForLocale("en")).toBe("ltr");
    expect(directionForLocale("de-DE")).toBe("ltr");
    expect(["ltr", "rtl"]).toContain(getDirection());
    expect(directionForLocale(getLocale())).toBe(getDirection());
  });

  it("uses no physical direction utilities or CSS properties in the source", () => {
    const offenders: string[] = [];
    for (const root of SOURCE_ROOTS) {
      const dir = path.join(process.cwd(), root);
      for (const file of sourceFiles(dir)) {
        const relative = path.relative(process.cwd(), file);
        const content = readFileSync(file, "utf8");
        if (file.endsWith(".css")) {
          const physicalCss = content.match(
            /margin-left|margin-right|padding-left|padding-right|border-left|border-right|text-align:\s*(left|right)|(?<![-\w])left:(?!=)|(?<![-\w])right:(?!=)/g,
          );
          if (physicalCss) {
            offenders.push(`${relative}: ${physicalCss.join(", ")}`);
          }
          continue;
        }
        const bad = physicalTokens(content);
        if (bad.length > 0) {
          offenders.push(`${relative}: ${bad.join(" ")}`);
        }
      }
    }
    expect(offenders, "physical direction utilities break RTL mirroring").toEqual([]);
  });

  it("renders the nav under dir=rtl with only logical classes", async () => {
    signInAs("admin");
    const { container } = renderWithAuth(
      <div dir="rtl">
        <RoleNav />
      </div>,
    );

    expect(await screen.findByRole("link", { name: "TAT board" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(collectPhysicalClasses(container)).toEqual([]);
  });

  it("renders the TAT board under dir=rtl with only logical classes", async () => {
    seedSample({ caseId: "CASE-RTL", stage: 3, receivedAt: new Date().toISOString() });
    signInAs("admin");

    const { container } = renderWithAuth(
      <div dir="rtl">
        <BoardPage />
      </div>,
    );

    expect(await screen.findByRole("article", { name: "CASE-RTL card" })).toBeInTheDocument();
    expect(collectPhysicalClasses(container)).toEqual([]);
  });

  it("renders the sign-in form under dir=rtl with only logical classes", async () => {
    const { container } = renderWithAuth(
      <div dir="rtl">
        <LoginPage />
      </div>,
    );

    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(collectPhysicalClasses(container)).toEqual([]);
  });
});

function collectPhysicalClasses(container: HTMLElement): string[] {
  const offenders: string[] = [];
  for (const element of Array.from(container.querySelectorAll<HTMLElement>("*"))) {
    const bad = physicalTokens(element.className);
    if (bad.length > 0) {
      offenders.push(`<${element.tagName.toLowerCase()}> ${bad.join(" ")}`);
    }
  }
  return offenders;
}
