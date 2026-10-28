"""Strict, transactional exact SEARCH/REPLACE planning; never executes source."""
from dataclasses import dataclass
import difflib
from pathlib import Path, PurePosixPath
import re


class EditError(ValueError):
    def __init__(self, code, detail):
        self.code = code
        super().__init__(code + ': ' + detail)


@dataclass(frozen=True)
class Edit:
    path: str
    search: str
    replacement: str


def parse_edits(text, allowed_paths):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 131072:
        raise EditError('invalid_edit_format', 'Missing or oversized output')
    text = text.replace('\r\n', '\n').lstrip('\ufeff\n')
    fence = re.fullmatch(r'```(?:text|python)?[ \t]*\n(.*?)\n```[ \t\n]*', text, re.S)
    if fence:
        text = fence[1] + '\n'
    lines = text.splitlines(keepends=True)
    edits = []; i = 0
    def marker(line):return line.rstrip('\r\n')
    while i < len(lines):
        if not lines[i].strip():i += 1;continue
        path = marker(lines[i]).strip();i += 1
        posix = PurePosixPath(path)
        if (path not in set(allowed_paths) or posix.is_absolute() or '..' in posix.parts
                or '\\' in path or ':' in path or not path.endswith('.py')):
            raise EditError('disallowed_file', path)
        if i >= len(lines) or marker(lines[i]) != '<<<<<<< SEARCH':
            raise EditError('invalid_edit_format', 'Expected SEARCH marker after file path')
        i += 1; start = i
        while i < len(lines) and marker(lines[i]) != '=======':
            if marker(lines[i]) in {'<<<<<<< SEARCH', '>>>>>>> REPLACE'}:
                raise EditError('invalid_edit_format', 'Nested/missing separator')
            i += 1
        if i == len(lines):raise EditError('invalid_edit_format', 'Missing separator')
        search = ''.join(lines[start:i]);i += 1;start = i
        while i < len(lines) and marker(lines[i]) != '>>>>>>> REPLACE':
            if marker(lines[i]) in {'<<<<<<< SEARCH', '======='}:
                raise EditError('invalid_edit_format', 'Nested/missing replacement terminator')
            i += 1
        if i == len(lines):raise EditError('invalid_edit_format', 'Missing REPLACE terminator')
        replacement = ''.join(lines[start:i]);i += 1
        if not search.strip():raise EditError('empty_search', 'A nonblank exact search is required')
        edits.append(Edit(path, search, replacement))
        if len(edits) > 32:raise EditError('invalid_edit_format', 'Too many edit blocks')
    if not edits:raise EditError('invalid_edit_format', 'No edit blocks')
    return edits


def matching_starts(text, search):
    positions = []; start = 0
    while True:
        position = text.find(search, start)
        if position < 0:break
        end = position + len(search)
        if (position == 0 or text[position-1] == '\n') and (search.endswith('\n') or end == len(text)):
            positions.append(position)
        start = position + 1
    return positions


def plan_edits(root, edits):
    root = Path(root).resolve()
    originals = {}; working = {}; matches = []
    for index, edit in enumerate(edits):
        path = root.joinpath(*PurePosixPath(edit.path).parts)
        if not path.resolve().is_relative_to(root) or path.is_symlink() or not path.is_file():
            raise EditError('disallowed_file', edit.path)
        if edit.path not in working:
            originals[edit.path] = path.read_bytes()
            try:working[edit.path] = originals[edit.path].decode('utf-8')
            except UnicodeDecodeError:raise EditError('unsupported_encoding', edit.path)
        text = working[edit.path]; positions = matching_starts(text, edit.search); count = len(positions)
        if count == 0:raise EditError('search_not_found', edit.path + ': exact code not found')
        if count != 1:raise EditError('search_ambiguous', edit.path + ': search matches ' + str(count) + ' locations')
        position = positions[0]
        working[edit.path] = text[:position] + edit.replacement + text[position+len(edit.search):]
        matches.append({'block': index, 'path': edit.path, 'matches': count})
    replacements = {path: text.encode('utf-8') for path, text in working.items()}
    if all(originals[path] == new for path, new in replacements.items()):
        raise EditError('no_effect', 'Edits make no source changes')
    return originals, replacements, matches


def render_diff(root, text, allowed_paths):
    edits = parse_edits(text, allowed_paths)
    originals, replacements, matches = plan_edits(root, edits)
    diff = []
    for path in sorted(originals):
        old = originals[path].decode('utf-8'); new = replacements[path].decode('utf-8')
        for line in difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        fromfile='a/'+path, tofile='b/'+path, n=3):
            if line.endswith('\n'):diff.append(line)
            else:diff.append(line+'\n\\ No newline at end of file\n')
    # This representation is generated by the tool from exact edits, not predicted
    # line numbers, fuzzy matching, target-answer lookup, or repair of model diffs.
    return ''.join(diff), matches


def reference_block(path, buggy, clean):
    """Build one exact reference edit per changed file for mechanical QA only."""
    old = buggy.splitlines(keepends=True); new = clean.splitlines(keepends=True)
    changed = [x for x in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes() if x[0] != 'equal']
    if not changed:return ''
    first, last = changed[0], changed[-1]
    for context in [3, 6, 12, 24, 48, max(len(old),len(new))]:
        left = min(context, first[1], first[3]);right = min(context, len(old)-last[2], len(new)-last[4])
        search = ''.join(old[first[1]-left:last[2]+right]);replacement = ''.join(new[first[3]-left:last[4]+right])
        if search and len(matching_starts(buggy, search)) == 1:
            if not search.endswith('\n') or replacement and not replacement.endswith('\n'):
                raise EditError('reference_unrepresentable', 'Reference span lacks a final newline')
            markers={'<<<<<<< SEARCH','=======','>>>>>>> REPLACE'}
            if any(line in markers for line in (search+replacement).splitlines()):
                raise EditError('reference_unrepresentable', 'Source contains protocol marker')
            return path+'\n<<<<<<< SEARCH\n'+search+'=======\n'+replacement+'>>>>>>> REPLACE\n'
    raise EditError('reference_unrepresentable', 'No unique reference anchor')
