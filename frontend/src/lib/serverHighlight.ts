/** Interpret only the server's em delimiters. Every other character stays React text. */
export function serverHighlightParts(value: string): {text: string; match: boolean}[] {
  let match = false;
  const entities: Record<string,string> = {amp:"&", lt:"<", gt:">", quot:'"', apos:"'", "#39":"'"};
  return value.split(/(<\/?em>)/g).flatMap(part => {
    if (part === "<em>") { match = true; return []; }
    if (part === "</em>") { match = false; return []; }
    return [{text: part.replace(/&(amp|lt|gt|quot|apos|#39);/g, (_, entity: string) => entities[entity]), match}];
  });
}
