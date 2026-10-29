import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { BarChart3, BookOpen, Check, ChevronDown, Compass, FilePlus2, FolderCheck, Home, Layers, Menu, Monitor, Pause, Play, Search, Sparkles, X } from "lucide-react";
import { Brand } from "./Brand";
import { MotionEffects } from "./MotionEffects";
import { DATA_SOURCE, getLibraryStats } from "../services/papers";
import { GLASS_PRESETS, useStudio } from "../App";
import { useAuth } from "../services/AuthContext";

const MAIN_NAV = [
  {to:"/",label:"首页",Icon:Home}, {to:"/search",label:"论文检索",Icon:Search},
  {to:"/explore",label:"探索论文",Icon:Compass}, {to:"/library",label:"我的文献",Icon:BookOpen}
] as const;
const TOOL_NAV = [
  {to:"/evaluation",label:"检索评测",Icon:BarChart3},
  {to:"/upload",label:"PDF 工作区",Icon:FilePlus2},
  {to:"/admin",label:"审核工作台",Icon:FolderCheck},
  {to:"/assistant",label:"证据助手",Icon:Sparkles}
] as const;

export function SiteLayout({ children }: { children: ReactNode }) {
  const {user}=useAuth();
  const { pathname } = useLocation();
  const { favorites, presentation, setPresentation, toast, notify, motionPaused, setMotionPaused, glass, setGlass, reducedMotion } = useStudio();
  const [menu, setMenu] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const isToolActive = TOOL_NAV.some(({ to }) => to === pathname);
  const toolsTimer = useRef<number | null>(null);
  const toolsMenuRef = useRef<HTMLDivElement>(null);

  const openTools = () => {
    if (toolsTimer.current) {
      clearTimeout(toolsTimer.current);
      toolsTimer.current = null;
    }
    setToolsOpen(true);
  };

  const closeTools = () => {
    if (toolsTimer.current) {
      clearTimeout(toolsTimer.current);
    }
    toolsTimer.current = window.setTimeout(() => {
      setToolsOpen(false);
      toolsTimer.current = null;
    }, 220);
  };

  useEffect(() => {
    return () => {
      if (toolsTimer.current) {
        clearTimeout(toolsTimer.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!toolsOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (toolsMenuRef.current && !toolsMenuRef.current.contains(e.target as Node)) {
        if (toolsTimer.current) clearTimeout(toolsTimer.current);
        setToolsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [toolsOpen]);
  const [dataStatus, setDataStatus] = useState(DATA_SOURCE === "demo" ? "演示空间 · 18 篇虚构论文" : "正在连接论文库…");
  useEffect(() => {
    if (DATA_SOURCE === "demo") return;
    let active = true;
    getLibraryStats().then(data => { if (active) setDataStatus((data.status === "real" ? "真实论文库" : data.status === "mock" ? "后端模拟库" : "论文服务") + " · " + data.count + " 篇"); })
      .catch(() => { if (active) setDataStatus("论文服务暂不可用"); });
    return () => { active = false; };
  }, []);
  const menuRef = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const current = [...MAIN_NAV,...TOOL_NAV].find(({to})=>to===pathname)?.label ?? (pathname==="/account"?"研究账户":pathname.startsWith("/paper/")?"论文阅读":"页面");
  useEffect(() => { setMenu(false); setToolsOpen(false); }, [pathname]);
  useEffect(() => { document.title = (current === "页面" ? "页面未找到" : current) + " · ScholarLens"; }, [current, pathname]);
  useEffect(() => {
    if (!menu) return;
    menuRef.current?.querySelector<HTMLAnchorElement>("a")?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if(event.key==="Escape"){setMenu(false);menuButton.current?.focus();}
      if(event.key!=="Tab")return;
      const items=menuRef.current?.querySelectorAll<HTMLElement>("a,button");
      if(!items?.length)return;
      const first=items[0],last=items[items.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    };
    document.addEventListener("keydown",keyboard);
    return()=>document.removeEventListener("keydown",keyboard);
  },[menu]);
  const togglePresentation=()=>{
    setPresentation(!presentation);
    notify(!presentation?"课堂展示字号已开启":"已恢复正常字号");
  };
  const cycleGlass=()=>{
    const index = GLASS_PRESETS.findIndex((preset) => preset.value === glass);
    const next = GLASS_PRESETS[(index + 1) % GLASS_PRESETS.length];
    setGlass(next.value);
    notify("玻璃通透度：" + next.label + " · " + next.hint);
  };
  const glassLabel = GLASS_PRESETS.find((preset) => preset.value === glass)?.label ?? "标准";
  return <div className="shell shell-light workspace-shell" data-glass={glass} data-motion={motionPaused || reducedMotion ? "paused" : "running"}>
    <div className="observatory-backdrop" aria-hidden="true"><img src="/images/iceland-jokulsarlon.webp" srcSet="/images/iceland-jokulsarlon-1600.webp 1600w, /images/iceland-jokulsarlon-2560.webp 2560w, /images/iceland-jokulsarlon.webp 3200w" sizes="100vw" width="3200" height="1801" alt="" fetchPriority="high"/></div>
    <MotionEffects/>
    <a className="skip-link" href="#main">跳转到内容</a>
    <aside className="app-sidebar" aria-label="研究空间导航">
      <div className="sidebar-brand"><Brand/><span>学术研究工作区</span></div>
      <span className="sidebar-section-label">研究空间</span>
      <nav className="desktop-nav" aria-label="主要功能">
        {MAIN_NAV.map(({to,label,Icon})=><NavLink key={to} to={to} end={to==="/"} className={({isActive})=>
          "nav-link"+(isActive?" active":"")+(to==="/library"?" account-link":"")}>
          <Icon size={18} strokeWidth={1.7}/><span>{label}</span>{to==="/library"&&favorites.length>0&&<small className="nav-link-count">{favorites.length}</small>}
        </NavLink>)}
      </nav>
      <span className="sidebar-section-label sidebar-tools-label">研究工具</span>
      <nav className="sidebar-tools" aria-label="研究工具">
        {TOOL_NAV.map(({to,label,Icon})=><NavLink key={to} to={to} className={({isActive})=>"tool-item"+(isActive?" active":"")}>
          <Icon size={18} strokeWidth={1.7}/><span>{label}</span>{to==="/assistant"&&<small>可配置</small>}
        </NavLink>)}
      </nav>
      <div className="sidebar-bottom">
        <button className="site-motion-toggle" type="button" disabled={reducedMotion} aria-pressed={motionPaused || reducedMotion} onClick={()=>setMotionPaused(!motionPaused)}>
          {motionPaused || reducedMotion ? <Play size={18}/> : <Pause size={18}/>}<span>{reducedMotion ? "已跟随系统静态显示" : motionPaused ? "开启网站动效" : "暂停网站动效"}</span>
        </button>
        <button className="site-glass-toggle" type="button" onClick={cycleGlass} title="调整页面玻璃的通透度：通透 / 标准 / 厚雾">
          <Layers size={18}/><span>玻璃通透度 · {glassLabel}</span>
        </button>
        <button className={"presentation-toggle"+(presentation?" active":"")} onClick={togglePresentation} aria-pressed={presentation} title="放大论文标题与正文">
          <Monitor size={18}/><span>{presentation?"退出展示模式":"课堂展示模式"}</span>
        </button>
        <Link to="/account" className="sidebar-signature"><span className="sidebar-signature-mark">{user?.username[0].toUpperCase()||"S"}</span><div><strong>{user?.username||"登录研究账户"}</strong><small>{user?(user.role==="admin"?"管理员 · 账户空间":"已登录 · 账户空间"):"游客数据保留在本机"}</small></div></Link>
      </div>
    </aside>
    <div className="app-stage" data-space={pathname.startsWith("/paper/")?"reading":pathname==="/"?"home":"workspace"}>
      <header className="site-header header-light">
        <div className="header-inner content-wrap">
          <div className="header-brand-wrap">
            <Brand />
            <span className="header-brand-divider" aria-hidden="true">/</span>
            <span className="header-brand-desc">学术研究与核验</span>
          </div>
          <nav className="header-dock-nav" aria-label="主要导航">
            {MAIN_NAV.map(({ to, label, Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  "header-dock-pill" + (isActive ? " active" : "") + (to === "/library" ? " account-link" : "")
                }
              >
                <Icon size={15} strokeWidth={1.8} />
                <span>{label}</span>
                {to === "/library" && favorites.length > 0 && (
                  <small className="dock-pill-badge">{favorites.length}</small>
                )}
              </NavLink>
            ))}
            <div
              ref={toolsMenuRef}
              className="header-tools-menu"
              onMouseEnter={openTools}
              onMouseLeave={closeTools}
            >
              <button
                type="button"
                className={"header-dock-pill header-tools-trigger" + (isToolActive ? " active" : "")}
                onClick={() => (toolsOpen ? closeTools() : openTools())}
                aria-expanded={toolsOpen}
              >
                <Sparkles size={15} strokeWidth={1.8} />
                <span>研究工具</span>
                <ChevronDown size={13} className={"tools-caret" + (toolsOpen ? " open" : "")} />
              </button>
              {toolsOpen && (
                <div
                  className="header-tools-popover"
                  role="menu"
                  onMouseEnter={openTools}
                  onMouseLeave={closeTools}
                >
                  {TOOL_NAV.map(({ to, label, Icon }) => (
                    <NavLink
                      key={to}
                      to={to}
                      className={({ isActive }) => "tools-popover-item" + (isActive ? " active" : "")}
                      onClick={() => {
                        if (toolsTimer.current) clearTimeout(toolsTimer.current);
                        setToolsOpen(false);
                      }}
                    >
                      <Icon size={15} strokeWidth={1.8} />
                      <span>{label}</span>
                      {to === "/assistant" && <small className="popover-tag">可配置</small>}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          </nav>
          <div className="header-actions">
            <button
              className="header-action-pill site-glass-toggle"
              type="button"
              onClick={cycleGlass}
              title="调整页面玻璃通透度：通透 / 标准 / 厚雾"
            >
              <Layers size={14} />
              <span>{glassLabel}</span>
            </button>
            <button
              className="header-action-icon site-motion-toggle"
              type="button"
              disabled={reducedMotion}
              aria-pressed={motionPaused || reducedMotion}
              onClick={() => setMotionPaused(!motionPaused)}
              title={reducedMotion ? "已跟随系统静态显示" : motionPaused ? "开启网站动效" : "暂停网站动效"}
            >
              {motionPaused || reducedMotion ? <Play size={14} /> : <Pause size={14} />}
            </button>
            <button
              className={"header-action-icon presentation-toggle" + (presentation ? " active" : "")}
              type="button"
              onClick={togglePresentation}
              aria-pressed={presentation}
              title="放大论文标题与正文"
            >
              <Monitor size={14} />
            </button>
            <span className="header-data-status">
              <span className="env-dot" />
              {dataStatus}
            </span>
            <Link
              to="/account"
              className="button button-secondary account-entry"
              title={user?.username || "登录研究账户"}
            >
              <span className="account-initial-mark">{user?.username[0].toUpperCase() || "S"}</span>
              <span>{user?.username || "登录"}</span>
            </Link>
            <button
              ref={menuButton}
              className="mobile-menu-button icon-button"
              onClick={() => setMenu(!menu)}
              aria-label={menu ? "收起导航" : "展开导航"}
              aria-controls="mobile-navigation"
              aria-expanded={menu}
            >
              {menu ? <X size={22} /> : <Menu size={22} />}
            </button>
          </div>
        </div>
        {menu&&<div className="mobile-navigation-layer">
          <button className="mobile-nav-backdrop" aria-label="关闭导航" onClick={()=>{setMenu(false);menuButton.current?.focus();}}/>
          <nav ref={menuRef} id="mobile-navigation" className="mobile-nav" aria-label="移动端导航">
            <span className="mobile-nav-heading">研究空间</span>
            {MAIN_NAV.map(({to,label,Icon})=><NavLink key={to} to={to} end={to==="/"}><Icon size={18}/>{label}</NavLink>)}
            <span className="mobile-nav-heading">研究工具</span>
            {TOOL_NAV.map(({to,label,Icon})=><NavLink key={to} to={to}><Icon size={18}/>{label}</NavLink>)}
            <button className="mobile-motion-toggle" type="button" disabled={reducedMotion} aria-pressed={motionPaused || reducedMotion} onClick={()=>setMotionPaused(!motionPaused)}>{motionPaused || reducedMotion?<Play size={18}/>:<Pause size={18}/>} {reducedMotion?"已跟随系统静态显示":motionPaused?"开启网站动效":"暂停网站动效"}</button>
            <button type="button" onClick={()=>{togglePresentation();setMenu(false);}}><Monitor size={18}/>{presentation?"退出展示模式":"课堂展示模式"}</button>
            <button className="mobile-nav-close" type="button" onClick={()=>{setMenu(false);menuButton.current?.focus();}}><X size={18}/>收起导航</button>
          </nav>
        </div>}
      </header>
      {DATA_SOURCE==="demo"&&<div className="environment-strip" role="status"><span className="env-dot"/>演示空间 · 18 篇虚构示例论文，非真实研究数据</div>}
      <main id="main" className="site-main" key={pathname}>{children}</main>
      <footer className="site-footer footer-light"><div className="content-wrap footer-inner">
        <span className="footer-motto">ScholarLens <span>把注意力留给研究本身。</span></span>
        <div className="footer-links"><Link to="/search">论文检索</Link><Link to="/library">我的文献</Link><Link to="/evaluation">检索评测</Link></div>
        <div className="footer-copy">{DATA_SOURCE==="demo"?"虚构样本仅供演示":"API 模式"}<a className="landscape-credit" href="https://www.pexels.com/photo/stunning-icebergs-in-jokulsarlon-glacier-lagoon-32014201/" target="_blank" rel="noreferrer">冰岛影像 · X1ntao ZHOU ↗</a></div>
      </div></footer>
    </div>
    {toast&&<div className="toast" role="status"><Check size={17}/>{toast}</div>}
  </div>;
}
export function PageHeading({ eyebrow,title,desc,extra }: { eyebrow:string;title:string;desc?:string;extra?:ReactNode }) {
  return <section className="page-heading"><div><span className="page-kicker">{eyebrow.split("/")[0].trim()}</span><h1>{title}</h1>{desc&&<p>{desc}</p>}</div>{extra&&<div className="page-heading-extra">{extra}</div>}</section>;
}
export function IntegrationNotice({title,desc}:{title:string;desc:string}) {
  return <div className="integration-notice" role="note"><span className="integration-orb"><Sparkles size={16}/></span><div><strong>{title}</strong><p>{desc}</p></div></div>;
}
export function DemoBadge(){return <span className="demo-badge">演示论文</span>;}
