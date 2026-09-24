#!/usr/bin/env bash
# Legacy installer guard.  The v6 deployment path is not approved yet.
set -euo pipefail

cat >&2 <<'MESSAGE'
The legacy Pi-hole patch installer is disabled on this development branch.
It would modify the Pi-hole web installation before the v6 adapter has passed QA.
See DEPLOY.md and docs/QA-AND-ACCEPTANCE.md for the safe development path.
MESSAGE
exit 64
