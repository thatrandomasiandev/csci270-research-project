"""Resolve an input manifest against a declared root before any work.

Relative paths are joined to that root. The process working directory is
not consulted. A missing file, a size mismatch, or an MD5 mismatch raises
InputManifestError. The message always starts with STOP_INPUTS, and the
check creates no files.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

_INPUT_FLAGS = ("--old", "--new", "--queries", "--iseq", "--root")
_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_VAR = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(?::\?[^}]*)?\}(.*)$|^\$([A-Za-z_][A-Za-z0-9_]*)(.*)$")


class InputManifestError(Exception):
    """Inputs are missing or do not match the manifest. No work has started."""

    def __init__(self, message: str) -> None:
        text = message.removeprefix("STOP_INPUTS:").strip()
        super().__init__(f"STOP_INPUTS: {text}")


@dataclass(frozen=True)
class InputSpec:
    """One named input. `path` may be relative to the declared root.

    A directory is checked by a relative `member` file. Size and MD5 apply
    to that member, or to the file itself when `kind` is `file`.
    """

    name: str
    path: str
    size: int | None = None
    md5: str | None = None
    kind: str = "file"
    member: str | None = None
    executable: bool = False


@dataclass(frozen=True)
class ResolvedInput:
    """Absolute path plus the size and MD5 the check actually read."""

    name: str
    path: Path
    size: int | None
    md5: str | None
    member: Path | None = None

    def as_dict(self) -> dict:
        payload = {"path": str(self.path), "size": self.size, "md5": self.md5}
        if self.member is not None:
            payload["member"] = str(self.member)
        return payload


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_path(root: Path, raw: str) -> Path:
    """Absolute path. Relative inputs join `root` and never the working directory."""
    root_path = Path(root)
    if not root_path.is_absolute():
        raise InputManifestError(f"root is not absolute: {root}")
    text = str(raw).strip()
    if not text:
        raise InputManifestError("path is empty")
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    return root_path / candidate


def check_manifest(specs: list[InputSpec], root: Path) -> dict[str, ResolvedInput]:
    """Validate every spec. Raise before returning if any input is wrong."""
    resolved: dict[str, ResolvedInput] = {}
    errors: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        if spec.name in seen:
            errors.append(f"duplicate input name {spec.name}")
            continue
        seen.add(spec.name)
        try:
            path = resolve_path(root, spec.path)
        except InputManifestError as exc:
            errors.append(_detail(exc))
            continue
        if spec.kind == "directory":
            _check_directory(spec, path, resolved, errors)
            continue
        if spec.kind != "file":
            errors.append(f"{spec.name} kind {spec.kind} is unknown")
            continue
        _check_file(spec, path, path, resolved, errors, member=None)
    if errors:
        raise InputManifestError("; ".join(errors))
    return resolved


def parse_pins(text: str) -> dict[str, str]:
    """Parse `name==version` lines. An unpinned line is rejected."""
    pins: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "==" not in line or line.startswith("-"):
            raise InputManifestError(f"unpinned requirement on line {lineno}: {line}")
        name, version = line.split("==", 1)
        name = name.strip()
        version = version.strip()
        if not name or not version or not version[:1].isdigit():
            raise InputManifestError(f"unpinned requirement on line {lineno}: {line}")
        pins[name] = version
    if not pins:
        raise InputManifestError("requirements file has no pins")
    return pins


def check_requirement_pins(path: Path, lookup=None) -> dict[str, str]:
    """Installed distributions must equal the pinned versions."""
    pins = parse_pins(Path(path).read_text())
    if lookup is None:
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as dist_version

        def lookup(name: str) -> str:
            try:
                return dist_version(name)
            except PackageNotFoundError as exc:
                raise InputManifestError(f"{name} is not installed") from exc

    found: dict[str, str] = {}
    errors: list[str] = []
    for name, pin in pins.items():
        try:
            got = lookup(name)
        except InputManifestError as exc:
            errors.append(_detail(exc))
            continue
        except Exception as exc:
            errors.append(f"{name} is not installed ({exc})")
            continue
        if got != pin:
            errors.append(f"{name} version is {got}, pinned {pin}")
            continue
        found[name] = got
    if errors:
        raise InputManifestError("; ".join(errors))
    return found


def relative_input_paths(text: str, flags: tuple[str, ...] = _INPUT_FLAGS) -> list[str]:
    """Input-flag values in a job script that are not absolute paths.

    A value is absolute when it starts with `/`, when it expands from a
    variable whose assignments are absolute, when that variable is rejected
    at runtime unless it starts with `/`, or when it is produced by a sound
    `require_absolute` helper. Reading a path file with `$(cat ...)` and
    passing the text through is not absolute: the file can hold a relative
    path, which is the failure mode of job 12759635.
    """
    body = "\n".join(_logical_lines(text))
    assignments = _assignments(body)
    findings: list[str] = []
    if "require_absolute" in body and not _require_absolute_sound(body):
        findings.append("require_absolute does not reject a non-absolute path")
    for line in _logical_lines(text):
        if not any(flag in line for flag in flags):
            continue
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError as exc:
            findings.append(f"unparsed input line ({exc}): {line.strip()}")
            continue
        for index, token in enumerate(tokens):
            if token not in flags or index + 1 >= len(tokens):
                continue
            value = tokens[index + 1]
            if value.startswith("-") and token != "--root":
                findings.append(f"{token} is missing a path")
                continue
            if not _value_is_absolute(value, assignments, body, frozenset()):
                findings.append(f"{token} {value}")
    return findings


def scan_job_directory(jobs_dir: Path, flags: tuple[str, ...] = _INPUT_FLAGS) -> list[str]:
    """Relative input paths in every `*.job` under `jobs_dir`."""
    helper = jobs_dir.parent / "scripts" / "absolute_inputs.sh"
    helper_text = helper.read_text() if helper.is_file() else ""
    findings: list[str] = []
    jobs = sorted(Path(jobs_dir).glob("*.job"))
    if not jobs:
        raise InputManifestError(f"no job scripts in {jobs_dir}")
    for job in jobs:
        text = job.read_text()
        if "absolute_inputs.sh" in text:
            text = helper_text + "\n" + text
        for item in relative_input_paths(text, flags):
            findings.append(f"{job.name}: {item}")
    return findings


def _check_directory(spec: InputSpec, path: Path, resolved: dict, errors: list[str]) -> None:
    if not path.is_dir():
        errors.append(f"{spec.name} is not a directory: {path}")
        return
    if spec.member is None:
        if spec.size is not None or spec.md5 is not None:
            errors.append(f"{spec.name} is a directory; set member to check size and md5")
            return
        resolved[spec.name] = ResolvedInput(spec.name, path, None, None, None)
        return
    if Path(spec.member).is_absolute():
        errors.append(f"{spec.name} member is not relative: {spec.member}")
        return
    member = path / spec.member
    _check_file(spec, path, member, resolved, errors, member=member)


def _check_file(
    spec: InputSpec,
    record_path: Path,
    data_path: Path,
    resolved: dict,
    errors: list[str],
    *,
    member: Path | None,
) -> None:
    if not data_path.is_file():
        errors.append(f"{spec.name} is missing: {data_path}")
        return
    size = data_path.stat().st_size
    if spec.size is not None and size != spec.size:
        errors.append(f"{spec.name} size is {size}, expected {spec.size}: {data_path}")
        return
    digest = None
    if spec.md5 is not None:
        digest = file_md5(data_path)
        if digest != spec.md5.lower():
            errors.append(f"{spec.name} md5 is {digest}, expected {spec.md5}: {data_path}")
            return
    if spec.executable and not os.access(data_path, os.X_OK):
        errors.append(f"{spec.name} is not executable: {data_path}")
        return
    resolved[spec.name] = ResolvedInput(spec.name, record_path, size, digest, member)


def _detail(exc: InputManifestError) -> str:
    return str(exc).removeprefix("STOP_INPUTS:").strip()


def _logical_lines(text: str) -> list[str]:
    lines: list[str] = []
    buffer = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not buffer and (not stripped or stripped.startswith("#")):
            continue
        if buffer:
            buffer += " " + stripped
        else:
            buffer = stripped
        if buffer.endswith("\\"):
            buffer = buffer[:-1].rstrip()
            continue
        lines.append(buffer)
        buffer = ""
    if buffer:
        lines.append(buffer)
    return lines


def _assignments(body: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for line in body.splitlines():
        match = _ASSIGN.match(line.strip())
        if match is None:
            continue
        found.setdefault(match.group(1), []).append(match.group(2).strip())
    return found


def _require_absolute_sound(text: str) -> bool:
    return (
        "require_absolute()" in text
        and 'case "${value}" in' in text
        and "/*)" in text
        and "STOP_INPUTS:" in text
        and "exit 2" in text
    )


def _case_anchored(name: str, text: str) -> bool:
    pattern = re.compile(
        rf'case\s+"\$\{{{re.escape(name)}\}}"\s+in\s+'
        rf"/\*\)[\s\S]*?;;\s+\*\)[\s\S]*?exit\s+[0-9]+",
        re.M,
    )
    return pattern.search(text) is not None


def _unwrap(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _value_is_absolute(token: str, assignments: dict[str, list[str]], text: str, seen: frozenset[str]) -> bool:
    raw = _unwrap(token)
    if raw.startswith("/"):
        return True
    if "require_absolute" in raw and _require_absolute_sound(text):
        return True
    match = _VAR.match(raw)
    if match is None:
        return False
    name = match.group(1) or match.group(3)
    if name in seen:
        return False
    if _case_anchored(name, text):
        return True
    values = assignments.get(name, [])
    if not values:
        return False
    child = seen | {name}
    return all(_value_is_absolute(value, assignments, text, child) for value in values)
