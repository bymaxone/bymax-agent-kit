"""Gate layer: a body a document tells a model to post keeps its marker on a line of its own.

A skill that posts to GitHub tags its own comments with an HTML comment marker and later
finds them again by `startswith`. GitHub renders the body as GitHub Flavored Markdown, where
a line starting with `<!--` opens an HTML block that ends only with the line holding `-->`.
A marker that shares its line with the text turns that whole line into raw HTML: backticks
stay literal and a quoted `<h1>` posts as a heading. These tests read every document for
such a template, and read the reply templates for the shape the idempotency guard needs.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
BABYSIT = ROOT / 'plugins/bymax-pr/skills/babysit-pr/SKILL.md'
# A document finds its own comments by the marker the body starts with, said in a jq
# `startswith("...")` or in prose as starting with the marker in backticks.
MATCHED = re.compile(r'(?:startswith\("|starting with `)(<!-- [a-z-]+ -->)')
TEMPLATE = re.compile(r'```text\n(.*?)```', re.S)


def documents():
    """The canonical command, skill and agent documents a model reads."""
    return sorted(path for pattern in ('plugins/*/commands/*.md', 'plugins/*/skills/**/*.md',
                                       'plugins/*/agents/*.md')
                  for path in ROOT.glob(pattern))


def markers():
    """Markers some document matches a posted body against."""
    return sorted({m for path in documents() for m in MATCHED.findall(path.read_text())})


def shared_lines(text, marker):
    """Lines where text follows the marker: the template shape GitHub renders as HTML.

    A mention closes right after the marker, with a backtick or a quote; a template
    goes on with the body.
    """
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in re.finditer(re.escape(marker), line):
            rest = line[match.end():].lstrip()
            if rest and rest[0] not in '`"\'':
                found.append(number)
    return found


class PostedMarkerTests(unittest.TestCase):
    """What a skill posts must render as Markdown and still be found by its marker."""

    def test_markers_are_found(self):
        """An empty marker list would make every rule below vacuous."""
        self.assertIn('<!-- babysit-reply -->', markers())
        self.assertIn('<!-- babysit-state -->', markers())

    def test_no_template_puts_text_on_the_marker_line(self):
        """`<!-- babysit-reply --> Fixed in <sha>: ...` posted every reply as raw HTML."""
        for path in documents():
            text = path.read_text()
            for marker in markers():
                with self.subTest(path=path.relative_to(ROOT).as_posix(), marker=marker):
                    self.assertEqual(shared_lines(text, marker), [])

    def test_rule_catches_the_same_line_template(self):
        """The shape the rule exists for is caught, and a mention of the marker is not."""
        marker = '<!-- babysit-reply -->'
        self.assertEqual(shared_lines(f'   `{marker} Fixed in <sha>: why.`', marker), [1])
        self.assertEqual(shared_lines(f'{marker} Not applied: nit.', marker), [1])
        self.assertEqual(shared_lines(f'replies marked `{marker}`).', marker), [])
        self.assertEqual(shared_lines(f'startswith("{marker}")', marker), [])
        self.assertEqual(shared_lines(marker, marker), [])

    def test_reply_templates_lead_with_the_marker_and_a_blank_line(self):
        """Each reply template is the marker, a blank line, then the text."""
        marker = '<!-- babysit-reply -->'
        templates = [t for t in TEMPLATE.findall(BABYSIT.read_text()) if marker in t]
        self.assertEqual(len(templates), 2)
        for template in templates:
            lines = [line.strip() for line in template.strip('\n').splitlines()]
            with self.subTest(text=lines[-1]):
                self.assertEqual(lines[0], marker)
                self.assertEqual(lines[1], '')
                self.assertTrue(lines[2])

    def test_reply_templates_satisfy_the_already_processed_guard(self):
        """The guard matches a body by `startswith`, so the marker must open the body."""
        marker = '<!-- babysit-reply -->'
        self.assertIn(f'starting with `{marker}`', BABYSIT.read_text())
        for template in TEMPLATE.findall(BABYSIT.read_text()):
            if marker in template:
                body = '\n'.join(line.strip() for line in template.strip('\n').splitlines())
                self.assertTrue(body.startswith(marker))


if __name__ == '__main__':
    unittest.main()
