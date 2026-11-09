'use strict';
// Job search dashboard. Talks only to dashboard.py on this computer.

// ---------- helpers ----------
const $ = (s, el = document) => el.querySelector(s);

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'value') el.value = v;
    else if (k === 'checked') el.checked = true;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

async function api(path, method = 'GET', body) {
  const opts = { method };
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(path, opts);
  let data = {};
  try { data = await r.json(); } catch (e) { /* not JSON */ }
  if (!r.ok || data.ok === false) throw new Error(data.error || data.message || `HTTP ${r.status}`);
  return data;
}

const clone = (o) => JSON.parse(JSON.stringify(o));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const money = (x) => (x == null || x === '' || isNaN(x) ? '—' : '$' + Number(x).toFixed(2));
const getPath = (o, p) => p.split('.').reduce((x, k) => (x == null ? undefined : x[k]), o);
function setPath(o, p, v) {
  const ks = p.split('.');
  let x = o;
  for (const k of ks.slice(0, -1)) {
    if (x[k] == null || typeof x[k] !== 'object') x[k] = {};
    x = x[k];
  }
  x[ks[ks.length - 1]] = v;
}

function autogrow(t) {
  const fit = () => { t.style.height = 'auto'; t.style.height = t.scrollHeight + 2 + 'px'; };
  t.addEventListener('input', fit);
  requestAnimationFrame(fit);
  return t;
}

// Split a regex like "a|b|(c|d)" into its top-level alternatives, and join them back.
function splitAlt(re) {
  if (!re) return [];
  const out = [];
  let depth = 0, inClass = false, cur = '';
  for (let i = 0; i < re.length; i++) {
    const c = re[i];
    if (c === '\\') { cur += c + (re[i + 1] || ''); i++; continue; }
    if (inClass) { if (c === ']') inClass = false; cur += c; continue; }
    if (c === '[') inClass = true;
    else if (c === '(') depth++;
    else if (c === ')') depth--;
    if (c === '|' && depth === 0) { out.push(cur); cur = ''; continue; }
    cur += c;
  }
  out.push(cur);
  return out;
}
const joinAlt = (text) => text.split('\n').map((s) => s.trim()).filter(Boolean).join('|');
function reProblem(pattern) {
  if (!pattern) return '';
  try { new RegExp(pattern); return ''; } catch (e) { return e.message.replace(/^Invalid regular expression: /, ''); }
}

function pageHead(title, text) {
  return h('div', { class: 'page-head' }, h('h1', {}, title), text ? h('p', {}, text) : null);
}
function code(s) { return h('code', {}, s); }
function field(label, control, hint) {
  return h('div', { class: 'field' }, h('label', {}, label), control, hint ? h('div', { class: 'hint' }, hint) : null);
}
function pill(decision) { return decision ? h('span', { class: 'pill ' + decision }, decision) : ''; }
function extLink(url, text) { return url ? h('a', { href: url, target: '_blank', rel: 'noopener noreferrer' }, text || url) : ''; }

// ---------- unsaved changes ----------
let dirty = false;
window.addEventListener('beforeunload', (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

// A sticky bar with a message, Revert and Save. Also asks for confirmation when needed.
function saveBar({ onSave, onRevert }) {
  const msg = h('span', { class: 'msg' });
  const revert = h('button', { class: 'btn', disabled: true, onclick: () => onRevert() }, 'Revert');
  const save = h('button', { class: 'btn primary', disabled: true, onclick: () => onSave() }, 'Save');
  const actions = h('div', { class: 'actions' }, revert, save);
  const el = h('div', { class: 'savebar' }, msg, actions);
  let isDirty = false, blocked = '';
  const bar = {
    el,
    show(text, kind = '') { msg.textContent = text; msg.className = 'msg ' + kind; },
    setDirty(v) {
      isDirty = v; dirty = v;
      revert.disabled = !v;
      save.disabled = !v || !!blocked;
      if (blocked) bar.show(blocked, 'err');
      else if (v) bar.show('Unsaved changes.');
      else if (msg.className !== 'msg ok') bar.show('');
    },
    block(reason) { blocked = reason || ''; bar.setDirty(isDirty); },
    busy(v) { save.disabled = v || !isDirty || !!blocked; revert.disabled = v || !isDirty; if (v) bar.show('Saving…'); },
    ask(text, onYes) {
      bar.show(text, 'ask');
      const cancel = h('button', { class: 'btn', onclick: () => { actions.replaceChildren(revert, save); bar.setDirty(isDirty); } }, 'Cancel');
      const yes = h('button', { class: 'btn primary', onclick: () => { actions.replaceChildren(revert, save); onYes(); } }, 'Confirm and save');
      actions.replaceChildren(cancel, yes);
    },
  };
  return bar;
}

// A table that sorts when you click a column header.
function dataTable(cols, { emptyText = 'Nothing to show.', auto = false } = {}) {
  const wrap = h('div', { class: 'table-wrap' + (auto ? ' auto' : '') });
  let rows = [], sortKey = null, dir = 1;
  function draw() {
    if (!rows.length) { wrap.replaceChildren(h('div', { class: 'empty', style: 'padding:16px' }, emptyText)); return; }
    let list = rows;
    if (sortKey) {
      const c = cols.find((x) => x.key === sortKey);
      const val = (r) => (c.sort ? c.sort(r) : r[c.key]);
      list = [...rows].sort((a, b) => {
        const x = val(a), y = val(b);
        const r = c.num ? (parseFloat(x) || 0) - (parseFloat(y) || 0) : String(x ?? '').localeCompare(String(y ?? ''));
        return r * dir;
      });
    }
    const head = h('tr', {}, cols.map((c) => h('th', {
      class: (c.num ? 'num ' : '') + 'sortable',
      onclick: () => { dir = sortKey === c.key ? -dir : 1; sortKey = c.key; draw(); },
    }, c.label, sortKey === c.key ? (dir > 0 ? ' ↑' : ' ↓') : '')));
    const body = list.map((r) => h('tr', {}, cols.map((c) => h('td', { class: (c.num ? 'num ' : '') + (c.cls || '') },
      c.render ? c.render(r) : (r[c.key] ?? '')))));
    wrap.replaceChildren(h('table', {}, h('thead', {}, head), h('tbody', {}, body)));
  }
  return { el: wrap, update(list) { rows = list; draw(); } };
}

function searchBox(placeholder, oninput) {
  return h('input', { type: 'search', class: 'grow', placeholder, oninput });
}
const matches = (q, r, keys) => !q || keys.some((k) => String(r[k] || '').toLowerCase().includes(q));

// ---------- router ----------
const VIEWS = [
  ['profile', 'Profile', viewProfile],
  ['rules', 'Ranking rules', viewRules],
  ['plan', 'Search plan', viewPlan],
  ['jobs', 'Jobs', viewJobs],
  ['applications', 'Applications', viewApplications],
  ['resumes', 'Resumes', viewResumes],
  ['searches', 'Searches', viewSearches],
];
let current = null;

async function route() {
  const id = location.hash.slice(1) || 'profile';
  const view = VIEWS.find((v) => v[0] === id) || VIEWS[0];
  if (current && view[0] !== current && dirty && !confirm('You have unsaved changes. Leave without saving?')) {
    history.replaceState(null, '', '#' + current);
    return;
  }
  dirty = false;
  current = view[0];
  document.title = view[1] + ' · Job search';
  for (const a of document.querySelectorAll('#nav a')) a.classList.toggle('active', a.dataset.id === current);
  const main = $('#main');
  main.replaceChildren(h('div', { class: 'empty' }, 'Loading…'));
  const box = h('div');
  try {
    await view[2](box);
    main.replaceChildren(box);
  } catch (e) {
    main.replaceChildren(pageHead(view[1]), h('div', { class: 'error-box' }, e.message));
  }
  window.scrollTo(0, 0);
}

$('#nav').append(...VIEWS.map(([id, label]) => h('a', { href: '#' + id, 'data-id': id }, label)));
window.addEventListener('hashchange', route);
route();

// ---------- Profile ----------
async function viewProfile(main) {
  let state = await api('/api/profile');
  main.append(pageHead('Profile', h('span', {}, 'Who you are and what you want, from ', code('profile/about_me.md'),
    '. Claude reads it in every search and tailoring session.')));
  if (!state.exists) {
    main.append(h('div', { class: 'empty' }, 'No profile yet. Run setup first: send @README.md to Claude.'));
    return;
  }
  let raw = false, edits = () => ({});
  const box = h('div', { class: 'narrow' });
  const toggle = h('button', { class: 'link', onclick: () => {
    if (dirty && !confirm('Switching discards your unsaved changes. Continue?')) return;
    raw = !raw; render();
  } });
  const bar = saveBar({ onSave: save, onRevert: render });
  main.append(h('div', { class: 'toolbar narrow' }, h('span', { class: 'spacer' }), toggle), box, bar.el);

  function render() {
    box.replaceChildren();
    toggle.textContent = raw ? 'Edit by section' : 'Edit whole file';
    if (raw) {
      const t = autogrow(h('textarea', { class: 'mono', value: state.raw, oninput: () => bar.setDirty(t.value !== state.raw) }));
      box.append(t);
      edits = () => ({ raw: t.value });
    } else {
      const areas = state.sections.map((s) => {
        const t = autogrow(h('textarea', { value: s.body, oninput: check }));
        box.append(h('section', { class: 'field' }, h('h2', {}, s.title), t));
        return t;
      });
      function check() { bar.setDirty(areas.some((t, i) => t.value !== state.sections[i].body)); }
      edits = () => ({ sections: state.sections.map((s, i) => ({ title: s.title, body: areas[i].value })) });
    }
    bar.setDirty(false);
  }
  async function save() {
    bar.busy(true);
    try {
      state = await api('/api/profile', 'PUT', { ...edits(), version: state.version });
      render();
      bar.show(state.message, 'ok');
    } catch (e) { bar.busy(false); bar.show(e.message, 'err'); }
  }
  render();
}

// ---------- Ranking rules ----------
const WA = [
  ['us_citizen', 'US citizen'],
  ['green_card', 'Green card holder'],
  ['f1_opt', 'F-1 student on OPT / STEM OPT'],
  ['needs_sponsorship', 'Needs visa sponsorship (H-1B)'],
];

async function viewRules(main) {
  let state = await api('/api/config');
  main.append(pageHead('Ranking rules', h('span', {}, 'How ', code('rank_jobs.py'), ' filters and scores jobs, from ',
    code('profile/rank_config.json'), '. Changes apply to the next search or re-rank.')));
  if (!state.exists) {
    main.append(h('div', { class: 'empty' }, 'No ranking rules yet. Run setup first: send @README.md to Claude.'));
    return;
  }
  let cfg, base, rawMode = false;  // base: cfg as first drawn (empty sections the form adds don't count as edits)
  const form = h('fieldset', { class: 'narrow' });
  const rawArea = autogrow(h('textarea', { class: 'mono', rows: 12, oninput: onRaw }));
  const advanced = h('details', { class: 'advanced narrow', ontoggle: () => { if (advanced.open && !rawMode) fillRaw(); } },
    h('summary', {}, 'Advanced: edit the raw JSON'),
    h('p', { class: 'muted small' }, 'Editing here turns the form off until you save or revert.'), rawArea);
  const bar = saveBar({ onSave: save, onRevert: () => load(state) });
  const errBox = h('div');
  main.append(errBox, form, advanced, bar.el);

  const formText = () => (same(cfg, base) ? state.raw : JSON.stringify(cfg, null, 1));
  function changed() { bar.setDirty(!same(cfg, base)); }
  function fillRaw() {
    rawArea.value = formText();
    rawArea.classList.remove('invalid');
    requestAnimationFrame(() => rawArea.dispatchEvent(new Event('input')));
  }
  function onRaw(e) {
    if (!advanced.open || !e.isTrusted) return;  // only real typing switches to raw mode
    rawMode = true;
    form.disabled = true;
    let problem = '';
    try { JSON.parse(rawArea.value); } catch (err) { problem = 'Raw JSON: ' + err.message; }
    rawArea.classList.toggle('invalid', !!problem);
    bar.block(problem);
    bar.setDirty(rawArea.value !== state.raw);
  }

  function load(s) {
    state = s;
    errBox.replaceChildren(s.error ? h('div', { class: 'error-box' }, s.error) : '');
    rawMode = false; form.disabled = false; bar.block('');
    if (!s.config) {  // the file isn't valid JSON: only the raw editor works
      form.replaceChildren(); advanced.open = true; rawArea.value = s.raw; rawMode = true; bar.setDirty(false);
      return;
    }
    cfg = clone(s.config);
    drawForm();
    base = clone(cfg);
    if (advanced.open) fillRaw();
    bar.setDirty(false);
  }

  async function save() {
    bar.busy(true);
    try {
      const body = rawMode ? { raw: rawArea.value } : { config: cfg };
      const r = await api('/api/config', 'PUT', { ...body, version: state.version });
      load(r);
      bar.show(r.message, 'ok');
    } catch (e) { bar.busy(false); bar.show(e.message, 'err'); }
  }

  // --- form pieces bound to cfg ---
  function num(label, path, { nullable = false, hint, step = 'any', scale = 1 } = {}) {
    const v = getPath(cfg, path);
    const inp = h('input', { type: 'number', step, value: v == null ? '' : +(v / scale).toFixed(2), placeholder: nullable ? 'off' : '',
      oninput: () => {
        const t = inp.value.trim();
        if (t === '' && !nullable) { inp.classList.add('invalid'); return; }
        inp.classList.remove('invalid');
        setPath(cfg, path, t === '' ? null : Math.round(Number(t) * scale * 100) / 100);
        changed();
      } });
    return field(label, inp, hint);
  }
  function alt(label, path, hint) {
    const v = getPath(cfg, path) || '';
    const warn = h('div', { class: 'warn-text' });
    const count = h('div', { class: 'hint' });
    const t = autogrow(h('textarea', { class: 'mono', rows: 2, value: splitAlt(v).join('\n'), oninput: () => {
      setPath(cfg, path, joinAlt(t.value)); changed(); check();
    } }));
    function check() {
      const p = reProblem(getPath(cfg, path));
      warn.textContent = p ? 'Check this pattern: ' + p : '';
      const n = splitAlt(getPath(cfg, path) || '').filter(Boolean).length;
      count.textContent = (hint ? hint + ' ' : '') + `${n} ${n === 1 ? 'entry' : 'entries'}, one per line.`;
    }
    check();
    return h('div', { class: 'field' }, h('label', {}, label), t, warn, count);
  }
  function checkbox(label, path, dflt) {
    const v = getPath(cfg, path);
    const inp = h('input', { type: 'checkbox', checked: v == null ? dflt : !!v, onchange: () => { setPath(cfg, path, inp.checked); changed(); } });
    return h('div', { class: 'field' }, h('label', { class: 'check' }, inp, label));
  }

  function drawForm() {
    form.replaceChildren(
      h('section', {}, h('h2', {}, 'Basics'), h('div', { class: 'row' },
        num('Minimum fit score', 'min_fit', { hint: 'The main quality bar. Raise it if lists get too long.' }),
        num('Minimum salary ($/year)', 'min_salary', { nullable: true, hint: 'Empty turns the salary filter off.' }),
        num('Max years of experience', 'seniority.max_years', { nullable: true, step: 1, hint: 'Empty means no limit.' }),
        num('Max jobs per site', 'top_n_per_site', { nullable: true, step: 1, hint: 'Empty means no cap.' }))),
      workAuth(),
      skillsEditor(),
      h('section', {}, h('h2', {}, 'Job titles'),
        alt('Titles must contain one of', 'titles.include'),
        alt('Drop titles containing', 'titles.exclude'),
        alt('Drop unless the title is a core role', 'titles.exclude_unless_core'),
        alt('Core roles', 'titles.core'),
        alt('Main role (bonus points)', 'titles.role_bonus')),
      seniorityEditor(),
      locationsEditor(),
      sitesEditor(),
      h('section', {}, h('h2', {}, 'Companies'),
        checkbox('Drop known staffing and OPT-placement firms (built-in list)', 'use_default_company_blocklist', true),
        alt('Also drop these companies', 'exclude_companies')),
      flagsEditor(),
    );
  }

  function workAuth() {
    const status = getPath(cfg, 'work_authorization.status') || 'us_citizen';
    const sel = h('select', { onchange: () => { setPath(cfg, 'work_authorization.status', sel.value); changed(); } },
      WA.map(([v, l]) => h('option', { value: v, selected: v === status }, l)));
    return h('section', {}, h('h2', {}, 'Work authorization'),
      field('Status', sel, 'Decides which citizenship, green card, OPT and sponsorship rules drop a job.'),
      checkbox('Drop jobs that need a security clearance', 'work_authorization.exclude_clearance_jobs', status !== 'us_citizen'));
  }

  function skillsEditor() {
    const box = h('div');
    const sum = h('div', { class: 'hint' });
    function entries() { return Object.entries(cfg.skills || {}); }
    function put(list) { cfg.skills = Object.fromEntries(list); changed(); total(); }
    function total() {
      const s = entries().reduce((a, [, v]) => a + (Number(v.weight) || 0), 0);
      sum.textContent = `Weights add up to ${s}. Aim for about 25, so the minimum fit score keeps its meaning.`;
    }
    function draw() {
      const rows = entries().map(([name, sk], i) => {
        const nameIn = h('input', { value: name, oninput: () => {
          const list = entries();
          const n = nameIn.value.trim();
          const clash = !n || list.some(([k], j) => j !== i && k === n);
          nameIn.classList.toggle('invalid', clash);
          if (clash) return;
          list[i] = [n, list[i][1]]; put(list);
        } });
        const patIn = h('input', { class: 'mono', value: sk.pattern || '', oninput: () => {
          sk.pattern = patIn.value; patIn.classList.toggle('invalid', !patIn.value || !!reProblem(patIn.value)); changed();
        } });
        const wIn = h('input', { type: 'number', step: 'any', value: sk.weight ?? 1, style: 'width:70px', oninput: () => {
          if (wIn.value.trim() === '') return; sk.weight = Number(wIn.value); changed(); total();
        } });
        const del = h('button', { class: 'icon', title: 'Remove', onclick: () => { put(entries().filter((_, j) => j !== i)); draw(); } }, '✕');
        return h('tr', {}, h('td', { style: 'width:22%' }, nameIn), h('td', {}, patIn), h('td', { style: 'width:90px' }, wIn), h('td', { style: 'width:36px' }, del));
      });
      box.replaceChildren(h('div', { class: 'table-wrap auto' }, h('table', { class: 'edit' },
        h('thead', {}, h('tr', {}, h('th', {}, 'Skill'), h('th', {}, 'Pattern (regex)'), h('th', {}, 'Weight'), h('th'))),
        h('tbody', {}, rows))));
      total();
    }
    const add = h('button', { class: 'btn small', onclick: () => {
      let n = 'New skill', i = 2;
      while ((cfg.skills || {})[n]) n = `New skill ${i++}`;
      put([...entries(), [n, { pattern: '', weight: 1 }]]); draw();
    } }, '+ Add skill');
    draw();
    return h('section', {}, h('h2', {}, 'Skills'), h('p', { class: 'muted small', style: 'margin-top:-6px' },
      'Fit points for each skill a job description mentions.'), box, sum, h('div', { style: 'margin-top:8px' }, add));
  }

  function seniorityEditor() {
    const yb = getPath(cfg, 'seniority.years_bonus') || {};
    const inputs = Object.keys(yb).map((k) => {
      const inp = h('input', { type: 'number', step: 'any', value: yb[k], oninput: () => {
        if (inp.value.trim() === '') return; cfg.seniority.years_bonus[k] = Number(inp.value); changed();
      } });
      return h('label', {}, `${k} yrs`, inp);
    });
    return h('section', {}, h('h2', {}, 'Seniority'),
      alt('Entry-level words in the title (+12)', 'seniority.title_bonus'),
      alt('Entry-level words in the description (+6)', 'seniority.desc_bonus'),
      alt('Title words one level up (−6)', 'seniority.title_penalty'),
      inputs.length ? h('div', { class: 'field' }, h('div', { class: 'label' }, 'Points by the minimum years a job asks for'),
        h('div', { class: 'inline-inputs' }, inputs)) : null);
  }

  function locationsEditor() {
    const box = h('div');
    const result = h('span', { class: 'result' });
    const test = h('input', { placeholder: 'e.g. Decatur, GA', oninput: () => runTest() });
    function runTest() {
      const loc = test.value.trim();
      result.textContent = loc ? tierOf(loc, cfg.locations || {}) : '';
    }
    function draw() {
      const L = cfg.locations || (cfg.locations = {});
      const tiers = L.tiers || (L.tiers = []);
      const cards = tiers.map((t, i) => {
        const tierIn = h('input', { type: 'number', step: 1, value: t.tier, style: 'width:70px', oninput: () => {
          if (tierIn.value.trim() === '') return; t.tier = Number(tierIn.value); changed(); runTest();
        } });
        const nameIn = h('input', { value: t.name || '', oninput: () => { t.name = nameIn.value; changed(); runTest(); } });
        const codes = h('input', { class: 'mono', value: (t.state_codes || []).join(', '), placeholder: 'e.g. GA, FL, NC', oninput: () => {
          const list = codes.value.split(/[,\s]+/).map((s) => s.trim().toUpperCase()).filter(Boolean);
          if (list.length) t.state_codes = list; else delete t.state_codes;
          changed(); runTest();
        } });
        const del = h('button', { class: 'icon', title: 'Remove tier', onclick: () => { tiers.splice(i, 1); changed(); draw(); } }, '✕');
        const matchField = alt('Places (city or region names, one per line)', `locations.tiers.${i}.match`);
        matchField.querySelector('textarea').addEventListener('input', runTest);
        return h('div', { class: 'tier-card' },
          h('div', { class: 'row' }, field('Tier', tierIn), h('div', { class: 'field', style: 'flex:1 1 200px' }, h('label', {}, 'Name'), nameIn),
            h('div', { class: 'field' }, del)),
          matchField,
          field('State codes', codes, 'Matches locations like "Raleigh, NC". Optional.'));
      });
      box.replaceChildren(...cards);
      runTest();
    }
    const add = h('button', { class: 'btn small', onclick: () => {
      const tiers = cfg.locations.tiers;
      tiers.push({ tier: tiers.length ? tiers[tiers.length - 1].tier : 1, name: 'New tier', match: '' });
      changed(); draw();
    } }, '+ Add tier');
    draw();
    return h('section', {}, h('h2', {}, 'Locations'),
      h('p', { class: 'muted small', style: 'margin-top:-6px' }, 'Checked in order; the first match wins. Tier 1 is where you most want to work.'),
      box, h('div', { style: 'margin:4px 0 18px' }, add),
      catchAll('remote', 'Keep remote jobs', 'Remote (US)', 2),
      catchAll('other', 'Keep jobs in all other places', 'Other', 3),
      h('div', { class: 'field' }, h('label', {}, 'Test a location'), h('div', { class: 'tester' }, test, result),
        h('div', { class: 'hint' }, 'Uses the rules above, including unsaved changes.')));
  }

  function catchAll(key, label, defName, defTier) {
    const L = cfg.locations || (cfg.locations = {});
    const v = L[key];
    const tierIn = h('input', { type: 'number', step: 1, value: v ? v.tier : defTier, style: 'width:70px', disabled: !v, oninput: () => {
      if (L[key] && tierIn.value.trim() !== '') { L[key].tier = Number(tierIn.value); changed(); }
    } });
    const nameIn = h('input', { value: v ? v.name : defName, disabled: !v, style: 'max-width:220px', oninput: () => {
      if (L[key]) { L[key].name = nameIn.value; changed(); }
    } });
    const box = h('input', { type: 'checkbox', checked: !!v, onchange: () => {
      L[key] = box.checked ? { tier: Number(tierIn.value) || defTier, name: nameIn.value || defName } : null;
      tierIn.disabled = nameIn.disabled = !box.checked; changed();
    } });
    return h('div', { class: 'field' }, h('div', { class: 'inline-inputs' }, h('label', { class: 'check', style: 'color:inherit' }, box, label),
      h('label', {}, 'tier', tierIn), h('label', {}, 'named', nameIn)));
  }

  function sitesEditor() {
    const box = h('div');
    function draw() {
      const order = cfg.site_order || (cfg.site_order = []);
      const ages = cfg.max_age_hours || (cfg.max_age_hours = {});
      const extra = Object.keys(ages).filter((s) => !order.includes(s));
      const ageIn = (site) => {
        const inp = h('input', { type: 'number', step: 'any', value: ages[site] == null ? '' : +(ages[site] / 24).toFixed(2), placeholder: 'no limit',
          style: 'width:90px', oninput: () => {
            const t = inp.value.trim();
            if (t === '') delete ages[site]; else ages[site] = Math.round(Number(t) * 24);
            changed();
          } });
        return inp;
      };
      const move = (i, d) => { const j = i + d; [order[i], order[j]] = [order[j], order[i]]; changed(); draw(); };
      const rows = order.map((s, i) => h('tr', {},
        h('td', { class: 'nowrap', style: 'width:70px' },
          h('button', { class: 'icon', title: 'Move up', disabled: i === 0, onclick: () => move(i, -1) }, '↑'),
          h('button', { class: 'icon', title: 'Move down', disabled: i === order.length - 1, onclick: () => move(i, 1) }, '↓')),
        h('td', {}, s), h('td', {}, ageIn(s))));
      const more = extra.map((s) => h('tr', {}, h('td'), h('td', { class: 'muted' }, s === 'default' ? 'All other sites' : s), h('td', {}, ageIn(s))));
      box.replaceChildren(h('div', { class: 'table-wrap auto' }, h('table', { class: 'edit' },
        h('thead', {}, h('tr', {}, h('th', {}, 'Order'), h('th', {}, 'Site'), h('th', {}, 'Max age (days)'))),
        h('tbody', {}, rows, more))));
    }
    draw();
    return h('section', {}, h('h2', {}, 'Sites'),
      h('p', { class: 'muted small', style: 'margin-top:-6px' },
        'The job list is grouped by site in this order. A job found on several sites is listed under the first one. Older posts are dropped.'), box);
  }

  function flagsEditor() {
    const box = h('div');
    function entries() { return Object.entries(cfg.flags || {}); }
    function put(list) { cfg.flags = Object.fromEntries(list); changed(); }
    function draw() {
      const rows = entries().map(([label, pat], i) => {
        const l = h('input', { value: label, oninput: () => {
          const list = entries(); const n = l.value.trim();
          const clash = !n || list.some(([k], j) => j !== i && k === n);
          l.classList.toggle('invalid', clash); if (clash) return;
          list[i] = [n, list[i][1]]; put(list);
        } });
        const p = h('input', { class: 'mono', value: pat, oninput: () => {
          const list = entries(); list[i] = [list[i][0], p.value]; put(list);
          p.classList.toggle('invalid', !!reProblem(p.value));
        } });
        const del = h('button', { class: 'icon', title: 'Remove', onclick: () => { put(entries().filter((_, j) => j !== i)); draw(); } }, '✕');
        return h('tr', {}, h('td', { style: 'width:30%' }, l), h('td', {}, p), h('td', { style: 'width:36px' }, del));
      });
      box.replaceChildren(rows.length ? h('div', { class: 'table-wrap auto' }, h('table', { class: 'edit' },
        h('thead', {}, h('tr', {}, h('th', {}, 'Note'), h('th', {}, 'Pattern (regex)'), h('th'))), h('tbody', {}, rows)))
        : h('p', { class: 'muted small' }, 'No flags.'));
    }
    const add = h('button', { class: 'btn small', onclick: () => {
      let n = 'New flag', i = 2;
      while ((cfg.flags || {})[n]) n = `New flag ${i++}`;
      put([...entries(), [n, '']]); draw();
    } }, '+ Add flag');
    draw();
    return h('section', {}, h('h2', {}, 'Flags'),
      h('p', { class: 'muted small', style: 'margin-top:-6px' }, 'Notes added to matching jobs in the list. Matching jobs are kept, not dropped.'),
      box, h('div', { style: 'margin-top:8px' }, add));
  }

  load(state);
}

// A JavaScript copy of tier() in rank_jobs.py, for the "Test a location" box.
function tierOf(loc, L) {
  const l = loc.toLowerCase();
  const re = (p) => { try { return new RegExp(p); } catch (e) { return null; } };
  for (const t of L.tiers || []) {
    if (t.match && re(t.match)?.test(l)) return `Tier ${t.tier}: ${t.name}`;
    if (t.state_codes?.length && re(',\\s*(' + t.state_codes.join('|') + ')\\b')?.test(loc)) return `Tier ${t.tier}: ${t.name}`;
  }
  if (L.remote && (l.includes('remote') || l.trim() === 'united states')) return `Tier ${L.remote.tier}: ${L.remote.name}`;
  if (L.other) return `Tier ${L.other.tier}: ${L.other.name}`;
  return 'Dropped: outside your locations';
}

// ---------- Search plan ----------
async function viewPlan(main) {
  let state = await api('/api/plan');
  main.append(pageHead('Search plan', h('span', {}, 'The Apify runs a normal search starts, from ', code('profile/search_plan.json'),
    ', and the budget from ', code('profile/search_notes.md'), '. A search never spends more than the budget.')));
  if (!state.exists) {
    main.append(h('div', { class: 'empty' }, 'No search plan yet. Your first @fresh_search.md (the test run) creates it.'));
    return;
  }
  let plan, base, budget, rawMode = false;
  const badInputs = new Set();
  const summary = h('div', { class: 'stats' });
  const budgetIn = h('input', { type: 'number', step: '0.25', min: '0', style: 'width:110px', oninput: () => {
    const v = parseFloat(budgetIn.value);
    budgetIn.classList.toggle('invalid', !(v > 0));
    if (v > 0) { budget = Math.round(v * 100) / 100; changed(); }
  } });
  const form = h('fieldset');
  const rawArea = autogrow(h('textarea', { class: 'mono', rows: 12, oninput: onRaw }));
  const advanced = h('details', { class: 'advanced', ontoggle: () => { if (advanced.open && !rawMode) fillRaw(); } },
    h('summary', {}, 'Advanced: edit the raw JSON'),
    h('p', { class: 'muted small' }, 'Editing here turns the run list off until you save or revert. The budget field still applies.'), rawArea);
  const bar = saveBar({ onSave: save, onRevert: () => load(state) });
  const errBox = h('div');
  main.append(errBox, h('div', { class: 'field' }, h('label', {}, 'Budget per search ($)'), budgetIn,
    h('div', { class: 'hint' }, 'apify.py stops starting runs, and stops running ones, once this much is spent.')),
  summary, form, advanced, bar.el);

  const runsOf = (p) => (Array.isArray(p) ? p : (p && p.runs) || []);
  const isOn = (r) => r.enabled !== false;
  const capsOn = (p) => runsOf(p).filter(isOn).reduce((a, r) => a + (Number(r.max_charge_usd) || 0), 0);
  const planText = () => (same(plan, base) ? state.raw : JSON.stringify(plan, null, 1));

  function changed() {
    drawSummary();
    bar.block(badInputs.size ? 'Fix the inputs marked in red before saving.' : '');
    bar.setDirty(rawMode ? rawArea.value !== state.raw || budget !== state.budget : !same(plan, base) || budget !== state.budget);
  }
  function drawSummary() {
    if (!plan) { summary.replaceChildren(); return; }
    const runs = runsOf(plan), on = runs.filter(isOn).length;
    summary.replaceChildren(
      h('div', { class: 'stat' }, h('div', { class: 'v' }, `${on} / ${runs.length}`), h('div', { class: 'k' }, 'runs on')),
      h('div', { class: 'stat' }, h('div', { class: 'v' }, money(capsOn(plan))), h('div', { class: 'k' }, 'caps of runs on')),
      h('div', { class: 'stat' }, h('div', { class: 'v' }, money(budget)), h('div', { class: 'k' }, 'budget')));
    if (capsOn(plan) > (budget || 0)) {
      summary.append(h('p', { class: 'muted small', style: 'flex-basis:100%;margin:0' },
        'Caps add up to more than the budget. That is normal: a cap is a limit, not a cost. apify.py starts a run only when its cap fits in what is left.'));
    }
  }
  function fillRaw() {
    rawArea.value = planText();
    rawArea.classList.remove('invalid');
    requestAnimationFrame(() => rawArea.dispatchEvent(new Event('input')));
  }
  function onRaw(e) {
    if (!advanced.open || !e.isTrusted) return;
    rawMode = true;
    form.disabled = true;
    let problem = '';
    try { JSON.parse(rawArea.value); } catch (err) { problem = 'Raw JSON: ' + err.message; }
    rawArea.classList.toggle('invalid', !!problem);
    bar.block(problem);
    bar.setDirty(rawArea.value !== state.raw || budget !== state.budget);
  }

  function load(s) {
    state = s;
    budget = s.budget;
    budgetIn.value = s.budget == null ? '' : Number(s.budget).toFixed(2);
    budgetIn.classList.remove('invalid');
    errBox.replaceChildren(s.error ? h('div', { class: 'error-box' }, s.error) : '',
      s.budget == null ? h('p', { class: 'muted small' }, 'No "Budget per search" line in search_notes.md yet. Setting a budget here adds one.') : '');
    rawMode = false; form.disabled = false; badInputs.clear(); bar.block('');
    if (!s.plan) {
      plan = null; form.replaceChildren(); advanced.open = true; rawArea.value = s.raw; rawMode = true;
      drawSummary(); bar.setDirty(false); return;
    }
    plan = clone(s.plan);
    base = clone(plan);
    drawRuns();
    drawSummary();
    if (advanced.open) fillRaw();
    bar.setDirty(false);
  }

  function drawRuns() {
    const runs = runsOf(plan);
    const groups = [];
    runs.forEach((r, i) => {
      let g = groups.find((x) => x.site === r.site);
      if (!g) groups.push(g = { site: r.site, items: [] });
      g.items.push([r, i]);
    });
    const body = [];
    for (const g of groups) {
      const sub = h('span', { class: 'count' });
      const updSub = () => {
        const on = g.items.filter(([r]) => isOn(r));
        sub.textContent = ` · ${on.length} of ${g.items.length} on · caps ${money(on.reduce((a, [r]) => a + (Number(r.max_charge_usd) || 0), 0))}`;
      };
      updSub();
      body.push(h('tr', { class: 'group' }, h('td', { colspan: 4 }, g.site, sub)));
      for (const [r, i] of g.items) {
        const tr = h('tr', { class: isOn(r) ? '' : 'off' });
        const toggle = h('input', { type: 'checkbox', checked: isOn(r), title: 'Run this search', onchange: () => {
          if (toggle.checked) { if ('enabled' in base_run(i)) r.enabled = true; else delete r.enabled; } else r.enabled = false;
          tr.className = toggle.checked ? '' : 'off'; updSub(); changed();
        } });
        const note = h('input', { value: r.note || '', placeholder: describe(r), oninput: () => {
          if (note.value) r.note = note.value; else delete r.note; changed();
        } });
        const cap = h('input', { type: 'number', step: '0.01', min: '0', value: r.max_charge_usd, style: 'width:90px', oninput: () => {
          const v = parseFloat(cap.value);
          cap.classList.toggle('invalid', !(v > 0));
          if (!(v > 0)) return;
          const prev = r.max_charge_usd;
          r.max_charge_usd = Math.round(v * 100) / 100;
          if (r.min_charge_usd === prev) r.min_charge_usd = r.max_charge_usd;  // keep "wait for room" runs in step
          updSub(); changed();
        } });
        const inputArea = autogrow(h('textarea', { class: 'mono', value: JSON.stringify(r.input, null, 1), oninput: () => {
          try {
            const v = JSON.parse(inputArea.value);
            if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error('must be a JSON object');
            r.input = v; badInputs.delete(i); inputArea.classList.remove('invalid');
          } catch (e) { badInputs.add(i); inputArea.classList.add('invalid'); }
          changed();
        } }));
        const detail = h('tr', { hidden: true }, h('td'), h('td', { colspan: 3 },
          h('div', { class: 'small muted', style: 'margin-bottom:6px' }, `Scraper: ${r.actor} · parser: ${r.parser}`
            + (r.min_charge_usd != null ? ` · waits until ${money(r.min_charge_usd)} of budget is free` : '')),
          inputArea));
        const more = h('button', { class: 'btn small', onclick: () => {
          detail.hidden = !detail.hidden; more.textContent = detail.hidden ? 'Inputs' : 'Hide';
          if (!detail.hidden) inputArea.dispatchEvent(new Event('input'));
        } }, 'Inputs');
        tr.append(h('td', { style: 'width:36px' }, toggle), h('td', {}, note), h('td', { style: 'width:110px' }, cap),
          h('td', { style: 'width:80px' }, more));
        body.push(tr, detail);
      }
    }
    form.replaceChildren(h('div', { class: 'table-wrap auto' }, h('table', { class: 'edit' },
      h('thead', {}, h('tr', {}, h('th', {}, 'On'), h('th', {}, 'Search'), h('th', {}, 'Cap ($)'), h('th'))),
      h('tbody', {}, body))));
  }
  const base_run = (i) => runsOf(base)[i] || {};
  function describe(r) {
    const x = r.input || {};
    const kw = x.title || x.keywords || x.keyword || (x.searchQueries || x.titleSearch || []).join(', ') || '';
    const loc = x.location || (x.locations || x.locationSearch || []).join(', ') || '';
    return [kw, loc].filter(Boolean).join(' / ') || r.actor;
  }

  function moneyChanges() {
    const parts = [];
    if (budget !== state.budget) parts.push(`budget ${money(state.budget)} → ${money(budget)}`);
    if (!rawMode && plan) {
      const c0 = capsOn(base), c1 = capsOn(plan);
      if (Math.abs(c0 - c1) > 1e-9) parts.push(`caps of runs on ${money(c0)} → ${money(c1)}`);
      const n0 = runsOf(base).filter(isOn).length, n1 = runsOf(plan).filter(isOn).length;
      if (n0 !== n1) parts.push(`runs on ${n0} → ${n1}`);
    }
    return parts;
  }
  function save() {
    const parts = moneyChanges();
    if (rawMode) parts.push('the plan is saved from the raw JSON');
    if (parts.length) bar.ask('Save these changes? ' + parts.join('; ') + '.', doSave);
    else doSave();
  }
  async function doSave() {
    bar.busy(true);
    try {
      const body = rawMode ? { raw: rawArea.value } : { plan };
      const r = await api('/api/plan', 'PUT', { ...body, budget, version: state.version, notes_version: state.notes_version });
      load(r);
      bar.show(r.message, 'ok');
    } catch (e) { bar.busy(false); bar.show(e.message, 'err'); }
  }
  load(state);
}

// ---------- Jobs ----------
async function viewJobs(main, file) {
  const d = await api('/api/jobs' + (file ? '?file=' + encodeURIComponent(file) : ''));
  main.append(pageHead('Jobs', h('span', {}, 'Ranked job lists in ', code('search_results/'),
    ', in the order to apply. Rows marked handled are already in applications.csv.')));
  if (!d.files.length) { main.append(h('div', { class: 'empty' }, 'No job lists yet. Send @fresh_search.md to Claude to run a search.')); return; }
  const pick = h('select', { onchange: () => { main.replaceChildren(); viewJobs(main, pick.value).catch((e) => main.append(h('div', { class: 'error-box' }, e.message))); } },
    d.files.map((f) => h('option', { value: f, selected: f === d.file }, f.replace(/^top_jobs_|\.csv$/g, ''))));
  const sites = [...new Set(d.rows.map((r) => r.platform))];
  const tiers = [...new Set(d.rows.map((r) => r.tier))].sort();
  const site = h('select', { onchange: draw }, h('option', { value: '' }, 'All sites'), sites.map((s) => h('option', { value: s }, s)));
  const tier = h('select', { onchange: draw }, h('option', { value: '' }, 'All tiers'), tiers.map((t) => h('option', { value: t }, 'Tier ' + t)));
  const hide = h('input', { type: 'checkbox', onchange: draw });
  const q = searchBox('Search title, company, location, notes', draw);
  const count = h('span', { class: 'count' });
  const table = dataTable([
    { key: 'apply_order', label: '#', num: true },
    { key: 'handled', label: 'Handled', render: (r) => pill(r.handled) },
    { key: 'platform', label: 'Site', cls: 'nowrap' },
    { key: 'tier', label: 'Tier', num: true },
    { key: 'fit_score', label: 'Fit', num: true },
    { key: 'title', label: 'Title', cls: 'wrap', render: (r) => extLink(r.url, r.title) },
    { key: 'company', label: 'Company' },
    { key: 'location', label: 'Location' },
    { key: 'posted', label: 'Posted', cls: 'nowrap' },
    { key: 'salary', label: 'Salary', cls: 'nowrap' },
    { key: 'notes', label: 'Notes', cls: 'notes' },
  ], { emptyText: 'No jobs match.' });
  main.append(h('div', { class: 'toolbar' }, pick, q, site, tier, h('label', { class: 'check' }, hide, 'Hide handled'), count), table.el);
  function draw() {
    const s = q.value.trim().toLowerCase();
    const rows = d.rows.filter((r) => (!site.value || r.platform === site.value) && (!tier.value || r.tier === tier.value)
      && (!hide.checked || !r.handled) && matches(s, r, ['title', 'company', 'location', 'notes', 'skills']));
    count.textContent = `${rows.length} of ${d.rows.length}`;
    table.update(rows);
  }
  draw();
}

// ---------- Applications ----------
async function viewApplications(main) {
  const d = await api('/api/applications');
  main.append(pageHead('Applications', h('span', {}, 'Every job handled so far, from ', code('applications.csv'), '. View only.')));
  if (!d.rows.length) { main.append(h('div', { class: 'empty' }, 'No applications logged yet. Send @tailor-resumes.md to Claude to start.')); return; }
  const by = (k) => d.rows.filter((r) => r.decision === k).length;
  main.append(h('div', { class: 'stats' },
    [['Total', d.rows.length], ['Apply', by('apply')], ['Skip', by('skip')], ['Blocked', by('blocked')]]
      .map(([k, v]) => h('div', { class: 'stat' }, h('div', { class: 'v' }, v), h('div', { class: 'k' }, k)))));
  const decisions = [...new Set(d.rows.map((r) => r.decision).filter(Boolean))];
  const dec = h('select', { onchange: draw }, h('option', { value: '' }, 'All decisions'), decisions.map((x) => h('option', { value: x }, x)));
  const q = searchBox('Search company, title, reason', draw);
  const count = h('span', { class: 'count' });
  const special = {
    title: { key: 'title', label: 'Title', cls: 'wrap', render: (r) => extLink(r.url, r.title) },
    decision: { key: 'decision', label: 'Decision', render: (r) => pill(r.decision) },
    resume_file: { key: 'resume_file', label: 'Resume', render: (r) => (r.resume_exists ? extLink('/files/' + r.resume_file, 'PDF') : '') },
    reason: { key: 'reason', label: 'Reason', cls: 'notes' },
    // the list a job came from is shown as a tooltip on its number, to keep the table narrow
    apply_order: { key: 'apply_order', label: '#', num: true, render: (r) => h('span', { title: r.csv_file || '' }, r.apply_order) },
    date: { key: 'date', label: 'Date', cls: 'nowrap' },
    status_date: { key: 'status_date', label: 'Status date', cls: 'nowrap' },
  };
  const label = (k) => k.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
  const hidden = new Set(['csv_file', ...(d.columns.includes('title') ? ['url'] : [])]);
  const cols = d.columns.filter((k) => !hidden.has(k)).map((k) => special[k] || { key: k, label: label(k) });
  const table = dataTable(cols, { emptyText: 'No rows match.' });
  main.append(h('div', { class: 'toolbar' }, q, dec, count), table.el);
  function draw() {
    const s = q.value.trim().toLowerCase();
    const rows = d.rows.filter((r) => (!dec.value || r.decision === dec.value) && matches(s, r, ['company', 'title', 'reason', 'status']))
      .slice().reverse();  // newest first
    count.textContent = `${rows.length} of ${d.rows.length}`;
    table.update(rows);
  }
  draw();
}

// ---------- Resumes ----------
async function viewResumes(main) {
  const d = await api('/api/resumes');
  main.append(pageHead('Resumes', h('span', {}, 'Your base resume (', code('resumes/base.html'), ') and the tailored ones in ',
    code('tailored/'), '. View only.')));
  const left = h('div');
  if (d.base) {
    const frame = h('iframe', { src: d.base_url, title: 'Base resume', tabindex: '-1' });
    const paper = h('div', { class: 'paper' }, frame);
    const fit = () => {
      const s = Math.min(1, paper.clientWidth / 816);
      frame.style.transform = `scale(${s})`;
      paper.style.height = 1056 * s + 'px';
    };
    new ResizeObserver(fit).observe(paper);
    left.append(h('h2', { style: 'margin-top:0' }, 'Base resume'), paper,
      h('div', { class: 'links' }, extLink(d.base_url, 'Open full size'), d.base_pdf ? extLink(d.base_pdf, 'PDF') : null));
  } else {
    left.append(h('h2', { style: 'margin-top:0' }, 'Base resume'), h('div', { class: 'empty' }, 'No resumes/base.html yet. Setup builds it.'));
  }
  const q = searchBox('Search company or role', draw);
  const count = h('span', { class: 'count' });
  const table = dataTable([
    { key: 'company', label: 'Company', render: (r) => r.company || r.slug },
    { key: 'title', label: 'Role', cls: 'wrap', render: (r) => (r.job_url ? extLink(r.job_url, r.title || 'posting') : r.title) },
    { key: 'modified', label: 'Made', cls: 'nowrap' },
    { key: 'file', label: '', render: (r) => extLink(r.url, 'PDF') },
  ], { emptyText: 'No tailored resumes yet.' });
  const right = h('div', {}, h('h2', { style: 'margin-top:0' }, `Tailored resumes (${d.tailored.length})`),
    h('div', { class: 'toolbar' }, q, count), table.el);
  main.append(h('div', { class: 'resumes' }, left, right));
  function draw() {
    const s = q.value.trim().toLowerCase();
    const rows = d.tailored.filter((r) => matches(s, r, ['company', 'slug', 'title']));
    count.textContent = `${rows.length} of ${d.tailored.length}`;
    table.update(rows);
  }
  draw();
}

// ---------- Searches ----------
async function viewSearches(main) {
  const d = await api('/api/searches');
  main.append(pageHead('Searches', 'Apify credit, and the job lists of past searches. View only.'));

  const credit = h('div', { class: 'card' }, h('span', { class: 'muted' }, 'Checking Apify credit…'));
  const refresh = h('button', { class: 'btn small', onclick: loadCredit }, 'Refresh');
  main.append(h('h2', {}, 'Apify credit this month'), credit);
  async function loadCredit() {
    credit.replaceChildren(h('span', { class: 'muted' }, 'Checking Apify credit…'));
    try {
      const c = await api('/api/credit');
      if (!c.ok) { credit.replaceChildren(h('span', { class: 'muted' }, c.message), ' ', refresh); return; }
      const pct = c.limit ? Math.min(100, (100 * c.used) / c.limit) : 0;
      credit.replaceChildren(
        h('div', { class: 'toolbar', style: 'margin:0' }, h('div', {},
          h('b', {}, money(c.used)), h('span', { class: 'muted' }, ` used of ${money(c.limit)}`),
          c.cycle_end ? h('span', { class: 'muted' }, ` · resets after ${c.cycle_end}`) : null), h('span', { class: 'spacer' }), refresh),
        h('div', { class: 'bar' }, h('span', { style: `width:${pct}%` })));
    } catch (e) { credit.replaceChildren(h('span', { class: 'muted' }, e.message), ' ', refresh); }
  }
  loadCredit();

  main.append(h('h2', {}, 'Past searches'));
  if (!d.searches.length) { main.append(h('div', { class: 'empty' }, 'No searches yet.')); return; }
  const preview = h('div');
  const table = dataTable([
    { key: 'label', label: 'Date', cls: 'nowrap' },
    { key: 'jobs', label: 'Jobs listed', num: true, render: (s) => (s.jobs == null ? '—' : s.jobs) },
    { key: 'per_site', label: 'By site', cls: 'notes', sort: (s) => s.jobs,
      render: (s) => Object.entries(s.per_site).map(([k, v]) => `${k} ${v}`).join(' · ') },
    { key: 'cost', label: 'Apify cost', num: true, sort: (s) => s.raw.reduce((a, r) => a + r.cost, 0),
      render: (s) => (s.raw.length ? money(s.raw.reduce((a, r) => a + r.cost, 0)) : '—') },
    { key: 'runs', label: 'Runs', sort: (s) => s.raw.reduce((a, r) => a + r.runs, 0),
      render: (s) => s.raw.map((r) => `${r.runs} runs` + (r.problems ? `, ${r.problems} not OK` : '')).join('; ') || '—' },
    { key: 'action', label: '', render: (s) => s.raw.map((r) => h('button', { class: 'btn small', onclick: () => runPreview(r.folder) },
      s.raw.length > 1 ? `Preview re-rank (${r.folder})` : 'Preview re-rank')) },
  ], { auto: true });
  table.update(d.searches);
  main.append(table.el, h('p', { class: 'muted small' },
    'Searches made before the dashboard existed have no downloaded data, so they show counts only and can\'t be re-ranked.'), preview);

  async function runPreview(folder) {
    preview.replaceChildren(h('h2', {}, 'Re-rank preview'), h('div', { class: 'muted' }, `Ranking ${folder} with your current rules…`));
    preview.scrollIntoView({ behavior: 'smooth', block: 'start' });
    try {
      const r = await api('/api/rerank-preview', 'POST', { folder });
      const sites = [...new Set([...Object.keys(r.current), ...Object.keys(r.preview)])];
      const cmp = dataTable([
        { key: 'site', label: 'Site' },
        { key: 'cur', label: r.current_file ? 'Current list' : 'Current list (none)', num: true },
        { key: 'new', label: 'Preview', num: true },
      ], { auto: true });
      cmp.update(sites.map((s) => ({ site: s, cur: r.current[s] || 0, new: r.preview[s] || 0 })));
      const drops = Object.entries(r.drops).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v}`).join(' · ');
      const jobs = dataTable([
        { key: 'apply_order', label: '#', num: true },
        { key: 'handled', label: 'Handled', render: (x) => pill(x.handled) },
        { key: 'platform', label: 'Site', cls: 'nowrap' },
        { key: 'tier', label: 'Tier', num: true },
        { key: 'fit_score', label: 'Fit', num: true },
        { key: 'title', label: 'Title', cls: 'wrap', render: (x) => extLink(x.url, x.title) },
        { key: 'company', label: 'Company' },
        { key: 'location', label: 'Location' },
        { key: 'salary', label: 'Salary', cls: 'nowrap' },
        { key: 'notes', label: 'Notes', cls: 'notes' },
      ]);
      jobs.update(r.rows);
      preview.replaceChildren(h('h2', {}, `Re-rank preview: ${r.folder}`),
        h('p', { class: 'muted small' }, `Ranked with your current rules, with job ages measured from ${r.now} UTC (when the search ran). `
          + 'Jobs already in applications.csv are kept and marked handled, so the counts compare with the list made then. Nothing was saved.'),
        h('div', { class: 'narrow' }, cmp.el), h('p', { class: 'muted small' }, 'Dropped: ' + (drops || 'none')),
        h('h2', {}, `Preview list (${r.rows.length} jobs)`), jobs.el);
    } catch (e) {
      preview.replaceChildren(h('h2', {}, 'Re-rank preview'), h('div', { class: 'error-box' }, e.message));
    }
  }
}
