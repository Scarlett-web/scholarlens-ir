import { readLocal, writeLocal } from "./storage.ts";

export interface ReadingPosition {
  ratio: number;
  expanded: boolean;
  textLength: number;
  savedAt: string;
}

const keyFor = (userId: number | undefined) => "reading-positions:" + (userId === undefined ? "guest" : "user-" + userId);

function positions(userId: number | undefined): Record<string, ReadingPosition> {
  const raw: unknown = readLocal(keyFor(userId), {});
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const entries = Object.entries(raw).filter((entry): entry is [string, ReadingPosition] => {
    const value = entry[1];
    return value && typeof value === "object" && typeof value.ratio === "number" && Number.isFinite(value.ratio)
      && value.ratio >= 0 && value.ratio <= 1 && typeof value.expanded === "boolean"
      && Number.isSafeInteger(value.textLength) && value.textLength >= 0
      && typeof value.savedAt === "string" && Number.isFinite(Date.parse(value.savedAt));
  }).sort((a, b) => Date.parse(b[1].savedAt) - Date.parse(a[1].savedAt)).slice(0, 100);
  return Object.fromEntries(entries);
}

export function loadReadingPosition(userId: number | undefined, paperId: string, textLength?: number): ReadingPosition | null {
  const entry = positions(userId)[paperId];
  return entry && (textLength === undefined || entry.textLength === textLength) ? entry : null;
}

export function saveReadingPosition(userId: number | undefined, paperId: string, value: ReadingPosition): boolean {
  const entries = positions(userId);
  const next = Object.fromEntries([[paperId, value], ...Object.entries(entries).filter(([id]) => id !== paperId)].slice(0, 100));
  return writeLocal(keyFor(userId), next);
}
