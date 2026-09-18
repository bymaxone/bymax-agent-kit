#!/usr/bin/env python3
"""What a delta asserts in words, and which of those assertions a command can settle.

The campaign already runs commands against code: a suite, a mutation matrix, declared gates.
None of them reads prose, and prose is where this package's correction rounds went. Measured
across two repositories on the same loop: a comment naming a constant the same commit deleted;
a paragraph describing a rule the same commit removed; two different counts of one fact inside
one delta; a `measured` line whose method was wrong in the command it did not print; a triage
disposition certifying a correction whose sentence was still in HEAD.

Tiers, because precision differs and a gate nobody trusts is worse than no gate:

    retired / unkept   exact       a name this delta removed, still asserted; a removal
                                   claimed of a string still present. These refuse.
    (a third tier, one subject given two counts, was built and deleted: measured on a real
     delta it produced seven false positives and no true one, because narrating history in a
     docstring states many numbers about many things. A heuristic at that precision trains a
     reader to skip the whole report, and the exact tier needs to be read.)
    unchecked          inventory   assertions no command here settles. Not a verdict — the
                                   list a reviewer is owed, so silence stops reading as proof.

Deliberately absent: anything that asks a model whether its own text is true. Re-reading
re-runs the reasoning that wrote the sentence, so the flawed premise is still in place and the
conclusion is reached again. The state of the art for that reaches AUC-PR 0.73-0.84 — a
detector, not a gate. Every check here is a command.
"""
import ast
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

FENCED = re.compile(r'```.*?```', re.DOTALL)
# A name worth resolving: CONSTANT_CASE, or snake_case with an underscore, or a call. Bare
# lowercase words are prose, not identifiers, and treating them as identifiers is how a
# checker like this earns its reputation for noise.
NAME = re.compile(r'`?\b([A-Z][A-Z0-9_]{2,}|[a-z_][a-z0-9_]*_[a-z0-9_]+)\b`?(?:\(\))?')
GONE = re.compile(r'\b(remove[sd]?|delete[sd]?|drop(?:s|ped)?|no longer|deleted|gone)\b',
                  re.IGNORECASE)
QUOTED = re.compile(r'`([^`\n]{4,80})`')


def git(*args, cwd=None):
    """stdout of a git command, or '' when git refuses — an absent side, never a crash."""
    done = subprocess.run(['git', *args], capture_output=True, text=True, cwd=cwd)
    return done.stdout if done.returncode == 0 else ''


def prose(name, text):
    """What a file asserts in words: markdown minus its examples, or docstrings and comments.

    A name inside a fenced block is an example about somebody else's repository, and a name
    inside a string literal is data the author passes to something. Neither is an assertion,
    and counting them as assertions was measured to produce false positives on this tree.
    """
    if name.endswith('.md'):
        return FENCED.sub(' ', text)
    if not name.endswith('.py'):
        return ''
    lines = text.split('\n')
    return '\n'.join(lines[n - 1] for n in sorted(marks(name, text)) if 0 < n <= len(lines))


def marks(name, text):
    """Line numbers a file devotes to words rather than to code.

    One definition, used by everything that has to tell prose from code: the claims report,
    the prose:code ratio the reviewers are shown, and the envelope that keeps a prose pass
    from editing behaviour. Two classifiers would drift, and the drift would be invisible
    until one of them let a code edit through as prose.
    """
    if name.endswith('.md'):
        return set(range(1, len(text.split('\n')) + 2))
    if not name.endswith('.py'):
        return set()
    found = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                found.update(range(tok.start[0], tok.end[0] + 1))
        # Docstrings by AST, not every string token. A string literal is data the author
        # passes to something — a fixture, an expected message, a command — and counting it
        # as prose does two wrong things at once: the claims report reads test data as
        # assertions (measured on this delta: a fixture containing "Six attempts" was read
        # as the author asserting six of something), and the prose pass would be allowed to
        # edit data while the envelope reported it had touched only words.
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                     ast.AsyncFunctionDef)):
                continue
            first = (node.body or [None])[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                found.update(range(first.lineno, first.end_lineno + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return set()
    return found


GENERATED = ('codex/plugins/bymax-codex/references/upstream/',)


def authored(name):
    """Whether this path is one the repository wrote rather than generated.

    The Codex mirror is a copy of the plugin sources, so every sentence in it exists twice by
    construction. Measured on this delta: reading it doubled every count and produced four
    removal claims that were each a file flagging its own mirror. A generated copy asserts
    nothing of its own.
    """
    return not name.startswith(GENERATED)


def touched(base, head, cwd=None):
    """The .md and .py files this delta changed, excluding what it generated."""
    listed = git('diff', '--name-only', '-z', base, head, cwd=cwd)
    return [n for n in listed.split('\0') if n.endswith(('.md', '.py')) and authored(n)]


def sides(name, base, head, cwd=None):
    """(before, after) prose for one file, either side possibly empty."""
    return (prose(name, git('show', '%s:%s' % (base, name), cwd=cwd)),
            prose(name, git('show', '%s:%s' % (head, name), cwd=cwd)))


def added(base, head, cwd=None):
    """Prose this delta added, per file: the lines present after and absent before."""
    out = {}
    for name in touched(base, head, cwd=cwd):
        before, after = sides(name, base, head, cwd=cwd)
        old = set(before.split('\n'))
        fresh = [line for line in after.split('\n') if line.strip() and line not in old]
        if fresh:
            out[name] = '\n'.join(fresh)
    return out


def split_delta(base, head, cwd=None):
    """Lines this delta added, separated into code and prose.

    One walker, because the count the reviewers are shown and the code-only view they are
    asked to review must agree. Two walkers would drift, and the drift would show up as a
    reviewer reviewing a hunk the count said was prose.
    """
    out = {'code': [], 'prose': []}
    for name in touched(base, head, cwd=cwd):
        after = review_marks(name, git('show', '%s:%s' % (head, name), cwd=cwd))
        at = None
        for row in git('diff', '-U0', base, head, '--', name, cwd=cwd).split('\n'):
            if row.startswith('@@'):
                at = int(row.split('+')[1].split(',')[0].split()[0])
            elif row.startswith('+') and not row.startswith('+++') and at is not None:
                out['prose' if at in after else 'code'].append((name, at, row[1:]))
                at += 1
    return out


def review_marks(name, text):
    """marks(), under the name split_delta reads it by, so one rename cannot split them."""
    return marks(name, text)


def defined(text):
    """Names a python source defines, read as text so a half-written file still answers."""
    found = set(re.findall(r'^\s*(?:def|class)\s+([A-Za-z_]\w*)', text, re.MULTILINE))
    found |= set(re.findall(r'^\s*([A-Z][A-Z0-9_]{2,})\s*=', text, re.MULTILINE))
    return found


def orphaned(base, head, cwd=None):
    """Names this delta removed from code and left defined nowhere in the tree."""
    lost = set()
    for name in touched(base, head, cwd=cwd):
        if name.endswith('.py'):
            lost |= defined(git('show', '%s:%s' % (base, name), cwd=cwd)) - \
                    defined(git('show', '%s:%s' % (head, name), cwd=cwd))
    # POSIX classes, not \s: git grep runs its own engine, where \s is not a space and the
    # pattern silently matches nothing. Measured — every name read as orphaned, including the
    # ones that had simply moved to another module, which is the false positive that would
    # have made this unusable on its first real delta.
    alive = r'^[[:space:]]*(def|class)[[:space:]]+%s\b|^[[:space:]]*%s[[:space:]]*='
    return sorted(name for name in lost
                  if not git('grep', '-lE', alive % (name, name), head,
                             '--', '*.py', cwd=cwd).strip())


def retired(base, head, cwd=None):
    """Names this delta removed from code that the tree's prose still asserts.

    Searched over the WHOLE tree, not over what the delta added — which is the correction that
    made this check work at all. A dangling reference is almost never in new text: the code
    moved and the sentence stayed. Measured on this repository's own history: a comment reading
    `rather than read from FOREIGN` survived the commit that deleted FOREIGN, sitting six lines
    from its own replacement, and an added-lines-only version of this function reported nothing.

    Matching the largest published study of this defect, which scanned over 3,000 GitHub
    projects and found most of them carry an outdated code-element reference at some point.
    """
    found = []
    for token in orphaned(base, head, cwd=cwd):
        listed = git('grep', '-lw', '--', token, head, '--', '*.py', '*.md', cwd=cwd)
        # Filtered here as well as in touched(): the search that finds the dangling mention is
        # a different search from the one that finds the removal, and excluding the generated
        # copy in only one of them leaves the other reporting a file that asserts nothing of
        # its own.
        for name in sorted({p.split(':', 1)[-1] for p in listed.split('\n')
                            if p and authored(p.split(':', 1)[-1])}):
            if re.search(r'\b%s\b' % token,
                         prose(name, git('show', '%s:%s' % (head, name), cwd=cwd))):
                found.append((name, token))
    return sorted(found)


def unkept(base, head, cwd=None):
    """Prose claiming a removal whose quoted subject is still in the tree, verbatim.

    Measured elsewhere on this loop: a triage disposition reading "Corrected with the other
    three", written without opening the file, where the sentence it certified as corrected was
    still in HEAD. A claim of removal is the one claim whose subject is quoted often enough to
    check, and checking it is a string search.
    """
    found = []
    for name, text in added(base, head, cwd=cwd).items():
        for line in text.split('\n'):
            if not GONE.search(line):
                continue
            for quote in QUOTED.findall(line):
                if len(quote.split()) < 2:
                    continue            # one word is a name, and names live on legitimately
                before = git('grep', '-Fl', '--', quote, base, cwd=cwd).count('\n')
                hit = git('grep', '-Fl', '--', quote, head, cwd=cwd)
                surviving = [p.split(':', 1)[-1] for p in hit.split('\n')
                             if p and authored(p.split(':', 1)[-1])
                             and p.split(':', 1)[-1] != name]
                # The phrase must have existed BEFORE. Nothing can be removed that was never
                # there, so a sentence quoting text this same delta wrote is narrating, not
                # claiming — which is what produced every false positive measured here: a
                # changelog quoting `69 passed` as an example from a file the commit created.
                # An earlier rule asked instead that a removal had happened somewhere, and it
                # dropped the worse case: a removal claimed and not carried out at all.
                if surviving and before:
                    found.append((name, quote, surviving[0]))
    return sorted(found)


def unchecked(base, head, cwd=None):
    """Assertions this file settles nothing about: the inventory a reviewer is owed.

    Not a verdict and not an accusation. Without it a clean run reads as "the prose is true",
    when what it means is "the two exact checks found nothing". Coverage stated is the only
    honest form of coverage.
    """
    lines = []
    for name, text in sorted(added(base, head, cwd=cwd).items()):
        for line in text.split('\n'):
            stripped = line.strip(' #\t')
            if len(stripped.split()) >= 6 and not stripped.startswith(('>>>', '$')):
                lines.append((name, ' '.join(stripped.split())[:110]))
    return lines


def report(base, head, cwd=None):
    """Every check, and the exit status the campaign reads: exact failures only."""
    gone, broken = retired(base, head, cwd=cwd), unkept(base, head, cwd=cwd)
    for name, token in gone:
        print('RETIRED  %s asserts %s, which this delta removed from the code' % (name, token))
    for name, quote, where in broken:
        print('UNKEPT   %s claims removal of `%s`, still present in %s' % (name, quote, where))
    rest = unchecked(base, head, cwd=cwd)
    print('\n%d assertion(s) added; %d exact failure(s). No command here settles the rest:'
          % (len(rest), len(gone) + len(broken)))
    for name, line in rest[:40]:
        print('   %s: %s' % (name, line))
    if len(rest) > 40:
        print('   ... and %d more' % (len(rest) - 40))
    return 1 if gone or broken else 0


def main(argv):
    if len(argv) != 3:
        print('usage: review_claims.py <base> <head>', file=sys.stderr)
        return 2
    return report(argv[1], argv[2], cwd=str(Path.cwd()))


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
