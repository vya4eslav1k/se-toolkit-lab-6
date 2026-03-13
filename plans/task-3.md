# Task 3 Plan: The System Agent

## query_api Tool Schema

Add a new tool `query_api` alongside `read_file` and `list_files`:

- **Name:** `query_api`
- **Description:** Call the deployed backend API to query data or check system behavior
- **Parameters:**
  - `method` (string, required): HTTP method (GET, POST, etc.)
  - `path` (string, required): API endpoint path (e.g., `/items/`)
  - `body` (string, optional): JSON request body for POST/PUT requests

## Authentication

- Read `LMS_API_KEY` from `.env.docker.secret` (or environment variable)
- Include in request header: `Authorization: Bearer {LMS_API_KEY}`
- Read `AGENT_API_BASE_URL` from environment (default: `http://localhost:42002`)

## System Prompt Update

Update the system prompt to guide the LLM on tool selection:

- Use `read_file` for wiki documentation and source code questions
- Use `list_files` to discover file structure
- Use `query_api` for:
  - Runtime data queries (database counts, analytics)
  - System behavior questions (status codes, API responses)
  - Bug diagnosis (query API, then read source to find the bug)

## Environment Variables

The agent must read from environment variables (not hardcoded):

| Variable | Purpose | Default |
|----------|---------|---------|
| `LLM_API_KEY` | LLM provider auth | from `.env.agent.secret` |
| `LLM_API_BASE` | LLM API URL | from `.env.agent.secret` |
| `LLM_MODEL` | Model name | from `.env.agent.secret` |
| `LMS_API_KEY` | Backend API auth | from `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Backend URL | `http://localhost:42002` |

## Benchmark Iteration Strategy

1. Run `uv run run_eval.py` to test all 10 questions
2. For each failure:
   - Check if correct tool was used
   - Check if tool arguments were correct
   - Check if answer contains expected keywords
3. Fix issues: improve tool descriptions, adjust system prompt, fix bugs
4. Re-run until all 10 questions pass

## Benchmark Results

**Initial Score:** Will be updated after first run

**First Failures:** Will be documented after first run

**Iteration Strategy:**
- If LLM doesn't use correct tool → improve tool description in schema
- If tool returns error → fix tool implementation
- If answer doesn't match keywords → adjust system prompt for more precise phrasing
- If agent times out → reduce max iterations or use faster model
