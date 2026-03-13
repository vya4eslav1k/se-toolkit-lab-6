#!/usr/bin/env python3
"""CLI agent that answers questions using an LLM.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "tool_calls": []}
    All debug output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path

import httpx


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


def call_llm(question: str, config: dict[str, str], timeout: float = 60.0) -> str:
    """Call the LLM API and return the answer.
    
    Uses OpenAI-compatible chat completions API.
    """
    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. Answer questions concisely and accurately."},
            {"role": "user", "content": question},
        ],
    }
    
    print(f"Calling LLM at {url}...", file=sys.stderr)
    print(f"Model: {config['model']}", file=sys.stderr)
    
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors
        data = response.json()
    
    # Extract answer from OpenAI-compatible response format
    choices = data.get("choices", [])
    if not choices:
        raise ValueError("LLM returned no choices in response")
    
    answer = choices[0].get("message", {}).get("content", "")
    if not answer:
        raise ValueError("LLM returned empty answer")
    
    return answer


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
        # Call the LLM
        answer = call_llm(question, config)
        
        # Output result as JSON
        result = {
            "answer": answer,
            "tool_calls": [],  # Empty for Task 1, will be populated in Task 2
        }
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
