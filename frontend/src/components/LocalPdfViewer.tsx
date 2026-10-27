import { useEffect, useRef, useState } from "react";
import { Download, FileQuestion, X } from "lucide-react";
import { getLocalPdf } from "../lib/pdfStore";

export function LocalPdfViewer({ id, title, onClose }: { id: string; title: string; onClose(): void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [message, setMessage] = useState("正在读取浏览器本地保存的 PDF…");

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    getLocalPdf(id).then((blob) => {
      if (!active) return;
      if (!blob) { setMessage("未找到 PDF 原文。旧版文件记录可能只保存了文件名。"); return; }
      objectUrl = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
      setUrl(objectUrl);
    }).catch((error: unknown) => {
      if (active) setMessage(error instanceof Error ? error.message : "读取 PDF 失败");
    });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [id]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const previousPadding = document.body.style.paddingRight;
    const scrollbar = window.innerWidth - document.documentElement.clientWidth;
    dialog.showModal();
    closeRef.current?.focus({ preventScroll: true });
    document.body.style.overflow = "hidden";
    if (scrollbar > 0) {
      document.body.style.paddingRight = parseFloat(getComputedStyle(document.body).paddingRight) + scrollbar + "px";
    }
    return () => {
      dialog.close();
      document.body.style.overflow = previousOverflow;
      document.body.style.paddingRight = previousPadding;
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);

  return (
    <dialog ref={dialogRef} className="pdf-viewer-backdrop" aria-label={"预览 PDF：" + title}
      onCancel={(event) => { event.preventDefault(); onClose(); }} onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const items = event.currentTarget.querySelectorAll<HTMLElement>("a[href],button:not(:disabled),iframe");
        const first = items[0], last = items[items.length - 1];
        if (!first || !last) return;
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault(); last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault(); first.focus();
        }
      }} onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="pdf-viewer">
        <div className="pdf-viewer-header">
          <div><strong>{title}</strong><span>仅从本机浏览器读取，不上传服务器</span></div>
          <div className="pdf-viewer-actions">
            {url && <a className="button button-secondary" href={url} download={title}><Download size={16}/> 下载本地副本</a>}
            <button ref={closeRef} className="icon-button" onClick={onClose} aria-label="关闭 PDF 预览"><X size={21}/></button>
          </div>
        </div>
        {url ? <iframe src={url} title={"PDF 原文：" + title} className="pdf-viewer-frame" /> :
          <div className="pdf-viewer-empty"><FileQuestion size={34}/><p>{message}</p></div>}
      </section>
    </dialog>
  );
}
