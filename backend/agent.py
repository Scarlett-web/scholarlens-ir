"""ScholarLens evidence agent orchestration.

The agent is deliberately small and traceable: it plans a bounded set of local
tools, retrieves source evidence, delegates grounded generation to the existing
RAG adapter, and returns the execution trace with the answer. MCP and skills are
project configuration concerns; this module is the runtime contract they target.
"""

from dataclasses import dataclass


AGENT_NAME = "ScholarLens Evidence Agent"
AGENT_VERSION = "0.1.0"


@dataclass(frozen=True)
class AgentTool:
    name: str
    label: str
    purpose: str


TOOLS = (
    AgentTool("search_papers", "检索论文", "按问题从论文索引中找到候选来源"),
    AgentTool("retrieve_evidence", "核对原文", "从标题、摘要或全文片段提取可引用证据"),
    AgentTool("grounded_answer", "生成回答", "只根据已核对片段生成带引用的回答"),
    AgentTool("citation_guard", "校验引用", "确认回答中的引用来自本次证据且定位有效"),
)


def plan(operation: str, question: str, paper_ids: list[str] | None) -> list[dict]:
    """Return a stable, user-readable plan without exposing credentials or prompts."""
    scope = f"限定 {len(paper_ids)} 篇论文" if paper_ids else "全库范围"
    operation_label = {"ask": "回答问题", "summarize": "总结单篇论文", "compare": "比较多篇论文"}.get(
        operation, "回答问题"
    )
    return [
        {"id": "route", "tool": "search_papers", "label": f"确定任务：{operation_label} · {scope}", "status": "done"},
        {"id": "evidence", "tool": "retrieve_evidence", "label": "检索并逐段核对原文证据", "status": "running"},
        {"id": "answer", "tool": "grounded_answer", "label": "基于证据生成回答", "status": "queued"},
        {"id": "guard", "tool": "citation_guard", "label": "检查引用与证据范围", "status": "queued"},
    ]


def finish_plan(steps: list[dict], evidence_count: int, answer_ready: bool) -> list[dict]:
    result = [dict(step) for step in steps]
    result[1]["status"] = "done" if evidence_count else "empty"
    result[2]["status"] = "done" if answer_ready else "skipped"
    result[3]["status"] = "done" if answer_ready else "skipped"
    return result


def trace(operation: str, question: str, paper_ids: list[str] | None, evidence_count: int, answer_ready: bool):
    steps = plan(operation, question, paper_ids)
    return {
        "name": AGENT_NAME,
        "version": AGENT_VERSION,
        "workflow": "evidence-grounded-answer",
        "tools": [{"name": tool.name, "label": tool.label} for tool in TOOLS],
        "steps": finish_plan(steps, evidence_count, answer_ready),
        "evidence_count": evidence_count,
        "grounded": bool(answer_ready and evidence_count),
    }
