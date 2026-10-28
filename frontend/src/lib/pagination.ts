export type PaginationItem = number | "gap-left" | "gap-right";

/** Bounded page window, with explicit gaps and enough nearby pages at both ends. */
export function paginationItems(current: number, total: number): PaginationItem[] {
  const last = Math.max(1, Math.floor(total));
  const page = Math.min(last, Math.max(1, Math.floor(current)));
  if (last <= 7) return Array.from({ length: last }, (_, i) => i + 1);
  const start = page <= 4 ? 1 : page >= last - 3 ? last - 4 : page - 1;
  const end = page <= 4 ? 5 : page >= last - 3 ? last : page + 1;
  const visible = [...new Set([1, ...Array.from({ length: end - start + 1 }, (_, i) => start + i), last])];
  const items: PaginationItem[] = [];
  for (const n of visible) {
    const previous = items.at(-1);
    if (typeof previous === "number" && n - previous === 2) items.push(previous + 1);
    else if (typeof previous === "number" && n - previous > 2) items.push(previous === 1 ? "gap-left" : "gap-right");
    items.push(n);
  }
  return items;
}
