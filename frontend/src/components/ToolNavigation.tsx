import { NavLink } from "react-router-dom";
import { BarChart3, FileUp, FolderCheck } from "lucide-react";

const links = [
  {to:"/evaluation",label:"检索评测",Icon:BarChart3},
  {to:"/upload",label:"PDF 工作区",Icon:FileUp},
  {to:"/admin",label:"审核工作台",Icon:FolderCheck}
] as const;

export function ToolNavigation() {
  return <nav className="tool-navigation" aria-label="研究工具切换">
    {links.map(({to,label,Icon})=><NavLink key={to} to={to}
      className={({isActive})=>isActive?"tool-navigation-link active":"tool-navigation-link"}>
      <Icon size={16} strokeWidth={1.8}/>{label}
    </NavLink>)}
  </nav>;
}
