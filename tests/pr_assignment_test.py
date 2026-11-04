import unittest

import pandas as pd

from pages.utils.pr_assignment_utils import pr_assignment


class PullRequestAssignmentTests(unittest.TestCase):
    start = pd.Timestamp("2026-01-01", tz="UTC")
    end = pd.Timestamp("2026-01-08", tz="UTC")

    def frame(self, events):
        rows = []
        for pr_id, assignee, action, date in events:
            rows.append(
                {
                    "pull_request_id": pr_id,
                    "assignee": assignee,
                    "assignment_action": action,
                    "assign_date": date,
                    "created_at": "2026-01-01",
                    "closed_at": None,
                }
            )
        df = pd.DataFrame(
            rows,
            columns=["pull_request_id", "assignee", "assignment_action", "assign_date", "created_at", "closed_at"],
        )
        for column in ("created_at", "closed_at", "assign_date"):
            df[column] = pd.to_datetime(df[column], utc=True)
        return df

    def test_multiple_reviewers_count_as_one_assigned_pull_request(self):
        df = self.frame([(1, "alice", "assigned", "2026-01-02"), (1, "bob", "assigned", "2026-01-03")])
        self.assertEqual(pr_assignment(df, self.start, self.end), (1, 0))

    def test_unassigning_one_reviewer_keeps_pull_request_assigned(self):
        df = self.frame(
            [
                (1, "alice", "assigned", "2026-01-02"),
                (1, "bob", "assigned", "2026-01-03"),
                (1, "alice", "unassigned", "2026-01-04"),
            ]
        )
        self.assertEqual(pr_assignment(df, self.start, self.end), (1, 0))

    def test_same_reviewer_on_different_pull_requests(self):
        df = self.frame([(1, "alice", "assigned", "2026-01-02"), (2, "alice", "assigned", "2026-01-03")])
        self.assertEqual(pr_assignment(df, self.start, self.end), (2, 0))

    def test_unassigning_all_reviewers_makes_pull_request_unassigned(self):
        df = self.frame(
            [
                (1, "alice", "assigned", "2026-01-02"),
                (1, "bob", "assigned", "2026-01-03"),
                (1, "alice", "unassigned", "2026-01-04"),
                (1, "bob", "unassigned", "2026-01-05"),
            ]
        )
        self.assertEqual(pr_assignment(df, self.start, self.end), (0, 1))

    def test_mixed_pull_requests_are_counted_independently(self):
        df = self.frame(
            [
                (1, "alice", "assigned", "2026-01-02"),
                (1, "bob", "assigned", "2026-01-03"),
                (2, None, None, None),
                (3, "carol", "assigned", "2026-01-02"),
                (3, "carol", "unassigned", "2026-01-04"),
            ]
        )
        self.assertEqual(pr_assignment(df, self.start, self.end), (1, 2))

    def test_reassignment_does_not_duplicate_pull_request(self):
        df = self.frame(
            [
                (1, "alice", "assigned", "2026-01-02"),
                (1, "alice", "unassigned", "2026-01-03"),
                (1, "alice", "assigned", "2026-01-04"),
            ]
        )
        self.assertEqual(pr_assignment(df, self.start, self.end), (1, 0))

    def test_events_after_bucket_end_do_not_affect_counts(self):
        df = self.frame(
            [
                (1, "alice", "assigned", "2026-01-02"),
                (1, "bob", "assigned", "2026-01-03"),
                (1, "bob", "unassigned", "2026-01-09"),
                (2, "carol", "assigned", "2026-01-09"),
            ]
        )
        self.assertEqual(pr_assignment(df, self.start, self.end), (1, 1))

    def test_only_pull_requests_open_in_bucket_are_counted(self):
        df = self.frame(
            [
                (1, "alice", "assigned", "2026-01-02"),
                (1, "bob", "assigned", "2026-01-03"),
                (2, None, None, None),
                (3, None, None, None),
            ]
        )
        df.loc[df.pull_request_id == 2, "closed_at"] = self.start
        df.loc[df.pull_request_id == 3, "created_at"] = pd.Timestamp("2026-01-09", tz="UTC")
        self.assertEqual(pr_assignment(df, self.start, self.end), (1, 0))

    def test_no_assignments(self):
        df = self.frame([(1, None, None, None)])
        self.assertEqual(pr_assignment(df, self.start, self.end), (0, 1))

    def test_empty_data(self):
        self.assertEqual(pr_assignment(self.frame([]), self.start, self.end), (0, 0))

    def test_input_is_not_modified(self):
        df = self.frame([(1, "alice", "assigned", "2026-01-02")])
        before = df.copy(deep=True)
        pr_assignment(df, self.start, self.end)
        pd.testing.assert_frame_equal(df, before)


if __name__ == "__main__":
    unittest.main()
