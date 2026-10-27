"""User-isolated reading workspace with optimistic concurrency and server-owned paper data."""
import json
import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from backend.accounts import Store, now, problem


class SavedPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper_id: str = Field(min_length=1, max_length=512)
    collection: str = Field(default="全部收藏", min_length=1, max_length=36)
    note: str = Field(default="", max_length=2000)
    savedAt: str = Field(default="", max_length=64)


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper_id: str = Field(min_length=1, max_length=512)
    viewedAt: str = Field(default="", max_length=64)


class Workspace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0)
    favorites: list[SavedPaper] = Field(max_length=1000)
    history: list[Reading] = Field(max_length=50)
    collections: list[Annotated[str, Field(min_length=1, max_length=36)]] = Field(max_length=100)


def router(store: Store, read_paper):
    api = APIRouter(prefix="/api/me")
    with store.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS workspaces (
            user_id INTEGER PRIMARY KEY REFERENCES users(id), version INTEGER NOT NULL,
            payload TEXT NOT NULL)""")

    def snapshot(paper_id):
        doc, _ = read_paper(paper_id)
        return {**{k: doc.get(k) for k in ("paper_id", "title", "authors", "year", "date", "affiliation", "address", "pages", "parse_status")},
                "abstract": doc.get("abstract", "")[:1800], "fulltext": "", "pdf_available": False}

    def native(db, uid):
        return {
            "favorites": [dict(r) for r in db.execute("SELECT paper_id,created_at FROM favorites WHERE user_id=? ORDER BY paper_id", (uid,))],
            "folders": [dict(r) for r in db.execute("SELECT id,name FROM favorite_folders WHERE user_id=? ORDER BY id", (uid,))],
            "items": [dict(r) for r in db.execute("SELECT i.folder_id,i.paper_id FROM favorite_folder_items i JOIN favorite_folders f ON f.id=i.folder_id WHERE f.user_id=? ORDER BY i.folder_id,i.paper_id", (uid,))],
            "history": [dict(r) for r in db.execute("SELECT paper_id,accessed_at FROM browsing_history WHERE user_id=? ORDER BY accessed_at DESC,id DESC LIMIT 500", (uid,))],
        }

    def digest(data):
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def revision(version, state):
        # 48-bit digest remains an exact integer in JavaScript; GET has no write side effects.
        return int(digest({"version": version, "native": state})[:12], 16)

    @api.get("/workspace")
    def get_workspace(user=Depends(store.current)):
        with store.connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT version,payload FROM workspaces WHERE user_id=?", (user["id"],)).fetchone()
            saved = db.execute("SELECT paper_id,created_at FROM favorites WHERE user_id=? ORDER BY created_at DESC,paper_id", (user["id"],)).fetchall()
            state = native(db, user["id"])
        payload = json.loads(row["payload"]) if row else {"favorites": [], "history": [], "collections": ["全部收藏", "待读", "重点阅读"]}
        metadata = {item["paper_id"]: item for item in payload["favorites"]}
        folder_names = {r["id"]: r["name"] for r in state["folders"]}
        placement = {r["paper_id"]: folder_names[r["folder_id"]] for r in state["items"]}
        payload["collections"] = list(dict.fromkeys(["全部收藏", *folder_names.values(), *(["待读", "重点阅读"] if row is None and not folder_names else [])]))
        seen = set()
        payload["history"] = []
        for entry in state["history"]:
            if entry["paper_id"] not in seen:
                payload["history"].append({"paper_id": entry["paper_id"], "viewedAt": entry["accessed_at"]})
                seen.add(entry["paper_id"])
            if len(payload["history"]) >= 50:
                break
        current = revision(row["version"] if row else 0, state)
        favorites, history = [], []
        for item in saved:
            try:
                favorites.append({"paper": snapshot(item["paper_id"]), "savedAt": item["created_at"],
                                  "note": metadata.get(item["paper_id"], {}).get("note", ""),
                                  "collection": placement.get(item["paper_id"], "全部收藏")})
            except Exception as exc:
                if getattr(exc, "status_code", None) != 404:
                    raise
                favorites.append({"paper": {"paper_id": item["paper_id"], "title": "论文当前不可访问"}, "savedAt": item["created_at"], "note": metadata.get(item["paper_id"], {}).get("note", ""), "collection": placement.get(item["paper_id"], "全部收藏")})
        for item in payload["history"]:
            try:
                history.append({"paper": snapshot(item["paper_id"]), "viewedAt": item["viewedAt"]})
            except Exception as exc:
                if getattr(exc, "status_code", None) != 404:
                    raise
        return {"version": current, "favorites": favorites, "history": history, "collections": payload["collections"]}

    @api.put("/workspace")
    def save_workspace(body: Workspace, user=Depends(store.current)):
        ids = [item.paper_id for item in body.favorites]
        if len(ids) != len(set(ids)) or len(body.history) != len({item.paper_id for item in body.history}):
            raise problem(400, "invalid_parameter", "收藏或阅读记录中有重复论文")
        names = list(dict.fromkeys(["全部收藏", *body.collections]))
        if len(names) > 100 or any(item.collection not in names for item in body.favorites):
            raise problem(400, "invalid_parameter", "收藏分类无效")
        with store.connect() as db:
            existing = {r[0] for r in db.execute("SELECT paper_id FROM favorites WHERE user_id=?", (user["id"],))}
        for paper_id in set(ids + [item.paper_id for item in body.history]) - existing:
            read_paper(paper_id)
        payload = body.model_dump(exclude={"version"})
        payload["collections"] = names
        for item in payload["favorites"]:
            item["savedAt"] = item["savedAt"] or now()
        for item in payload["history"]:
            item["viewedAt"] = item["viewedAt"] or now()
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT version,payload FROM workspaces WHERE user_id=?", (user["id"],)).fetchone()
            current = row[0] if row else 0
            native_before = native(db,user["id"])
            if revision(current, native_before) != body.version:
                raise problem(409, "workspace_conflict", "其他页面已更新阅读空间，请重新加载账户数据后再编辑")
            previous = json.loads(row["payload"]) if row else {}
            db.execute("INSERT INTO workspaces VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET version=excluded.version,payload=excluded.payload",
                       (user["id"], current + 1, json.dumps(payload, ensure_ascii=False)))
            db.execute("DELETE FROM favorites WHERE user_id=?", (user["id"],))
            db.executemany("INSERT INTO favorites VALUES(?,?,?)", [(user["id"], item["paper_id"], item["savedAt"]) for item in payload["favorites"]])
            stamp = now()
            managed = {r["name"]: r["id"] for r in db.execute("SELECT id,name FROM favorite_folders WHERE user_id=?", (user["id"],))}
            for name, fid in managed.items():
                if name not in names:
                    db.execute("DELETE FROM favorite_folders WHERE id=?", (fid,))
            for name in names:
                if name == "全部收藏":
                    continue
                if name not in managed:
                    managed[name] = db.execute("INSERT INTO favorite_folders(user_id,name,created_at,updated_at) VALUES(?,?,?,?)", (user["id"],name,stamp,stamp)).lastrowid
            old_folder_names = {r["id"]:r["name"] for r in native_before["folders"]}
            previous_categories = {r["paper_id"]:old_folder_names[r["folder_id"]] for r in native_before["items"]}
            for pid in existing - set(ids):
                db.execute("DELETE FROM favorite_folder_items WHERE paper_id=? AND folder_id IN (SELECT id FROM favorite_folders WHERE user_id=?)", (pid,user["id"]))
            for item in payload["favorites"]:
                if previous_categories.get(item["paper_id"], "全部收藏") != item["collection"]:
                    db.execute("DELETE FROM favorite_folder_items WHERE paper_id=? AND folder_id IN (SELECT id FROM favorite_folders WHERE user_id=?)", (item["paper_id"],user["id"]))
                    if item["collection"] != "全部收藏":
                        db.execute("INSERT OR IGNORE INTO favorite_folder_items VALUES(?,?,?)", (managed[item["collection"]],item["paper_id"],stamp))
            old_client = {r["paper_id"]:r["viewedAt"] for r in previous.get("history", [])}
            native_latest = {}
            for entry in native_before["history"]:
                native_latest.setdefault(entry["paper_id"], entry["accessed_at"])
            retained = {r["paper_id"] for r in payload["history"]}
            if not retained:
                db.execute("DELETE FROM browsing_history WHERE user_id=?", (user["id"],))
            else:
                visible = list(native_latest)[:50]
                for pid in set(visible) - retained:
                    db.execute("DELETE FROM browsing_history WHERE user_id=? AND paper_id=?", (user["id"],pid))
                for item in reversed(payload["history"]):
                    pid = item["paper_id"]
                    if item["viewedAt"] not in (old_client.get(pid), native_latest.get(pid)):
                        db.execute("INSERT INTO browsing_history(user_id,paper_id,accessed_at) VALUES(?,?,?)", (user["id"],pid,stamp))
                db.execute("DELETE FROM browsing_history WHERE user_id=? AND id NOT IN (SELECT id FROM browsing_history WHERE user_id=? ORDER BY id DESC LIMIT 500)", (user["id"],user["id"]))
            next_revision = revision(current + 1, native(db,user["id"]))
            db.execute("UPDATE workspaces SET payload=? WHERE user_id=?", (json.dumps(payload,ensure_ascii=False),user["id"]))
        return {"version": next_revision}

    return api
