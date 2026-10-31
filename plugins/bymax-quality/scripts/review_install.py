"""Installation layer: say when the running runtime is not the one the checkout in hand ships.

Campaigns run the copy installed under ~/.claude/bymax-review, and nothing re-installs it when the
toolkit's own scripts change: a merged fix stayed absent from the installed copy, and a hand patch
to the installed copy was never carried back. Inside a checkout of this toolkit, `start` compares
the two and says which files differ. It warns and never refuses: the runtime in hand is still the
one every receipt so far was written by.

review_flow imports this module, so nothing here imports review_flow.
"""
from pathlib import Path
import sys

from review_git import git

SOURCE = Path('plugins/bymax-quality/scripts')


def drifted(runtime=None):
    """Runtime files that differ from the same files in the checkout being reviewed, or []."""
    runtime = Path(runtime or Path(__file__).resolve().parent)
    top = git('rev-parse', '--show-toplevel')
    source = Path(top) / SOURCE if top else None
    if source is None or not (source / 'review_flow.py').is_file() or source.resolve() == runtime:
        return []
    names = sorted(p.name for p in source.iterdir() if p.suffix in ('.py', '.json') and p.is_file())
    return [name for name in names
            if not (runtime / name).is_file() or (runtime / name).read_bytes() != (source / name).read_bytes()]


def drift_notice():
    """Print the warning when this checkout ships a runtime the installed one is not."""
    stale = drifted()
    if stale:
        print('Note: the installed review runtime differs from this checkout in ' + ', '.join(stale)
              + '. Run `python3 scripts/install-review-flow.py` so the next campaign runs the code '
              'this checkout ships. The campaign continues.', file=sys.stderr)
