export type WorkflowState = "done" | "current" | "waiting" | "blocked";
export interface WorkflowStep { label: string; state: WorkflowState }

const labels: Record<string, string> = {
  pending: "待审核", approved: "已批准，待解析", rejected: "审核未通过",
  processing: "正在解析与关键词入库", indexed: "关键词可检索",
  failed: "处理失败", dependency_unavailable: "解析服务暂不可用",
};
const reasons: Record<string, string> = {
  pdf_requires_ocr: "未提取到足够文本，这份 PDF 可能是扫描件，需要先完成 OCR。",
  parse_dependency_unavailable: "解析服务暂时无法连接，管理员可在服务恢复后重试。",
  index_busy_retry: "另一个入库任务正在运行，请稍后重试。",
  processing_failed: "处理未完成，请管理员检查文件或服务后重试。",
};

export function uploadWorkflow(status: string) {
  const steps: WorkflowStep[] = [
    {label: "收到 PDF", state: "done"}, {label: "审核", state: "waiting"},
    {label: "解析与关键词入库", state: "waiting"}, {label: "可检索", state: "waiting"},
  ];
  if (status === "pending") steps[1].state = "current";
  else if (status === "rejected") steps[1].state = "blocked";
  else if (["approved", "processing", "indexed", "failed", "dependency_unavailable"].includes(status)) {
    steps[1].state = "done";
    if (status === "processing") steps[2].state = "current";
    if (status === "failed" || status === "dependency_unavailable") steps[2].state = "blocked";
    if (status === "indexed") { steps[2].state = "done"; steps[3].state = "done"; }
  }
  const known = Object.prototype.hasOwnProperty.call(labels,status);
  return { steps, label: known ? labels[status] : "未知处理状态", known };
}

export function uploadReason(reason: string) { return Object.prototype.hasOwnProperty.call(reasons,reason) ? reasons[reason] : reason; }
export function canProcessUpload(status: string) { return ["approved", "failed", "dependency_unavailable"].includes(status); }
