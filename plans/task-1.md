# Task 1 Plan

**LLM Provider:** Qwen Code API  
**Model:** `meta-llama/llama-3.3-70b-instruct:free`

**Structure:**
- `agent.py` reads question from `sys.argv[1]`
- Loads `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL` from `.env.agent.secret`
- Calls `{LLM_API_BASE}/chat/completions` via `httpx`
- Outputs JSON: `{"answer": "...", "tool_calls": []}` to stdout
- Debug output goes to stderr

**Test:** Run `agent.py` as subprocess, verify JSON has `answer` and `tool_calls` fields.
