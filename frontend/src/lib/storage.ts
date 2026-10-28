export function readLocal<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem("scholarlens-v1:" + key);
    return raw ? JSON.parse(raw) as T : fallback;
  } catch {
    return fallback;
  }
}

export function writeLocal<T>(key: string, value: T): boolean {
  try {
    window.localStorage.setItem("scholarlens-v1:" + key, JSON.stringify(value));
    return true;
  } catch {
    // React state still works, but users must be told persistence has failed.
    return false;
  }
}

export function downloadJson(filename: string, value: unknown): void {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
