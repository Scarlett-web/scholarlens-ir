/**
 * Browser-only PDF persistence. No file bytes or private user data reach our server.
 * The browser may clear IndexedDB under storage pressure; this is NOT durable backup.
 */
const DATABASE = "scholarlens-pdf-workbench";
const STORE = "pdfFiles";

function dbOpen(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!("indexedDB" in window)) {
      reject(new Error("当前浏览器不支持本地 PDF 存储"));
      return;
    }
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("无法打开本地文件存储"));
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  action: (store: IDBObjectStore, resolve: (v: T) => void, reject: (error: Error) => void) => void
): Promise<T> {
  const db = await dbOpen();
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    const done = (value: T) => { if (!settled) { settled = true; resolve(value); } };
    const fail = (error: Error) => { if (!settled) { settled = true; reject(error); } };
    const tx = db.transaction(STORE, mode);
    tx.onerror = () => fail(tx.error || new Error("浏览器本地文件存储失败"));
    tx.onabort = () => fail(tx.error || new Error("浏览器本地文件操作已取消"));
    tx.oncomplete = () => db.close();
    action(tx.objectStore(STORE), done, fail);
  });
}

export async function saveLocalPdf(id: string, blob: Blob): Promise<void> {
  return withStore<void>("readwrite", (store, resolve, reject) => {
    const request = store.put(blob, id);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error || new Error("保存 PDF 失败"));
  });
}

export async function getLocalPdf(id: string): Promise<Blob | null> {
  return withStore<Blob | null>("readonly", (store, resolve, reject) => {
    const request = store.get(id);
    request.onsuccess = () => resolve(request.result instanceof Blob ? request.result : null);
    request.onerror = () => reject(request.error || new Error("读取 PDF 失败"));
  });
}

export async function deleteLocalPdf(id: string): Promise<void> {
  return withStore<void>("readwrite", (store, resolve, reject) => {
    const request = store.delete(id);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error || new Error("删除 PDF 失败"));
  });
}

export async function verifyPdf(file: File): Promise<{ hash: string; size: number }> {
  if (!file.name.toLowerCase().endsWith(".pdf")) throw new Error("请选择 .pdf 格式的论文");
  if (!file.size) throw new Error("文件为空，无法提交");
  if (file.size > 15 * 1024 * 1024) throw new Error("PDF 不能超过 15 MB");
  const head = await file.slice(0, 1024).arrayBuffer();
  if (!new TextDecoder("latin1").decode(head).includes("%PDF-")) throw new Error("文件内容不是有效 PDF 头部");
  if (!crypto?.subtle) throw new Error("需要安全浏览器环境才能验证文件 SHA-256");
  const hashBytes = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  const hash = [...new Uint8Array(hashBytes)].map((value) => value.toString(16).padStart(2, "0")).join("");
  return { hash, size: file.size };
}
