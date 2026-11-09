#!/bin/zsh
# Usage: resumes/render.sh <resume.html> [out.pdf]
# Prints the HTML to a Letter PDF with headless Chrome, then reports:
#   pages=N   (must be 1)
#   fill=0.NN (share of the page height used by content; aim for 0.95-0.99)
#   warning=  (only when fill is over 1.00)
# The page hides overflow, so pages is always 1 and only fill shows cut-off content.
set -e
HTML="${1:A}"
OUT="${2:-${HTML:r}.pdf}"
# Google Chrome or Chromium. Set CHROME=/path/to/chrome to use another one.
if [[ -z "$CHROME" ]]; then
  for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
           "/Applications/Chromium.app/Contents/MacOS/Chromium" \
           "$(command -v google-chrome || true)" "$(command -v chromium || true)" "$(command -v chromium-browser || true)"; do
    [[ -n "$c" && -x "$c" ]] && CHROME="$c" && break
  done
fi
if [[ -z "$CHROME" ]]; then
  echo "error=Google Chrome not found. Install it, or set CHROME=/path/to/chrome." >&2
  exit 1
fi
TMP=$(mktemp -d)
"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer --user-data-dir="$TMP" \
  --print-to-pdf="$OUT" "file://$HTML" >/dev/null 2>&1
# Measure content height. The page must have <main id="page"> sized to 8.5in x 11in.
FILL=$("$CHROME" --headless=new --disable-gpu --user-data-dir="$TMP" --virtual-time-budget=2000 \
  --window-size=816,1056 --dump-dom "file://$HTML" 2>/dev/null | grep -o 'data-fill="[0-9.]*"' | head -1 | grep -o '[0-9.]*')
PAGES=$(LC_ALL=C grep -a -o '/Count [0-9]*' "$OUT" | head -1 | grep -o '[0-9]*' || true)
rm -rf "$TMP"
echo "pdf=$OUT"
echo "pages=$PAGES"
echo "fill=${FILL:-unknown}"
if [[ -n "$FILL" ]] && (( FILL > 1.0 )); then
  echo "warning=content is cut off at the bottom (fill over 1.00). Trim it."
fi
