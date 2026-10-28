import test from "node:test";
import assert from "node:assert/strict";
import {createPaperApi, normalizePaper, buildSearchParams} from "../src/services/paperApi.ts";
import {serverHighlightParts} from "../src/lib/serverHighlight.ts";
import {buildPaperGraph} from "../src/lib/paperRelations.ts";
import {highlightParts} from "../src/lib/highlight.ts";
import {paginationItems} from "../src/lib/pagination.ts";

const query = {q:" magnetic ",field:"all",page:2,pageSize:6,sort:"newest",mode:"keyword",yearFrom:1990,yearTo:2026};
const reply = data => new Response(JSON.stringify(data), {headers:{"Content-Type":"application/json"}});

test("real contract maps summaries, nested parser state and page count without inventing fields", () => {
  const paper = normalizePaper({paper_id:"source-sha256:test",title:"Real delivery",abstract_snippet:"Actual abstract",
    highlights:{fulltext:["A <em>magnetic</em> field"]},source_status:{parse_status:"partial"},pages:{first:15,last:20,count:6}});
  assert.equal(paper.abstract,"Actual abstract");
  assert.equal(paper.parse_status,"partial");
  assert.equal(paper.pages,6);
  assert.equal(paper.highlight.fulltext[0],"A <em>magnetic</em> field");
  assert.deepEqual(paper.topics,[]);
  assert.equal(paper.pdf_available,false);
});

test("sort, mode, pagination and years use FastAPI vocabulary", () => {
  const params = buildSearchParams(query);
  assert.equal(params.get("sort"),"year_desc");
  assert.equal(params.get("q"),"magnetic");
  assert.equal(params.get("page"),"2");
  assert.equal(params.get("page_size"),"6");
  assert.equal(params.get("year_from"),"1990");
  assert.equal(buildSearchParams({...query,sort:"oldest",mode:"hybrid"}).get("sort"),"year_asc");
  assert.equal(buildSearchParams({...query,mode:"semantic"}).get("mode"),"semantic");
  assert.throws(()=>buildSearchParams({...query,sort:"title"}),/不支持/);
});

test("API summaries create only supplied institution relations without invented topic fields", () => {
  const papers = [
    {paper_id:"synthetic-a",title:"Fixture A",authors:["Author A"],affiliation:["Fixture university"]},
    {paper_id:"synthetic-b",title:"Fixture B",authors:["Author B"],affiliation:["Fixture university"]},
    {paper_id:"synthetic-c",title:"Fixture C",authors:[]}
  ].map(normalizePaper);
  assert.ok(papers.every(paper=>paper.topics.length===0 && paper.keywords.length===0));
  const graph=buildPaperGraph(papers);
  assert.equal(graph.edges.length,1);
  assert.deepEqual(graph.edges[0].reasons,[{kind:"affiliation",value:"Fixture university"}]);
  assert.equal(graph.nodes.find(node=>node.paper.paper_id==="synthetic-c").degree,0);
});

test("search keeps actual server count, zero score, highlights and elapsed time", async () => {
  let requested;
  const api = createPaperApi("/api/", async url => {
    requested = url;
    return reply({total:25,page:2,page_size:6,took_ms:8,results:[{paper_id:"p",title:"Paper",score:0,abstract_snippet:"Abstract",highlights:{title:["<em>Paper</em>"]}}]});
  });
  const result = await api.search(query);
  assert.ok(requested.startsWith("/api/search?"));
  assert.equal(result.total,25);
  assert.equal(result.papers[0].score,0);
  assert.deepEqual(result.papers[0].highlight.title,["<em>Paper</em>"]);
  assert.equal(result.durationMs,8);
});

test("blank browsing uses discover selection, not invalid search or a false library total", async () => {
  const api = createPaperApi("/api", async url => {
    assert.equal(url,"/api/discover?limit=20");
    return reply({papers:859,recommendations:[{paper_id:"a",year:2024},{paper_id:"b",year:2000}],example_searches:[],years:[]});
  });
  const result = await api.search({...query,q:"",page:1,pageSize:6,yearFrom:2020});
  assert.equal(result.total,1);
  assert.equal(result.papers[0].paper_id,"a");
  assert.equal(result.durationMs,null);
});

test("detail encodes stable source IDs and treats only 404 as missing", async () => {
  const api = createPaperApi("/api", async url => {
    assert.equal(url,"/api/papers/source-sha256%3Aabc");
    return new Response("",{status:404});
  });
  assert.equal(await api.paper("source-sha256:abc"),null);
  await assert.rejects(createPaperApi("/api",async()=>new Response("",{status:503})).paper("p"),/503/);
});

test("backend dependency reasons are shown and failure never becomes synthetic results", async () => {
  const api = createPaperApi("/api",async()=>new Response(JSON.stringify({error:{code:"dependency_unavailable",message:"向量索引尚未就绪"}}),{status:503}));
  await assert.rejects(api.search(query),/向量索引尚未就绪/);
});

test("non-JSON proxy output is an error", async () => {
  await assert.rejects(createPaperApi("/api",async()=>new Response("<html>Vite</html>")).stats(),/有效 JSON/);
});

test("suggestions preserve author field; capabilities require explicit ready", async () => {
  const api = createPaperApi("/api",async url => url.includes("suggest")
    ? reply({suggestions:[{text:"A. Author",field:"authors"}]})
    : reply({modules:{keyword_search:{status:"ready",reason:"索引可用"},semantic_search:{status:"dependency_unavailable",reason:"模型缺失"}}}));
  assert.deepEqual(await api.suggestions("Author"),[{text:"A. Author",field:"authors"}]);
  const capabilities = await api.capabilities();
  assert.equal(capabilities.keyword.ready,true);
  assert.equal(capabilities.semantic.ready,false);
  assert.equal(capabilities.hybrid.ready,false);
});

test("server highlights decode as text, and cannot create executable HTML", () => {
  const parts = serverHighlightParts("&lt;img src=x onerror=alert(1)&gt; <em>magnetic &amp; field</em>");
  assert.equal(parts[0].text,"<img src=x onerror=alert(1)> ");
  assert.deepEqual(parts.find(part=>part.match),{text:"magnetic & field",match:true});
});

test("query highlighting ignores connective noise, respects word boundaries, and keeps Chinese and literal input", () => {
  const matches=(value,q)=>highlightParts(value,q).filter(part=>part.match).map(part=>part.text);
  assert.deepEqual(matches("The dynamics of the aurora", "Simulating the Dynamics of the Dancing Lights"),["dynamics"]);
  assert.deepEqual(matches("office software of the lab", "of"),["of"]);
  assert.deepEqual(matches("theory and theater the", "the"),["the"]);
  assert.deepEqual(matches("中文文献的信息检索与全文检索", "中文 检索"),["中文","检索","检索"]);
  assert.deepEqual(matches("C++ and C++17", "C++"),["C++"]);
  assert.equal(highlightParts("<script>text</script>",".*").map(p=>p.text).join(""),"text");
  assert.deepEqual(matches("of the", "of the"),["of","the"]);
});

test("pagination shows readable first, middle and last windows without silent gaps", () => {
  assert.deepEqual(paginationItems(1,37),[1,2,3,4,5,"gap-right",37]);
  assert.deepEqual(paginationItems(18,37),[1,"gap-left",17,18,19,"gap-right",37]);
  assert.deepEqual(paginationItems(37,37),[1,"gap-left",33,34,35,36,37]);
  assert.deepEqual(paginationItems(4,7),[1,2,3,4,5,6,7]);
  for(let total=1;total<=60;total++)for(let page=1;page<=total;page++){
    const items=paginationItems(page,total),numbers=items.filter(n=>typeof n==='number');
    assert.ok(numbers.includes(1)&&numbers.includes(page)&&numbers.includes(total));
    assert.equal(new Set(items).size,items.length);
    assert.ok(items.length<=9);
    for(let i=1;i<items.length;i++)if(typeof items[i-1]==='number'&&typeof items[i]==='number')assert.equal(items[i]-items[i-1],1);
    assert.ok(items.every((n,i)=>typeof n==='number'||(typeof items[i-1]==='number'&&typeof items[i+1]==='number'&&items[i+1]-items[i-1]>2)));
  }
});
