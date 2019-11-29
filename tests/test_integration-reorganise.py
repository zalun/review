# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import imp
import os
import mock
import pytest

from .conftest import git_out

mozphab = imp.load_source(
    "mozphab", os.path.join(os.path.dirname(__file__), os.path.pardir, "moz-phab")
)
mozphab.SHOW_SPINNER = False

call_conduit = mock.Mock()


def test_no_need_to_reorganise(in_process, git_repo_path, init_sha):
    # One commit
    call_conduit.side_effect = (
        dict(),  # ping
        dict(data=[dict(phid="PHID-1", id=1)]),  # differential.get_revision
        dict(data=[]),  # edge.search
    )

    f = git_repo_path / "X"
    f.write_text("A")
    git_out("add", ".")
    msgfile = git_repo_path / "msg"
    msgfile.write_text(
        """\
Bug 1: A r?alice

Differential Revision: http://example.test/D1
"""
    )
    git_out("commit", "--file", "msg")
    with pytest.raises(mozphab.Error) as e:
        mozphab.main(["reorganise", "--yes", init_sha])

    assert (str(e.value)) == "Reorganisation is not needed."

    # Stack of commits
    call_conduit.side_effect = (
        dict(data=[dict(phid="PHID-1", id=1), dict(phid="PHID-2", id=2)]),
        dict(data=[dict(sourcePHID="PHID-1", destinationPHID="PHID-2", edgeType="revision.child")]),
    )

    f.write_text("B")
    msgfile = git_repo_path / "msg"
    msgfile.write_text(
        """\
Bug 1: B r?alice

Differential Revision: http://example.test/D2
"""
    )
    git_out("commit", "-a", "--file", "msg")

    with pytest.raises(mozphab.Error) as e:
        mozphab.main(["reorganise", "--yes", init_sha])

    assert (str(e.value)) == "Reorganisation is not needed."


def test_new_separate_revisions_to_stack(in_process, git_repo_path, init_sha):
    call_conduit.side_effect = (
        dict(),  # ping
        dict(data=[dict(phid="PHID-1", id=1), dict(phid="PHID-2", id=2)]),
        dict(data=[]),  # edge.search
        dict(data=[dict(phid="PHID-1", id=1)]),  #  differential.edit_revision
    )

    f = git_repo_path / "X"
    f.write_text("A")
    git_out("add", ".")
    msgfile = git_repo_path / "msg"
    msgfile.write_text(
        """\
Bug 1: A r?alice

Differential Revision: http://example.test/D1
"""
    )
    git_out("commit", "--file", "msg")
    f.write_text("B")
    msgfile = git_repo_path / "msg"
    msgfile.write_text(
        """\
Bug 1: B r?alice

Differential Revision: http://example.test/D2
"""
    )
    git_out("commit", "-a", "--file", "msg")
    mozphab.main(["reorganise", "--yes", init_sha])
    assert (
        mock.call(
            "differential.revision.edit",
            {
                "objectIdentifier": "PHID-1",
                "transactions": [{"type": "children.set", "value": ["PHID-2"]}],
            },
        )
        in call_conduit.call_args_list
    )
