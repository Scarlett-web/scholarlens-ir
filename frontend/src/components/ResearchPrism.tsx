/** A decorative ice object, not a representation of paper or citation data. */
export function ResearchPrism() {
  return <div className="research-prism" aria-hidden="true">
    <svg viewBox="0 0 560 560" focusable="false">
      <g className="prism-thickness">
        <path d="M84 138 231 47 468 126 514 357 349 508 135 414Z"/>
        <path d="M135 414 349 508 339 480 113 390Z"/>
        <path d="M349 508 514 357 488 341 339 480Z"/>
      </g>
      <g className="prism-facets">
        <path className="facet-north" d="M73 117 225 29 460 111 293 167Z"/>
        <path className="facet-west" d="M73 117 293 167 113 390Z"/>
        <path className="facet-core" d="M293 167 460 111 488 341 339 480 113 390Z"/>
        <path className="facet-east" d="M460 111 488 341 398 273Z"/>
        <path className="facet-south" d="M113 390 293 167 339 480Z"/>
        <path className="facet-reflection" d="M225 29 293 167 113 390 185 174Z"/>
        <path className="facet-reflection" d="M460 111 398 273 339 480 383 228Z"/>
      </g>
      <g className="prism-edges">
        <path d="M73 117 225 29 460 111 488 341 339 480 113 390Z"/>
        <path d="M73 117 293 167 460 111M225 29 293 167 339 480M113 390 293 167M488 341 398 273 460 111"/>
      </g>
      <g className="prism-caustics">
        <path d="M79 119 224 36 443 112M121 387 335 471"/>
        <path d="m89 155 20 83M100 159l7 28M467 162l14 168"/>
      </g>
    </svg>
    <span className="prism-shadow"/>
  </div>;
}
