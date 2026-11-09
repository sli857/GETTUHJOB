"""Local dashboard: review and edit your profile and settings, and browse jobs, applications, resumes and searches.

Usage:
  python3 dashboard.py                 # opens http://127.0.0.1:8765 in your browser
  python3 dashboard.py --no-browser --port 8800 --root <project folder>

It runs only on this computer and needs nothing beyond Python 3.9+. It edits only these files:
  profile/about_me.md, profile/rank_config.json, profile/search_plan.json, profile/search_notes.md
Job lists, applications.csv, resumes and tailored resumes are read-only here. It never reads or shows .env;
the Apify credit check goes through apify.py, so the token stays on this computer. Stop it with Ctrl-C.
"""
import argparse, csv, glob, hashlib, importlib.util, json, mimetypes, os, re, subprocess, sys, tempfile, webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, 'dashboard')
ROOT = HERE          # project folder; --root changes it (for testing on a copy)
PORT = 8765

# The only files the dashboard may write.
ABOUT, CONFIG, PLAN, NOTES = 'profile/about_me.md', 'profile/rank_config.json', 'profile/search_plan.json', 'profile/search_notes.md'
WRITABLE = {ABOUT, CONFIG, PLAN, NOTES}
SERVED_DIRS = ('resumes', 'tailored')   # read-only, under /files/
BUDGET_RE = re.compile(r'(?im)^([ \t]*(?:[-*][ \t]+)?\**Budget per search:\**[ \t]*)\$?[ \t]*([0-9]+(?:\.[0-9]+)?)')
WA_STATUSES = ('us_citizen', 'green_card', 'f1_opt', 'needs_sponsorship')


class Refused(Exception):
    """A request the dashboard refuses, with a message for the page."""
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


# ---------- files ----------
def path(rel):
    return os.path.join(ROOT, rel)


def read(rel):
    try:
        with open(path(rel), encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return None


def version(text):
    return hashlib.sha1((text or '').encode()).hexdigest()[:12]


def check_version(rel, sent):
    if sent is not None and sent != version(read(rel)):
        raise Refused(f'{rel} changed on disk since you opened it (maybe Claude edited it). Reload to see the new version.', 409)


def write(rel, text):
    if rel not in WRITABLE:  # never write anything else
        raise Refused(f'{rel} is read-only in the dashboard.', 403)
    full = path(rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(full), prefix='.dashboard-', suffix='.tmp')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, full)


def dump(obj):
    return json.dumps(obj, indent=1, ensure_ascii=False)


def keep_types(new, old):
    """The page sends 1.0 back as 1 (JavaScript has one number type). Turn ints back into floats where the
    file had a float, so saving doesn't rewrite "1.0" as "1"."""
    if isinstance(new, dict) and isinstance(old, dict):
        return {k: keep_types(v, old.get(k)) for k, v in new.items()}
    if isinstance(new, list) and isinstance(old, list):
        return [keep_types(v, old[i] if i < len(old) else None) for i, v in enumerate(new)]
    if isinstance(old, float) and isinstance(new, int) and not isinstance(new, bool):
        return float(new)
    return new


def load_json(rel):
    text = read(rel)
    if text is None:
        return None, None
    try:
        return json.loads(text), text
    except ValueError as e:
        return None, text  # the raw editor can still fix it


def read_csv(rel):
    full = path(rel)
    if not os.path.exists(full):
        return [], []
    with open(full, newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        cols = r.fieldnames or []
        rows = [{c: (row.get(c) or '') for c in cols} for row in r]  # old rows can be shorter
    return cols, rows


# ---------- profile/about_me.md ----------
def split_sections(text):
    parts = re.split(r'(?m)^## ', text)
    out = []
    for p in parts[1:]:
        title, _, body = p.partition('\n')
        out.append(dict(title=title.strip(), body=body.strip('\n')))
    return parts[0], parts[1:], out


def get_profile():
    text = read(ABOUT)
    if text is None:
        return dict(exists=False, sections=[], raw='', version=version(None))
    _, _, sections = split_sections(text)
    return dict(exists=True, sections=sections, raw=text, version=version(text))


def put_profile(d):
    check_version(ABOUT, d.get('version'))
    old = read(ABOUT) or ''
    if 'raw' in d:
        new = d['raw']
        if not new.strip():
            raise Refused('The file would be empty.')
    else:
        head, parts, sections = split_sections(old)
        sent = d.get('sections') or []
        if [s.get('title') for s in sent] != [s['title'] for s in sections]:
            raise Refused('The sections changed on disk. Reload, or use "Edit whole file".', 409)
        new = head
        for part, orig, s in zip(parts, sections, sent):
            body = str(s.get('body', '')).replace('\r\n', '\n').strip('\n')
            if body == orig['body']:
                new += '## ' + part  # untouched: keep it byte for byte
                continue
            title_line, _, old_body = part.partition('\n')
            lead = old_body[:len(old_body) - len(old_body.lstrip('\n'))]
            trail = old_body[len(old_body.rstrip('\n')):] or '\n'
            new += '## ' + title_line + '\n' + lead + body + trail
    if new == old:
        return dict(ok=True, message='No changes.', **get_profile())
    write(ABOUT, new)
    return dict(ok=True, message='Saved profile/about_me.md.', **get_profile())


# ---------- profile/rank_config.json ----------
def get_config():
    cfg, text = load_json(CONFIG)
    return dict(exists=text is not None, config=cfg, raw=text or '', version=version(text),
                error=None if cfg is not None or text is None else 'rank_config.json is not valid JSON. Fix it in the raw editor.')


def is_num(x, allow_none=False):
    return (x is None and allow_none) or (isinstance(x, (int, float)) and not isinstance(x, bool))


def check_config(cfg):
    errs = []
    if not isinstance(cfg, dict):
        return ['The config must be a JSON object.']
    if not is_num(cfg.get('min_fit', 16)):
        errs.append('min_fit must be a number.')
    if not is_num(cfg.get('min_salary'), allow_none=True):
        errs.append('min_salary must be a number or null.')
    if not is_num(cfg.get('top_n_per_site'), allow_none=True):
        errs.append('top_n_per_site must be a number or null.')
    s = cfg.get('seniority') or {}
    if not is_num(s.get('max_years'), allow_none=True):
        errs.append('seniority.max_years must be a number or null.')
    for k, v in (s.get('years_bonus') or {}).items():
        if not str(k).isdigit() or not is_num(v):
            errs.append(f'seniority.years_bonus: "{k}" needs a whole number of years and a number of points.')
    for name, sk in (cfg.get('skills') or {}).items():
        if not isinstance(sk, dict) or not sk.get('pattern') or not is_num(sk.get('weight', 1)):
            errs.append(f'skill "{name}" needs a pattern and a numeric weight.')
    for t in (cfg.get('locations') or {}).get('tiers') or []:
        if not isinstance(t, dict) or not is_num(t.get('tier')) or not t.get('name'):
            errs.append('each location tier needs a tier number and a name.')
    for k in ('remote', 'other'):
        v = (cfg.get('locations') or {}).get(k)
        if v is not None and (not isinstance(v, dict) or not is_num(v.get('tier')) or not v.get('name')):
            errs.append(f'locations.{k} must be null or have a tier number and a name.')
    for site, h in (cfg.get('max_age_hours') or {}).items():
        if not is_num(h):
            errs.append(f'max_age_hours.{site} must be a number.')
    if (cfg.get('work_authorization') or {}).get('status', 'us_citizen') not in WA_STATUSES:
        errs.append('work_authorization.status must be one of: ' + ', '.join(WA_STATUSES) + '.')
    return errs


def run_rank_check(text):
    fd, tmp = tempfile.mkstemp(suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
        r = subprocess.run([sys.executable, path('rank_jobs.py'), '--check', '--config', tmp],
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    finally:
        os.remove(tmp)


def put_config(d):
    check_version(CONFIG, d.get('version'))
    old_text = read(CONFIG)
    if 'raw' in d:
        text = d['raw']
        try:
            cfg = json.loads(text)
        except ValueError as e:
            raise Refused(f'Not valid JSON: {e}')
    else:
        cfg = d.get('config')
        try:
            old_cfg = json.loads(old_text) if old_text is not None else None
        except ValueError:
            old_cfg = None
        if old_cfg is not None and old_cfg == cfg:
            return dict(ok=True, message='No changes.', **get_config())
        cfg = keep_types(cfg, old_cfg)
        text = dump(cfg)
    if text == old_text:
        return dict(ok=True, message='No changes.', **get_config())
    errs = check_config(cfg)
    if errs:
        raise Refused(' '.join(errs))
    ok, msg = run_rank_check(text)
    if not ok:
        raise Refused('rank_jobs.py --check found problems: ' + msg)
    write(CONFIG, text)
    return dict(ok=True, message='Saved profile/rank_config.json. ' + msg, **get_config())


# ---------- profile/search_plan.json + budget in search_notes.md ----------
def get_budget():
    m = BUDGET_RE.search(read(NOTES) or '')
    return float(m.group(2)) if m else None


def get_plan():
    plan, text = load_json(PLAN)
    notes = read(NOTES)
    return dict(exists=text is not None, plan=plan, raw=text or '', budget=get_budget(), version=version(text),
                notes_version=version(notes), notes_exists=notes is not None,
                error=None if plan is not None or text is None else 'search_plan.json is not valid JSON. Fix it in the raw editor.')


def check_plan(plan):
    runs = plan.get('runs') if isinstance(plan, dict) else plan
    if not isinstance(runs, list):
        return ['The plan needs a "runs" list.']
    errs = []
    for i, r in enumerate(runs, 1):
        where = f'Run {i} ({r.get("site", "?")})' if isinstance(r, dict) else f'Run {i}'
        if not isinstance(r, dict):
            errs.append(f'{where} must be an object.'); continue
        for k in ('site', 'parser', 'actor'):
            if not isinstance(r.get(k), str) or not r[k].strip():
                errs.append(f'{where}: "{k}" is missing.')
        if isinstance(r.get('actor'), str) and '/' not in r['actor']:
            errs.append(f'{where}: "actor" must look like user/name.')
        if not is_num(r.get('max_charge_usd')) or r['max_charge_usd'] <= 0:
            errs.append(f'{where}: the cap (max_charge_usd) must be a number above 0.')
        if 'min_charge_usd' in r and (not is_num(r['min_charge_usd']) or r['min_charge_usd'] <= 0):
            errs.append(f'{where}: min_charge_usd must be a number above 0.')
        if 'enabled' in r and not isinstance(r['enabled'], bool):
            errs.append(f'{where}: "enabled" must be true or false.')
        if not isinstance(r.get('input'), dict):
            errs.append(f'{where}: "input" must be a JSON object.')
    return errs


def put_plan(d):
    check_version(PLAN, d.get('version'))
    check_version(NOTES, d.get('notes_version'))
    old_text, msgs = read(PLAN), []
    if 'raw' in d:
        text = d['raw']
        try:
            plan = json.loads(text)
        except ValueError as e:
            raise Refused(f'Not valid JSON: {e}')
    else:
        plan = d.get('plan')
        try:
            old_plan = json.loads(old_text) if old_text is not None else None
        except ValueError:
            old_plan = None
        if old_plan is not None and old_plan == plan:
            text = old_text
        else:
            plan = keep_types(plan, old_plan)
            text = dump(plan)
    errs = check_plan(plan)
    budget = d.get('budget', get_budget())
    if budget is not None and (not is_num(budget) or budget <= 0):
        errs.append('The budget must be a number above 0.')
    if errs:
        raise Refused(' '.join(errs))
    if text != old_text:
        write(PLAN, text)
        msgs.append('Saved profile/search_plan.json.')
    if budget is not None and budget != get_budget():
        notes = read(NOTES)
        line = f'${budget:.2f}'
        if notes is None:
            notes = f'# Search notes\n\nBudget per search: {line}\n'
        elif BUDGET_RE.search(notes):
            notes = BUDGET_RE.sub(lambda m: m.group(1) + line, notes, count=1)
        else:
            notes = notes.rstrip('\n') + f'\n\nBudget per search: {line}\n'
        write(NOTES, notes)
        msgs.append(f'Budget set to {line} in profile/search_notes.md.')
    return dict(ok=True, message=' '.join(msgs) or 'No changes.', **get_plan())


# ---------- read-only views ----------
def handled_by_url():
    _, rows = read_csv('applications.csv')
    return {r['url'].strip(): r['decision'] for r in rows if r.get('url')}


def list_job_files():
    files = [os.path.basename(f) for f in glob.glob(path('search_results/top_jobs_*.csv'))]
    return sorted(files, reverse=True)


def get_jobs(q):
    files = list_job_files()
    name = (q.get('file') or [files[0] if files else ''])[0]
    if name and name not in files:
        raise Refused('No such job list.', 404)
    cols, rows = read_csv('search_results/' + name) if name else ([], [])
    done = handled_by_url()
    for r in rows:
        r['handled'] = done.get((r.get('url') or '').strip(), '')
    return dict(files=files, file=name, columns=cols, rows=rows)


def get_applications():
    cols, rows = read_csv('applications.csv')
    for r in rows:
        f = r.get('resume_file') or ''
        r['resume_exists'] = bool(f) and os.path.isfile(path(f)) and f.split('/')[0] in SERVED_DIRS
    return dict(columns=cols, rows=rows)


def get_resumes():
    _, apps = read_csv('applications.csv')
    by_file = {os.path.basename(r['resume_file']): r for r in apps if r.get('resume_file')}
    items = []
    for f in sorted(glob.glob(path('tailored/*.pdf'))):
        name = os.path.basename(f)
        m = re.search(r'-resume-(.+)\.pdf$', name)
        app = by_file.get(name)
        items.append(dict(file=name, url='/files/tailored/' + name, slug=m.group(1) if m else name[:-4],
                          modified=datetime.fromtimestamp(os.path.getmtime(f)).strftime('%Y-%m-%d'),
                          company=app['company'] if app else '', title=app['title'] if app else '',
                          job_url=app['url'] if app else ''))
    items.sort(key=lambda x: x['modified'], reverse=True)
    base = os.path.isfile(path('resumes/base.html'))
    return dict(base=base, base_url='/files/resumes/base.html' if base else '',
                base_pdf='/files/resumes/base.pdf' if os.path.isfile(path('resumes/base.pdf')) else '', tailored=items)


def raw_summary(folder):
    runs_path = os.path.join(folder, 'runs.json')
    if not os.path.isfile(runs_path):
        return None
    try:
        runs = json.load(open(runs_path, encoding='utf-8'))
    except ValueError:
        return None
    sites = {}
    for r in runs:
        s = sites.setdefault(r.get('site') or '?', dict(runs=0, items=0, cost=0.0, problems=0))
        s['runs'] += 1
        s['items'] += r.get('items') or 0
        s['cost'] += r.get('cost_usd') or 0
        s['problems'] += r.get('status') != 'SUCCEEDED'
    return dict(folder=os.path.basename(folder), runs=len(runs), cost=round(sum(s['cost'] for s in sites.values()), 3),
                problems=sum(s['problems'] for s in sites.values()), sites=sites,
                when=datetime.fromtimestamp(os.path.getmtime(runs_path), timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))


def get_searches():
    out = {}
    for name in list_job_files():
        label = name[len('top_jobs_'):-len('.csv')]
        _, rows = read_csv('search_results/' + name)
        per = {}
        for r in rows:
            per[r.get('platform') or '?'] = per.get(r.get('platform') or '?', 0) + 1
        out[label] = dict(label=label, file=name, jobs=len(rows), per_site=per, raw=[])
    for folder in sorted(glob.glob(path('search_results/raw/*'))):
        info = raw_summary(folder)
        if not info:
            continue
        label = re.sub(r'^test_', '', info['folder'])
        out.setdefault(label, dict(label=label, file='', jobs=None, per_site={}, raw=[]))['raw'].append(info)
    return dict(searches=sorted(out.values(), key=lambda s: s['label'], reverse=True))


def get_credit():
    try:
        spec = importlib.util.spec_from_file_location('apify_helper', path('apify.py'))
        apify = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(apify)
        if not apify.token() or apify.token() == 'your_token_here':
            return dict(ok=False, message='No Apify token yet. Put APIFY_TOKEN=... in the .env file (see README).')
        lim = apify.call('GET', '/users/me/limits', tries=1)['data']
    except BaseException as e:  # apify.call can sys.exit; never let it stop the server
        msg = str(e)
        if '401' in msg:
            msg = 'Apify refused the token in .env (HTTP 401). Check that it is current.'
        return dict(ok=False, message='Could not read Apify usage: ' + msg[:200])
    cur, cap, cyc = lim.get('current') or {}, lim.get('limits') or {}, lim.get('monthlyUsageCycle') or {}
    return dict(ok=True, used=cur.get('monthlyUsageUsd'), limit=cap.get('maxMonthlyUsageUsd'),
                cycle_end=(cyc.get('endAt') or '')[:10], cycle_start=(cyc.get('startAt') or '')[:10])


def rerank_preview(d):
    folder = str(d.get('folder') or '')
    raw_dir = path('search_results/raw')
    target = os.path.realpath(os.path.join(raw_dir, folder))
    if not folder or '/' in folder or folder.startswith('.') or os.path.dirname(target) != os.path.realpath(raw_dir) \
            or not os.path.isdir(target):
        raise Refused('No such search folder.', 404)
    runs_path = os.path.join(target, 'runs.json')
    when = os.path.getmtime(runs_path if os.path.isfile(runs_path) else target)
    now = datetime.fromtimestamp(when, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    with tempfile.TemporaryDirectory(prefix='dashboard-rerank-') as tmp:  # outside the project; deleted after
        out_csv, stats = os.path.join(tmp, 'preview.csv'), os.path.join(tmp, 'stats.json')
        # --log points at a file that doesn't exist, so handled jobs stay in (and get marked) and the
        # preview compares fairly with the list made at search time
        r = subprocess.run([sys.executable, path('rank_jobs.py'), target, out_csv, '--stats', stats, '--now', now,
                            '--log', os.path.join(tmp, 'no-log.csv')], capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not os.path.isfile(out_csv):
            tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
            msg = 'no job passed the filters' if 'IndexError' in (r.stderr or '') else ' '.join(tail)
            raise Refused('Re-rank failed: ' + msg)
        with open(out_csv, newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        st = json.load(open(stats, encoding='utf-8')) if os.path.isfile(stats) else {}
    label = re.sub(r'^test_', '', folder)
    _, cur = read_csv(f'search_results/top_jobs_{label}.csv')
    count = lambda rs: {k: sum(1 for x in rs if x.get('platform') == k) for k in {x.get('platform') for x in rs}}
    drops = {}
    for s in st.values():
        for k, v in (s.get('drops') or {}).items():
            drops[k] = drops.get(k, 0) + v
    done = handled_by_url()
    for x in rows:
        x['handled'] = done.get((x.get('url') or '').strip(), '')
    return dict(folder=folder, now=now, rows=rows, preview=count(rows), current=count(cur),
                current_file=f'top_jobs_{label}.csv' if cur else '', drops=drops)


# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    server_version = 'JobDashboard'

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def allowed_hosts(self):
        return {f'127.0.0.1:{PORT}', f'localhost:{PORT}'}

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, full):
        ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
        if full.endswith('.ttf'):
            ctype = 'font/ttf'
        with open(full, 'rb') as f:
            body = f.read()
        self.send_response(200)
        self.send_header('Content-Type', ctype + ('; charset=utf-8' if ctype.startswith('text/') or ctype.endswith('javascript') else ''))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def guard(self, write=False):
        if self.headers.get('Host') not in self.allowed_hosts():
            raise Refused('Wrong host.', 403)
        if write:
            if not (self.headers.get('Content-Type') or '').startswith('application/json'):
                raise Refused('Writes must be JSON.', 415)
            if self.headers.get('Origin') not in {'http://' + h for h in self.allowed_hosts()}:
                raise Refused('Writes are only accepted from the dashboard page.', 403)

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > 5_000_000:
            raise Refused('Request too large.', 413)
        try:
            return json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            raise Refused('Bad JSON in the request.')

    def handle_errors(self, fn):
        try:
            fn()
        except Refused as e:
            self.send_json(dict(ok=False, error=str(e)), e.code)
        except Exception as e:
            self.send_json(dict(ok=False, error=f'Server error: {type(e).__name__}: {e}'), 500)

    def do_GET(self):
        self.handle_errors(self._get)

    def do_PUT(self):
        self.handle_errors(self._write)

    def do_POST(self):
        self.handle_errors(self._write)

    def _get(self):
        self.guard()
        u = urlsplit(self.path)
        p, q = unquote(u.path), parse_qs(u.query)
        api = {'/api/profile': get_profile, '/api/config': get_config, '/api/plan': get_plan,
               '/api/applications': get_applications, '/api/resumes': get_resumes, '/api/searches': get_searches,
               '/api/credit': get_credit}
        if p in api:
            return self.send_json(api[p]())
        if p == '/api/jobs':
            return self.send_json(get_jobs(q))
        if p.startswith('/files/'):
            rel = p[len('/files/'):]
            top = rel.split('/')[0]
            if top in SERVED_DIRS and not any(part.startswith('.') for part in rel.split('/')):
                base = os.path.realpath(path(top))
                full = os.path.realpath(path(rel))
                if full.startswith(base + os.sep) and os.path.isfile(full):
                    return self.send_file(full)
            raise Refused('Not found.', 404)
        static = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}
        if p in static:
            return self.send_file(os.path.join(STATIC, static[p]))
        raise Refused('Not found.', 404)

    def _write(self):
        self.guard(write=True)
        p = urlsplit(self.path).path
        routes = {('PUT', '/api/profile'): put_profile, ('PUT', '/api/config'): put_config,
                  ('PUT', '/api/plan'): put_plan, ('POST', '/api/rerank-preview'): rerank_preview}
        fn = routes.get((self.command, p))
        if not fn:
            raise Refused('Not allowed.', 405)
        self.send_json(fn(self.body()))


def main():
    global ROOT, PORT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--root', default=HERE, help='project folder (default: the folder of this script)')
    a = ap.parse_args()
    ROOT = os.path.abspath(a.root)
    server = None
    for port in range(a.port, a.port + 10):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
            PORT = port
            break
        except OSError:
            continue
    if not server:
        sys.exit(f'Ports {a.port}-{a.port + 9} are all in use. Try --port <number>.')
    url = f'http://127.0.0.1:{PORT}/'
    print(f'Dashboard running at {url}  (project: {ROOT})\nPress Ctrl-C to stop.')
    if not a.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')


if __name__ == '__main__':
    main()
