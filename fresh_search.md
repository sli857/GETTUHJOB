# Task: job search

Scrape job sites with Apify, rank the results with `rank_jobs.py`, and save `search_results/top_jobs_<today>.csv`.

- **First time:** this is a **test run**. It tries every likely site on a small budget, so the user can pick the sites that work best for them.
- **After that:** it's a **normal run** that uses the sites they picked.

## Rules for every run

- **Money:** Apify charges the user's account, and only `apify.py` may start runs.
  - Never start runs that could cost more than the budget in `profile/about_me.md` (test run) or `profile/search_notes.md` (normal run) without asking.
  - Never raise a run's `max_charge_usd`, `max_items` or the input's result limits without asking.
  - `apify.py` enforces the budget with charge caps per run and stops everything once the total is reached. Always pass `--budget`.
- **Failures:** if a run fails, `apify.py` retries it once. If it fails again, report it and move on. Don't retry by hand.
- **Interrupted runs:** if `apify.py` stops partway (network error, Ctrl-C), run the same command again. Runs that already finished are skipped, so nothing is paid for twice.
- **Personal details** go only in `profile/` and `search_results/`. Never edit template files (`README.md`, `setup.md`, this file, `sites_catalog.md`, `profile.example/`) with personal details.
- **Tokens:** read the big data files only through `rank_jobs.py`. Never open `search_results/raw/` files directly.

## Step 0: Check

1. **Setup:** `profile/about_me.md` and `profile/rank_config.json` must exist. If either is missing, tell the user to run setup first by sending `@README.md`, and stop.
2. **Token:** run `python3 apify.py check`. If it fails, point to the README section "Apify account and token" and stop.
3. **Run type:** if `profile/search_plan.json` exists, do **Normal run**. Otherwise do **Test run**.

---

## Test run (first time only)

### 1. Plan the test

1. Read `profile/about_me.md`, `profile/rank_config.json` and `sites_catalog.md`.
2. Choose candidate sites from the catalog that could suit this user:
   - **Handshake:** only for students and recent graduates.
   - **Jobright and Hiring Cafe:** mostly US jobs.
   - **Workday and Greenhouse career sites:** good for most office jobs.
3. **Other fields:** if their field has its own job boards, search for 1–2 more with `python3 apify.py store "<field> jobs"`, using the catalog's selection rules. Check each with `python3 apify.py info <actor>`.
4. **Write `profile/test_plan.json`.** Use the same format as `profile.example/search_plan.json`:
   - one or two runs per candidate site, at the catalog's **test size**
   - inputs adapted to the user's roles, seniority, locations and work authorization
   - each run's `max_charge_usd` set to about 1.5 × its estimated cost (minimum $0.05)
   - Jobright needs `min_charge_usd: 1.0`
5. **Estimate each run's cost:** expected results × price per result, plus the start fee. Prices come from the catalog or `apify.py info`. The total estimate must stay under the test budget, $2 unless `about_me.md` says otherwise.
6. **Show the user a short table** (site, what it searches, estimated cost) and the total. Ask them to confirm before starting.

### 2. Run it

```
python3 apify.py run profile/test_plan.json --budget <test budget> --out search_results/raw/test_<today>
```

It prints progress every few runs and takes about 10–20 minutes. Use a long timeout, or run it in the background and wait for it to finish.

### 3. Rank and check the filters

```
python3 rank_jobs.py search_results/raw/test_<today> search_results/top_jobs_<today>.csv \
    --stats search_results/raw/test_<today>/stats.json --dropped search_results/raw/test_<today>/dropped.csv
```

1. **Read the stats.** Read `stats.json` and the `drops` line.
2. **Check what the filters dropped.** Read about 30 rows of `dropped.csv` (`grep` by reason, `head`), especially:
   - `title not a target role`: are good jobs dropped? Widen `titles.include` or narrow `titles.exclude`.
   - `outside target locations`: are tier 1 or 2 places missing from `locations`?
   - `work authorization/clearance`: are the drops correct?
3. **Check what was kept.** Read the first 15 rows of the CSV. Is anything there that clearly shouldn't be? Tighten the config.
4. **Re-rank after edits.** Rank again after each config change. Ranking is free, and re-ranking the same folder doesn't re-scrape. Stop after 3 rounds of changes, and tell the user what changed.
5. **Generic sites:** for a site using the `generic` parser where few jobs were parsed (`parsed` far below `downloaded`), write a parser for its format in `rank_jobs.py`, next to the others. Then re-rank.

### 4. Compare sites and choose

1. **Show a table per site:** jobs downloaded, jobs kept, tier 1 jobs kept, average fit, cost, and cost per kept job. Sites are judged on their unique jobs, since a job found on several sites is listed under the first site in `site_order`.
2. **Recommend which sites to keep.** Drop sites with almost no kept jobs, or a high cost per kept job, unless the user wants them. Usually 4–6 sites are worth keeping.
3. **Ask the user to confirm the choice.** Then ask how often they'll search: 2–3 times a week, or weekly. That sets how far back each search looks (3 or 7 days).

### 5. Save the normal search plan

1. **Write `profile/search_plan.json`** for the chosen sites:
   - scale each run up to the catalog's **full size**, adjusted by what the test returned
   - set each date filter to match how often they search
   - set each `max_charge_usd` to about 1.5 × its new estimate
2. **Update `profile/rank_config.json`:**
   - `site_order`: the best sites first
   - `max_age_hours`: per site, about the search interval plus a day, and 30 days for career sites
3. **Write `profile/search_notes.md`:**
   - the date and the per-site table from step 4
   - which sites were kept or dropped, and why
   - the estimated cost of one normal search
   - a line `Budget per search: $<estimate × 1.3, rounded up to $0.25>`. Tell the user they can change it.

### 6. Report

1. The new list file and how many jobs it has.
2. What the test cost.
3. The chosen sites.
4. The expected cost per search, and how many searches the $5 monthly free credit covers.
5. Next steps:
   - send `@fresh_search.md` in a new chat for each search
   - send `@tailor-resumes.md` (or run `./run_batches.sh`) to build tailored resumes from the list

---

## Normal run

1. **Read the plan.** Read `profile/search_notes.md` for the budget, and summarize `profile/search_plan.json` in one line per site.
   - Runs with `"enabled": false` are turned off: `apify.py` skips them. Leave them out of the summary and the sum below.
   - If the summed `max_charge_usd` of the runs that are on is within the budget, go ahead.
   - If not, show the numbers and ask first.
2. **Run it:**
   ```
   python3 apify.py run profile/search_plan.json --budget <budget per search> --out search_results/raw/<today>
   ```
   If `search_results/raw/<today>` is from an earlier full search today and the user wants a new one, use `<today>_2`.
3. **Rank it:**
   ```
   python3 rank_jobs.py search_results/raw/<today> search_results/top_jobs_<today>.csv --stats search_results/raw/<today>/stats.json
   ```
   Jobs already in `applications.csv` are left out automatically.
4. **Report:**
   - jobs kept per site, the total, and what the search cost
   - any site that failed or returned nothing

   If a site has returned nothing two searches in a row, the scraper may be broken. Suggest checking it with `python3 apify.py info <actor>`, or replacing it from `sites_catalog.md`.
