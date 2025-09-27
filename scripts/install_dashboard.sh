#!/usr/bin/env bash
set -euo pipefail
ADMIN_ROOT="/var/www/html/admin"
SRC_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")"/.. >/dev/null 2>&1 && pwd)"
PAGE_SRC="${SRC_ROOT}/web"
DATA_JSON="/etc/pihole/speedtest/speedtest.json"

if [[ ! -d "${ADMIN_ROOT}" ]]; then
  echo "Admin root not found at ${ADMIN_ROOT}" >&2
  exit 1
fi

sudo mkdir -p "${ADMIN_ROOT}/speedtest"
sudo cp -f "${PAGE_SRC}/speedtest.html" "${ADMIN_ROOT}/speedtest/index.html"
sudo cp -f "${PAGE_SRC}/speedtest.js"   "${ADMIN_ROOT}/speedtest/speedtest.js"
sudo cp -f "${PAGE_SRC}/widget.js"      "${ADMIN_ROOT}/speedtest/widget.js"
sudo ln -sf "${DATA_JSON}" "${ADMIN_ROOT}/speedtest/speedtest.json"

INDEX_LP="${ADMIN_ROOT}/index.lp"
if ! sudo grep -q "speedtest/widget.js" "${INDEX_LP}"; then
  echo "Patching index.lp to include widget.js"
  sudo cp "${INDEX_LP}" "${INDEX_LP}.bak"
  sudo sed -i 's~</body>~<script src="/admin/speedtest/widget.js"></script>\n</body>~' "${INDEX_LP}"
else
  echo "index.lp already patched"
fi

SIDEBAR="${ADMIN_ROOT}/scripts/lua/sidebar.lp"
if ! sudo grep -q "/admin/speedtest/" "${SIDEBAR}"; then
  echo "Adding sidebar link"
  sudo cp "${SIDEBAR}" "${SIDEBAR}.bak"
  sudo awk '
    /menu-icon fa-home/ && !done {
      print;
      print "            <li><a href=\"/admin/speedtest/\"><i class=\"fa fa-fw menu-icon fa-line-chart\"></i> <span>Speedtest</span></a></li>";
      done=1; next
    } { print }
  ' "${SIDEBAR}" | sudo tee "${SIDEBAR}.new" >/dev/null
  sudo mv "${SIDEBAR}.new" "${SIDEBAR}"
else
  echo "Sidebar already has link"
fi

echo "Installed page and widget into Admin.  Visit /admin and /admin/speedtest/"
