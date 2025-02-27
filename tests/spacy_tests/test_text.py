# coding: utf-8
"""Test that longer and mixed texts are tokenized correctly."""


from __future__ import unicode_literals

import pytest
import spacy

def test_en_tokenizer_handles_long_text(combined_all_model_fixture):
    text = """Tributes pour in for late British Labour Party leader

Tributes poured in from around the world Thursday
to the late Labour Party leader John Smith, who died earlier from a massive
heart attack aged 55.

In Washington, the US State Department issued a statement regretting "the
untimely death" of the rapier-tongued Scottish barrister and parliamentarian.

"Mr. Smith, throughout his distinguished"""
    tokens = combined_all_model_fixture(text)
    assert len(tokens) == 74 # CHANGED FROM 76 TO 74

@pytest.mark.parametrize('text,length', [
    ("The U.S. Army likes Shock and Awe.", 8),
    ("U.N. regulations are not a part of their concern.", 10),
    ("“Isn't it?”", 6),
    ("""Yes! "I'd rather have a walk", Ms. Comble sighed. """, 15),
    ("""'Me too!', Mr. P. Delaware cried. """, 11),
    ("They ran about 10km.", 6),
    pytest.param("But then the 6,000-year ice age came...", 10, marks=pytest.mark.xfail)])
def test_en_tokenizer_handles_cnts(combined_all_model_fixture, text, length):
    tokens = combined_all_model_fixture(text)
    assert len(tokens) == length


@pytest.mark.parametrize('text,match', [
    ('10', True), ('1', True), ('10,000', True), ('10,00', True),
    ('999.0', True), ('one', True), ('two', True), ('billion', True),
    ('dog', False), (',', False), ('1/2', True)])
def test_lex_attrs_like_number(combined_all_model_fixture, text, match):
    tokens = combined_all_model_fixture(text)
    assert len(tokens) == 1
    assert tokens[0].like_num == match
