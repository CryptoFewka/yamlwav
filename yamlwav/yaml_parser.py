"""Full YAML 1.2 parser — pure Python stdlib, no external dependencies.

Public API:
    parse(text: str) -> object
        Parse a YAML 1.2 stream. Returns the value of the first document.
        Raises YAMLError on invalid YAML.

Architecture:
    Scanner  — converts raw text into a token stream
    Parser   — converts tokens into Python native values (recursive descent)
    Resolver — applies YAML 1.2 Core Schema type coercion to plain scalars
"""
import re
import math

# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class YAMLError(Exception):
    pass


# ---------------------------------------------------------------------------
# Token types
# ---------------------------------------------------------------------------

(
    TOK_STREAM_START,
    TOK_STREAM_END,
    TOK_DOCUMENT_START,    # ---
    TOK_DOCUMENT_END,      # ...
    TOK_BLOCK_SEQ_ENTRY,   # - (at block level)
    TOK_KEY,               # ? or implicit key
    TOK_VALUE,             # :
    TOK_SCALAR,            # any scalar value
    TOK_BLOCK_MAP_START,
    TOK_BLOCK_SEQ_START,
    TOK_FLOW_SEQ_START,    # [
    TOK_FLOW_SEQ_END,      # ]
    TOK_FLOW_MAP_START,    # {
    TOK_FLOW_MAP_END,      # }
    TOK_COMMA,             # ,
    TOK_ANCHOR,            # &name
    TOK_ALIAS,             # *name
    TOK_TAG,               # !!tag or !tag
    TOK_DIRECTIVE,         # %YAML or %TAG
    TOK_BLOCK_MAP_END,     # end of block mapping scope
    TOK_BLOCK_SEQ_END,     # end of block sequence scope
) = range(21)


class Token:
    __slots__ = ("type", "value", "style", "line")

    def __init__(self, type_, value=None, style=None, line=0):
        self.type = type_
        self.value = value
        self.style = style   # None=plain ' " | > for scalars
        self.line = line

    def __repr__(self):
        return f"Token({self.type}, {self.value!r}, style={self.style!r})"


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

_ESCAPE_MAP = {
    "0": "\x00", "a": "\x07", "b": "\x08", "t": "\x09", "\t": "\x09",
    "n": "\x0a", "v": "\x0b", "f": "\x0c", "r": "\x0d", "e": "\x1b",
    " ": " ",    "\"": "\"",  "/": "/",    "\\": "\\",  "N": "\x85",
    "_": "\xa0", "L": "\u2028", "P": "\u2029",
}


def _unescape_double_quoted(s: str) -> str:
    """Process escape sequences inside a double-quoted scalar."""
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        i += 1
        if i >= len(s):
            raise YAMLError("Trailing backslash in double-quoted scalar")
        esc = s[i]
        if esc in _ESCAPE_MAP:
            out.append(_ESCAPE_MAP[esc])
            i += 1
        elif esc == "x":
            hex_str = s[i + 1: i + 3]
            if len(hex_str) < 2:
                raise YAMLError("\\x escape too short")
            out.append(chr(int(hex_str, 16)))
            i += 3
        elif esc == "u":
            hex_str = s[i + 1: i + 5]
            if len(hex_str) < 4:
                raise YAMLError("\\u escape too short")
            out.append(chr(int(hex_str, 16)))
            i += 5
        elif esc == "U":
            hex_str = s[i + 1: i + 9]
            if len(hex_str) < 8:
                raise YAMLError("\\U escape too short")
            out.append(chr(int(hex_str, 16)))
            i += 9
        else:
            raise YAMLError(f"Unknown escape sequence: \\{esc}")
    return "".join(out)


def _process_single_quoted(s: str) -> str:
    """Process '' escape (the only escape in single-quoted scalars)."""
    return s.replace("''", "'")


def _fold_block(lines: list, chomping: str) -> str:
    """Apply folded (>) block scalar line-folding rules."""
    if not lines:
        return ""
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == "":
            # Empty line — emit newline
            result.append("\n")
            i += 1
        elif line.startswith(" ") or line.startswith("\t"):
            # More-indented line — keep newline, no folding
            if result and result[-1] not in ("\n",):
                result.append("\n")
            result.append(line + "\n")
            i += 1
        else:
            # Normal line — fold with space unless followed by empty/more-indented
            result.append(line)
            i += 1
            if i < len(lines):
                next_line = lines[i]
                if next_line == "" or next_line.startswith(" ") or next_line.startswith("\t"):
                    result.append("\n")
                else:
                    result.append(" ")
    text = "".join(result)
    return _apply_chomping(text, chomping)


def _literal_block(lines: list, chomping: str) -> str:
    """Join literal (|) block scalar lines."""
    text = "\n".join(lines)
    if lines:
        text += "\n"
    return _apply_chomping(text, chomping)


def _apply_chomping(text: str, chomping: str) -> str:
    if chomping == "-":  # strip
        return text.rstrip("\n")
    elif chomping == "+":  # keep
        return text
    else:  # clip (default)
        return text.rstrip("\n") + "\n" if text.rstrip("\n") else ""


class Scanner:
    """Tokenize a YAML text into a stream of Token objects."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.line = 1
        self._tokens: list[Token] = []
        self._done = False
        self._indent_levels: list[int] = [-1]

    def peek(self, offset=0) -> str:
        i = self.pos + offset
        return self.text[i] if i < len(self.text) else ""

    def advance(self, n=1) -> str:
        chunk = self.text[self.pos: self.pos + n]
        for ch in chunk:
            if ch == "\n":
                self.line += 1
        self.pos += n
        return chunk

    def skip_whitespace_and_comments(self, newlines=False):
        while self.pos < len(self.text):
            ch = self.peek()
            if ch in (" ", "\t"):
                self.advance()
            elif newlines and ch in ("\n", "\r"):
                self.advance()
                if ch == "\r" and self.peek() == "\n":
                    self.advance()
            elif ch == "#":
                while self.pos < len(self.text) and self.peek() not in ("\n", "\r"):
                    self.advance()
            else:
                break

    def skip_to_eol(self):
        while self.pos < len(self.text) and self.peek() not in ("\n", "\r"):
            self.advance()
        if self.pos < len(self.text):
            ch = self.advance()
            if ch == "\r" and self.peek() == "\n":
                self.advance()

    def current_column(self) -> int:
        """Return 0-based column of current position."""
        start = self.text.rfind("\n", 0, self.pos)
        return self.pos - start - 1

    def token_stream(self):
        """Lazy token generator — O(1) memory regardless of document size."""
        yield Token(TOK_STREAM_START, line=self.line)
        yield from self._scan_stream()
        yield Token(TOK_STREAM_END, line=self.line)

    def tokenize(self) -> list:
        """Return all tokens as a list (kept for debugging/tests)."""
        return list(self.token_stream())

    def _scan_stream(self):
        while self.pos < len(self.text):
            self.skip_whitespace_and_comments(newlines=True)
            if self.pos >= len(self.text):
                break
            # Directive
            if self.peek() == "%":
                yield from self._scan_directive()
                continue
            # Document start/end
            if self.text[self.pos:self.pos+3] == "---":
                after = self.text[self.pos+3:self.pos+4]
                if after in ("", " ", "\t", "\n", "\r"):
                    yield Token(TOK_DOCUMENT_START, line=self.line)
                    self.advance(3)
                    # Skip only optional whitespace — inline content (e.g. "--- text") is valid
                    while self.peek() in (" ", "\t"):
                        self.advance()
                    # If a comment or end-of-line, skip the rest; otherwise parse inline content
                    if self.peek() in ("#", "\n", "\r", ""):
                        self.skip_to_eol()
                    yield from self._scan_document()
                    continue
            if self.text[self.pos:self.pos+3] == "...":
                after = self.text[self.pos+3:self.pos+4]
                if after in ("", " ", "\t", "\n", "\r"):
                    yield Token(TOK_DOCUMENT_END, line=self.line)
                    self.advance(3)
                    self.skip_to_eol()
                    continue
            # Implicit document (no ---)
            prev_pos = self.pos
            yield Token(TOK_DOCUMENT_START, line=self.line)
            yield from self._scan_document()
            # Safety: if nothing was consumed, skip one character to prevent infinite loop
            if self.pos == prev_pos:
                self.advance()

    def _scan_directive(self):
        self.advance()  # skip %
        name = self._scan_plain_word()
        rest = ""
        while self.pos < len(self.text) and self.peek() not in ("\n", "\r"):
            rest += self.advance()
        yield Token(TOK_DIRECTIVE, value=(name, rest.strip()), line=self.line)
        self.skip_whitespace_and_comments(newlines=True)

    def _scan_plain_word(self) -> str:
        word = []
        while self.pos < len(self.text) and self.peek() not in (" ", "\t", "\n", "\r", ":", "#"):
            word.append(self.advance())
        return "".join(word)

    def _scan_document(self):
        """Scan one document's worth of tokens."""
        yield from self._scan_node(0, block=True)

    def _scan_node(self, indent, block=True):
        self.skip_whitespace_and_comments(newlines=True)
        if self.pos >= len(self.text):
            return
        ch = self.peek()

        # Check for document end markers — stop scanning
        if self.text[self.pos:self.pos+3] in ("---", "..."):
            after = self.text[self.pos+3:self.pos+4]
            if after in ("", " ", "\t", "\n", "\r"):
                return

        col = self.current_column()
        if block and col < indent:
            return

        anchor = None
        tag = None
        anchor_tok = None  # Token to emit; may be deferred when anchor precedes a block mapping
        tag_tok = None
        # col_start: the column where the anchor/tag begins (used for block mapping
        # indent when anchor and content are on the same line).
        col_start = col

        # Anchor
        if ch == "&":
            anchor_line = self.line
            self.advance()
            name = []
            while self.pos < len(self.text) and self.peek() not in (" ", "\t", "\n", "\r", ",", "[", "]", "{", "}"):
                name.append(self.advance())
            anchor = "".join(name)
            anchor_tok = Token(TOK_ANCHOR, value=anchor, line=self.line)
            # Skip whitespace; if anchor is alone on a line, advance to next line's content
            self.skip_whitespace_and_comments(newlines=True)
            ch = self.peek()
            # If content moved to a new line, update col_start to content column
            if self.line != anchor_line:
                col_start = self.current_column()

        # Tag
        if ch == "!":
            tag_line = self.line
            tag = self._scan_tag()
            tag_tok = Token(TOK_TAG, value=tag, line=self.line)
            self.skip_whitespace_and_comments(newlines=True)
            ch = self.peek()
            # If content moved to a new line, update col_start to content column
            if self.line != tag_line:
                col_start = self.current_column()

        # col_content: column of actual content after consuming anchor/tag.
        # col: block mapping/sequence indent — col_start when same line, col_content when crossed.
        col_content = self.current_column()
        col = col_start

        # If an anchor/tag was consumed and nothing follows on the same line, the value is null.
        # Emit the anchor/tag and a null scalar immediately before any block content is consumed,
        # so that the anchor names an empty (null) value rather than the next sibling entry.
        if (anchor_tok is not None or tag_tok is not None) and ch in ("\n", "\r", "") and col == col_start:
            if anchor_tok: yield anchor_tok
            if tag_tok: yield tag_tok
            yield Token(TOK_SCALAR, value="", style=None, line=self.line)
            return

        # Flow sequence
        if ch == "[":
            if anchor_tok: yield anchor_tok
            if tag_tok: yield tag_tok
            self.advance()
            yield Token(TOK_FLOW_SEQ_START, line=self.line)
            yield from self._scan_flow_sequence()
            return

        # Flow mapping
        if ch == "{":
            if anchor_tok: yield anchor_tok
            if tag_tok: yield tag_tok
            self.advance()
            yield Token(TOK_FLOW_MAP_START, line=self.line)
            yield from self._scan_flow_mapping()
            return

        # Block sequence
        if block and ch == "-":
            next_ch = self.peek(1)
            if next_ch in (" ", "\t", "\n", "\r", ""):
                if anchor_tok: yield anchor_tok
                if tag_tok: yield tag_tok
                yield Token(TOK_BLOCK_SEQ_START, line=self.line)
                yield from self._scan_block_sequence(col)
                return

        # Block mapping — check before alias so that "*alias :" is caught as a mapping key
        if block:
            saved_pos = self.pos
            saved_line = self.line
            is_mapping = self._looks_like_block_mapping()
            self.pos = saved_pos
            self.line = saved_line
            if is_mapping:
                # Determine whether anchor/tag was on the same line as the mapping content.
                # If so, the anchor/tag belongs to the FIRST KEY of the mapping, not to the
                # mapping itself — defer the anchor/tag tokens into the block mapping scan.
                same_line_prefix = (anchor_tok is not None or tag_tok is not None) and (col_content > col_start)
                if same_line_prefix:
                    # Anchor/tag applies to first key; emit BLOCK_MAP_START first, then
                    # let _scan_block_mapping re-emit the deferred tokens before the key.
                    yield Token(TOK_BLOCK_MAP_START, line=self.line)
                    yield from self._scan_block_mapping(
                        col_start,
                        first_entry_in_progress=True,
                        deferred_tokens=[t for t in (anchor_tok, tag_tok) if t is not None],
                    )
                else:
                    if anchor_tok: yield anchor_tok
                    if tag_tok: yield tag_tok
                    yield Token(TOK_BLOCK_MAP_START, line=self.line)
                    yield from self._scan_block_mapping(col_start)
                return

        # Anchor/tag for non-block-mapping paths
        if anchor_tok: yield anchor_tok
        if tag_tok: yield tag_tok

        # Alias (value position — not a key)
        if ch == "*":
            self.advance()
            name = []
            while self.pos < len(self.text) and self.peek() not in (" ", "\t", "\n", "\r", ",", "[", "]", "{", "}"):
                name.append(self.advance())
            yield Token(TOK_ALIAS, value="".join(name), line=self.line)
            return

        # Scalar
        yield from self._scan_scalar(indent, block=block, tag=tag)

    def _scan_tag(self) -> str:
        self.advance()  # skip first !
        if self.peek() == "!":
            self.advance()  # !!
            name = []
            while self.pos < len(self.text) and self.peek() not in (" ", "\t", "\n", "\r", ",", "[", "]", "{", "}"):
                name.append(self.advance())
            return "!!" + "".join(name)
        elif self.peek() == "<":
            # Verbatim tag !<...>
            self.advance()
            name = []
            while self.pos < len(self.text) and self.peek() != ">":
                name.append(self.advance())
            if self.peek() == ">":
                self.advance()
            return "!<" + "".join(name) + ">"
        else:
            # Local tag !foo
            name = []
            while self.pos < len(self.text) and self.peek() not in (" ", "\t", "\n", "\r", ",", "[", "]", "{", "}"):
                name.append(self.advance())
            return "!" + "".join(name)

    def _looks_like_block_mapping(self) -> bool:
        """Quick peek: does the current position start a block mapping entry?"""
        self.skip_whitespace_and_comments(newlines=False)
        if self.pos >= len(self.text):
            return False
        ch = self.peek()
        # Explicit key: ? must be followed by space/tab/newline to be a key indicator
        if ch == "?":
            after = self.peek(1)
            if after in (" ", "\t", "\n", "\r", ""):
                return True
        # Anchors and tags before the key — skip them
        if ch in ("&", "!"):
            while self.pos < len(self.text) and self.peek() not in (" ", "\t", "\n", "\r"):
                self.advance()
            self.skip_whitespace_and_comments(newlines=False)
            ch = self.peek()
        # Alias as key: *alias must be followed by space then :
        if ch == "*":
            while self.pos < len(self.text) and self.peek() not in (" ", "\t", "\n", "\r", ",", "[", "]", "{", "}"):
                self.advance()
            self.skip_whitespace_and_comments(newlines=False)
            if self.peek() != ":":
                return False
            after = self.peek(1)
            return after in (" ", "\t", "\n", "\r", "")
        # Quoted scalar key - find closing quote, look for :
        if ch in ('"', "'"):
            q = self.advance()
            while self.pos < len(self.text):
                c = self.advance()
                if c == q:
                    if q == "'" and self.peek() == "'":
                        self.advance()
                        continue
                    break
            self.skip_whitespace_and_comments(newlines=False)
            return self.peek() == ":"
        # Plain scalar key: scan until we find ": " (colon+space = key-value separator).
        # The key may itself contain colons not followed by spaces, and # not preceded by space.
        while self.pos < len(self.text) and self.peek() not in ("\n", "\r"):
            ch = self.peek()
            if ch == "#" and self.pos > 0 and self.text[self.pos - 1] in (" ", "\t"):
                break  # comment
            if ch == ":":
                after = self.peek(1)
                if after in (" ", "\t", "\n", "\r", ""):
                    return True
            self.advance()
        return False

    def _scan_block_sequence(self, seq_indent):
        """Scan a block sequence starting at seq_indent."""
        while self.pos < len(self.text):
            self.skip_whitespace_and_comments(newlines=True)
            if self.pos >= len(self.text):
                break
            if self.text[self.pos:self.pos+3] in ("---", "..."):
                after = self.text[self.pos+3:self.pos+4]
                if after in ("", " ", "\t", "\n", "\r"):
                    break
            col = self.current_column()
            if col < seq_indent:
                break
            if col > seq_indent:
                break
            if self.peek() != "-":
                break
            next_ch = self.peek(1)
            if next_ch not in (" ", "\t", "\n", "\r", ""):
                break
            yield Token(TOK_BLOCK_SEQ_ENTRY, line=self.line)
            self.advance()  # skip -
            # Inline value on same line?
            if self.peek() in (" ", "\t"):
                self.skip_whitespace_and_comments(newlines=False)
                if self.peek() not in ("\n", "\r", ""):
                    yield from self._scan_node(seq_indent + 1, block=True)
                else:
                    self.skip_whitespace_and_comments(newlines=True)
                    yield from self._scan_node(seq_indent + 1, block=True)
            else:
                # - immediately followed by newline
                self.skip_whitespace_and_comments(newlines=True)
                yield from self._scan_node(seq_indent + 1, block=True)
        yield Token(TOK_BLOCK_SEQ_END, line=self.line)

    def _scan_block_mapping(self, map_indent, first_entry_in_progress=False, deferred_tokens=None):
        """Scan a block mapping starting at map_indent.

        first_entry_in_progress: caller (e.g. _scan_node after consuming an anchor/tag
        on the same line) has already advanced past the entry indicator; skip the col
        check for the very first entry only.
        deferred_tokens: anchor/tag tokens that were consumed before BLOCK_MAP_START and
        must be emitted before the first key scalar.
        """
        first = True
        while self.pos < len(self.text):
            if first and first_entry_in_progress:
                # Position is already past an anchor/tag on this line; don't skip
                # whitespace across lines or check column for this first entry.
                first = False
            else:
                first = False
                self.skip_whitespace_and_comments(newlines=True)
                if self.pos >= len(self.text):
                    break
                if self.text[self.pos:self.pos+3] in ("---", "..."):
                    after = self.text[self.pos+3:self.pos+4]
                    if after in ("", " ", "\t", "\n", "\r"):
                        break
                col = self.current_column()
                if col < map_indent:
                    break
                if col > map_indent:
                    break

            # Explicit key with ? — only when ? is followed by space/tab/newline
            if self.peek() == "?" and self.peek(1) in (" ", "\t", "\n", "\r", ""):
                self.advance()
                self.skip_whitespace_and_comments(newlines=False)
                yield Token(TOK_KEY, line=self.line)
                yield from self._scan_node(map_indent + 1, block=True)
                self.skip_whitespace_and_comments(newlines=True)
                if self.peek() == ":" and self.current_column() == map_indent:
                    self.advance()
                    self.skip_whitespace_and_comments(newlines=False)
                    yield Token(TOK_VALUE, line=self.line)
                    yield from self._scan_node(map_indent + 1, block=True)
                continue

            # Implicit key: scan key scalar then expect :
            yield Token(TOK_KEY, line=self.line)
            # Emit any deferred anchor/tag tokens before the key scalar
            if deferred_tokens:
                yield from deferred_tokens
                deferred_tokens = None
            yield from self._scan_implicit_key(map_indent)
            self.skip_whitespace_and_comments(newlines=False)
            if self.peek() == ":":
                self.advance()
                yield Token(TOK_VALUE, line=self.line)
                # Inline value on same line?
                self.skip_whitespace_and_comments(newlines=False)
                if self.peek() in ("\n", "\r", ""):
                    # Value is on next lines
                    self.skip_whitespace_and_comments(newlines=True)
                    next_col = self.current_column()
                    if next_col > map_indent:
                        yield from self._scan_node(next_col, block=True)
                    elif next_col == map_indent and self.peek() == "-" and self.peek(1) in (" ", "\t", "\n", "\r", ""):
                        # Block sequence at same indent level as the mapping keys — valid per YAML spec
                        yield from self._scan_node(next_col, block=True)
                    else:
                        # Empty value
                        yield Token(TOK_SCALAR, value="", style=None, line=self.line)
                else:
                    yield from self._scan_node(map_indent + 1, block=True)
            else:
                # No value — emit empty scalar
                yield Token(TOK_VALUE, line=self.line)
                yield Token(TOK_SCALAR, value="", style=None, line=self.line)
        yield Token(TOK_BLOCK_MAP_END, line=self.line)

    def _scan_implicit_key(self, indent):
        """Scan the key part of an implicit key: value pair."""
        ch = self.peek()
        # Anchor before key
        if ch == "&":
            self.advance()
            name = []
            while self.pos < len(self.text) and self.peek() not in (" ", "\t", "\n", "\r", ":"):
                name.append(self.advance())
            yield Token(TOK_ANCHOR, value="".join(name), line=self.line)
            self.skip_whitespace_and_comments(newlines=False)
            ch = self.peek()
        # Tag before key
        if ch == "!":
            tag = self._scan_tag()
            yield Token(TOK_TAG, value=tag, line=self.line)
            self.skip_whitespace_and_comments(newlines=False)
            ch = self.peek()
        # Alias as key (*name)
        if ch == "*":
            self.advance()
            name = []
            while self.pos < len(self.text) and self.peek() not in (" ", "\t", "\n", "\r", ",", "[", "]", "{", "}"):
                name.append(self.advance())
            yield Token(TOK_ALIAS, value="".join(name), line=self.line)
            return
        # Use block=True so that [ ] { } are allowed in block-context keys
        yield from self._scan_scalar(indent, block=True, tag=None, in_key=True)

    def _scan_scalar(self, indent, block=True, tag=None, in_key=False):
        ch = self.peek()
        line = self.line

        # Double-quoted
        if ch == '"':
            value = self._scan_double_quoted()
            yield Token(TOK_SCALAR, value=value, style='"', line=line)
            return

        # Single-quoted
        if ch == "'":
            value = self._scan_single_quoted()
            yield Token(TOK_SCALAR, value=value, style="'", line=line)
            return

        # Block scalars (only in block context, not in key)
        if block and not in_key and ch in ("|", ">"):
            value = self._scan_block_scalar(ch, indent)
            yield Token(TOK_SCALAR, value=value, style=ch, line=line)
            return

        # Plain scalar
        value = self._scan_plain(indent, block=block, in_key=in_key)
        yield Token(TOK_SCALAR, value=value, style=None, line=line)

    def _scan_double_quoted(self) -> str:
        self.advance()  # opening "
        parts = []
        while self.pos < len(self.text):
            ch = self.peek()
            if ch == '"':
                self.advance()
                break
            if ch in ("\n", "\r"):
                # Line folding inside double-quoted scalar
                self.advance()
                if ch == "\r" and self.peek() == "\n":
                    self.advance()
                # Skip leading whitespace on next line (unless backslash-newline)
                while self.peek() in (" ", "\t"):
                    self.advance()
                if parts and parts[-1] != " " and not (parts[-1] == "\\" and False):
                    parts.append(" ")
                continue
            if ch == "\\":
                # Read the escape, handle backslash-newline (line continuation)
                self.advance()
                esc = self.peek()
                if esc in ("\n", "\r"):
                    # Backslash-newline = line continuation (no space)
                    self.advance()
                    if esc == "\r" and self.peek() == "\n":
                        self.advance()
                    while self.peek() in (" ", "\t"):
                        self.advance()
                    continue
                parts.append("\\" + esc)
                self.advance()
                continue
            parts.append(ch)
            self.advance()
        return _unescape_double_quoted("".join(parts))

    def _scan_single_quoted(self) -> str:
        self.advance()  # opening '
        parts = []
        while self.pos < len(self.text):
            ch = self.peek()
            if ch == "'":
                self.advance()
                if self.peek() == "'":
                    parts.append("'")
                    self.advance()
                    continue
                break
            if ch in ("\n", "\r"):
                self.advance()
                if ch == "\r" and self.peek() == "\n":
                    self.advance()
                while self.peek() in (" ", "\t"):
                    self.advance()
                if parts and parts[-1] != " ":
                    parts.append(" ")
                continue
            parts.append(ch)
            self.advance()
        return "".join(parts)

    def _scan_block_scalar(self, style: str, indent: int) -> str:
        self.advance()  # skip | or >
        # Read optional indentation indicator and chomping indicator
        chomping = ""  # default = clip
        explicit_indent = 0
        while self.peek() in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "-", "+"):
            ch = self.peek()
            if ch in ("-", "+"):
                chomping = ch
                self.advance()
            elif ch.isdigit():
                explicit_indent = int(ch)
                self.advance()
        # Skip comment and rest of line
        self.skip_to_eol()

        # Determine indentation from first non-empty line
        lines = []
        block_indent = -1

        while self.pos < len(self.text):
            # Peek at line
            line_start = self.pos
            # Count leading spaces
            spaces = 0
            while self.pos < len(self.text) and self.peek() == " ":
                self.advance()
                spaces += 1

            # Check for end of block scalar
            ch = self.peek()
            if ch in ("\n", "\r") or self.pos >= len(self.text):
                # Empty line — keep as ""
                lines.append("")
                if ch == "\r":
                    self.advance()
                    if self.peek() == "\n":
                        self.advance()
                elif ch == "\n":
                    self.advance()
                continue

            # Document marker check
            rest = self.text[self.pos:self.pos+3]
            if rest in ("---", "..."):
                after = self.text[self.pos+3:self.pos+4]
                if after in ("", " ", "\t", "\n", "\r"):
                    # Rewind to line start
                    self.pos = line_start
                    self.line -= 0  # line tracking already advanced
                    break

            if block_indent == -1:
                if explicit_indent > 0:
                    block_indent = indent + explicit_indent
                else:
                    block_indent = spaces

            if spaces < block_indent:
                # Line is less indented — end of block scalar
                self.pos = line_start
                break

            # Read rest of line (remove block_indent leading spaces)
            content = []
            # We've already consumed 'spaces' spaces; need block_indent of them
            # Re-position to block_indent
            self.pos = line_start
            for _ in range(block_indent):
                if self.peek() == " ":
                    self.advance()

            while self.pos < len(self.text) and self.peek() not in ("\n", "\r"):
                content.append(self.advance())
            lines.append("".join(content))

            if self.pos < len(self.text):
                ch = self.advance()  # newline
                if ch == "\r" and self.peek() == "\n":
                    self.advance()

        # Strip trailing empty lines for clip/strip, keep for keep
        if chomping != "+":
            while lines and lines[-1] == "":
                lines.pop()

        if style == "|":
            return _literal_block(lines, chomping)
        else:
            return _fold_block(lines, chomping)

    def _scan_plain(self, indent, block=True, in_key=False) -> str:
        """Scan a plain (unquoted) scalar."""
        lines = []
        current = []

        while self.pos < len(self.text):
            ch = self.peek()

            # Document markers
            if self.text[self.pos:self.pos+3] in ("---", "..."):
                after = self.text[self.pos+3:self.pos+4]
                if after in ("", " ", "\t", "\n", "\r"):
                    break

            # End-of-line
            if ch in ("\n", "\r"):
                if in_key:
                    break
                # Fold lines
                line_val = "".join(current).rstrip(" \t")
                if line_val:
                    lines.append(line_val)
                elif lines:
                    lines.append("")
                current = []
                self.advance()
                if ch == "\r" and self.peek() == "\n":
                    self.advance()
                # Skip leading whitespace on next line
                col_before = self.current_column()
                while self.peek() in (" ", "\t"):
                    self.advance()
                col_after = self.current_column()
                # Check if next line is still in the scalar
                next_ch = self.peek()
                if next_ch == "":
                    break  # EOF — end of scalar, no trailing newline
                if next_ch in ("\n", "\r"):
                    lines.append("")
                    continue
                if next_ch == "#":
                    # Comment — end of scalar
                    break
                next_col = self.current_column()
                if block and next_col < indent:
                    # Dedent — end of scalar
                    break
                if self.text[self.pos:self.pos+3] in ("---", "..."):
                    after = self.text[self.pos+3:self.pos+4]
                    if after in ("", " ", "\t", "\n", "\r"):
                        break
                continue

            # Flow indicators only terminate plain scalars in flow context
            if not block and ch in (",", "[", "]", "{", "}"):
                break

            # : followed by safe char terminates a plain scalar in all contexts.
            # In flow context, flow indicators also act as safe chars after :.
            if ch == ":":
                next_ch = self.peek(1)
                if next_ch in (" ", "\t", "\n", "\r", ""):
                    break
                if not block and next_ch in (",", "[", "]", "{", "}"):
                    break

            # # preceded by space is a comment
            if ch == "#":
                prev = self.text[self.pos - 1] if self.pos > 0 else ""
                if prev in (" ", "\t"):
                    break

            current.append(ch)
            self.advance()

        val = "".join(current).rstrip(" \t")
        if val:
            lines.append(val)

        # Fold lines: empty lines become \n, others join with space
        if not lines:
            return ""
        if len(lines) == 1:
            return lines[0]

        result = []
        for i, line in enumerate(lines):
            if line == "":
                result.append("\n")
            else:
                result.append(line)
                if i < len(lines) - 1 and lines[i + 1] != "":
                    result.append(" ")
        return "".join(result)

    def _looks_like_flow_map_entry(self) -> bool:
        """Check if current position starts an implicit 'key: value' inside a flow sequence."""
        saved_pos = self.pos
        saved_line = self.line
        # Skip anchor/tag if present
        if self.peek() == "&":
            while self.pos < len(self.text) and self.peek() not in (" ", "\t", "\n", "\r", ",", "[", "]", "{", "}"):
                self.advance()
            while self.pos < len(self.text) and self.peek() in (" ", "\t"):
                self.advance()
        if self.peek() == "!":
            while self.pos < len(self.text) and self.peek() not in (" ", "\t", "\n", "\r", ",", "[", "]", "{", "}"):
                self.advance()
            while self.pos < len(self.text) and self.peek() in (" ", "\t"):
                self.advance()
        # Skip quoted scalar
        if self.peek() in ('"', "'"):
            q = self.advance()
            while self.pos < len(self.text):
                c = self.advance()
                if c == q:
                    break
        else:
            # Skip plain scalar until potential ': '
            while self.pos < len(self.text) and self.peek() not in ("\n", "\r", ":", ",", "[", "]", "{", "}"):
                self.advance()
        # Skip whitespace
        while self.pos < len(self.text) and self.peek() in (" ", "\t"):
            self.advance()
        result = self.peek() == ":" and self.peek(1) in (" ", "\t", "\n", "\r", "", ",", "[", "]", "{", "}")
        self.pos = saved_pos
        self.line = saved_line
        return result

    def _scan_flow_sequence(self):
        """Scan inside [...] flow sequence (opening [ already consumed)."""
        while self.pos < len(self.text):
            self.skip_whitespace_and_comments(newlines=True)
            if self.peek() == "]":
                self.advance()
                yield Token(TOK_FLOW_SEQ_END, line=self.line)
                return
            if self.peek() == ",":
                self.advance()
                continue
            if self.pos >= len(self.text):
                break
            # Detect implicit single-pair flow mapping: key: value inside a sequence
            # e.g. [foo: bar, baz: qux] is equivalent to [{foo: bar}, {baz: qux}]
            if self._looks_like_flow_map_entry():
                yield Token(TOK_FLOW_MAP_START, line=self.line)
                yield Token(TOK_KEY, line=self.line)
                yield from self._scan_node(0, block=False)  # key
                self.skip_whitespace_and_comments(newlines=True)
                if self.peek() == ":":
                    self.advance()
                    yield Token(TOK_VALUE, line=self.line)
                    self.skip_whitespace_and_comments(newlines=True)
                    if self.peek() not in (",", "]", "}"):
                        yield from self._scan_node(0, block=False)  # value
                    else:
                        yield Token(TOK_SCALAR, value="", style=None, line=self.line)
                else:
                    yield Token(TOK_VALUE, line=self.line)
                    yield Token(TOK_SCALAR, value="", style=None, line=self.line)
                yield Token(TOK_FLOW_MAP_END, line=self.line)
            else:
                yield from self._scan_node(0, block=False)
        yield Token(TOK_FLOW_SEQ_END, line=self.line)

    def _scan_flow_mapping(self):
        """Scan inside {...} flow mapping (opening { already consumed)."""
        while self.pos < len(self.text):
            self.skip_whitespace_and_comments(newlines=True)
            if self.peek() == "}":
                self.advance()
                yield Token(TOK_FLOW_MAP_END, line=self.line)
                return
            if self.peek() == ",":
                self.advance()
                continue
            if self.pos >= len(self.text):
                break
            # Check for empty value (trailing comma case)
            if self.peek() == "}":
                continue
            # Key
            yield Token(TOK_KEY, line=self.line)
            if self.peek() == "?":
                self.advance()
                self.skip_whitespace_and_comments(newlines=True)
            yield from self._scan_node(0, block=False)
            self.skip_whitespace_and_comments(newlines=True)
            if self.peek() == ":":
                self.advance()
                yield Token(TOK_VALUE, line=self.line)
                self.skip_whitespace_and_comments(newlines=True)
                if self.peek() not in (",", "}"):
                    yield from self._scan_node(0, block=False)
                else:
                    yield Token(TOK_SCALAR, value="", style=None, line=self.line)
            else:
                # Key only (no value)
                yield Token(TOK_VALUE, line=self.line)
                yield Token(TOK_SCALAR, value="", style=None, line=self.line)
        yield Token(TOK_FLOW_MAP_END, line=self.line)


# ---------------------------------------------------------------------------
# Resolver — YAML 1.2 Core Schema type coercion
# ---------------------------------------------------------------------------

_RE_NULL = re.compile(r"^(~|null|Null|NULL)$")
_RE_BOOL_TRUE = re.compile(r"^(true|True|TRUE)$")
_RE_BOOL_FALSE = re.compile(r"^(false|False|FALSE)$")
_RE_INT_DEC = re.compile(r"^[-+]?[0-9]+$")
_RE_INT_HEX = re.compile(r"^0x[0-9a-fA-F]+$")
_RE_INT_OCT = re.compile(r"^0o[0-7]+$")
_RE_FLOAT = re.compile(
    r"^[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?$"
)
_RE_FLOAT_INF = re.compile(r"^[-+]?(\.inf|\.Inf|\.INF)$")
_RE_FLOAT_NAN = re.compile(r"^(\.nan|\.NaN|\.NAN)$")


def _resolve(value: str, style) -> object:
    """Apply YAML 1.2 Core Schema resolution to a plain scalar string."""
    if style is not None:
        # Quoted scalars are always strings — no type guessing
        return value
    if _RE_NULL.match(value) or value == "":
        return None
    if _RE_BOOL_TRUE.match(value):
        return True
    if _RE_BOOL_FALSE.match(value):
        return False
    if _RE_INT_DEC.match(value):
        return int(value, 10)
    if _RE_INT_HEX.match(value):
        return int(value, 16)
    if _RE_INT_OCT.match(value):
        return int(value, 8)
    if _RE_FLOAT.match(value):
        return float(value)
    if _RE_FLOAT_INF.match(value):
        return math.copysign(math.inf, -1.0 if value.startswith("-") else 1.0)
    if _RE_FLOAT_NAN.match(value):
        return math.nan
    return value


def _resolve_tagged(tag: str, value: str, style) -> object:
    """Apply explicit tag coercion."""
    if tag in ("!!str", "!str"):
        return str(value) if value is not None else ""
    if tag in ("!!int", "!int"):
        v = value.strip()
        if _RE_INT_HEX.match(v):
            return int(v, 16)
        if _RE_INT_OCT.match(v):
            return int(v, 8)
        return int(v, 10)
    if tag in ("!!float", "!float"):
        return float(value)
    if tag in ("!!bool", "!bool"):
        return _RE_BOOL_TRUE.match(value.strip()) is not None
    if tag in ("!!null", "!null"):
        return None
    if tag in ("!!seq", "!seq"):
        return value if isinstance(value, list) else []
    if tag in ("!!map", "!map"):
        return value if isinstance(value, dict) else {}
    # Unknown tags: return value as-is
    return value


# ---------------------------------------------------------------------------
# Parser — builds Python values from a token stream
# ---------------------------------------------------------------------------

class Parser:
    """Convert a token stream into Python native values."""

    def __init__(self, tokens):
        """Accept either a list or a lazy iterator of Token objects."""
        self._iter = iter(tokens)
        self._buf: Token = None  # one-token lookahead
        self._advance_buf()
        self._anchors: dict = {}

    def _advance_buf(self):
        try:
            self._buf = next(self._iter)
        except StopIteration:
            self._buf = Token(TOK_STREAM_END)

    def peek(self) -> Token:
        return self._buf

    def consume(self) -> Token:
        tok = self._buf
        self._advance_buf()
        return tok

    def expect(self, type_) -> Token:
        tok = self.consume()
        if tok.type != type_:
            raise YAMLError(
                f"Expected token {type_} but got {tok.type} ({tok.value!r}) at line {tok.line}"
            )
        return tok

    def parse(self) -> object:
        """Parse the full stream and return the first document's value."""
        self.expect(TOK_STREAM_START)
        result = None
        while self.peek().type not in (TOK_STREAM_END,):
            tok = self.peek()
            if tok.type == TOK_DOCUMENT_START:
                self.consume()
                if self.peek().type not in (TOK_DOCUMENT_END, TOK_DOCUMENT_START, TOK_STREAM_END):
                    result = self.parse_node()
                # Stop after first document
                break
            elif tok.type == TOK_DIRECTIVE:
                self.consume()
            elif tok.type == TOK_DOCUMENT_END:
                self.consume()
                break
            else:
                # Implicit document
                result = self.parse_node()
                break
        return result

    def parse_node(self) -> object:
        tok = self.peek()

        anchor = None
        tag = None

        if tok.type == TOK_ANCHOR:
            self.consume()
            anchor = tok.value
            tok = self.peek()

        if tok.type == TOK_ALIAS:
            self.consume()
            if tok.value not in self._anchors:
                raise YAMLError(f"Unknown alias: *{tok.value}")
            return self._anchors[tok.value]

        if tok.type == TOK_TAG:
            self.consume()
            tag = tok.value
            tok = self.peek()

        # After tag, re-check for anchor
        if tok.type == TOK_ANCHOR:
            self.consume()
            anchor = tok.value
            tok = self.peek()

        if tok.type == TOK_SCALAR:
            self.consume()
            if tag:
                value = _resolve_tagged(tag, tok.value, tok.style)
            else:
                value = _resolve(tok.value, tok.style)
        elif tok.type == TOK_BLOCK_SEQ_START:
            self.consume()
            value = self.parse_block_sequence()
        elif tok.type == TOK_BLOCK_MAP_START:
            self.consume()
            value = self.parse_block_mapping()
        elif tok.type == TOK_FLOW_SEQ_START:
            self.consume()
            value = self.parse_flow_sequence()
        elif tok.type == TOK_FLOW_MAP_START:
            self.consume()
            value = self.parse_flow_mapping()
        elif tok.type in (TOK_DOCUMENT_END, TOK_DOCUMENT_START, TOK_STREAM_END,
                          TOK_BLOCK_MAP_END, TOK_BLOCK_SEQ_END):
            value = None
        else:
            value = None

        if tag and not isinstance(value, (list, dict)):
            # Re-apply tag coercion if value was already resolved
            if tok.type == TOK_SCALAR:
                value = _resolve_tagged(tag, tok.value, tok.style)

        if anchor is not None:
            self._anchors[anchor] = value

        return value

    def parse_block_sequence(self) -> list:
        result = []
        while self.peek().type == TOK_BLOCK_SEQ_ENTRY:
            self.consume()
            tok = self.peek()
            if tok.type in (TOK_BLOCK_SEQ_ENTRY, TOK_BLOCK_SEQ_END,
                             TOK_DOCUMENT_START, TOK_DOCUMENT_END, TOK_STREAM_END):
                result.append(None)
            else:
                result.append(self.parse_node())
        if self.peek().type == TOK_BLOCK_SEQ_END:
            self.consume()
        return result

    def parse_block_mapping(self) -> dict:
        result = {}
        while self.peek().type == TOK_KEY:
            self.consume()
            key_node = self.parse_node()
            key = key_node if key_node is not None else None
            if not isinstance(key, str):
                key = str(key) if key is not None else ""
            if self.peek().type == TOK_VALUE:
                self.consume()
                tok = self.peek()
                if tok.type in (TOK_KEY, TOK_BLOCK_MAP_END, TOK_DOCUMENT_START,
                                 TOK_DOCUMENT_END, TOK_STREAM_END):
                    value = None
                else:
                    value = self.parse_node()
            else:
                value = None
            result[key] = value
        if self.peek().type == TOK_BLOCK_MAP_END:
            self.consume()
        return result

    def parse_flow_sequence(self) -> list:
        result = []
        while self.peek().type != TOK_FLOW_SEQ_END:
            if self.peek().type == TOK_STREAM_END:
                break
            result.append(self.parse_node())
        if self.peek().type == TOK_FLOW_SEQ_END:
            self.consume()
        return result

    def parse_flow_mapping(self) -> dict:
        result = {}
        while self.peek().type != TOK_FLOW_MAP_END:
            if self.peek().type == TOK_STREAM_END:
                break
            if self.peek().type == TOK_KEY:
                self.consume()
                key_node = self.parse_node()
                key = str(key_node) if key_node is not None else ""
                if self.peek().type == TOK_VALUE:
                    self.consume()
                    if self.peek().type in (TOK_FLOW_MAP_END, TOK_FLOW_SEQ_END):
                        value = None
                    else:
                        value = self.parse_node()
                else:
                    value = None
                result[key] = value
            else:
                # Unexpected — skip
                self.consume()
        if self.peek().type == TOK_FLOW_MAP_END:
            self.consume()
        return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(text: str) -> object:
    """Parse a YAML 1.2 document from *text*.

    Returns the Python value of the first document in the stream.
    Raises YAMLError on parse failure.
    """
    scanner = Scanner(text)
    parser = Parser(scanner.token_stream())
    return parser.parse()
