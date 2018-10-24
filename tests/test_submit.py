import copy
import imp
import mock
import os
import sys
import unittest

review = imp.load_source(
    "review", os.path.join(os.path.dirname(__file__), os.path.pardir, "moz-phab")
)


def reviewers_dict(reviewers=None):
    return dict(
        request=reviewers[0] if reviewers else [],
        granted=reviewers[1] if reviewers else [],
    )


def commit(bug_id=None, reviewers=None, body="", name="", title=""):
    return {
        "name": name,
        "title": title,
        "bug-id": bug_id,
        "reviewers": reviewers_dict(reviewers),
        "body": body,
    }


# noinspection PyPep8Naming,PyBroadException
class Commits(unittest.TestCase):
    def _assertNoError(self, callableObj, *args):
        try:
            callableObj(*args)
        except review.Error:
            info = sys.exc_info()
            self.fail("%s raised" % repr(info[0]))

    def _assertError(self, callableObj, *args):
        try:
            callableObj(*args)
        except review.Error:
            return
        except Exception:
            info = sys.exc_info()
            self.fail("%s raised" % repr(info[0]))
        self.fail("%s failed to raise Error" % callableObj)

    def test_commit_validation(self):
        repo = review.Repository(None, None, "dummy")
        check = repo.check_commits_for_submit

        self._assertNoError(check, [])
        self._assertNoError(check, [commit("1", (["r"], []))])
        self._assertNoError(
            check,
            [
                commit("1", (["r1"], [])),
                commit("2", (["r1"], [])),
                commit("3", (["r1", "r2"], [])),
            ],
        )
        self._assertNoError(check, [commit("1", None)])
        self._assertNoError(check, [commit("1", (["r"], [])), commit("1", None)])

        self._assertError(check, [commit(None, (["r"], []))])
        self._assertError(check, [commit("", (["r"], []))])
        self._assertError(
            check, [commit("1", (["r"], []), body="Summary: blah\nReviewers: r")]
        )

        self._assertError(check, [commit("1", (["r"], [])), commit("", (["r"], []))])

    def test_commit_preview(self):
        build = review.build_commit_title

        self.assertEqual(
            "Bug 1, blah, r=turnip",
            build(commit("1", ([], ["turnip"]), title="bug 1, blah, r=turnip")),
        )
        self.assertEqual(
            "blah (Bug 1) r=turnip",
            build(commit("1", ([], ["turnip"]), title="blah (bug 1) r=turnip")),
        )
        self.assertEqual(
            "Bug 1 - blah r?turnip",
            build(commit("1", (["turnip"], []), title="blah r?turnip")),
        )

        self.assertEqual(
            "blah r=turnip", build(commit("", ([], ["turnip"]), title="blah r=turnip"))
        )
        self.assertEqual(
            "Bug 1 - blah", build(commit("1", None, title="Bug 1 - blah r?turnip"))
        )
        self.assertEqual(
            "Bug 1 - blah", build(commit("1", None, title="Bug 1 - blah r=turnip"))
        )
        self.assertEqual(
            "Bug 1 - helper_bug2.html",
            build(commit("1", None, title="Bug 1 - helper_bug2.html")),
        )

    @mock.patch("review.build_commit_title")
    def test_update_commit_title_previews(self, m_build_commit_title):
        m_build_commit_title.side_effect = lambda x: x["title"] + " preview"
        commits = [dict(title="a"), dict(title="b")]
        review.update_commit_title_previews(commits)
        self.assertEqual(
            [
                {"title": "a", "title-preview": "a preview"},
                {"title": "b", "title-preview": "b preview"},
            ],
            commits,
        )

    def test_replace_request_reviewers(self):
        replace = review.replace_reviewers
        self.assertEqual("", replace("", reviewers_dict()))
        self.assertEqual("Title", replace("Title", reviewers_dict()))
        self.assertEqual(
            "Title\n\nr?one r=two", replace("Title\n\nr?one r=two", reviewers_dict())
        )
        self.assertEqual("r?one", replace("", reviewers_dict([["one"], []])))
        self.assertEqual("r?one", replace("r?one", reviewers_dict([["one"], []])))
        self.assertEqual("r?one,two", replace("", reviewers_dict([["one", "two"], []])))
        self.assertEqual(
            "Some Title r?one,two",
            replace("Some Title", reviewers_dict([["one", "two"], []])),
        )
        self.assertEqual(
            "Title r?one\n\nDescr\niption",
            replace("Title\n\nDescr\niption", reviewers_dict([["one"], []])),
        )
        self.assertEqual(
            "Title r?one,two\n\nr?two",
            replace("Title\n\nr?two", reviewers_dict([["one", "two"], []])),
        )

        self.assertEqual("Title", replace("Title r?one", reviewers_dict()))
        self.assertEqual("Title", replace("Title r?one,two", reviewers_dict()))
        self.assertEqual("Title", replace("Title r?one r?two", reviewers_dict()))
        self.assertEqual(
            "Title r?one!", replace("Title r?one!", reviewers_dict([["one!"], []]))
        )
        self.assertEqual(
            "Title r?one", replace("Title r?one!", reviewers_dict([["one"], []]))
        )
        self.assertEqual(
            "Title r?one!", replace("Title r?one", reviewers_dict([["one!"], []]))
        )
        self.assertEqual(
            "Title r?one", replace("Title r?one", reviewers_dict([["one"], []]))
        )
        self.assertEqual(
            "Title r?one one", replace("Title r? one", reviewers_dict([["one"], []]))
        )
        self.assertEqual(
            "Title r?one,two",
            replace("Title r?one,two", reviewers_dict([["one", "two"], []])),
        )
        self.assertEqual(
            "Title r?one,two",
            replace("Title r?two", reviewers_dict([["one", "two"], []])),
        )
        self.assertEqual(
            "Title r?one,two",
            replace("Title r?one r?two", reviewers_dict([["one", "two"], []])),
        )
        self.assertEqual(
            "Title r?one", replace("Title r=one", reviewers_dict([["one"], []]))
        )
        self.assertEqual(
            "Title r?one", replace("Title r=one,two", reviewers_dict([["one"], []]))
        )
        self.assertEqual(
            "Title r?one,two",
            replace("Title r=one,two", reviewers_dict([["one", "two"], []])),
        )
        self.assertEqual(
            "Title r?one,two",
            replace("Title r=one r=two", reviewers_dict([["one", "two"], []])),
        )
        self.assertEqual(
            "Title r?one,two",
            replace("Title r?one r=two", reviewers_dict([["one", "two"], []])),
        )

    def test_replace_granted_reviewers(self):
        replace = review.replace_reviewers
        self.assertEqual("r=one", replace("", reviewers_dict([[], ["one"]])))
        self.assertEqual("r=one", replace("r=one", reviewers_dict([[], ["one"]])))
        self.assertEqual("r=one,two", replace("", reviewers_dict([[], ["one", "two"]])))
        self.assertEqual(
            "Some Title r=one,two",
            replace("Some Title", reviewers_dict([[], ["one", "two"]])),
        )
        self.assertEqual(
            "Title r=one\n\nDescr\niption",
            replace("Title\n\nDescr\niption", reviewers_dict([[], ["one"]])),
        )
        self.assertEqual(
            "Title r=one,two\n\nr?two",
            replace("Title\n\nr?two", reviewers_dict([[], ["one", "two"]])),
        )
        self.assertEqual("Title", replace("Title r=one", reviewers_dict()))
        self.assertEqual("Title", replace("Title r=one,two", reviewers_dict()))
        self.assertEqual("Title", replace("Title r=one r=two", reviewers_dict()))
        self.assertEqual(
            "Title r=one", replace("Title r=one", reviewers_dict([[], ["one"]]))
        )
        self.assertEqual(
            "Title r=one!", replace("Title r=one!", reviewers_dict([[], ["one!"]]))
        )
        self.assertEqual(
            "Title r=one", replace("Title r=one!", reviewers_dict([[], ["one"]]))
        )
        self.assertEqual(
            "Title r=one!", replace("Title r=one", reviewers_dict([[], ["one!"]]))
        )
        self.assertEqual(
            "Title r=one one", replace("Title r= one", reviewers_dict([[], ["one"]]))
        )
        self.assertEqual(
            "Title r=one,two",
            replace("Title r=one,two", reviewers_dict([[], ["one", "two"]])),
        )
        self.assertEqual(
            "Title r=one,two",
            replace("Title r=two", reviewers_dict([[], ["one", "two"]])),
        )
        self.assertEqual(
            "Title r=one,two",
            replace("Title r=one r=two", reviewers_dict([[], ["one", "two"]])),
        )
        self.assertEqual(
            "Title r=one", replace("Title r?one", reviewers_dict([[], ["one"]]))
        )
        self.assertEqual(
            "Title r=one", replace("Title r?one,two", reviewers_dict([[], ["one"]]))
        )
        self.assertEqual(
            "Title r=one,two",
            replace("Title r?one,two", reviewers_dict([[], ["one", "two"]])),
        )
        self.assertEqual(
            "Title r=one,two",
            replace("Title r?one r?two", reviewers_dict([[], ["one", "two"]])),
        )
        self.assertEqual(
            "Title r=one,two",
            replace("Title r=one r?two", reviewers_dict([[], ["one", "two"]])),
        )

    def test_replace_mixed_reviewers(self):
        replace = review.replace_reviewers
        self.assertEqual(
            "Title r?one r=two", replace("Title", reviewers_dict([["one"], ["two"]]))
        )
        self.assertEqual(
            "Title r?one r=two",
            replace("Title r=one r?two", reviewers_dict([["one"], ["two"]])),
        )
        self.assertEqual(
            "Title r?one r=two",
            replace("Title r?two r=one", reviewers_dict([["one"], ["two"]])),
        )
        self.assertEqual(
            "Title r?one,two r=three",
            replace("Title r=one r?two", reviewers_dict([["one", "two"], ["three"]])),
        )
        self.assertEqual(
            "Title r?one r=two,three",
            replace("Title r=one r?two", reviewers_dict([["one"], ["two", "three"]])),
        )

    @unittest.skip("These tests should pass we should fix the function")
    def test_badly_replaced_reviewers(self):
        replace = review.replace_reviewers
        # r?two
        self.assertEqual("r?one", replace("r?two", reviewers_dict([["one"], []])))
        # r=one
        self.assertEqual("r?one", replace("r=one", reviewers_dict([["one"], []])))
        # r? one
        self.assertEqual("r?one one", replace("r? one", reviewers_dict([["one"], []])))
        # r?one,
        self.assertEqual("r?one", replace("r?one,", reviewers_dict([["one"], []])))
        # r?one
        self.assertEqual(
            "r?one,two", replace("r?one", reviewers_dict([["one", "two"], []]))
        )
        # r?one,two
        self.assertEqual("r?one", replace("r?one,two", reviewers_dict([["one"], []])))
        # Title r?one,two,,two
        self.assertEqual(
            "Title r?one,two",
            replace("Title r?one,,two", reviewers_dict([["one"], ["two"], []])),
        )
        # r?one
        self.assertEqual("", replace("r?one", reviewers_dict()))
        # r?one,two
        self.assertEqual("", replace("r?one,two", reviewers_dict()))
        # r?one
        self.assertEqual("", replace("r?one r?two", reviewers_dict()))
        # r?two
        self.assertEqual(
            "r?one,two", replace("r?two", reviewers_dict([["one", "two"], []]))
        )
        # r?one r?one,two
        self.assertEqual(
            "r?one,two", replace("r?one r?two", reviewers_dict([["one", "two"], []]))
        )
        # r=one
        self.assertEqual("r?one", replace("r=one", reviewers_dict([["one"], []])))
        # r=one,two
        self.assertEqual("r?one", replace("r=one,two", reviewers_dict([["one"], []])))
        # r=one,two
        self.assertEqual(
            "r?one,two", replace("r=one,two", reviewers_dict([["one", "two"], []]))
        )
        # r=one, r?one,two
        self.assertEqual(
            "r?one,two", replace("r=one r=two", reviewers_dict([["one", "two"], []]))
        )
        # r? one, r?one,two
        self.assertEqual(
            "r?one,two", replace("r?one r=two", reviewers_dict([["one", "two"], []]))
        )

        # Granted
        # r=two
        self.assertEqual("r=one", replace("r=two", reviewers_dict([[], ["one"]])))
        # r?one
        self.assertEqual("r=one", replace("r?one", reviewers_dict([[], ["one"]])))
        # r?one
        self.assertEqual(
            "r=one,two", replace("r=one", reviewers_dict([[], ["one", "two"]]))
        )
        # r?one,two
        self.assertEqual("r?one", replace("r?one,two", reviewers_dict([["one"], []])))

    @mock.patch("review.logger")
    def test_show_commit_stack(self, mock_logger):
        class Repository:
            phab_url = "http://phab/"

        repo = Repository()

        review.show_commit_stack(repo, [])
        self.assertFalse(mock_logger.info.called, "logger.info() shouldn't be called")
        self.assertFalse(
            mock_logger.warning.called, "logger.warning() shouldn't be called"
        )

        review.show_commit_stack(repo, [{"name": "aaa000", "title-preview": "A"}])
        mock_logger.info.assert_called_with("aaa000 A")
        self.assertFalse(
            mock_logger.warning.called, "logger.warning() shouldn't be called"
        )
        mock_logger.reset_mock()

        review.show_commit_stack(
            repo,
            [
                {"name": "aaa000", "title-preview": "A"},
                {"name": "bbb000", "title-preview": "B"},
            ],
        )
        self.assertEqual(2, mock_logger.info.call_count)
        self.assertEqual(
            [mock.call("bbb000 B"), mock.call("aaa000 A")],
            mock_logger.info.call_args_list,
        )
        mock_logger.reset_mock()

        review.show_commit_stack(
            repo,
            [
                {
                    "name": "aaa000",
                    "title-preview": "A",
                    "bug-id-orig": 2,
                    "bug-id": 1,
                    "reviewers": ["one"],
                }
            ],
            show_warnings=True,
        )
        mock_logger.info.assert_called_with("aaa000 A")
        mock_logger.warning.assert_called_with("!! Bug ID changed from 2 to 1")
        mock_logger.reset_mock()

        review.show_commit_stack(
            repo,
            [
                {
                    "name": "aaa000",
                    "title-preview": "A",
                    "bug-id-orig": None,
                    "reviewers": [],
                }
            ],
            show_warnings=True,
        )
        mock_logger.warning.assert_called_with("!! Missing reviewers")
        mock_logger.reset_mock()

        review.show_commit_stack(
            repo,
            [{"name": "aaa000", "title-preview": "A", "rev-id": "123"}],
            show_rev_urls=True,
        )
        mock_logger.warning.assert_called_with("-> http://phab/D123")

    @mock.patch("review.update_commit_title_previews")
    def test_update_commits_from_args(self, m_update_title):
        m_update_title.side_effect = lambda x: x

        update = review.update_commits_from_args

        class Args:
            def __init__(self, reviewer=None, blocker=None, bug=None):
                self.reviewer = reviewer
                self.blocker = blocker
                self.bug = bug

        _commits = [
            {"title": "A", "reviewers": dict(granted=[], request=[]), "bug-id": None},
            {"title": "B", "reviewers": dict(granted=[], request=["one"]), "bug-id": 1},
        ]

        # No change if noreviewer  args provided
        commits = copy.deepcopy(_commits)
        commits[1]["reviewers"]["granted"].append("two")
        with mock.patch("review.config") as m_config:
            m_config.always_blocking = False
            update(commits, Args())
            self.assertEqual(
                commits,
                [
                    {
                        "title": "A",
                        "reviewers": dict(granted=[], request=[]),
                        "bug-id": None,
                    },
                    {
                        "title": "B",
                        "reviewers": dict(granted=["two"], request=["one"]),
                        "bug-id": 1,
                    },
                ],
            )

        # Adding and removing reviewers, forcing the bug ID
        commits = copy.deepcopy(_commits)
        update(commits, Args(reviewer=["two", "three"], bug=2))
        self.assertEqual(
            commits,
            [
                {
                    "title": "A",
                    "reviewers": dict(granted=["two", "three"], request=[]),
                    "bug-id": 2,
                },
                {
                    "title": "B",
                    "reviewers": dict(granted=["two", "three"], request=[]),
                    "bug-id": 2,
                },
            ],
        )

        # Removing duplicates
        commits = copy.deepcopy(_commits)
        update(
            commits,
            Args(
                reviewer=["two", "two", "two!", "three"],
                blocker=["two", "three!", "three", "three"],
            ),
        )
        self.assertEqual(
            commits,
            [
                {
                    "title": "A",
                    "reviewers": dict(granted=["two!", "three!"], request=[]),
                    "bug-id": None,
                },
                {
                    "title": "B",
                    "reviewers": dict(granted=["two!", "three!"], request=[]),
                    "bug-id": 1,
                },
            ],
        )

        # Adding blocking reviewers via args
        commits = copy.deepcopy(_commits)
        commits[1]["reviewers"]["request"].append("three")
        commits[0]["reviewers"]["granted"].append("four")
        commits[0]["reviewers"]["granted"].append("five")
        update(
            commits, Args(reviewer=["one", "two!", "four"], blocker=["three", "four!"])
        )
        self.assertEqual(
            commits,
            [
                {
                    "title": "A",
                    "reviewers": dict(
                        granted=["one", "four!", "three!", "two!"], request=[]
                    ),
                    "bug-id": None,
                },
                {
                    "title": "B",
                    "reviewers": dict(
                        granted=["four!", "two!"], request=["one", "three!"]
                    ),
                    "bug-id": 1,
                },
            ],
        )

        # Forcing blocking reviewers
        commits = copy.deepcopy(_commits)
        commits[1]["reviewers"]["granted"].append("two")
        with mock.patch("review.config") as m_config:
            m_config.always_blocking = True
            update(commits, Args())
            self.assertEqual(
                commits,
                [
                    {
                        "title": "A",
                        "reviewers": dict(granted=[], request=[]),
                        "bug-id": None,
                    },
                    {
                        "title": "B",
                        "reviewers": dict(granted=["two!"], request=["one!"]),
                        "bug-id": 1,
                    },
                ],
            )


if __name__ == "__main__":
    unittest.main()
