"""Phase 2 — Preprocessing & cleaning tests."""

from __future__ import annotations

from pipeline import preprocessing


def test_preprocess_empty_string():
    result = preprocessing.preprocess("")
    assert result.cleaned_text == ""
    assert result.sentences == []
    assert result.tokens == []
    assert result.language is None
    assert result.duplicate_lines_removed == 0


def test_preprocess_collapses_extra_whitespace():
    raw = "Hello     world\t\t!"
    result = preprocessing.preprocess(raw)
    assert "Hello world" in result.cleaned_text
    # Tab/space runs collapsed to single spaces
    assert "  " not in result.cleaned_text


def test_preprocess_strips_control_chars():
    raw = "Clean\x00\x07Text"
    result = preprocessing.preprocess(raw)
    assert "\x00" not in result.cleaned_text
    assert "\x07" not in result.cleaned_text
    assert "CleanText" in result.cleaned_text


def test_preprocess_dedupes_long_repeated_lines():
    line = "This is a long repeated header that should be deduplicated"
    raw = "\n".join([line, "Body content here", line, line])
    result = preprocessing.preprocess(raw)
    assert result.duplicate_lines_removed == 2
    assert result.cleaned_text.count(line) == 1


def test_preprocess_does_not_dedupe_short_lines():
    # Short legitimate repeats (field labels) must survive
    raw = "Name:\nJohn\nName:\nJane"
    result = preprocessing.preprocess(raw)
    assert result.cleaned_text.count("Name:") == 2
    assert result.duplicate_lines_removed == 0


def test_preprocess_drops_page_numbers():
    raw = "Real content\n\n1\n\nPage 2 of 10\n\nMore content"
    result = preprocessing.preprocess(raw)
    assert "Real content" in result.cleaned_text
    assert "More content" in result.cleaned_text
    # Bare page-number lines stripped
    lines = [l for l in result.cleaned_text.splitlines() if l.strip()]
    assert "1" not in lines
    assert not any(l.lower().startswith("page ") for l in lines)


def test_preprocess_collapses_3plus_blank_lines():
    raw = "A\n\n\n\n\nB"
    result = preprocessing.preprocess(raw)
    # 3+ newlines should collapse to exactly 2
    assert "\n\n\n" not in result.cleaned_text
    assert "A" in result.cleaned_text and "B" in result.cleaned_text


def test_preprocess_detects_english(resume_text):
    result = preprocessing.preprocess(resume_text)
    assert result.language == "en"


def test_preprocess_returns_sentences_and_tokens(resume_text):
    result = preprocessing.preprocess(resume_text)
    assert len(result.sentences) > 0
    assert len(result.tokens) > 0
    # Every token should be non-empty and non-whitespace
    assert all(t.strip() for t in result.tokens)


def test_preprocess_short_text_no_language():
    # langdetect skips very short strings
    result = preprocessing.preprocess("Hi.")
    assert result.language is None
