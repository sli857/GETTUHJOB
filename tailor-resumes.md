# Task: tailored resumes for my job list

You are my job application secretary. In this session, you take the next jobs from my ranked job list. For each one, decide whether I should apply. If yes, build a one-page PDF resume tailored to that job.

I submit applications myself. Never apply, email or sign in anywhere.

**How many jobs:** if my message after this file gives a number ("3"), an `apply_order` ("#12"), a job description or a URL, do that. Otherwise do the **next 5 jobs**, then stop.

**Don't read** `README.md`, `setup.md`, `rank_jobs.py`, `apify.py`, old CSVs or any PDF. Everything you need is here.

## Files

| Path | What it is |
|---|---|
| `profile/about_me.md` | Who I am: target roles, seniority, work authorization, locations, resume file prefix and resume tips. **Read it first.** |
| `search_results/top_jobs_<date>.csv` | Ranked jobs. Use the one with the newest date. Useful columns: `apply_order`, `company`, `title`, `location`, `salary`, `min_yrs`, `notes`, `url` |
| `applications.csv` | Log of jobs already handled. Create it if missing |
| `resumes/general.md` | Everything I've done. Source of facts |
| `resumes/base.html` | My one-page resume as HTML. Copy it to start each tailored resume |
| `resumes/resume.css`, `resumes/fill.js`, `resumes/fonts/` | Shared style and fill measurement. Don't read or edit them |
| `resumes/render.sh` | Turns an HTML resume into a PDF and reports page count and fill |
| `tailored/` | Your output: one `.html` and one `.pdf` per job |

Read `about_me.md`, `general.md` and `base.html` once at the start of the session, not once per job. `<Prefix>` below means the "Resume file prefix" in `about_me.md`.

## Steps for each job

### 1. Pick the job

1. Take the lowest `apply_order` in the newest CSV in `search_results/` whose `url` isn't in `applications.csv`.
2. Read only the CSV rows you need (use `head`, `grep` or `sed`), not the whole file.

### 2. Get the job description

**First, every job:** run `python3 fetch_job.py "<url>" --saved-only`.
- **If it prints `SAVED DESCRIPTION`,** that's the posting text saved during the search. Use it and don't fetch the page. Read it to the end, since clearance and visa lines are often last. Don't repeat it in chat.
- **If it prints `NO SAVED DESCRIPTION`:**
  - **Indeed jobs (`url` contains `indeed.com`): skip them.** Don't fetch them (Indeed blocks automated fetches), and don't ask me for the description. Log the job as `skip` with reason `Indeed posting, no saved description`, and report it as `#41 Acme, Analyst: SKIP (Indeed, no saved description)`. Go on to the next job. It counts toward the batch.
  - **All other jobs:** fetch the `url`.
    - **If you have a web fetch tool** (Claude Code's WebFetch, or its web-fetch agent), use it. Ask for only the parts listed below.
    - **Otherwise** (e.g. Codex), run `python3 fetch_job.py "<url>"`, which prints the page text.

The parts you need:
- work authorization, visa, citizenship or clearance text
- years of experience
- required and preferred skills
- a 2-line role summary
- location and salary

If a fetched page fails to load or needs a login (Handshake always does, and LinkedIn sometimes does), log the job as `blocked` and move on.

### 3. Decide: apply or skip

Check in this order:

1. **Work authorization.** Use my status in `about_me.md`.
   - **Skip** jobs whose requirements I can't meet, for example:
     - US citizenship, when I'm not a citizen
     - a green card, when I don't have one
     - "no OPT/F-1", when I'm on OPT
     - "no sponsorship", when I need sponsorship
   - **Flag but apply** anything `about_me.md` says to flag.
2. **Clearances.** If `about_me.md` says to skip clearance jobs, skip any job that requires a clearance, even if the posting never says "citizenship" or "clearance".
   - Look for: Secret, Top Secret, TS/SCI, Tier 3 / T3 / T-3, Tier 5 / T5, DOE Q or L, polygraph, "active clearance", "able to obtain a clearance", or a clearance required "under the PWS" or contract.
   - Defense and federal contractor jobs often bury this in one line at the end, so read to the bottom.
   - If the only requirement is Public Trust, flag it instead of skipping, because some Public Trust jobs accept non-citizens.
3. **Experience.** Skip if it requires more years than `about_me.md` allows. One year over: apply, but mark it as a stretch.
4. **Fit.** Skip if most of the core required skills aren't in `general.md`, or the role is one `about_me.md` says I'm not interested in.

### 4. Choose the content

- **If `base.html` already fits the job,** keep its content and only trim it to one page. Say "base resume fits."
- **Otherwise,** swap in the experience, projects, bullets and skills from `general.md` that best match the job, and use the job's terms where my experience supports them. Follow the "Resume tips" in `about_me.md`. Explain your picks in 2 or 3 sentences, no more.

### 5. Build the one-page resume

1. **Copy the base.** Copy `resumes/base.html` to `tailored/<Prefix>-resume-<company>.html`.
   - Use the company as a lowercase slug, such as `acme`.
   - If that file already exists, add the role, as in `acme-backend`.
   - Then make your changes with small edits to that copy.
2. **Render it.** Run `resumes/render.sh tailored/<Prefix>-resume-<company>.html`. It prints:
   - `pages=`: must be 1.
   - `fill=`: the share of the page height the content uses. **The target is 0.95 to 0.99.** Over 1.00 means content is cut off at the bottom. Under 0.95 means there's empty space at the bottom.
3. **Edit and re-render until fill is in range:**
   - **Too full:**
     1. Shorten bullets that end with a line of only 1 to 3 words.
     2. Cut the weakest bullet for this job.
     3. Drop the least relevant project.
   - **Too empty:** add a relevant bullet or project from `general.md`.
   - **Last resort only:** fine-tune with CSS variables on the `<body>` tag, for example `<body style="--fs:9.6pt; --sec-gap:6pt">`. Available:
     - `--fs`: font size, default 9.75pt. Keep it between 9.5 and 10.5pt.
     - `--lh`: line height, default 1.17.
     - `--sec-gap`: default 7pt.
     - `--entry-gap`: default 4pt.
     - `--margin-x` and `--margin-y`: default 0.45in.
4. **Don't open the PDF or take screenshots.** The `fill` number is your check.

Keep the HTML structure of `base.html`:
- Each job or project is a `<div class="entry">`.
- It has a `.head` line, with the title on the left and the date in `<span class="date">` on the right.
- Then an optional `<p class="sub">` and a `<ul>` of bullets.
- Keep the `<link>` and `<script>` tags as they are.

### 6. Log it

Append a row to `applications.csv`. If the file doesn't exist, create it with this header first:

```
date,csv_file,apply_order,company,title,url,decision,reason,resume_file
```

- `csv_file`: the bare file name of the list you used (e.g. `top_jobs_2026-11-06.csv`), without the `search_results/` folder.
- `decision`: `apply`, `skip` or `blocked`.
- `reason`: under about 12 words.
- `resume_file`: fill it only for `apply`.

### 7. Report

After each job, write one short block in chat:

```
#3 Acme, Software Engineer: APPLY (OPT ok, 0-2 yrs, Python/Java/CI match)
Resume: tailored/<Prefix>-resume-acme.pdf (added the course planner, cut the crawler; fill 0.97)
Link: <url>
```

If the description came from a saved file, add `(saved JD)` at the end of the first line, since that job may have closed after the search.

For a skip: `#4 Acme, Engineer II: SKIP (requires US citizenship)`.

At the end, list any blocked jobs with their links so I can paste the descriptions. When I paste one, run steps 3 to 7 for it and replace its `blocked` row in the log.

## Writing rules

- **No em-dashes (—).** Use commas, colons or parentheses instead. En-dashes (–) in date ranges are fine.
- **No words that read as AI-written:** leverage, spearhead, robust, seamless, delve, passionate, cutting-edge, innovative, dynamic, synergy, utilize, showcase, foster, harness, streamline, elevate, empower, transformative, pivotal, meticulous, engineered (as a verb), "proven track record", "results-driven", "fast-paced environment". If a bullet in `general.md` uses one of these, reword it when you use it.
- **Plain, specific wording:** built, shipped, fixed, wrote, cut, found, ran, with real numbers.
- **Only facts from `general.md`.** Rewording and shortening are fine. New tools, numbers, results or claims are not. If a job wants a skill I don't have, leave it out and don't hint at it.
- **Keep the header, education and skills sections.** Edit skill lines to put the job's matching skills first, using only skills I have.

## Saving tokens

- Keep reasoning short. The report in step 7 is all I need to see.
- Use small edits to the tailored HTML between renders. Don't rewrite the whole file.
- Don't re-read files you have already read this session.
- Stop after the requested number of jobs.
