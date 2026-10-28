import { useEffect, useRef, useState } from "react";
import { ArrowRight, ArrowUpRight, BookOpen, Pause, Play } from "lucide-react";
import { Link } from "react-router-dom";
import { SearchBox } from "../components/SearchBox";
import { useStudio } from "../App";
import { RecentReadingDeck } from "../components/RecentReadingDeck";
import { ResearchPrism } from "../components/ResearchPrism";
import { DATA_SOURCE, getDiscovery } from "../services/papers";

const TOPICS = [
  { title:"计算机科学", description:"计算方法、视觉与信息检索", query:"computer", index:"01" },
  { title:"机器学习", description:"模型、算法与学习方法", query:"machine learning", index:"02" },
  { title:"气候与环境", description:"气候变化与环境研究", query:"climate", index:"03" }
];
export function HomePage(){
  const {favorites,history,motionPaused:paused,setMotionPaused:setPaused,reducedMotion}=useStudio();
  const lastRead=history[0]?.paper;
  const [topics, setTopics] = useState(DATA_SOURCE === "demo" ? TOPICS : []);
  useEffect(() => {
    if (DATA_SOURCE === "demo") return;
    let active = true;
    getDiscovery().then(data => { if (active) setTopics(data.examples.slice(0,3).map((item,index) => ({
      title: item.q, description: "从这篇论文展开标题检索", query: item.q, index: String(index+1).padStart(2,"0")
    }))); }).catch(() => {});
    return () => { active = false; };
  }, []);
  const sceneRef=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    const scene=sceneRef.current;
    if(!scene)return;
    const preference=window.matchMedia("(prefers-reduced-motion: reduce)");
    const finePointer=window.matchMedia("(hover: hover) and (pointer: fine)");
    let frame=0;
    let rotateX=0,rotateY=0;
    let inView=false;
    const reset=()=>{
      cancelAnimationFrame(frame);frame=0;
      scene.style.removeProperty("--scene-rx");
      scene.style.removeProperty("--scene-ry");
      delete scene.dataset.tilt;
    };
    const syncPreference=()=>{reset();};
    const syncVisibility=()=>{
      scene.dataset.sceneActive=String(inView&&!document.hidden);
      if(document.hidden)reset();
    };
    const move=(event:PointerEvent)=>{
      if(paused||preference.matches||!finePointer.matches||event.pointerType!=="mouse")return;
      // Keep hit targets stable while the reader reaches a link or a page control.
      if(event.target instanceof Element && event.target.closest("a,button")){
        cancelAnimationFrame(frame);frame=0;return;
      }
      const rect=scene.getBoundingClientRect();
      rotateX=(.5-(event.clientY-rect.top)/rect.height)*14;
      rotateY=((event.clientX-rect.left)/rect.width-.5)*18;
      if(frame)return;
      frame=requestAnimationFrame(()=>{
        scene.style.setProperty("--scene-rx",rotateX+"deg");
        scene.style.setProperty("--scene-ry",rotateY+"deg");
        scene.dataset.tilt="active";
        frame=0;
      });
    };
    syncPreference();
    const observer=new IntersectionObserver(([entry])=>{
      inView=entry.isIntersecting;syncVisibility();
      if(!inView)reset();
    },{threshold:.15});
    observer.observe(scene);
    scene.addEventListener("pointermove",move);
    scene.addEventListener("pointerleave",reset);
    preference.addEventListener("change",syncPreference);
    document.addEventListener("visibilitychange",syncVisibility);
    return()=>{
      observer.disconnect();reset();
      scene.removeEventListener("pointermove",move);
      scene.removeEventListener("pointerleave",reset);
      preference.removeEventListener("change",syncPreference);
      document.removeEventListener("visibilitychange",syncVisibility);
    };
  },[paused]);
  return <div className="home-page apple-home" data-motion={paused||reducedMotion?"paused":"running"}>
    <section className="hero content-wrap" aria-labelledby="home-title">
      <div className="observatory-caption"><span><i/> ScholarLens · 论文与研究线索</span><span>冰岛 · 杰古沙龙冰河湖</span></div>
      <div className="hero-composition">
        <div className="hero-inner">
          <svg className="hero-knowledge-map" viewBox="0 0 500 280" aria-hidden="true"><g className="knowledge-paths"><path d="M20 210 130 100 270 150 390 40 480 110M130 100 205 30M270 150 360 250M20 210 190 240 270 150M390 40 360 250"/></g><g className="knowledge-nodes">{[[20,210],[130,100],[270,150],[390,40],[480,110],[205,30],[360,250],[190,240]].map(([x,y],i)=><circle key={i} cx={x} cy={y} r={i===2?5:3} style={{animationDelay:i*350+"ms"}}/>)}</g></svg>
          <span className="hero-label"><span/> 检索 · 原文 · 研究笔记</span>
          <h1 id="home-title">找到论文，<br/><span>留下研究的线索。</span></h1>
          <p className="hero-subtitle">检索标题、作者、机构与全文，回到原文核对证据。<br/>收藏、摘录，再从上次读到的地方继续。</p>
          <div className="home-search-area">
            <div className="home-search-heading"><span>从你的研究问题出发</span><span>关键词 · 作者 · 机构 · 全文</span></div>
            <SearchBox/>
            <div className="hero-chips" aria-label="尝试检索示例"><span>试试搜索</span>{(DATA_SOURCE === "demo" ? ["computer","machine learning","climate"] : ["magnetic","quantum","protein"]).map(term=><Link key={term} to={"/search?q="+encodeURIComponent(term)+"&field=all&mode=keyword"}>{term}<ArrowUpRight size={12}/></Link>)}</div>
          </div>
          <div className="hero-caption"><span className="hero-caption-line"/> 每一条线索，都有原文可循
            <button className="motion-toggle" type="button" disabled={reducedMotion} aria-pressed={paused||reducedMotion} onClick={()=>setPaused(!paused)} title={reducedMotion?"已跟随系统减少动态效果":"控制首页的装饰动画与鼠标视差"}>
              {paused||reducedMotion?<Play size={12}/>:<Pause size={12}/>} {reducedMotion?"静态效果":paused?"开启动效":"暂停动效"}
            </button>
          </div>
        </div>
        <div className="hero-paper-stage" ref={sceneRef} data-scene-active="false">
          <ResearchPrism/>
          <div className="hero-paper-float scene-motion"><div className="hero-paper-stack" data-count={Math.min(history.length,5)}>
          <RecentReadingDeck/>
          </div></div>
        </div>
      </div>

    </section>
    <section className="home-workspace content-wrap" aria-label="探索与阅读空间">
      <div className="home-workspace-heading"><div><span className="section-kicker">从论文继续</span><h2>接着读，或找一条新线索。</h2></div><Link to="/explore">{DATA_SOURCE === "demo" ? "探索全部领域" : "探索近期论文"} <ArrowRight size={16}/></Link></div>
      <div className="home-shelf">
        <div className="home-topics"><div className="home-topic-list">{topics.map(({title,description,query,index})=><Link key={query} className="home-topic" to={"/search?q="+encodeURIComponent(query)+"&field="+(DATA_SOURCE === "demo" ? "all" : "title")+"&mode=keyword"}><span className="home-topic-index">{index}</span><span><strong>{title}</strong><small>{description}</small></span><ArrowUpRight size={18}/></Link>)}{!topics.length&&<Link className="home-topic" to="/search"><span>输入关键词，开始探索论文</span><ArrowUpRight size={18}/></Link>}</div></div>
        <div className="home-reading"><div className="home-reading-top"><BookOpen size={20} strokeWidth={1.5}/><span>个人阅读空间</span></div><h2>{lastRead?"接着上次的思路。":"把线索，留在一起。"}</h2>
          {lastRead?<Link className="home-recent-paper" to={"/paper/"+encodeURIComponent(lastRead.paper_id)}><span>继续阅读</span><strong>{lastRead.title}</strong></Link>:<p>收藏值得读的论文，整理分类与笔记。<br/>下一次打开，就从这里继续。</p>}
          <div className="home-reading-bottom"><span>{favorites.length?favorites.length+" 篇已收藏":"你的第一篇收藏，正在路上"}</span><Link className="home-library-link" to="/library" aria-label="打开我的文献"><ArrowRight size={20}/></Link></div>
        </div>
      </div>
    </section>
  </div>;
}
