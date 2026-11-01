"""The backend image trusts proxy headers from Docker-network peers only (SEC F03, INFRA-07, PD-07).

The image ran uvicorn with ``--proxy-headers --forwarded-allow-ips '*'``. With ``*``,
uvicorn's ProxyHeadersMiddleware takes the LEFT-MOST X-Forwarded-For entry as the
client — the one the client itself writes, since Cloudflare and Traefik append to the
header rather than replace it. So every per-IP rate limit (login 5/min, register,
forgot-password, refresh) was keyed on a value of the caller's choosing: a different
left-most entry per request, and the limit never fired (probe
``test_f03_limiter_key_is_leftmost_forwarded_for_entry``).

These tests read the trust list the image actually runs with — the CMD's
``--forwarded-allow-ips`` value, resolved against the Dockerfile's ENV defaults — and
run uvicorn's own middleware with it. They do not start a container: the Dockerfile is
the single source of the default, and this pins what it says.
"""

import ipaddress
import json
import re
import shlex
from pathlib import Path

import httpx
import pytest
import yaml
from starlette.responses import PlainTextResponse
from starlette.types import Receive, Scope, Send
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from majlisna.api.constants import CLOUDFLARE_IP_RANGES

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"
PRODUCTION_COMPOSE = Path(__file__).resolve().parents[3] / "docker-compose.dokploy.yml"

# uvicorn's own default when neither the flag nor $FORWARDED_ALLOW_IPS is given.
UVICORN_DEFAULT_TRUSTED = "127.0.0.1"

# A Cloudflare edge (inside 162.158.0.0/15), a Traefik / nginx container on a Docker
# network, the Docker bridge gateway, and an address on the public internet.
CLOUDFLARE_EDGE = "162.158.12.34"
TRAEFIK_PEER = "172.18.0.3"
FRONTEND_NGINX_PEER = "172.20.0.5"
DOCKER_GATEWAY = "172.20.0.1"
PUBLIC_PEER = "203.0.113.7"
CLIENT_WRITTEN = "1.2.3.4"


def _dockerfile_text() -> str:
    # Backslash continuations joined, so a multi-line ENV or CMD reads as one line.
    return DOCKERFILE.read_text().replace("\\\n", " ")


def _production_stage() -> str:
    text = _dockerfile_text()
    marker = re.search(r"^FROM\s+\S+\s+AS\s+production\s*$", text, flags=re.MULTILINE | re.IGNORECASE)
    assert marker, "backend/Dockerfile has no `production` stage"
    return text[marker.end() :]


def _env_defaults(stage: str) -> dict[str, str]:
    """Every `ENV KEY=value` of the stage (the last one wins, as in Docker)."""
    values: dict[str, str] = {}
    for line in re.findall(r"^ENV\s+(.+)$", stage, flags=re.MULTILINE):
        for token in shlex.split(line):
            if "=" in token:
                key, _, value = token.partition("=")
                values[key] = value
    return values


def _cmd(stage: str) -> str:
    commands = re.findall(r"^CMD\s+(.+)$", stage, flags=re.MULTILINE)
    assert commands, "the production stage has no CMD"
    return commands[-1].strip()


def _shell_command(cmd: str) -> str:
    """The command line the container's shell runs, exec form or shell form."""
    if cmd.startswith("["):
        # Exec form is a JSON array; `sh -c "<command line>"` puts the line last.
        return json.loads(cmd)[-1]
    return cmd


def _expand(match: re.Match[str], env: dict[str, str]) -> str:
    name, fallback = match.group("braced") or match.group("bare"), match.group("fallback")
    value = env.get(name, "")
    # `${VAR:-word}`: the word when VAR is unset OR empty, as POSIX sh (and compose) read it.
    return fallback if fallback is not None and not value else value


def _resolve(value: str, env: dict[str, str]) -> str:
    """Expand ${VAR}, ${VAR:-default} and $VAR from ``env``, as the container's sh does."""
    pattern = r"\$(?:\{(?P<braced>[A-Z_][A-Z0-9_]*)(?::-(?P<fallback>[^}]*))?\}|(?P<bare>[A-Z_][A-Z0-9_]*))"
    return re.sub(pattern, lambda m: _expand(m, env), value)


def image_trusted_hosts(env: dict[str, str] | None = None) -> str:
    """The --forwarded-allow-ips value the image's uvicorn starts with (``env``: the container's, else the image's)."""
    stage = _production_stage()
    env = _env_defaults(stage) if env is None else env
    command = _shell_command(_cmd(stage))
    words = shlex.split(command)
    # `sh -c "uvicorn …"` nests the real command line one level down.
    while words and words[0] in {"sh", "/bin/sh"} and "-c" in words:
        words = shlex.split(words[words.index("-c") + 1])
    if "--forwarded-allow-ips" in words:
        return _resolve(words[words.index("--forwarded-allow-ips") + 1], env)
    return env.get("FORWARDED_ALLOW_IPS", UVICORN_DEFAULT_TRUSTED)


async def _echo_client(scope: Scope, receive: Receive, send: Send) -> None:
    """The address the app (and so the rate limiter) sees as the client."""
    client = scope.get("client")
    await PlainTextResponse(client[0] if client else "")(scope, receive, send)


async def _client_seen(peer: str, forwarded_for: str | None) -> str:
    app = ProxyHeadersMiddleware(_echo_client, trusted_hosts=image_trusted_hosts())
    headers = {"X-Forwarded-For": forwarded_for} if forwarded_for is not None else {}
    transport = httpx.ASGITransport(app=app, client=(peer, 40000))
    async with httpx.AsyncClient(transport=transport, base_url="http://backend:5000") as client:
        response = await client.get("/api/v1/auth/me", headers=headers)
    return response.text


async def test_a_public_peer_cannot_pick_its_own_address():
    """A direct hit from the internet carrying X-Forwarded-For keeps its real address."""
    # Act
    seen = await _client_seen(PUBLIC_PEER, CLIENT_WRITTEN)

    # Assert
    assert seen == PUBLIC_PEER


async def test_the_client_written_leftmost_entry_is_never_the_client():
    """Behind Traefik, the client is the first untrusted hop from the right: the Cloudflare edge.

    WP-17's limiter key then reads CF-Connecting-IP, and only from a Cloudflare peer.
    """
    # Act
    seen = await _client_seen(TRAEFIK_PEER, f"{CLIENT_WRITTEN}, {CLOUDFLARE_EDGE}")

    # Assert
    assert seen == CLOUDFLARE_EDGE


@pytest.mark.parametrize("leftmost", ["198.19.7.100", "198.19.7.101", "198.19.7.102"])
async def test_rotating_the_leftmost_entry_does_not_rotate_the_key(leftmost: str):
    """The probe's attack, inverted: a new left-most value per request keeps one key."""
    # Act
    seen = await _client_seen(TRAEFIK_PEER, f"{leftmost}, 203.0.113.250")

    # Assert
    assert seen == "203.0.113.250"


async def test_the_e2e_path_through_the_frontend_nginx_is_unchanged():
    """nginx on the stack's network forwards the browser's address; it is still the client."""
    # Act
    seen = await _client_seen(FRONTEND_NGINX_PEER, DOCKER_GATEWAY)

    # Assert
    assert seen == DOCKER_GATEWAY


async def test_the_container_healthcheck_is_its_own_client():
    """curl from inside the container: loopback, no header, nothing to rewrite."""
    # Act
    seen = await _client_seen("127.0.0.1", None)

    # Assert
    assert seen == "127.0.0.1"


def test_the_image_never_trusts_every_peer():
    """No `*` in the trust list, whatever the CMD or ENV spells it."""
    # Act
    trusted = [item.strip() for item in image_trusted_hosts().split(",")]

    # Assert
    assert "*" not in trusted
    assert trusted, "an empty list would fall back to uvicorn's 127.0.0.1 only"


def test_no_cloudflare_range_is_trusted_as_a_proxy():
    """A trusted Cloudflare edge would hand the left-most, client-written entry back as the client."""
    # Prepare
    trusted_networks = [ipaddress.ip_network(item.strip()) for item in image_trusted_hosts().split(",")]

    # Act
    overlaps = [
        (str(trusted), cloudflare)
        for trusted in trusted_networks
        for cloudflare in CLOUDFLARE_IP_RANGES
        if trusted.version == ipaddress.ip_network(cloudflare).version
        and trusted.overlaps(ipaddress.ip_network(cloudflare))
    ]

    # Assert
    assert overlaps == []


def test_uvicorn_is_pid_1_and_drains_on_sigterm():
    """`exec` makes uvicorn PID 1, so `docker stop`'s SIGTERM reaches it (INFRA-10, BDP-14).

    Two shells sat in front of it (shell-form CMD wrapping `sh -c`, neither exec'ing):
    SIGTERM never arrived, every stop waited out Docker's 10 s and ended in SIGKILL
    (exit 137), and the lifespan teardown never ran.
    """
    # Prepare
    cmd = _cmd(_production_stage())

    # Act
    command = _shell_command(cmd)

    # Assert
    assert cmd.startswith("["), "shell-form CMD wraps the command in a second /bin/sh"
    assert re.match(r"^exec\s+uvicorn\s", command), command
    assert "--timeout-graceful-shutdown" in command


def _container_env(compose_entries: dict[str, object], dokploy_env: dict[str, str]) -> dict[str, str]:
    """The backend container's environment: the image's ENV, then compose's ``environment:``.

    A key with no value (``KEY:``, YAML null) passes the variable through from the
    deploying shell, and when that shell does not set it the engine UNSETS it in the
    container — the image's ENV default goes too. A string is interpolated against the
    deploying environment (Dokploy's) the way compose does.
    """
    env = _env_defaults(_production_stage())
    for key, raw in compose_entries.items():
        if raw is None:
            if key in dokploy_env:
                env[key] = dokploy_env[key]
            else:
                env.pop(key, None)
        else:
            env[key] = _resolve(str(raw), dokploy_env)
    return env


def _backend_environment() -> dict[str, object]:
    services = yaml.safe_load(PRODUCTION_COMPOSE.read_text())["services"]
    return services["backend"].get("environment") or {}


def test_production_runs_the_images_trust_list_when_dokploy_sets_none():
    """Review INT-01: ``FORWARDED_ALLOW_IPS:`` with no value unset the variable in the container,
    the CMD passed ``--forwarded-allow-ips ""``, uvicorn trusted no proxy, and every anonymous
    per-IP limit (login, register, forgot-password) became ONE bucket keyed on Traefik."""
    # Prepare
    image_default = _env_defaults(_production_stage())["FORWARDED_ALLOW_IPS"]

    # Act
    trusted = image_trusted_hosts(_container_env(_backend_environment(), dokploy_env={}))

    # Assert
    assert trusted == image_default


def test_dokploy_can_still_set_the_trust_list():
    """The override path stays: a value set in Dokploy reaches uvicorn."""
    # Act
    trusted = image_trusted_hosts(
        _container_env(_backend_environment(), dokploy_env={"FORWARDED_ALLOW_IPS": "10.9.0.0/16"})
    )

    # Assert
    assert trusted == "10.9.0.0/16"


def test_an_empty_value_falls_back_to_the_default_list():
    """Whatever empties the variable, the CMD never hands uvicorn an empty list."""
    # Prepare
    image_default = _env_defaults(_production_stage())["FORWARDED_ALLOW_IPS"]

    # Act
    trusted = image_trusted_hosts({"FORWARDED_ALLOW_IPS": "", "UVICORN_WORKERS": "4"})

    # Assert
    assert trusted == image_default
