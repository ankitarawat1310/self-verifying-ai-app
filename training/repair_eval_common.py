"""Pure helpers for the frozen development repair comparison; no code execution."""
import hashlib
import re
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from pathlib import PurePosixPath

MODEL_ID = 'Qwen/Qwen2.5-Coder-1.5B-Instruct'
MODEL_REVISION = '2e1fd397ee46e1388853d2af2c993145b0f1098a'
SOURCE_REVISION = '77cab9055d42ab4a5c25c89a8f937096db13558e'
SELECTION_SEED = 'svaga-repair-dev20-v1'


def sha(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def select_tasks(rows, count=20):
    if not 0 < count <= len(rows):
        raise ValueError('Invalid selection size')
    if len({row['instance_id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate development IDs')
    groups = defaultdict(list)
    for row in rows:
        groups[row['repo']].append(row)
    queues = {repo: deque(sorted(items, key=lambda r: sha(SELECTION_SEED + r['instance_id'])))
              for repo, items in groups.items()}
    order = sorted(queues, key=lambda repo: sha(SELECTION_SEED + repo))
    selected = []
    while len(selected) < count:
        for repo in order:
            if queues[repo]:
                selected.append(queues[repo].popleft())
                if len(selected) == count:
                    break
    return selected


def safe_source_path(value):
    if value.startswith(('a/', 'b/')):
        value = value[2:]
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or '..' in path.parts or '\\' in value
            or ':' in value or not value.endswith('.py') or any(p.startswith('.') for p in path.parts)):
        raise ValueError('Unsafe/non-Python patch path: ' + value)
    return value


def diff_header_path(value, old_header=False):
    # Traditional unified diffs may label the OLD file .orig and include dates.
    # Preserve the raw diff; Git still decides whether it applies to the actual file.
    parts = value.split()
    if not parts:
        raise ValueError('Empty diff path')
    name = parts[0]
    if len(parts) > 1 and not re.match(r'^\d{4}-\d{2}-\d{2}$', parts[1]):
        raise ValueError('Unexpected diff filename suffix')
    if old_header and name.endswith('.orig'):
        name = name[:-5]
    return safe_source_path(name)


def patch_paths(text):
    pairs = []
    git_headers = set()
    pending = None
    for line in text.splitlines():
        if line.startswith('diff --git '):
            header = re.fullmatch(r'diff --git a/(\S+) b/(\S+)', line)
            if not header or header[1] != header[2]:
                raise ValueError('Invalid or renamed Git diff header')
            git_headers.add(safe_source_path(header[1]))
        if line.startswith(('GIT binary patch', 'Binary files ', 'rename ', 'copy ', 'new file mode ',
                            'deleted file mode ', 'old mode ', 'new mode ')):
            raise ValueError('Only edits to existing source files are allowed')
        if line.startswith('--- '):
            if pending is not None:
                raise ValueError('Unpaired old-file header')
            pending = diff_header_path(line[4:], old_header=True)
        elif line.startswith('+++ '):
            new = diff_header_path(line[4:])
            if pending != new:
                raise ValueError('New/deleted/renamed files are not supported')
            pairs.append(new)
            pending = None
    if pending is not None or not pairs or not re.search(r'^@@ ', text, re.M):
        raise ValueError('Missing unified-diff headers/hunks')
    if git_headers and git_headers != set(pairs):
        raise ValueError('Conflicting Git and unified-diff file headers')
    return set(pairs)


def extract_diff(text, allowed_paths):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 131072:
        raise ValueError('Invalid/oversized output')
    text = text.replace('\r\n', '\n').lstrip('\ufeff\r\n')
    fence = re.fullmatch(r'```(?:diff|patch)?[ \t]*\n(.*?)\n```[ \t\r\n]*', text, re.S)
    if fence:
        text = fence[1]
    if not text.startswith(('diff --git ', '--- ')):
        raise ValueError('Output must be a diff, optionally in one diff/patch code fence')
    paths = patch_paths(text)
    if not paths <= set(allowed_paths):
        raise ValueError('Patch edits files outside the supplied affected source files')
    return text if text.endswith('\n') else text + '\n'


def selector_key(selector):
    head, bracket, parameters = selector.partition('[')
    parts = head.split('::')
    if bracket:
        parts[-1] += '[' + parameters
    path = PurePosixPath(parts[0])
    if (selector.startswith('-') or path.is_absolute() or '..' in path.parts
            or not parts[0].endswith('.py') or len(parts) < 2 or '\n' in selector or '\r' in selector):
        raise ValueError('Invalid explicit pytest selector')
    return '.'.join([parts[0][:-3].replace('/', '.'), *parts[1:-1]]) + '::' + parts[-1]


def junit_outcomes(xml_path):
    result = {}
    for case in ET.parse(xml_path).iter('testcase'):
        key = case.attrib.get('classname', '') + '::' + case.attrib.get('name', '')
        if key in result:
            raise ValueError('Ambiguous duplicate JUnit test identity')
        result[key] = ('failed' if case.find('failure') is not None else
                       'error' if case.find('error') is not None else
                       'skipped' if case.find('skipped') is not None else 'passed')
    return result


def all_passed(stage, expected):
    return stage['exit_code'] == 0 and set(stage['outcomes']) == set(expected) and all(
        value == 'passed' for value in stage['outcomes'].values())


def normalize_official_selector(selector, repo):
    # Mido metadata was collected from ../dev/tests. Only map this reviewed prefix;
    # the container still requires the mapped file and all three reference controls.
    if selector.startswith('../dev/tests/') and repo.split('/')[-1].startswith('mido__mido.'):
        selector = selector[len('../dev/'):]
    selector_key(selector)
    return selector


def observed_bug_failures(stage, fail_keys, pass_keys):
    expected = set(fail_keys) | set(pass_keys)
    outcomes = stage['outcomes']
    if (stage['exit_code'] != 1 or set(outcomes) != expected
            or any(outcomes[k] not in {'passed', 'failed'} for k in fail_keys)
            or any(outcomes[k] != 'passed' for k in pass_keys)):
        raise ValueError('Bug reference has collection errors, missing tests, skips, or regression-control failures')
    observed = [key for key in fail_keys if outcomes[key] == 'failed']
    if not observed:
        raise ValueError('No listed bug failure reproduced')
    return observed
