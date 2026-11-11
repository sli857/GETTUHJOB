"""Print a job posting's text: the description saved by rank_jobs.py if there is one, otherwise the live page.

Usage: python3 fetch_job.py <url> [max_chars] [--saved-only]   (default 12000 characters)
  --saved-only   print only a saved description; never fetch the page (use for Indeed, which blocks fetches)

rank_jobs.py saves the description of every job it keeps to search_results/jd/, so most jobs on a
ranked list need no fetch at all. The live fetch is for AI tools without a web fetch tool (e.g. Codex).
"""
import hashlib, html, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
JD_DIR = os.path.join(HERE, 'search_results', 'jd')
TAIL = 2500     # when cutting a long text, keep this much of the end: clearance and visa lines are often last


def jd_path(url):
    """Where rank_jobs.py saves the description for this job URL."""
    return os.path.join(JD_DIR, hashlib.sha1(url.strip().encode()).hexdigest()[:16] + '.txt')


def clip(text, limit):
    if len(text) <= limit:
        return text
    return text[:limit - TAIL] + '\n[... middle cut ...]\n' + text[-TAIL:]


def fetch(url):
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
    return text


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    saved_only = '--saved-only' in sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    url = args[0]
    limit = int(args[1]) if len(args) > 1 else 12000
    p = jd_path(url)
    if os.path.exists(p):
        print(clip(open(p, encoding='utf-8').read(), limit))
    elif saved_only:
        sys.exit('NO SAVED DESCRIPTION')
    else:
        print(clip(fetch(url), limit))


if __name__ == '__main__':
    main()
