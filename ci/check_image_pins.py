"""Every image the repository pulls is pinned by tag and digest.

    python ci/check_image_pins.py              check, print every problem
    python ci/check_image_pins.py --list       print the pinned references
    python ci/check_image_pins.py --selftest   planted defects must be refused

A tag can be moved by whoever can push it; a digest cannot. A reference is
``name:tag@sha256:<64 hex>``: the tag says which release it is, the digest
makes a pull unable to move it. Changing the version means changing both.

Read: ``FROM`` of each Dockerfile (a stage built earlier in the same file is
not an image and is skipped), ``image:`` of the compose file and of the CI
workflow. A Dockerfile without a single pulled image is a problem too: a check
that finds nothing to check proves nothing.
"""

import argparse
import re
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DOCKERFILES = ("backend/Dockerfile", "frontend/Dockerfile")
YAML_FILES = ("docker-compose.yml", ".github/workflows/ci.yml")

PINNED = re.compile(r"^[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")
FROM_LINE = re.compile(
    r"^\s*FROM\s+(?:--platform=\S+\s+)?(?P<ref>\S+)(?:\s+AS\s+(?P<stage>\S+))?\s*$",
    re.IGNORECASE,
)
IMAGE_LINE = re.compile(r"^\s*image:\s*(?P<ref>\S+)\s*$")


@dataclass(frozen=True)
class Ref:
    """One pulled image reference and where it is written."""

    file: str
    line: int
    ref: str


def dockerfile_refs(file: str, text: str) -> list[Ref]:
    """Images pulled by ``FROM``; earlier stages of the same file are skipped."""
    stages: set[str] = set()
    refs: list[Ref] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = FROM_LINE.match(line)
        if match is None:
            continue
        ref = match.group("ref")
        if ref.lower() not in stages:
            refs.append(Ref(file, number, ref))
        if match.group("stage"):
            stages.add(match.group("stage").lower())
    return refs


def yaml_refs(file: str, text: str) -> list[Ref]:
    """Images named by ``image:`` lines."""
    return [
        Ref(file, number, match.group("ref").strip("\"'"))
        for number, line in enumerate(text.splitlines(), start=1)
        if (match := IMAGE_LINE.match(line))
    ]


def collect(root: Path) -> tuple[list[Ref], list[str]]:
    """Every reference under ``root`` and the problems found."""
    refs: list[Ref] = []
    problems: list[str] = []
    for file in DOCKERFILES:
        found = dockerfile_refs(file, (root / file).read_text(encoding="utf-8"))
        if not found:
            problems.append(f"{file}: no FROM pulls an image")
        refs += found
    for file in YAML_FILES:
        refs += yaml_refs(file, (root / file).read_text(encoding="utf-8"))
    for ref in refs:
        if not PINNED.fullmatch(ref.ref):
            problems.append(
                f"{ref.file}:{ref.line}: {ref.ref!r} is not name:tag@sha256:<digest>"
            )
    return refs, problems


def check(root: Path) -> int:
    """Print every problem; 1 if there is any."""
    refs, problems = collect(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    if not problems:
        print(f"{len(refs)} image references, each pinned by tag and digest")
    return 1 if problems else 0


def _strip_digest(text: str) -> str:
    return re.sub(r"@sha256:[0-9a-f]{64}", "", text, count=1)


def _drop_tag(text: str) -> str:
    return re.sub(r"(FROM\s+[a-z0-9./-]+):[A-Za-z0-9._-]+@", r"\1@", text, count=1)


def _no_from(text: str) -> str:
    return re.sub(r"(?im)^FROM\s.*$", "# no FROM", text)


# file -> planted defect; each must be refused.
DEFECTS: dict[str, tuple[str, Callable[[str], str]]] = {
    "FROM without digest": ("backend/Dockerfile", _strip_digest),
    "image: without digest": ("docker-compose.yml", _strip_digest),
    "CI service without digest": (".github/workflows/ci.yml", _strip_digest),
    "FROM with digest, no tag": ("frontend/Dockerfile", _drop_tag),
    "Dockerfile pulling nothing": ("frontend/Dockerfile", _no_from),
}


def selftest(root: Path) -> int:
    """The tree must pass; each planted defect, in a copy, must not."""
    refs, problems = collect(root)
    if problems:
        print("selftest: the tree itself does not pass", file=sys.stderr)
        return 1
    backend = (root / "backend/Dockerfile").read_text(encoding="utf-8")
    stage_from = re.search(r"(?im)^FROM\s+base\s+AS\s", backend)
    if stage_from is None or any(r.ref == "base" for r in refs):
        print("selftest: a stage name was taken for an image", file=sys.stderr)
        return 1
    passed: list[str] = []
    for name, (file, plant) in DEFECTS.items():
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            for each in (*DOCKERFILES, *YAML_FILES):
                (copy / each).parent.mkdir(parents=True, exist_ok=True)
                (copy / each).write_text((root / each).read_text(encoding="utf-8"))
            original = (copy / file).read_text(encoding="utf-8")
            planted = plant(original)
            if planted == original:
                print(f"selftest: defect {name!r} was not planted", file=sys.stderr)
                return 1
            (copy / file).write_text(planted, encoding="utf-8")
            _, found = collect(copy)
        if found:
            print(f"selftest: {name!r} refused: {found[0]}")
        else:
            passed.append(name)
    for name in passed:
        print(f"selftest: planted defect {name!r} passed", file=sys.stderr)
    return 1 if passed else 0


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python ci/check_image_pins.py")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest(ROOT)
    if args.list:
        refs, problems = collect(ROOT)
        if problems:
            return check(ROOT)
        for ref in sorted({r.ref for r in refs}):
            print(ref)
        return 0
    return check(ROOT)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
