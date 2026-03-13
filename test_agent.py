"""Regression tests for agent.py.

These tests verify that agent.py produces valid JSON output
with the required 'answer' and 'tool_calls' fields.

Run with: uv run pytest backend/tests/unit/test_agent.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


AGENT_PATH = Path(__file__).parent.parent.parent.parent / "agent.py"


class TestAgentOutput:
    """Tests for agent.py output format."""

    @pytest.mark.asyncio
    async def test_agent_returns_valid_json(self):
        """Test that agent.py outputs valid JSON."""
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), "What is 2+2?"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        # Should exit successfully
        assert result.returncode == 0, f"Agent failed: {result.stderr}"
        
        # Should produce output
        assert result.stdout.strip(), "Agent produced no output"
        
        # Output should be valid JSON
        try:
            data = json.loads(result.stdout.strip())
        except json.JSONDecodeError as e:
            pytest.fail(f"Agent output is not valid JSON: {e}\nOutput: {result.stdout[:200]}")

    @pytest.mark.asyncio
    async def test_agent_has_answer_field(self):
        """Test that agent.py output contains 'answer' field."""
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), "What is the capital of France?"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        assert result.returncode == 0, f"Agent failed: {result.stderr}"
        
        data = json.loads(result.stdout.strip())
        
        assert "answer" in data, "Missing 'answer' field in output"
        assert isinstance(data["answer"], str), "'answer' should be a string"
        assert len(data["answer"]) > 0, "'answer' should not be empty"

    @pytest.mark.asyncio
    async def test_agent_has_tool_calls_field(self):
        """Test that agent.py output contains 'tool_calls' field."""
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), "Explain what an API is."],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        assert result.returncode == 0, f"Agent failed: {result.stderr}"
        
        data = json.loads(result.stdout.strip())
        
        assert "tool_calls" in data, "Missing 'tool_calls' field in output"
        assert isinstance(data["tool_calls"], list), "'tool_calls' should be an array"


class TestDocumentationAgent:
    """Tests for documentation agent with tool-calling capabilities."""

    @pytest.mark.asyncio
    async def test_merge_conflict_uses_read_file(self):
        """Test that agent uses read_file to answer git workflow questions."""
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), "How do you resolve a merge conflict?"],
            capture_output=True,
            text=True,
            timeout=120,  # Increased timeout for agentic loop
        )

        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        data = json.loads(result.stdout.strip())

        # Should have answer
        assert "answer" in data, "Missing 'answer' field"
        assert len(data["answer"]) > 0, "'answer' should not be empty"

        # Should have source reference to a git-related file
        assert "source" in data, "Missing 'source' field"
        source = data["source"]
        assert "git" in source.lower(), f"Source should reference a git file, got: {source}"

        # Should have used read_file tool
        assert "tool_calls" in data, "Missing 'tool_calls' field"
        assert len(data["tool_calls"]) > 0, "Should have made at least one tool call"
        tools_used = {tc.get("tool") for tc in data["tool_calls"]}
        assert "read_file" in tools_used, f"Should have used read_file, got: {tools_used}"

    @pytest.mark.asyncio
    async def test_wiki_files_uses_list_files(self):
        """Test that agent uses list_files to discover wiki files."""
        result = subprocess.run(
            [sys.executable, str(AGENT_PATH), "What files are in the wiki?"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        data = json.loads(result.stdout.strip())

        # Should have answer
        assert "answer" in data, "Missing 'answer' field"
        assert len(data["answer"]) > 0, "'answer' should not be empty"

        # Should have used list_files tool
        assert "tool_calls" in data, "Missing 'tool_calls' field"
        assert len(data["tool_calls"]) > 0, "Should have made at least one tool call"
        tools_used = {tc.get("tool") for tc in data["tool_calls"]}
        assert "list_files" in tools_used, f"Should have used list_files, got: {tools_used}"
