"""
MCP Client Manager
==================
Manages the lifecycle of the MCP server subprocess and exposes a singleton
ClientSession for all agent nodes to share.

Usage:
    # In lifespan startup:
    await start_mcp_client()

    # In nodes:
    session = await get_mcp_session()
    result = await session.call_tool("execute_query", {...})

    # In lifespan shutdown:
    await stop_mcp_client()
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# MCP client session singleton
_mcp_session: Any | None = None
_mcp_exit_stack: Any | None = None


async def start_mcp_client() -> None:
    """Spawn the MCP server subprocess and establish a persistent ClientSession."""
    global _mcp_session, _mcp_exit_stack

    try:
        from contextlib import AsyncExitStack
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_script = str(
            Path(__file__).resolve().parent.parent / "mcp_server" / "server.py"
        )

        import os
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_script],
            env=dict(os.environ),
        )

        _mcp_exit_stack = AsyncExitStack()
        read, write = await _mcp_exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        _mcp_session = await _mcp_exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await _mcp_session.initialize()
        logger.info("MCP client connected to %s", server_script)

    except Exception as exc:
        logger.error("MCP client failed to start: %s", exc)
        _mcp_session = None


async def stop_mcp_client() -> None:
    """Shut down the MCP session and terminate the server subprocess."""
    global _mcp_session, _mcp_exit_stack
    if _mcp_exit_stack is not None:
        try:
            await _mcp_exit_stack.aclose()
            logger.info("MCP client disconnected")
        except Exception as exc:
            logger.warning("MCP client shutdown error: %s", exc)
        finally:
            _mcp_session = None
            _mcp_exit_stack = None


async def get_mcp_session() -> Any:
    """Return the active MCP ClientSession. Raises RuntimeError if not started."""
    if _mcp_session is None:
        raise RuntimeError(
            "MCP session is not initialized. Ensure start_mcp_client() "
            "was called during application startup."
        )
    return _mcp_session
