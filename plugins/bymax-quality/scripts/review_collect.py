"""A pytest plugin that reports the node ids a collect produced, through pytest rather than
through its output.

Read from stdout instead, a node id was whatever line held `::`, and a module that printed
while it failed to import could name any file it liked: pytest replays that print, sometimes
after its report banner and sometimes — a conftest below the collected directory — ahead of
every real id. The hook below receives the items pytest collected and nothing else can
reach it.

The destination is a path the caller names in the environment, so the ids never share a stream
with anything a test can write.
"""
import os


def pytest_collection_finish(session):
    """Write what was collected, one node id per line, to the file the caller named.

    After collection finishes and not while items are being modified: a selector deselects in a
    hook of its own, so a plugin that writes the items as they arrive reports the ones `-k` was
    about to drop, and a caller asking which nodes a case collects got every node in the file.
    """
    where = os.environ.get('BYMAX_COLLECT_OUT')
    if not where:
        return
    with open(where, 'a', encoding='utf-8') as out:
        for item in session.items:
            out.write(item.nodeid + '\n')
