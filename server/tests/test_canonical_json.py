from __future__ import annotations

import pytest

from server.domain.shared.canonical_json import canonical_json, canonical_sha256
from server.domain.shared.errors import ValidationFailure

EMOJI = "\U0001F600"  # U+1F600, UTF-16 surrogate pair D83D DE00
FULLWIDTH_BANG = "！"  # U+FF01, single UTF-16 code unit


def test_key_order_is_utf16_sorted_and_stable() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert canonical_json({"é": 1, "e": 2, "z": 3}) == '{"e":2,"z":3,"é":1}'
    # RFC 8785 sorts keys by UTF-16 code units: U+1F600 is D83D DE00, so it
    # sorts before U+FF01 even though its code point is larger.
    assert canonical_json({EMOJI: 1, FULLWIDTH_BANG: 2}) == '{"' + EMOJI + '":1,"' + FULLWIDTH_BANG + '":2}'


def test_nested_structures_and_scalars() -> None:
    value = {"a": [1, True, False, None, "x"], "b": {"d": 4, "c": 3}}
    assert canonical_json(value) == '{"a":[1,true,false,null,"x"],"b":{"c":3,"d":4}}'


def test_floats_and_non_string_keys_are_rejected() -> None:
    with pytest.raises(ValidationFailure) as error:
        canonical_json({"cost": 1.5})
    assert error.value.code == "NON_CANONICAL_JSON"
    with pytest.raises(ValidationFailure):
        canonical_json({1: "x"})


def test_hash_is_stable_golden_fixture() -> None:
    payload = {"schema_version": "1.0.0", "a": "文化", "n": [1, 2, 3]}
    assert canonical_json(payload) == '{"a":"文化","n":[1,2,3],"schema_version":"1.0.0"}'
    # Fixed cross-checksum: sha256 of the UTF-8 bytes above. A TS implementation
    # must reproduce this exact value (G03 cross-language golden fixture).
    assert canonical_sha256(payload) == "893e9929704c727cbdf8c2899076ec2aeab289050bd246f72904602a6e77bd79"


def test_string_escaping_uses_shortest_form() -> None:
    assert canonical_json({"k": 'quote " backslash \\ newline \n'}) == '{"k":"quote \\" backslash \\\\ newline \\n"}'
    assert canonical_json({"k": "\u0001"}) == '{"k":"\\u0001"}'
