"""A pytest plugin that reports the node ids a collect produced, through pytest rather than
through its output.

Read from stdout instead, a node id was whatever line held `::`, and a module that printed
while it failed to import could name any file it liked: pytest replays that print, sometimes
after its report banner and sometimes — a conftest below the collected directory — ahead of
every real id. The hook below receives the items pytest collected and nothing else can reach it.

Each line carries a token the caller generated for this run, and the caller keeps only the lines
that carry it. That is what makes accidental contamination impossible: a file inherited from an
earlier run, or a project that writes to the same path, says nothing the caller will read. It is
not tamper-proof and is not claimed to be — the token reaches this process through the
environment, so a conftest that means to forge an id can read it — and the header the caller
requires turns the other failure, a plugin that never ran at all, into a refusal instead of an
empty answer.

The module name is the caller's own rather than a plain word, because `python -m pytest` puts
the repository under review on the path ahead of the caller's own directory: a module named for
a common word there is loaded instead of this one, and the hook silently never runs.
"""
import os

MARK = 'BYMAX_COLLECT'


def pytest_collection_finish(session):
    """Write the token, then the node ids it vouches for, one per line.

    After collection finishes and not while items are being modified: a selector deselects in a
    hook of its own, so a plugin that writes the items as they arrive reports the ones `-k` was
    about to drop, and a caller asking which nodes a case collects got every node in the file.
    """
    where, token = os.environ.get('BYMAX_COLLECT_OUT'), os.environ.get('BYMAX_COLLECT_TOKEN')
    if not where or not token:
        return
    with open(where, 'a', encoding='utf-8') as out:
        out.write('%s %s\n' % (MARK, token))
        for item in session.items:
            out.write('%s %s\n' % (token, item.nodeid))
