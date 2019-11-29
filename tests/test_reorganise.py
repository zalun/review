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
        (([], ["A"]), {}),
        # Abandon
        (
            ("ABC", "A"),
            {
                "A": [{"type": "children.remove", "value": ["B"]}],
                "B": [
                    {"type": "children.remove", "value": ["C"]},
                    {"type": "abandon", "value": True},
                ],
                "C": [{"type": "abandon", "value": True}],
            },
        ),
        (
            ("ABC", "B"),
            {
                "A": [
                    {"type": "children.remove", "value": ["B"]},
                    {"type": "abandon", "value": True},
                ],
                "B": [{"type": "children.remove", "value": ["C"]}],
                "C": [{"type": "abandon", "value": True}],
            },
        ),
        (
            ("ABC", "C"),
            {
                "A": [
                    {"type": "children.remove", "value": ["B"]},
                    {"type": "abandon", "value": True},
                ],
                "B": [
                    {"type": "children.remove", "value": ["C"]},
                    {"type": "abandon", "value": True},
                ],
            },
        ),
        # Reorder
        (
            ("AB", "BA"),
            {
                "A": [{"type": "children.remove", "value": ["B"]}],
                "B": [{"type": "children.set", "value": ["A"]}],
            },
        ),
        (
            ("ABC", "BC"),
            {
                "A": [
                    {"type": "children.remove", "value": ["B"]},
                    {"type": "abandon", "value": True},
                ]
            },
        ),
        (
            ("ABC", "ACB"),
            {
                "A": [{"type": "children.set", "value": ["C"]}],
                "B": [{"type": "children.remove", "value": ["C"]}],
                "C": [{"type": "children.set", "value": ["B"]}],
            },
        ),
        (
            ("ABC", "BAC"),
            {
                "A": [{"type": "children.set", "value": ["C"]}],
                "B": [{"type": "children.set", "value": ["A"]}],
            },
        ),
        (
            ("ABC", "CAB"),
            {
                "B": [{"type": "children.remove", "value": ["C"]}],
                "C": [{"type": "children.set", "value": ["A"]}],
            },
        ),
        (
            ("ABC", "CBA"),
            {
                "A": [{"type": "children.remove", "value": ["B"]}],
                "B": [{"type": "children.set", "value": ["A"]}],
                "C": [{"type": "children.set", "value": ["B"]}],
            },
        ),
        # Insert
        (("ABC", "DABC"), {"D": [{"type": "children.set", "value": ["A"]}]}),
        (
            ("ABC", "ADBC"),
            {
                "A": [{"type": "children.set", "value": ["D"]}],
                "D": [{"type": "children.set", "value": ["B"]}],
            },
        ),
        (
            ("ABC", "ABDC"),
            {
                "B": [{"type": "children.set", "value": ["D"]}],
                "D": [{"type": "children.set", "value": ["C"]}],
            },
        ),
        (
            ("ABC", "BCAD"),
            {
                "A": [{"type": "children.set", "value": ["D"]}],
                "C": [{"type": "children.set", "value": ["A"]}],
            },
        ),
        (([], ["A", "B"]), {"A": [{"type": "children.set", "value": ["B"]}]}),
        # Insert and reorder
        (
            ("ABC", "DCAB"),
            {
                "B": [{"type": "children.remove", "value": ["C"]}],
                "C": [{"type": "children.set", "value": ["A"]}],
                "D": [{"type": "children.set", "value": ["C"]}],
            },
        ),
        (
            ("ABC", "CDAB"),
            {
                "B": [{"type": "children.remove", "value": ["C"]}],
                "C": [{"type": "children.set", "value": ["D"]}],
                "D": [{"type": "children.set", "value": ["A"]}],
            },
        ),
        (
            ("ABC", "CADB"),
            {
                "A": [{"type": "children.set", "value": ["D"]}],
                "B": [{"type": "children.remove", "value": ["C"]}],
                "C": [{"type": "children.set", "value": ["A"]}],
                "D": [{"type": "children.set", "value": ["B"]}],
            },
        ),
        (
            ("ABC", "CABD"),
            {
                "B": [{"type": "children.set", "value": ["D"]}],
                "C": [{"type": "children.set", "value": ["A"]}],
            },
        ),
        # Nothing in common
        (("A", "B"), {"A": [{"type": "abandon", "value": True}]}),
    ],
)
def test_prepare_transactions(phids, transactions):
    assert mozphab.stack_transactions(*phids) == transactions


@pytest.mark.parametrize(
    "stacks,expected",
    [
        (({"A": None}, [{"rev-id": 1, "rev-phid": "A"}]), (["A"], ["A"])),
        (({"B": None}, [{"rev-id": 1, "rev-phid": "A"}]), (["B"], ["A"])),
        (
            ({"A": "B", "B": None}, [{"rev-id": 1, "rev-phid": "A"}]),
            (["A", "B"], ["A"]),
        ),
        (
            (
                {"A": None},
                [{"rev-id": 1, "rev-phid": "A"}, {"rev-id": 2, "rev-phid": "B"}],
            ),
            (["A"], ["A", "B"]),
        ),
    ],
)
@mock.patch("mozphab.stack_transactions")
@mock.patch("mozphab.ConduitAPI.check")
@mock.patch("mozphab.augment_commits_from_body")
@mock.patch("mozphab.ConduitAPI.get_stack")
@mock.patch("mozphab.ConduitAPI.get_revisions")
@mock.patch("mozphab.ConduitAPI.id_to_phid")
@mock.patch("mozphab.ConduitAPI.phid_to_id")
@mock.patch("mozphab.ConduitAPI.edit_revision")
def test_reorg_calling_stack_transactions(
    _edit_revision,
    _phid2id,
    m_id2phid,
    _get_revs,
    m_remote_stack,
    _augment_commits,
    _check,
    m_trans,
    git,
    stacks,
    expected,
):
    class Args:
        yes = True

    phabstack, commits = stacks
    m_remote_stack.return_value = phabstack
    mozphab.conduit.set_repo(git)
    mozphab.conduit.repo.commit_stack = mock.Mock()
    mozphab.conduit.repo.commit_stack.return_value = commits
    m_id2phid.return_value = [c["rev-phid"] for c in commits]
    mozphab.reorganise(git, Args())
    m_trans.assert_called_once_with(*expected)


@mock.patch("mozphab.ConduitAPI.check")
def test_conduit_broken(m_check):
    m_check.return_value = False
    with pytest.raises(mozphab.Error) as e:
        mozphab.reorganise(None, None)

    assert str(e.value) == "Failed to use Conduit API"


@mock.patch("mozphab.ConduitAPI.check")
@mock.patch("mozphab.augment_commits_from_body")
def test_commits_invalid(_augment, _check, git):
    mozphab.conduit.set_repo(git)
    mozphab.conduit.repo.commit_stack = mock.Mock()
    mozphab.conduit.repo.commit_stack.return_value = []
    with pytest.raises(mozphab.Error) as e:
        mozphab.reorganise(git, None)

    assert str(e.value) == "Failed to find any commits to reorganise."

    mozphab.conduit.repo.commit_stack.return_value = [{"rev-id": None, "name": "A"}]
    with pytest.raises(mozphab.Error) as e:
        mozphab.reorganise(git, None)

    error = str(e.value)
    assert error.startswith("Found new commit in the local stack: A.")
