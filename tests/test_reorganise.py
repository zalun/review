# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import imp
import json
import mock
import os
import pytest
from contextlib import contextmanager
from frozendict import frozendict

mozphab = imp.load_source(
    "mozphab", os.path.join(os.path.dirname(__file__), os.path.pardir, "moz-phab")
)


@pytest.mark.parametrize(
    "phids,transactions",
    [
        # No change
        (("A", "A"), {}),
        (("ABC", "ABC"), {}),
        # Abandon
        (
            ("ABC", "A"),
            {
                "abandon": ["B", "C"],
                "children.set": [("B", None), ("C", None), ("A", None)],
            },
        ),
        (
            ("ABC", "B"),
            {
                "abandon": ["A", "C"],
                "children.set": [("A", None), ("C", None), ("B", None)],
            },
        ),
        (
            ("ABC", "C"),
            {"abandon": ["A", "B"], "children.set": [("A", None), ("B", None)],},
        ),
        # Reorder
        (("AB", "BA"), {"children.set": [("A", None), ("B", "A")]}),
        (("ABC", "BC"), {"abandon": ["A"], "children.set": [("A", None)],}),
        (("ABC", "ACB"), {"children.set": [("A", "C"), ("B", None), ("C", "B")]}),
        (("ABC", "BAC"), {"children.set": [("A", "C"), ("B", "A")]}),
        (("ABC", "CAB"), {"children.set": [("B", None), ("C", "A")]}),
        (("ABC", "CBA"), {"children.set": [("A", None), ("B", "A"), ("C", "B")]}),
        # Insert
        (("ABC", "DABC"), {"children.set": [("D", "A")]}),
        (("ABC", "ADBC"), {"children.set": [("D", "B"), ("A", "D")]}),
        (("ABC", "ABDC"), {"children.set": [("D", "C"), ("B", "D")]}),
        (("ABC", "BCAD"), {"children.set": [("D", None), ("A", "D"), ("C", "A")]}),
        # Insert and reorder
        (("ABC", "DCAB"), {"children.set": [("D", "C"), ("B", None), ("C", "A")]}),
        (("ABC", "CDAB"), {"children.set": [("D", "A"), ("B", None), ("C", "D")]}),
        (
            ("ABC", "CADB"),
            {"children.set": [("D", "B"), ("A", "D"), ("B", None), ("C", "A")]},
        ),
        (("ABC", "CABD"), {"children.set": [("D", None), ("B", "D"), ("C", "A")]}),
        # Nothing in common
        (("A", "B"), {"abandon": ["A"], "children.set": [("A", None), ("B", None)]}),
    ],
)
def test_prepare_transactions(phids, transactions):
    assert mozphab.prepare_transactions(*phids) == transactions


@pytest.mark.parametrize(
    "params,expected",
    [
        ((["A"], [{"rev-phid": "A"}]), (["A"], ["A"])),
        ((["B"], [{"rev-phid": "A"}]), (["B"], ["A"])),
        ((["A"], [{"rev-phid": None}]), (["A"], ["0"])),
        ((["A"], [{"rev-phid": None}, {"rev-phid": "A"}]), (["A"], ["0", "A"])),
        ((["A"], [{"rev-phid": "A"}, {"rev-phid": None}]), (["A"], ["A", "1"])),
    ],
)
@mock.patch("mozphab.prepare_transactions")
def test_reorg_calling_prepare_transactions(m_trans, params, expected):
    mozphab.prepare_reorg(*params)
    m_trans.assert_called_once_with(*expected)


@mock.patch("mozphab.prepare_transactions")
def test_not_calling_prepare_transactions(m_trans):
    # New revision
    assert mozphab.prepare_reorg([], [{"rev-id": None}]) is None
    m_trans.assert_not_called()
