// Writes the share of the page height used by #content onto <body data-fill>. render.sh reads it.
const p = document.getElementById('page'), c = document.getElementById('content');
const s = getComputedStyle(p), pad = parseFloat(s.paddingTop) + parseFloat(s.paddingBottom);
document.body.setAttribute('data-fill', (c.scrollHeight / (p.clientHeight - pad)).toFixed(3));
