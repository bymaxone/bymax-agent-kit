"""Git access layer: read repository state without a shell, and the refusal a review step
raises."""
import codecs
import subprocess
import sys


def for_a_reader(text):
    """Text as a model reads it: valid UTF-8, what git gave read back as the bytes it was, and a
    byte that is not UTF-8 spelled \\xNN. Codex refuses stdin that is not valid UTF-8 before any
    model reads it, so the bytes git_raw() keeps as surrogate escapes cannot be handed on raw.

    Each character goes back through the filesystem encoding git_raw() read with, so a UTF-8 name
    read under a Latin-1 locale reaches the reader as itself; one that encoding cannot hold — an
    em dash in the runtime's own sentences — goes as its UTF-8, since it never came from git. A
    character of the Latin-1 range written in the runtime's own text would come out spelled under
    a Latin-1 locale; none is, outside comments.
    """
    return text.encode(sys.getfilesystemencoding(), 'bymax-reader').decode('utf-8', 'backslashreplace')


def as_given(error):
    """Encode what the filesystem encoding cannot: a surrogate escape as the byte it stands for,
    anything else as its UTF-8."""
    part = error.object[error.start:error.end]
    return b''.join(bytes([ord(c) - 0xDC00]) if 0xDC80 <= ord(c) <= 0xDCFF else c.encode('utf-8')
                    for c in part), error.end


codecs.register_error('bymax-reader', as_given)


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
    an argument is encoded the same way.
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
