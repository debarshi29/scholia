from corpus.text import line_count, split_lines, split_lines_keepends


def test_split_lines_only_on_newline() -> None:
    assert split_lines("a\n\x0cb\r\nc") == ["a", "\x0cb", "c"]
    assert split_lines("a\n") == ["a"]
    assert split_lines("") == []


def test_keepends_roundtrip() -> None:
    text = "a\r\n\x0c\nb"
    assert "".join(split_lines_keepends(text)) == text
    assert line_count(text) == 3
