import { Check, Circle, Minus, AlertCircle } from "lucide-react";
import { uploadWorkflow } from "../lib/uploadWorkflow";

export function UploadTimeline({status}: {status: string}) {
  const workflow = uploadWorkflow(status);
  return <ol className="upload-timeline" aria-label={"文件处理流程：" + workflow.label}>
    {workflow.steps.map((step, index) => <li key={step.label} data-state={step.state} aria-current={step.state === "current" ? "step" : undefined}>
      <span className="upload-step-mark" aria-hidden="true">{step.state === "done" ? <Check size={12}/> : step.state === "blocked" ? <AlertCircle size={14}/> : step.state === "current" ? <Circle size={12}/> : <Minus size={12}/>}</span>
      <span>{step.label}<small>{step.state === "done" ? "已确认" : step.state === "blocked" ? "需处理" : step.state === "current" ? "当前阶段" : index === 2 && status === "approved" ? "等待管理员处理" : "尚未完成"}</small></span>
    </li>)}
  </ol>;
}
