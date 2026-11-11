"""Combine job scrapes from several sites, drop jobs that don't fit, score the rest, and write one CSV
in apply order (grouped by site, then location tier, then fit score).

Usage:
  python3 rank_jobs.py <folder with downloaded results> <output.csv> [--config profile/rank_config.json]
                       [--now 2026-11-06T15:45] [--stats stats.json] [--no-jd]

It also saves the description of every job it keeps to search_results/jd/ (see fetch_job.py), so
tailoring can read it without fetching the page. --no-jd turns that off.

The folder is what `apify.py run --out` writes: one <datasetId>.json per run plus runs.json.
Every personal rule (titles, skills, locations, salary, work authorization) lives in the config file,
written during setup. See profile.example/rank_config.json for an example with comments.
"""
import json, glob, re, csv, sys, html, os, argparse
from datetime import datetime, timezone, timedelta
from fetch_job import jd_path

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('src', nargs='?'); ap.add_argument('out', nargs='?')
ap.add_argument('--config', default=os.path.join(HERE, 'profile', 'rank_config.json'))
ap.add_argument('--now', help='ISO time to measure job age from (default: now)')
ap.add_argument('--log', default=os.path.join(HERE, 'applications.csv'), help='jobs already handled')
ap.add_argument('--stats', help='also write per-site statistics to this JSON file')
ap.add_argument('--dropped', help='also write dropped jobs (site, reason, title, company, location, url) to this CSV')
ap.add_argument('--check', action='store_true', help='only check that the config is valid')
ap.add_argument('--no-jd', action='store_true', help="don't save job descriptions to search_results/jd/")
A = ap.parse_args()
if not os.path.exists(A.config):
    sys.exit(f'No config at {A.config}. Run setup first (send README.md to your AI assistant).')
C = json.load(open(A.config))

if A.check:
    bad = []
    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                if not k.startswith('_'):
                    walk(v, f'{path}.{k}')
        elif isinstance(x, str) and x and not path.endswith(('.status', '.name')):
            try:
                re.compile(x)
            except re.error as e:
                bad.append(f'{path}: {e}')
    walk(C, 'config')
    for need in ('titles.include', 'locations.tiers'):
        a, b = need.split('.')
        if not (C.get(a) or {}).get(b):
            bad.append(f'missing {need}')
    if (C.get('work_authorization') or {}).get('status', 'us_citizen') not in ('us_citizen', 'green_card', 'f1_opt', 'needs_sponsorship'):
        bad.append('work_authorization.status must be us_citizen, green_card, f1_opt or needs_sponsorship')
    print('\n'.join(bad) or 'Config OK.')
    sys.exit(1 if bad else 0)
if not (A.src and A.out):
    ap.error('src and out are required')
NOW = datetime.fromisoformat(A.now).replace(tzinfo=timezone.utc) if A.now else datetime.now(timezone.utc)

TOP_N = C.get('top_n_per_site')            # max jobs per site; None keeps every job that passes min_fit
MIN_FIT = C.get('min_fit', 16)
MAX_AGE_H = C.get('max_age_hours', {})       # per site; sites not listed have no age limit
SITE_ORDER = C.get('site_order', [])
MIN_SALARY = C.get('min_salary')             # annual; None turns the salary filter off

# ---------- load ----------
def flatten(d):
    """Add 'a.b' keys for nested fields, so both nested and pre-flattened rows read the same way."""
    out = dict(d)
    for k, v in d.items():
        if isinstance(v, dict):
            for k2, v2 in flatten(v).items():
                out.setdefault(f'{k}.{k2}', v2)
        elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            for k2 in {kk for x in v for kk in x}:
                out.setdefault(f'{k}.{k2}', [x.get(k2) for x in v])
    return out

runs_meta = {}
if os.path.exists(os.path.join(A.src, 'runs.json')):
    for r in json.load(open(os.path.join(A.src, 'runs.json'))):
        if r.get('dataset_id'):
            runs_meta[r['dataset_id']] = r

raw = {}            # (parser, site) -> {job key: merged row}
raw_count = {}      # site -> items downloaded
for f in sorted(glob.glob(os.path.join(A.src, '*.json')) + glob.glob(os.path.join(A.src, '*.txt'))):
    try:
        d = json.load(open(f))
        ds, items = d['datasetId'], d['items']
    except Exception:
        continue
    meta = runs_meta.get(ds, {})
    parser, site = d.get('parser') or meta.get('parser'), d.get('site') or meta.get('site')
    if not parser:
        print(f'skipping {os.path.basename(f)}: no parser known for dataset {ds}')
        continue
    bucket = raw.setdefault((parser, site), {})
    for it in items:
        it = flatten(it)
        k = str(it.get('jobId') or it.get('key') or it.get('id') or it.get('url') or it.get('jobUrl') or len(bucket))
        bucket.setdefault(k, {}).update(it)
    raw_count[site] = raw_count.get(site, 0) + len(items)

def rows(parser):
    for (p, site), b in raw.items():
        if p == parser:
            for k, j in b.items():
                yield site, k, j

def g(j, key):
    """Read 'a.b' from a flattened row (key 'a.b') or a nested one (j['a']['b'])."""
    if key in j:
        return j[key]
    for part in key.split('.'):
        j = j.get(part) if isinstance(j, dict) else None
    return j

def first(j, *keys):
    for k in keys:
        v = g(j, k)
        if has(v):
            return v
    return None

def has(x):
    return x not in (None, 'None', '', [])

def ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)  # some dates have no timezone
    except Exception:
        return None

def strip_html(s):
    return html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))

def money(vals, guess_monthly=False):
    # guess_monthly: LinkedIn gives no pay period, so $300-$20k is taken as a monthly figure
    v = []
    for x in vals:
        try:
            x = float(str(x).replace('$', '').replace(',', ''))
        except Exception:
            continue
        if x <= 0:
            continue
        v.append(x * 2080 if x < 300 else x * 12 if guess_monthly and x < 20000 else x)
    return (min(v), max(v)) if v else None

def k_range(s):
    return '' if not s else (f"${s[0]/1000:.0f}k-${s[1]/1000:.0f}k" if round(s[0]) != round(s[1]) else f"${s[0]/1000:.0f}k")

# ---------- one parser per scraper output format ----------
jobs = []
for site, k, j in rows('linkedin'):         # cheap_scraper/linkedin-job-scraper
    if 'jobDescription' not in j:
        continue
    jobs.append(dict(platform=site or 'LinkedIn', id=k, title=j['jobTitle'], company=j.get('companyName') or '',
        location=j.get('location') or '', posted=ts(j.get('publishedAt')), posted_txt=j.get('postedTime', ''),
        salary=money(j.get('salaryInfo') or [], guess_monthly=True), desc=j.get('jobDescription') or '',
        url=j['jobUrl'].split('?')[0]))

for site, k, j in rows('indeed'):           # valig/indeed-jobs-scraper
    unit = (j.get('baseSalary.unitOfWork') or '').upper()
    lo, hi = j.get('baseSalary.min'), j.get('baseSalary.max')
    mult = 2080 if unit == 'HOUR' else 12 if unit == 'MONTH' else 1
    sal = money([float(x) * mult for x in (lo, hi) if has(x)]) if unit in ('HOUR', 'MONTH', 'YEAR') else None
    loc = ', '.join(x for x in [j.get('location.city'), j.get('location.admin1Code')] if x and x != 'None') or 'Remote'
    jobs.append(dict(platform=site or 'Indeed', id=k, title=j['title'], company=j.get('employer.name') or '',
        location=loc, posted=ts(j.get('datePublished')), posted_txt='', salary=sal,
        desc=j.get('description.text') or '', url=j.get('url') or j.get('jobUrl')))

for site, k, j in rows('handshake'):        # memo23/handshake-jobs-scraper
    if j.get('employmentType') == 'PART_TIME':
        continue
    per = (j.get('salaryPeriod') or '').upper()
    mult = 2080 if per == 'HOUR' else 12 if per == 'MONTH' else 1
    sal = money([float(x) * mult for x in (j.get('salaryMin'), j.get('salaryMax')) if has(x)])
    cities = j.get('allLocations.city') or []
    states = j.get('allLocations.state') or []
    if isinstance(cities, list) and cities:
        loc = '; '.join(f"{c}, {s_}" for c, s_ in zip(cities, list(states) + [''] * len(cities)))
    else:
        loc = j.get('location') or ''
    if str(j.get('isRemote')) == 'True':
        loc = (loc + '; Remote').strip('; ')
    jobs.append(dict(platform=site or 'Handshake', id=k, title=j['title'], company=j.get('employerName') or '', location=loc,
        posted=ts(j.get('datePosted')), posted_txt='', salary=sal, desc=j.get('description') or strip_html(j.get('descriptionHtml')),
        url=j.get('jobUrl') or f"https://app.joinhandshake.com/public/jobs/{k}"))

for site, k, j in rows('glassdoor'):        # valig/glassdoor-jobs-scraper
    per = (g(j, 'pay.period') or '').upper()
    mult = 2080 if per == 'HOURLY' else 12 if per == 'MONTHLY' else 1
    pay = money([float(x) * mult for x in (g(j, 'pay.min'), g(j, 'pay.max')) if has(x)])
    listed = g(j, 'pay.source') == 'EMPLOYER_PROVIDED'  # otherwise it's Glassdoor's own estimate
    age = g(j, 'ageInDays')
    jobs.append(dict(platform=site or 'Glassdoor', id=k, title=j['title'], company=g(j, 'employer.name') or '',
        location=g(j, 'location.name') or '', posted=NOW - timedelta(days=int(age)) if has(age) else None, posted_txt='',
        salary=pay if listed else None, est='' if listed or not pay else f'Glassdoor est. {k_range(pay)}',
        desc=strip_html(j.get('description')), url=j.get('seoUrl') or j.get('url')))

for site, k, j in rows('hiringcafe'):       # memo23/apify-hiring-cafe-scraper
    v = lambda f: g(j, 'v5_processed_job_data.' + f)
    if str(j.get('is_expired')) == 'True':
        continue
    loc = v('formatted_workplace_location') or ''
    if v('workplace_type') == 'Remote' and 'remote' not in loc.lower():
        loc = (loc + '; Remote').strip('; ')
    jobs.append(dict(platform=site or 'Hiring Cafe', id=k, title=(g(j, 'job_information.title') or '').strip(),
        company=v('company_name') or '', location=loc, posted=ts(v('estimated_publish_date')), posted_txt='',
        salary=money([x for x in (v('yearly_min_compensation'), v('yearly_max_compensation')) if has(x)]),
        desc=g(j, 'job_information.descriptionText') or strip_html(g(j, 'job_information.description')),
        yrs=v('min_industry_and_role_yoe'), clearance=has(v('security_clearance')),
        url=j.get('apply_url') or f"https://hiring.cafe/job/{k}"))

for site, k, j in rows('careersite'):       # fantastic-jobs feeds; 'source' says workday, greenhouse, ...
    unit = (j.get('ai_salary_unit_text') or '').upper()
    mult = {'HOUR': 2080, 'WEEK': 52, 'MONTH': 12, 'YEAR': 1}.get(unit)
    sal = money([float(x) * mult for x in (j.get('ai_salary_min_value'), j.get('ai_salary_max_value')) if has(x)]) if mult else None
    locs = j.get('locations_derived') or []
    loc = '; '.join(map(str, locs)) if isinstance(locs, list) else str(locs)
    if 'remote' in str(j.get('ai_work_arrangement') or '').lower() and 'remote' not in loc.lower():
        loc = (loc + '; Remote').strip('; ')
    jobs.append(dict(platform=(j.get('source') or site or 'Career site').title(), id=k, title=j['title'],
        company=j.get('organization') or '', location=loc, posted=ts(j.get('date_posted')), posted_txt='', salary=sal,
        desc=j.get('description_text') or strip_html(j.get('description_html')), url=j['url']))

for site, k, j in rows('jobright'):         # datascraperes/jobright-jobs-scraper
    # Jobright has no raw description, only summary + bullet lists
    parts = [j.get('summary')] + [x for f in ('responsibilities', 'requirements', 'qualificationsMustHave', 'qualificationsPreferred')
                                  for x in (j.get(f) or [])]
    loc = j.get('location') or ''
    if str(j.get('isRemote')) == 'True' and 'remote' not in loc.lower():
        loc = (loc + '; Remote').strip('; ')
    jobs.append(dict(platform=site or 'Jobright', id=k, title=j['title'], company=j.get('companyName') or '', location=loc,
        posted=ts(j.get('postedAt')), posted_txt='',
        salary=money([x for x in (j.get('salaryAnnualMin'), j.get('salaryAnnualMax')) if has(x)]),
        desc='\n'.join(str(p) for p in parts if p), yrs=j.get('minYearsOfExperience'),
        citizen_only=str(j.get('isCitizenOnly')) == 'True', clearance=str(j.get('isClearanceRequired')) == 'True',
        url=j.get('applyLink') or j.get('url'), summary_only=True))

for site, k, j in rows('generic'):          # any other scraper: guess the common field names
    title = first(j, 'title', 'jobTitle', 'positionName', 'position', 'name')
    url = first(j, 'url', 'jobUrl', 'link', 'applyUrl', 'applyLink', 'apply_url')
    if not title or not url:
        continue
    desc = first(j, 'description.text', 'descriptionText', 'description_text', 'jobDescription', 'description', 'snippet') or ''
    if not isinstance(desc, str):
        desc = json.dumps(desc)
    if '<' in desc and '>' in desc:
        desc = strip_html(desc)
    lo, hi = first(j, 'salaryMin', 'minSalary', 'salary.min', 'salary_min'), first(j, 'salaryMax', 'maxSalary', 'salary.max', 'salary_max')
    sal = money([x for x in (lo, hi) if has(x)])
    if not sal and isinstance(first(j, 'salary'), str):
        sal = money(re.findall(r'\$?\s?(\d[\d,]*(?:\.\d+)?)\s*[kK]?', j['salary'])[:2])
    loc = first(j, 'location.name', 'location', 'jobLocation', 'locationName', 'city') or ''
    if isinstance(loc, (list, dict)):
        loc = json.dumps(loc)
    jobs.append(dict(platform=site or 'Other', id=k, title=str(title), company=str(first(j, 'company.name', 'companyName', 'company',
        'employer.name', 'employerName', 'employer', 'organization') or ''), location=str(loc),
        posted=ts(first(j, 'postedAt', 'datePosted', 'publishedAt', 'date_posted', 'postingDate', 'createdAt', 'date')),
        posted_txt=str(first(j, 'postedTime', 'posted', 'age') or ''), salary=sal, desc=desc, url=str(url)))

# ---------- rules from the config ----------
LOC = C.get('locations', {})
def tier(loc):
    l = loc.lower()
    for t in LOC.get('tiers', []):
        if t.get('match') and re.search(t['match'], l):
            return t['tier'], t['name']
        if t.get('state_codes') and re.search(r',\s*(%s)\b' % '|'.join(t['state_codes']), loc):
            return t['tier'], t['name']
    rem = LOC.get('remote')
    if rem and ('remote' in l or l.strip() == 'united states'):
        return rem['tier'], rem['name']
    other = LOC.get('other')
    return (other['tier'], other['name']) if other else (None, 'Other')

T = C['titles']
TITLE_OK, TITLE_BAD = T['include'], T.get('exclude') or r'(?!x)x'
TITLE_SOFT_BAD, CORE_TITLE = T.get('exclude_unless_core') or r'(?!x)x', T.get('core') or r'(?!x)x'
S = C.get('seniority', {})
MAX_YEARS = S.get('max_years')
YEARS_BONUS = {int(k): v for k, v in (S.get('years_bonus') or {}).items()}
SKILLS = {k: (v['pattern'], v.get('weight', 1)) for k, v in C.get('skills', {}).items()}
FLAGS = C.get('flags', {})

WA = C.get('work_authorization', {})
STATUS = WA.get('status', 'us_citizen')     # us_citizen | green_card | f1_opt | needs_sponsorship
NO_CITIZEN_ONLY = STATUS != 'us_citizen'
NO_GC_ONLY = STATUS in ('f1_opt', 'needs_sponsorship')
NO_CLEARANCE = WA.get('exclude_clearance_jobs', STATUS != 'us_citizen')

CITIZEN_ONLY = [r'u\.?s\.? citizen(ship)? (is )?(required|only)', r'must be (a )?u\.?s\.? citizen', r'citizenship (is )?required',
                r'\bitar\b', r'u\.?s\.? persons?\b', r'only (us|u\.s\.) citizens', r'u\.?s\.? citizenship']
GC_ONLY = [r'green card holders? only', r'permanent residents? only', r'citizens? or (lawful )?permanent residents? only']
NO_OPT = [r'(not|unable to) (accept|consider) (opt|cpt|f-?1)', r'\bopt\b[^.]{0,40}not (be )?(accepted|eligible|considered)',
          r'no (opt|cpt|c2c)']
CLEARANCE = [r'security clearance', r'\bts/sci\b', r'secret clearance', r'clearance (is )?required',
             r'(active|obtain|eligib\w*( to obtain)?|maintain) (a |an )?(dod |u\.s\. )?(secret|top secret|clearance)',
             r'top secret', r'polygraph', r'clearable', r'dod 8570',
             # clearance named only by level: Tier 3/5, DOE Q/L, clearance under the PWS/contract
             r'\b(tier|t)\s*-?\s*[35]\b[^.]{0,40}(clearance|investigation|background|suitability)',
             r'(clearance|investigation|background)[^.]{0,40}\b(tier|t)\s*-?\s*[35]\b',
             r'\bdoe\s*[ql]\b', r'\b[ql][- ](clearance|access authorization)',
             r'(clearance|cleared)[^.]{0,60}\b(pws|contract)\b', r'\bpws\b[^.]{0,60}clearance',
             r'(able|ability) to obtain (a |an )?(\w+ )?clearance', r'active clearance']
WA_BAD = (CITIZEN_ONLY if NO_CITIZEN_ONLY else []) + (GC_ONLY if NO_GC_ONLY else []) + \
         (NO_OPT if STATUS == 'f1_opt' else []) + (CLEARANCE if NO_CLEARANCE else [])
WA_TITLE_BAD = r'clearance|\bts/sci\b' if NO_CLEARANCE else r'(?!x)x'
NOSPON = r'(not|unable to|cannot|won.t|will not|does not)[^.]{0,30}sponsor|sponsorship[^.]{0,30}(not|unavailable)|without (the need for )?(current or future )?(visa )?sponsorship'
OPT_OK = r'\bopt\b|stem opt|f-1|international students|visa sponsorship (is )?available|will sponsor|sponsorship available|h-?1b sponsorship'
SPONSOR_OK = r'visa sponsorship (is )?available|will sponsor|sponsorship available|h-?1b sponsorship'

# Staffing firms, OPT training/placement firms and job aggregators that post as the "company"
DEFAULT_BLOCKED_COMPANIES = r'emonics|prestige staffing|brooksource|insight global|skillstorm|beaconfire|revature|synergisticit|themesoft|spectraforce|cybercoders|jobot|robert half|teksystems|apex systems|kforce|randstad|motion recruitment|\bdice\b|actalent|hirekeyz|infodrive|fdm group|smoothstack|genspark|talent path|cognizant|infosys|tata consultancy|wipro|capgemini|\bhcl\b|harnham|recruiterforge|talenthop|goliath partners|dexian|franklin fitch|centraprise|eximius|lensa|jobs via dice|hireright|jobright|wiraa|crossover|mindrift|outlier|dataannotation|\bturing\b|peregrine advisors|dev10|international applied technology|quantum insights|vinvast|itlize|contriva|lbi software|viis global|washon meddata|baanyan|icylon|fedstack|hiredbuddy|stabile search|robotics technologies|bv teck|calimontex'
BLOCKED = '|'.join(x for x in [DEFAULT_BLOCKED_COMPANIES if C.get('use_default_company_blocklist', True) else '',
                               C.get('exclude_companies') or ''] if x) or r'(?!x)x'

def min_years(t):
    ys = []
    # (?<![\d.]) and (?:\.\d+)? keep "1.5+ years" from being read as "5+ years"
    for m in re.finditer(r'(?<![\d.])(\d{1,2})(?:\.\d+)?\s*\+?\s*(?:-|to|–)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)(?:\'s)?\s+(?:of\s+)?(?:\w+[\s,/-]+){0,5}?(?:experience|exp\b)', t, re.I):
        n = int(m.group(1))
        if n < 15:
            ys.append(n)
    return min(ys) if ys else None

CO_SUFFIX = r'\b(inc|incorporated|corp|corporation|co|company|llc|ltd|limited|pte|plc|services|group|holdings|technologies|usa)\b\.?'

def norm(r):
    co = re.sub(CO_SUFFIX, '', (r['company'] or '').lower())  # "Quest Global Services Pte" == "Quest Global"
    return (re.sub(r'[^a-z]', '', co)[:12], re.sub(r'[^a-z0-9]', '', r['title'].lower().split(' - ')[0].split(',')[0])[:30])

def full_key(r):  # stricter than norm(): whole title, so other roles at the same company aren't caught
    return (norm(r)[0], re.sub(r'[^a-z0-9]', '', r['title'].lower()))

# Jobs already applied to or skipped (applications.csv), matched by URL or by company + full title
done_urls, done_keys = set(), set()
try:
    with open(A.log, newline='') as fh:
        for r in csv.DictReader(fh):
            done_urls.add((r.get('url') or '').strip())
            done_keys.add(full_key(r))
except FileNotFoundError:
    pass

# ---------- filter and score ----------
out, drops, site_drops, dropped = [], {}, {}, []
def drop(j, reason):
    drops[reason] = drops.get(reason, 0) + 1
    sd = site_drops.setdefault(j['platform'], {})
    sd[reason] = sd.get(reason, 0) + 1
    dropped.append(dict(site=j['platform'], reason=reason, title=j['title'], company=j['company'],
                        location=j['location'], url=j['url']))

for j in jobs:
    t, dl = j['title'], j['desc'].lower()
    if (j['url'] or '').strip() in done_urls or full_key(j) in done_keys:
        drop(j, 'already in applications.csv'); continue
    if not re.search(TITLE_OK, t, re.I) or re.search(TITLE_BAD, t, re.I) or \
            (re.search(TITLE_SOFT_BAD, t, re.I) and not re.search(CORE_TITLE, t, re.I)):
        drop(j, 'title not a target role'); continue
    if (NO_CITIZEN_ONLY and j.get('citizen_only')) or (NO_CLEARANCE and j.get('clearance')) or \
            re.search(WA_TITLE_BAD, t, re.I) or any(re.search(p, dl) for p in WA_BAD):
        drop(j, 'work authorization/clearance'); continue
    y = min_years(j['desc'])
    if y is None and has(j.get('yrs')):  # site's own years field, when the text doesn't say
        y = int(float(j['yrs']))
    if MAX_YEARS is not None and y is not None and y > MAX_YEARS:
        drop(j, f'>{MAX_YEARS} yrs exp'); continue
    s = j['salary']
    if MIN_SALARY and s and s[1] < MIN_SALARY:
        drop(j, 'salary too low'); continue
    age_h = (NOW - j['posted']).total_seconds() / 3600 if j['posted'] else None
    if age_h is not None and age_h > MAX_AGE_H.get(j['platform'], MAX_AGE_H.get('default', float('inf'))):
        drop(j, 'posted too long ago'); continue
    if re.search(BLOCKED, j['company'].lower()) or re.search(r'\b(opt|cpt)\b[^,]{0,20}candidates?', t, re.I):
        drop(j, 'staffing/training firm'); continue
    tr, area = tier(j['location'])
    if tr is None and LOC.get('remote') and re.search(r'\bremote\b', t, re.I):  # e.g. "Engineer I (Remote Eligible)" listed in Bellevue, WA
        tr, area = LOC['remote']['tier'], 'Remote (per title)'
    if tr is None:
        drop(j, 'outside target locations'); continue

    sk = [k for k, (p, w) in SKILLS.items() if re.search(p, dl)]
    score = sum(SKILLS[k][1] for k in sk)
    tl = t.lower()
    if S.get('title_bonus') and re.search(S['title_bonus'], tl): score += 12
    if T.get('role_bonus') and re.search(T['role_bonus'], tl): score += 8
    if S.get('desc_bonus') and re.search(S['desc_bonus'], dl): score += 6
    if y is not None: score += YEARS_BONUS.get(y, 0)
    else: score -= 1
    if s: score += 5 if not MIN_SALARY or s[0] >= MIN_SALARY else 2
    if STATUS == 'f1_opt' and re.search(OPT_OK, dl) and not re.search(NOSPON, dl): score += 4
    if STATUS == 'needs_sponsorship' and re.search(SPONSOR_OK, dl) and not re.search(NOSPON, dl): score += 4
    if S.get('title_penalty') and re.search(S['title_penalty'], tl): score -= 6
    if age_h is not None and age_h <= 24: score += 2
    if not j['company'].strip(): score -= 8
    notes = []
    if not j['company'].strip(): notes.append('company hidden (likely recruiter)')
    if STATUS == 'needs_sponsorship' and re.search(NOSPON, dl):
        drop(j, 'no visa sponsorship'); continue
    if STATUS == 'f1_opt':
        if re.search(NOSPON, dl): notes.append('no H1B sponsorship (OPT ok)')
        elif re.search(OPT_OK, dl): notes.append('mentions OPT/sponsorship')
    if NO_CITIZEN_ONLY and 'public trust' in dl: notes.append('Public Trust (check citizenship)')
    if not s: notes.append('salary not listed' + (f" ({j['est']})" if j.get('est') else ''))
    elif MIN_SALARY and s[0] < MIN_SALARY: notes.append(f'range starts <${MIN_SALARY / 1000:.0f}k')
    if y is None: notes.append('yrs not stated')
    for label, pat in FLAGS.items():
        if re.search(pat, t + ' ' + j['desc'][:800], re.I): notes.append(label)
    if j['platform'] not in ('LinkedIn', 'Indeed') and age_h and age_h > 72: notes.append(f'posted {int(age_h // 24)}d ago')
    if score < MIN_FIT:
        drop(j, 'low fit score'); continue
    out.append(dict(platform=j['platform'], tier=tr, area=area, fit_score=score, title=t, company=j['company'],
        location=j['location'], posted=(j['posted'].strftime('%Y-%m-%d') if j['posted'] else j['posted_txt']),
        salary=k_range(s), min_yrs='' if y is None else y, skills=', '.join(sk), notes='; '.join(notes), url=j['url'],
        _desc='' if j.get('summary_only') else j['desc']))

# ---------- order: by site, then location tier, then fit ----------
sites = SITE_ORDER + sorted({r['platform'] for r in out} - set(SITE_ORDER))
final, seen, counts = [], set(), {}
for plat in sites:
    cand = sorted([r for r in out if r['platform'] == plat], key=lambda r: (r['tier'], -r['fit_score']))
    picked = []
    for r in cand:
        k = norm(r)
        if k in seen:
            continue
        seen.add(k)
        picked.append(r)
        if TOP_N and len(picked) == TOP_N:
            break
    if cand:
        counts[plat] = (len(cand), len(picked))
    for i, r in enumerate(picked, 1):
        final.append(dict(apply_order=len(final) + 1, platform=plat, platform_rank=i, **{k: v for k, v in r.items() if k != 'platform'}))
descs = {r['url']: r.pop('_desc') for r in final}

print('candidates/picked per site:', counts)
print('drops:', drops)
if A.dropped:
    os.makedirs(os.path.dirname(A.dropped) or '.', exist_ok=True)
    with open(A.dropped, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['site', 'reason', 'title', 'company', 'location', 'url'])
        w.writeheader(); w.writerows(sorted(dropped, key=lambda d: (d['reason'], d['site'])))
if not final:
    sys.exit('No jobs passed the filters. Check the config, or look at the drops above.')
os.makedirs(os.path.dirname(A.out) or '.', exist_ok=True)
with open(A.out, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(final[0]))
    w.writeheader(); w.writerows(final)
if not A.no_jd:
    saved = 0
    for r in final:
        d = (descs.get(r['url']) or '').strip()
        if not r['url'] or len(d) < 300:     # too short to be a real posting (or a Jobright summary)
            continue
        p = jd_path(r['url'])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        head = [f"SAVED DESCRIPTION (scraped {NOW.strftime('%Y-%m-%d')}; the posting may have closed since)",
                f"{r['title']} | {r['company']} | {r['location']} | salary: {r['salary'] or 'not listed'} | {r['platform']}",
                r['url'], '']
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(head) + '\n' + d + '\n')
        saved += 1
    print(f'saved {saved} of {len(final)} descriptions to search_results/jd/')
for r in final:
    print(r['platform'][:4], r['platform_rank'], r['tier'], r['fit_score'], '|', r['title'][:55], '|', r['company'][:25], '|', r['location'][:25], '|', r['salary'], '|', r['notes'][:60])

if A.stats:
    cost = {}
    for m in runs_meta.values():
        cost[m.get('site')] = cost.get(m.get('site'), 0) + (m.get('cost_usd') or 0)
    st = {}
    for plat in sorted(set(raw_count) | {j['platform'] for j in jobs}):
        kept = [r for r in final if r['platform'] == plat]
        st[plat] = dict(downloaded=raw_count.get(plat), parsed=sum(j['platform'] == plat for j in jobs), kept=len(kept),
                        tier1=sum(r['tier'] == 1 for r in kept),
                        avg_fit=round(sum(r['fit_score'] for r in kept) / len(kept), 1) if kept else None,
                        cost_usd=round(cost[plat], 3) if plat in cost else None,
                        usd_per_kept=round(cost[plat] / len(kept), 3) if plat in cost and kept else None,
                        drops=site_drops.get(plat, {}))
    json.dump(st, open(A.stats, 'w'), indent=1)
    print('per-site stats written to', A.stats)
