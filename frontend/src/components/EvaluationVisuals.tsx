import type { ReactNode } from "react";

export function MetricRing({ value, children }: { value: number | null; children: ReactNode }) {
  const circumference = 2 * Math.PI * 26;
  return <div className="metric-ring" data-ready={value !== null}>
    <svg viewBox="0 0 64 64" aria-hidden="true"><circle className="metric-ring-track" cx="32" cy="32" r="26"/>
      {value !== null && <circle className="metric-ring-value" cx="32" cy="32" r="26"
        strokeDasharray={(Math.max(0, Math.min(1, value)) * circumference) + " " + circumference}/>}
    </svg><strong className="metric-value">{children}</strong>
  </div>;
}

export function MetricScale({ value }: { value: number | null }) {
  return <div className="metric-scale" data-ready={value !== null} aria-hidden="true">
    <span style={{ transform: "scaleX(" + (value === null ? 0 : Math.max(0, Math.min(1, value))) + ")" }}/>
  </div>;
}

export interface QueryTiming { query: string; ms: number }
export function QueryTimings({ entries }: { entries: QueryTiming[] }) {
  if (!entries.length) return <span className="metric-awaiting">等待真实请求</span>;
  const max = Math.max(1, ...entries.map(entry => entry.ms));
  return <ol className="query-timings" aria-label="本页最近的实际检索引擎耗时">
    {entries.map((entry, index) => <li key={index} title={entry.query + " · " + entry.ms + " ms"} aria-label={entry.query + "，" + entry.ms + " 毫秒"}>
      <span style={{ transform: "scaleY(" + entry.ms / max + ")" }}/><small>{entry.ms}</small>
    </li>)}
  </ol>;
}
