from agent.state import SQLSubgraphState


async def reflect_node(state: SQLSubgraphState) -> SQLSubgraphState:
    """Reflection and self-correction node intercepting query or validation failures."""
    retry_count = state.get("retry_count", 0) + 1
    db_error = state.get("db_error", "Unknown execution error")

    # Formulate reflection instructions for the next plan phase
    reflection_notes = (
        f"Attempt #{retry_count} failed with error: {db_error}. "
        "Correct the SQL syntax, verify table names in schema catalog, and ensure strict SELECT compliance."
    )

    return {
        "retry_count": retry_count,
        "error_message": reflection_notes,  # Read by sql_gen_node
    }
