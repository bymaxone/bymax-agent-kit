"""Markdown block layer: which lines of a document are code blocks, read as CommonMark reads them.

The block-structure layer under review_claims: it knows nothing about git, a delta or a claim.

A line is judged against the lines before it, so the reading is a walk with state rather than
a pattern: every regex spelling tried for it fixed one shape while breaking another.
"""
import re

FENCE = re.compile(r'^(?P<indent> *)(?P<run>`{3,}|~{3,})(?P<info>.*)$')
NESTING = 100
ITEM = re.compile(r'^ *(?:(?:[-*+]|\d{1,9}[.)])(?:[ \t]+|$))+')
TAG = re.compile(r'<(?:(?P<close>/?)(?P<name>[A-Za-z][A-Za-z0-9-]*)(?=[\s/>]|$)|!--|\?|![A-Za-z]|!\[CDATA\[)')
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
RUN = re.compile(r'(?:[^\[\]\\]|\\.?)*')
LABEL = re.compile(r'\[((?:[^\[\]\\]|\\.){1,999})\]:')
UNDERLINE = re.compile(r' *(?:=+|-+) *$')
HEADING = re.compile(r'#{1,6}(?:[ \t]|$)')
BREAK = re.compile(r'([-*_])(?:[ \t]*\1){2,}[ \t]*$')


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
        # from the innermost item instead, a line four columns into its container opened a fence.
        if self.para and lazy(line, self.items, indent >= self.content):
            return self.continued(line, indent)
        # Anything else is read against the open items, a `>` included, since a quote below the
        # item's content closes the item.
        self.items, mark = listing(line, indent, self.items)
        # What follows the markers is the item's first line and may open any block in it.
        if mark is not None:
            self.para, view = False, ' ' * mark + line[mark:]
            # An item opened empty ends at a blank line unless its content comes first.
            self.empty = not view.strip(' ')
            return line if self.empty or self.read(view) == view else ' '
        # Past NESTING a `>` is read as text: each level is a frame, and a line of a
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
        # A paragraph of complete link reference definitions is not one an underline heads.
        self.defined = self.para and definition(line.lstrip(' '))
        return ' ' if self.fence else line

    def continued(self, line, indent):
        """This line, which only continues the open paragraph, and what it leaves open.

        An underline the paragraph's own container reads ends it as a heading, unless the paragraph
        holds only complete link reference definitions, which leave no text for it to head.
        """
        self.para = not (self.defined not in ('whole', 'titled') and self.content <= indent < self.content + 4
                         and UNDERLINE.match(line))
        self.advance(line.lstrip(' '))
        return line

    def advance(self, text):
        """Carry a continuation line into the definition state of the innermost open paragraph."""
        if self.quote is not None:
            self.quote.advance(text)
        else:
            self.defined = defining(self.defined, text)

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
                self.quote.advance(line.lstrip(' '))
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


def definition(text):
    """The state a link reference definition starting on this text leaves, or None if it starts
    none: 'bracket' or 'empty' while its label runs on, 'label' with the destination to come, 'whole'
    with it, 'titled' with its one title, 'open' and the closing character while a title runs on."""
    found = LABEL.match(text)
    if not found:
        return bracketed('empty', text[1:]) if text.startswith('[') else None
    return destined(text[found.end():], 'label') if found[1].strip() else None


def bracketed(state, text):
    """The state after more of an open label: 'empty' while it holds only space, 'bracket' once
    it holds text, then what its destination leaves; a label of space alone is no definition."""
    closed = labelled(text)
    state = 'bracket' if state == 'bracket' or text[:closed and closed - 2].strip(' ') else 'empty'
    if closed is None:
        return state
    return destined(text[closed:], 'label') if closed and state == 'bracket' else None


def labelled(text):
    """Where the label running through this text closes, just past its `]:`: None while it
    runs on, False where it closes without the colon or breaks on another bracket."""
    found = RUN.match(text)
    if found.end() == len(text):
        return None
    return found.end() + 2 if text[found.end():found.end() + 2] == ']:' else False


def defining(state, text):
    """The definition state after one more line of the paragraph it opened, or None once the
    paragraph is past any definition."""
    if state == 'label':
        return destined(text, None)
    if state in ('bracket', 'empty'):
        return bracketed(state, text)
    if state == 'whole':
        return definition(text) or titled(text, None)
    if state and state.startswith('open'):
        return titled(('(' if state[-1] == ')' else state[-1]) + text, None)
    return definition(text) if state == 'titled' else None


def destined(rest, empty):
    """The state a destination and what follows it leave, `empty` where there is nothing."""
    rest = rest.strip(' ')
    if not rest:
        return empty
    pointed = re.match(r'<(?:[^<>\\]|\\.)*>', rest)
    target = pointed.group(0) if pointed else rest.split(' ', 1)[0]
    # An unbalanced destination is none, and CommonMark reads the line as paragraph text.
    if rest.startswith('<') and not pointed or not pointed and not balanced(target):
        return None
    after = rest[len(target):]
    return titled(after, 'whole') if not after or after.startswith(' ') else None


def titled(rest, none):
    """The state a title leaves: 'titled' closed with nothing after it, 'open' and its closing
    character while it runs on, `none` where there is no title, None where it is malformed."""
    rest = rest.strip(' ')
    if not rest:
        return none
    closer = {'"': '"', "'": "'", '(': ')'}.get(rest[0])
    at = 1
    while closer and at < len(rest):
        if rest[at] == '\\':
            at += 2
            continue
        if rest[at] == closer:
            return None if rest[at + 1:].strip(' ') else 'titled'
        if closer == ')' and rest[at] == '(':
            return None
        at += 1
    return 'open' + closer if closer else None


def balanced(destination):
    """Whether a destination's parentheses balance, escapes aside."""
    depth = 0
    for char in re.sub(r'\\.', '', destination):
        depth += {'(': 1, ')': -1}.get(char, 0)
        if depth < 0:
            return False
    return depth == 0


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
    return not (item or text.startswith('>') or html(text, True) or opens(text)
                or closing(text))


def ending(text):
    """What ends the HTML block this text starts: the text that closes it, or True where a
    blank line does. A comment runs to `-->` over blank lines, and so do raw-text tags."""
    lowered = text.lower()
    for start, end in (('<!--', '-->'), ('<?', '?>'), ('<![cdata[', ']]>')):
        if lowered.startswith(start):
            return end
    if re.match(r'<![A-Za-z]', text):
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
    """The fence this line opens, as its character and its length, or None where it opens none.
    A backtick fence's info string may hold no backtick: with one, the line is paragraph text."""
    found = FENCE.match(line)
    if not found or found['run'][0] == '`' and '`' in found['info']:
        return None
    return found['run'][0], len(found['run'])


def closes(line, fence):
    """Whether this line ends the open fence: the same character, at least as long, and nothing
    after it — an info string is allowed where a fence opens and nowhere else."""
    found = FENCE.match(line)
    return bool(found and found['run'][0] == fence[0] and len(found['run']) >= fence[1]
                and not found['info'].strip(' '))
