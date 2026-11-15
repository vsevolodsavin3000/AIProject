import os
import re
import html
import json
from pathlib import Path
import httpx
from dotenv import load_dotenv

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

load_dotenv()
mcp = MCPServer("ConfluenceMCP")

USE_MOCK = os.getenv("USE_MOCK_CONFLUENCE", os.getenv("USE_MOCK", "true")).lower() == "true"
MOCK_DIR = Path("evals/mock_storage/confluence")
LOG_FILE = Path("evals/reports/tool_calls.jsonl")


def log_call(tool_name: str, args: dict):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"server": "confluence", "tool": tool_name, "args": args}, ensure_ascii=False) + "\n")


def clean_html(raw_html: str) -> str:
    """Превращает Confluence storage XHTML в чистый читаемый текст."""
    text = re.sub(r"<(br|p|div|h[1-6]|li|tr)[^>]*>", "\n", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


@mcp.tool()
async def get_page_requirements(page_id: str) -> str:
    """
    Получает текст требований со страницы Confluence по её числовому ID (например, '3604481').
    Если передан полный URL страницы, автоматически извлекает ID.
    """
    # На случай если агент передаст всю ссылку целиком вместо ID
    match = re.search(r"/pages/(\d+)", str(page_id))
    clean_id = match.group(1) if match else str(page_id).strip()

    log_call("get_page_requirements", {"page_id": clean_id})

    if USE_MOCK:
        mock_file = MOCK_DIR / f"{clean_id}.json"
        if not mock_file.exists():
            return json.dumps({"error": f"Mock page {clean_id} not found"}, ensure_ascii=False)
        data = json.loads(mock_file.read_text(encoding="utf-8"))
        return json.dumps({"id": clean_id, "title": data.get("title", clean_id), "body": data["body"]}, ensure_ascii=False)

    base_url = os.getenv("CONFLUENCE_URL", "").rstrip("/")
    url = f"{base_url}/api/v2/pages/{clean_id}?body-format=storage"
    auth = (os.getenv("CONFLUENCE_EMAIL"), os.getenv("CONFLUENCE_API_TOKEN"))

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, auth=auth, headers={"Accept": "application/json"})
        if resp.status_code == 404:
            return json.dumps({"error": f"Страница {clean_id} не найдена или нет прав доступа."}, ensure_ascii=False)
        if resp.status_code == 401:
            return json.dumps({"error": "Ошибка авторизации (401). Проверь CONFLUENCE_EMAIL и CONFLUENCE_API_TOKEN."}, ensure_ascii=False)
        resp.raise_for_status()
        data = resp.json()

        clean_body = clean_html(data["body"]["storage"]["value"])
        return json.dumps({
            "id": data["id"],
            "title": data["title"],
            "body": clean_body
        }, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
