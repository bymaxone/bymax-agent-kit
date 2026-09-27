"""Git access layer: read repository state without a shell, and the refusal a review step
raises."""
import subprocess
import sys


def for_a_reader(text):
    """Text as a model reads it: the bytes git gave, as UTF-8, with a byte that is not UTF-8
    spelled \\xNN. git_raw() keeps such a byte as a surrogate escape, and Codex refuses stdin
    that is not valid UTF-8 before any model reads it, so the bytes themselves cannot be handed
    on. Encoded back through the filesystem encoding first, because that is how git_raw() read
    them: re-encoding the decoded text as UTF-8 garbled a UTF-8 name under a Latin-1 locale."""
    return text.encode(sys.getfilesystemencoding(), 'surrogateescape').decode('utf-8', 'backslashreplace')


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
    answer. The escapes reach git again as the original bytes, since
    an argument is encoded the same way; a reader is handed them through for_a_reader().
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
