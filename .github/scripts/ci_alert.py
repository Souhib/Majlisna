"""GitHub CI results on main → Discord (majlisna-deployments); trusted default-branch code only.

Ported from LaTabdhir (infrastructure/discord-monitoring/ci_alert.py). A failed run alerts;
the next success (a re-run attempt included) reports the recovery; routine green runs are
quiet. A cancelled run stays quiet too: Majlisna's CI diffs each push against `production`
(paths-filter `base: production`), so the next run re-tests what a cancelled one skipped.
The webhook comes from the DISCORD_CI_WEBHOOK secret and is never logged.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FAILURES = {"failure", "timed_out", "action_required", "startup_failure"}
# Keep in sync with `workflows:` in .github/workflows/discord-ci.yml.
WORKFLOWS = {"CI"}
REPOSITORY = "Souhib/Majlisna"
USER_AGENT = "Majlisna-CI-monitor"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def github(path: str) -> dict:
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPOSITORY + path,
        headers={
            "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
        return json.load(response)


def eligible(run: dict) -> bool:
    return (
        run.get("head_repository", {}).get("full_name") == REPOSITORY
        and run.get("head_branch") == "main"
        and run.get("event") in {"push", "schedule", "workflow_dispatch"}
        and run.get("name") in WORKFLOWS
        and run.get("status") == "completed"
    )


def previous_conclusion(run: dict) -> str | None:
    # A re-run keeps its ID: compare its previous attempt before older runs.
    attempt = int(run.get("run_attempt", 1))
    if attempt > 1:
        previous = github(f"/actions/runs/{int(run['id'])}/attempts/{attempt - 1}")
        if previous.get("conclusion") in FAILURES | {"success"}:
            return previous["conclusion"]
    for page in range(1, 6):
        result = github(f"/actions/workflows/{int(run['workflow_id'])}/runs?branch=main&per_page=100&page={page}")
        for previous in result["workflow_runs"]:
            if (
                int(previous["id"]) < int(run["id"])
                and eligible(previous)
                and previous.get("conclusion") in FAILURES | {"success"}
            ):
                return previous["conclusion"]
        if len(result["workflow_runs"]) < 100:
            break
    return None


def payload(run: dict, previous: str | None, *, test: bool = False) -> dict | None:
    if not eligible(run):
        return None
    status = run.get("conclusion")
    failed = status in FAILURES
    recovered = status == "success" and previous in FAILURES
    if not failed and not recovered and not test:
        return None
    if status not in FAILURES | {"success"}:
        return None
    sha = run["head_sha"]
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("Invalid commit SHA")
    title = "🔴 CI en échec" if failed else "🟢 CI rétablie" if recovered else "🧪 Test de livraison CI"
    description = (
        "Consulter le premier job en échec et ses journaux : rien n'est déployé tant que la CI n'est pas verte. "
        if failed
        else "Ce workflow a terminé avec succès. "
    )
    if test:
        title = "[TEST — résultat historique] " + title
    run_id = int(run["id"])
    return {
        "username": "Majlisna · CI",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": title + " — " + run["name"],
                "description": description
                + "La CI ne confirme pas le déploiement : Dokploy le signale dans server-deployments.",
                "url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}/attempts/{int(run.get('run_attempt', 1))}",
                "color": 15158332 if failed else 3066993,
                "fields": [
                    {"name": "Périmètre", "value": "Majlisna · branche main · CI (suites, E2E, promotion)"},
                    {"name": "Commit", "value": f"[{sha[:8]}](https://github.com/{REPOSITORY}/commit/{sha})"},
                    {"name": "Résultat GitHub", "value": str(status)},
                ],
            }
        ],
    }


def send(webhook: str, message: dict) -> None:
    parsed = urllib.parse.urlsplit(webhook)
    if parsed.scheme != "https" or parsed.netloc != "discord.com" or not parsed.path.startswith("/api/webhooks/"):
        raise ValueError("Invalid Discord destination")
    request = urllib.request.Request(
        webhook,
        data=json.dumps(message).encode(),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=10):
                return
        except urllib.error.HTTPError as exc:
            with exc:
                if exc.code != 429 or attempt == 2:
                    raise RuntimeError("Discord delivery rejected") from None
                delay = float(json.load(exc)["retry_after"])
                if not 0 <= delay <= 10:
                    raise RuntimeError("Invalid Discord retry delay") from None
                time.sleep(delay)
    raise RuntimeError("Discord delivery failed")


def main() -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    test = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if test:
        run_id = str(event.get("inputs", {}).get("run_id", ""))
        if not run_id.isdecimal():
            raise ValueError("A real completed run ID is required")
        run = github("/actions/runs/" + run_id)
    else:
        run = event["workflow_run"]
    if not eligible(run):
        print("Run outside monitoring scope; nothing sent.")
        return
    previous = previous_conclusion(run) if run["conclusion"] == "success" and not test else None
    message = payload(run, previous, test=test)
    if message:
        send(os.environ["DISCORD_CI_WEBHOOK"], message)
        print("Discord accepted the CI notification.")
    else:
        print("No failure/recovery transition; nothing sent.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Network exceptions can carry the full webhook URL. Never log them.
        print("CI notification failed: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1) from None
