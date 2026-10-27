"""Actual local text extraction through upload, review, index, vector and download routes."""
from io import BytesIO
from docx import Document
from pypdf import PdfWriter
from backend.accounts import Store
from test_v21 import v21, token, pdf_bytes


def test_local_pdf_complete_route_and_scan_failure(v21):
    api, es, settings, root = v21
    owner=token(api,"desktop_uploader")
    other=token(api,"desktop_other")
    admin=token(api,"desktop_admin")
    with Store(str(root)).connect() as db:
        db.execute("UPDATE users SET role='admin' WHERE username='desktop_admin'")
    uploaded=api.post("/api/uploads",headers=owner,files={"file":("controlled-text.pdf",pdf_bytes(),"application/pdf")})
    assert uploaded.status_code==201
    item=uploaded.json();route="/api/admin/uploads/"+item["id"]
    assert api.get("/api/uploads/"+item["id"]+"/pdf",headers=owner).content[:5]==b"%PDF-"
    assert api.get("/api/uploads/"+item["id"]+"/pdf",headers=other).status_code==404
    assert api.post(route+"/review",headers=owner,json={"decision":"approve"}).status_code==403
    assert api.post(route+"/review",headers=admin,json={"decision":"approve"}).status_code==200
    assert api.post(route+"/process",headers=admin).status_code==202
    result=api.get("/api/uploads/"+item["id"],headers=owner).json()
    assert result["status"]=="indexed",result
    pid=result["paper_id"]
    paper=api.get("/api/papers/"+pid).json()
    assert "Controlled PDF conversion evidence" in paper["fulltext"]
    assert paper["year"] is None and paper["authors"]==[] and paper["date"]==""
    assert paper["pdf_available"] is True
    search=api.get("/api/search",params={"q":"Controlled PDF conversion evidence","mode":"keyword","field":"fulltext","phrase":"true"}).json()
    assert pid in [r["paper_id"] for r in search["results"]]
    docx=api.get("/api/papers/"+pid+"/docx")
    assert docx.status_code==200
    assert "Controlled PDF conversion evidence" in "\n".join(p.text for p in Document(BytesIO(docx.content)).paragraphs)
    chunk=es.search(index=settings.upload_vector_index,size=1)["hits"]["hits"][0]["_source"]
    assert api.get("/api/chunks/"+chunk["chunk_id"]).json()["text"]==chunk["text"]
    assert api.post("/api/admin/uploads/vectorize",headers=admin).json()["reused_chunks"]>0
    assert es.count(index=settings.index)["count"]==859
    assert api.get("/api/me/notifications",headers=owner).json()["total"]>=2
    assert api.delete(route,headers=admin).json()["source_preserved"]
    assert api.get("/api/papers/"+pid+"/pdf").status_code==200
    blank=BytesIO();writer=PdfWriter();writer.add_blank_page(width=300,height=300);writer.write(blank)
    scan=api.post("/api/admin/uploads",headers=admin,files={"file":("scan.pdf",blank.getvalue(),"application/pdf")}).json()
    scan_route="/api/admin/uploads/"+scan["id"]
    assert scan["status"]=="approved"
    assert api.post(scan_route+"/process",headers=admin).status_code==202
    failure=api.get("/api/uploads/"+scan["id"],headers=admin).json()
    assert failure["status"]=="failed" and failure["reason"]=="pdf_requires_ocr"
    assert api.get("/api/admin/uploads/"+scan["id"]+"/pdf",headers=admin).status_code==200
