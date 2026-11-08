# Notes for AI assistants

This folder is a job search workflow. The user starts tasks by sending one of these files:
- `README.md`: setup, which follows `setup.md`
- `fresh_search.md`: job search
- `tailor-resumes.md`: tailored resumes

Follow the file they send.

## Privacy

- **The user's personal data lives only in these places:**
  - `profile/`
  - `resumes/originals/`, `resumes/general.md`, `resumes/one_page.md`, `resumes/base.html`
  - `search_results/`
  - `applications.csv`
  - `tailored/`
  - `.env`
- **Template files must stay generic,** so updates can be shared:
  - `README.md`, `setup.md`, `fresh_search.md`, `tailor-resumes.md`, `sites_catalog.md`, `AGENTS.md`, `CLAUDE.md`
  - `*.py`, `*.sh`
  - `profile.example/`
  - `resumes/example_base.html`, `resume.css`, `fill.js`
- **Never read or print `.env`.** It holds the Apify token.
- **Never commit or push unless the user asks.** Never push to the `template` remote.

## Money

- Apify scrapers cost the user money. Start them only through `apify.py run`, always with `--budget`.
- Before starting runs, state the estimated cost.
- Never raise a budget, charge cap or result limit without asking.

## Writing rules

Every resume line, cover letter or application answer you write for the user follows these rules:

- **No em-dashes (—).** Use commas, colons or parentheses. En-dashes (–) in date ranges are fine.
- **No words that read as AI-written,** such as: leverage, spearhead, robust, seamless, delve, passionate, cutting-edge, innovative, dynamic, synergy, utilize, showcase, foster, harness, streamline, elevate, empower, transformative, pivotal, meticulous, "proven track record", "results-driven", "fast-paced environment".
- **Plain, specific wording:** built, shipped, fixed, wrote, cut, found, ran, with real numbers.
- **Only facts from the user's resumes or that they confirmed.** Nothing invented.
