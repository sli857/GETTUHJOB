"""Measure what each job site and each scraper run is worth: jobs per dollar, jobs no other site found,
where jobs get filtered out, overlap between sites, and what you decided about the jobs each site listed.

Usage:
  python3 analyze_sites.py [search folder ...] [--out report.md]

Default: every search_results/raw/<folder> that has a runs.json. It re-ranks each folder with
rank_jobs.py --detail (free, no scraping), using only the applications logged before that search,
so an old search is measured the way it looked on its day. Writes the report to
search_results/analysis_<today>.md and prints it.
"""
import argparse, csv, glob, hashlib, json, os, subprocess, sys, tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, 'search_results', 'raw')
APPS = os.path.join(HERE, 'applications.csv')
PLAN = os.path.join(HERE, 'profile', 'search_plan.json')
PASSED = ('kept', 'duplicate (listed under an earlier site)', 'over top_n_per_site')
# rank_jobs.py checks in this order, so each column is the share lost at that step
FUNNEL = ['already in applications.csv', 'title not a target role', 'work authorization/clearance', 'no visa sponsorship',
          '>yrs', 'salary too low', 'posted too long ago', 'staffing/training firm', 'outside target locations', 'low fit score']
SHORT = {'already in applications.csv': 'seen before', 'title not a target role': 'title', 'work authorization/clearance': 'work auth',
         'no visa sponsorship': 'no visa', '>yrs': 'too many yrs', 'salary too low': 'salary', 'posted too long ago': 'too old',
         'staffing/training firm': 'staffing', 'outside target locations': 'location', 'low fit score': 'low fit'}

ap = argparse.ArgumentParser()
ap.add_argument('folders', nargs='*')
ap.add_argument('--out', default=os.path.join(HERE, 'search_results', f"analysis_{datetime.now():%Y-%m-%d}.md"))
A = ap.parse_args()
folders = [os.path.abspath(f) for f in A.folders] or sorted(
    os.path.dirname(p) for p in glob.glob(os.path.join(RAW, '*', 'runs.json')))
if not folders:
    sys.exit('No search folders with runs.json found.')

def read_csv(p):
    try:
        with open(p, newline='') as fh:
            return list(csv.DictReader(fh))
    except FileNotFoundError:
        return []

def per10(n, cost):
    return f'{n / cost * 0.1:.1f}' if cost else ('free' if n else '-')

def table(head, rows):
    out = ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return '\n'.join(out)

# ---------- run labels from the search plan (same key as apify.py's entry_key) ----------
labels = {}
try:
    for i, e in enumerate(json.load(open(PLAN)).get('runs', [])):
        k = f'{i}:' + hashlib.sha1(json.dumps([e.get('actor'), e.get('input')], sort_keys=True).encode()).hexdigest()[:10]
        inp = e.get('input') or {}
        q = next((inp[f] for f in ('title', 'keywords', 'keyword', 'searchQueries', 'titleSearch', 'roles') if inp.get(f)), '')
        loc = next((inp[f] for f in ('location', 'locations', 'locationSearch') if inp.get(f)), '')
        if inp.get('startUrls'):
            qs = parse_qs(urlparse(inp['startUrls'][0].get('url', '')).query)
            q, loc = qs.get('keywords', [''])[0], qs.get('location', [''])[0] + f" ({len(inp['startUrls'])} URLs)"
        q = '/'.join(q) if isinstance(q, list) else q
        loc = (', '.join(loc[:3]) + (f' +{len(loc) - 3}' if len(loc) > 3 else '')) if isinstance(loc, list) else loc
        if inp.get('remoteOnly') or inp.get('remoteWorkType'):
            loc += ' (remote)'
        labels[k] = f"{q[:40]} @ {loc[:45]}".strip(' @')
except FileNotFoundError:
    pass

apps = read_csv(APPS)
report = [f"# Site analysis ({datetime.now():%Y-%m-%d})", '',
          'All numbers come from local files; nothing was scraped. "Passed" = passed every filter (before removing',
          'jobs listed by more than one site). "Only here" = passed, and no other site found it passing. Costs are what',
          'Apify reported per run.', '']
summary = defaultdict(dict)   # site -> folder -> (passed/$0.1, only/$0.1)
search_cost = {}              # date -> {site: cost}

for folder in folders:
    name = os.path.basename(folder)
    day = name[:10]
    runs = json.load(open(os.path.join(folder, 'runs.json')))
    now = datetime.fromtimestamp(os.path.getmtime(os.path.join(folder, 'runs.json')), timezone.utc)

    # re-rank with only the applications logged before this search
    tmp = tempfile.mkdtemp()
    log = os.path.join(tmp, 'log.csv')
    with open(log, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(apps[0]) if apps else ['url'])
        w.writeheader(); w.writerows(r for r in apps if (r.get('date') or '') < day)
    detail_p = os.path.join(folder, 'detail.csv')
    res = subprocess.run([sys.executable, os.path.join(HERE, 'rank_jobs.py'), folder, os.path.join(tmp, 'out.csv'), '--log', log,
                          '--now', now.strftime('%Y-%m-%dT%H:%M'), '--no-jd', '--detail', detail_p], capture_output=True, text=True)
    if res.returncode and not os.path.exists(detail_p):
        print(f'{name}: rank_jobs.py failed:\n{res.stderr[-800:]}'); continue
    det = read_csv(detail_p)
    for d in det:
        if d['outcome'].startswith('>') and 'yrs' in d['outcome']:
            d['outcome'] = '>yrs'

    cost, items = Counter(), Counter()
    for r in runs:
        cost[r['site']] += r.get('cost_usd') or 0
        items[r['site']] += r.get('items') or 0
    search_cost[day] = dict(cost)
    # Workday/Greenhouse rows are named by the feed's 'source'; match them to the run's site name
    for d in det:
        d['site'] = next((s for s in cost if s.lower() == d['site'].lower()), d['site'])
    sites = sorted({d['site'] for d in det} | set(cost), key=lambda s: -cost.get(s, 0))

    passed = [d for d in det if d['outcome'] in PASSED]
    by_site = defaultdict(set)              # site -> passing job keys
    for d in passed:
        by_site[d['site']].add(d['key'])
    sites_of = defaultdict(set)
    for s, ks in by_site.items():
        for k in ks:
            sites_of[k].add(s)

    report += [f'## Search {name}', '', f"{len(det)} jobs parsed, {len({d['key'] for d in passed})} distinct jobs passed, "
               f"${sum(cost.values()):.2f} spent. Re-ranked at {now:%Y-%m-%d %H:%M} UTC with {sum(1 for r in apps if (r.get('date') or '') < day)} earlier applications.", '']

    # A + C + F: value per site
    rows = []
    for s in sites:
        ks = by_site[s]
        only = {k for k in ks if sites_of[k] == {s}}
        t1 = {d['key'] for d in passed if d['site'] == s and d['tier'] == '1'}
        fits = [float(d['fit_score']) for d in passed if d['site'] == s and d['fit_score']]
        parsed = [d for d in det if d['site'] == s]
        seen = sum(d['outcome'] == 'already in applications.csv' for d in parsed)
        c = cost.get(s, 0)
        rows.append([s, f'${c:.3f}', items[s], len(parsed), len(ks), len(only), len(t1), len(only & t1),
                     round(sum(fits) / len(fits), 1) if fits else '-', per10(len(ks), c), per10(len(only), c), per10(len(t1), c),
                     f'{seen / len(parsed):.0%}' if parsed else '-'])
        summary[s][name] = (per10(len(ks), c), per10(len(only), c))
    report += ['### Value per site', '', table(
        ['site', 'cost', 'downloaded', 'parsed', 'passed', 'only here', 'tier 1', 'tier 1 only here', 'avg fit',
         'passed / $0.10', 'only here / $0.10', 'tier 1 / $0.10', 'seen before'], rows), '']

    # D: funnel
    rows = []
    for s in sites:
        parsed = [d for d in det if d['site'] == s]
        if not parsed:
            continue
        cnt = Counter(d['outcome'] for d in parsed)
        rows.append([s, len(parsed)] + [f"{cnt[r] / len(parsed):.0%}" if cnt[r] else '' for r in FUNNEL] +
                    [f"{sum(cnt[o] for o in PASSED) / len(parsed):.0%}"])
    report += ['### Where jobs are lost (share of parsed jobs, in filter order)', '',
               table(['site', 'parsed'] + [SHORT[r] for r in FUNNEL] + ['passed'], rows), '']

    # B: overlap
    active = [s for s in sites if by_site[s]]
    rows = [[s, len(by_site[s])] + ['' if s == t else f"{len(by_site[s] & by_site[t]) / len(by_site[s]):.0%}" for t in active]
            for s in active]
    report += ['### Overlap: share of the row site\'s passing jobs that the column site also found', '',
               table(['site', 'passed'] + active, rows), '']

    # E: per run
    run_keys = defaultdict(set)              # run -> passing job keys
    for d in passed:
        for rk in filter(None, d['runs'].split(';')):
            run_keys[rk].add(d['key'])
    runs_of = defaultdict(set)
    for rk, ks in run_keys.items():
        for k in ks:
            runs_of[k].add(rk)
    rows = []
    for r in runs:
        ks = run_keys.get(r['key'], set())
        only = {k for k in ks if runs_of[k] == {r['key']} and len(sites_of[k]) == 1}
        t1 = {d['key'] for d in passed if d['tier'] == '1' and r['key'] in d['runs'].split(';')}
        c = r.get('cost_usd') or 0
        rows.append([r['site'], labels.get(r['key'], r['key']), r.get('items') or 0, f'${c:.3f}', len(ks), len(only), len(t1),
                     per10(len(ks), c), r.get('status', '')])
    report += ['### Per run', '', '"Only this run" = passing jobs no other run (on any site) found. Turning a run off loses about that many.', '',
               table(['site', 'search', 'items', 'cost', 'passed', 'only this run', 'tier 1', 'passed / $0.10', 'status'], rows), '']

# G + H: what was decided about the jobs each site listed
plat_of, list_of = {}, {}
for p in sorted(glob.glob(os.path.join(HERE, 'search_results', 'top_jobs_*.csv'))):
    for r in read_csv(p):
        plat_of[(os.path.basename(p), r.get('url', ''))] = r.get('platform', '')
        list_of.setdefault(os.path.basename(p), Counter())[r.get('platform', '')] += 1
dec = defaultdict(Counter)                  # site -> decision counts
dec_by_list = defaultdict(lambda: defaultdict(Counter))
status = defaultdict(Counter)
for r in apps:
    s = plat_of.get((r.get('csv_file', ''), r.get('url', '')))
    if not s:
        continue
    dec[s][r.get('decision') or '?'] += 1
    dec_by_list[r['csv_file']][s][r.get('decision') or '?'] += 1
    if (r.get('status') or '').strip():
        status[s][r['status'].strip()] += 1
rows = []
for s in sorted(dec, key=lambda s: -sum(dec[s].values())):
    n = sum(dec[s].values())
    rows.append([s, n, dec[s]['apply'], f"{dec[s]['apply'] / n:.0%}", f"{dec[s]['skip'] / n:.0%}", f"{dec[s]['blocked'] / n:.0%}",
                 ', '.join(f'{k} {v}' for k, v in status[s].most_common()) or '-'])
report += ['## Your decisions on listed jobs (all lists)', '',
           'Joined by URL: each job in a top_jobs list against applications.csv. "skip" and "blocked" jobs passed the filters',
           'but were not usable, and still cost a tailoring session to find out.', '',
           table(['site', 'handled', 'applied', 'apply %', 'skip %', 'blocked %', 'replies so far'], rows), '']
rows = []
for lst, per in sorted(dec_by_list.items()):
    day = lst.replace('top_jobs_', '').replace('.csv', '')
    if day not in search_cost:
        continue
    for s, c in sorted(per.items()):
        n = sum(c.values())
        cs = search_cost[day].get(s, 0)
        rows.append([day, s, list_of[lst][s], n, c['apply'], f'${cs:.3f}', per10(c['apply'], cs)])
if rows:
    report += ['### Applications per $0.10 (searches with cost data)', '',
               table(['search', 'site', 'listed', 'handled', 'applied', 'cost', 'applied / $0.10'], rows), '']

# I: stability
names = [os.path.basename(f) for f in folders]
if len(names) > 1:
    rows = [[s] + [' / '.join(summary[s].get(n, ('-', '-'))) for n in names] for s in sorted(summary)]
    report += ['## Across searches: passed / $0.10 and only here / $0.10', '', table(['site'] + names, rows), '']

text = '\n'.join(report)
os.makedirs(os.path.dirname(A.out), exist_ok=True)
open(A.out, 'w').write(text + '\n')
print(text)
print(f'\nSaved to {A.out}')
