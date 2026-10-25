"""Docker for the probes: build, run, read, remove -- all labelled.

Every image and container a probe makes carries ``pridem.probe=DM-26`` and is
removed when the probe session ends. A docker command that fails raises with
its output; nothing here is silent.
"""

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABEL = "pridem.probe=DM-26"


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run ``docker args``; with ``check`` a non-zero exit raises with output."""
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"docker {' '.join(args)} exited {result.returncode}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def build(
    context: str, tag: str, target: str, build_args: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Build ``context`` at ``target``; returns the result, raises on nothing."""
    args = ["build", "--label", LABEL, "--target", target, "-t", tag]
    for name, value in build_args.items():
        args += ["--build-arg", f"{name}={value}"]
    return docker(*args, str(ROOT / context), check=False)


def run_detached(image: str, env: dict[str, str]) -> str:
    """Start ``image`` with port 80 published on the loopback; return its id."""
    args = ["run", "-d", "--label", LABEL, "-p", "127.0.0.1::80"]
    for name, value in env.items():
        args += ["-e", f"{name}={value}"]
    return docker(*args, image).stdout.strip()


def list_files(image: str, root: str) -> list[str]:
    """Every regular file under ``root`` in ``image``, relative to it."""
    out = docker(
        "run",
        "--rm",
        "--label",
        LABEL,
        "--entrypoint",
        "find",
        image,
        root,
        "-type",
        "f",
    ).stdout
    prefix = root.rstrip("/") + "/"
    return sorted(line.removeprefix(prefix) for line in out.splitlines() if line)


def image_config(image: str) -> dict[str, list[str]]:
    """``Env`` and ``Cmd`` of the image config."""
    raw = docker("image", "inspect", "--format", "{{json .Config}}", image).stdout
    config = json.loads(raw)
    return {"Env": list(config.get("Env") or []), "Cmd": list(config.get("Cmd") or [])}


def wait_http(container: str, path: str, timeout_s: float = 30) -> tuple[int, bytes]:
    """GET ``path`` on the container's port 80 once it answers."""
    address = docker("port", container, "80/tcp").stdout.splitlines()[0].strip()
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with urllib.request.urlopen(f"http://{address}{path}", timeout=3) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()
        except (urllib.error.URLError, ConnectionError):
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def wait_exit(container: str, timeout_s: float = 30) -> int:
    """The exit code of ``container`` once it stopped; raises if it keeps running."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = json.loads(
            docker("inspect", "--format", "{{json .State}}", container).stdout
        )
        if not state["Running"] and state["Status"] in ("exited", "dead"):
            code: int = state["ExitCode"]
            return code
        time.sleep(0.5)
    raise AssertionError(f"container {container} is still running after {timeout_s}s")


def remove_labelled() -> None:
    """Remove every container and image the probes made."""
    ids = docker("ps", "-aq", "--filter", f"label={LABEL}").stdout.split()
    if ids:
        docker("rm", "-f", *ids)
    images = docker("images", "-q", "--filter", f"label={LABEL}").stdout.split()
    if images:
        docker("rmi", "-f", *sorted(set(images)))
