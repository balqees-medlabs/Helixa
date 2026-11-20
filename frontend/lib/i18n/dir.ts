export type Direction = "ltr" | "rtl";

export const DEFAULT_LOCALE = "en";

const RTL_LANGUAGES = new Set(["ar", "fa", "he", "ur"]);

export function getLocale(): string {
  return process.env.NEXT_PUBLIC_LOCALE?.trim() || DEFAULT_LOCALE;
}

export function directionForLocale(locale: string): Direction {
  const language = locale.split("-")[0]?.toLowerCase() ?? DEFAULT_LOCALE;
  return RTL_LANGUAGES.has(language) ? "rtl" : "ltr";
}

export function getDirection(): Direction {
  return directionForLocale(getLocale());
}

function labelWord(word: string, index: number): string {
  if (/^[A-Z0-9]{2,}$/.test(word)) {
    return word;
  }
  const lower = word.toLowerCase();
  return index === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
}

/** Turn API slugs/enums into sentence-case UI labels ("signed_consent" → "Signed consent"). */
export function sentenceCase(value: string): string {
  const words = value.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim().split(" ").filter(Boolean);

  return words.map(labelWord).join(" ");
}

/** Alias used by table/badge renderers for enum-valued fields. */
export const formatLabel = sentenceCase;
