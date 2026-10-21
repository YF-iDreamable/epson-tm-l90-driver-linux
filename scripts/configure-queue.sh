#!/bin/sh
set -eu
if [ "$#" -lt 2 ] || [ "$#" -gt 4 ]; then
    echo "Usage: $0 QUEUE PRINTER_HOST [Custom.50x25mm] [None|Page|Job]" >&2
    exit 2
fi
queue=$1
host=$2
media=${3:-Custom.50x25mm}
cut=${4:-None}
case "$queue" in ''|*[!A-Za-z0-9_-]*) echo 'Use letters, digits, _ or - in queue names' >&2; exit 2;; esac
case "$host" in ''|*[!A-Za-z0-9.-]*) echo 'Use an IPv4 address or DNS hostname (no URI)' >&2; exit 2;; esac
case "$cut" in None|Page|Job) ;; *) echo 'Cut must be None, Page, or Job' >&2; exit 2;; esac
python3 - "$media" <<'PY'
import re, sys
m = re.fullmatch(r'Custom\.([0-9]+(?:\.[0-9]+)?)x([0-9]+(?:\.[0-9]+)?)mm', sys.argv[1])
if not m or not (38 <= float(m[1]) <= 78 and 15 <= float(m[2]) <= 300):
    sys.exit('Media must be Custom.WxHmm, width 38..78 mm, length 15..300 mm')
PY
case "$(cups-config --version)" in 2.*) ;; *) echo 'Requires CUPS 2.x with PPD support' >&2; exit 2;; esac
if lpstat -p "$queue" >/dev/null 2>&1; then
    echo "Queue $queue already exists; inspect and modify it explicitly with lpadmin" >&2
    exit 2
fi
ppd="$(cups-config --datadir)/model/cloverhelper/epson-tm-l90.ppd"
test -r "$ppd"
test -x "$(cups-config --serverbin)/filter/rastertotml90"
lpadmin -p "$queue" -E -v "socket://$host:9100/?contimeout=10" -P "$ppd" \
    -o printer-is-shared=false -o printer-error-policy=stop-printer \
    -o media-default="$media" -o MediaType=DieCut -o TML90Cut="$cut" \
    -o job-sheets-default=none,none
echo "Created $queue for calibrated die-cut media $media; cutting: $cut."
echo 'No job was printed. Validate layout, interface, and cutting on hardware before production.'
