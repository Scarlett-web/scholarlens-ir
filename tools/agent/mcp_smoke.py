"""Real MCP SDK client/subprocess smoke test; HTTP fixture is explicit by default."""
import argparse
import asyncio
import json
import sys
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import AnyUrl

ROOT = Path(__file__).resolve().parents[2]
PAPER = "source-sha256:" + "a" * 64


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/search":
            data = {"total": 1, "results": [{"paper_id": PAPER, "title": "Controlled MCP fixture"}]}
        elif path.startswith("/api/papers/") and path.endswith("/chunks"):
            data = {"total": 1, "results": [{"chunk_id": "chunk:fixture", "text": "Controlled source slice."}]}
        else:
            self.send_error(404)
            return
        self.respond(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        if self.path != "/api/agent/run" or body.get("operation") != "evidence":
            self.send_error(400)
            return
        self.respond({"answer": "", "evidence_status": "evidence_only",
                      "evidence": [{"chunk_id": "chunk:fixture", "quote": "Controlled source slice."}]})

    def respond(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def result_data(result):
    assert not result.isError, result
    return result.structuredContent or json.loads(result.content[0].text)


async def verify(origin, query):
    params = StdioServerParameters(command=sys.executable,
                                  args=["-m", "backend.mcp_server", "--api-base-url", origin], cwd=ROOT)
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write, read_timeout_seconds=timedelta(seconds=45)) as session,
    ):
        initialized = await session.initialize()
        tools = (await session.list_tools()).tools
        names = {tool.name for tool in tools}
        assert names == {"search_papers", "read_paper", "retrieve_evidence"}
        assert all(tool.annotations.readOnlyHint and not tool.annotations.destructiveHint for tool in tools)
        found = result_data(await session.call_tool("search_papers", {"query": query, "limit": 2}))
        assert found["results"] and found["total"] > 0
        paper = found["results"][0]["paper_id"]
        chunks = result_data(await session.call_tool("read_paper", {"paper_id": paper}))
        assert chunks["results"] and chunks["results"][0]["text"]
        evidence = result_data(await session.call_tool("retrieve_evidence", {"question": query}))
        assert evidence["evidence_status"] == "evidence_only" and evidence["evidence"]
        assert not evidence["answer"]
        assert (await session.call_tool("read_paper", {"paper_id": "private-upload"})).isError
        assert (await session.call_tool("search_papers", {"query": "x", "limit": 999})).isError
        resources = (await session.list_resources()).resources
        assert len(resources) == 2
        for resource in resources:
            value = await session.read_resource(AnyUrl(str(resource.uri)))
            assert value.contents and value.contents[0].text
        prompts = (await session.list_prompts()).prompts
        assert [p.name for p in prompts] == ["research_question"]
        prompt = await session.get_prompt("research_question", {"question": query})
        assert prompt.messages and query in prompt.messages[0].content.text
        return {"status": "passed", "server": initialized.serverInfo.name,
                "tools": sorted(names), "resources": len(resources), "prompts": len(prompts),
                "search_results": len(found["results"]), "evidence_count": len(evidence["evidence"]),
                "private_id_rejected": True, "invalid_limit_rejected": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", help="Explicit loopback origin for real, read-only API acceptance")
    parser.add_argument("--query", default="magnetic resonance imaging")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fixture = None
    try:
        if args.api_base_url:
            origin = args.api_base_url
        else:
            fixture = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
            Thread(target=fixture.serve_forever, daemon=True).start()
            origin = "http://127.0.0.1:" + str(fixture.server_port)
        report = asyncio.run(verify(origin, args.query))
        report.update(http_source="controlled_fixture" if fixture else "real_read_only_api",
                      provider_generation="not_tested")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    finally:
        if fixture:
            fixture.shutdown()
            fixture.server_close()


if __name__ == "__main__":
    main()
