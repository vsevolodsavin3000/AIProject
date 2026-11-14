# Мультиагентная ИИ-система автоматизации работы с требованиями (OpenCode)

Система автоматизирует полный цикл анализа требований: получение спецификации из **Confluence** $\rightarrow$ ревью и проверка безопасности (**Quality Gate**) $\rightarrow$ декомпозиция на задачи в **Jira** $\rightarrow$ генерация тест-кейсов в **Qase TMS**.

## Архитектура
- **Orchestrator** (`.opencode/agents/orchestrator.md`) — управляет маршрутизацией и блокирует пайплайн при обнаружении дефектов или Prompt Injection.
- **Requirement Review Agent** — проверяет полноту, противоречия, неоднозначности и инъекции.
- **Task Management Agent** — формирует User Stories с критериями приемки и создает их в Jira.
- **Test Design Agent** — применяет техники тест-дизайна (EP, BVA) и создает тест-кейсы в Qase.

## Быстрый старт

1. **Установка зависимостей:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Настройка переменных окружения:**
   ```bash
   cp .env.example .env
   # Укажите USE_MOCK=false и реальные токены для работы с боевыми API
   ```
3. **Запуск обработки страницы Confluence:**
   ```bash
   opencode run "Обработай требования со страницы Confluence ID: 123456"
   ```
4. **Запуск автоматического тестирования (Golden Dataset + LLM-as-a-Judge):**
   ```bash
   python evals/run_evals.py
   ```
   Результаты и расчет **Pass Rate** сохраняются в `evals/reports/summary_report.md`.
