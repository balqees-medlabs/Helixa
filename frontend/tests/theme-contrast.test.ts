import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * WCAG-AA contrast verification for the Medlabs palette (SC-007 / quickstart 8).
 *
 * Parses the `:root` HSL tokens from styles/globals.css and checks the pairs
 * the app actually renders: body/secondary/brand text, solid button labels,
 * status text on its tinted chip background (bg-success/10 + text-success), and the focus
 * ring (non-text, 3:1). Fails the suite if a token edit breaks AA.
 */

const CSS_PATH = path.join(process.cwd(), "styles", "globals.css");

type Rgb = readonly [number, number, number];

function parseTokens(css: string): Record<string, [number, number, number]> {
  const tokens: Record<string, [number, number, number]> = {};
  const pattern = /--([a-z-]+):\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%;/g;
  for (const match of css.matchAll(pattern)) {
    tokens[match[1]] = [Number(match[2]), Number(match[3]), Number(match[4])];
  }
  return tokens;
}

function hslToRgb([h, s, l]: [number, number, number]): Rgb {
  const sat = s / 100;
  const light = l / 100;
  const a = sat * Math.min(light, 1 - light);
  const channel = (n: number): number => {
    const k = (n + h / 30) % 12;
    return light - a * Math.max(-1, Math.min(k - 3, Math.min(9 - k, 1)));
  };
  return [channel(0), channel(8), channel(4)];
}

function relativeLuminance(rgb: Rgb): number {
  const linear = rgb.map((value) =>
    value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4),
  );
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** `alpha` of `token` composited over `base` (Tailwind's `bg-token/alpha`). */
function tint(color: Rgb, alpha: number, base: Rgb): Rgb {
  return [
    alpha * color[0] + (1 - alpha) * base[0],
    alpha * color[1] + (1 - alpha) * base[1],
    alpha * color[2] + (1 - alpha) * base[2],
  ];
}

const css = readFileSync(CSS_PATH, "utf8");
const token = parseTokens(css);
const rgb = (name: string): Rgb => {
  const hsl = token[name];
  if (!hsl) {
    throw new Error(`Missing --${name} token in ${CSS_PATH}`);
  }
  return hslToRgb(hsl);
};

const TEXT_MIN = 4.5;
const UI_MIN = 3;

describe("Medlabs palette meets WCAG-AA (SC-007)", () => {
  const background = rgb("background");

  it("parses the theme tokens from globals.css", () => {
    for (const name of [
      "background",
      "foreground",
      "card",
      "muted",
      "muted-foreground",
      "secondary",
      "secondary-foreground",
      "primary",
      "primary-foreground",
      "accent",
      "accent-foreground",
      "destructive",
      "success",
      "warning",
      "brand",
      "ring",
    ]) {
      expect(token[name], `--${name}`).toBeDefined();
    }
  });

  const textPairs: Array<[string, string]> = [
    // Body and secondary text on page surfaces.
    ["foreground", "background"],
    ["foreground", "card"],
    ["foreground", "muted"],
    ["foreground", "secondary"],
    ["muted-foreground", "background"],
    ["muted-foreground", "card"],
    ["muted-foreground", "muted"],
    ["muted-foreground", "secondary"],
    // Brand accents used as text (nav logo, stage badges).
    ["brand", "background"],
    ["brand", "card"],
    // Chip foreground/background pairs (StageBadge, status chips).
    ["secondary-foreground", "secondary"],
    ["accent-foreground", "accent"],
    // Status text on white (text-destructive/success/warning).
    ["destructive", "background"],
    ["success", "background"],
    ["warning", "background"],
  ];

  for (const [fg, bg] of textPairs) {
    it(`--${fg} text on --${bg} ≥ ${TEXT_MIN}:1`, () => {
      expect(contrast(rgb(fg), rgb(bg))).toBeGreaterThanOrEqual(TEXT_MIN);
    });
  }

  const tintedStatus: Array<[string, number]> = [
    // Real usage: bg-*/10 and bg-*/5 chips/callouts with text-*.
    ["destructive", 0.1],
    ["destructive", 0.05],
    ["success", 0.1],
    ["success", 0.05],
    ["warning", 0.1],
    ["warning", 0.05],
  ];

  for (const [name, alpha] of tintedStatus) {
    it(`--${name} text on its ${Math.round(alpha * 100)}% tint over the page ≥ ${TEXT_MIN}:1`, () => {
      expect(contrast(rgb(name), tint(rgb(name), alpha, background))).toBeGreaterThanOrEqual(
        TEXT_MIN,
      );
    });
  }

  const solidLabels: Array<[string, string]> = [
    // SubmitButton primary, destructive buttons/chips with their foreground.
    ["primary-foreground", "primary"],
    ["destructive-foreground", "destructive"],
    ["success-foreground", "success"],
    ["warning-foreground", "warning"],
  ];

  for (const [fg, bg] of solidLabels) {
    it(`--${fg} label on solid --${bg} ≥ ${TEXT_MIN}:1`, () => {
      expect(contrast(rgb(fg), rgb(bg))).toBeGreaterThanOrEqual(TEXT_MIN);
    });
  }

  it(`focus ring on page/card surfaces ≥ ${UI_MIN}:1 (non-text)`, () => {
    expect(contrast(rgb("ring"), background)).toBeGreaterThanOrEqual(UI_MIN);
    expect(contrast(rgb("ring"), rgb("card"))).toBeGreaterThanOrEqual(UI_MIN);
  });
});
