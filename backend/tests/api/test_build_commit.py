"""The commit an image is built from: stamped at build, answered by /health, sent as the release.

/health answered ``"version": "unknown"`` in production: Dokploy builds
docker-compose.dokploy.yml with no build arg, so the image's ``GIT_SHA`` stayed at its
default, and the promote job could not check that a deploy went live (its last step stays
off until it can: ``VERIFY_DEPLOYED_VERSION``). Dokploy's build runs in a depth-1 clone whose
``.git`` sits next to the compose file, so the compose file hands the repository root to both
builds as the named context ``gitmeta`` (the root ``.dockerignore`` lets only the git metadata
through), and each image's LAST build step reads the commit from it
(``scripts/build-commit.sh``): the backend writes it to ``/app/GIT_SHA``, which settings read
when the ``GIT_SHA`` variable names no commit; the front stamps it into index.html's
``majlisna-release`` meta. CI keeps ``--build-arg GIT_SHA``, which wins; a build with neither
(the E2E stack) says ``unknown``.
"""

import re
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi import FastAPI

from majlisna import settings as settings_module
from majlisna.app import _configure_observability
from majlisna.settings import Settings

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "backend" / "scripts" / "build-commit.sh"
FRONT_SCRIPT = REPO / "front" / "scripts" / "build-commit.sh"
BACKEND_DOCKERFILE = REPO / "backend" / "Dockerfile"
FRONT_DOCKERFILE = REPO / "front" / "Dockerfile"
PRODUCTION_COMPOSE = REPO / "docker-compose.dokploy.yml"
ROOT_DOCKERIGNORE = REPO / ".dockerignore"

COMMIT = "146c7ca180e4c1f2a80bb3771b075eae476ae5b5"
OTHER_COMMIT = "0f3c9a1b2d4e5f60718293a4b5c6d7e8f9012345"


def _resolve(git_dir: Path, build_arg: str | None = None) -> str:
    """What the image's build step writes: the script run by POSIX sh, as in the Dockerfiles."""
    args = ["sh", str(SCRIPT), str(git_dir)] + ([build_arg] if build_arg is not None else [])
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def _git_dir(tmp_path: Path, head: str, files: dict[str, str] | None = None) -> Path:
    git_dir = tmp_path / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text(head)
    for name, content in (files or {}).items():
        path = git_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return git_dir


# ─── scripts/build-commit.sh ────────────────────────────────────────────────


def test_a_dokploy_clone_names_its_commit_through_its_branch(tmp_path: Path):
    """Dokploy's depth-1 clone: HEAD names the branch; the branch's ref is a file or a packed-refs line."""
    # Prepare
    loose = _git_dir(tmp_path / "loose", "ref: refs/heads/production\n", {"refs/heads/production": f"{COMMIT}\n"})
    packed = _git_dir(
        tmp_path / "packed",
        "ref: refs/heads/production\n",
        {
            "packed-refs": (
                "# pack-refs with: peeled fully-peeled sorted \n"
                f"{OTHER_COMMIT} refs/heads/main\n"
                f"{COMMIT} refs/heads/production\n"
                f"^{OTHER_COMMIT}\n"
            ),
            "shallow": f"{COMMIT}\n",
        },
    )

    # Act / Assert — the GIT_SHA build arg's default, "unknown", names no commit
    assert _resolve(loose, "unknown") == f"{COMMIT}\n"
    assert _resolve(packed, "unknown") == f"{COMMIT}\n"


def test_a_detached_head_is_the_commit(tmp_path: Path):
    """A checkout of the commit itself (HEAD holds the hash)."""
    assert _resolve(_git_dir(tmp_path, f"{COMMIT}\n")) == f"{COMMIT}\n"


def test_the_build_arg_wins_when_it_is_a_commit(tmp_path: Path):
    """CI's `--build-arg GIT_SHA=$GITHUB_SHA`, with or without git metadata beside it."""
    # Prepare
    git_dir = _git_dir(tmp_path, f"{OTHER_COMMIT}\n")

    # Act / Assert
    assert _resolve(git_dir, COMMIT) == f"{COMMIT}\n"
    assert _resolve(tmp_path / "no-such-dir", COMMIT) == f"{COMMIT}\n"


@pytest.mark.parametrize(
    "build_arg",
    ["unknown", "", COMMIT[:7], COMMIT.upper(), COMMIT + "0", COMMIT + "\n" + COMMIT, "$(id)"],
    ids=["unknown", "empty", "short", "uppercase", "41-digits", "two-lines", "shell"],
)
def test_a_build_arg_that_is_not_a_commit_is_not_believed(tmp_path: Path, build_arg: str):
    """Only exactly 40 lowercase hex digits are a commit; anything else falls through to the metadata."""
    assert _resolve(tmp_path / "no-such-dir", build_arg) == "unknown\n"
    assert _resolve(_git_dir(tmp_path, f"{OTHER_COMMIT}\n"), build_arg) == f"{OTHER_COMMIT}\n"


@pytest.mark.parametrize(
    ("head", "files"),
    [
        ("ref: refs/heads/production\n", {}),  # the branch exists nowhere
        ("ref: refs/heads/production\n", {"refs/heads/production": f"{COMMIT[:12]}\n"}),
        ("ref: refs/heads/production\n", {"refs/heads/production": f"{COMMIT}{COMMIT[:24]}\n"}),  # SHA-256 length
        ("ref: refs/heads/production\n", {"packed-refs": f"{COMMIT} refs/heads/main\n"}),  # another branch
        ("ref: refs/heads/../../HEAD\n", {}),
        ("ref: ../outside\n", {}),
        ("not a commit\n", {}),
        ("", {}),
    ],
    ids=["no-ref", "short-ref", "long-ref", "other-branch", "dot-dot", "outside-refs", "garbage", "empty"],
)
def test_metadata_that_names_no_commit_says_unknown(tmp_path: Path, head: str, files: dict[str, str]):
    """Whatever the metadata holds, the output is a commit or ``unknown``, never something else."""
    assert _resolve(_git_dir(tmp_path, head, files), "unknown") == "unknown\n"


def test_no_metadata_at_all_says_unknown(tmp_path: Path):
    """The E2E stack and a bare `docker build`: the `gitmeta` stage is empty."""
    # Prepare — an empty context, as the Dockerfiles' `FROM scratch AS gitmeta` mounts it
    empty = tmp_path / "gitmeta"
    empty.mkdir()

    # Act / Assert
    assert _resolve(empty / ".git") == "unknown\n"


def test_each_image_carries_the_same_script():
    """Each image's build context holds only its own directory, so the script exists twice."""
    assert FRONT_SCRIPT.read_bytes() == SCRIPT.read_bytes()


# ─── The app reads the stamp ────────────────────────────────────────────────


@pytest.fixture(name="stamp")
def get_stamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Where the image's build step writes the commit, here a temporary file."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    stamp = tmp_path / "GIT_SHA"
    monkeypatch.setattr(settings_module, "BUILD_COMMIT_FILE", stamp)
    return stamp


@pytest.mark.parametrize("env_value", ["unknown", None], ids=["unknown", "unset"])
def test_settings_read_the_stamp_when_the_variable_names_no_commit(
    stamp: Path, monkeypatch: pytest.MonkeyPatch, env_value: str | None
):
    """Dokploy's image: ENV GIT_SHA=unknown (no build arg), the commit in /app/GIT_SHA."""
    # Prepare
    stamp.write_text(f"{COMMIT}\n")
    if env_value is None:
        monkeypatch.delenv("GIT_SHA", raising=False)
    else:
        monkeypatch.setenv("GIT_SHA", env_value)

    # Act / Assert
    assert Settings().git_sha == COMMIT


def test_settings_prefer_a_variable_that_names_a_commit(stamp: Path, monkeypatch: pytest.MonkeyPatch):
    """CI's image: the build arg reached ENV GIT_SHA (the stamp holds the same commit there)."""
    # Prepare
    stamp.write_text(f"{OTHER_COMMIT}\n")
    monkeypatch.setenv("GIT_SHA", COMMIT)

    # Act / Assert
    assert Settings().git_sha == COMMIT


@pytest.mark.parametrize(
    ("env_value", "stamped"),
    [
        ("unknown", None),  # a development checkout: no stamp at all
        ("unknown", "unknown\n"),  # the E2E image: neither source named a commit
        ("unknown", f"{COMMIT[:7]}\n"),
        ("not-a-commit", None),
        (COMMIT.upper(), f"{COMMIT}{COMMIT}\n"),
    ],
    ids=["no-stamp", "stamped-unknown", "short-stamp", "garbage-variable", "both-malformed"],
)
def test_settings_say_unknown_when_neither_names_a_commit(
    stamp: Path, monkeypatch: pytest.MonkeyPatch, env_value: str, stamped: str | None
):
    """Never a value /health would wrongly read as a commit."""
    # Prepare
    if stamped is not None:
        stamp.write_text(stamped)
    monkeypatch.setenv("GIT_SHA", env_value)

    # Act / Assert
    assert Settings().git_sha == "unknown"


# ─── The error tracker's release ────────────────────────────────────────────


@pytest.mark.parametrize(("git_sha", "release"), [(COMMIT, COMMIT), ("unknown", None)])
def test_backend_error_reports_carry_the_commit_as_their_release(
    test_settings: Settings, git_sha: str, release: str | None
):
    """Bugsink groups events by release: the running commit, or none rather than "unknown"."""
    # Prepare
    configured = test_settings.model_copy(
        update={"sentry_dsn": "https://key@errors.example/9", "git_sha": git_sha, "logfire_token": ""}
    )

    # Act
    with patch("majlisna.app.sentry_sdk.init") as init, patch("majlisna.app.logger") as logger:
        _configure_observability(configured, FastAPI())

    # Assert
    init.assert_called_once()
    assert init.call_args.kwargs["release"] == release
    logger.add.assert_called_once()


# ─── The builds ─────────────────────────────────────────────────────────────


def _instructions(dockerfile: Path) -> list[str]:
    """The Dockerfile's instructions, one string each (continuations joined, comments dropped)."""
    lines = [line for line in dockerfile.read_text().splitlines() if not line.lstrip().startswith("#")]
    joined = "\n".join(lines).replace("\\\n", " ")
    return [line.strip() for line in joined.splitlines() if line.strip()]


@pytest.mark.parametrize("dockerfile", [BACKEND_DOCKERFILE, FRONT_DOCKERFILE], ids=["backend", "front"])
def test_each_image_stamps_the_commit_in_its_last_layer(dockerfile: Path):
    """An empty `gitmeta` stage by default, and the stamp after every other layer: a new commit
    rebuilds that one step (a few bytes), never a cached layer before it."""
    # Prepare
    instructions = _instructions(dockerfile)
    stamp = next(i for i, line in enumerate(instructions) if "from=gitmeta" in line)

    # Act
    layers_after = [line for line in instructions[stamp + 1 :] if re.match(r"(RUN|COPY|ADD)\b", line)]

    # Assert
    assert "FROM scratch AS gitmeta" in instructions
    assert instructions[stamp].startswith("RUN --mount=type=bind,from=gitmeta,")
    assert "build-commit.sh" in instructions[stamp]
    assert any(line.startswith("ARG GIT_SHA=unknown") for line in instructions[:stamp])
    assert layers_after == []


def test_dokploys_compose_hands_the_repository_root_to_both_builds():
    """The named context is the root (always there, unlike `.git`: a missing context path fails
    the whole build), reduced by the root .dockerignore to the git metadata that names the commit."""
    # Prepare
    services = yaml.safe_load(PRODUCTION_COMPOSE.read_text())["services"]
    ignored = [line.strip() for line in ROOT_DOCKERIGNORE.read_text().splitlines()]
    patterns = [line for line in ignored if line and not line.startswith("#")]

    # Act / Assert
    for name in ("backend", "frontend"):
        assert services[name]["build"]["additional_contexts"] == {"gitmeta": "."}, name
    assert patterns == ["*", "!.git/HEAD", "!.git/refs", "!.git/packed-refs"]


def test_ci_and_the_e2e_stack_build_without_the_git_metadata():
    """CI passes the build arg instead; the E2E images say `unknown`, so their layers stay cached."""
    # Prepare
    e2e = yaml.safe_load((REPO / "e2e" / "docker-compose.e2e.yml").read_text())["services"]

    # Act / Assert
    for name in ("backend", "frontend"):
        assert "additional_contexts" not in e2e[name]["build"], name
