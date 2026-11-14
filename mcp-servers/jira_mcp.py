import os
import json
import uuid
from pathlib import Path
import httpx
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

load_dotenv()
mcp = MCPServer("JiraMCP")

USE_MOCK = os.getenv("USE_MOCK", "true").lower() == "true"
MOCK_OUT = Path("evals/mock_storage/jira_created.json")
LOG_FILE = Path("evals/reports/tool_calls.jsonl")

def log_call(tool_name: str, args: dict):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"server": "jira", "tool": tool_name, "args": args}, ensure_ascii=False) + "\n")

@mcp.tool()
async def create_jira_issue(summary: str, description: str, issue_type: str = "Story") -> str:
    """Создает задачу (Story, Task, Bug) в Jira. Вызывать ТОЛЬКО после прохождения Quality Gate."""
    log_call("create_jira_issue", {"summary": summary, "issue_type": issue_type})
    project_key = os.getenv("JIRA_PROJECT_KEY", "PROJ")

    if USE_MOCK:
        MOCK_OUT.parent.mkdir(parents=True, exist_ok=True)
        existing = json.loads(MOCK_OUT.read_text(encoding="utf-8")) if MOCK_OUT.exists() else []
        issue_key = f"{project_key}-{len(existing) + 101}"
        record = {"key": issue_key, "type": issue_type, "summary": summary, "description": description}
        existing.append(record)
        MOCK_OUT.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        return json.dumps({"status": "created", "key": issue_key, "url": f"https://jira.local{issue_key}"})

    # Боевой HTTPS-запрос к Jira REST API v3
    url = f"{os.getenv('JIRA_URL')}/rest/api/3/issue"
    auth = (os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN"))
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]
            }
        }
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, auth=auth, headers={"Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()
        return json.dumps({"status": "created", "key": data["key"], "id": data["id"]})

if __name__ == "__main__":
    mcp.run()
