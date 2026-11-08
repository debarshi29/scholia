import pytest

from api.backends.base import ChatMessage
from api.tokens import HFTokenCounter, count_messages, render_chatml


class CharCounter:
    name = "chars"

    def count(self, text: str) -> int:
        return len(text)


MSGS = [ChatMessage(role="system", content="sys"), ChatMessage(role="user", content="hi")]


def test_render_chatml_matches_qwen_template() -> None:
    assert render_chatml(MSGS) == (
        "<|im_start|>system\nsys<|im_end|>\n<|im_start|>user\nhi<|im_end|>\n<|im_start|>assistant\n"
    )


def test_count_messages_counts_rendered_prompt() -> None:
    assert count_messages(CharCounter(), MSGS) == len(render_chatml(MSGS))


@pytest.mark.live
def test_real_qwen_tokenizer_counts_special_tokens_once() -> None:
    counter = HFTokenCounter("Qwen/Qwen2.5-Coder-3B-Instruct")
    # <|im_start|> system \n hi <|im_end|> \n
    assert counter.count("<|im_start|>system\nhi<|im_end|>\n") == 6
    assert count_messages(counter, MSGS) > counter.count("sys") + counter.count("hi")
