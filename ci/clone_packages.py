"""The published packages of the blank, each at its tag and its pinned commit.

    python ci/clone_packages.py <dir>              clone, print NAME=path lines
    python ci/clone_packages.py <dir> --selftest   planted defects must be refused

A tag can be moved by whoever can push to the package's repository; a commit
cannot. Each package is cloned by its tag (``<SLOT>_TAG``) and its checkout
must be the commit pinned beside the tag (``<SLOT>_COMMIT``), the way CI
checks the machine it installs (``PRIDEM_COMMIT``). A tag moved, a tag gone or
a pin that is not a full commit is a problem named with its package; any
problem is exit 1.

The repositories are ``https://github.com/<PACKAGES_OWNER>/<name>.git``. Each
package lands in ``<dir>/<slot>``; stdout gets one ``PRIMER_BLANK_<SLOT>=``
line per package, for ``$GITHUB_ENV``.

``--selftest`` builds repositories in a temporary directory, with no network:
the right pin must pass, and a moved tag, a missing tag, an empty and a short
pin must each be refused.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

# slot -> repository of the package
PACKAGES = {
    "skin": "primer-blank-skin",
    "texts": "primer-blank-texts",
    "brand": "primer-blank-brand",
}

COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is not on PATH")
    # Arguments are this script's own and the pinned names; no shell.
    return subprocess.run(  # noqa: S603
        [git, *args], capture_output=True, text=True, check=False
    )


def clone(url: str, tag: str, commit: str, target: Path) -> list[str]:
    """Clone ``url`` at ``tag`` into ``target``; its HEAD must be ``commit``."""
    if not COMMIT.fullmatch(commit):
        return [f"{url}: the pin of {tag} is not a full commit: {commit!r}"]
    done = _git("clone", "-q", "--depth", "1", "--branch", tag, url, str(target))
    if done.returncode != 0:
        return [f"{url}: no clone at {tag}: {done.stderr.strip()}"]
    head = _git("-C", str(target), "rev-parse", "HEAD")
    if head.returncode != 0:
        return [f"{url}: no HEAD at {tag}: {head.stderr.strip()}"]
    found = head.stdout.strip()
    if found != commit:
        return [f"{url}: {tag} is {found}, pinned {commit}: the tag moved"]
    return []


def clone_all(
    base: str, env: Mapping[str, str], target: Path
) -> tuple[list[str], list[str]]:
    """Every package from ``base``/<name>.git into ``target``/<slot>.

    Returns the ``NAME=path`` lines and the problems."""
    lines: list[str] = []
    problems: list[str] = []
    for slot, name in PACKAGES.items():
        key = slot.upper()
        tag, commit = env.get(f"{key}_TAG", ""), env.get(f"{key}_COMMIT", "")
        if not tag:
            problems.append(f"{name}: {key}_TAG is not set")
            continue
        found = clone(f"{base}/{name}.git", tag, commit, target / slot)
        if found:
            problems += found
        else:
            lines.append(f"PRIMER_BLANK_{key}={target / slot}")
    return lines, problems


def run(target: Path) -> int:
    owner = os.environ.get("PACKAGES_OWNER", "")
    if not owner:
        print("PACKAGES_OWNER is not set", file=sys.stderr)
        return 1
    lines, problems = clone_all(f"https://github.com/{owner}", os.environ, target)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    for line in lines:
        print(line)
    return 0


def _repository(root: Path, name: str) -> dict[str, str]:
    """A bare repository ``root``/<name>.git with tag v1 on a second commit;
    returns the two commits as ``first`` and ``tagged``."""
    work = root / "work" / name
    work.mkdir(parents=True)
    done = _git("init", "-q", str(work))
    if done.returncode != 0:
        raise RuntimeError(done.stderr)
    commits: dict[str, str] = {}
    for step in ("first", "tagged"):
        (work / "file").write_text(step, encoding="utf-8")
        steps: list[list[str]] = [
            ["add", "file"],
            ["-c", "user.name=ci", "-c", "user.email=ci@ci", "commit", "-qm", step],
        ]
        for args in steps:
            done = _git("-C", str(work), *args)
            if done.returncode != 0:
                raise RuntimeError(done.stderr)
        commits[step] = _git("-C", str(work), "rev-parse", "HEAD").stdout.strip()
    tags: list[list[str]] = [
        ["-C", str(work), "tag", "v1"],
        ["clone", "-q", "--bare", str(work), str(root / f"{name}.git")],
    ]
    for args in tags:
        done = _git(*args)
        if done.returncode != 0:
            raise RuntimeError(done.stderr)
    return commits


def selftest() -> int:
    """The right pins must pass; each planted defect must be refused."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        commits = {name: _repository(root, name) for name in PACKAGES.values()}
        base = f"file://{root}"
        right = {f"{slot.upper()}_TAG": "v1" for slot in PACKAGES}
        right |= {
            f"{slot.upper()}_COMMIT": commits[name]["tagged"]
            for slot, name in PACKAGES.items()
        }
        lines, problems = clone_all(base, right, root / "right")
        if problems or len(lines) != len(PACKAGES):
            print(f"selftest: the right pins do not pass: {problems}", file=sys.stderr)
            return 1
        print(f"selftest: the right pins pass: {len(lines)} packages")
        planted: dict[str, tuple[dict[str, str], str]] = {
            "a moved tag": (
                right | {"TEXTS_COMMIT": commits["primer-blank-texts"]["first"]},
                "the tag moved",
            ),
            "a missing tag": (right | {"BRAND_TAG": "v9"}, "no clone at v9"),
            "an empty pin": (right | {"SKIN_COMMIT": ""}, "is not a full commit"),
            "a short pin": (
                right | {"SKIN_COMMIT": commits["primer-blank-skin"]["tagged"][:12]},
                "is not a full commit",
            ),
        }
        for number, (name, (env, problem)) in enumerate(planted.items()):
            _, found = clone_all(base, env, root / f"planted-{number}")
            if len(found) != 1 or problem not in found[0]:
                print(
                    f"selftest: {name!r} not refused as {problem!r}: {found}",
                    file=sys.stderr,
                )
                return 1
            print(f"selftest: {name!r} refused: {found[0]}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python ci/clone_packages.py")
    parser.add_argument("dir", type=Path, help="where the packages land")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    return selftest() if args.selftest else run(args.dir)


if __name__ == "__main__":
    sys.exit(main())
