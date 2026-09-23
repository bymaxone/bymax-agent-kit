"""A pytest plugin that reports the node ids a collect produced, through pytest rather than
through its output.

Read from stdout instead, a node id was whatever line held `::`, and a module that printed
while it failed to import could name any file it liked: pytest replays that print, sometimes
after its report banner and sometimes — a conftest below the collected directory — ahead of
every real id. The hook below receives the items pytest collected, which nothing printed can reach.

Each line carries a token the caller generated for this run, and the caller keeps only the lines
that carry it. That is what makes accidental contamination impossible: a file inherited from an
earlier run, or a project that writes to the same path, says nothing the caller will read. It is
not tamper-proof and is not claimed to be: the path and the token leave the environment before
any conftest is imported, so what remains is code that goes looking for them inside this module,
which is tampering with one's own review. The header tells a plugin that never ran apart from one
that collected nothing.

A module of this name at the root of the repository under review is loaded instead of this one,
because `python -m pytest` puts that root on the path first; the header is written only here,
so the caller can tell that happened rather than read silence.
"""
import os

MARK = 'BYMAX_COLLECT'

# Taken, and taken out of the environment, when pytest imports this module: `-p` loads it before
# any conftest, root or nested, so no conftest can read where the ids go or what vouches for
# them. Read at write time instead, both were in reach of every conftest, and one rewriting the
# file in pytest_sessionfinish made a directory holding a real test answer empty.
_WHERE = os.environ.pop('BYMAX_COLLECT_OUT', None)
_TOKEN = os.environ.pop('BYMAX_COLLECT_TOKEN', None)


def pytest_collection_finish(session):
    """Write the token, then the node ids it vouches for, one per line.

    After collection finishes and not while items are being modified: a selector deselects in a
    hook of its own, so a plugin that writes the items as they arrive reports the ones `-k` was
    about to drop, and a caller asking which nodes a case collects got every node in the file.
    """
    where, token = _WHERE, _TOKEN
    if not where or not token:
        return
    with open(where, 'a', encoding='utf-8') as out:
        out.write('%s %s\n' % (MARK, token))
        for item in session.items:
            out.write('%s %s\n' % (token, item.nodeid))
