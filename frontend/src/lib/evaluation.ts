export type Relevance = 0 | 1 | 2;
export type RelevanceJudgments = Record<string, Relevance>;

/**
 * Evaluates a judged prefix of a single ranking.
 * Cannot estimate corpus-wide Recall without a complete relevance pool.
 * Precision@k requires ALL top-k entries judged to avoid false precision.
 */
export interface EvaluationMetrics {
  count: number;
  judged: number;
  precisionK: number | null;
  precisionAt: number;
  ndcgK: number | null;
  ndcgAt: number;
  relevantCount: number;
  message: string;
}

function dcg(grades: number[]): number {
  return grades.reduce((sum, grade, index) =>
    sum + (Math.pow(2, grade) - 1) / Math.log2(index + 2), 0);
}

export function computeEvaluation(ids: string[], grades: RelevanceJudgments): EvaluationMetrics {
  const k5 = Math.min(5, ids.length);
  const k10 = Math.min(10, ids.length);
  const rank5 = ids.slice(0, k5).map((id) => grades[id]);
  const rank10 = ids.slice(0, k10).map((id) => grades[id]);
  const judged = ids.filter((id) => grades[id] === 0 || grades[id] === 1 || grades[id] === 2).length;
  const all5Judged = k5 > 0 && rank5.every((grade) => grade !== undefined);
  const all10Judged = k10 > 0 && rank10.every((grade) => grade !== undefined);
  const precisionK = all5Judged ? rank5.filter((grade) => grade >= 1).length / k5 : null;
  const rank10Numeric = rank10.filter((grade): grade is Relevance => grade !== undefined);
  const optimal = [...rank10Numeric].sort((a,b) => b - a);
  const ideal = dcg(optimal);
  const ndcgK = all10Judged ? (ideal === 0 ? 0 : dcg(rank10Numeric) / ideal) : null;
  return {
    count: ids.length, judged, precisionK, precisionAt: k5,
    ndcgK, ndcgAt: k10,
    relevantCount: ids.filter((id) => grades[id] !== undefined && grades[id] >= 1).length,
    message: all10Judged ? "当前结果的前缀已标注完整；指标仅代表当前人工标注样本。" : "请先标注当前排序的所有结果，才会展示对应指标。"
  };
}
