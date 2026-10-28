import type { SearchField } from "../types";

const STOP_WORDS = new Set("a an and are as at be by for from in is it of on or that the this to was were with".split(" "));

export function isExactTitleQuery(title: string, query: string): boolean {
  const normalize=(value:string)=>value.trim().replace(/\s+/gu," ").toLocaleLowerCase();
  return Boolean(normalize(query)) && normalize(query)===normalize(title);
}

export function resultHighlightScope(title: string, query: string, field: SearchField = "all"): SearchField {
  return field==="all"&&isExactTitleQuery(title,query)?"title":field;
}

/** HTML-like input stays safe React text, never executable markup. */
export function safePlainText(value: string): string {
  return value.replace(/<[^>]*>/g, "");
}

export function highlightParts(value: string, query: string): { text: string; match: boolean }[] {
  const plain = safePlainText(value);
  const words = [...new Set(query.trim().split(/\s+/u).map(term => term.replace(/^["'.,:;!?()]+|["'.,:;!?()]+$/gu, "")).filter(Boolean))];
  const meaningful = words.filter(term => !STOP_WORDS.has(term.toLocaleLowerCase()));
  const terms = (meaningful.length ? meaningful : words).sort((a, b) => b.length - a.length);
  if (!terms.length) return [{ text: plain, match: false }];
  const escaped = terms.map(term => {
    const literal = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    // Latin words match whole words; CJK queries may match within unspaced text.
    return /^[\x00-\x7f]+$/u.test(term) && /[a-z0-9]/iu.test(term)
      ? "(?<![\\p{L}\\p{N}_])" + literal + "(?![\\p{L}\\p{N}_])" : literal;
  });
  const expression = new RegExp(escaped.join("|"), "giu");
  const parts: { text: string; match: boolean }[] = [];
  let offset = 0;
  for (const match of plain.matchAll(expression)) {
    const index = match.index!;
    if (index > offset) parts.push({ text: plain.slice(offset, index), match: false });
    parts.push({ text: match[0], match: true });
    offset = index + match[0].length;
  }
  if (offset < plain.length) parts.push({ text: plain.slice(offset), match: false });
  return parts;
}
