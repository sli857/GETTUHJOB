"""Small Apify helper: start scraper runs, enforce a budget, and download the results.

Usage:
  python3 apify.py check                         # token works? how much credit is used this month?
  python3 apify.py store "<search words>"        # find scrapers in the Apify Store, with prices
  python3 apify.py info <user/actor>             # price and input fields of one scraper
  python3 apify.py run <plan.json> --budget 2 --out search_results/raw/<date>

The token is read from the APIFY_TOKEN environment variable or from a `.env` file in this folder
(a line `APIFY_TOKEN=...`). The token is never printed.

`run` reads a plan (see profile.example/search_plan.json), starts the runs a few at a time, and stops
when the budget is used up: it gives each pay-per-event run a charge cap that fits in what's left,
aborts every run if the total still goes over, and aborts running runs on Ctrl-C. Results go to
<out>/<datasetId>.json and a summary to <out>/runs.json. Running the same command again skips runs
that already finished, so nothing is paid for twice.
"""
import json, os, sys, time, argparse, hashlib, urllib.request, urllib.error, urllib.parse

API = 'https://api.apify.com/v2'
HERE = os.path.dirname(os.path.abspath(__file__))
POLL_SECS = 15
DEFAULT_CAP_USD = 1.00      # charge cap for a run whose plan entry gives none
OTHER_RESERVE_USD = 0.25    # what a run of an actor without per-event pricing is assumed to cost


def token():
    t = os.environ.get('APIFY_TOKEN', '').strip()
    if not t and os.path.exists(os.path.join(HERE, '.env')):
        for line in open(os.path.join(HERE, '.env')):
            k, _, v = line.strip().partition('=')
            if k.strip() == 'APIFY_TOKEN':
                t = v.strip().strip('"\'')
    return t


def call(method, path, body=None, params=None, auth=True, tries=3):
    url = API + path + ('?' + urllib.parse.urlencode(params) if params else '')
    headers = {'Content-Type': 'application/json'}
    if auth:
        tok = token()
        if not tok:
            sys.exit('No Apify token. Put a line APIFY_TOKEN=... in the .env file in this folder (see README).')
        headers['Authorization'] = 'Bearer ' + tok
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data, headers, method=method), timeout=120) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors='replace')[:500]
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(5 * (i + 1)); continue
            raise RuntimeError(f'HTTP {e.code} on {method} {path}: {msg}')
        except (urllib.error.URLError, TimeoutError) as e:
            if i < tries - 1:
                time.sleep(5 * (i + 1)); continue
            raise RuntimeError(f'Network error on {method} {path}: {e}')


def actor_path(actor):
    return '/acts/' + actor.replace('/', '~')


# ---------- pricing ----------
def event_price(ev):
    if 'eventPriceUsd' in ev:
        return ev['eventPriceUsd']
    tiers = ev.get('eventTieredPricingUsd') or {}
    t = tiers.get('FREE') or next(iter(tiers.values()), {})
    return t.get('tieredEventPriceUsd', 0)


def pricing(actor):
    """Return dict(model, item_usd, start_usd, min_cap, text) for an actor's current pricing."""
    d = call('GET', actor_path(actor), auth=False)['data']
    infos = d.get('pricingInfos') or []
    p = infos[-1] if infos else {}
    model = p.get('pricingModel', 'FREE')
    out = dict(model=model, item_usd=0.0, start_usd=0.0, min_cap=p.get('minimalMaxTotalChargeUsd') or 0, text=model)
    if model == 'PAY_PER_EVENT':
        evs = (p.get('pricingPerEvent') or {}).get('actorChargeEvents') or {}
        parts = []
        for name, ev in evs.items():
            price = event_price(ev)
            parts.append(f"{ev.get('eventTitle') or name} ${price:g}")
            if 'start' in name:
                out['start_usd'] += price
            elif ev.get('isPrimaryEvent') or name == 'apify-default-dataset-item':
                out['item_usd'] = max(out['item_usd'], price)
        out['text'] = 'per event: ' + ', '.join(parts)
    elif model == 'PRICE_PER_DATASET_ITEM':
        price = p.get('pricePerUnitUsd')
        if price is None:
            tiers = p.get('tieredPricing') or {}
            price = (tiers.get('FREE') or next(iter(tiers.values()), {})).get('tieredPricePerUnitUsd', 0)
        out['item_usd'] = price or 0
        out['text'] = f"per result ${out['item_usd']:g}"
    elif model == 'FLAT_PRICE_PER_MONTH':
        out['text'] = f"monthly rental ${p.get('pricePerUnitUsd', '?')} (avoid)"
    else:
        out['text'] = 'free actor, you pay platform usage'
    return out


# ---------- commands ----------
def cmd_check(_):
    me = call('GET', '/users/me')['data']
    print('Token works. Apify user:', me.get('username'))
    try:
        lim = call('GET', '/users/me/limits')['data']
        used = (lim.get('current') or {}).get('monthlyUsageUsd')
        cap = (lim.get('limits') or {}).get('maxMonthlyUsageUsd')
        print(f'Used this billing month: ${used:.2f} of ${cap:.2f}' if used is not None and cap else f'Limits: {lim}')
    except Exception as e:
        print('Could not read usage:', e)


def cmd_store(a):
    d = call('GET', '/store', params={'search': a.query, 'limit': a.limit}, auth=False)['data']['items']
    for x in d:
        s = x.get('stats') or {}
        try:
            price = pricing(f"{x['username']}/{x['name']}")['text']
        except Exception:
            price = (x.get('currentPricingInfo') or {}).get('pricingModel', '?')
        print(f"{x['username']}/{x['name']}  | {x.get('title')} | users 30d: {s.get('totalUsers30Days')} | "
              f"rating {x.get('actorReviewRating') or '-'} | {price}")
        print('   ', (x.get('description') or '')[:200].replace('\n', ' '))


def cmd_info(a):
    p = pricing(a.actor)
    print(f'{a.actor}: {p["text"]}' + (f' | minimum charge cap ${p["min_cap"]}' if p['min_cap'] else ''))
    try:
        b = call('GET', actor_path(a.actor) + '/builds/default', auth=False)['data']
        schema = b.get('inputSchema') or (b.get('actorDefinition') or {}).get('input') or {}
        schema = json.loads(schema) if isinstance(schema, str) else schema
        req = set(schema.get('required') or [])
        print('Input fields (* = required):')
        for k, v in (schema.get('properties') or {}).items():
            extra = ''
            if v.get('enum'):
                extra = ' one of: ' + ', '.join(map(str, v['enum'][:12])) + (' ...' if len(v['enum']) > 12 else '')
            if 'default' in v:
                extra += f' (default {json.dumps(v["default"])[:60]})'
            print(f"  {k}{'*' if k in req else ''} [{v.get('type', '?')}] {(v.get('description') or v.get('title') or '')[:160]}{extra}"
                  .replace('\n', ' '))
    except Exception as e:
        print('Could not read the input schema:', e)


def entry_key(i, e):
    return f"{i}:" + hashlib.sha1(json.dumps([e.get('actor'), e.get('input')], sort_keys=True).encode()).hexdigest()[:10]


def cmd_run(a):
    plan = json.load(open(a.plan))
    entries = plan['runs'] if isinstance(plan, dict) else plan
    os.makedirs(a.out, exist_ok=True)
    state_path = os.path.join(a.out, 'runs.json')
    old = {r['key']: r for r in json.load(open(state_path))} if os.path.exists(state_path) else {}

    prices = {}
    for e in entries:
        if e['actor'] not in prices:
            prices[e['actor']] = pricing(e['actor'])

    runs = []
    for i, e in enumerate(entries):
        k = entry_key(i, e)
        r = old.get(k) or dict(key=k, site=e['site'], parser=e.get('parser', 'generic'), actor=e['actor'],
                               note=e.get('note', ''), run_id=None, dataset_id=None, status='PENDING',
                               items=0, cost_usd=0.0, cap_usd=None, attempts=0, error='')
        r['_entry'] = e
        if r['status'] in ('ABORTED-BUDGET', 'SKIPPED-BUDGET', 'START-FAILED', 'ABORTED-BY-USER'):  # give these another chance
            r.update(status='PENDING', attempts=0, prev_cost_usd=r['cost_usd'])
        runs.append(r)

    def save():
        json.dump([{k: v for k, v in r.items() if k != '_entry'} for r in runs], open(state_path, 'w'), indent=1)

    def live_cost(r, run):
        c = run.get('usageTotalUsd') or 0
        p = prices[r['actor']]
        if p['model'] == 'PRICE_PER_DATASET_ITEM' and r['dataset_id']:
            try:
                n = call('GET', f"/datasets/{r['dataset_id']}")['data'].get('itemCount') or 0
                c = max(c, n * p['item_usd'])
            except Exception:
                pass
        return c

    def reserve(r):
        p, e = prices[r['actor']], r['_entry']
        if p['model'] == 'PAY_PER_EVENT':
            return r['cap_usd'] or 0
        if p['model'] == 'PRICE_PER_DATASET_ITEM':
            return (e.get('max_items') or 100) * p['item_usd']
        return e.get('max_charge_usd') or OTHER_RESERVE_USD

    def download(r):
        items, off = [], 0
        while True:
            page = call('GET', f"/datasets/{r['dataset_id']}/items", params={'clean': 'true', 'format': 'json', 'offset': off, 'limit': 1000})
            items += page if isinstance(page, list) else []
            if not isinstance(page, list) or len(page) < 1000:
                break
            off += 1000
        json.dump(dict(datasetId=r['dataset_id'], site=r['site'], parser=r['parser'], actor=r['actor'], items=items),
                  open(os.path.join(a.out, r['dataset_id'] + '.json'), 'w'))
        r['items'] = len(items)

    def abort_all(reason):
        for r in runs:
            if r['status'] == 'RUNNING':
                try:
                    call('POST', f"/actor-runs/{r['run_id']}/abort")
                except Exception as ex:
                    print('  could not abort', r['site'], ex)
                r['status'] = reason
            elif r['status'] == 'PENDING':
                r['status'] = 'SKIPPED-BUDGET'
        save()

    print(f'Budget ${a.budget:.2f}. {len(runs)} runs in the plan, {sum(r["status"] == "PENDING" for r in runs)} to start.')
    try:
        while True:
            # 1. update running runs
            for r in runs:
                if r['status'] != 'RUNNING':
                    continue
                run = call('GET', f"/actor-runs/{r['run_id']}")['data']
                r['dataset_id'] = run.get('defaultDatasetId')
                r['cost_usd'] = round(r.get('prev_cost_usd', 0) + live_cost(r, run), 4)  # includes failed earlier attempts
                st = run.get('status')
                if st in ('SUCCEEDED', 'FAILED', 'TIMED-OUT', 'ABORTED'):
                    download(r)
                    r['status'] = st
                    print(f"  {r['site']} ({r['actor']}): {st}, {r['items']} items, ${r['cost_usd']:.3f}")
                    if st != 'SUCCEEDED' and r['items'] == 0 and r['attempts'] < 2:
                        print('    no items; will retry once')
                        r['status'] = 'PENDING'
                        r['prev_cost_usd'] = r['cost_usd']
                    save()
            spent = sum(r['cost_usd'] for r in runs)
            if spent >= a.budget:
                print(f'Budget reached (${spent:.2f}). Stopping all runs.')
                abort_all('ABORTED-BUDGET')
                break
            # 2. start pending runs while there is room and budget
            running = [r for r in runs if r['status'] == 'RUNNING']
            free = a.budget - sum(r['cost_usd'] for r in runs if r['status'] != 'RUNNING') \
                   - sum(max(reserve(r), r['cost_usd']) for r in running)
            for r in runs:
                if r['status'] != 'PENDING' or len(running) >= a.parallel:
                    continue
                e, p = r['_entry'], prices[r['actor']]
                params = {}
                if e.get('max_items'):
                    params['maxItems'] = e['max_items']
                need_min = max(p['min_cap'], e.get('min_charge_usd') or 0, 0.02)
                if p['model'] == 'PAY_PER_EVENT':
                    cap = round(min(e.get('max_charge_usd') or DEFAULT_CAP_USD, free), 2)
                    if cap < need_min:
                        if not running:
                            print(f"  skipping {r['site']}: only ${free:.2f} of budget left, it needs a cap of ${need_min:.2f}")
                            r['status'] = 'SKIPPED-BUDGET'
                        continue
                    r['cap_usd'] = params['maxTotalChargeUsd'] = cap
                else:
                    need = (e.get('max_items') or 100) * p['item_usd'] if p['model'] == 'PRICE_PER_DATASET_ITEM' \
                        else e.get('max_charge_usd') or OTHER_RESERVE_USD
                    if p['model'] == 'PRICE_PER_DATASET_ITEM' and not e.get('max_items'):
                        params['maxItems'] = 100
                    if need > free:
                        if not running:
                            print(f"  skipping {r['site']}: needs about ${need:.2f}, only ${free:.2f} left")
                            r['status'] = 'SKIPPED-BUDGET'
                        continue
                    r['cap_usd'] = round(need, 2)
                    params['maxTotalChargeUsd'] = round(max(need, need_min), 2)
                try:
                    run = call('POST', actor_path(r['actor']) + '/runs', body=e.get('input') or {}, params=params)['data']
                except RuntimeError as ex:
                    msg = str(ex)
                    if running and any(w in msg.lower() for w in ('memory', 'concurrent', 'limit')):
                        break  # account is busy; try again after a run finishes
                    r['attempts'] += 1
                    r['error'] = msg[:300]
                    print(f"  could not start {r['site']}: {msg[:200]}")
                    if r['attempts'] >= 2:
                        r['status'] = 'START-FAILED'
                    continue
                r.update(run_id=run['id'], dataset_id=run.get('defaultDatasetId'), status='RUNNING', error='')
                r['attempts'] += 1
                running.append(r)
                free -= reserve(r)
                print(f"  started {r['site']} ({r['actor']}), cap ${r['cap_usd']:.2f}")
                save()
            if not any(r['status'] in ('RUNNING', 'PENDING') for r in runs):
                break
            if not running and all(r['status'] != 'PENDING' for r in runs):
                break
            time.sleep(POLL_SECS)
    except KeyboardInterrupt:
        print('\nInterrupted: aborting running runs so they stop costing money.')
        abort_all('ABORTED-BY-USER')
        raise SystemExit(130)

    save()
    print(f"\n{'site':<14} {'actor':<40} {'status':<15} {'items':>6} {'cost':>7}")
    for r in runs:
        print(f"{r['site'][:14]:<14} {r['actor'][:40]:<40} {r['status']:<15} {r['items']:>6} ${r['cost_usd']:>6.3f}")
    print(f"Total: {sum(r['items'] for r in runs)} items, ${sum(r['cost_usd'] for r in runs):.2f} of the ${a.budget:.2f} budget.")
    print('Costs shown are what Apify reports per run; check the Apify console Billing page for the final number.')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('check')
    s = sub.add_parser('store'); s.add_argument('query'); s.add_argument('--limit', type=int, default=8)
    s = sub.add_parser('info'); s.add_argument('actor')
    s = sub.add_parser('run'); s.add_argument('plan'); s.add_argument('--budget', type=float, required=True)
    s.add_argument('--out', required=True); s.add_argument('--parallel', type=int, default=5)
    a = ap.parse_args()
    {'check': cmd_check, 'store': cmd_store, 'info': cmd_info, 'run': cmd_run}[a.cmd](a)


if __name__ == '__main__':
    main()
