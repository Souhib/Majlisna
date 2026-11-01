#!/usr/bin/env bash
# Majlisna's CI runner on the owner's home server (lgf: x86_64, 12 cores, 62 GB, Ubuntu
# 24.04). Same model as Majlisna's VPS runner and LaTabdhir's home runner
# (Souhib/LaTabdhir, infrastructure/home-ci): a dedicated unprivileged account, its own
# rootless Docker, a root-owned egress boundary, a systemd budget. It touches nothing of
# the other runners on this host (LaTabdhir's, Souverain's): its own account, firewall
# chain, units and env file. Idempotent. Run as root: sudo bash setup.sh
set -euo pipefail
umask 022
U=ci-majlisna
H=/var/lib/$U
HERE=$(cd "$(dirname "$0")" && pwd)
# A range no other account of this host uses (/etc/subuid ended at 427679 on 2026-11-02).
SUBIDS=500000-565535

apt-get install -y -qq uidmap iptables >/dev/null

if ! id "$U" >/dev/null 2>&1; then
  useradd --create-home --home-dir "$H" --shell /bin/bash --user-group "$U"
fi
passwd -l "$U" >/dev/null
chmod 700 "$H"
grep -q "^$U:" /etc/subuid || usermod --add-subuids "$SUBIDS" "$U"
grep -q "^$U:" /etc/subgid || usermod --add-subgids "$SUBIDS" "$U"
CI_UID=$(id -u "$U")

# Egress boundary for this account only: the home network, the tailnet, link-local,
# multicast and loopback are refused, except the resolver and the e2e stack's own
# published ports. The host's global IPv6 /64s are read at each run (the ISP prefix
# changes: LaTabdhir's script still names an old one).
install -m 755 "$HERE/majlisna-ci-egress" /usr/local/sbin/majlisna-ci-egress
cat > /etc/systemd/system/majlisna-ci-egress.service <<'EOF'
[Unit]
Description=Restrict the Majlisna CI account from the home network
After=network-online.target
Wants=network-online.target
Before=majlisna-ci-runner.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/majlisna-ci-egress
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# The whole user manager (rootless dockerd and its containers) cannot see /home, the NAS
# or the media trees, nor the rootful Docker, and starts only after the firewall. Not
# ProtectHome=: it also masks /run/user, the account's bus and docker.sock.
mkdir -p "/etc/systemd/system/user@${CI_UID}.service.d"
cat > "/etc/systemd/system/user@${CI_UID}.service.d/ci-boundary.conf" <<'EOF'
[Unit]
Requires=majlisna-ci-egress.service
After=majlisna-ci-egress.service

[Service]
InaccessiblePaths=-/home -/root -/mnt/nas -/media -/srv -/var/lib/docker -/var/run/docker.sock
EOF
# Budget: 8 of the 12 cores and 16 GiB, so LaTabdhir's runner (10 cores, 24 GiB) and the
# owner's services still get their share when both CIs run at once.
mkdir -p "/etc/systemd/system/user-${CI_UID}.slice.d"
cat > "/etc/systemd/system/user-${CI_UID}.slice.d/ci-budget.conf" <<'EOF'
[Slice]
CPUQuota=800%
MemoryMax=16G
TasksMax=4096
EOF

systemctl daemon-reload
systemctl enable --now majlisna-ci-egress.service
loginctl enable-linger "$U"
systemctl restart "user@${CI_UID}.service"
for _ in $(seq 1 20); do [ -S "/run/user/$CI_UID/bus" ] && break; sleep 1; done

# Rootless Docker, installed inside the account's own user manager (a `sudo -u` has no
# user bus, which cost LaTabdhir a second script).
install -d -o "$U" -g "$U" -m 700 "$H/.config" "$H/.config/docker"
printf '{ "dns": ["1.1.1.1", "9.9.9.9"] }\n' > "$H/.config/docker/daemon.json"
chown "$U:$U" "$H/.config/docker/daemon.json"
systemd-run --user -M "$U@" --wait --pipe --quiet /usr/bin/dockerd-rootless-setuptool.sh install --force >/dev/null
systemctl --user -M "$U@" daemon-reload
systemctl --user -M "$U@" enable --now docker.service
for _ in $(seq 1 30); do [ -S "/run/user/$CI_UID/docker.sock" ] && break; sleep 1; done
sudo -u "$U" env DOCKER_HOST="unix:///run/user/$CI_UID/docker.sock" docker info --format 'rootless docker {{.ServerVersion}} {{.SecurityOptions}}'

# The runner's environment and unit (the unit is filled with this account's uid).
install -d -m 755 /etc/majlisna-ci
printf 'DOCKER_HOST=unix:///run/user/%s/docker.sock\nXDG_RUNTIME_DIR=/run/user/%s\n' "$CI_UID" "$CI_UID" > /etc/majlisna-ci/runner.env
chmod 600 /etc/majlisna-ci/runner.env
sed -e "s#@CI_UID@#$CI_UID#g" "$HERE/majlisna-ci-runner.service" > /etc/systemd/system/majlisna-ci-runner.service
systemctl daemon-reload
echo "SETUP_OK uid=$CI_UID"
