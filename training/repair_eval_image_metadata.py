"""Read-only validation of preinstalled, untracked Python packaging metadata."""
import hashlib
from pathlib import PurePosixPath

NAMES = {'PKG-INFO', 'SOURCES.txt', 'dependency_links.txt', 'top_level.txt',
         'requires.txt', 'entry_points.txt', 'not-zip-safe', 'zip-safe'}


def validate_packaging_status(status, root):
    root = root.resolve()
    records = []
    for line in status.splitlines():
        if not line.startswith('?? '):
            raise ValueError('Tracked image modifications are not allowed')
        relative = line[3:].rstrip('/')
        posix = PurePosixPath(relative)
        if (not relative.endswith('.egg-info') or posix.is_absolute() or '..' in posix.parts
                or '\\' in relative or ':' in relative):
            raise ValueError('Unexpected untracked image content')
        directory = root/relative
        if directory.is_symlink() or not directory.is_dir() or not directory.resolve().is_relative_to(root):
            raise ValueError('Unsafe packaging metadata path')
        files = list(directory.iterdir())
        if not files:
            raise ValueError('Empty metadata directory')
        for file in files:
            if file.is_symlink() or not file.is_file() or file.name not in NAMES:
                raise ValueError('Unexpected file in packaging metadata')
            records.append({'path':str(file.relative_to(root)),
                            'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
    return records



def derived_strip_level(diff):
    old = None
    levels = set()
    for line in diff.splitlines():
        if line.startswith('--- '):
            old = line[4:].split()[0]
        elif line.startswith('+++ '):
            new = line[4:].split()[0]
            if old is None:
                raise ValueError('Missing old-file header')
            if old.startswith('a/') and new.startswith('b/'):
                levels.add(1)
            elif old in {new, new + '.orig'}:
                levels.add(0)
            else:
                raise ValueError('Unsupported path-pair convention')
            old = None
    if old is not None or len(levels) != 1:
        raise ValueError('Missing or mixed path-prefix conventions')
    return levels.pop()
