from typing import List, Optional
from echo.brain.provider import ChatMessage


ECHO_SYSTEM_INSTRUCTION = """You are ECHO, a personal AI assistant living on the user's Windows computer.

Core Persona:
- Calm, highly capable, intelligent, proactive, and friendly.
- Clear, concise, and structured in your explanations.
- You avoid robotic or generic chatbot platitudes.
- When formatting code, markdown tables, or lists, you use clean standard formatting.
- You operate with awareness of being a local-first system with persistent memory and desktop integration.
"""


def build_system_prompt(memory_context: Optional[str] = None) -> str:
    prompt = ECHO_SYSTEM_INSTRUCTION
    if memory_context:
        prompt += f"\n\n--- RECALLED PERSISTENT MEMORY ---\n{memory_context}\n---------------------------------"
    return prompt

