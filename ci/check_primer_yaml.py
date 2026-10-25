"""Check ``primer.yaml`` with the deploy machine's own loader.

    python ci/check_primer_yaml.py primer.yaml
    python ci/check_primer_yaml.py primer.yaml --selftest

The loader of ``pridem`` holds the contract's rules; its JSON Schema holds only
the form, so the file is checked by the machine, not by the schema. The job
installs ``pridem`` at a fixed commit.

``--selftest`` plants defects the loader must refuse into copies of the file
-- an alias, a seed written as a string, a value in ``env`` -- and fails if one
of them passes. The file itself must pass first: a loader that refuses
everything would pass the planted defects too.
"""

import argparse
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from pridem.stacks.loader import ContractError
from pridem.stacks.schema import load_primer_yaml


def _alias(text: str) -> str:
    return text.replace(
        "  core: { services: [] }", "  core: &core { services: [] }\n  full: *core"
    )


def _seed_as_string(text: str) -> str:
    return text.replace(
        "bootstrap: { run: python -m app.seed bootstrap, when: install }",
        "bootstrap: python -m app.seed bootstrap",
    )


def _value_in_env(text: str) -> str:
    return text.replace(
        "POSTGRES_PASSWORD: { source: minted }",
        "POSTGRES_PASSWORD: { source: minted, value: hunter2 }",
    )


DEFECTS: dict[str, Callable[[str], str]] = {
    "alias": _alias,
    "seed as a string": _seed_as_string,
    "value in env": _value_in_env,
}


def check(file: Path) -> int:
    """Load ``file``; print every problem and return 1 if there are any."""
    try:
        stack = load_primer_yaml(file)
    except ContractError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"{file}: {stack.kind} {stack.name!r} passes the loader of pridem")
    return 0


def selftest(file: Path) -> int:
    """Each planted defect must be refused; the file itself must pass."""
    if check(file) != 0:
        print("selftest: the file itself does not pass", file=sys.stderr)
        return 1
    text = file.read_text(encoding="utf-8")
    passed: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, plant in DEFECTS.items():
            planted = plant(text)
            if planted == text:
                print(f"selftest: defect {name!r} was not planted", file=sys.stderr)
                return 1
            copy = Path(tmp) / "primer.yaml"
            copy.write_text(planted, encoding="utf-8")
            try:
                load_primer_yaml(copy)
            except ContractError as error:
                print(f"selftest: {name!r} refused: {error.problems[0].code}")
                continue
            passed.append(name)
    for name in passed:
        print(f"selftest: planted defect {name!r} passed the loader", file=sys.stderr)
    return 1 if passed else 0


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python ci/check_primer_yaml.py")
    parser.add_argument("file", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    file: Path = args.file
    return selftest(file) if args.selftest else check(file)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
