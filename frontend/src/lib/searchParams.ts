import { FIELD_OPTIONS } from "../types.ts";
import type { SearchField, SearchMode } from "../types";

// API search windows are limited to 10,000 records; the UI uses six per page.
export function normalizeSearchPage(value: string | null): number {
  const number = Number(value);
  return Number.isSafeInteger(number) && number >= 1 && number <= 1666 ? number : 1;
}

export function normalizeSearchField(value: string | null, mode: SearchMode): SearchField {
  if (!FIELD_OPTIONS.some(item => item.value === value)) return "all";
  if (mode === "semantic" && !["all", "title", "fulltext"].includes(value!)) return "all";
  return value as SearchField;
}
