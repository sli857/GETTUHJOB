# Job Search Assistant

> **For the AI assistant:** if the user sent you this file (for example `@README.md`) with no other request, they want setup.
> - If `profile/about_me.md` doesn't exist, follow `setup.md` from the start.
> - If it exists but `profile/search_plan.json` doesn't, setup is done or partly done. Finish any missing setup steps, then tell them to start a new chat and send `@fresh_search.md` for the test run.
> - If both exist, explain how to run a search (`@fresh_search.md`) and tailor resumes (`@tailor-resumes.md`), and ask what they'd like to do.

This project finds jobs that fit you on LinkedIn, Indeed, Glassdoor, Handshake, Jobright, Hiring Cafe and company career sites. It drops the ones you can't or don't want to apply to, and ranks the rest into one list. Then your AI assistant (Claude Code or Codex) builds a one-page resume tailored to each job worth applying to.

You still submit every application yourself.

## What it costs

- **Apify** runs the job-site scrapers. The free plan includes **$5 of credit each month**.
  - The one-time test run is capped at **$2**.
  - A normal search usually costs **$0.50–$2**, depending on how many sites and cities you search.
  - The scripts enforce the budget: every run gets a spending cap, and everything stops once the total is reached.
- **Your AI subscription** (Claude or ChatGPT) does the reading and writing. A setup session, a search, or a batch of 5 tailored resumes each takes one normal chat session's worth of usage.

## One-time setup

### 1. Your own copy

Keep your copy in a private repository that only you can see, because it will hold your resumes and job list. Don't use GitHub's Fork button: a fork of a private repo stays visible to the repo's owner, and it's deleted if your access is removed.

```
git clone https://github.com/sli857/GETTUHJOB.git job-search
cd job-search
git remote rename origin template
```

Create an **empty private** repository on GitHub (no README), then:

```
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

From then on, `git push` backs up your data to your repo. To get updates to the template later, run `git pull template main`. Your personal files never conflict with updates, because they live in separate files (`profile/`, `resumes/`, `search_results/`).

### 2. Tools

- **An AI coding assistant:** [Claude Code](https://claude.com/claude-code) or [Codex](https://developers.openai.com/codex), opened in this folder.
- **Python 3.9+:** check with `python3 --version`. On a Mac, `xcode-select --install` provides it.
- **Google Chrome:** used to turn resumes into PDFs.
- **macOS or Linux:** the shell scripts use `zsh`.

### 3. Apify account and token

1. Sign up for free at [apify.com](https://apify.com).
2. In the Apify Console, open **Settings → API & Integrations** and copy your **Personal API token**.
3. In this folder, create a file named `.env` containing one line. Don't paste the token into the AI chat.
   ```
   echo 'APIFY_TOKEN=your_token_here' > .env
   ```
   `.env` is ignored by git, so it never gets uploaded.
4. Check it: `python3 apify.py check`.

## How to use it

Start each step in a **new chat**, from this folder. In Claude Code or Codex, type `@` and pick the file to send it.

| When | Send | What happens |
|---|---|---|
| **First time** | `@README.md` | **Setup, about 15 minutes.** The assistant checks your tools, asks about the jobs you want, your locations, work authorization and salary, and asks for your resume. Put your resume files (PDF, Word, text; one or several) in `resumes/originals/`. It saves your profile and builds a one-page HTML/PDF resume. |
| **Second time** | `@fresh_search.md` | **Test run, about 20 minutes, at most $2.** It tries every likely job site with a small search, shows how many good jobs each one found and what they cost, and you pick the sites to keep. It saves your first ranked list. |
| **Each search after that** | `@fresh_search.md` | **Normal search, about 15 minutes.** It searches your chosen sites and saves `search_results/top_jobs_<date>.csv`, best jobs first. Jobs you've already handled are left out. |
| **To apply** | `@tailor-resumes.md` | **Tailored resumes.** It works through the next 5 jobs on the list: checks if each one fits, and builds a tailored one-page PDF in `tailored/`. You can also add a number (`@tailor-resumes.md 3`), a list position (`#12`), or a job link or description. |
| **Many jobs, unattended** | `./run_batches.sh 4` in a terminal | Runs 4 tailoring sessions of 5 jobs in a row with Claude Code. Use `./run_batches.sh 4 --codex` for Codex. It stops early when the list runs out or a session logs nothing. Each session uses your AI subscription, so start small. |

Indeed blocks automated page reads, so tailoring skips Indeed jobs. Open those links yourself.

## What's in this folder

| Path | What it is | Yours or template |
|---|---|---|
| `README.md`, `setup.md`, `fresh_search.md`, `tailor-resumes.md` | Instructions for you and the assistant | template |
| `sites_catalog.md` | Job site scrapers that work, with prices and example inputs | template |
| `apify.py` | Starts Apify scrapers, enforces the budget, downloads results | template |
| `rank_jobs.py` | Filters and ranks jobs using `profile/rank_config.json` | template |
| `fetch_job.py` | Prints a job page as text (for assistants without a web tool) | template |
| `run_batches.sh` | Several tailoring sessions in a row | template |
| `profile.example/` | Example profile (a made-up entry-level software engineer) | template |
| `resumes/resume.css`, `fill.js`, `fonts/`, `render.sh`, `example_base.html` | Resume style and the HTML-to-PDF script | template |
| `profile/` | Your details, ranking rules, chosen sites and search budget | yours |
| `resumes/originals/`, `general.md`, `one_page.md`, `base.html` | Your resumes | yours |
| `search_results/` | Your ranked job lists. Raw scraper data in `raw/` isn't uploaded | yours |
| `applications.csv`, `tailored/` | Log of jobs handled, and tailored resumes | yours |
| `.env` | Your Apify token, never uploaded | yours |

## How ranking works

`rank_jobs.py` reads what the scrapers downloaded and applies the rules in `profile/rank_config.json`:

1. **Drops** jobs that:
   - are already in `applications.csv`
   - have titles outside your target roles or level
   - your work authorization rules out (citizenship, green card, no OPT, no sponsorship, security clearance)
   - ask for more years of experience than your limit
   - list a salary below your minimum
   - are too old
   - come from staffing or OPT-placement firms
   - are outside your locations
   - score too low
2. **Scores fit:**
   - points for your skills in the description
   - points for your level in the title and description
   - points for a listed salary at or above your minimum, and for a fresh post
   - points for OPT- or sponsorship-friendly wording, when that applies to you
3. **Orders** jobs by site (your best site first), then location tier, then fit score. A job found on several sites appears once.

The setup and test-run sessions write and tune the rules. You can ask the assistant to change them any time, e.g. "also include data analyst jobs" or "raise the minimum salary to $90k".

## CSV columns

| Column | Meaning |
|---|---|
| `apply_order` | Overall order to apply in |
| `platform`, `platform_rank` | Source site and rank within that site |
| `tier`, `area` | Location tier (1 = where you most want to work) |
| `fit_score` | Higher means a better match |
| `title`, `company`, `location`, `posted`, `salary` | From the posting. Salaries are annualized: hourly pay × 2080. |
| `min_yrs` | Minimum years of experience found in the description (blank if not stated) |
| `skills` | Which of your skills the posting mentions |
| `notes` | Things to check before applying, e.g. no visa sponsorship, salary not listed, years not stated, posted N days ago |
| `url` | Link to the posting |

## Tips

- **Check flagged rows by hand.** The filters are a first pass, especially rows marked "yrs not stated" or "salary not listed".
- **Don't use bots on LinkedIn Easy Apply.** It's against LinkedIn's terms and can get your account banned. This project never applies for you.
- **If a site keeps returning nothing,** its scraper may have broken. Ask the assistant to check it, or to replace it from `sites_catalog.md`.
