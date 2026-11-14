import os
import json
from pathlib import Path
import httpx
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

load_dotenv()
mcp = MCPServer("QaseMCP")

USE_MOCK = os.getenv("USE_MOCK", "true").lower() == "true"
MOCK_OUT = Path("evals/mock_storage/qase_created.json")
LOG_FILE = Path("evals/reports/tool_calls.jsonl")

def log_call(tool_name: str, args: dict):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"server": "qase", "tool": tool_name, "args": args}, ensure_ascii=False) + "\n")

@mcp.tool()
async def create_test_case(title: str, preconditions: str, steps: list[dict], severity: int = 2) -> str:
    """
    Создает тест-кейс в Qase TMS.
    steps: список словарей формата [{"action": "действие", "expected_result": "ожидаемый результат"}]
    """
    log_call("create_test_case", {"title": title, "steps_count": len(steps)})
    project_code = os.getenv("QASE_PROJECT_CODE", "DEMO")

    if USE_MOCK:
        MOCK_OUT.parent.mkdir(parents=True, exist_ok=True)
        existing = json.loads(MOCK_OUT.read_text(encoding="utf-8")) if MOCK_OUT.exists() else []
        case_id = len(existing) + 1
        record = {
            "id": case_id,
            "title": title,
            "preconditions": preconditions,
            "steps": steps,
            "severity": severity
        }
        existing.append(record)
        MOCK_OUT.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        return json.dumps({"status": "created", "case_id": case_id, "url": f"https://qase.io{project_code}-{case_id}"})

    # Боевой HTTPS-запрос к Qase API v1
    url = f"{os.getenv('QASE_URL')}/case/{project_code}"
    headers = {
        "Token": os.getenv("QASE_API_TOKEN"),
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    formatted_steps = [
        {"position": idx + 1, "action": s["action"], "expected_result": s["expected_result"]}
        for idx, s in enumerate(steps)
    ]
    payload = {
        "title": title,
        "preconditions": preconditions,
        "severity": severity,
        "steps": formatted_steps
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return json.dumps({"status": "created", "case_id": data["result"]["id"]})

if __name__ == "__main__":
    mcp.run()
