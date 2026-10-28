import { Link } from "react-router-dom";
import { BookOpen } from "lucide-react";
import { useAuth } from "../services/AuthContext";
import { loadReadingPosition } from "../lib/readingPosition";

/** Library snapshots omit source text; the reader validates its length on opening. */
export function ReadingPositionHint({ paperId }: { paperId: string }) {
  const { user } = useAuth();
  const position = loadReadingPosition(user?.id, paperId);
  if (!position || position.ratio <= .02) return null;
  return <div className="library-reading-position">
    <BookOpen size={14}/><span>上次记录 {Math.round(position.ratio * 100)}% <small>· 本机</small></span>
    <progress max={1} value={position.ratio} aria-label="上次记录的阅读位置"/>
    <Link to={"/paper/" + encodeURIComponent(paperId)}>继续阅读</Link>
  </div>;
}
