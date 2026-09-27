"""Git access layer: read repository state without a shell, and the refusal a review step
raises."""
import subprocess
import sys

# Text handed to a model or printed for one. A path or a line that is not valid UTF-8 reaches
# the runtime as surrogate escapes (see git_raw), which a strict encoder refuses; the reader
# gets the original bytes back.
FOR_A_READER = {'encoding': 'utf-8', 'errors': 'surrogateescape'}


def git(*args):
    """Read Git state without invoking a shell, trimmed for the usual single-value answer."""
    return git_raw(*args).strip()


def git_raw(*args):
    """The same, untrimmed: a NUL-delimited listing is exact, and stripping edits a name.

    A path may legitimately begin or end with whitespace, and trimming one silently
    collapses it onto its neighbour — which is how a file no finding named became
    invisible to the rule that exists to catch it.

    Decoded as the filesystem encodes names, with what does not decode kept as surrogate
    escapes. A repository may hold a path or a line that is not valid UTF-8 — a Latin-1 name
    committed on Linux, a Latin-1 source — and decoding strictly raised before any step could
    answer. The escapes survive the JSON state and reach git again as the original bytes, since
    an argument is encoded the same way; a reader is handed them through FOR_A_READER.
    """
    return subprocess.check_output(['git', *args], encoding=sys.getfilesystemencoding(),
                                   errors='surrogateescape')


def require(condition, message):
    """Reject an incomplete or stale review operation."""
    if not condition:
        raise ValueError(message)


def clean_head():
    """Resolve a candidate only when tracked and untracked work is clean."""
    # The envelope's own listing: a status listing honours the assume-unchanged bit,
    # submodule.<name>.ignore and status.showUntrackedFiles, and a tree that passed as clean
    # under any of them would start a pass on the author's edits.
    import review_prose
    require(not review_prose.changed(), 'Commit the intended candidate first; worktree is dirty.')
    return git('rev-parse', 'HEAD')
