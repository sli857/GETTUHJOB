# Job site catalog

Scrapers (Apify "actors") that are known to work with `apify.py` and `rank_jobs.py`. The test run in `fresh_search.md` picks candidates from here. Each person's chosen sites end up in `profile/search_plan.json`.

Prices were checked in November 2026 for the Apify free plan. Run `python3 apify.py info <actor>` for current prices and every input field.

**Notes for every site**
- Sample inputs below are examples from an entry-level software search near Atlanta. Change the keywords, locations and seniority to fit the person.
- "Test size" is a sample big enough to compare sites. "Full size" is a typical size for a normal search.
- Searches covering the last 3 days suit a search run 2–3 times a week. Use 7 days for a weekly search.
- Each entry gives the `parser` value that `rank_jobs.py` needs for that site's output.

## LinkedIn

- **Actor:** `cheap_scraper/linkedin-job-scraper`. **Parser:** `linkedin`.
- **Price:** $0.0007 per job, plus $0.005 per run.
- **Test size:** `maxItems` 150. **Full size:** 300–350 per run.
- **Input:** search URLs built on linkedin.com. Set the filters on the site, then copy the address bar. Useful URL parameters:
  - `f_TPR=r259200` (posted in the last 72 hours; `r604800` is 7 days)
  - `f_E=2` (entry level; 1 internship, 3 associate, 4 mid-senior)
  - `f_JT=F` (full-time)
  - `f_WT=2` (remote)
  - `location=` (a city, metro or state)
  - `keywords=`
  ```json
  {"startUrls": [{"url": "https://www.linkedin.com/jobs/search/?keywords=software%20engineer&location=Atlanta%2C%20Georgia%2C%20United%20States&f_TPR=r259200&f_E=2&f_JT=F"},
                 {"url": "https://www.linkedin.com/jobs/search/?keywords=software%20developer&location=Atlanta%2C%20Georgia%2C%20United%20States&f_TPR=r259200&f_E=2&f_JT=F"}],
   "jobTitleExclude": ["senior", "staff", "lead", "principal", "manager", "intern"],
   "saveOnlyUniqueItems": true, "maxItems": 150}
  ```
- **Notes:** often the site with the most relevant jobs. Leave `useAiJobDescriptionParsing` off, because it costs extra per job.

## Indeed

- **Actor:** `valig/indeed-jobs-scraper`. **Parser:** `indeed`.
- **Price:** about $0.0001 per result, plus $0.001 per run. Very cheap.
- **Test size:** 2 runs × `limit` 60. **Full size:** one run per keyword and city, `limit` 60–150 each.
- **Input:** one keyword and one location per run.
  ```json
  {"country": "us", "title": "entry level software engineer", "location": "Atlanta, GA", "datePosted": "3", "limit": 60}
  ```
- **Notes:** Indeed blocks automated page fetches, so `tailor-resumes.md` skips Indeed jobs. The person has to open those links themselves.

## Glassdoor

- **Actor:** `valig/glassdoor-jobs-scraper`. **Parser:** `glassdoor`.
- **Price:** $0.0004 per result, plus $0.001 per run.
- **Test size:** 2 runs × `limit` 60. **Full size:** one run per keyword and city, `limit` 100–150.
- **Input:**
  ```json
  {"keywords": "entry level software engineer", "location": "Atlanta, GA", "daysOld": 3, "sortBy": "date_desc", "limit": 60}
  ```
- **Notes:** Glassdoor's own salary estimates are shown in the notes, but they don't count as a listed salary.

## Handshake (students and recent graduates)

- **Actor:** `memo23/handshake-jobs-scraper`. **Parser:** `handshake`.
- **Price:** $0.001 per result, plus $0.009 per run. Leave `enrichEmails` off, because it costs $0.005 per job.
- **Test size:** `maxItems` 150. **Full size:** 2–3 runs × 400, splitting the cities across runs. One run returns about 100 jobs.
- **Input:** `roles` are Handshake category slugs. Run `python3 apify.py info` for examples, such as `software-engineering`, `data-analytics` or `nursing`. `locations` are city slugs.
  ```json
  {"roles": ["software-engineering"], "locations": ["atlanta-ga", "charlotte-nc", "nashville-tn"], "remoteOnly": true, "maxItems": 150}
  ```
- **Notes:**
  - It sees only **public** Handshake jobs. Jobs posted only for one school's students need a logged-in account, so check those by hand.
  - Avoid `maximedupre/handshake-jobs-scraper`: it was very slow and returned almost nothing.

## Jobright

- **Actor:** `datascraperes/jobright-jobs-scraper`. **Parser:** `jobright`.
- **Price:** $0.001 per job. **Set `min_charge_usd` to 1.0 in the plan:** runs need a charge cap of at least $1. That's only a cap; a run costs about $0.10–0.20.
- **Test size:** `maxResults` 100. **Full size:** 150 per city.
- **Input:** `seniority` is one or more of: Intern/New Grad, Entry Level, Mid Level, Senior Level, Lead/Staff, Director/Executive.
  ```json
  {"searchQueries": ["software engineer", "software developer"], "location": "Atlanta, GA", "country": "US", "maxResults": 100,
   "includeJobDetails": true, "postedWithinDays": 3, "seniority": ["Intern/New Grad", "Entry Level"], "employmentTypes": ["Full-time"],
   "radiusMiles": 50, "excludeStaffingAgencies": true, "excludeSecurityClearance": true, "excludeUsCitizen": true}
  ```
- **Notes:**
  - Returns many US-remote jobs.
  - `excludeUsCitizen` and `excludeSecurityClearance` suit non-citizens. A US citizen can set them to false.
  - `h1bOnly: true` keeps only known H-1B sponsors.

## Workday career sites

- **Actor:** `fantastic-jobs/workday-jobs-api`. **Parser:** `careersite`.
- **Price:** $0.002 per job. `limit` can't go below 200, so a run can cost up to $0.40.
- **Test size:** `limit` 200. **Full size:** 200.
- **Input:** `locationSearch` uses exact "State, Country" or "City, State, Country" names. `aiExperienceLevelFilter` is one of: 0-2, 2-5, 5-10, 10+.
  ```json
  {"limit": 200, "titleSearch": ["software engineer", "software developer"], "titleExclusionSearch": ["senior", "staff", "principal", "lead", "manager", "intern"],
   "locationSearch": ["Georgia, United States", "North Carolina, United States"], "aiExperienceLevelFilter": ["0-2"],
   "aiEmploymentTypeFilter": ["FULL_TIME"], "removeAgency": true, "descriptionType": "text"}
  ```
- **Notes:**
  - Pulls straight from company career sites, so there are no recruiters and few duplicates.
  - There's no date filter, so `rank_jobs.py` drops posts by `max_age_hours`.

## Greenhouse career sites

- **Actor:** `fantastic-jobs/greenhouse-jobs-api`. **Parser:** `careersite`.
- **Price, sizes and input:** same as Workday.
- **Notes:** Greenhouse is used mostly by tech startups and mid-size companies.

## Hiring Cafe

- **Actor:** `memo23/apify-hiring-cafe-scraper`. **Parser:** `hiringcafe`.
- **Price:** $0.00125 per result, plus $0.005 per run.
- **Test size:** `maxItems` 100. **Full size:** 150.
- **Input:** the `location` field accepts only a country, so a nationwide run yields few local jobs. For one city, set the location on hiring.cafe, then copy the address bar URL into `startUrls`.
  ```json
  {"keyword": "software engineer", "location": "United States", "commitmentTypes": ["Full Time"],
   "seniorityLevels": ["No Prior Experience Required", "Entry Level"], "dateFetchedPastNDays": 3, "maxYoe": 2, "sortBy": "date", "maxItems": 100}
  ```

## Tested and not recommended for entry-level software jobs

These may still suit other fields. They use the `generic` parser, so check the parsed output after a test.

- **Dice** (`worldunboxer/dice-jobs-scraper`): mostly IT consulting firms, and only 500-character job summaries.
- **Built In** (`solidcode/builtin-scraper`): only 6 jobs near Atlanta in 3 days.

## Other fields

For fields with their own job boards (nursing, teaching, finance, government and so on), search the Apify Store:

```
python3 apify.py store "<board name or field> jobs"
```

Prefer actors that meet all of these:
- per-event or per-result pricing (avoid "monthly rental")
- more than about 100 users in the last 30 days
- a rating of 4 or higher

Check the input fields with `python3 apify.py info <actor>` and use `parser: generic`. After the test run, if `rank_jobs.py` parses few jobs from it, write a small parser for its output format in `rank_jobs.py`, next to the others.
