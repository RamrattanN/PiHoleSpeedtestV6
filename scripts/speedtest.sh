    #!/usr/bin/env bash
    # v6 safe speedtest runner
    # Writes CSV and JSON into a data directory, default /etc/pihole/speedtest
    set -euo pipefail

    OUT_DIR=""
    BIN=""
    ONESHOT_INTERVAL=0

    usage() {
      cat <<'USAGE'
    Usage: speedtest.sh [options]
      -o, --out <dir>     Output directory for CSV and JSON.  Default: /etc/pihole/speedtest
      --bin <name>        CLI to run.  Default: speedtest
      --interval <sec>    If >0, loop forever with this sleep between runs.
      -h, --help          Help.
    USAGE
    }

    while [[ $# -gt 0 ]]; do
      case "$1" in
        -o|--out) OUT_DIR="${2:-}"; shift 2;;
        --bin) BIN="${2:-}"; shift 2;;
        --interval) ONESHOT_INTERVAL="${2:-0}"; shift 2;;
        -h|--help) usage; exit 0;;
        *) echo "Unknown option $1" >&2; usage; exit 2;;
      esac
    done

    # Load defaults if present
    if [[ -f /etc/default/pihole-speedtest ]]; then
      # shellcheck disable=SC1091
      . /etc/default/pihole-speedtest
    fi

    OUT_DIR="${OUT_DIR:-${SPEEDTEST_DATA_DIR:-/etc/pihole/speedtest}}"
    BIN="${BIN:-${SPEEDTEST_BIN:-speedtest}}"

    mkdir -p "$OUT_DIR"
    CSV="${OUT_DIR}/speedtest.csv"
    JSON="${OUT_DIR}/speedtest.json"

    require_cmd() { command -v "$1" >/dev/null 2>&1; }

    # Pick a working CLI
    PICKED=""
    try_bins=()
    if [[ -n "$BIN" ]]; then
      try_bins+=("$BIN")
    fi
    try_bins+=("speedtest" "librespeed-cli" "fast")
    for b in "${try_bins[@]}"; do
      if require_cmd "$b"; then
        PICKED="$b"
        break
      fi
    done

    if [[ -z "$PICKED" ]]; then
      echo "No speedtest CLI found.  Install ookla speedtest or librespeed-cli." >&2
      exit 5
    fi

    run_once() {
      local ts iso dl ul ping jitter server_id server_name iface
      ts="$(date +%s)"
      iso="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

      case "$PICKED" in
        speedtest)
          # Ookla CLI JSON
          out="$(speedtest --accept-license --accept-gdpr -f json || true)"
          ;;
        librespeed-cli)
          out="$(librespeed-cli --json || true)"
          ;;
        fast)
          out="$(fast --upload --json || true)"
          ;;
      esac

      if [[ -z "${out:-}" ]]; then
        echo "Speedtest failed to produce output." >&2
        return 1
      fi

      # Basic JSON extraction using awk and sed to avoid jq dependency
      # We will try to parse common fields.  If format is unknown, write raw blob.
      dl=""
      ul=""
      ping=""
      jitter=""
      server_name=""
      iface=""

      # Extract numeric Mbps like values first
      dl="$(printf "%s" "$out" | sed -n 's/.*"download"[[:space:]]*:[[:space:]]*{[^}]*"bandwidth"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)"
      ul="$(printf "%s" "$out" | sed -n 's/.*"upload"[[:space:]]*:[[:space:]]*{[^}]*"bandwidth"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)"
      ping="$(printf "%s" "$out" | sed -n 's/.*"ping"[[:space:]]*:[[:space:]]*{[^}]*"latency"[[:space:]]*:[[:space:]]*\([0-9.]\+\).*/\1/p' | head -n1)"
      jitter="$(printf "%s" "$out" | sed -n 's/.*"ping"[[:space:]]*:[[:space:]]*{[^}]*"jitter"[[:space:]]*:[[:space:]]*\([0-9.]\+\).*/\1/p' | head -n1)"
      server_name="$(printf "%s" "$out" | sed -n 's/.*"server"[[:space:]]*:[^{]*{[^}]*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
      iface="$(printf "%s" "$out" | sed -n 's/.*"interface"[[:space:]]*:[^{]*{[^}]*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"

      # Convert Ookla bandwidth bytes per second to Mbps if we got values
      to_mbps() {
        awk 'BEGIN{v='"'"$1"'"'; printf("%.2f", (v*8)/1000000)}'
      }
      if [[ -n "$dl" ]]; then dl="$(to_mbps "$dl")"; fi
      if [[ -n "$ul" ]]; then ul="$(to_mbps "$ul")"; fi

      # Append CSV header if missing
      if [[ ! -s "$CSV" ]]; then
        echo "timestamp,iso8601,download_mbps,upload_mbps,latency_ms,jitter_ms,server,interface" >> "$CSV"
      fi
      echo "${ts},${iso},${dl},${ul},${ping},${jitter},"${server_name}","${iface}"" >> "$CSV"

      # Update JSON summary with last run and small tail of records
      tail_json="$(tail -n 200 "$CSV" | awk -F',' 'NR>1{printf("{\"ts\":%s,\"iso\":\"%s\",\"dl\":%s,\"ul\":%s,\"lat\":%s,\"jit\":%s,\"srv\":%s,\"if\":%s},", $1,$2,$3,$4,$5,$6,$7,$8)}' | sed 's/,$//')"
      printf '{"last_run":"%s","records":[%s]}
' "$iso" "${tail_json:-}" > "$JSON"
      chmod 0644 "$CSV" "$JSON"
      echo "Recorded at ${iso} using ${PICKED}."
    }

    if [[ "${ONESHOT_INTERVAL}" -gt 0 ]]; then
      while true; do
        run_once || true
        sleep "${ONESHOT_INTERVAL}"
      done
    else
      run_once
    fi
