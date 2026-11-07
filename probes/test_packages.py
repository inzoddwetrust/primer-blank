"""The instance's packages in the frontend image (DM-58, apply: runtime).

The packages are the published ones -- ``primer-blank-skin``,
``primer-blank-texts`` and ``primer-blank-brand`` (its ``skin/`` and
``texts/``) at the tags CI clones -- given by ``PRIMER_BLANK_SKIN``,
``PRIMER_BLANK_TEXTS`` and ``PRIMER_BLANK_BRAND``; without them the probes
error: they have no other color. ``validate-skin`` and ``validate-texts``
run the way the machine runs a package's ``validate``: ``docker run --rm`` of
the image with its own entrypoint and the package bound read-only at its
mount path.
"""

import json
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from probes.docker import docker, run_detached, run_once, wait_http

API = {
    "API_BASE_URL": "api.packages.test",
    "LANGUAGES": "en,ru",
    "DEFAULT_LANGUAGE": "en",
}


@pytest.fixture(scope="session")
def skin() -> Path:
    return Path(os.environ["PRIMER_BLANK_SKIN"])


@pytest.fixture(scope="session")
def texts() -> Path:
    return Path(os.environ["PRIMER_BLANK_TEXTS"])


@pytest.fixture(scope="session")
def brand() -> Path:
    return Path(os.environ["PRIMER_BLANK_BRAND"])


def _bind(directory: Path, path: str) -> str:
    return f"{directory}:{path}:ro"


def test_validate_takes_the_published_packages(
    frontend_runtime: str, skin: Path, texts: Path, brand: Path
) -> None:
    for given in (skin, brand / "skin"):
        done = run_once(
            frontend_runtime, (_bind(given, "/srv/skin"),), "validate-skin", "/srv/skin"
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "validate-skin: /srv/skin: ok" in done.stdout
    for given in (texts, brand / "texts"):
        done = run_once(
            frontend_runtime,
            (_bind(given, "/srv/texts"),),
            "validate-texts",
            "/srv/texts",
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "validate-texts: /srv/texts: ok" in done.stdout


def test_validate_refuses_a_planted_defect_by_its_file(
    frontend_runtime: str, skin: Path, texts: Path, tmp_path: Path
) -> None:
    bad_skin = tmp_path / "skin"
    shutil.copytree(skin, bad_skin, ignore=shutil.ignore_patterns(".git"))
    logo = bad_skin / "assets" / "logo.svg"
    logo.write_text(logo.read_text(encoding="utf-8") + "<script>x()</script>\n")
    done = run_once(
        frontend_runtime, (_bind(bad_skin, "/srv/skin"),), "validate-skin", "/srv/skin"
    )
    assert done.returncode != 0, done.stdout
    assert "validate-skin: assets/logo.svg: has a script" in done.stdout

    bad_texts = tmp_path / "texts"
    shutil.copytree(texts, bad_texts, ignore=shutil.ignore_patterns(".git"))
    english = bad_texts / "ui" / "en.json"
    body = json.loads(english.read_text(encoding="utf-8"))
    body["title"] = "<b>bold</b>"
    english.write_text(json.dumps(body), encoding="utf-8")
    # a language the product has no built-in texts of: the image's own list
    (bad_texts / "ui" / "de.json").write_text('{"title": "D"}', encoding="utf-8")
    done = run_once(
        frontend_runtime,
        (_bind(bad_texts, "/srv/texts"),),
        "validate-texts",
        "/srv/texts",
    )
    assert done.returncode != 0, done.stdout
    assert "validate-texts: ui/en.json: title: has markup" in done.stdout
    assert (
        "validate-texts: ui/de.json: language de is not one of the product's: en, ru"
    ) in done.stdout


def _get(container: str, path: str) -> tuple[int, bytes, str]:
    address = docker("port", container, "80/tcp").stdout.splitlines()[0].strip()
    try:
        with urllib.request.urlopen(f"http://{address}{path}", timeout=5) as answer:
            return answer.status, answer.read(), answer.headers["Content-Type"]
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers["Content-Type"]


def test_the_container_serves_the_mounted_packages(
    frontend_runtime: str, skin: Path, texts: Path
) -> None:
    container = run_detached(
        frontend_runtime,
        API,
        (_bind(skin, "/srv/skin"), _bind(texts, "/srv/texts")),
    )
    wait_http(container, "/config.json")
    colors = json.loads((skin / "tokens" / "color.tokens.json").read_text())
    primary = colors["color"]["brand"]["primary"]["$value"].lower()
    status, body, kind = _get(container, "/skin.css")
    assert (status, kind) == (200, "text/css; charset=utf-8"), body
    assert f"--color-brand-primary: {primary};" in body.decode()
    assert '--asset-logo: url("/skin/assets/logo.svg");' in body.decode()
    status, body, _ = _get(container, "/texts.json")
    given = {
        file.stem: json.loads(file.read_text(encoding="utf-8"))
        for file in sorted((texts / "ui").glob("*.json"))
    }
    assert sorted(given) == ["en", "ru"], given
    assert (status, json.loads(body)) == (200, given)
    status, body, kind = _get(container, "/skin/assets/logo.svg")
    assert (status, kind) == (200, "image/svg+xml")
    assert body == (skin / "assets" / "logo.svg").read_bytes()


def test_without_packages_the_page_keeps_its_own_theme_and_texts(
    frontend_runtime: str,
) -> None:
    container = run_detached(frontend_runtime, API)
    wait_http(container, "/config.json")
    status, body, _ = _get(container, "/skin.css")
    assert status == 200 and b"--" not in body, body
    assert _get(container, "/texts.json")[:2] == (200, b"{}")
    assert _get(container, "/skin/assets/logo.svg")[0] == 404


def _skin_with_logo(skin: Path, at: Path, inside: str) -> Path:
    """A copy of ``skin`` at ``at`` whose logo has ``inside`` before ``</svg>``."""
    shutil.copytree(skin, at, ignore=shutil.ignore_patterns(".git"))
    logo = at / "assets" / "logo.svg"
    body = logo.read_text(encoding="utf-8")
    assert body.count("</svg>") == 1, body
    logo.write_text(body.replace("</svg>", f"{inside}</svg>"), encoding="utf-8")
    return at


def test_probe_DM_74_svg_handler_and_unquoted_href_refused(
    frontend_runtime: str, skin: Path, tmp_path: Path
) -> None:
    """validate-skin of the image refuses an event handler after a slash
    (``<g/onload=…>``; a root ``<svg/onload=…>`` is not an SVG image at all)
    and a link out of the file without quotes, each by its file and rule; a
    link inside the file is taken."""
    refused = {
        '<g/onload="x()"/>': "validate-skin: assets/logo.svg: has an event handler",
        "<image href=https://x.test/a.png />": (
            "validate-skin: assets/logo.svg: has a link out of the file"
        ),
    }
    for number, (inside, problem) in enumerate(refused.items()):
        given = _skin_with_logo(skin, tmp_path / f"refused-{number}", inside)
        done = run_once(
            frontend_runtime, (_bind(given, "/srv/skin"),), "validate-skin", "/srv/skin"
        )
        assert done.returncode != 0, done.stdout
        assert problem in done.stdout.splitlines(), done.stdout
    taken = _skin_with_logo(skin, tmp_path / "taken", '<use href="#a"/><g id="a"/>')
    done = run_once(
        frontend_runtime, (_bind(taken, "/srv/skin"),), "validate-skin", "/srv/skin"
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "validate-skin: /srv/skin: ok" in done.stdout


ASSET_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-cache",
}


def _headers(container: str, path: str) -> tuple[int, dict[str, str]]:
    address = docker("port", container, "80/tcp").stdout.splitlines()[0].strip()
    try:
        with urllib.request.urlopen(f"http://{address}{path}", timeout=5) as answer:
            return answer.status, {name: answer.headers[name] for name in ASSET_HEADERS}
    except urllib.error.HTTPError as error:
        return error.code, {name: error.headers[name] for name in ASSET_HEADERS}


def test_the_skin_assets_run_nothing_when_opened(
    frontend_runtime: str, skin: Path
) -> None:
    """``/skin/assets/``: a policy that runs and loads nothing, and nosniff,
    on an image and on a missing one alike."""
    container = run_detached(frontend_runtime, API, (_bind(skin, "/srv/skin"),))
    wait_http(container, "/config.json")
    assert _headers(container, "/skin/assets/logo.svg") == (200, ASSET_HEADERS)
    assert _headers(container, "/skin/assets/none.svg") == (404, ASSET_HEADERS)


def test_a_package_is_checked_once_per_container(
    frontend_runtime: str, skin: Path, tmp_path: Path
) -> None:
    """The skin is checked on its first request and its answer kept: a defect
    planted in the mounted files afterwards is not seen by that container. A
    new container -- what a new version of the package gets -- checks again
    and refuses it."""
    given = tmp_path / "skin"
    shutil.copytree(skin, given, ignore=shutil.ignore_patterns(".git"))
    container = run_detached(frontend_runtime, API, (_bind(given, "/srv/skin"),))
    wait_http(container, "/config.json")
    first = _get(container, "/skin.css")
    assert first[0] == 200, first
    logo = given / "assets" / "logo.svg"
    logo.write_text(
        logo.read_text(encoding="utf-8").replace(
            "</svg>", "<script>x()</script></svg>"
        ),
        encoding="utf-8",
    )
    assert _get(container, "/skin.css") == first
    fresh = run_detached(frontend_runtime, API, (_bind(given, "/srv/skin"),))
    wait_http(fresh, "/config.json")
    assert _get(fresh, "/skin.css")[0] == 500
