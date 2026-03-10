from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LLMCall:
    agent_name: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    task_id: str = ""
    call_type: str = ""
    sprint_id: str = ""
    timestamp: str = ""


class TokenLogger:
    def log_call(self, call: LLMCall) -> None:
        return None

    @staticmethod
    def calculate_cost(model: str, input_tokens: int, output_tokens: int, reasoning_tokens: int = 0) -> float:
        return 0.0
