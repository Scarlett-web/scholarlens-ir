import { ArrowLeft, ArrowRight, FileQuestion } from "lucide-react";
import { Link } from "react-router-dom";

export function NotFoundPage() {
  return <div className="workspace-page content-wrap">
    <section className="missing-page" aria-labelledby="missing-title">
      <div className="missing-page-symbol"><FileQuestion size={30} strokeWidth={1.6}/></div>
      <span className="missing-page-code">页面不存在 · 404</span>
      <h1 id="missing-title">这里暂时没有你要找的页面。</h1>
      <p>链接可能输入有误，也可能已经失效。你可以从论文检索重新开始。</p>
      <div className="missing-page-actions">
        <Link className="button button-primary" to="/search">去检索论文 <ArrowRight size={17}/></Link>
        <Link className="button button-secondary" to="/"><ArrowLeft size={17}/> 返回首页</Link>
      </div>
    </section>
  </div>;
}
