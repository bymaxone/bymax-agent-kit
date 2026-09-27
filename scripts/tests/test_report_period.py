"""Gate layer for what the standup reads from its arguments and from a subject line: the
period a spelling resolves to, and the type and scope a Conventional Commits subject carries.
"""
import datetime as dt
from pathlib import Path
import sys
import unittest

# The loader is test_report_collect's, imported whether this file is run by path or by module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_report_collect import load


class PeriodTests(unittest.TestCase):
    def setUp(self):
        self.m = load()
        self.today = dt.date(2026, 9, 21)  # a Monday

    def test_last_week_is_the_previous_monday_through_sunday(self):
        self.assertEqual(self.m.parse_period('last-week', self.today),
                         (dt.date(2026, 9, 14), dt.date(2026, 9, 20)))

    def test_last_week_from_a_thursday_still_ends_on_sunday(self):
        self.assertEqual(self.m.parse_period(None, dt.date(2026, 9, 24)),
                         (dt.date(2026, 9, 14), dt.date(2026, 9, 20)))

    def test_days_end_today(self):
        self.assertEqual(self.m.parse_period('7d', self.today), (dt.date(2026, 9, 15), self.today))

    def test_explicit_range(self):
        self.assertEqual(self.m.parse_period('2026-09-01..2026-09-07', self.today),
                         (dt.date(2026, 9, 1), dt.date(2026, 9, 7)))

    def test_a_typo_is_refused_rather_than_becoming_last_week(self):
        for bad in ('lastweek', '2026-09-07..2026-09-01', '0d', 'week'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.m.parse_period(bad, self.today)


class ConventionalTests(unittest.TestCase):
    def test_type_scope_and_summary(self):
        m = load()
        self.assertEqual(m.conventional('feat(likes): stand the sweep down'),
                         {'type': 'feat', 'scope': 'likes', 'summary': 'stand the sweep down'})
        self.assertEqual(m.conventional('Guideline flags reach Pearl')['scope'], None)
        self.assertEqual(m.conventional('fix!: breaking')['type'], 'fix')

    def test_remote_prefix_is_not_a_branch_name(self):
        m = load()
        self.assertEqual(m.branch_name('refs/remotes/origin/fix/x'), 'fix/x')
        self.assertEqual(m.branch_name('refs/heads/feat/y'), 'feat/y')


if __name__ == '__main__':
    unittest.main()
