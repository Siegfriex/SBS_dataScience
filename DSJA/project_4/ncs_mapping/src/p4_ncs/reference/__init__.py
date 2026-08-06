"""Offline contracts for reference-agent outputs and state transitions."""

from .contracts import (
    ReferenceAgentOutput, ReferenceRuntime, build_reference_label,
    needs_adjudication, transition_reference_state, validate_agent_output,
)

__all__ = [
    "ReferenceAgentOutput",
    "ReferenceRuntime",
    "build_reference_label",
    "needs_adjudication",
    "transition_reference_state",
    "validate_agent_output",
]
