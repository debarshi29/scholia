"""Token counting for the Constrained-mode context cap (invariant 3.2).

Counts use the real Qwen tokenizer (``LOCAL_TOKENIZER``) on the fully rendered ChatML
prompt, i.e. exactly what Ollama feeds the model, special tokens included. Gemini
counts in Realistic mode reuse the same counter and are approximate.
"""

from typing import Protocol

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class TokenCounter(Protocol):
    name: str

    def count(self, text: str) -> int: ...


def render_chatml(messages: list[ChatMessage]) -> str:
    """Qwen2.5 chat template, with the generation prompt for the assistant turn."""
    body = "".join(f"<|im_start|>{m.role}\n{m.content}<|im_end|>\n" for m in messages)
    return body + "<|im_start|>assistant\n"


def count_messages(counter: TokenCounter, messages: list[ChatMessage]) -> int:
    return counter.count(render_chatml(messages))


class HFTokenCounter:
    """Hugging Face ``tokenizers`` counter. Loading may download ``tokenizer.json`` once
    into the HF cache, so construct it off the event loop (``asyncio.to_thread``)."""

    def __init__(self, name: str) -> None:
        from tokenizers import Tokenizer

        self.name = name
        self._tok = Tokenizer.from_pretrained(name)

    def count(self, text: str) -> int:
        return len(self._tok.encode(text, add_special_tokens=False).ids)
