import { Link } from "react-router-dom";

export function BrandMark({ size = 32, glow = false }: { size?: number; glow?: boolean }) {
  return (
    <svg className={glow ? "brand-mark brand-mark-glow" : "brand-mark"} width={size} height={size}
      viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <circle cx="24" cy="24" r="18" stroke="currentColor" strokeWidth="1.6" opacity=".72" />
      <ellipse cx="24" cy="24" rx="20" ry="8" transform="rotate(-32 24 24)" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="24" cy="24" r="4.4" fill="currentColor" />
      <circle cx="38.2" cy="14.1" r="2.1" fill="currentColor" />
    </svg>
  );
}

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className="brand-link" to="/" aria-label="ScholarLens 首页">
      <BrandMark size={compact ? 27 : 33} />
      <span className="brand-wordmark">Scholar<span>Lens</span></span>
    </Link>
  );
}
