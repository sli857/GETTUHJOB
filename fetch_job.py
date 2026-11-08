"""Print the readable text of a job posting page, for AI tools without a web fetch tool (e.g. Codex).

Usage: python3 fetch_job.py <url> [max_chars]   (default 12000 characters)
"""
import html, re, sys, urllib.request

url = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 12000
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                                                        '(KHTML, like Gecko) Chrome/130.0 Safari/537.36'})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        page = r.read().decode(r.headers.get_content_charset() or 'utf-8', errors='replace')
except Exception as e:
    sys.exit(f'FETCH FAILED: {e}')
page = re.sub(r'(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>', ' ', page)
page = re.sub(r'(?i)<br\s*/?>|</(p|div|li|h\d|tr)>', '\n', page)
text = html.unescape(re.sub(r'<[^>]+>', ' ', page))
text = re.sub(r'[ \t\r\f\v]+', ' ', text)
text = re.sub(r'\n\s*\n+', '\n', text).strip()
if len(text) < 300:
    sys.exit('FETCH FAILED: page has almost no text (it may need a login or JavaScript)')
print(text[:limit])
