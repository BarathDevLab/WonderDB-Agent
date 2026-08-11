"""
chat_node
=========
Handles two non-data intents:
  - "chat"       : greetings, help, small talk — no DB access needed
  - "contextual" : follow-up on previous turn ("simpler", "continue",
                   "explain above") — reads session memory for context
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from agent.state import GlobalState
from app.config import get_settings
from services.session_memory import get_session_history, append_session_event

logger = logging.getLogger(__name__)


_GREETING_KEYWORDS = frozenset(["hi", "hello", "hey", "hiya", "howdy", "good morning", "good evening"])
_HELP_KEYWORDS = frozenset(["help", "what can you do", "how does this work", "what do you do", "capabilities"])
_SIMPLER_KEYWORDS = ["simpler", "simple", "plain english", "layman", "easy", "explain simpler"]
_CONTINUE_KEYWORDS = ["continue", "tell me more", "more", "go on", "elaborate", "more details", "and?"]
_EXPLAIN_ABOVE_KEYWORDS = ["explain above", "explain that", "explain this", "what does this mean", "what does that mean"]


async def _call_gemini(system_instruction: str, user_content: str) -> str:
    """Make a single Gemini generateContent call and return the text response."""
    settings = get_settings()
    if not settings.gemini_api_key or not settings.gemini_model:
        return "I'm here to help! Ask me to query your database, generate charts, or draw ER diagrams."

    try:
        model_name = settings.gemini_model.strip()
        if model_name.startswith("models/"):
            model_name = model_name[len("models/"):]
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{system_instruction}\n\n{user_content}"}]}],
            "generationConfig": {"temperature": 0.7},
        }
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model_name}:generateContent?key={settings.gemini_api_key}")
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                data = res.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as exc:
        logger.warning("chat_node Gemini call failed: %s", exc)

    return "I'm here to help! Ask me to query your database, generate charts, or draw ER diagrams."


def _build_context_from_history(history: list[dict[str, Any]]) -> str:
    """Build a context string from the last relevant session events."""
    # Find the most recent query/summary event
    for event in reversed(history):
        phase = event.get("phase", "")
        if phase in ("plan", "summary"):
            parts = []
            if event.get("prompt"):
                parts.append(f"Previous question: {event['prompt']}")
            if event.get("sql_query"):
                parts.append(f"SQL executed: {event['sql_query']}")
            if event.get("summary"):
                parts.append(f"Previous answer: {event['summary']}")
            if event.get("rows_count") is not None:
                parts.append(f"Rows returned: {event['rows_count']}")
            return "\n".join(parts)
    return ""


async def chat_node(state: GlobalState) -> GlobalState:
    """Handle chat and contextual follow-up intents."""
    plan = state.get("supervisor_plan", {})
    intent = plan.get("intent", "chat")
    prompt = state.get("prompt", "").strip()
    session_id = state.get("session_id", "default")
    prompt_lower = prompt.lower()

    context = ""
    system_msg = ""

    if intent == "contextual":
        # Load session history for context-aware response
        history = await get_session_history(session_id)
        context = _build_context_from_history(history)

        if any(kw in prompt_lower for kw in _SIMPLER_KEYWORDS):
            system_msg = (
                "You are a friendly data analyst. The user wants you to re-explain "
                "the previous database query result in very simple, non-technical, "
                "plain English that anyone can understand. Avoid SQL and technical jargon."
            )
        elif any(kw in prompt_lower for kw in _CONTINUE_KEYWORDS):
            system_msg = (
                "You are a senior data analyst. The user wants you to continue the analysis "
                "and provide additional insights, trends, or observations from the previous result."
            )
        elif any(kw in prompt_lower for kw in _EXPLAIN_ABOVE_KEYWORDS):
            system_msg = (
                "You are a data analyst. Explain the previous database query result "
                "in detail — what the data shows, what it means for the business, "
                "and any notable patterns."
            )
        else:
            system_msg = (
                "You are a helpful AI database assistant. Answer the user's follow-up "
                "question using the context from the previous database query."
            )

        user_content = f"{context}\n\nUser follow-up: {prompt}" if context else prompt

    else:  # intent == "chat"
        if any(kw in prompt_lower for kw in _GREETING_KEYWORDS) or prompt_lower in _GREETING_KEYWORDS:
            system_msg = (
                "You are a friendly and enthusiastic AI database assistant named DataBot. "
                "Greet the user warmly and briefly explain your capabilities in 2-3 sentences: "
                "you can query databases using natural language, generate bar/line/pie/scatter charts, "
                "draw ER diagrams and process flow diagrams, and explain data in plain language."
            )
        elif any(kw in prompt_lower for kw in _HELP_KEYWORDS):
            system_msg = (
                "You are a helpful AI database assistant. Explain your capabilities clearly:\n"
                "1. Query databases with natural language (e.g. 'show top 10 customers by revenue')\n"
                "2. Generate charts: bar, line, pie, scatter plots\n"
                "3. Draw diagrams: ER diagrams, process flows, decision trees\n"
                "4. Explain data and results in plain language\n"
                "Give examples of questions the user can ask."
            )
        else:
            system_msg = (
                "You are a helpful AI database assistant. Answer the user's question. "
                "If it's not database-related, gently guide them to ask database questions."
            )
        user_content = prompt

    reply = await _call_gemini(system_msg, user_content)

    await append_session_event(session_id, {
        "phase": "chat",
        "intent": intent,
        "prompt": prompt,
        "summary": reply,
    })

    return {
        "summary": reply,
        "current_phase": "chat_complete",
    }
