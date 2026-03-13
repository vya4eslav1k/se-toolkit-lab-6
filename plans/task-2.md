# Task 2 Plan: The Documentation Agent

## Tool Schemas

Define two tools as OpenAI-compatible function schemas:

- `read_file(path: str)` — reads file contents, validates path is within project root
- `list_files(path: str)` — lists directory contents, validates path is within project root

Both tools will be passed in the `tools` parameter of the chat completions API request.

## Agentic Loop

1. Send user question + tool schemas to LLM
2. Parse response:
   - If `tool_calls` present → execute each tool, append results as `tool` role messages, repeat
   - If no tool calls → extract final answer and source, output JSON
3. Limit: maximum 10 tool calls per question
4. Output: `{"answer": "...", "source": "...", "tool_calls": [...]}`

## Path Security

- Resolve paths using `Path.resolve()` to get absolute path
- Check that resolved path starts with project root directory
- Reject any path with `..` traversal or outside project root
- Return error message to LLM if path is invalid

## System Prompt

Tell the LLM to:
- Use `list_files` to discover wiki files
- Use `read_file` to find answers
- Include source reference (file path + section anchor) in the answer
