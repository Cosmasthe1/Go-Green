"""
base_agent.py — Go Green 🌿
────────────────────────────────────────────────────────────────────────────
Core AI model wrapper shared by every Go Green agent.

Provides:
  • ShortTermMemory   – sliding-window conversation history (per rider session)
  • LongTermMemory    – persistent key-value store (rider prefs, history, saved places)
  • ToolRegistry      – maps tool names → Python callables + Anthropic schemas
  • BaseAgent         – abstract base with full tool-call agentic loop
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import anthropic

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Memory
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ShortTermMemory:
    """Sliding-window per-session conversation history."""
    max_turns: int = 30
    messages: list[dict] = field(default_factory=list)

    def add(self, role: str, content: str | list) -> None:
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > self.max_turns * 2:
            self.messages = self.messages[-(self.max_turns * 2):]

    def get_history(self) -> list[dict]:
        return list(self.messages)

    def clear(self) -> None:
        self.messages.clear()


@dataclass
class LongTermMemory:
    """
    Persistent in-process key-value store.
    Namespaces used by Go Green:
      rider:{phone}         – rider profile
      trip:{id}             – trip record
      saved:{phone}:{label} – saved places (home, work)
      prefs:{phone}         – ride preferences
    """
    store: dict[str, Any] = field(default_factory=dict)

    def remember(self, key: str, value: Any) -> None:
        self.store[key] = value

    def recall(self, key: str, default: Any = None) -> Any:
        return self.store.get(key, default)

    def forget(self, key: str) -> None:
        self.store.pop(key, None)

    def search(self, prefix: str) -> dict:
        return {k: v for k, v in self.store.items() if k.startswith(prefix)}

    def all_facts(self) -> dict:
        return dict(self.store)


# ─────────────────────────────────────────────────────────────────────────────
# Tool registry
# ─────────────────────────────────────────────────────────────────────────────

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, callable] = {}
        self._schemas: list[dict] = []

    def register(self, schema: dict, fn: callable) -> None:
        self._tools[schema["name"]] = fn
        self._schemas.append(schema)

    @property
    def schemas(self) -> list[dict]:
        return list(self._schemas)

    def call(self, name: str, inputs: dict) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        logger.info("Tool '%s' ← %s", name, inputs)
        return self._tools[name](**inputs)


# ─────────────────────────────────────────────────────────────────────────────
# BaseAgent
# ─────────────────────────────────────────────────────────────────────────────

class BaseAgent(ABC):
    DEFAULT_MODEL  = "claude-sonnet-4-20250514"
    MAX_TOOL_ITERS = 12

    def __init__(self, model: str | None = None, max_turns: int = 30) -> None:
        self.model          = model or self.DEFAULT_MODEL
        self.client         = anthropic.Anthropic()
        self.short_term     = ShortTermMemory(max_turns=max_turns)
        self.long_term      = LongTermMemory()
        self._tool_registry = ToolRegistry()
        self._register_tools()

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def system(self) -> str: ...

    def _register_tools(self) -> None:
        """Override to register tools."""

    def pre_run(self, msg: str) -> str:
        return msg

    def post_run(self, result: str) -> str:
        return result

    def run(self, user_message: str, *, inject_history: bool = True) -> str:
        user_message = self.pre_run(user_message)
        self.short_term.add("user", user_message)
        messages = (
            self.short_term.get_history() if inject_history
            else [{"role": "user", "content": user_message}]
        )
        result = self._agentic_loop(messages)
        self.short_term.add("assistant", result)
        return self.post_run(result)

    def reset_memory(self) -> None:
        self.short_term.clear()

    def _agentic_loop(self, messages: list[dict]) -> str:
        for iteration in range(self.MAX_TOOL_ITERS):
            kwargs: dict[str, Any] = {
                "model":      self.model,
                "max_tokens": 4096,
                "system":     self._build_system_prompt(),
                "messages":   messages,
            }
            if self._tool_registry.schemas:
                kwargs["tools"] = self._tool_registry.schemas

            response = self.client.messages.create(**kwargs)
            text_parts, tool_calls = [], []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(block)

            if response.stop_reason == "end_turn" or not tool_calls:
                return "\n".join(text_parts).strip()

            messages = list(messages)
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for tc in tool_calls:
                try:
                    output   = self._tool_registry.call(tc.name, tc.input)
                    content  = json.dumps(output) if not isinstance(output, str) else output
                    is_error = False
                except Exception as exc:
                    content  = f"Error: {exc}"
                    is_error = True
                    logger.warning("Tool %s failed: %s", tc.name, exc)

                tool_results.append({
                    "type": "tool_result", "tool_use_id": tc.id,
                    "content": content, "is_error": is_error,
                })

            messages.append({"role": "user", "content": tool_results})

        return "Reached maximum iterations. Please try again."

    def _build_system_prompt(self) -> str:
        base  = self.system
        facts = self.long_term.all_facts()
        if facts:
            lines = "\n".join(f"  {k}: {v}" for k, v in list(facts.items())[:15])
            base += f"\n\n## Session context\n{lines}"
        return base
