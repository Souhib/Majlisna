#!/usr/bin/env bash
# Install the GitHub Actions runner for ci-majlisna (checksum verified), register it on
# Souhib/Majlisna as ci-majlisna-home (labels isolated-rootless,home-x64), start it.
# Run as root after setup.sh. The registration token comes through the environment,
# never a command-line argument:
#   gh api -X POST repos/Souhib/Majlisna/actions/runners/registration-token --jq .token \
#     | ssh souhib@192.168.1.33 'sudo bash -c "RUNNER_TOKEN=\$(cat) bash ~/majlisna-ci/register.sh"'
set -euo pipefail
U=ci-majlisna
H=/var/lib/$U
: "${RUNNER_TOKEN:?set RUNNER_TOKEN (gh api -X POST repos/Souhib/Majlisna/actions/runners/registration-token --jq .token)}"

rel=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest)
read -r url digest < <(python3 -c '
import json,sys
a=[x for x in json.load(sys.stdin)["assets"] if x["name"].startswith("actions-runner-linux-x64-") and x["name"].endswith(".tar.gz")][0]
print(a["browser_download_url"], a["digest"].split(":",1)[1])' <<<"$rel")
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/runner.tgz" "$url"
echo "$digest  $tmp/runner.tgz" | sha256sum -c -
install -d -o "$U" -g "$U" -m 700 "$H/runner"
sudo -u "$U" tar -xz -C "$H/runner" < "$tmp/runner.tgz"
"$H/runner/bin/installdependencies.sh" >/dev/null
sudo -u "$U" install -m 700 "$H/runner/bin/runsvc.sh" "$H/runner/runsvc.sh"
sudo -u "$U" env ACTIONS_RUNNER_INPUT_TOKEN="$RUNNER_TOKEN" bash -c "cd $H/runner && ./config.sh --unattended \
  --url https://github.com/Souhib/Majlisna --name ci-majlisna-home \
  --labels isolated-rootless,home-x64 --work _work --replace >/dev/null"
systemctl enable --now majlisna-ci-runner.service
systemctl --no-pager --lines=3 status majlisna-ci-runner.service | head -5
echo "REGISTER_OK $(basename "$url") sha256 verified"
