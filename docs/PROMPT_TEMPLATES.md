# AI Coding Agent Prompts

## Prompt 1: Initializing a Module
"Using the constraints in `.cursorrules` and `ARCHITECTURE.md`, implement `[module_name.py]`. 
Ensure all I/O functions are fully asynchronous (`async`/`await`), include explicit type hints, 
and adhere strictly to Pydantic v2 models."

## Prompt 2: Refactoring for SSE Alignment
"Review `src/agent/sse.py`. Ensure every state transition emitted by `graph.astream()` 
is converted into a valid SSE wire event frame (`event: <name>\ndata: <json>\n\n`) 
and yielded immediately to prevent buffering."

## Prompt 3: Adding Security Safeguards
"Implement `src/services/ast_service.py` using `sqlglot`. Ensure it parses raw SQL, 
verifies the root statement is `exp.Select`, and rejects any query containing DML commands 
or multi-statement execution."