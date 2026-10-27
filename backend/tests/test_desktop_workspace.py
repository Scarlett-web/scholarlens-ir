"""Desktop aggregate adapter uses native V2.1 tables and preserves user boundaries."""
import hashlib
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.accounts import Store, router as account_router
from backend.workspace import router as workspace_router
from backend.uploads import local_pdf_to_paper


def test_workspace_native_interop_conflicts_and_user_isolation(tmp_path):
    store = Store(str(tmp_path))
    def read_paper(pid):
        if pid != "real-paper":
            raise HTTPException(404)
        return {"paper_id":pid,"title":"Real source","abstract":"Verified text","fulltext":"Text"}, "base"
    app = FastAPI()
    app.include_router(account_router(store,read_paper))
    app.include_router(workspace_router(store,read_paper))
    with TestClient(app) as api:
        def login(name):
            body={"username":name,"password":"desktop-test-password"}
            assert api.post("/api/auth/register",json=body).status_code==201
            response=api.post("/api/auth/login",json=body)
            assert response.status_code==200
            return {"Authorization":"Bearer "+response.json()["access_token"]}
        a,b=login("reader_a"),login("reader_b")
        initial=api.get("/api/me/workspace",headers=a).json()
        payload={"version":initial["version"],"collections":["全部收藏","待读"],"favorites":[{"paper_id":"real-paper","collection":"待读","note":"Private note"}],"history":[{"paper_id":"real-paper","viewedAt":"2026-10-27T00:00:00+00:00"}]}
        assert api.put("/api/me/workspace",headers=a,json=payload).status_code==200
        assert api.get("/api/me/favorites",headers=a).json()["total"]==1
        folder=api.get("/api/me/favorite-folders",headers=a).json()[0]
        assert folder["paper_count"]==1
        assert api.get("/api/me/browsing-history",headers=a).json()["total"]==1
        assert api.get("/api/me/workspace",headers=b).json()["favorites"]==[]
        assert api.put("/api/me/workspace",headers=a,json=payload).status_code==409
        before=api.get("/api/me/workspace",headers=a).json()
        api.patch("/api/me/favorite-folders/"+str(folder["id"]),headers=a,json={"name":"Native rename"})
        payload["version"]=before["version"]
        assert api.put("/api/me/workspace",headers=a,json=payload).status_code==409
        after=api.get("/api/me/workspace",headers=a).json()
        assert after["favorites"][0]["collection"]=="Native rename"
        assert after["favorites"][0]["note"]=="Private note"
        assert after["version"]!=before["version"]
        second=api.post("/api/me/favorite-folders",headers=a,json={"name":"Second category"}).json()
        assert api.put("/api/me/favorite-folders/"+str(second["id"])+"/papers",headers=a,json={"paper_id":"real-paper"}).status_code==200
        fresh=api.get("/api/me/workspace",headers=a).json()
        def body(snapshot):
            return {"version":snapshot["version"],"collections":snapshot["collections"],"favorites":[{"paper_id":r["paper"]["paper_id"],"collection":r["collection"],"note":r["note"],"savedAt":r["savedAt"]} for r in snapshot["favorites"]],"history":[{"paper_id":r["paper"]["paper_id"],"viewedAt":r["viewedAt"]} for r in snapshot["history"]]}
        edit=body(fresh);edit["favorites"][0]["note"]="Edited after native changes"
        assert api.put("/api/me/workspace",headers=a,json=edit).status_code==200
        folders=api.get("/api/me/favorite-folders",headers=a).json()
        assert sum(r["paper_count"] for r in folders)==2, "Unchanged desktop category must preserve native multiple membership"
        assert api.get("/api/me/browsing-history",headers=a).json()["total"]==1, "Editing a note after reload must not record another visit"
        edit=body(api.get("/api/me/workspace",headers=a).json())
        edit["collections"].remove("Native rename")
        assert api.put("/api/me/workspace",headers=a,json=edit).status_code==200
        assert "Native rename" not in api.get("/api/me/workspace",headers=a).json()["collections"]
        edit=body(api.get("/api/me/workspace",headers=a).json());edit["history"]=[]
        assert api.put("/api/me/workspace",headers=a,json=edit).status_code==200
        assert api.get("/api/me/browsing-history",headers=a).json()["total"]==0
        assert api.post("/api/auth/logout",headers=a).status_code==200
        assert api.get("/api/me/workspace",headers=a).status_code==401


def test_local_text_pdf_is_partial_and_blank_requires_ocr(tmp_path):
    writer=PdfWriter()
    page=writer.add_blank_page(width=300,height=300)
    font=DictionaryObject({NameObject("/Type"):NameObject("/Font"),NameObject("/Subtype"):NameObject("/Type1"),NameObject("/BaseFont"):NameObject("/Helvetica")})
    page[NameObject("/Resources")]=DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):font})})
    stream=DecodedStreamObject();stream.set_data(b"BT /F1 12 Tf 20 200 Td (Actual PDF research text.) Tj ET")
    page[NameObject("/Contents")]=writer._add_object(stream)
    path=tmp_path/"actual.pdf"
    with path.open("wb") as output:writer.write(output)
    row={"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"stored_name":"actual.pdf","original_name":"actual.pdf"}
    paper=local_pdf_to_paper(path,row)
    assert "Actual PDF research text." in paper["fulltext"]
    assert paper["parse_status"]=="partial" and paper["authors"]==[]
    assert not paper.get("year") and not paper.get("date")
    blank=PdfWriter();blank.add_blank_page(width=300,height=300)
    with path.open("wb") as output:blank.write(output)
    try:local_pdf_to_paper(path,row)
    except ValueError as exc:assert str(exc)=="pdf_requires_ocr"
    else:raise AssertionError("Blank scans must not become successful papers")
