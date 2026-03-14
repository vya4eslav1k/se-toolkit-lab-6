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
MAX_TOOL_CALLS = 20

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
            "description": "Read the contents of a file from the project repository. Use this to find information in documentation files or source code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file from project root (e.g., 'wiki/git-workflow.md' or 'backend/app/main.py')",
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
                        "description": "Relative path to the directory from project root (e.g., 'wiki' or 'backend/app/routers')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Call the deployed backend API to query data, check system behavior, or diagnose bugs. Use this for runtime questions about the database, API responses, or status codes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE, etc.)",
                    },
                    "path": {
                        "type": "string",
                        "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate')",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional JSON request body for POST/PUT requests",
                    },
                    "use_auth": {
                        "type": "boolean",
                        "description": "Whether to include the Authorization header (default: true). Set to false to test unauthenticated requests.",
                    },
                },
                "required": ["method", "path"],
            },
        },
    },
]

# System prompt for the agent
SYSTEM_PROMPT = """You are a system assistant with access to three tools:

1. `read_file` - Read files from the project repository (wiki documentation, source code, config files)
2. `list_files` - List files and directories in the project
3. `query_api` - Call the deployed backend API to query runtime data

When asked a question:
- For wiki documentation questions: use `list_files` to discover files, then `read_file` to find answers
- For source code questions: use `read_file` to read the relevant source files
- For runtime data questions (database counts, analytics, API behavior): use `query_api`
- For bug diagnosis: use `query_api` to reproduce the error, then `read_file` to find the bug in source code
- For system architecture questions: read config files like `docker-compose.yml`, `Dockerfile`, and `Caddyfile`

IMPORTANT - TOOL CALL EFFICIENCY:
- You have a maximum of 15 tool calls per question - use them wisely
- After reading 3-5 key files, STOP and provide your answer in the next response
- Do NOT keep exploring after you have enough information
- For "explain the journey" or "trace the flow" questions: read the main config files (docker-compose.yml, Dockerfile, Caddyfile, main.py) then synthesize the answer
- After gathering information, respond with just your answer (no more tool calls) to end the conversation

Include source references when reading files (e.g., wiki/file.md#section or backend/file.py:function).
For multi-part questions, synthesize all information into one comprehensive answer.
"""


def get_lms_config() -> dict[str, str]:
    """Load LMS backend configuration from environment or .env.docker.secret."""
    # First try environment variables
    lms_api_key = os.environ.get("LMS_API_KEY", "")
    agent_api_base_url = os.environ.get("AGENT_API_BASE_URL", "http://localhost:42002")

    # If not set, load from .env.docker.secret
    if not lms_api_key:
        env_path = Path(__file__).parent / ".env.docker.secret"
        env_vars = load_env(env_path)
        lms_api_key = env_vars.get("LMS_API_KEY", "")

    return {
        "api_key": lms_api_key,
        "base_url": agent_api_base_url.rstrip("/"),
    }


def query_api(method: str, path: str, body: str = None, use_auth: bool = True) -> str:
    """Call the deployed backend API.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API endpoint path
        body: Optional JSON request body
        use_auth: Whether to include the Authorization header (default: True)

    Returns:
        JSON string with status_code and body, or error message.
    """
    config = get_lms_config()
    url = f"{config['base_url']}{path}"
    headers = {
        "Content-Type": "application/json",
    }
    
    # Only add Authorization header if use_auth is True
    if use_auth:
        headers["Authorization"] = f"Bearer {config['api_key']}"

    print(f"  Calling API: {method} {url} (auth: {use_auth})", file=sys.stderr)

    try:
        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                data = json.loads(body) if body else {}
                response = client.post(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                data = json.loads(body) if body else {}
                response = client.put(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return f"Error: Unsupported method: {method}"

            result = {
                "status_code": response.status_code,
                "body": response.json() if response.text else None,
            }
            return json.dumps(result)
    except httpx.HTTPStatusError as e:
        return json.dumps({"status_code": e.response.status_code, "error": str(e), "body": e.response.text[:500]})
    except httpx.RequestError as e:
        return json.dumps({"error": f"Request failed: {e}"})
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON body: {e}"})
    except Exception as e:
        return json.dumps({"error": f"API call failed: {e}"})


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
    elif name == "query_api":
        method = args.get("method", "GET")
        path = args.get("path", "")
        body = args.get("body")
        use_auth = args.get("use_auth", True)  # Default to True for backward compatibility
        return query_api(method, path, body, use_auth)
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
