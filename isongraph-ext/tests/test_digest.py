import hashlib
from pathlib import Path

from isongraph_ext.igx.digest import corpus_digest, normalize_newlines, sha256_file, sha256_hex


def test_sha256_bytes():
    assert sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_sha256_str_is_utf8_of_given_text():
    # Review Focus 2: a str is hashed exactly as given - CRLF and BOM included, nothing normalised.
    text = "﻿nodes.p\r\nid\r\n1\r\n"
    assert sha256_hex(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_sha256_file_reads_bytes_exactly(tmp_path: Path):
    p = tmp_path / "f.ison"
    p.write_bytes(b"a\r\nb")
    assert sha256_file(p) == hashlib.sha256(b"a\r\nb").hexdigest()


def test_normalize_newlines_only_touches_crlf():
    assert normalize_newlines(b"a\r\nb\nc\r") == b"a\nb\nc\r"


def test_corpus_digest_matches_core_algorithm(tmp_path: Path):
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "y.ison").write_bytes(b"Y")
    (tmp_path / "a.ison").write_bytes(b"A")
    h = hashlib.sha256()
    h.update(b"a.ison\0A\0")
    h.update(b"b/y.ison\0Y\0")
    assert corpus_digest(tmp_path) == h.hexdigest()
