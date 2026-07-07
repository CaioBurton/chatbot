from app.ingestion.chunker import _split_by_tokens


class _FakeEncoder:
    """One token per character — deterministic and network-free (no tiktoken
    BPE download), unlike tiktoken.get_encoding() which needs network access."""

    def encode(self, s: str, disallowed_special=()):
        return list(s)


_enc = _FakeEncoder()


def test_split_by_tokens_overlap_zero_matches_no_overlap_behavior():
    text = "palavra " * 500
    no_overlap = _split_by_tokens(text, max_tokens=32, enc=_enc, overlap_tokens=0)
    default_arg = _split_by_tokens(text, max_tokens=32, enc=_enc)
    assert no_overlap == default_arg
    assert len(no_overlap) > 1


def test_split_by_tokens_with_overlap_repeats_trailing_words():
    words = [f"palavra{i}" for i in range(60)]
    text = " ".join(words)
    segments = _split_by_tokens(text, max_tokens=20, enc=_enc, overlap_tokens=5)
    assert len(segments) > 1
    # Every segment after the first must share its leading word(s) with the
    # trailing word of the previous segment (the sliding-window overlap).
    for prev, cur in zip(segments, segments[1:]):
        prev_words = prev.split()
        cur_words = cur.split()
        assert prev_words[-1] in cur_words


def test_split_by_tokens_single_word_longer_than_max_tokens():
    huge_word = "a" * 5000  # 5000 "tokens" under the 1-char-per-token fake encoder
    text = f"{huge_word} depois outra palavra normal"
    segments = _split_by_tokens(text, max_tokens=8, enc=_enc, overlap_tokens=4)
    assert segments
    # Must terminate (no infinite loop) and must not lose any word.
    assert segments[0].split() == [huge_word]
    assert " ".join(segments).split() == text.split()


def test_split_by_tokens_empty_text_returns_empty_list():
    assert _split_by_tokens("", max_tokens=32, enc=_enc, overlap_tokens=8) == []
    assert _split_by_tokens("   ", max_tokens=32, enc=_enc, overlap_tokens=8) == []
