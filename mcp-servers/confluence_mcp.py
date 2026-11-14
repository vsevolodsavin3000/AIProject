import os
import json
from pathlib import Path
import httpx
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

load_dotenv()
mcp = MCPServer("ConfluenceMCP")

USE_MOCK = os.getenv("USE_MOCK", "true").lower() == "true"
MOCK_DIR = Path("evals/mock_storage/confluence")
LOG_FILE = Path("evals/reports/tool_calls.jsonl")


def log_call(tool_name: str, args: dict):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"server": "confluence", "tool": tool_name, "args": args}, ensure_ascii=False) + "\n")


@mcp.tool()
async def get_page_requirements(page_id: str) -> str:
    """Получает текст требований со страницы Confluence по её ID."""
    log_call("get_page_requirements", {"page_id": page_id})

    if USE_MOCK:
        mock_file = MOCK_DIR / f"{page_id}.json"
        if not mock_file.exists():
            return json.dumps({"error": f"Mock page {page_id} not found"}, ensure_ascii=False)
        data = json.loads(mock_file.read_text(encoding="utf-8"))
        return json.dumps({"id": page_id, "title": data.get("title", page_id), "body": data["body"]},
                          ensure_ascii=False)

    # Боевой HTTPS-запрос к Confluence REST API v2
    url = f"{os.getenv('CONFLUENCE_URL')}/api/v2/pages/{page_id}?body-format=storage"
    auth = (os.getenv("CONFLUENCE_EMAIL"), os.getenv("CONFLUENCE_API_TOKEN"))

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, auth=auth, headers={"Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()
        return json.dumps({
            "id": data["id"],
            "title": data["title"],
            "body": data["body"]["storage"]["value"]
        }, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
