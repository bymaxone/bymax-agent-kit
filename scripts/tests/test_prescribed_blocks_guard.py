"""Gate layer: every shell block the kit tells a model to run gets past the kit's own push guard.

The PreToolUse adapter (review_push.py) and the command documents are two halves of one contract.
When they disagree, the documented step cannot be executed as written and a session improvises
around it. This module feeds each fenced bash block of every command and skill document to the
adapter exactly as Claude Code's hook would, and requires it to pass. The one exception is a block
that is nothing but a literal `git push` template with a `<placeholder>`, which the model fills in
before running and the adapter rightly refuses while it holds `<`.
"""
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / 'plugins/bymax-quality/scripts/review_push.py'
BLOCK = re.compile(r'```bash\n(.*?)```', re.S)


def foreign_roots():
    """Folders this repository ships unchanged from elsewhere: ATTRIBUTION.md beside a LICENSE."""
    return sorted(path.parent for path in ROOT.glob('plugins/**/ATTRIBUTION.md')
                  if (path.parent / 'LICENSE').is_file())


def documents():
    """Every command and skill document the kit authors."""
    found = set(ROOT.glob('plugins/*/commands/*.md')) | set(ROOT.glob('plugins/*/skills/**/*.md'))
    foreign = foreign_roots()
    return sorted(path for path in found if not any(path.is_relative_to(root) for root in foreign))


def template(block):
    """Whether a block is only a literal push to be filled in: one `git push` line with a placeholder."""
    lines = [line.strip() for line in block.splitlines()
             if line.strip() and not line.strip().startswith('#')]
    return len(lines) == 1 and lines[0].startswith('git push ') and '<' in lines[0]


def verdict(command):
    """The adapter's answer for one command: the refusal text, or '' when it passes."""
    payload = json.dumps({'tool_name': 'Bash', 'tool_input': {'command': command}, 'cwd': str(ROOT)})
    run = subprocess.run([sys.executable, str(ADAPTER)], input=payload, capture_output=True,
                         text=True, cwd=ROOT, timeout=60)
    return '' if run.returncode == 0 else (run.stderr.strip() or run.stdout.strip() or 'exit %d' % run.returncode)


class PrescribedBlocksTests(unittest.TestCase):
    """What a document prescribes, the guard lets run."""

    def test_documents_carry_blocks_to_check(self):
        """A glob matching nothing would make the case below pass on nothing."""
        self.assertTrue(any(BLOCK.findall(path.read_text()) for path in documents()))

    def test_every_prescribed_block_passes_the_push_guard(self):
        """Prescribed blocks were refused: a handoff path read through
        `$(git rev-parse --git-dir)` counted as `git --git-dir=`, an apostrophe inside a comment
        made a block unparseable and so able to push, and babysit's rebase push named no refspec."""
        for path in documents():
            for number, block in enumerate(BLOCK.findall(path.read_text()), start=1):
                if template(block):
                    continue
                with self.subTest(document=str(path.relative_to(ROOT)), block=number):
                    self.assertEqual(verdict(block), '')

    def test_a_disarming_option_beside_a_handoff_read_is_still_refused(self):
        """Setting the query aside must not set aside a real redirection on the same line."""
        for command in ('X=$(git rev-parse --git-dir); git --git-dir=/x push origin HEAD:f',
                        'git rev-parse --git-dir=/x push origin HEAD:f',
                        # rev-parse as a mere word on the line set the redirection aside.
                        'env A=rev-parse git --git-dir /tmp/other push origin HEAD:f',
                        'echo rev-parse x --git-dir && git --git-dir /x push origin HEAD:f',
                        'git -c core.hooksPath=/dev/null rev-parse --git-dir && git push origin HEAD:f',
                        "# the PR's branch\ngit -c core.hooksPath=/dev/null push origin HEAD:f"):
            with self.subTest(command=command):
                self.assertIn('BLOCKED', verdict(command))


if __name__ == '__main__':
    unittest.main()
