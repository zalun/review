import copy
import imp
import mock
import os
import sys
import unittest
import uuid


mozphab = imp.load_source(
    "mozphab", os.path.join(os.path.dirname(__file__), os.path.pardir, "moz-phab")
)


def reviewers_dict(reviewers=None):
    return dict(
        request=reviewers[0] if reviewers else [],
        granted=reviewers[1] if reviewers else [],
    )


def commit(bug_id=None, reviewers=None, body="", name="", title="", rev_id=None):
    return {
        "name": name,
        "title": title,
        "bug-id": bug_id,
        "reviewers": reviewers_dict(reviewers),
        "body": body,
        "rev-id": rev_id,
        "node": uuid.uuid4().get_hex(),
    }


# noinspection PyPep8Naming,PyBroadException
class Commits(unittest.TestCase):
    def _assertNoError(self, callableObj, *args):
        try:
            callableObj(*args)
        except mozphab.Error:
            info = sys.exc_info()
            self.fail("%s raised" % repr(info[0]))

    def _assertError(self, callableObj, *args):
        try:
            callableObj(*args)
        except mozphab.Error:
            return
        except Exception:
            info = sys.exc_info()
            self.fail("%s raised" % repr(info[0]))
        self.fail("%s failed to raise Error" % callableObj)

    @mock.patch("mozphab.check_if_current_events")
    @mock.patch("mozphab.check_for_invalid_reviewers")
    @mock.patch("mozphab.get_users")
    def test_commit_validation(self, m_users, check_reviewers, check_events):
        check_reviewers.return_value = []
        m_users.return_value = [{"username": "alice", "phid": "PHID-1"}]
        check_events.return_value = False
        repo = mozphab.Repository(None, None, "dummy")
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

    @mock.patch("mozphab.check_if_current_events")
    @mock.patch("mozphab.check_for_invalid_reviewers")
    @mock.patch("mozphab.get_users")
    def test_invalid_reviewers_fails_the_stack_validation_check(
        self, m_users, check_reviewers, check_events
    ):
        m_users.return_value = [{"username": "alice", "phid": "PHID-1"}]
        check_events.return_value = False

        def fail_gonzo(reviewers, *args):
            # Replace the check_for_invalid_reviewers() function with something that
            # fails if "gonzo" is in the reviewers list.
            if "gonzo" in reviewers:
                response = ["gonzo"]
            else:
                response = []
            return response

        check_reviewers.side_effect = fail_gonzo
        repo = mozphab.Repository(None, None, "dummy")

        with self.assertRaises(mozphab.Error):
            # Build a stack with an invalid reviewer in the middle.
            repo.check_commits_for_submit(
                [
                    commit("1", (["alice"], [])),
                    commit("2", (["bob", "gonzo"], [])),
                    commit("3", (["charlie"], [])),
                ]
            )

    def test_commit_preview(self):
        build = mozphab.build_commit_title

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

    @mock.patch("mozphab.build_commit_title")
    def test_update_commit_title_previews(self, m_build_commit_title):
        m_build_commit_title.side_effect = lambda x: x["title"] + " preview"
        commits = [dict(title="a"), dict(title="b")]
        mozphab.update_commit_title_previews(commits)
        self.assertEqual(
            [
                {"title": "a", "title-preview": "a preview"},
                {"title": "b", "title-preview": "b preview"},
            ],
            commits,
        )

    def test_replace_request_reviewers(self):
        replace = mozphab.replace_reviewers
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
        replace = mozphab.replace_reviewers
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
        replace = mozphab.replace_reviewers
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
        replace = mozphab.replace_reviewers
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

    @mock.patch("mozphab.logger")
    def test_show_commit_stack(self, mock_logger):
        class Repository:
            phab_url = "http://phab/"

        repo = Repository()

        mozphab.show_commit_stack(repo, [])
        self.assertFalse(mock_logger.info.called, "logger.info() shouldn't be called")
        self.assertFalse(
            mock_logger.warning.called, "logger.warning() shouldn't be called"
        )

        mozphab.show_commit_stack(repo, [{"name": "aaa000", "title-preview": "A"}])
        mock_logger.info.assert_called_with("aaa000 A")
        self.assertFalse(
            mock_logger.warning.called, "logger.warning() shouldn't be called"
        )
        mock_logger.reset_mock()

        mozphab.show_commit_stack(
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

        mozphab.show_commit_stack(
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

        mozphab.show_commit_stack(
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

        mozphab.show_commit_stack(
            repo,
            [{"name": "aaa000", "title-preview": "A", "rev-id": "123"}],
            show_rev_urls=True,
        )
        mock_logger.warning.assert_called_with("-> http://phab/D123")

    @mock.patch("mozphab.update_commit_title_previews")
    def test_update_commits_from_args(self, m_update_title):
        m_update_title.side_effect = lambda x: x

        update = mozphab.update_commits_from_args

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
        with mock.patch("mozphab.config") as m_config:
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
                reviewer=["Two", "two", "two!", "three", "Three", "THREE!"],
                blocker=["Two", "THREE!", "three", "two", "three"],
            ),
        )
        self.assertEqual(
            commits,
            [
                {
                    "title": "A",
                    "reviewers": dict(granted=["two!", "THREE!"], request=[]),
                    "bug-id": None,
                },
                {
                    "title": "B",
                    "reviewers": dict(granted=["two!", "THREE!"], request=[]),
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
        with mock.patch("mozphab.config") as m_config:
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


class TestUpdateCommitSummary(unittest.TestCase):
    @mock.patch("mozphab.check_output")
    @mock.patch("mozphab.config")
    def test_update_summary_cli_args(self, config, check_output):
        config.arc = ["arc"]
        c = commit(rev_id="D123")
        check_output.return_value = (
            '{"error": null, "errorMessage": null, "response": {}}'
        )

        mozphab.update_phabricator_commit_summary(c, mock.Mock())

        check_output.assert_called_once_with(
            ["arc", "call-conduit", "differential.revision.edit"],
            cwd=mock.ANY,
            split=mock.ANY,
            stdin=mock.ANY,
        )

    def test_build_api_call_to_update_title_and_summary(self):
        # From https://phabricator.services.mozilla.com/api/differential.revision.edit
        #
        # Example call format we are aiming for:
        #
        # $ echo '{
        #   "transactions": [
        #     {
        #       "type": "title",
        #       "value": "Remove unnecessary branch statement"
        #     }
        #     {
        #       "type": "summary",
        #       "value": "Blah"
        #     }
        #   ],
        #   "objectIdentifier": "D8095"
        # }' | arc call-conduit --conduit-uri \
        #       https://phabricator.services.mozilla.com/ \
        #       --conduit-token <conduit-token> differential.revision.edit

        c = commit(
            rev_id="D123",
            title="hi!",
            body="hello!\n\nDifferential Revision: http://phabricator.test/D123",
        )
        expected_json = {
            "transactions": [
                {"type": "title", "value": "hi!"},
                {"type": "summary", "value": "hello!"},
            ],
            "objectIdentifier": "D123",
        }

        api_call_args = mozphab.build_api_call_to_update_commit_title_and_summary(c)

        self.assertDictEqual(expected_json, api_call_args)

    def test_parse_api_response_with_no_problems(self):
        # Response comes from running:
        # $ echo '{... (some valid update summary JSON) ...}' | \
        #   arc call-conduit differential.revision.edit
        api_response = (
            '{"error":null,"errorMessage":null,"response":{"object":{'
            '"id":56,"phid":"PHID-DREV-ke6jhbdnwd5chtnk2q5w"},'
            '"transactions":[{"phid":"PHID-XACT-DREV-itlxgx7rsjrcnta"}]}} '
        )
        self.assertEqual(None, mozphab.parse_api_error(api_response))

    def test_parse_api_response_with_errors(self):
        # Error response from running:
        # $ echo '{}' | arc call-conduit differential.revision.edit
        api_response = (
            '{"error":"ERR-CONDUIT-CORE", '
            '"errorMessage":"ERR-CONDUIT-CORE: Parameter '
            '\\"transactions\\" is not a list of transactions.",'
            '"response":null} '
        )
        self.assertEqual(
            'ERR-CONDUIT-CORE: Parameter "transactions" is not a list of transactions.',
            mozphab.parse_api_error(api_response),
        )


if __name__ == "__main__":
    unittest.main()
