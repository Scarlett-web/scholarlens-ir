import { useEffect, useState } from "react";
import { getSearchCapabilities } from "./papers";
import type { SearchCapabilities } from "./paperApi";

export function useSearchCapabilities() {
  const [capabilities, setCapabilities] = useState<SearchCapabilities | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active=true;
    const refresh=()=>getSearchCapabilities().then(data=>{if(active){setCapabilities(data);setError("");}})
      .catch(cause=>{if(active){setCapabilities(null);setError(cause instanceof Error?cause.message:"无法检查检索服务");}});
    void refresh();
    const timer=window.setInterval(()=>void refresh(),30000);
    window.addEventListener("focus",refresh);
    return()=>{active=false;window.clearInterval(timer);window.removeEventListener("focus",refresh);};
  }, []);
  return {capabilities, error};
}
