#!/usr/bin/env bash
set -euo pipefail

label="com.my-virtual-office.8090"
domain="gui/$(id -u)"
health_url="http://127.0.0.1:8090/health"
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if launchctl print "${domain}/${label}" >/dev/null 2>&1; then
  launchctl kickstart -k "${domain}/${label}"
else
  launchctl submit -l "$label" \
    -o /private/tmp/my-virtual-office-8090.log \
    -e /private/tmp/my-virtual-office-8090.err \
    -- /usr/bin/env \
    "HOME=$HOME" \
    "PATH=/Users/bytedance/.nvm/versions/node/v20.20.2/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    /bin/bash "$repo_dir/start.sh"
fi

for _ in $(seq 1 45); do
  if curl -fsS "$health_url" >/dev/null 2>&1; then
    printf '8090 service restarted and healthy\n'
    exit 0
  fi
  sleep 1
done

printf '8090 service did not become healthy\n' >&2
exit 1
