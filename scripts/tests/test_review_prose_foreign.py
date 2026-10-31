"""Regression layer: the prose pass neither reads nor edits a tree vendored from another project.

A vendored folder (a tracked ATTRIBUTION.md beside a tracked LICENSE) holds someone else's text,
shipped unchanged and pinned by a hash manifest. The pass was handed that text — 87% of what one
reader got on a delta vendoring twenty playbooks — and nothing refused an edit to it.
"""
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Importing the bench also puts the runtime's scripts on sys.path.
from test_review_prose import Bench
import review_claims

VENDORED = {'vendor/tool/ATTRIBUTION.md': 'Copied from elsewhere.\n',
            'vendor/tool/LICENSE': 'MIT\n',
            'vendor/tool/README.md': '# Tool\n\nThe limit is ten.\n',
            'docs/own.md': '# Own\n\nThe limit is ten.\n'}


def commit(bench, files):
    """Write files into the bench and commit them as one more candidate commit."""
    for name, text in files.items():
        (bench.where / name).parent.mkdir(parents=True, exist_ok=True)
        (bench.where / name).write_text(text)
    for args in (['add', '-A'], ['-c', 'user.email=a@b.invalid', '-c', 'user.name=A', 'commit', '-q', '-m', 'y']):
        subprocess.run(['git', '-C', str(bench.where), *args], check=True)


class ForeignTreeTests(unittest.TestCase):
    """What the pass reads and may change when the delta carries a vendored folder."""

    def test_vendored_prose_is_not_handed_to_the_pass(self):
        """Only the repository's own documents are the pass's to read."""
        bench = Bench(self)
        commit(bench, VENDORED)
        touched = review_claims.touched('HEAD~1', 'HEAD', cwd=str(bench.where))
        self.assertEqual(sorted(touched), ['docs/own.md'])

    def test_a_folder_without_both_markers_is_still_read(self):
        """An ATTRIBUTION.md alone marks nothing: the convention puts a LICENSE beside it."""
        bench = Bench(self)
        commit(bench, {name: text for name, text in VENDORED.items() if not name.endswith('LICENSE')})
        touched = review_claims.touched('HEAD~1', 'HEAD', cwd=str(bench.where))
        self.assertIn('vendor/tool/README.md', touched)

    def test_an_edit_inside_a_vendored_folder_leaves_the_envelope(self):
        """A pass that corrects vendored prose breaks the pin the vendor test holds."""
        bench = Bench(self, files=VENDORED)
        bench.write('# Tool\n\nThe limit is eleven.\n', name='vendor/tool/README.md')
        self.assertIn('shipped unchanged from another project', ' | '.join(bench.offences()))


if __name__ == '__main__':
    unittest.main()
