from agent.state import AgentState


async def reflect_node(state: AgentState) -> AgentState:
    """Reflection and self-correction node intercepting query or validation failures."""
    retry_count = state.get("retry_count", 0) + 1
    error_message = state.get("error_message", "Unknown execution error")

    # Formulate reflection instructions for the next plan phase
    reflection_notes = (
        f"Attempt #{retry_count} failed with error: {error_message}. "
        "Correct the SQL syntax, verify table names in schema catalog, and ensure strict SELECT compliance."
    )

    return {
        **state,
        "retry_count": retry_count,
        "error_message": reflection_notes,
        "current_phase": "reflection_retry",
    }
