# Agent Architecture

## Overview

This agent is a CLI tool that answers questions using a Large Language Model (LLM) with tool-calling capabilities. It can read files, list directories, and query a deployed backend API to find accurate answers with source references.

## LLM Provider

**Provider:** OpenRouter (free tier)  
**Model:** `openrouter/free` (router that selects from available free models)

## How It Works

### Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Command Line   │ ──> │   agent.py       │ ──> │   LLM API       │
│  "Question?"    │     │  Agentic Loop    │     │   (OpenRouter)  │
│                 │     │  1. Send + tools │     │                 │
│                 │     │  2. Get tool call│     │                 │
│                 │     │  3. Execute tool │     │                 │
│                 │     │  4. Feed result  │     │                 │
│                 │     │  5. Repeat/Answer│     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                v
                {"answer": "...", "source": "...", "tool_calls": [...]}
```

### Agentic Loop

1. **Send question + tool schemas** to the LLM
2. **Parse response:**
   - If `tool_calls` present → execute each tool, append results as `tool` role messages, repeat
   - If no tool calls → extract final answer and source, output JSON
3. **Limit:** Maximum 10 tool calls per question
4. **Output:** `{"answer": "...", "source": "...", "tool_calls": [...]}`

### Tools

The agent has three tools registered as function-calling schemas:

#### `read_file`

Reads the contents of a file from the project repository.

- **Parameters:** `path` (string) — relative path from project root (e.g., `wiki/git-workflow.md`, `backend/app/main.py`)
- **Returns:** File contents as a string, or an error message
- **Security:** Validates path is within project root (no `../` traversal)
- **Use cases:** Wiki documentation, source code analysis, configuration files

#### `list_files`

Lists files and directories at a given path.

- **Parameters:** `path` (string) — relative directory path from project root (e.g., `wiki`, `backend/app/routers`)
- **Returns:** Newline-separated list of entries, or an error message
- **Security:** Validates path is within project root (no `../` traversal)
- **Use cases:** Discovering file structure, finding relevant files

#### `query_api`

Calls the deployed backend API to query runtime data or check system behavior.

- **Parameters:**
  - `method` (string, required) — HTTP method (GET, POST, PUT, DELETE)
  - `path` (string, required) — API endpoint path (e.g., `/items/`, `/analytics/completion-rate`)
  - `body` (string, optional) — JSON request body for POST/PUT requests
- **Returns:** JSON string with `status_code` and `body`, or error message
- **Authentication:** Uses `LMS_API_KEY` from environment or `.env.docker.secret`
- **Use cases:** Database queries, analytics, status code checks, bug reproduction

### Tool Selection Strategy

The system prompt guides the LLM on when to use each tool:

| Question Type | Tool to Use |
|--------------|-------------|
| Wiki documentation | `list_files` → `read_file` |
| Source code analysis | `read_file` |
| Runtime data (counts, analytics) | `query_api` |
| API behavior (status codes) | `query_api` |
| Bug diagnosis | `query_api` → `read_file` |
| System architecture | `read_file` (docker-compose.yml, Dockerfile) |

### Path Security

Both file tools validate paths to prevent accessing files outside the project:

1. Resolve the path to an absolute path
2. Check for `..` traversal attempts
3. Verify the resolved path is within `PROJECT_ROOT`
4. Return an error message to the LLM if validation fails

### System Prompt

The system prompt instructs the LLM to:

1. Use the right tool for each question type
2. Include source references when reading files
3. Be concise and accurate
4. Chain tools for complex tasks (e.g., query API error → read source to find bug)

## Configuration

### Environment Variables

The agent reads all configuration from environment variables (with fallback to `.env` files):

| Variable | Purpose | Source | Default |
|----------|---------|--------|---------|
| `LLM_API_KEY` | LLM provider authentication | `.env.agent.secret` | — |
| `LLM_API_BASE` | LLM API base URL | `.env.agent.secret` | — |
| `LLM_MODEL` | Model name | `.env.agent.secret` | — |
| `LMS_API_KEY` | Backend API authentication | `.env.docker.secret` | — |
| `AGENT_API_BASE_URL` | Backend API base URL | `.env.docker.secret` or env | `http://localhost:42002` |

**Important:** The autochecker injects its own values for these variables. Never hardcode credentials.

### Setup

```bash
# LLM configuration
cp .env.agent.example .env.agent.secret
# Edit with your LLM provider credentials

# Backend API configuration
cp .env.docker.example .env.docker.secret
# Edit with your backend credentials
```

## Usage

### Basic Usage

```bash
# Wiki question
uv run agent.py "How do you resolve a merge conflict?"

# Source code question
uv run agent.py "What framework does the backend use?"

# Runtime data question
uv run agent.py "How many items are in the database?"

# Bug diagnosis
uv run agent.py "Why does /analytics/completion-rate crash for lab-99?"
```

### Output

```json
{
  "answer": "There are 42 items in the database.",
  "source": "",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": [...]}"
    }
  ]
}
```

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's answer to the question |
| `source` | string | Reference to source file (optional for API questions) |
| `tool_calls` | array | All tool calls made during the agentic loop |

Each tool call entry has:
- `tool` (string): Tool name
- `args` (object): Arguments passed to the tool
- `result` (string): Tool output (truncated to 500 chars if long)

### Error Handling

- All debug/logging output goes to **stderr**
- Only valid JSON goes to **stdout**
- Exit code 0 on success, non-zero on error
- 60-second timeout on LLM API requests
- 30-second timeout on backend API requests
- Maximum 10 tool calls per question
- Retry logic with exponential backoff for rate limiting (HTTP 429)

## File Structure

```
project-root/
├── agent.py              # Main agent CLI with agentic loop
├── .env.agent.secret     # LLM credentials (gitignored)
├── .env.docker.secret    # Backend API credentials (gitignored)
├── AGENT.md              # This documentation
├── wiki/                 # Documentation files
├── backend/              # Backend source code
└── plans/
    ├── task-1.md         # Task 1: Basic LLM integration
    ├── task-2.md         # Task 2: Documentation agent
    └── task-3.md         # Task 3: System agent with query_api
```

## Dependencies

- `httpx` — HTTP client for API requests
- Standard library: `json`, `os`, `sys`, `pathlib`, `re`, `time`

## Testing

Run the regression tests:

```bash
uv run pytest backend/tests/unit/test_agent.py -v
```

Tests verify:
- Valid JSON output with required fields
- Tool usage for different question types
- Source reference extraction
- API tool integration

## Lessons Learned

### Challenge 1: Rate Limiting

The OpenRouter free tier has a 50 requests/day limit and can be unreliable. I added retry logic with exponential backoff (2s, 4s delays) to handle transient rate limiting. For production use, Qwen Code API (1000 requests/day) is more reliable.

### Challenge 2: Tool Selection

Initially, the LLM would sometimes call `read_file` for runtime data questions. I improved the tool descriptions and system prompt to clearly distinguish when to use each tool:
- `read_file` for static content (docs, source code)
- `query_api` for runtime data (database, API responses)

### Challenge 3: Source References

The agent needs to cite sources for wiki/code questions but not for API questions. I made the `source` field optional and extract it from the answer text or the last `read_file` call.

### Challenge 4: Path Security

Preventing path traversal attacks was critical. I validate all paths by:
1. Checking for `..` patterns
2. Resolving to absolute paths
3. Verifying the path is within `PROJECT_ROOT`

### Challenge 5: Environment Variables

The autochecker injects different credentials, so I ensured the agent:
- Reads from environment variables first
- Falls back to `.env` files only if env vars are not set
- Never hardcodes any credentials

## Benchmark Performance

The agent is tested against 10 local questions covering:
- Wiki lookups (branch protection, SSH)
- Source code analysis (framework, routers)
- Runtime data queries (item count, status codes)
- Bug diagnosis (ZeroDivisionError, TypeError)
- System architecture (request lifecycle, ETL idempotency)

Local evaluation: Run `uv run run_eval.py` to test all questions.
