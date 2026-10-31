"""Library layer: which files of a vendored skill folder came from upstream, and their hashes.

A vendored folder ships upstream's files unchanged beside the `OWN` files this repository
writes at its top level.
"""
import hashlib
from pathlib import Path

# Written by this repository at the folder's top level, not copied from upstream.
OWN = frozenset({'ATTRIBUTION.md', 'upstream.json'})


def digest(path: Path) -> str:
    """The SHA-256 of one file's bytes, as lowercase hex."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copied(skill: Path) -> dict:
    """Every file under the skill folder that came from upstream, keyed by POSIX path relative
    to it.

    Recursive because a file in a subfolder ships. Only the top-level `OWN` files are left out;
    a file with one of those names deeper down is an upstream file like any other.
    """
    files = {path.relative_to(skill).as_posix(): path for path in sorted(skill.rglob('*'))
             if path.is_file()}
    return {name: path for name, path in files.items() if name not in OWN}
