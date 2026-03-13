# Agent Architecture

## Overview

This agent is a CLI tool that answers questions using a Large Language Model (LLM) with tool-calling capabilities. It can read files and list directories from the project wiki to find accurate answers with source references.

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

The agent has two tools registered as function-calling schemas:

#### `read_file`

Reads the contents of a file from the project repository.

- **Parameters:** `path` (string) — relative path from project root (e.g., `wiki/git-workflow.md`)
- **Returns:** File contents as a string, or an error message
- **Security:** Validates path is within project root (no `../` traversal)

#### `list_files`

Lists files and directories at a given path.

- **Parameters:** `path` (string) — relative directory path from project root (e.g., `wiki`)
- **Returns:** Newline-separated list of entries, or an error message
- **Security:** Validates path is within project root (no `../` traversal)

### Path Security

Both tools validate paths to prevent accessing files outside the project:

1. Resolve the path to an absolute path
2. Check for `..` traversal attempts
3. Verify the resolved path is within `PROJECT_ROOT`
4. Return an error message to the LLM if validation fails

### System Prompt

The system prompt instructs the LLM to:

1. Use `list_files` to discover what files exist in the wiki directory
2. Use `read_file` to read relevant files and find the answer
3. Include a source reference in the answer using the format: `wiki/filename.md#section-anchor`
4. Be concise and accurate, citing sources

## Configuration

Create `.env.agent.secret` in the project root:

```bash
cp .env.agent.example .env.agent.secret
```

Edit `.env.agent.secret`:

```env
LLM_API_KEY=your-api-key-here
LLM_API_BASE=https://openrouter.ai/api/v1
LLM_MODEL=openrouter/free
```

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for authentication | `sk-or-...` |
| `LLM_API_BASE` | Base URL of the LLM API | `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | Model name to use | `openrouter/free` |

## Usage

### Basic Usage

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

### Output

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "..."
    }
  ]
}
```

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's answer to the question |
| `source` | string | Reference to the wiki section (e.g., `wiki/file.md#section`) |
| `tool_calls` | array | All tool calls made during the agentic loop |

Each tool call entry has:
- `tool` (string): Tool name (`read_file` or `list_files`)
- `args` (object): Arguments passed to the tool
- `result` (string): Tool output (truncated to 500 chars if long)

### Error Handling

- All debug/logging output goes to **stderr**
- Only valid JSON goes to **stdout**
- Exit code 0 on success, non-zero on error
- 60-second timeout on API requests
- Maximum 10 tool calls per question

## File Structure

```
project-root/
├── agent.py              # Main agent CLI with agentic loop
├── .env.agent.secret     # LLM credentials (gitignored)
├── .env.agent.example    # Example configuration
├── AGENT.md              # This documentation
├── wiki/                 # Documentation files the agent can read
│   ├── git-workflow.md
│   └── ...
└── plans/
    ├── task-1.md         # Task 1 implementation plan
    └── task-2.md         # Task 2 implementation plan
```

## Dependencies

- `httpx` — HTTP client for API requests
- Standard library: `json`, `os`, `sys`, `pathlib`, `re`

## Testing

Run the regression tests:

```bash
uv run pytest backend/tests/unit/test_agent.py -v
```

Tests verify:
- Valid JSON output with `answer`, `source`, and `tool_calls` fields
- Tool usage for documentation questions
- Source reference extraction
