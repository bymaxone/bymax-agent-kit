"""A ref a command file or script hands to `git merge-base` is read as an option when it starts
with a dash: a branch the repository holds under `--octopus` made `merge-base` answer HEAD, an
empty diff, with a status that passed the caller's non-empty check."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CALL = re.compile(r'git merge-base(?! -- )')


def shipped():
    """Every shell-bearing file a plugin ships: command and reference text a model runs, and scripts."""
    plugins = ROOT / 'plugins'
    return sorted([*plugins.rglob('*.md'), *plugins.rglob('*.sh')])


class MergeBaseOptionTests(unittest.TestCase):

    def test_every_merge_base_a_plugin_ships_ends_the_options_before_its_refs(self):
        """`--` goes between the command and the refs, so a ref cannot be taken for an option."""
        loose = [f'{path.relative_to(ROOT)}:{number}'
                 for path in shipped()
                 for number, line in enumerate(path.read_text().splitlines(), 1)
                 if CALL.search(line)]
        self.assertEqual(loose, [], 'git merge-base without `--` before its refs')

    def test_the_scan_reads_the_files_it_is_meant_to(self):
        """A scan over nothing passes however the commands are spelled."""
        names = {path.name for path in shipped()}
        self.assertIn('push.md', names)
        self.assertIn('codex-review.sh', names)
        self.assertIn('review-quickstart.md', names)


if __name__ == '__main__':
    unittest.main()
