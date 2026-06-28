from __future__ import annotations

TEXT_DECODING_CANDIDATES = (
    "utf-8-sig",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "gb18030",
    "latin-1",
)


def iter_text_decoding_candidates(sample: bytes | None = None) -> tuple[str, ...]:
    sample_bytes = sample or b""
    candidates = ["utf-8-sig"]
    if _should_probe_utf16(sample_bytes):
        candidates.extend(["utf-16", "utf-16-le", "utf-16-be"])
    candidates.extend(["gb18030", "latin-1"])
    return tuple(candidates)


def decode_text_bytes(raw: bytes, fallback_encoding: str = "utf-8") -> tuple[str, str]:
    for encoding in iter_text_decoding_candidates(raw):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode(fallback_encoding, errors="replace"), fallback_encoding


def _should_probe_utf16(sample: bytes) -> bool:
    if not sample:
        return False
    if sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        return True
    return b"\x00" in sample
