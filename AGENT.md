# Agent Architecture

## Overview

This agent is a CLI tool that answers questions using a Large Language Model (LLM). It serves as the foundation for a more advanced agent with tool-calling capabilities in later tasks.

## LLM Provider

**Provider:** Qwen Code API

**Model:** `qwen3-coder-plus`

**Why Qwen Code:**
- 1000 free requests per day
- Works from Russia without restrictions
- No credit card required
- OpenAI-compatible API

## How It Works

### Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Command Line   │ ──> │   agent.py       │ ──> │   LLM API       │
│  "Question?"    │     │  1. Parse args   │     │   (Qwen Code)   │
│                 │     │  2. Load .env    │     │                 │
│                 │     │  3. Call API     │     │                 │
│                 │     │  4. Format JSON  │     │                 │
│                 │     │  5. Output       │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                v
                        {"answer": "...", "tool_calls": []}
```

### Flow

1. **Parse arguments** — reads the question from `sys.argv[1]`
2. **Load configuration** — reads `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL` from `.env.agent.secret`
3. **Call LLM API** — sends POST request to `{LLM_API_BASE}/chat/completions` with OpenAI-compatible format
4. **Parse response** — extracts the answer from `choices[0].message.content`
5. **Output JSON** — prints `{"answer": "...", "tool_calls": []}` to stdout

### Output Format

```json
{"answer": "The LLM's response text", "tool_calls": []}
```

- `answer` (string): The LLM's answer to the question
- `tool_calls` (array): Empty for Task 1; will contain tool invocations in Task 2+

## Configuration

Create `.env.agent.secret` in the project root:

```bash
cp .env.agent.example .env.agent.secret
```

Edit `.env.agent.secret`:

```env
LLM_API_KEY=your-api-key-here
LLM_API_BASE=http://your-vm-ip:42005/v1
LLM_MODEL=qwen3-coder-plus
```

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for authentication | `sk-...` |
| `LLM_API_BASE` | Base URL of the LLM API | `http://localhost:42005/v1` |
| `LLM_MODEL` | Model name to use | `qwen3-coder-plus` |

## Usage

### Basic Usage

```bash
uv run agent.py "What does REST stand for?"
```

### Output

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

### Error Handling

- All debug/logging output goes to **stderr**
- Only valid JSON goes to **stdout**
- Exit code 0 on success, non-zero on error
- 60-second timeout on API requests

## File Structure

```
project-root/
├── agent.py              # Main agent CLI
├── .env.agent.secret     # LLM credentials (gitignored)
├── .env.agent.example    # Example configuration
├── AGENT.md              # This documentation
└── plans/
    └── task-1.md         # Implementation plan
```

## Dependencies

- `httpx` — HTTP client for API requests
- Standard library: `json`, `os`, `sys`, `pathlib`

## Testing

Run the regression test:

```bash
uv run pytest backend/tests/unit/test_agent.py -v
```

## Future Work (Tasks 2–3)

- Add tool-calling capabilities (`read_file`, `query_api`, etc.)
- Implement agentic loop for multi-step reasoning
- Expand system prompt with domain knowledge
- Add more regression tests
