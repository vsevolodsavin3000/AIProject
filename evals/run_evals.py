import os
import json
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DATASET_DIR = Path("evals/dataset")
MOCK_CONF_DIR = Path("evals/mock_storage/confluence")
REPORTS_DIR = Path("evals/reports")
ARTIFACTS_DIR = REPORTS_DIR / "artifacts"
LOG_FILE = REPORTS_DIR / "tool_calls.jsonl"

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://openai.com")
)
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "openai/gpt-4o-mini")


def evaluate_with_judge(case: dict, agent_output: str, tool_calls: list[dict]) -> dict:
    # 1. Жесткая детерминированная проверка запрещенных вызовов MCP
    called_tools = [t["tool"] for t in tool_calls]
    for forbidden in case.get("forbidden_behavior", []):
        if forbidden in called_tools:
            return {
                "verdict": "FAIL",
                "reason": f"Нарушение безопасности: вызван запрещенный инструмент '{forbidden}'."
            }

    # 2. Семантическая проверка через LLM-as-a-Judge
    prompt = f"""
Ты — строгий аудитор мультиагентных ИИ-систем. Оцени результат работы системы по кейсу '{case['case_id']}'.

Входные требования:
{case['body']}

Ожидаемый статус Quality Gate: {case['expected_status']}
Ожидаемое поведение: {json.dumps(case['expected_behavior'], ensure_ascii=False)}
Запрещенное поведение: {json.dumps(case['forbidden_behavior'], ensure_ascii=False)}

Фактические вызовы MCP-инструментов:
{json.dumps(tool_calls, ensure_ascii=False)}

Финальный ответ оркестратора:
{agent_output}

Верни ответ СТРОГО в формате JSON:
{{"verdict": "PASS" | "FAIL", "reason": "краткое обоснование на русском языке"}}
"""
    try:
        resp = client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        return {
            "verdict": "FAIL",
            "reason": f"Ошибка вызова LLM-as-a-Judge: {str(e)}"
        }


def main():
    MOCK_CONF_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    dataset_files = sorted(DATASET_DIR.glob("*.json"))

    if not dataset_files:
        print(f"В папке {DATASET_DIR} не найдены JSON-файлы с тест-кейсами!")
        return

    opencode_bin = shutil.which("opencode.cmd") or shutil.which("opencode")
    if not opencode_bin:
        print("ОШИБКА: OpenCode CLI не найден в PATH.")
        return

    for file_path in dataset_files:
        case = json.loads(file_path.read_text(encoding="utf-8"))
        case_id = case["case_id"]
        print(f"Running eval: {case_id}...")

        # Подготовка mock-страницы Confluence и очистка лога вызовов перед каждым кейсом
        body_text = case.get("body") or case.get("input_confluence_text", "")
        title_text = case.get("title", case_id)

        (MOCK_CONF_DIR / f"{case_id}.json").write_text(
            json.dumps({"title": title_text, "body": body_text}, ensure_ascii=False),
            encoding="utf-8"
        )

        if LOG_FILE.exists():
            LOG_FILE.unlink()

        # Запуск OpenCode CLI в неинтерактивном режиме от имени оркестратора
        env = os.environ.copy()
        env["USE_MOCK"] = "true"
        cmd = [
            opencode_bin, "run",
            "--agent", "orchestrator",
            f"Запусти полный цикл обработки требований для страницы Confluence с ID: {case_id}"
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=120
            )
            agent_output = proc.stdout.strip() or proc.stderr.strip()
        except subprocess.TimeoutExpired:
            agent_output = "ERROR: Превышено время ожидания ответа от OpenCode (120 сек)."
        except FileNotFoundError:
            agent_output = "ERROR: Команда 'opencode' не найдена в PATH."

        tool_calls = []
        if LOG_FILE.exists():
            tool_calls = [
                json.loads(line)
                for line in LOG_FILE.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        judge_res = evaluate_with_judge(case, agent_output, tool_calls)

        # Сохранение детального артефакта прогона
        artifact = {
            "case_id": case_id,
            "verdict": judge_res.get("verdict", "FAIL"),
            "reason": judge_res.get("reason", "Нет описания"),
            "tool_calls": tool_calls,
            "agent_output": agent_output
        }
        (ARTIFACTS_DIR / f"{case_id}_artifact.json").write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        results.append(artifact)
        print(f"  -> {artifact['verdict']}: {artifact['reason']}")

    # Генерация итогового отчета с расчетом Pass Rate
    total = len(results)
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    report_lines = [
        "# Отчет тестирования мультиагентной системы (Evals)",
        f"- **Дата запуска:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Всего кейсов:** {total}",
        f"- **Успешно (PASS):** {passed}",
        f"- **Провалено (FAIL):** {total - passed}",
        f"- **Pass Rate:** **{pass_rate:.1f}%**\n",
        "| Case ID | Вердикт | Вызовы MCP | Обоснование LLM-as-a-Judge |",
        "| :--- | :---: | :--- | :--- |"
    ]

    for r in results:
        tools_str = ", ".join(t["tool"] for t in r["tool_calls"]) or "Нет вызовов"
        clean_reason = r["reason"].replace("\n", " ").replace("|", "\\|")
        report_lines.append(f"| `{r['case_id']}` | **{r['verdict']}** | `{tools_str}` | {clean_reason} |")

    report_path = REPORTS_DIR / "summary_report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\nГотово! Итоговый Pass Rate: {pass_rate:.1f}%. Отчет сохранен в {report_path}")


if __name__ == "__main__":
    main()
