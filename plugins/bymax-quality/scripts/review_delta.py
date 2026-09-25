"""Delta layer: what a candidate's delta shows its reviewers, code first, then what the claims
checker settled and what the delta did to tests; and the refusal for prose a command already
disproves. Read by the orchestration in review_flow when it writes the brief and opens a round."""
import review_claims
from review_evidence import merged_in_tests, tests_changed
from review_git import require


def regression_note(state):
    """What the delta did to tests, and what the reviewer should do about it.

    Read from the diff on every round. This read `regression_tests`, which only a correction
    round sets, and the round the note was first shown on round one it told a reviewer
    "No test changed in this delta. Recorded reason: ." about a delta that changed four test
    files — the brief asserting what the tree does not support, committed while widening the
    brief so that round one would stop being blind. The input has one source now.
    """
    tests, _ = tests_changed(state['review_base'], state['head'])
    # Named in every branch, because the diff shown beside this note holds those files: silence
    # here while a changed test is visible there is the brief contradicting itself in one message.
    carried = merged_in_tests(state['review_base'], state['head'])
    also = ('' if not carried else
            ' This delta also changes ' + ', '.join(carried) + ', none of it on its own '
            'first-parent line, so nothing here can say whose work it is and no matrix is asked '
            'for it. Judge those changes on the diff.')
    if tests:
        return ('Tests changed in this delta: ' + ', '.join(tests)
                + '. A test whose expectation was flipped rather than added must be justified '
                'in the triage evidence; report an unjustified flip.' + also)
    reason = state.get('no_regression_reason', '')
    if reason:
        return ('No test this correction wrote changed. Recorded reason: ' + reason
                + '. Judge whether that is justified.' + also)
    return ('No test this correction wrote changed. Judge whether a delta this size can carry '
            'no case.' + also)


def code_touched(base, head):
    """Lines this delta changed, added and removed, counted as code and as prose.

    A correction that writes only prose is a round spent on text, and the prose it writes is
    the next round's findings — so the two are counted apart and the difference is stated.
    """
    split = review_claims.split_delta(base, head)
    return {kind: len(rows) for kind, rows in split.items()}


def code_view(state):
    """The delta with its prose hunks elided: what a logic reviewer is asked to review.

    Not a blindfold — the tree is theirs to read, and a logic defect noticed BECAUSE a
    docstring disagrees with the code is still a logic defect and still wanted. What it does
    is put the code where the eye lands, in a delta whose prose usually outweighs it.
    """
    split = review_claims.split_delta(state['review_base'], state['head'])
    if not split['code']:
        return ('This delta changed no code — %d prose line(s) only. A prose-only correction is '
                'a round spent on text; judge whether it earned one.' % len(split['prose']))
    shown = ['Code changed in this delta, prose elided: %d code line(s), %d prose, marked + for '
             'an added line, - for a removed one and ? for a file that changed without any '
             'line changing, such as a binary or a rename. Review THIS first. A finding whose fix is '
             'CODE is yours however you noticed it — including by a comment disagreeing with '
             'what the code does.' % (len(split['code']), len(split['prose']))]
    for name, at, text in split['code'][:120]:
        # A removal is rendered as one. It reached reviewers as `file:-39 <text>` through the
        # format an addition uses, with nothing saying what the minus meant.
        mark = '+' if at > 0 else '-' if at < 0 else '?'
        shown.append('  %s %s:%d %s' % (mark, name, abs(at), text.rstrip()[:100]))
    if len(split['code']) > 120:
        shown.append('  ... and %d more; the full diff is yours to read.' % (len(split['code']) - 120))
    return '\n'.join(shown)


def claims_coverage(state):
    """What the claims checker settled, and — the part that matters — what it did not.

    The inventory is a count and a command rather than the lines themselves: a delta adds a
    hundred assertions and pasting them would cost every reviewer the context they need for
    the code. What must not be cheap is the statement that nothing checked them, because a
    silent checker reads as "the prose is true" when it means "the one refusing check found nothing".
    """
    base, head = state['review_base'], state['head']
    rest = review_claims.unchecked(base, head)
    unread = review_claims.opaque(base, head)
    said = ['Prose in this delta: one exact check ran and passed — no name it asserts was '
            'removed by this delta and left dangling.']
    # Run here rather than described here. The brief said a second check reports, and nothing
    # on this path called it, so its rows reached nobody — a sentence about a check is not the
    # check. It refuses nothing: across 40 mainline commits it flags one, a shell command read
    # as the subject of a sentence beside it, and one wrong refusal in forty is a delivery
    # blocked by mistake.
    for where, quote, still in review_claims.unkept(base, head):
        said.append('REPORTED, not refusing: %s says `%s` is gone and it is in %s. Judge it; '
                    'it cannot hold a receipt.' % (where, quote, still))
    if unread:
        said.append('They read Python and Markdown only, so they read NOTHING in %d changed '
                    'file(s) of other kinds (%s). For those the checks are silent, which is not '
                    'the same as clean.' % (len(unread), ', '.join(unread[:6])))
    counts = code_touched(base, head)
    if counts['prose'] or counts['code']:
        said.append('This delta changed %d line(s) of code and %d of prose. Prose is surface '
                    'no command checks: judge whether the explanation earns its size.'
                    % (counts['code'], counts['prose']))
    said.append('%d assertion(s) added that NO command settles — docstrings, comments and '
                'markdown, which is what this reads. They are unverified, not verified; treat '
                'each as a claim to check against the code. List them with '
                '`review_claims.py %s %s`.' % (len(rest), base, head))
    return ' '.join(said)


def claims_settled(base, head):
    """Refuse a candidate whose own prose asserts something a command already disproves.

    The suite runs against code; the mutation matrix runs against rules; nothing ran against
    sentences, and sentences are where this package's correction rounds went. Each refusal
    here was measured on a real delta, and each was found by a reviewer a round later, at
    the cost of a candidate.
    """
    gone = review_claims.retired(base, head)
    require(not gone, 'Prose asserts a name this delta removed from the code: '
            + '; '.join('%s says %s' % (where, name) for where, name in gone)
            + '. Correct the sentence or restore the name before a reviewer spends a round on it.')


def delta_view(state):
    """The delta as a reviewer is asked to read it: code first, then what the checks settled.

    Built for EVERY round. These three lived inside correction_brief, which returns early on
    round one, so the round that reads the whole delta received none of them while the
    changelog said every reviewer receives them. Round one is where the last of them matters
    most: on a repository of languages these checks cannot read, "they read NOTHING in N
    changed files" is the sentence that stops silence from reading as clean, and it was
    absent from exactly the reading that covers the most ground.
    """
    return '\n'.join([code_view(state), claims_coverage(state), regression_note(state)])
