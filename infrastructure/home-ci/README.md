# Majlisna's CI runner on the owner's home server (2 November 2026)

Owner decision: run Majlisna's E2E job on the home server `lgf` (192.168.1.33, x86_64,
12 cores, 62 GB, Ubuntu 24.04), which LaTabdhir already uses (Souhib/LaTabdhir,
`infrastructure/home-ci`: 42 min of CI on the VPS against 14 on this machine). On the VPS
the E2E job ran 41 to 44 min on one core.

Runner `ci-majlisna-home`, labels `isolated-rootless,home-x64`, registered on
`Souhib/Majlisna` only. Same model as the VPS runner (`ci-majlisna`, ARM64) and LaTabdhir's:

- **Account** `ci-majlisna` (uid 1005 on lgf), locked password, no sudo, not in `docker`,
  its own rootless Docker (`/run/user/1005/docker.sock`, subuids 500000-565535).
- **Network** (`/usr/local/sbin/majlisna-ci-egress`, run by `majlisna-ci-egress.service`
  before the account's user manager): one chain on OUTPUT for that uid; RFC 1918, the
  tailnet (100.64/10, fc00::/7), link-local, multicast, loopback and the host's own IPv6
  /64s are refused (the /64s are read when the service runs: the ISP prefix changes),
  except the resolver and the e2e stack's published ports 3049, 5049, 54339. Public
  internet stays open (GitHub, registries).
- **Files**: the user manager (rootless dockerd and its containers) cannot see `/home`,
  `/root`, `/mnt/nas`, `/media`, `/srv` or the rootful Docker; the runner unit adds
  `ProtectSystem=strict`, `ProtectHome=tmpfs` (its own docker.sock bound back),
  `NoNewPrivileges`, and writes only to `/var/lib/ci-majlisna`.
- **Budget**: `user-1005.slice` 800 % CPU, 16 GiB, 4096 tasks, so LaTabdhir's runner
  (1000 %, 24 GiB) and the owner's services keep their share when both CIs run at once.
- It touches nothing of the other runners on the host (LaTabdhir's `ci-runner@latabdhir`,
  Souverain's): its own account, chain, units (`majlisna-ci-egress.service`,
  `majlisna-ci-runner.service`) and env file (`/etc/majlisna-ci/runner.env`).

Verified on 2 November from inside the account's user manager: `sudo` asks for a password
(there is none); `/home` and the rootful docker.sock refused; `api.github.com` 200; the
router, the host's SSH (127.0.0.1:22) and the tailnet refused; from a container, the LAN
refused and GitHub reachable. Runner 2.338.2 (SHA-256 checked against GitHub's digest)
online.

## Install (as root on the host)

Copy this folder to the host, then:

```bash
sudo bash setup.sh            # account, egress, boundary, budget, rootless Docker, units
gh api -X POST repos/Souhib/Majlisna/actions/runners/registration-token --jq .token \
  | ssh souhib@192.168.1.33 'sudo bash -c "RUNNER_TOKEN=\$(cat) bash ~/majlisna-ci/register.sh"'
```

`setup.sh` is idempotent. `installdependencies.sh` reports `Unable to locate package
libicu75` on Ubuntu 24.04: harmless (libicu74 is installed), as on LaTabdhir's runner.

## Routing

GitHub hands a job to the first idle runner with the labels, and both runners carry
`isolated-rootless`. The E2E job reads the repository variable `E2E_RUNS_ON`:

- `["self-hosted","home-x64"]` (set 2 November 2026): the home server;
- deleted (`gh variable delete E2E_RUNS_ON --repo Souhib/Majlisna`): either runner.

When the home server is down (it dropped off its LAN for ~2 h once, LaTabdhir's README),
delete the variable or the job waits for it.

## Limits

- A persistent runner on a shared kernel, for this owner-only repository: not a sandbox
  for untrusted code. Keep fork workflow approval on.
- The e2e stack publishes 127.0.0.1:3049 and :5049: a developer gate run on this host as
  another user (`./run-local.sh`) at the same time as a CI job makes one of them fail to
  bind. Run manual gates elsewhere, or when no CI job is running.
