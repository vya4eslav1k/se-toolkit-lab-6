#!/usr/bin/env python3
"""CLI agent that answers questions using an LLM with tools.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    All debug output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path

import httpx

# Maximum tool calls per question
MAX_TOOL_CALLS = 10

# Project root directory
PROJECT_ROOT = Path(__file__).parent.resolve()


def load_env(env_path: Path) -> dict[str, str]:
    """Load environment variables from a .env file.

    Simple parser: handles KEY=value lines, ignores comments and empty lines.
    """
    env_vars = {}
    if not env_path.exists():
        return env_vars

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            env_vars[key] = value
    return env_vars


def get_config() -> dict[str, str]:
    """Load agent configuration from environment or .env.agent.secret."""
    # First try environment variables (already set)
    api_key = os.environ.get("LLM_API_KEY", "")
    api_base = os.environ.get("LLM_API_BASE", "")
    model = os.environ.get("LLM_MODEL", "")

    # If not set, load from .env.agent.secret
    if not api_key or not api_base or not model:
        env_path = Path(__file__).parent / ".env.agent.secret"
        env_vars = load_env(env_path)
        if not api_key:
            api_key = env_vars.get("LLM_API_KEY", "")
        if not api_base:
            api_base = env_vars.get("LLM_API_BASE", "")
        if not model:
            model = env_vars.get("LLM_MODEL", "")

    return {
        "api_key": api_key,
        "api_base": api_base.rstrip("/"),
        "model": model,
    }


def validate_path(path: str) -> tuple[bool, str]:
    """Validate that a path is within the project root.

    Returns (is_valid, error_message).
    """
    # Resolve to absolute path
    resolved = (PROJECT_ROOT / path).resolve()

    # Check for path traversal
    if ".." in path:
        return False, f"Path traversal not allowed: {path}"

    # Check that resolved path is within project root
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        return False, f"Path outside project root: {path}"

    return True, ""


def read_file(path: str) -> dict:
    """Read a file from the project repository.

    Args:
        path: Relative path from project root.

    Returns:
        dict with 'content' or 'error' key.
    """
    is_valid, error = validate_path(path)
    if not is_valid:
        return {"error": error}

    file_path = PROJECT_ROOT / path
    if not file_path.exists():
        return {"error": f"File not found: {path}"}

    if not file_path.is_file():
        return {"error": f"Not a file: {path}"}

    try:
        content = file_path.read_text()
        return {"content": content}
    except Exception as e:
        return {"error": f"Failed to read file: {e}"}


def list_files(path: str) -> dict:
    """List files and directories at a given path.

    Args:
        path: Relative directory path from project root.

    Returns:
        dict with 'entries' (newline-separated) or 'error' key.
    """
    is_valid, error = validate_path(path)
    if not is_valid:
        return {"error": error}

    dir_path = PROJECT_ROOT / path
    if not dir_path.exists():
        return {"error": f"Directory not found: {path}"}

    if not dir_path.is_dir():
        return {"error": f"Not a directory: {path}"}

    try:
        entries = [entry.name for entry in dir_path.iterdir()]
        return {"entries": "\n".join(sorted(entries))}
    except Exception as e:
        return {"error": f"Failed to list directory: {e}"}


# Tool definitions for function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from the project repository. Use this to find information in documentation files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file from project root (e.g., 'wiki/git-workflow.md')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories in a given directory path. Use this to discover what files exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the directory from project root (e.g., 'wiki')",
                    }
                },
                "required": ["path"],
            },
        },
    },
]

# System prompt for the documentation agent
SYSTEM_PROMPT = """You are a documentation assistant. You have access to tools that let you read files and list directories in a project wiki.

The wiki files are located in the 'wiki/' directory.

When asked a question:
1. Use `list_files` with path="wiki" to discover what files exist in the wiki directory
2. Use `read_file` with path="wiki/filename.md" to read relevant files and find the answer
3. Include a source reference in your answer using the format: wiki/filename.md#section-anchor
4. If you find the answer, provide it along with the source reference

Always be concise and accurate. Cite your sources by including the file path and section anchor."""


def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return the result as a string."""
    if name == "read_file":
        result = read_file(args.get("path", ""))
        if "error" in result:
            return f"Error: {result['error']}"
        return result["content"]
    elif name == "list_files":
        result = list_files(args.get("path", ""))
        if "error" in result:
            return f"Error: {result['error']}"
        return result["entries"]
    else:
        return f"Error: Unknown tool: {name}"


def call_llm_with_tools(
    messages: list[dict],
    config: dict[str, str],
    timeout: float = 60.0,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> dict:
    """Call the LLM API with tool support.

    Includes retry logic for rate limiting (HTTP 429).
    """
    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
    }

    import time
    
    last_error = None
    with httpx.Client(timeout=timeout) as client:
        for attempt in range(max_retries):
            try:
                response = client.post(url, headers=headers, json=payload)
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                        print(f"  Rate limited, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})", file=sys.stderr)
                        time.sleep(wait_time)
                        continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    print(f"  Rate limited, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})", file=sys.stderr)
                    time.sleep(wait_time)
                else:
                    raise
    
    # Should not reach here, but raise the last error if we do
    if last_error:
        raise last_error
    return {"choices": []}


def run_agentic_loop(question: str, config: dict[str, str]) -> dict:
    """Run the agentic loop to answer a question.

    Returns dict with 'answer', 'source', and 'tool_calls'.
    """
    # Initialize conversation
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_calls_log = []
    tool_call_count = 0
    source = ""

    print(f"Starting agentic loop...", file=sys.stderr)

    while tool_call_count < MAX_TOOL_CALLS:
        print(f"  Iteration {tool_call_count + 1}...", file=sys.stderr)

        # Call LLM
        response_data = call_llm_with_tools(messages, config)

        # Get the assistant message
        choices = response_data.get("choices", [])
        if not choices:
            print("Error: No choices in LLM response", file=sys.stderr)
            break

        message = choices[0].get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])

        # Add assistant message to conversation
        messages.append(message)

        # Check if there are tool calls
        if not tool_calls:
            # No tool calls - this is the final answer
            print(f"  LLM provided final answer", file=sys.stderr)
            if content:
                # Try to extract source from the answer
                # Look for patterns like wiki/file.md or wiki/file.md#section
                import re
                source_match = re.search(r'(wiki/[\w-]+\.md(?:#[\w-]+)?)', content)
                if source_match:
                    source = source_match.group(1)
                else:
                    # If no source in answer, try to get it from the last read_file call
                    for tc in reversed(tool_calls_log):
                        if tc["tool"] == "read_file":
                            path = tc["args"].get("path", "")
                            if path:
                                source = path
                                break
            break

        # Execute tool calls
        for tool_call in tool_calls:
            tool_call_count += 1
            if tool_call_count > MAX_TOOL_CALLS:
                print(f"  Reached max tool calls ({MAX_TOOL_CALLS})", file=sys.stderr)
                break

            function = tool_call.get("function", {})
            tool_name = function.get("name", "unknown")
            tool_args_str = function.get("arguments", "{}")

            try:
                tool_args = json.loads(tool_args_str)
            except json.JSONDecodeError:
                tool_args = {}

            print(f"  Executing tool: {tool_name}({tool_args})", file=sys.stderr)

            # Execute the tool
            tool_result = execute_tool(tool_name, tool_args)

            # Log the tool call
            tool_calls_log.append({
                "tool": tool_name,
                "args": tool_args,
                "result": tool_result[:500] if len(tool_result) > 500 else tool_result,  # Truncate long results
            })

            # Add tool result to conversation
            tool_call_id = tool_call.get("id", f"call_{tool_call_count}")
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": tool_result,
            })

    # Build final answer
    answer = content if content else "I couldn't find enough information to answer that question."

    return {
        "answer": answer,
        "source": source,
        "tool_calls": tool_calls_log,
    }


def main() -> int:
    """Main entry point."""
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"Your question here\"", file=sys.stderr)
        return 1

    question = sys.argv[1]

    # Load configuration
    config = get_config()
    if not config["api_key"]:
        print("Error: LLM_API_KEY not set", file=sys.stderr)
        return 1
    if not config["api_base"]:
        print("Error: LLM_API_BASE not set", file=sys.stderr)
        return 1
    if not config["model"]:
        print("Error: LLM_MODEL not set", file=sys.stderr)
        return 1

    print(f"Question: {question}", file=sys.stderr)

    try:
        # Run the agentic loop
        result = run_agentic_loop(question, config)

        # Output result as JSON
        print(json.dumps(result))

        return 0

    except httpx.TimeoutException:
        print("Error: LLM request timed out", file=sys.stderr)
        return 1
    except httpx.HTTPStatusError as e:
        print(f"Error: HTTP error {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text[:200]}", file=sys.stderr)
        return 1
    except httpx.RequestError as e:
        print(f"Error: Request failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
