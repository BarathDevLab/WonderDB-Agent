"""
chat_node
=========
Handles two non-data intents dispatched by the supervisor:

  intent = "chat"       → Greetings, help requests, small talk.
                          No database access. No session memory read.
  intent = "contextual" → Follow-up on the previous turn's result.
                          Reads session memory for context, then answers.

The node makes a single Gemini call with a carefully constructed system
instruction that matches the sub-intent detected from the user's words.
"""
from __future__ import annotations

from typing import Any

import httpx

from agent.state import GlobalState
from app.config import get_settings
from services.session_memory import get_session_history, append_session_event
from services.conversation_context import format_context_for_model
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Keyword sets ────────────────────────────────────────────────────────────

_GREETING_KEYWORDS = frozenset([
    "hi", "hello", "hey", "hiya", "howdy",
    "good morning", "good evening", "good afternoon",
    "greetings", "sup", "yo",
])
_HELP_KEYWORDS = frozenset([
    "help", "what can you do", "how does this work",
    "what do you do", "capabilities", "features",
    "what are you", "tell me about yourself",
])
_SIMPLER_KEYWORDS = [
    "simpler", "simple", "plain english", "layman", "easy",
    "explain simpler", "in simple terms", "dumb it down",
]
_CONTINUE_KEYWORDS = [
    "continue", "tell me more", "more", "go on",
    "elaborate", "more details", "and?", "keep going",
]
_EXPLAIN_KEYWORDS = [
    "explain above", "explain that", "explain this",
    "what does this mean", "what does that mean",
    "break it down", "break this down",
]


def _looks_like_identity_question(prompt: str) -> bool:
    """Detect identity/ownership questions that should be answered as WonderDB Agent."""
    if not prompt:
        return False
    text = prompt.lower().strip("?!. ")
    identity_markers = (
        "who are you",
        "who are you?",
        "what are you",
        "who is wonderdb agent",
        "who developed you",
        "who built you",
        "who created you",
        "who is your owner",
        "who owns you",
        "who is your developer",
        "who is the developer of wonderdb agent",
        "who made you",
        "who owns wonderdb agent",
    )
    return any(marker in text for marker in identity_markers)


async def _call_gemini(system_instruction: str, user_content: str) -> str:
    """Make a single Gemini generateContent call and return the text response."""
    settings = get_settings()
    if not settings.gemini_api_key or not settings.gemini_model:
        return "I am WonderDB Agent — a natural-language database assistant that can query your database, generate charts, and explain results. Ask me anything about your data or schema."

    try:
        model_name = settings.gemini_model.strip()
        if model_name.startswith("models/"):
            model_name = model_name[len("models/"):]

        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{system_instruction}\n\n{user_content}"}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 512},
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={settings.gemini_api_key}"
        )
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                data = res.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as exc:
        logger.warning("chat_node Gemini call failed: %s", exc)

    return "I'm here to help! Ask me to query your database, generate charts, or draw ER diagrams."


def _build_context_from_history(history: list[dict[str, Any]]) -> str:
    """Extract the most recent meaningful query/summary event for context."""
    for event in reversed(history):
        phase = event.get("phase", "")
        if phase in ("plan", "summary"):
            parts: list[str] = []
            if event.get("prompt"):
                parts.append(f"Previous question: {event['prompt']}")
            if event.get("sql_query"):
                parts.append(f"SQL executed: {event['sql_query']}")
            if event.get("summary"):
                parts.append(f"Previous answer: {event['summary']}")
            if event.get("rows_count") is not None:
                parts.append(f"Rows returned: {event['rows_count']}")
            if parts:
                return "\n".join(parts)
    return ""


async def chat_node(state: GlobalState) -> GlobalState:
    """Handle chat and contextual follow-up intents."""
    plan = state.get("supervisor_plan", {})
    intent = plan.get("intent", "chat")
    prompt = state.get("prompt", "").strip()
    tenant_id = state.get("tenant_id", "default-tenant")

    # Bug fix: was defaulting to literal "default" which could cause
    # session collision if multiple tenants sent chat messages simultaneously.
    session_id = state.get("session_id") or f"session-{tenant_id}"

    logger.info(f"Chat node starting for session {session_id}. Intent: {intent}")

    prompt_lower = prompt.lower()
    context = ""
    system_msg = ""

    if intent == "contextual":
        structured_context = state.get("conversation_context", {})
        if structured_context.get("is_followup"):
            context = format_context_for_model(structured_context)
        else:
            history = [
                event for event in await get_session_history(session_id)
                if event.get("tenant_id") == tenant_id
            ]
            context = _build_context_from_history(history)

        if any(kw in prompt_lower for kw in _SIMPLER_KEYWORDS):
            system_msg = (
                "You are a friendly data analyst. The user wants you to re-explain "
                "the previous database query result in very simple, non-technical, "
                "plain English that anyone can understand. Avoid SQL and technical jargon. "
                "Use analogies and everyday language."
            )
        elif any(kw in prompt_lower for kw in _CONTINUE_KEYWORDS):
            system_msg = (
                "You are a senior data analyst. Continue the analysis from the previous result. "
                "Provide additional insights, trends, patterns, or observations. "
                "Be specific — reference actual numbers and values from the data."
            )
        elif any(kw in prompt_lower for kw in _EXPLAIN_KEYWORDS):
            system_msg = (
                "You are a data analyst writing a business intelligence narrative. "
                "Explain the previous database query result in detail: "
                "what the data shows, what it means for the business, "
                "any notable patterns or anomalies, and actionable implications."
            )
        else:
            system_msg = (
                "You are a helpful AI database assistant. "
                "Answer the user's follow-up question using the context from the previous database query. "
                "Be specific and reference the data where relevant."
            )

        user_content = f"{context}\n\nUser follow-up: {prompt}" if context else prompt

    else:  # intent == "chat"
        is_greeting = any(kw in prompt_lower for kw in _GREETING_KEYWORDS)
        is_help = any(kw in prompt_lower for kw in _HELP_KEYWORDS)
        is_identity = _looks_like_identity_question(prompt)

        if is_identity:
            system_msg = (
                "You are WonderDB Agent, the database analytics assistant in this application. "
                "Answer identity questions directly and briefly: state that you are WonderDB Agent, "
                "that you help users query databases in plain language, generate charts and diagrams, "
                "and explain results. If asked who developed or owns you, say that WonderDB Agent is the project agent built by the WonderDB development team behind this application. "
                "Keep it concise, friendly, and confident."
            )
        elif is_greeting:
            system_msg = (
                "You are WonderDB Agent, a friendly and enthusiastic database assistant. "
                "Greet the user warmly and briefly explain your capabilities in 2-3 sentences: "
                "you can query databases using natural language, generate bar/line/pie/scatter charts, "
                "draw ER diagrams and process flow diagrams, and explain data in plain language. "
                "Keep the response concise and inviting."
            )
        elif is_help:
            system_msg = (
                "You are WonderDB Agent. Explain your capabilities clearly and concisely:\n"
                "1. Query databases with natural language (e.g. 'show top 10 customers by revenue')\n"
                "2. Generate charts: bar, line, pie, scatter\n"
                "3. Draw diagrams: ER diagrams, process flows, decision trees\n"
                "4. Explain data results in plain language\n"
                "Give 2-3 example questions the user can try."
            )
        else:
            system_msg = (
                "You are WonderDB Agent, a helpful database assistant. Answer the user's question. "
                "If the question is not related to databases or data analysis, "
                "politely explain that you specialise in database queries and analytics, "
                "and suggest they rephrase as a data question."
            )
        user_content = prompt

    reply = await _call_gemini(system_msg, user_content)

    await append_session_event(session_id, {
        "phase": "chat",
        "intent": intent,
        "prompt": prompt,
        "tenant_id": tenant_id,
        "summary": reply,
    })

    return {
        "summary": reply,
        "current_phase": "chat_complete",
    }
