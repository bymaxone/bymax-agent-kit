"""Git access layer: read repository state without a shell, and the refusal a review step
raises."""
import subprocess


def git(*args):
    """Read Git state without invoking a shell, trimmed for the usual single-value answer."""
    return git_raw(*args).strip()


def git_raw(*args):
    """The same, untrimmed: a NUL-delimited listing is exact, and stripping edits a name.

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
    # The envelope's own listing: a status listing honours the assume-unchanged bit,
    # submodule.<name>.ignore and status.showUntrackedFiles, and a tree that passed as clean
    # under any of them would start a pass on the author's edits.
    import review_prose
    require(not review_prose.changed(), 'Commit the intended candidate first; worktree is dirty.')
    # The listing above compares the tree with HEAD through an index of its own, so a change
    # staged and then reverted in the tree reads as clean there, and the next commit takes it.
    require(not git_raw('diff', '--cached', '--name-only', '-z'),
            'Commit the intended candidate first; the index differs from HEAD.')
    return git('rev-parse', 'HEAD')
