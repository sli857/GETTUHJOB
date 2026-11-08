# Task: first-time setup

You are setting up this job search workflow for a new user. By the end of this session:
- their details are in `profile/`
- their resumes are in `resumes/`
- they know how to run the test search next

The user may not be technical, so explain things plainly. Keep each message short.

## How to run this session

- **Ask a few questions at a time** (2–4), not a long form. Give an example answer with each question. Accept "skip" or "not sure" and pick a sensible default, saying what you picked.
- **Use only what the user tells you or what is in their resume.** Don't guess facts about them.
- **Never ask for or handle passwords or the Apify token in chat.** If the user pastes a token anyway, tell them to create a new one in Apify, since this one is now in the chat history.
- **Write personal details only to the files named here:** `profile/`, `resumes/`, `.env`. Never write them into template files (`README.md`, `setup.md`, `fresh_search.md`, `tailor-resumes.md`, `sites_catalog.md`, `*.py`, `*.sh`, `profile.example/`).
- **Resume after a break:** if `profile/about_me.md` already exists, setup was started or done before. Show what's there, ask what to change, and continue from the first missing step.

## Step 1: Welcome

In 3–4 lines, tell the user what this does and what happens in this session:
1. **Today, about 15 minutes:** answer some questions and add your resume.
2. **Next session:** a test search that tries every job site for about 20 minutes, using at most $2 of free Apify credit. It finds which sites have the most jobs for you.
3. **After that:** each new search is one message (`@fresh_search.md`). Tailored resumes are another (`@tailor-resumes.md`).

## Step 2: Check the tools

Run these and fix what fails:

1. **`python3 --version`**: needs 3.9 or newer. On a Mac without it, the user can run `xcode-select --install`.
2. **`ls "/Applications/Google Chrome.app"`**: Chrome turns resumes into PDFs. If it's missing, ask them to install it. On Linux, `render.sh` also finds `google-chrome` or `chromium`.
3. **`python3 apify.py check`**: confirms the Apify token works. If it fails, walk them through this:
   1. Create a free account at https://apify.com. The free plan includes $5 of credit each month.
   2. In the Apify Console, go to **Settings → API & Integrations** and copy the **Personal API token**.
   3. In this folder, create a file named `.env` with one line, `APIFY_TOKEN=<their token>`. Have them do this themselves, in their own terminal or a text editor, so the token never goes through the chat. For example: `echo 'APIFY_TOKEN=paste_here' > .env`. `.env` is ignored by git.
   4. Run `python3 apify.py check` again.

## Step 3: Interview

Ask in this order, a few at a time. Skip anything the resume already answers clearly, and confirm it instead.

1. **Name and resume header:** phone, email, links and city, exactly as they want them at the top of their resume.
2. **Status:**
   - Current student or recent graduate? Which school and degree, and when do they graduate?
   - Students and recent graduates can use Handshake.
3. **Target roles:**
   - What job titles are they looking for? For example: "software engineer, backend developer" or "financial analyst".
   - Anything they don't want, even if the title is close?
4. **Seniority:**
   - Internship, new grad / entry level, or experienced?
   - What's the most years of experience a job can ask for and still be worth applying to?
5. **Job type:** full-time, part-time, contract, internship?
6. **Work authorization:** choose one.
   - US citizen. Then ask: are jobs that need a security clearance OK?
   - Green card holder.
   - F-1 student on OPT / STEM OPT.
   - Needs visa sponsorship (H-1B) to start.
7. **Locations:**
   - Their home city.
   - **Tier 1:** where they most want to work, such as a metro area.
   - **Tier 2:** acceptable, such as a nearby region, a time zone or remote.
   - Is everything else skipped or kept at a lower priority?
8. **Salary:** the minimum yearly pay, or none.
9. **Skills:** suggest a list from their resume. Ask which matter most for the jobs they want.
10. **Job boards:**
    - Which sites have they used, and which worked?
    - Any boards for their field? For example, nursing, teaching, government or finance boards.
11. **Budget:** the test run is capped at $2 by default. Is that OK?

## Step 4: Resumes

1. **Get the files.** Ask the user to put their resume files in `resumes/originals/`. Create the folder if needed. Any of these work:
   - a long "everything" resume
   - one or more one-page resumes
   - just one resume

   If they drag a file into the chat instead, copy it into `resumes/originals/`.
2. **Read them.**
   - **PDF:** use your file-reading tool. If you can't read PDFs, try `pdftotext` (if installed).
   - **.docx on a Mac:** `textutil -convert txt -stdout <file>`.
   - **If nothing works:** ask for a .docx, or for the text pasted into the chat.
3. **Write `resumes/general.md`.**
   - It holds everything from all their resumes, merged and without duplicates: contact header, education, every job, project, activity and award with all bullets, and skills.
   - Use plain Markdown: bold section headings, one bold line per job or project with its date after a `|`, and `- ` bullets.
   - **Copy facts exactly. Don't improve, add or drop numbers.**
4. **Write `resumes/one_page.md`.** This is their best one-page resume for the roles they want.
   - If they gave a one-page resume for these roles, copy it.
   - Otherwise, pick the most relevant content from `general.md`.
5. **Build `resumes/base.html`.**
   - Turn `one_page.md` into HTML, following the structure of `resumes/example_base.html` exactly. Keep its `<link>` and `<script>` tags, and change the `<title>` to "<Name> Resume".
   - Run `resumes/render.sh resumes/base.html`. Adjust until it prints `pages=1` and `fill` between 0.95 and 0.99:
     - **Too full:** shorten or cut the weakest bullets.
     - **Too empty:** add relevant bullets from `general.md`.
   - Only as a last resort, adjust the CSS variables on `<body>`, as described in `tailor-resumes.md` step 5.
6. **Have them check it.** Ask the user to open `resumes/base.pdf` and say if anything is wrong. Fix what they point out.

## Step 5: Write the profile

1. **`profile/about_me.md`.** Follow the sections of `profile.example/about_me.md`, filled with their answers. Add a short "Resume tips" section saying which items in `general.md` suit which kinds of roles.
2. **`profile/rank_config.json`.** Start from `profile.example/rank_config.json`, which is set up for entry-level software jobs near Atlanta, and adapt every part to the user:
   - **`titles.include`:** words that appear in titles of jobs they want. Make it broad; `exclude` does the narrowing.
   - **`titles.exclude`:**
     - seniority words above their level (senior, staff, lead, principal, manager, director, `iii`)
     - intern words, unless they want internships
     - roles and specialties they don't want
   - **`titles.exclude_unless_core` and `titles.core`:** for ambiguous words that are only OK when the title also names the main role. Clear both if not needed.
   - **`titles.role_bonus`:** the main role names.
   - **`seniority`:**
     - `max_years`
     - `title_bonus` and `desc_bonus`: words for their level, such as "new grad|entry|junior" or "senior|lead"
     - `title_penalty`: words for one level above. For experienced people, clear it.
     - `years_bonus`: favor the experience levels they fit.
   - **`skills`:** 8–12 skills from their resume that the target jobs ask for. Each gets a regex pattern and a weight from 1 to 3. The weights should add up to about 25, so `min_fit` keeps its meaning.
   - **`min_salary`:** their minimum, or `null`.
   - **`work_authorization`:** `status` and `exclude_clearance_jobs`.
   - **`locations.tiers`:**
     - **Tier 1 `match`:** a regex of the metro's city names, including suburbs. List suburbs with their state where names are common, e.g. `decatur, ga`.
     - **Tier 2:** nearby cities, plus `state_codes` and state names for regions.
     - **`remote`:** `{"tier": 2, "name": "Remote (US)"}`, or `null` if remote jobs are unwanted.
     - **`other`:** `null` to drop everything else, or a tier to keep it.
   - **`max_age_hours` and `site_order`:** keep the defaults for now. The test run updates them.
   - **`flags`:** notes worth seeing in the CSV, such as `"2027 start": "\\b2027\\b"`. Clear it if none.
3. **Check the config.** Run `python3 rank_jobs.py --check` and fix any errors.
4. **Test the location tiers.** Pick five location strings, for example "Decatur, GA", "Remote" and "Austin, TX". Run each through the `tier()` logic with a short Python snippet, and show the user the results.

## Step 6: Wrap up

1. **Summarize.** List what was saved, in a few lines: `profile/about_me.md`, `profile/rank_config.json`, `resumes/general.md`, `resumes/one_page.md`, `resumes/base.html` and `resumes/base.pdf`, and `resumes/originals/`.
2. **Back it up in their own private repo.** Point to the README section "Your own copy" if they haven't done that yet. Offer to commit with `git add profile resumes && git commit -m "My profile and resumes"`. Commit only if they say yes, and never push unless they ask.
3. **Next step.** Tell them: "Start a new chat in this folder and send `@fresh_search.md`. It runs the test search, using at most $2, and shows which job sites work best for you."
