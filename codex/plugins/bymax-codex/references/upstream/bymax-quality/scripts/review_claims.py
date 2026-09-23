#!/usr/bin/env python3
"""What a delta asserts in words, and which of those assertions a command can settle.

The campaign already runs commands against code: a suite, a mutation matrix, declared gates.
None of them reads prose, and prose is where this package's correction rounds went. Measured
across two repositories on the same loop: a comment naming a constant the same commit deleted;
a paragraph describing a rule the same commit removed; two different counts of one fact inside
one delta; a `measured` line whose method was wrong in the command it did not print; a triage
disposition certifying a correction whose sentence was still in HEAD.

Tiers, because precision differs and a gate nobody trusts is worse than no gate:

    retired            exact       a name this delta removed that the tree still asserts,
                                   spelled like code rather than like an English word. This
                                   one refuses: measured at no false positive over 40 commits.
    unkept             reported     a removal claimed of a string still present. One false
                                   positive in those same 40 — a shell command read as the
                                   subject of a sentence near it — so it is read, not obeyed.
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

# A name inside a code block is an example about somebody else's repository, and reading it
# as an assertion refused a candidate whose README merely showed the call.
FENCE = re.compile(r'^(?P<indent> *)(?P<run>`{3,}|~{3,})(?P<info>.*)$')
NESTING = 100
ITEM = re.compile(r'^ *(?:(?:[-*+]|\d{1,9}[.)])(?:[ \t]+|$))+')
TAG = re.compile(r'<(?:(?P<close>/?)(?P<name>[A-Za-z][A-Za-z0-9-]*)(?=[\s/>]|$)|!--|\?|![A-Z]|!\[CDATA\[)')
ALONE = re.compile(r'</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>\s*$')
# CommonMark's block-level names: opened or closed, these start an HTML block anywhere.
BLOCK_TAGS = frozenset("""
    address article aside base basefont blockquote body caption center col colgroup dd details
    dialog dir div dl dt fieldset figcaption figure footer form frame frameset h1 h2 h3 h4 h5 h6
    head header hr html iframe legend li link main menu menuitem nav noframes ol optgroup option
    p param search section summary table tbody td tfoot th thead title tr track ul""".split())
# The raw-text names start one anywhere only when they open.
RAW_TAGS = frozenset(('pre', 'script', 'style', 'textarea'))
FIRST = re.compile(r'(?:[-*+]|0{0,8}1[.)])[ \t]')
MARKER = re.compile(r'(?P<mark>[-*+]|\d{1,9}[.)])(?:[ \t]+|$)')
DEFINITION = re.compile(r'\[(?:[^\]\\]|\\.)+\]: *(?:<[^<>\n]*>|[^ <][^ ]*)?'
                        r'(?: +(?:"[^"]*"|\'[^\']*\'|\([^()]*\)))? *$')
TITLE = re.compile(r'["\'(]')
UNDERLINE = re.compile(r' *(?:=+|-+) *$')
HEADING = re.compile(r'#{1,6}(?:[ \t]|$)')
BREAK = re.compile(r'([-*_])(?:[ \t]*\1){2,}[ \t]*$')
GONE = re.compile(r'\b(remove[sd]?|delete[sd]?|drop(?:s|ped)?|no longer|deleted|gone)\b',
                  re.IGNORECASE)
QUOTED = re.compile(r'`([^`\n]{4,80})`')


def root(cwd=None):
    """The worktree these questions are about, not the directory the process happens to be in.

    Every pathspec here (`-- '*.py'`, `-- <name>`) and every file read resolves against the
    caller's cwd, so running from a subdirectory answered about a subtree: measured, the
    checker reported zero changed files and missed a dangling reference it finds from the
    top. A tool whose answer depends on where it was invoked reports silence as cleanliness.
    """
    done = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                          capture_output=True, text=True, cwd=cwd)
    return done.stdout.strip() if done.returncode == 0 else (cwd or '.')


def git(*args, cwd=None):
    """stdout of a git command, or '' when git refuses — an absent side, never a crash."""
    done = subprocess.run(['git', *args], capture_output=True, text=True, cwd=root(cwd))
    return done.stdout if done.returncode == 0 else ''



def columns(line):
    """How far this line is indented. Its tabs are already spaces: outside_code() expands them."""
    return len(line) - len(line.lstrip(' '))


def outside_code(text):
    """Every Markdown code block blanked, and nothing else.

    Every regex spelling tried here fixed one shape while breaking another. The question needs
    state a regex has no way to carry, so the lines are walked once with it.
    """
    walk, out = Walk(), []
    for line in text.split('\n'):
        # Tabs are read as spaces to the next stop of four, as CommonMark reads block structure,
        # once and against the source line's own columns: expanded per container, a tab behind
        # a quote or a list marker was measured from a shortened line. A CRLF's carriage return
        # goes too, so from here on the walk measures indents and gaps in spaces alone.
        body = line.removesuffix('\r')
        # A lone carriage return ends a line too. Each is read as its own line and blanked in
        # place, so the output keeps every line break of the source, CR and LF alike.
        parts = [(part, part.expandtabs(4)) for part in body.split('\r')]
        read = [part if walk.read(spaced) == spaced else ' ' for part, spaced in parts]
        out.append('\r'.join(read) + line[len(body):])
    return '\n'.join(out)


class Walk:
    """One container read line by line: the document, or a block quote inside it.

    A quote holds Markdown of its own, so it gets a walk of its own, fed each line without its
    marker as the line arrives; a line that walk blanks is blanked here. Deciding each line once
    keeps the reading linear, where walking a quote again per line was quadratic.
    """

    def __init__(self, depth=0):
        self.fence, self.items, self.para, self.quote, self.html = None, [], False, None, False
        self.empty = self.defined = False
        self.depth = depth

    @property
    def content(self):
        """The column the innermost open list item's content starts at, or 0 outside a list."""
        return self.items[-1] if self.items else 0

    def read(self, line):
        """This line as prose sees it: the line, or a blank where it is code."""
        held = self.held(line)
        if held is not None:
            return held
        stripped, indent = line.strip(' '), columns(line)
        empty, self.empty = self.empty, False
        if not stripped:
            self.para, self.items = False, self.items[:-1] if empty else self.items
            return line
        # An indented block cannot interrupt a paragraph, and this far past the open item's
        # content the line is neither a marker nor a fence. No paragraph opens inside one, so a
        # block runs on over its own blank lines without a state of its own.
        if not self.para and indent < self.content:
            self.items = listing(line, indent, self.items)[0]
        if not self.para and indent >= self.content + 4:
            return ' '
        # A line continuing a paragraph lazily keeps its item open and starts no block. Measured
        # from the innermost item instead, a lazy line four columns short of it opened a fence.
        if self.para and lazy(line, self.items, indent >= self.content):
            return self.continued(line, indent)
        # Anything else is read against the open items, a `>` included, since a quote below the
        # item's content closes the item, and the item's paragraph ends with it.
        self.para = self.para and indent >= self.content
        self.items, mark = listing(line, indent, self.items)
        # What follows the markers is the item's first line and may open any block in it.
        if mark is not None:
            self.para, view = False, ' ' * mark + line[mark:]
            # An item opened empty ends at a blank line unless its content comes first.
            self.empty = not view.strip(' ')
            return line if self.empty or self.read(view) == view else ' '
        # Past NESTING a marker is read as text: each level is a frame, and a line of a
        # thousand markers exhausted the interpreter's recursion limit.
        if self.depth < NESTING and quotes(line, self.content):
            self.quote = Walk(self.depth + 1)
            return self.read(line)
        if html(line.lstrip(' '), self.para):
            self.html, self.para = ending(line.lstrip(' ')), False
            if self.html is not True and self.html in line.lower()[line.lower().index('<') + 1:]:
                self.html = False
            return line
        self.fence = opens(line)
        self.para = not (self.fence or indent < self.content + 4 and closing(line.lstrip(' ')))
        # A link reference definition is not a paragraph a line under it can underline.
        self.defined = self.para and bool(DEFINITION.match(line.lstrip(' ')))
        return ' ' if self.fence else line

    def continued(self, line, indent):
        """This line, which only continues the open paragraph, and what it leaves open.

        An underline the paragraph's own container reads ends it as a heading; under a link
        reference definition it is text, and a definition's title may follow it on its own line.
        """
        text = line.lstrip(' ')
        self.para = not (not self.defined and self.content <= indent < self.content + 4
                         and UNDERLINE.match(line))
        self.defined = self.defined and bool(DEFINITION.match(text) or TITLE.match(text))
        return line

    def held(self, line):
        """This line as the open quote, fence or HTML block reads it, or None where none holds it."""
        if self.quote is not None:
            if quotes(line, self.content) and columns(line) >= self.content:
                inner = unquoted(line)
                seen = self.quote.read(inner)
                self.para = self.quote.para
                return line if seen == inner else ' '
            # A line without a marker belongs to the quote only as a continuation of its open
            # paragraph, which no walk inside the quote reads again as a block of its own.
            if line.strip(' ') and self.quote.para and lazy(line, self.items, False):
                return line
            self.quote, self.para = None, False
        stripped, indent = line.strip(' '), columns(line)
        if self.fence is not None and (not stripped or indent >= self.content):
            # A closing fence, like an opening one, stands under four columns past the content.
            self.fence = None if indent < self.content + 4 and closes(line, self.fence) else self.fence
            return ' ' if stripped else line
        # A line that leaves the item ends the fence or the HTML block opened inside it; inside,
        # an HTML block with an end text holds every line up to the one carrying that text.
        self.fence = None
        if self.html is True and stripped and indent >= self.content:
            return line
        if self.html and self.html is not True and (not stripped or indent >= self.content):
            self.html = False if self.html in line.lower() else self.html
            return line
        self.html = False
        return None


def lazy(line, items, restricted):
    """Whether this line, read under an open paragraph, only continues it.

    Where the line reaches the paragraph's own container, a marker opens a list there only with
    text after it and, when ordered, only numbered 1: `2. two` there is a continuation.
    """
    # Measured from the content of the container the line reaches, not of the innermost item.
    reached = [column for column in items if column <= columns(line)]
    if columns(line) >= (reached[-1] if reached else 0) + 4:
        return True
    text = line.lstrip(' ')
    item = ITEM.match(line)
    # The first item's own text decides: in `- -` the second marker is that text.
    first = MARKER.match(text)
    if item and restricted and not (first and text[first.end():].strip(' ') and FIRST.match(text)):
        item = None
    return not (item or text.startswith('>') or html(text, restricted) or FENCE.match(text)
                or closing(text))


def ending(text):
    """What ends the HTML block this text starts: the text that closes it, or True where a
    blank line does. A comment runs to `-->` over blank lines, and so do raw-text tags."""
    lowered = text.lower()
    for start, end in (('<!--', '-->'), ('<?', '?>'), ('<![cdata[', ']]>')):
        if lowered.startswith(start):
            return end
    if re.match(r'<![A-Z]', text):
        return '>'
    raw = re.match(r'<(pre|script|style|textarea)(?=[\s>]|$)', lowered)
    return '</%s>' % raw.group(1) if raw else True


def html(text, para):
    """Whether this text, stripped of its indent, starts an HTML block. A comment, a declaration,
    a BLOCK_TAGS name or an opening RAW_TAGS name may interrupt a paragraph; any other tag starts
    one only alone on its line and where no paragraph is open."""
    found = TAG.match(text)
    if not found:
        return False
    name = (found['name'] or '').lower()
    if not name or name in BLOCK_TAGS or name in RAW_TAGS and ending(text) is not True:
        return True
    return not para and bool(ALONE.match(text))


def closing(text):
    """Whether this text, stripped of its indent, is a heading or a thematic break: a line that
    interrupts a paragraph and leaves none open after it."""
    return bool(HEADING.match(text) or BREAK.match(text))


def quotes(line, content):
    """Whether this line is a block quote's: a `>` less than four columns past the item content."""
    return line.lstrip(' ').startswith('>') and columns(line) < content + 4


def unquoted(line):
    """The line through its first `>` removed, and the one optional column after it."""
    rest = line.partition('>')[2]
    return rest[1:] if rest.startswith(' ') else rest


def listing(line, indent, items):
    """The content columns of the list items open once this line is read, innermost last, and
    where the text after the markers this line opened starts, or None where it opened none.

    A line indented less than an item's content closes it and every item inside it, and each
    marker on the line opens one: `- 1. x` is two items, and closing the inner one returns to
    the outer one's column rather than to none.
    """
    kept = [column for column in items if column <= indent]
    # Four columns past the content it reaches, a marker is inside an indented block.
    if not ITEM.match(line) or BREAK.match(line.lstrip(' ')) or indent >= (kept[-1] if kept else 0) + 4:
        return kept, None
    at, last = len(line) - len(line.lstrip(' ')), len(line.rstrip(' '))
    for marker in MARKER.finditer(line, at):
        if marker.start() != at:
            break
        end = marker.start() + len(marker['mark'])
        gap = marker.end() - end
        # Past four columns of gap, or with nothing after it, the content starts one column
        # past the marker, and what follows is an indented block or the item's next line.
        wide = gap > 4 or marker.end() >= last
        kept.append(end + 1 if wide else end + gap)
        at = end if wide else marker.end()
    return kept, at


def opens(line):
    """The fence this line opens, as its character and its length, or None where it opens none."""
    found = FENCE.match(line)
    return (found['run'][0], len(found['run'])) if found else None


def closes(line, fence):
    """Whether this line ends the open fence: the same character, at least as long, and nothing
    after it — an info string is allowed where a fence opens and nowhere else."""
    found = FENCE.match(line)
    return bool(found and found['run'][0] == fence[0] and len(found['run']) >= fence[1]
                and not found['info'].strip(' '))


def prose(name, text):
    """What a file asserts in words: markdown minus its examples, or docstrings and comments.

    A name inside a fenced block is an example about somebody else's repository, and a name
    inside a string literal is data the author passes to something. Neither is an assertion,
    and counting them as assertions was measured to produce false positives on this tree.
    """
    if name.endswith('.md'):
        return outside_code(text)
    if not name.endswith('.py'):
        return ''
    lines = text.split('\n')
    return '\n'.join(lines[n - 1] for n in sorted(marks(name, text)) if 0 < n <= len(lines))


def marks(name, text):
    """Line numbers a file devotes to words rather than to code.

    One definition, used by everything that has to tell prose from code: the claims report
    and the code-to-prose ratio the reviewers are shown. Two classifiers would drift, and the
    drift would be invisible until one of them read a line of code as a sentence.
    """
    if name.endswith('.md'):
        return set(range(1, len(text.split('\n')) + 2))
    if not name.endswith('.py'):
        return set()
    found = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            # Only where the comment is the whole line. Marking a line prose because it ENDS
            # in a comment filed `enabled = check()  # explanation` — code with a note after it,
            # the commonest edit there is — under prose, and the code view then told a reviewer
            # the delta changed no code while a production line had changed. The brief asserting
            # what the tree does not support is the defect this whole delivery is about.
            if tok.type == tokenize.COMMENT and not tok.line[:tok.start[1]].strip():
                found.update(range(tok.start[0], tok.end[0] + 1))
        # Docstrings by AST, not every string token. A string literal is data the author
        # passes to something — a fixture, an expected message, a command — and counting it
        # as prose does two wrong things at once: the claims report reads test data as
        # assertions (measured on this delta: a fixture containing "Six attempts" was read
        # as the author asserting six of something).
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


READABLE = ('.md', '.py')


def touched(base, head, cwd=None):
    """Files this delta changed whose prose this module can read.

    Renames are not detected: git reports a rename as the destination alone, and a definition
    removed in the same commit then lived in a path the base does not have, so nothing was
    read as removed at all.
    """
    listed = git('diff', '--name-only', '--no-renames', '-z', base, head, cwd=cwd)
    return [n for n in listed.split('\0') if n.endswith(READABLE) and authored(n)]


def opaque(base, head, cwd=None):
    """Files this delta changed whose prose this module CANNOT read.

    Only Python and Markdown are classified here. On a TypeScript, Rust or shell repository
    every changed file lands in this list, and saying so is the difference between a checker
    that is silent and one that lies: without it the brief told both reviewers that a real
    code delta changed no code, and that two checks had run over files nothing had opened.
    Renames are not detected here either: a renamed file the module cannot read changed on
    both sides, and counting it once tells the reader one side of it stayed put.
    """
    listed = git('diff', '--name-only', '--no-renames', '-z', base, head, cwd=cwd)
    return [n for n in listed.split('\0')
            if n and not n.endswith(READABLE) and authored(n)]


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


def unreadable(base, head, out, cwd=None):
    """Add what this module cannot read, counted by its real changed lines.

    A separate walk because it answers a different question: the readable side asks which
    lines are prose, and this side has no way to ask, so every changed line is code until
    something proves otherwise. Counting one row per file announced a six-hundred-line
    TypeScript delta as three lines, which is false in a new direction rather than true.
    """
    for name in opaque(base, head, cwd=cwd):
        rows = len(out['code'])
        at = was = None
        for row in git('diff', '-U0', '--output-indicator-new=>', '--output-indicator-old=<',
                       base, head, '--', name, cwd=cwd).split('\n'):
            if row.startswith('@@'):
                # Both coordinates. Reading only the added side numbered a removed line by
                # where it is NOT: a line deleted from old line 2 printed as `- a.ts:1`,
                # because the new side had moved on. A removal is located where it was.
                was = int(row.split('-')[1].split(',')[0].split()[0])
                at = int(row.split('+')[1].split(',')[0].split()[0])
            elif row.startswith('>'):
                out['code'].append((name, at or 0, row[1:]))
                at = (at + 1) if at else at
            elif row.startswith('<'):
                # Negative, like every other removal here — and never -0, which is 0 and reads
                # as an addition. A whole-file deletion has no added side, so its hunk header
                # says +0; taking the sign from that printed a deleted file as added, which is
                # the same defect one shape along from the one this replaced.
                # No `or` guard: a hunk carrying a removed line always numbers the old side
                # from 1, so the alternative could never fire and a mutant of it proved
                # nothing. A defensive branch that cannot run is a branch nothing can cover.
                out['code'].append((name, -was, row[1:]))
                was += 1
        if len(out['code']) == rows:
            # A binary file, a mode change or a pure rename has no text diff, and counting
            # zero rows for it announced "this delta changed no code" about a delta that
            # changed two files. One row says the file moved without claiming a line count
            # nothing can read.
            # Coordinate 0: the file changed and no line did, so naming a line would invent
            # one. The brief marks a row + or - by the sign, and 0 is neither, which is the
            # honest answer for a binary, a mode change or a pure rename.
            out['code'].append((name, 0, '(changed with no text diff)'))


def split_delta(base, head, cwd=None):
    """Lines this delta changed, added and removed, separated into code and prose.

    One walker, because the count the reviewers are shown and the code-only view they are
    asked to review must agree. Two walkers would drift, and the drift would show up as a
    reviewer reviewing a hunk the count said was prose.
    """
    out = {'code': [], 'prose': []}
    for name in touched(base, head, cwd=cwd):
        after = review_marks(name, git('show', '%s:%s' % (head, name), cwd=cwd))
        before = review_marks(name, git('show', '%s:%s' % (base, name), cwd=cwd))
        at = was = None
        for row in git('diff', '-U0', '--output-indicator-new=>', '--output-indicator-old=<',
                       base, head, '--', name, cwd=cwd).split('\n'):
            if row.startswith('@@'):
                was = int(row.split('-')[1].split(',')[0].split()[0])
                at = int(row.split('+')[1].split(',')[0].split()[0])
            # Indicators of git's choosing rather than its defaults: under `+`, a content
            # line `++n` prints as `+++n` and the header test dropped it, so a reviewer was
            # handed a delta missing the line that changed. `>` never opens a header.
            elif row.startswith('>') and at is not None:
                out['prose' if at in after else 'code'].append((name, at, row[1:]))
                at += 1
            elif row.startswith('<') and was is not None:
                # A deletion is a change. Counting only additions told both reviewers that a
                # correction which removed four lines of live code had changed no code.
                out['prose' if was in before else 'code'].append((name, -was, row[1:]))
                was += 1
    # Whatever this module cannot read is code until something proves otherwise: an unknown
    # file is not a file without claims, it is a file whose claims nothing here read. Counted
    # by its real changed lines — one row per file announced a 600-line TypeScript delta as
    # three lines of code, which is differently false rather than true.
    unreadable(base, head, out, cwd=cwd)
    return out


def review_marks(name, text):
    """marks(), under the name split_delta reads it by, so one rename cannot split them."""
    return marks(name, text)


def defined(text):
    """Names a python source defines, read as text so a half-written file still answers.
    An `async def` is a def: without it, an async function's removal went unreported."""
    found = set(re.findall(r'^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)', text, re.MULTILINE))
    found |= set(re.findall(r'^\s*([A-Z][A-Z0-9_]{2,})\s*=', text, re.MULTILINE))
    return found


def orphaned(base, head, cwd=None):
    """Names this delta removed from code and left defined nowhere in the tree."""
    lost = set()
    for name in touched(base, head, cwd=cwd):
        if name.endswith('.py'):
            lost |= defined(git('show', '%s:%s' % (base, name), cwd=cwd)) - \
                    defined(git('show', '%s:%s' % (head, name), cwd=cwd))
    # Neither \s nor \b: git grep runs its own engine, where both are literal and a pattern
    # using either silently matches nothing. Corrected twice — the \s half first, the \b half
    # only after a reviewer found that every function which merely MOVED to another module
    # read as removed. An `async def` counts here as it does in defined(): a name moved and
    # made async is alive.
    alive = (r'^[[:space:]]*(async[[:space:]]+)?(def|class)[[:space:]]+%s([^A-Za-z0-9_]|$)'
             r'|^[[:space:]]*%s[[:space:]]*=')
    return sorted(name for name in lost
                  if not git('grep', '-lE', alive % (name, name), head,
                             '--', '*.py', cwd=cwd).strip())


def code_shaped(token):
    """Whether a name could only be a code reference, never an ordinary English word.

    Measured on this delivery's own candidate: deleting a module orphaned its `prepare()`, and
    five files were accused of a dangling reference for containing the English word — a README,
    a command, an example. The gate refused the very candidate that added it. A name is a
    reference here when it is CONSTANT_CASE, or carries an underscore, or is capitalised and
    four characters or more; a bare lowercase word is prose until it is spelled like code. A capitalised name of four
    characters or more counts, which reaches CamelCase classes and acronym-led ones like
    HTTPServer; a capitalised English word opening a sentence could in principle reach it too,
    but only if something also DEFINED it and removed it, which is what orphaned() already
    required.

    A call — `outcome()` — would qualify too, and does not: deciding it needs the sentence,
    not the name, and this function is given only the name. A single-word lowercase function
    is therefore missed, which is a stated gap rather than a silent one. An earlier attempt at
    that lived here as a helper nobody called, which is the dead-rule shape this file warns
    about two functions down; it was deleted rather than left standing.

    An earlier version of this idea existed as an unused regex and was deleted as dead code,
    correctly: a rule that is defined and never applied is worse than absent, because its
    comment claims a protection nobody has.
    """
    return bool('_' in token
                or re.fullmatch(r'[A-Z][A-Z0-9_]{2,}', token)      # CONSTANT_CASE
                or re.fullmatch(r'[A-Z]\w{3,}', token) and any(c.islower() for c in token))


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
        if not code_shaped(token):
            continue
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


def claimed(line, quote):
    """Whether this line claims THIS subject was removed, rather than merely naming it.

    Given the line and the subject, and nothing else: an earlier version of this code lived
    inside unkept() and bound a slice of text to `head`, the revision that function is given,
    which sent every later git call looking inside a sentence instead of at the tree. The
    local name is `run_up` rather than `head` because a reviewer caught that same shadowing
    a round earlier in another file, so it is named here instead of quietly renamed.

    The verb must be in PROSE and in the run-up to the subject: outside the
    quoted subject itself, outside every other quoted span on the line, and
    before it. `git worktree remove` and `DROP TABLE` name things rather than
    promise anything about them.
    
    Measured over the last 40 mainline commits: reading the verb anywhere on
    the line refuses 8 of them; allowing it just after the subject refuses 5;
    the run-up alone refuses 1. Every one of the extra refusals is a backticked
    SHELL COMMAND — `ack --pager`, `rg --pre`, `git ls-remote --upload-pack` —
    named in a sentence that happens to contain the word. A command is a name.
    
    So the run-up alone, and the verb-last form ("`X` was removed") is a STATED
    gap rather than a hidden one: in a gate that refuses a push, a claim missed
    costs a sentence and a candidate wrongly blocked costs the delivery. An
    earlier disposition of mine recorded a case for the verb-last form that was
    never written; this is what that correction should have said.
    """
    run_up, _, _ = line.partition('`' + quote + '`')
    said = QUOTED.sub(' ', run_up)
    hit = GONE.search(said)
    if not hit:
        return False
    # "We did not remove X" is the opposite of a promise, and reading it as one refuses a
    # sentence written to say the work was NOT done. Only the clause carrying the verb is
    # examined: a negation earlier in a different clause is about something else.
    clause = re.split(r'[.;:,]|—|--', said[:hit.start()])[-1]
    return not re.search(r'\b(not|never|without|cannot|rather than)\b', clause, re.IGNORECASE)


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
            for quote in QUOTED.findall(line):
                if not claimed(line, quote):
                    continue
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
    when what it means is "the one refusing check found nothing". Coverage stated is the only
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
        print('UNKEPT   %s claims removal of `%s`, still present in %s — reported, not refused'
              % (name, quote, where))
    rest = unchecked(base, head, cwd=cwd)
    print('\n%d assertion(s) added; %d refusing, %d reported. No command here settles the '
          'rest:' % (len(rest), len(gone), len(broken)))
    for name, line in rest[:40]:
        print('   %s: %s' % (name, line))
    if len(rest) > 40:
        print('   ... and %d more' % (len(rest) - 40))
    # Only the dangling reference refuses. Measured over 40 mainline commits: retired()
    # reports none of them once a name must be spelled like code, while unkept() reports one —
    # a backticked shell command read as the subject of a nearby sentence. One wrong refusal
    # every forty commits is a delivery blocked by mistake, and this check is not worth that.
    # It is read, not obeyed, which is the same trade `trigger` makes for a finding.
    return 1 if gone else 0


def main(argv):
    """The command line: a base and a head, and the report over the delta between them.
    Exit 1 for a refusal — a claim the delta contradicts — and 0 otherwise, whatever
    the report merely reports; 2 is a bad command line."""
    if len(argv) != 3:
        print('usage: review_claims.py <base> <head>', file=sys.stderr)
        return 2
    return report(argv[1], argv[2], cwd=str(Path.cwd()))


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
