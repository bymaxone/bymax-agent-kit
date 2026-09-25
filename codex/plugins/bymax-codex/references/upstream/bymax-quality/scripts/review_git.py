"""Git access layer: read repository state without a shell, and the one refusal every step
of the review runtime raises."""
import subprocess


def git(*args):
    """Read Git state without invoking a shell, trimmed for the usual single-value answer."""
    return git_raw(*args).strip()


def git_raw(*args):
    """The same, untrimmed: a NUL-delimited listing is bytes, and stripping edits a name.

    A path may legitimately begin or end with whitespace, and trimming one silently
    collapses it onto its neighbour — which is how a file no finding named became
    invisible to the rule that exists to catch it.
    """
    return subprocess.check_output(['git', *args], text=True)


def require(condition, message):
    """Reject an incomplete or stale review operation."""
    if not condition:
        raise ValueError(message)


def clean_head():
    """Resolve a candidate only when tracked and untracked work is clean."""
    require(not git('status', '--porcelain'), 'Commit the intended candidate first; worktree is dirty.')
    return git('rev-parse', 'HEAD')
