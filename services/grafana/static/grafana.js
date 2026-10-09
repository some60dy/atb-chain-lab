/* ATB Grafana frontend bundle */
(function () {
'use strict';
var B = window.grafanaBootData || {user: {}}, P = window.__page || {};
var UTC = (B.user && B.user.timezone === 'utc');
function $(s, r) { return (r || document).querySelector(s); }
function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
  return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); }
function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
var SVGNS = 'http://www.w3.org/2000/svg';
function sv(tag, attrs) { var e = document.createElementNS(SVGNS, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); return e; }
function ic(path, size) { return '<svg class="ic" width="' + (size || 16) + '" height="' + (size || 16) + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + path + '</svg>'; }
var I = {
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z"/>',
  share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/>',
  cog: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  zoom: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4M8 11h6"/>',
  sync: '<path d="M20 11a8 8 0 0 0-14.6-4.5L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.6 4.5L20 16"/><path d="M20 20v-4h-4"/>',
  angle: '<path d="m6 9 6 6 6-6"/>', menu: '<circle cx="12" cy="5" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="12" cy="19" r="1.2"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>', apps: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  folder: '<path d="M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
  history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', play: '<path d="M7 4v16l13-8z"/>', trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14"/>',
  doc: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>', bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>'
};

/* ------------------------------------------------------------ common UI */
function toast(msg, kind) {
  var t = el('div', 'toast ' + (kind || ''), esc(msg)); document.body.appendChild(t);
  setTimeout(function () { t.remove(); }, 3500);
}
function modal(title, bodyHtml, wide) {
  var bg = el('div', 'modal-bg');
  bg.innerHTML = '<div class="modal"' + (wide ? ' style="width:min(1000px,96vw)"' : '') + '><div class="modal-h"><h3>' + esc(title) +
    '</h3><button class="btn-icon" data-close>' + ic(I.x) + '</button></div><div class="modal-b"></div></div>';
  $('.modal-b', bg).innerHTML = bodyHtml;
  bg.addEventListener('mousedown', function (e) { if (e.target === bg || e.target.closest('[data-close]')) bg.remove(); });
  document.body.appendChild(bg);
  return bg;
}
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') { $$('.modal-bg,.drawer').forEach(function (m) { m.remove(); }); closeDD(); }
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); openSearch(); }
});
function closeDD(except) { $$('.dd.open').forEach(function (d) { if (d !== except) d.classList.remove('open'); }); }
document.addEventListener('click', function (e) {
  var t = e.target.closest('[data-dd]');
  if (t) { var dd = t.closest('.dd'); closeDD(dd); dd.classList.toggle('open'); e.stopPropagation(); return; }
  if (!e.target.closest('.dd-menu')) closeDD();
  var sh = e.target.closest('[data-share]');
  if (sh) shareModal(location.origin + sh.getAttribute('data-share'));
});
var mb = $('#menuBtn');
try { if (localStorage.getItem('grafana.navbar.docked') === 'false') document.body.classList.add('menu-closed'); } catch (e) {}
if (mb) mb.addEventListener('click', function () {
  if (window.innerWidth < 900) { document.body.classList.toggle('menu-open'); return; }
  document.body.classList.toggle('menu-closed');
  try { localStorage.setItem('grafana.navbar.docked', !document.body.classList.contains('menu-closed')); } catch (e) {}
  window.dispatchEvent(new Event('resize'));
});
var kb = $('#kbdBtn');
if (kb) kb.addEventListener('click', function (e) {
  e.preventDefault(); closeDD();
  var rows = [['ctrl+k', 'Open search'], ['esc', 'Exit panel view / close modal'], ['d r', 'Refresh all panels'],
    ['t z', 'Zoom out time range'], ['t ←', 'Move time range back'], ['t →', 'Move time range forward'], ['v', 'Toggle panel fullscreen view'],
    ['i', 'Inspect panel'], ['x', 'Open panel in Explore'], ['shift+enter', 'Run query (Explore)']];
  modal('Shortcuts', '<table class="table">' + rows.map(function (r) { return '<tr><td><span class="badge">' + r[0] + '</span></td><td>' + r[1] + '</td></tr>'; }).join('') + '</table>');
});
function shareModal(url) {
  var m = modal('Share', '<div class="tabs"><a class="tab active">Link</a><a class="tab">Snapshot</a><a class="tab">Export</a></div>' +
    '<p class="muted">Create a direct link to this dashboard or panel, customized with the options below.</p>' +
    '<div class="field"><label>Link URL</label><div class="secret"><input id="shUrl" value="' + esc(url) + '" readonly><button class="btn btn-secondary btn-sm" id="shCopy">Copy</button></div></div>');
  $('#shCopy', m).onclick = function () { var i = $('#shUrl', m); i.select(); try { document.execCommand('copy'); toast('Content copied to clipboard', 'ok'); } catch (e) {} };
}

/* search */
var NAVPAGES = [['Explore', '/explore'], ['Alert rules', '/alerting/list'], ['Data sources', '/connections/datasources'], ['Users', '/admin/users'],
  ['Teams', '/org/teams'], ['Plugins', '/plugins'], ['Profile', '/profile'], ['Playlists', '/playlists'], ['Server settings', '/admin/settings']];
function openSearch() {
  if ($('.search-modal')) return;
  var m = modal('Search', '<input class="search-in" placeholder="Search or jump to..." autofocus><div class="search-res"></div>');
  m.classList.add('search-modal');
  var inp = $('.search-in', m), res = $('.search-res', m), sel = 0, items = [];
  function render() {
    res.innerHTML = items.map(function (it, i) {
      return '<a href="' + it.url + '" class="' + (i === sel ? 'sel' : '') + '">' + ic(it.type === 'dash-folder' ? I.folder : it.type === 'page' ? I.compass : I.apps) +
        esc(it.title) + '<span class="loc">' + esc(it.loc || '') + '</span></a>';
    }).join('') || '<div class="muted" style="padding:10px">No results found</div>';
  }
  function load() {
    var q = inp.value;
    fetch('/api/search?query=' + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (d) {
      items = d.map(function (x) { return {title: x.title, url: x.url, type: x.type, loc: x.type === 'dash-folder' ? 'Folder' : (x.folderTitle || 'Dashboards')}; });
      NAVPAGES.forEach(function (p) { if (p[0].toLowerCase().indexOf(q.toLowerCase()) >= 0) items.push({title: p[0], url: p[1], type: 'page', loc: 'Page'}); });
      sel = 0; render();
    });
  }
  inp.addEventListener('input', load);
  inp.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown') { sel = Math.min(items.length - 1, sel + 1); render(); e.preventDefault(); }
    if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); render(); e.preventDefault(); }
    if (e.key === 'Enter' && items[sel]) location.href = items[sel].url;
  });
  load(); setTimeout(function () { inp.focus(); }, 10);
}
var sb = $('#searchBtn'); if (sb) sb.addEventListener('click', openSearch);

function api(method, url, body) {
  return fetch(url, {method: method, headers: {'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined})
    .then(function (r) { return r.json().then(function (j) { return {status: r.status, body: j}; }); });
}
document.addEventListener('click', function (e) {
  var s = e.target.closest('.star-btn'); if (!s) return;
  var on = s.classList.toggle('starred');
  api(on ? 'POST' : 'DELETE', '/api/user/stars/dashboard/uid/' + s.getAttribute('data-uid'));
});

/* ---------------------------------------------------------- time utils */
var UNIT = {s: 1, m: 60, h: 3600, d: 86400, w: 604800, M: 2592000, y: 31536000};
function parseT(s, end) {
  if (s == null) return Date.now();
  s = String(s);
  if (/^\d+$/.test(s)) { var n = +s; return n < 1e11 ? n * 1000 : n; }
  var m = s.match(/^now(?:([+-])(\d+)([smhdwMy]))?(?:\/([smhdwMy]))?$/);
  if (!m) { var d = Date.parse(s.replace(' ', 'T')); return isNaN(d) ? Date.now() : d; }
  var t = Date.now();
  if (m[1]) { var dd = +m[2] * UNIT[m[3]] * 1000; t = m[1] === '-' ? t - dd : t + dd; }
  if (m[4]) {
    var x = new Date(t), u = m[4];
    if (u === 's') x.setMilliseconds(0);
    if (u === 'm') x.setSeconds(0, 0);
    if (u === 'h') x.setMinutes(0, 0, 0);
    if ('dwMy'.indexOf(u) >= 0) x.setHours(0, 0, 0, 0);
    if (u === 'w') x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
    if (u === 'M') x.setDate(1);
    if (u === 'y') { x.setMonth(0, 1); }
    t = x.getTime();
    if (end) {
      var y = new Date(t);
      if (u === 's') y.setSeconds(y.getSeconds() + 1); else if (u === 'm') y.setMinutes(y.getMinutes() + 1);
      else if (u === 'h') y.setHours(y.getHours() + 1); else if (u === 'd') y.setDate(y.getDate() + 1);
      else if (u === 'w') y.setDate(y.getDate() + 7); else if (u === 'M') y.setMonth(y.getMonth() + 1); else y.setFullYear(y.getFullYear() + 1);
      t = y.getTime() - 1;
    }
  }
  return t;
}
function pad(n) { return n < 10 ? '0' + n : '' + n; }
function dparts(ms) {
  var d = new Date(ms);
  return UTC ? [d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate(), d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds()]
    : [d.getFullYear(), d.getMonth() + 1, d.getDate(), d.getHours(), d.getMinutes(), d.getSeconds()];
}
function fmtDate(ms, withSec) {
  var p = dparts(ms);
  return p[0] + '-' + pad(p[1]) + '-' + pad(p[2]) + ' ' + pad(p[3]) + ':' + pad(p[4]) + (withSec === false ? '' : ':' + pad(p[5]));
}
function fmtAxis(ms, span) {
  var p = dparts(ms);
  if (span <= 86400e3 * 1.01) return pad(p[3]) + ':' + pad(p[4]);
  if (span <= 86400e3 * 7.1) return pad(p[1]) + '/' + pad(p[2]) + ' ' + pad(p[3]) + ':' + pad(p[4]);
  return pad(p[1]) + '/' + pad(p[2]);
}
var QUICK = [['now-5m', 'now', 'Last 5 minutes'], ['now-15m', 'now', 'Last 15 minutes'], ['now-30m', 'now', 'Last 30 minutes'],
  ['now-1h', 'now', 'Last 1 hour'], ['now-3h', 'now', 'Last 3 hours'], ['now-6h', 'now', 'Last 6 hours'], ['now-12h', 'now', 'Last 12 hours'],
  ['now-24h', 'now', 'Last 24 hours'], ['now-2d', 'now', 'Last 2 days'], ['now-7d', 'now', 'Last 7 days'],
  ['now/d', 'now/d', 'Today'], ['now-1d/d', 'now-1d/d', 'Yesterday'], ['now/w', 'now/w', 'This week'], ['now/d', 'now', 'Today so far']];
function rangeLabel(r) {
  for (var i = 0; i < QUICK.length; i++) if (QUICK[i][0] === r.from && QUICK[i][1] === r.to) return QUICK[i][2];
  var f = /^\d+$/.test(r.from) ? fmtDate(parseT(r.from)) : r.from, t = /^\d+$/.test(r.to) ? fmtDate(parseT(r.to)) : r.to;
  return f + ' to ' + t;
}

/* time picker component */
function TimePicker(host, state, onChange, withRefresh) {
  var refreshes = ['', '5s', '10s', '30s', '1m', '5m', '15m', '30m', '1h'];
  host.innerHTML = '<div class="btn-group"><div class="dd"><button class="tp-btn" data-dd>' + ic(I.clock) + '<span class="tp-l"></span>' + ic(I.angle, 12) + '</button>' +
    '<div class="dd-menu right tp-menu"><div class="tp-abs"><b>Absolute time range</b><label>From</label><input class="tp-f"><label>To</label><input class="tp-t">' +
    '<button class="btn btn-primary btn-sm tp-apply" style="margin-top:12px">Apply time range</button>' +
    '<p class="muted small" style="margin-top:14px">Time zone: ' + (UTC ? 'Coordinated Universal Time (UTC)' : 'Browser Time') + '</p></div>' +
    '<div class="tp-quick">' + QUICK.map(function (q, i) { return '<a href="#" data-i="' + i + '">' + q[2] + '</a>'; }).join('') + '</div></div></div>' +
    '<button class="tp-btn tp-zoom" title="Zoom out time range">' + ic(I.zoom) + '</button></div> ' +
    (withRefresh ? '<div class="btn-group"><button class="tp-btn tp-ref" title="Refresh dashboard">' + ic(I.sync) + '</button>' +
      '<div class="dd"><button class="tp-btn" data-dd><span class="tp-rl"></span>' + ic(I.angle, 12) + '</button><div class="dd-menu right" style="min-width:90px">' +
      refreshes.map(function (r) { return '<a href="#" data-r="' + r + '">' + (r || 'Off') + '</a>'; }).join('') + '</div></div></div>' : '');
  host.style.display = 'inline-flex'; host.style.gap = '6px';
  function sync() {
    $('.tp-l', host).textContent = rangeLabel(state.range);
    $('.tp-f', host).value = /^\d+$/.test(state.range.from) ? fmtDate(parseT(state.range.from)) : state.range.from;
    $('.tp-t', host).value = /^\d+$/.test(state.range.to) ? fmtDate(parseT(state.range.to)) : state.range.to;
    $$('.tp-quick a', host).forEach(function (a) { var q = QUICK[+a.dataset.i]; a.classList.toggle('on', q[0] === state.range.from && q[1] === state.range.to); });
    if (withRefresh) $('.tp-rl', host).textContent = state.refresh || '';
  }
  function norm(v) { v = v.trim(); if (/^now/.test(v)) return v; var t = Date.parse(v.replace(' ', 'T')); return isNaN(t) ? null : String(t); }
  host.addEventListener('click', function (e) {
    var a = e.target.closest('.tp-quick a');
    if (a) { e.preventDefault(); var q = QUICK[+a.dataset.i]; state.range = {from: q[0], to: q[1]}; closeDD(); sync(); onChange('range'); }
    var r = e.target.closest('[data-r]');
    if (r) { e.preventDefault(); state.refresh = r.dataset.r; closeDD(); sync(); onChange('refresh'); }
    if (e.target.closest('.tp-apply')) {
      var f = norm($('.tp-f', host).value), t = norm($('.tp-t', host).value);
      if (!f || !t) { toast('Please enter a past date or "now"', 'err'); return; }
      state.range = {from: f, to: t}; closeDD(); sync(); onChange('range');
    }
    if (e.target.closest('.tp-zoom')) {
      var ff = parseT(state.range.from), tt = parseT(state.range.to, true), span = tt - ff, c = ff + span / 2;
      var nt = Math.min(Date.now(), c + span); state.range = {from: String(Math.round(nt - span * 2)), to: String(Math.round(nt))};
      if (nt === Date.now()) state.range.to = 'now';
      sync(); onChange('range');
    }
    if (e.target.closest('.tp-ref')) onChange('refreshNow');
  });
  sync();
  return {sync: sync};
}

/* ---------------------------------------------------------- formatting */
var PALETTE = ['#73BF69', '#F2CC0C', '#8AB8FF', '#FF780A', '#F2495C', '#5794F2', '#B877D9', '#705DA0', '#37872D', '#FADE2A', '#447EBC', '#C15C17', '#890F02', '#0A437C', '#6D1F62', '#584477'];
var NAMED = {green: '#73BF69', red: '#F2495C', yellow: '#FADE2A', orange: '#FF9830', blue: '#5794F2', purple: '#B877D9',
  'dark-red': '#C4162A', 'dark-green': '#37872D', 'semi-dark-green': '#56A64B', text: '#ccccdc', transparent: 'transparent'};
function color(c) { return NAMED[c] || c; }
function thrColor(v, thr) {
  var steps = (thr && thr.steps) || [{color: 'green', value: null}], c = steps[0].color;
  for (var i = 1; i < steps.length; i++) if (v != null && v >= steps[i].value) c = steps[i].color;
  return color(c);
}
function autoDec(v) { var a = Math.abs(v); return a === 0 ? 0 : a >= 100 ? 0 : a >= 10 ? 1 : a >= 1 ? 2 : a >= .01 ? 3 : 4; }
function fx(v, d) { var s = (+v).toFixed(d == null ? autoDec(v) : d); if (d == null && s.indexOf('.') >= 0) s = s.replace(/\.?0+$/, ''); return s; }
function scaled(v, base, units, d) {
  var i = 0, a = Math.abs(v); while (a >= base && i < units.length - 1) { a /= base; v /= base; i++; }
  return [fx(v, d), units[i]];
}
function fmtParts(v, unit, d) {
  if (v == null || isNaN(v)) return ['No data', ''];
  switch (unit) {
    case 'percent': return [fx(v, d), '%'];
    case 'percentunit': return [fx(v * 100, d), '%'];
    case 'bytes': return scaled(v, 1024, [' B', ' KiB', ' MiB', ' GiB', ' TiB'], d);
    case 'Bps': return scaled(v, 1000, [' B/s', ' kB/s', ' MB/s', ' GB/s'], d);
    case 'bps': return scaled(v, 1000, [' b/s', ' kb/s', ' Mb/s', ' Gb/s'], d);
    case 'reqps': return [fx(v, d), ' req/s'];
    case 'ms': return v >= 1000 ? [fx(v / 1000, d), ' s'] : [fx(v, d), ' ms'];
    case 's':
      if (Math.abs(v) < 1) return [fx(v * 1000, d), ' ms'];
      if (v < 60) return [fx(v, d), ' s'];
      if (v < 3600) return [fx(v / 60, d), ' min'];
      if (v < 86400) return [fx(v / 3600, d), ' hour'];
      if (v < 86400 * 365) return [fx(v / 86400, d), ' day'];
      return [fx(v / 86400 / 365, d), ' year'];
    case 'short': return scaled(v, 1000, ['', ' K', ' Mil', ' Bil', ' Tri'], d);
    default: return [fx(v, d), ''];
  }
}
function fmtVal(v, unit, d) { var p = fmtParts(v, unit, d); return p[0] + p[1]; }

/* ---------------------------------------------------------- data shaping */
function fieldsOf(fr) { return (fr.schema && fr.schema.fields) || []; }
function valsOf(fr) { return (fr.data && fr.data.values) || []; }
function toSeries(frames) {
  var out = [];
  (frames || []).forEach(function (fr) {
    var F = fieldsOf(fr), V = valsOf(fr);
    var ti = -1; F.forEach(function (f, i) { if (f.type === 'time' && ti < 0) ti = i; });
    var si = [], ni = [];
    F.forEach(function (f, i) { if (i === ti) return; if (f.type === 'number') ni.push(i); else if (f.type === 'string') si.push(i); });
    var n = V.length ? (V[0] || []).length : 0;
    if (ti < 0) {
      if (si.length && ni.length) {
        for (var r = 0; r < n; r++) out.push({name: String(V[si[0]][r]), pts: [[null, V[ni[0]][r]]]});
      } else ni.forEach(function (j) { out.push({name: F[j].name, pts: V[j].map(function (v) { return [null, v]; })}); });
      return;
    }
    if (si.length) {
      var groups = {}, order = [];
      for (var k = 0; k < n; k++) {
        var key = si.map(function (j) { return V[j][k]; }).join(' ');
        ni.forEach(function (j) {
          var nm = ni.length > 1 ? key + ' ' + F[j].name : key;
          if (!groups[nm]) { groups[nm] = []; order.push(nm); }
          groups[nm].push([V[ti][k], V[j][k]]);
        });
      }
      order.forEach(function (nm) { out.push({name: nm, pts: groups[nm]}); });
    } else {
      ni.forEach(function (j) {
        var nm = (F[j].config && F[j].config.displayNameFromDS) || fr.schema.name || F[j].name;
        if (ni.length > 1 && !(F[j].config && F[j].config.displayNameFromDS)) nm = F[j].name;
        var pts = []; for (var k2 = 0; k2 < n; k2++) pts.push([V[ti][k2], V[j][k2]]);
        out.push({name: nm, pts: pts});
      });
    }
  });
  return out;
}
function reduce(pts, calc) {
  var vs = pts.map(function (p) { return p[1]; }).filter(function (v) { return v != null && !isNaN(v); });
  if (!vs.length) return null;
  switch (calc) {
    case 'mean': return vs.reduce(function (a, b) { return a + b; }, 0) / vs.length;
    case 'max': return Math.max.apply(null, vs);
    case 'min': return Math.min.apply(null, vs);
    case 'sum': return vs.reduce(function (a, b) { return a + b; }, 0);
    case 'first': case 'firstNotNull': return vs[0];
    default: return vs[vs.length - 1];
  }
}
var CALCNAME = {mean: 'Mean', max: 'Max', min: 'Min', sum: 'Total', lastNotNull: 'Last *', last: 'Last', first: 'First'};
function override(panel, name, prop) {
  var ov = (panel.fieldConfig && panel.fieldConfig.overrides) || [], res;
  ov.forEach(function (o) {
    var m = o.matcher || {}, hit = (m.id === 'byName' && m.options === name) || (m.id === 'byRegexp' && new RegExp('^' + m.options + '$').test(name));
    if (hit) (o.properties || []).forEach(function (p) { if (p.id === prop) res = p.value; });
  });
  return res;
}
function seriesColor(panel, s, i) {
  var c = override(panel, s.name, 'color');
  if (c && c.fixedColor) return color(c.fixedColor);
  return PALETTE[i % PALETTE.length];
}

/* ------------------------------------------------------------ timeseries */
var CROSS = [];
function niceTicks(lo, hi, count) {
  if (lo === hi) { lo -= 1; hi += 1; }
  var span = hi - lo, step = Math.pow(10, Math.floor(Math.log10(span / count))), err = count / span * step;
  if (err <= .15) step *= 10; else if (err <= .35) step *= 5; else if (err <= .75) step *= 2;
  var a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step, t = [];
  for (var v = a; v <= b + step / 2; v += step) t.push(+v.toFixed(10));
  return t;
}
var TSTEPS = [60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800].map(function (x) { return x * 1000; });
function drawTimeseries(box, series, panel, range, onZoom) {
  box.innerHTML = '';
  var dfl = (panel.fieldConfig && panel.fieldConfig.defaults) || {}, cus = dfl.custom || {}, opts = panel.options || {};
  var leg = opts.legend || {displayMode: 'list', placement: 'bottom', calcs: []};
  var unit = dfl.unit, dec = dfl.decimals;
  panel._hidden = panel._hidden || {};
  if (!series.length || !series.some(function (s) { return s.pts.length; })) { box.innerHTML = '<div class="nodata">No data</div>'; return; }
  series.forEach(function (s, i) { s.color = seriesColor(panel, s, i); });
  var wrap = el('div', 'ts-wrap' + (leg.placement === 'right' ? ' right' : '')), chart = el('div', 'ts'), lb = el('div', 'legend-box');
  wrap.appendChild(chart); if (leg.showLegend !== false && leg.displayMode !== 'hidden') wrap.appendChild(lb); box.appendChild(wrap);
  // legend
  var calcs = leg.calcs || [];
  function legend() {
    if (leg.displayMode === 'table' || leg.placement === 'right') {
      var h = '<table class="legend-table"><tr><th>Name</th>' + calcs.map(function (c) { return '<th>' + (CALCNAME[c] || c) + '</th>'; }).join('') + '</tr>';
      series.forEach(function (s, i) {
        h += '<tr class="li' + (panel._hidden[s.name] ? ' off' : '') + '" data-i="' + i + '"><td><span class="li"><span class="sw" style="background:' + s.color + '"></span>' + esc(s.name) + '</span></td>' +
          calcs.map(function (c) { return '<td>' + fmtVal(reduce(s.pts, c), unit, dec) + '</td>'; }).join('') + '</tr>';
      });
      lb.innerHTML = h + '</table>';
    } else {
      lb.innerHTML = '<div class="legend">' + series.map(function (s, i) {
        return '<span class="li' + (panel._hidden[s.name] ? ' off' : '') + '" data-i="' + i + '"><span class="sw" style="background:' + s.color + '"></span>' + esc(s.name) +
          calcs.map(function (c) { return ' <span class="muted">' + (CALCNAME[c] || c) + ': ' + fmtVal(reduce(s.pts, c), unit, dec) + '</span>'; }).join('') + '</span>';
      }).join('') + '</div>';
    }
  }
  legend();
  lb.addEventListener('click', function (e) {
    var li = e.target.closest('[data-i]'); if (!li) return;
    var s = series[+li.dataset.i], vis = series.filter(function (x) { return !panel._hidden[x.name]; });
    if (vis.length === 1 && vis[0] === s) panel._hidden = {};
    else { panel._hidden = {}; series.forEach(function (x) { if (x !== s) panel._hidden[x.name] = true; }); }
    drawTimeseries(box, series, panel, range, onZoom);
  });
  var W = chart.clientWidth || 400, H = chart.clientHeight || 200;
  var vis = series.filter(function (s) { return !panel._hidden[s.name]; });
  var stacked = cus.stacking && cus.stacking.mode === 'normal', bars = cus.drawStyle === 'bars';
  var draw = vis.map(function (s) { return {s: s, pts: s.pts.filter(function (p) { return p[0] != null; })}; });
  if (stacked) {
    var acc = {};
    draw.forEach(function (d) { d.base = d.pts.map(function (p) { return acc[p[0]] || 0; });
      d.pts = d.pts.map(function (p) { var b = acc[p[0]] || 0, v = b + (p[1] || 0); acc[p[0]] = v; return [p[0], v]; }); });
  }
  var lo = Infinity, hi = -Infinity;
  draw.forEach(function (d) { d.pts.forEach(function (p) { if (p[1] != null) { lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]); } }); });
  if (lo === Infinity) { lo = 0; hi = 1; }
  if (stacked || bars) lo = Math.min(0, lo);
  if (dfl.min != null) lo = dfl.min; if (dfl.max != null) hi = dfl.max;
  if (hi - lo < 1e-9) { hi = lo + (Math.abs(lo) || 1); }
  var yt = niceTicks(lo, hi, Math.max(2, Math.floor(H / 45)));
  if (dfl.min == null) lo = yt[0]; else yt = yt.filter(function (v) { return v >= lo; });
  if (dfl.max == null) hi = yt[yt.length - 1]; else yt = yt.filter(function (v) { return v <= hi; });
  var labels = yt.map(function (v) { return fmtVal(v, unit, null); });
  var ml = Math.max.apply(null, labels.map(function (l) { return l.length; }));
  var L = Math.min(90, 8 + ml * 6.6), R = 10, T = 6, Bm = 20, pw = Math.max(10, W - L - R), ph = Math.max(10, H - T - Bm);
  var f = range.f, t = range.t;
  function X(ms) { return L + (ms - f) / (t - f) * pw; }
  function Y(v) { return T + ph - (v - lo) / (hi - lo) * ph; }
  var svg = sv('svg', {width: W, height: H});
  var defs = sv('defs', {}); svg.appendChild(defs);
  var ax = sv('g', {'class': 'axis'}); svg.appendChild(ax);
  yt.forEach(function (v, i) {
    var y = Y(v); ax.appendChild(sv('line', {x1: L, x2: L + pw, y1: y, y2: y, 'class': 'grid-l'}));
    var tx = sv('text', {x: L - 6, y: y + 4, 'text-anchor': 'end'}); tx.textContent = labels[i]; ax.appendChild(tx);
  });
  var span = t - f, want = Math.max(2, Math.floor(pw / 90)), step = TSTEPS[TSTEPS.length - 1];
  for (var k = 0; k < TSTEPS.length; k++) if (span / TSTEPS[k] <= want) { step = TSTEPS[k]; break; }
  var tz = UTC ? 0 : new Date().getTimezoneOffset() * 60000;
  for (var x0 = Math.ceil((f - tz) / step) * step + tz; x0 <= t; x0 += step) {
    var xx = X(x0); ax.appendChild(sv('line', {x1: xx, x2: xx, y1: T, y2: T + ph, 'class': 'grid-l'}));
    var tl = sv('text', {x: xx, y: H - 5, 'text-anchor': 'middle'}); tl.textContent = fmtAxis(x0, span); ax.appendChild(tl);
  }
  var clip = 'c' + Math.random().toString(36).slice(2);
  var cp = sv('clipPath', {id: clip}); cp.appendChild(sv('rect', {x: L, y: T, width: pw, height: ph})); defs.appendChild(cp);
  var g = sv('g', {'clip-path': 'url(#' + clip + ')'}); svg.appendChild(g);
  var fo = (cus.fillOpacity != null ? cus.fillOpacity : 10) / 100, lw = cus.lineWidth || 1;
  draw.slice().reverse().forEach(function (d, ri) {
    var c = d.s.color, pts = d.pts;
    if (!pts.length) return;
    if (bars) {
      var bw = Math.max(1, pw / Math.max(pts.length, 1) * .7);
      pts.forEach(function (p, i) { var y0 = d.base ? Y(d.base[i]) : Y(Math.max(lo, 0)), y1 = Y(p[1]);
        g.appendChild(sv('rect', {x: X(p[0]) - bw / 2, y: Math.min(y0, y1), width: bw, height: Math.abs(y0 - y1), fill: c, 'fill-opacity': Math.max(fo, .5)})); });
      return;
    }
    var line = '', i;
    for (i = 0; i < pts.length; i++) line += (i ? 'L' : 'M') + X(pts[i][0]).toFixed(1) + ',' + Y(pts[i][1]).toFixed(1);
    if (fo > 0) {
      var gid = clip + 'g' + ri, lg = sv('linearGradient', {id: gid, x1: 0, y1: 0, x2: 0, y2: 1});
      lg.appendChild(sv('stop', {offset: 0, 'stop-color': c, 'stop-opacity': cus.gradientMode === 'opacity' ? Math.min(1, fo * 2) : fo}));
      lg.appendChild(sv('stop', {offset: 1, 'stop-color': c, 'stop-opacity': cus.gradientMode === 'opacity' ? fo / 4 : fo}));
      defs.appendChild(lg);
      var area = line;
      if (d.base) { for (i = pts.length - 1; i >= 0; i--) area += 'L' + X(pts[i][0]).toFixed(1) + ',' + Y(d.base[i]).toFixed(1); }
      else area += 'L' + X(pts[pts.length - 1][0]).toFixed(1) + ',' + Y(Math.max(lo, Math.min(0, hi))).toFixed(1) + 'L' + X(pts[0][0]).toFixed(1) + ',' + Y(Math.max(lo, Math.min(0, hi))).toFixed(1);
      g.appendChild(sv('path', {d: area + 'Z', fill: 'url(#' + gid + ')', stroke: 'none'}));
    }
    g.appendChild(sv('path', {d: line, fill: 'none', stroke: c, 'stroke-width': lw, 'stroke-linejoin': 'round'}));
  });
  var cross = sv('line', {y1: T, y2: T + ph, stroke: '#ff5286', 'stroke-width': 1, 'stroke-dasharray': '3,3', visibility: 'hidden'}); svg.appendChild(cross);
  var dots = sv('g', {}); svg.appendChild(dots);
  var selr = sv('rect', {y: T, height: ph, fill: 'rgba(120,120,130,.25)', visibility: 'hidden'}); svg.appendChild(selr);
  var ov = sv('rect', {x: L, y: T, width: pw, height: ph, fill: 'transparent', style: 'cursor:crosshair'}); svg.appendChild(ov);
  chart.appendChild(svg);
  var tip = $('#tooltip'), dragX = null;
  function nearest(pts, ms) { var a = 0, b = pts.length - 1; if (b < 0) return null;
    while (b - a > 1) { var m = (a + b) >> 1; if (pts[m][0] < ms) a = m; else b = m; }
    return Math.abs(pts[a][0] - ms) <= Math.abs(pts[b][0] - ms) ? a : b; }
  function showAt(ms, ev) {
    var xx = X(ms); cross.setAttribute('x1', xx); cross.setAttribute('x2', xx); cross.setAttribute('visibility', 'visible');
    dots.innerHTML = '';
    if (!ev) return;
    var rows = [], snapT = null;
    draw.forEach(function (d) { var i = nearest(d.pts, ms); if (i == null) return; var p = d.pts[i]; snapT = p[0];
      var raw = d.s.pts.filter(function (q) { return q[0] === p[0]; })[0];
      dots.appendChild(sv('circle', {cx: X(p[0]), cy: Y(p[1]), r: 3.5, fill: d.s.color}));
      rows.push([d.s, raw ? raw[1] : p[1]]); });
    rows.sort(function (a, b) { return (b[1] || 0) - (a[1] || 0); });
    tip.innerHTML = '<div class="tt-t">' + fmtDate(snapT || ms) + '</div>' + rows.map(function (r) {
      return '<div class="tt-r"><span class="sw" style="display:inline-block;width:12px;height:3px;background:' + r[0].color + '"></span>' + esc(r[0].name) + '<b>' + fmtVal(r[1], unit, dec) + '</b></div>'; }).join('');
    tip.style.display = 'block';
    var x = ev.clientX + 16, y = ev.clientY + 12, tw = tip.offsetWidth, th = tip.offsetHeight;
    if (x + tw > window.innerWidth - 8) x = ev.clientX - tw - 16; if (y + th > window.innerHeight - 8) y = ev.clientY - th - 12;
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  function hide() { cross.setAttribute('visibility', 'hidden'); dots.innerHTML = ''; tip.style.display = 'none'; }
  var me = {show: function (ms) { showAt(ms); }, hide: function () { cross.setAttribute('visibility', 'hidden'); dots.innerHTML = ''; }, box: box};
  CROSS = CROSS.filter(function (c) { return document.body.contains(c.box) && c.box !== box; }); CROSS.push(me);
  function msAt(ev) { var r = svg.getBoundingClientRect(); return f + (ev.clientX - r.left - L) / pw * (t - f); }
  ov.addEventListener('mousemove', function (ev) {
    var ms = msAt(ev); showAt(ms, ev);
    CROSS.forEach(function (c) { if (c !== me) c.show(ms); });
    if (dragX != null) { var a = Math.min(dragX, ev.clientX), b = Math.max(dragX, ev.clientX), r = svg.getBoundingClientRect();
      selr.setAttribute('x', a - r.left); selr.setAttribute('width', b - a); selr.setAttribute('visibility', 'visible'); }
  });
  ov.addEventListener('mouseleave', function () { hide(); CROSS.forEach(function (c) { if (c !== me) c.hide(); }); });
  ov.addEventListener('mousedown', function (ev) { dragX = ev.clientX; ev.preventDefault(); });
  window.addEventListener('mouseup', function up(ev) {
    window.removeEventListener('mouseup', up);
    if (dragX == null) return;
    var a = dragX; dragX = null; selr.setAttribute('visibility', 'hidden');
    if (Math.abs(ev.clientX - a) > 6 && onZoom) {
      var r = svg.getBoundingClientRect(), m1 = f + (Math.min(a, ev.clientX) - r.left - L) / pw * (t - f), m2 = f + (Math.max(a, ev.clientX) - r.left - L) / pw * (t - f);
      onZoom(Math.round(m1), Math.round(m2));
    }
  });
}

/* ------------------------------------------------------- other panels */
function sparkPath(pts, w, h) {
  var p = pts.filter(function (x) { return x[0] != null && x[1] != null; }); if (p.length < 2) return null;
  var lo = Infinity, hi = -Infinity, a = p[0][0], b = p[p.length - 1][0];
  p.forEach(function (x) { lo = Math.min(lo, x[1]); hi = Math.max(hi, x[1]); }); if (hi === lo) hi = lo + 1;
  var d = p.map(function (x, i) { return (i ? 'L' : 'M') + ((x[0] - a) / (b - a || 1) * w).toFixed(1) + ',' + (h - (x[1] - lo) / (hi - lo) * h * .9).toFixed(1); }).join('');
  return d;
}
function drawStat(box, series, panel) {
  var dfl = panel.fieldConfig.defaults, o = panel.options || {}, calc = ((o.reduceOptions || {}).calcs || ['lastNotNull'])[0];
  if (!series.length) { box.innerHTML = '<div class="nodata">No data</div>'; return; }
  box.innerHTML = ''; var grid = el('div', 'stat-multi'); box.appendChild(grid);
  var n = series.length, W = box.clientWidth, H = box.clientHeight;
  var cols = W > H * 1.5 ? n : 1; grid.style.gridTemplateColumns = 'repeat(' + cols + ',1fr)';
  series.forEach(function (s) {
    var v = reduce(s.pts, calc), p = fmtParts(v, dfl.unit, dfl.decimals), c = dfl.color && dfl.color.mode === 'fixed' ? color(dfl.color.fixedColor) : thrColor(v, dfl.thresholds);
    var cell = el('div', 'stat'), bgMode = o.colorMode === 'background';
    if (bgMode) { cell.style.background = 'linear-gradient(120deg,' + c + ',' + c + 'cc)'; cell.style.color = '#fff'; }
    var cw = W / cols, ch = H / Math.ceil(n / cols), txt = p[0] + p[1];
    var fs = Math.max(12, Math.min(ch * (n > 1 ? .38 : .45), cw / (txt.length * .62 + 1)));
    cell.innerHTML = (n > 1 ? '<div class="n">' + esc(s.name) + '</div>' : '') + '<div class="v" style="font-size:' + fs.toFixed(0) + 'px;color:' + (bgMode ? '#fff' : c) + '">' +
      esc(p[0]) + '<span class="u">' + esc(p[1]) + '</span></div>';
    if (o.graphMode === 'area' && s.pts.length > 1 && s.pts[0][0] != null) {
      var sw = Math.max(10, cw), sh = ch * .38, d = sparkPath(s.pts, sw, sh);
      if (d) { cell.classList.add('has-spark'); var svg = sv('svg', {'class': 'spark', viewBox: '0 0 ' + sw + ' ' + sh, preserveAspectRatio: 'none'});
        var sc = bgMode ? 'rgba(255,255,255,.6)' : c;
        svg.appendChild(sv('path', {d: d + 'L' + sw + ',' + sh + 'L0,' + sh + 'Z', fill: sc, 'fill-opacity': bgMode ? .18 : .14}));
        svg.appendChild(sv('path', {d: d, fill: 'none', stroke: sc, 'stroke-width': 1.5, 'vector-effect': 'non-scaling-stroke'})); cell.appendChild(svg); }
    }
    grid.appendChild(cell);
  });
}
function arc(cx, cy, r, a0, a1) {
  var x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0), x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
  return 'M' + x0 + ',' + y0 + 'A' + r + ',' + r + ' 0 ' + (a1 - a0 > Math.PI ? 1 : 0) + ' 1 ' + x1 + ',' + y1;
}
function drawGauge(box, series, panel) {
  var dfl = panel.fieldConfig.defaults, calc = (((panel.options || {}).reduceOptions || {}).calcs || ['lastNotNull'])[0];
  if (!series.length) { box.innerHTML = '<div class="nodata">No data</div>'; return; }
  var s = series[0], v = reduce(s.pts, calc), mn = dfl.min != null ? dfl.min : 0, mx = dfl.max != null ? dfl.max : 100;
  var W = box.clientWidth, H = box.clientHeight, size = Math.min(W, H * 1.25), r = size * .4, cx = W / 2, cy = H / 2 + r * .3;
  var a0 = Math.PI * .75, a1 = Math.PI * 2.25, fr = Math.max(0, Math.min(1, ((v || 0) - mn) / (mx - mn)));
  var svg = sv('svg', {width: W, height: H}), c = thrColor(v, dfl.thresholds), tw = Math.max(4, r * .2);
  svg.appendChild(sv('path', {d: arc(cx, cy, r, a0, a1), fill: 'none', stroke: 'rgba(204,204,220,.1)', 'stroke-width': tw}));
  var steps = (dfl.thresholds || {}).steps || [];
  steps.forEach(function (st, i) {
    var from = i === 0 ? mn : st.value, to = i + 1 < steps.length ? steps[i + 1].value : mx;
    from = Math.max(mn, Math.min(mx, from)); to = Math.max(mn, Math.min(mx, to));
    if (to <= from) return;
    svg.appendChild(sv('path', {d: arc(cx, cy, r + tw * .9, a0 + (from - mn) / (mx - mn) * (a1 - a0), a0 + (to - mn) / (mx - mn) * (a1 - a0) - .001), fill: 'none', stroke: color(st.color), 'stroke-width': Math.max(2, tw * .25)}));
  });
  if (fr > 0) svg.appendChild(sv('path', {d: arc(cx, cy, r, a0, a0 + fr * (a1 - a0) - .0001), fill: 'none', stroke: c, 'stroke-width': tw}));
  var tx = sv('text', {x: cx, y: cy + r * .12, 'text-anchor': 'middle', fill: c, 'font-size': Math.max(12, r * .42), 'font-weight': 500});
  tx.textContent = fmtVal(v, dfl.unit, dfl.decimals); svg.appendChild(tx);
  box.innerHTML = ''; var g = el('div', 'gauge'); g.appendChild(svg); box.appendChild(g);
}
function drawBarGauge(box, series, panel) {
  var dfl = panel.fieldConfig.defaults, o = panel.options || {}, calc = ((o.reduceOptions || {}).calcs || ['lastNotNull'])[0];
  if (!series.length) { box.innerHTML = '<div class="nodata">No data</div>'; return; }
  var vals = series.map(function (s) { return reduce(s.pts, calc); }), mx = dfl.max != null ? dfl.max : Math.max.apply(null, vals.concat([0])) * 1.1 || 1, mn = dfl.min || 0;
  var useThr = ((dfl.thresholds || {}).steps || []).length > 1;
  box.innerHTML = '<div class="bg-rows">' + series.map(function (s, i) {
    var v = vals[i], c = useThr ? thrColor(v, dfl.thresholds) : PALETTE[i % PALETTE.length], w = Math.max(0, Math.min(100, ((v || 0) - mn) / (mx - mn) * 100));
    var bg = o.displayMode === 'gradient' ? 'linear-gradient(90deg,' + c + '33,' + c + ')' : c;
    return '<div class="bg-row"><span class="nm" title="' + esc(s.name) + '">' + esc(s.name) + '</span><div class="bg-bar' + (o.displayMode === 'lcd' ? ' lcd' : '') + '"><div style="width:' + w.toFixed(1) + '%;background:' + bg + '"></div></div>' +
      '<span class="val" style="color:' + c + '">' + fmtVal(v, dfl.unit, dfl.decimals) + '</span></div>';
  }).join('') + '</div>';
}
function drawTable(box, frames, panel) {
  var fr = (frames || [])[0];
  if (!fr || !fieldsOf(fr).length) { box.innerHTML = '<div class="nodata">No data</div>'; return; }
  var dfl = (panel.fieldConfig || {}).defaults || {}, F = fieldsOf(fr), V = valsOf(fr), n = (V[0] || []).length;
  var rows = []; for (var r = 0; r < n; r++) rows.push(V.map(function (c) { return c[r]; }));
  panel._sort = panel._sort || null;
  var sb = (panel.options && panel.options.sortBy && panel.options.sortBy[0]);
  if (!panel._sort && sb) { var si = F.findIndex(function (f) { return f.name === sb.displayName; }); if (si >= 0) panel._sort = [si, sb.desc]; }
  if (panel._sort) { var k = panel._sort[0], d = panel._sort[1] ? -1 : 1; rows.sort(function (a, b) { return a[k] > b[k] ? d : a[k] < b[k] ? -d : 0; }); }
  function cell(f, v) {
    if (v == null) return ['', ''];
    if (f.type === 'time') return [fmtDate(v), ''];
    if (f.type === 'number') {
      var cellOpt = override(panel, f.name, 'custom.cellOptions'), thr = override(panel, f.name, 'thresholds');
      var txt = (Number.isInteger(v) && !dfl.unit) ? String(v) : fmtVal(v, dfl.unit, dfl.decimals);
      var st = cellOpt && cellOpt.type === 'color-text' ? 'color:' + thrColor(v, thr || dfl.thresholds) : '';
      return [txt, st, true];
    }
    var cop = override(panel, f.name, 'custom.cellOptions'), mp = override(panel, f.name, 'mappings'), mc = null;
    (mp || []).forEach(function (m) { if (m.options && m.options[v] && m.options[v].color) mc = color(m.options[v].color); });
    if (mc && cop && cop.type === 'color-background') return [String(v), 'background:' + mc + ';color:#fff'];
    if (mc && mc !== 'text' && cop) return [String(v), 'color:' + mc];
    return [String(v), ''];
  }
  var h = '<table class="ptable"><thead><tr>' + F.map(function (f, i) {
    return '<th data-c="' + i + '">' + esc(f.name) + (panel._sort && panel._sort[0] === i ? (panel._sort[1] ? ' ↓' : ' ↑') : '') + '</th>'; }).join('') + '</tr></thead><tbody>';
  rows.forEach(function (r) { h += '<tr>' + r.map(function (v, i) { var c = cell(F[i], v); return '<td' + (c[2] ? ' class="num"' : '') + ' style="' + c[1] + '">' + esc(c[0]) + '</td>'; }).join('') + '</tr>'; });
  box.innerHTML = h + '</tbody></table>'; box.classList.add('scroll');
  $$('th', box).forEach(function (th) { th.onclick = function () { var c = +th.dataset.c;
    panel._sort = panel._sort && panel._sort[0] === c ? (panel._sort[1] ? null : [c, true]) : [c, false]; drawTable(box, frames, panel); }; });
}
function drawAlertList(box) {
  fetch('/api/prometheus/grafana/api/v1/rules').then(function (r) { return r.json(); }).then(function (j) {
    var rules = []; j.data.groups.forEach(function (g) { g.rules.forEach(function (r) { r.folder = g.file; rules.push(r); }); });
    rules.sort(function (a, b) { return (a.state === 'firing' ? 0 : 1) - (b.state === 'firing' ? 0 : 1); });
    box.innerHTML = '<div class="alertlist">' + rules.map(function (r) {
      var f = r.state === 'firing', n = r.alerts.filter(function (a) { return a.state === 'Alerting'; }).length;
      return '<div class="ai"><span class="badge ' + (f ? 'bad' : 'ok') + '">' + (f ? 'Firing' : 'Normal') + '</span><a href="/alerting/grafana/' + r.uid + '/view">' + esc(r.name) + '</a>' +
        '<span class="tb-spacer"></span><span class="muted small">' + (f ? n + ' firing' : esc(r.folder)) + '</span></div>'; }).join('') + '</div>';
    box.classList.add('scroll');
  });
}

/* ------------------------------------------------------------ dashboard */
function interpolate(str, vars, kind) {
  return str.replace(/\$\{(\w+)(?::\w+)?\}|\$(\w+)|\[\[(\w+)\]\]/g, function (m, a, b, c) {
    var n = a || b || c; if (n.indexOf('__') === 0) return m;
    var v = vars[n]; if (!v) return m;
    var val = v.current.value;
    if (val === '$__all' || (Array.isArray(val) && val.indexOf('$__all') >= 0)) {
      var all = v.options.map(function (o) { return o.value; }).filter(function (x) { return x !== '$__all'; });
      return kind === 'prom' ? all.join('|') : all.join("','");
    }
    return Array.isArray(val) ? val.join(kind === 'prom' ? '|' : "','") : val;
  });
}
function runQueries(targets, range, maxPts, headers) {
  var body = {queries: targets.map(function (t) { var q = JSON.parse(JSON.stringify(t)); q.maxDataPoints = maxPts || 600; q.intervalMs = 60000; return q; }),
    from: String(range.from), to: String(range.to)};
  var h = {'Content-Type': 'application/json'}; for (var k in (headers || {})) h[k] = headers[k];
  var t0 = performance.now();
  return fetch('/api/ds/query', {method: 'POST', headers: h, body: JSON.stringify(body)}).then(function (r) {
    if (r.status === 401) { location.href = '/login'; return Promise.reject('unauthorized'); }
    return r.json().then(function (j) { return {req: body, res: j, status: r.status, ms: performance.now() - t0}; });
  });
}
function Dashboard() {
  var D = P.dashboard, meta = P.meta, root = $('#dashboard');
  var qs = new URLSearchParams(location.search);
  var state = {range: {from: qs.get('from') || D.time.from, to: qs.get('to') || D.time.to},
    refresh: qs.has('refresh') ? qs.get('refresh') : (D.refresh || ''), view: qs.get('viewPanel')};
  var vars = {};
  (D.templating.list || []).forEach(function (v) {
    var x = JSON.parse(JSON.stringify(v)); vars[v.name] = x;
    var u = qs.getAll('var-' + v.name);
    if (u.length) x.current = {text: u.join(' + '), value: u.length > 1 ? u : (u[0] === 'All' ? '$__all' : u[0])};
    if (x.type === 'custom' && x.includeAll) x.options = [{text: 'All', value: '$__all'}].concat(x.options);
  });
  var isHome = meta.isHome;
  root.innerHTML = '<div class="dash-nav"><div class="dash-title">' + (isHome ? '' : '<a class="folder" href="' + (meta.folderUid ? '/dashboards/f/' + meta.folderUid + '/' : '/dashboards') + '">' + esc(meta.folderTitle) + '</a><span class="muted">/</span>') +
    '<span>' + esc(D.title) + '</span>' + (isHome ? '' : '<button class="star-btn ' + (meta.isStarred ? 'starred' : '') + '" data-uid="' + D.uid + '" title="Mark as favorite">' + ic(I.star) + '</button>' +
    '<button class="btn-icon" id="dShare" title="Share dashboard">' + ic(I.share) + '</button>') + '</div>' +
    '<div class="tools" style="display:inline-flex;gap:6px;align-items:center">' + (isHome ? '' : '<button class="btn-icon" id="dSave" title="Save dashboard">' + ic('<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v6h8V3M8 21v-7h8v7"/>') + '</button>' +
    '<button class="btn-icon" id="dSettings" title="Dashboard settings">' + ic(I.cog) + '</button>') + '<span id="dTime"></span></div></div>' +
    '<div class="submenu" id="dVars"></div><div class="grid" id="dGrid"></div>';
  var tp = TimePicker($('#dTime'), state, function (what) {
    if (what === 'refresh') { setTimer(); pushUrl(); return; }
    if (what === 'range') pushUrl();
    refreshAll();
  }, true);
  function pushUrl() {
    var p = new URLSearchParams();
    if (!isHome || state.range.from !== D.time.from) { p.set('orgId', '1'); p.set('from', state.range.from); p.set('to', state.range.to); }
    Object.keys(vars).forEach(function (n) { var v = vars[n].current.value; (Array.isArray(v) ? v : [v]).forEach(function (x) { p.append('var-' + n, x === '$__all' ? 'All' : x); }); });
    if (state.refresh) p.set('refresh', state.refresh);
    if (state.view) p.set('viewPanel', state.view);
    if (qs.has('kiosk')) p.set('kiosk', '');
    if (qs.get('playlist')) { p.set('playlist', qs.get('playlist')); p.set('pi', qs.get('pi')); }
    history.replaceState(null, '', location.pathname + '?' + p.toString().replace('kiosk=', 'kiosk'));
  }
  var timer = null;
  function setTimer() { if (timer) clearInterval(timer); timer = null;
    var m = /^(\d+)([smh])$/.exec(state.refresh || ''); if (m) timer = setInterval(function () { if (!document.hidden) refreshAll(); }, +m[1] * {s: 1e3, m: 6e4, h: 36e5}[m[2]]); }
  setTimer();
  // variables
  var varBox = $('#dVars');
  function renderVars() {
    varBox.innerHTML = '';
    Object.keys(vars).forEach(function (n) {
      var v = vars[n], w = el('div', 'var'); w.innerHTML = '<label>' + esc(v.label || n) + '</label>';
      var s = el('select'); (v.options || []).forEach(function (o) { var op = el('option'); op.value = o.value; op.textContent = o.text;
        var cur = Array.isArray(v.current.value) ? v.current.value[0] : v.current.value; if (cur === o.value) op.selected = true; s.appendChild(op); });
      s.onchange = function () { v.current = {text: s.options[s.selectedIndex].text, value: s.value};
        loadVars(n).then(function () { renderVars(); pushUrl(); $$('.panel-t', grid).forEach(function (t) { var pp = t.closest('.panel')._p; t.textContent = interpolate(pp.title || '', vars, 'sql'); }); refreshAll(); }); };
      w.appendChild(s); varBox.appendChild(w);
    });
  }
  function loadVar(n) {
    var v = vars[n]; if (v.type !== 'query') return Promise.resolve();
    var qtxt = interpolate(v.query, vars, v.datasource.type === 'mysql' ? 'sql' : 'prom');
    var t = v.datasource.type === 'mysql' ? {refId: 'A', datasource: v.datasource, rawSql: qtxt, format: 'table'} : {refId: 'A', datasource: v.datasource, expr: qtxt};
    return runQueries([t], state.range, 100, {'X-Dashboard-Uid': D.uid, 'X-Panel-Id': 'var:' + n}).then(function (r) {
      var fr = (((r.res.results || {}).A || {}).frames || [])[0], vals = fr ? (valsOf(fr)[0] || []) : [];
      v.options = vals.map(function (x) { return {text: String(x), value: String(x)}; });
      if (v.includeAll) v.options.unshift({text: 'All', value: '$__all'});
      var cur = v.current && v.current.value;
      if (!v.options.some(function (o) { return o.value === cur; }))
        v.current = v.options.length ? {text: v.options[0].text, value: v.options[0].value} : {text: 'None', value: ''};
    }).catch(function () {});
  }
  function loadVars(after) {
    var names = Object.keys(vars), i = after ? names.indexOf(after) + 1 : 0;
    var p = Promise.resolve();
    names.slice(i).forEach(function (n) { p = p.then(function () { return loadVar(n); }); });
    return p;
  }
  // panels
  var grid = $('#dGrid'), panels = D.panels;
  function vp() { return state.view ? panels.filter(function (p) { return String(p.id) === String(state.view); }) : panels; }
  function layout() {
    grid.innerHTML = ''; grid.classList.toggle('view', !!state.view);
    vp().forEach(function (p) {
      var g = p.gridPos, pe = el('div', 'panel' + (p.type === 'text' ? ' transparent' : ''));
      pe.style.gridColumn = (g.x + 1) + ' / span ' + g.w; pe.style.gridRow = (g.y + 1) + ' / span ' + g.h;
      pe.innerHTML = '<div class="panel-h">' + (p.description ? '<span class="panel-desc" title="' + esc(p.description) + '">' + ic(I.info, 14) + '</span>' : '') +
        '<span class="panel-t">' + esc(interpolate(p.title || '', vars, 'sql')) + '</span>' +
        (p.title || p.type !== 'text' ? '<div class="dd pm"><button class="btn-icon" data-dd style="height:24px;min-width:24px">' + ic(I.menu) + '</button><div class="dd-menu right">' +
          '<button class="dd-item" data-a="view">' + ic(I.eye) + ' View <span class="tb-spacer"></span><span class="muted small">v</span></button>' +
          (p.targets ? '<button class="dd-item" data-a="explore">' + ic(I.compass) + ' Explore <span class="tb-spacer"></span><span class="muted small">x</span></button>' +
          '<button class="dd-item" data-a="inspect">' + ic(I.info) + ' Inspect <span class="tb-spacer"></span><span class="muted small">i</span></button>' : '') +
          '<button class="dd-item" data-a="share">' + ic(I.share) + ' Share</button><button class="dd-item" data-a="json">' + ic(I.doc) + ' Panel JSON</button></div></div>' : '') +
        '</div><div class="panel-b"></div>';
      if (!p.title && p.type === 'text') $('.panel-h', pe).style.display = 'none';
      pe._p = p; p._el = pe; grid.appendChild(pe);
      pe.addEventListener('click', function (e) { var a = e.target.closest('[data-a]'); if (!a) return; closeDD(); panelAction(p, a.dataset.a); });
      pe.addEventListener('mouseenter', function () { hoverPanel = p; });
    });
  }
  var hoverPanel = null;
  function panelAction(p, a) {
    if (a === 'view') { state.view = state.view ? null : p.id; pushUrl(); layout(); refreshAll(); }
    if (a === 'explore') {
      var t = p.targets.map(function (t) { var q = JSON.parse(JSON.stringify(t)); if (q.rawSql) q.rawSql = interpolate(q.rawSql, vars, 'sql'); if (q.expr) q.expr = interpolate(q.expr, vars, 'prom'); return q; });
      location.href = '/explore?left=' + encodeURIComponent(JSON.stringify({datasource: (p.datasource || {}).uid, queries: t, range: state.range}));
    }
    if (a === 'inspect') inspect(p);
    if (a === 'share') shareModal(location.origin + meta.url + '?orgId=1&from=' + encodeURIComponent(state.range.from) + '&to=' + encodeURIComponent(state.range.to) + '&viewPanel=' + p.id);
    if (a === 'json') { var c = JSON.parse(JSON.stringify(p, function (k, v) { return k.charAt(0) === '_' ? undefined : v; }));
      modal('Panel JSON', '<pre class="code-block" style="max-height:60vh">' + esc(JSON.stringify(c, null, 2)) + '</pre>', true); }
  }
  function inspect(p) {
    var last = p._last || {};
    var d = el('div', 'drawer');
    d.innerHTML = '<div class="modal-h"><h3>Inspect: ' + esc(p.title) + '</h3><button class="btn-icon" data-close>' + ic(I.x) + '</button></div>' +
      '<div style="padding:0 16px"><div class="tabs"><a class="tab active" data-t="data">Data</a><a class="tab" data-t="stats">Stats</a><a class="tab" data-t="json">JSON</a><a class="tab" data-t="query">Query</a></div></div><div class="modal-b" id="insB"></div>';
    document.body.appendChild(d);
    function show(tab) {
      $$('.tab', d).forEach(function (t) { t.classList.toggle('active', t.dataset.t === tab); });
      var b = $('#insB', d), frames = [];
      Object.keys((last.res || {}).results || {}).forEach(function (k) { frames = frames.concat(last.res.results[k].frames || []); });
      if (tab === 'data') {
        if (!frames.length) { b.innerHTML = '<p class="muted">No data</p>'; return; }
        b.innerHTML = '<div style="display:flex;gap:8px;margin-bottom:8px"><span class="muted small">' + frames.length + ' frame(s)</span><span class="tb-spacer"></span><button class="btn btn-secondary btn-sm" id="insCsv">Download CSV</button></div><div id="insT"></div>';
        var bx = $('#insT', b); drawTable(bx, [frames[0]], {fieldConfig: {defaults: {}}, options: {}});
        $('#insCsv', b).onclick = function () { var F = fieldsOf(frames[0]), V = valsOf(frames[0]), n = (V[0] || []).length, lines = [F.map(function (f) { return '"' + f.name + '"'; }).join(',')];
          for (var i = 0; i < n; i++) lines.push(V.map(function (c) { return F[V.indexOf(c)].type === 'time' ? fmtDate(c[i]) : c[i]; }).join(','));
          var a = el('a'); a.href = URL.createObjectURL(new Blob([lines.join('\n')], {type: 'text/csv'})); a.download = p.title.replace(/\W+/g, '-') + '-data-' + fmtDate(Date.now()).replace(/\W/g, '') + '.csv'; a.click(); };
      } else if (tab === 'stats') {
        var rows = (frames.length ? frames.reduce(function (a, f) { return a + (valsOf(f)[0] || []).length; }, 0) : 0);
        b.innerHTML = '<table class="table kvt"><tr><td>Total request time</td><td>' + (last.ms || 0).toFixed(0) + ' ms</td></tr><tr><td>Number of queries</td><td>' + (p.targets || []).length +
          '</td></tr><tr><td>Total number rows</td><td>' + rows + '</td></tr><tr><td>Data source</td><td>' + esc((p.datasource || {}).uid || '') + '</td></tr></table>';
      } else if (tab === 'json') {
        b.innerHTML = '<pre class="code-block">' + esc(JSON.stringify(JSON.parse(JSON.stringify(p, function (k, v) { return k.charAt(0) === '_' ? undefined : v; })), null, 2)) + '</pre>';
      } else {
        b.innerHTML = '<p class="muted">Query inspector allows you to view raw request and response.</p><h4>Request</h4><pre class="code-block">POST /api/ds/query\n' + esc(JSON.stringify(last.req || {}, null, 2)) +
          '</pre><h4>Response</h4><pre class="code-block" style="max-height:40vh">' + esc(JSON.stringify(last.res || {}, null, 2).slice(0, 40000)) + '</pre>';
      }
    }
    d.addEventListener('click', function (e) { var t = e.target.closest('[data-t]'); if (t) show(t.dataset.t); if (e.target.closest('[data-close]')) d.remove(); });
    show('data');
  }
  function resolved() { return {f: parseT(state.range.from), t: parseT(state.range.to, true)}; }
  function zoomTo(a, b) { state.range = {from: String(a), to: String(b)}; tp.sync(); pushUrl(); refreshAll(); }
  function renderPanel(p) {
    var pe = p._el, body = $('.panel-b', pe);
    if (!pe) return;
    var old = $('.panel-err', pe); if (old) old.remove();
    if (p.type === 'text') { body.innerHTML = '<div class="textp">' + ((p.options || {}).content || '') + '</div>'; return; }
    if (p.type === 'dashlist') { body.classList.add('scroll'); body.innerHTML = '<div class="dashlist">' + ((p._items || []).map(function (it) { return '<a href="' + it.url + '">' + ic(I.apps) + esc(it.title) + '<span class="f">' + esc(it.folder) + '</span></a>'; }).join('') || '<div class="muted small">No dashboards</div>') + '</div>'; return; }
    if (p.type === 'alertlist') { drawAlertList(body); return; }
    var ld = el('div', 'panel-load'); pe.appendChild(ld);
    var targets = (p.targets || []).map(function (t) { var q = JSON.parse(JSON.stringify(t)); if (q.rawSql) q.rawSql = interpolate(q.rawSql, vars, 'sql'); if (q.expr) q.expr = interpolate(q.expr, vars, 'prom'); return q; });
    var w = body.clientWidth || 600;
    runQueries(targets, state.range, Math.min(1200, Math.max(100, Math.round(w))), {'X-Dashboard-Uid': D.uid, 'X-Panel-Id': String(p.id)}).then(function (r) {
      ld.remove(); p._last = r;
      var frames = [], errs = [];
      Object.keys(r.res.results || {}).forEach(function (k) { var x = r.res.results[k]; if (x.error) errs.push(x.error); frames = frames.concat(x.frames || []); });
      p._frames = frames; draw(p);
      if (errs.length) { var e = el('div', 'panel-err', '<span>!</span>'); e.title = errs.join('\n'); pe.appendChild(e); }
    }).catch(function (e) { ld.remove(); });
  }
  function draw(p) {
    var body = $('.panel-b', p._el), frames = p._frames || [];
    var series = toSeries(frames);
    if (p.type === 'timeseries') drawTimeseries(body, series, p, resolved(), zoomTo);
    else if (p.type === 'stat') drawStat(body, series, p);
    else if (p.type === 'gauge') drawGauge(body, series, p);
    else if (p.type === 'bargauge') drawBarGauge(body, series, p);
    else if (p.type === 'table') drawTable(body, frames, p);
  }
  function refreshAll() { vp().forEach(renderPanel); }
  var rt; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { vp().forEach(function (p) { if (p._frames) draw(p); }); }, 150); });
  // keyboard
  var lastKey = '';
  document.addEventListener('keydown', function (e) {
    if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || e.ctrlKey || e.metaKey) return;
    var k = e.key;
    if (lastKey === 'd' && k === 'r') refreshAll();
    if (lastKey === 't' && k === 'z') $('.tp-zoom').click();
    if (lastKey === 't' && (k === 'ArrowLeft' || k === 'ArrowRight')) {
      var r = resolved(), sp = r.t - r.f, dir = k === 'ArrowLeft' ? -1 : 1; zoomTo(Math.round(r.f + dir * sp / 2), Math.round(Math.min(Date.now(), r.t + dir * sp / 2)));
    }
    if (hoverPanel && k === 'v') panelAction(hoverPanel, 'view');
    if (hoverPanel && k === 'i' && hoverPanel.targets) panelAction(hoverPanel, 'inspect');
    if (hoverPanel && k === 'x' && hoverPanel.targets) panelAction(hoverPanel, 'explore');
    if (k === 'Escape' && state.view) { state.view = null; pushUrl(); layout(); refreshAll(); }
    lastKey = k;
  });
  var sh = $('#dShare'); if (sh) sh.onclick = function () { shareModal(location.origin + meta.url + '?orgId=1&from=' + encodeURIComponent(state.range.from) + '&to=' + encodeURIComponent(state.range.to)); };
  var sv_ = $('#dSave'); if (sv_) sv_.onclick = function () {
    modal('Cannot save provisioned dashboard', '<p>This dashboard cannot be saved from the Grafana UI because it has been provisioned from another source. Copy the JSON or save it to a file below, then you can update your dashboard in the provisioning source.</p>' +
      '<p class="muted small">File path: /etc/grafana/provisioning/dashboards/' + esc(meta.folderUid || 'general') + '/' + esc(meta.provisionedExternalId) + '</p>');
  };
  var st = $('#dSettings'); if (st) st.onclick = function () {
    var c = JSON.parse(JSON.stringify(D, function (k, v) { return k.charAt(0) === '_' ? undefined : v; }));
    modal('Settings › JSON Model', '<p class="muted">The JSON model below is the data structure that defines the dashboard. This includes dashboard settings, panel settings, layout, queries, and so on.</p><pre class="code-block" style="max-height:60vh">' + esc(JSON.stringify(c, null, 2)) + '</pre>', true);
  };
  // playlist
  if (qs.get('playlist')) {
    fetch('/api/playlists').then(function (r) { return r.json(); });
  }
  loadVars().then(function () { renderVars(); layout(); refreshAll(); });
  renderVars();
}

/* -------------------------------------------------------------- explore */
function Explore() {
  var dss = P.datasources, ds = dss.filter(function (d) { return d.uid === P.datasource; })[0] || dss[0];
  var state = {range: P.range || {from: 'now-1h', to: 'now'}, queries: P.queries};
  var picker = $('#dsPicker');
  picker.innerHTML = '<select>' + dss.map(function (d) { return '<option value="' + d.uid + '"' + (d.uid === ds.uid ? ' selected' : '') + '>' + esc(d.name) + ' (' + esc(d.typeName) + ')</option>'; }).join('') + '</select>';
  $('select', picker).onchange = function () { ds = dss.filter(function (d) { return d.uid === this.value; }, this)[0];
    state.queries = [defaultQuery('A')]; renderQueries(); pushUrl(); $('#exResults').innerHTML = ''; };
  var sp = $('#exSplit'); if (sp) sp.onclick = function () { window.open(location.href, '_blank'); };
  $('#exAddToDash').onclick = function () { modal('Add panel to dashboard', '<div class="alert alert-info">' + ic(I.info) + ' Dashboards on this instance are provisioned from the <code>grafana-dashboards</code> repository and cannot be modified from the UI.</div>'); };
  TimePicker($('#exTime'), state, function () { pushUrl(); run(); }, false);
  function defaultQuery(ref) {
    if (ds.type === 'mysql') return {refId: ref, rawSql: '', format: 'table'};
    if (ds.type === 'prometheus') return {refId: ref, expr: '', legendFormat: '', range: true, instant: false};
    return {refId: ref, scenarioId: 'random_walk', seriesCount: 1};
  }
  var host = $('#exQueries');
  // keep server-rendered textarea content as initial SQL
  var ta0 = $('textarea', host); if (ta0 && ds.type === 'mysql' && state.queries[0] && ta0.value) state.queries[0].rawSql = ta0.value;
  function renderQueries() {
    host.innerHTML = '';
    state.queries.forEach(function (q, i) {
      var row = el('div', 'query-row');
      var head = '<div class="qr-head"><span class="ref">' + q.refId + '</span><span class="muted">(' + esc(ds.name) + ')</span><span class="tb-spacer"></span>' +
        (state.queries.length > 1 ? '<button type="button" class="btn-icon" data-rm title="Remove query">' + ic(I.trash, 14) + '</button>' : '') + '</div>';
      if (ds.type === 'mysql') {
        row.innerHTML = head + '<div class="qr-opts"><span class="muted">Format</span><select data-k="format"><option value="table">Table</option><option value="time_series">Time series</option></select>' +
          '<span class="seg"><button type="button" disabled>Builder</button><button type="button" class="on">Code</button></span><span class="muted small">Run with Shift+Enter · macros: $__unixEpochFilter(col), $__timeFilter(col), $__unixEpochGroupAlias(col, $__interval)</span></div>' +
          '<textarea class="code" data-k="rawSql" spellcheck="false" rows="6" placeholder="SELECT ..."></textarea>';
        $('[data-k=format]', row).value = q.format || 'table'; $('[data-k=rawSql]', row).value = q.rawSql || '';
      } else if (ds.type === 'prometheus') {
        row.innerHTML = head + '<div class="qr-opts"><div class="dd"><button type="button" class="btn btn-secondary btn-sm" data-dd>Metrics browser ' + ic(I.angle, 12) + '</button><div class="dd-menu metric-dd">' +
          P.metrics.map(function (m) { return '<button type="button" class="dd-item" data-m="' + m + '">' + m + '</button>'; }).join('') + '</div></div>' +
          '<span class="tb-spacer"></span><span class="muted">Legend</span><input data-k="legendFormat" placeholder="{{instance}}" style="width:160px"><span class="muted">Type</span><select data-k="qtype"><option value="range">Range</option><option value="instant">Instant</option></select></div>' +
          '<input class="code" data-k="expr" placeholder="Enter a PromQL query… (run with Shift+Enter)" spellcheck="false">';
        $('[data-k=expr]', row).value = q.expr || ''; $('[data-k=legendFormat]', row).value = q.legendFormat || ''; $('[data-k=qtype]', row).value = q.instant ? 'instant' : 'range';
        row.addEventListener('click', function (e) { var m = e.target.closest('[data-m]'); if (m) { $('[data-k=expr]', row).value = m.dataset.m; closeDD(); collect(); } });
      } else {
        row.innerHTML = head + '<div class="qr-opts"><span class="muted">Scenario</span><select data-k="scenarioId"><option value="random_walk">Random Walk</option><option value="sine">Sine wave</option></select>' +
          '<span class="muted">Series count</span><input data-k="seriesCount" type="number" min="1" max="10" style="width:70px"></div>';
        $('[data-k=scenarioId]', row).value = q.scenarioId || 'random_walk'; $('[data-k=seriesCount]', row).value = q.seriesCount || 1;
      }
      row.addEventListener('change', collect); row.addEventListener('input', collect);
      row.addEventListener('keydown', function (e) { if (e.key === 'Enter' && (e.shiftKey || e.ctrlKey)) { e.preventDefault(); collect(); run(); } });
      var rm = $('[data-rm]', row); if (rm) rm.onclick = function () { state.queries.splice(i, 1); renderQueries(); };
      host.appendChild(row);
    });
  }
  function collect() {
    $$('.query-row', host).forEach(function (row, i) { var q = state.queries[i]; if (!q) return;
      $$('[data-k]', row).forEach(function (f) { var k = f.dataset.k, v = f.value;
        if (k === 'qtype') { q.instant = v === 'instant'; q.range = v === 'range'; } else if (k === 'seriesCount') q[k] = +v; else q[k] = v; }); });
  }
  function pushUrl() { history.replaceState(null, '', '/explore?orgId=1&left=' + encodeURIComponent(JSON.stringify({datasource: ds.uid, queries: state.queries, range: state.range}))); }
  var acts = $('#exActions');
  acts.innerHTML = '<button class="btn btn-secondary btn-sm" id="exAdd">' + ic(I.plus) + ' Add query</button><button class="btn btn-secondary btn-sm" id="exHist">' + ic(I.history) + ' Query history</button>' +
    '<button class="btn btn-secondary btn-sm" id="exInsp">' + ic(I.info) + ' Query inspector</button>';
  $('#exAdd').onclick = function () { collect(); state.queries.push(defaultQuery(String.fromCharCode(65 + state.queries.length))); renderQueries(); };
  $('#exRun').onclick = function () { collect(); pushUrl(); run(); };
  $('#exForm').addEventListener('submit', function (e) { e.preventDefault(); collect(); pushUrl(); run(); });
  var last = null;
  $('#exInsp').onclick = function () {
    if (!last) { toast('Run a query first'); return; }
    modal('Query inspector', '<table class="table kvt"><tr><td>Total request time</td><td>' + last.ms.toFixed(0) + ' ms</td></tr></table><h4>Request</h4><pre class="code-block">POST /api/ds/query\n' + esc(JSON.stringify(last.req, null, 2)) +
      '</pre><h4>Response</h4><pre class="code-block" style="max-height:45vh">' + esc(JSON.stringify(last.res, null, 2).slice(0, 60000)) + '</pre>', true);
  };
  $('#exHist').onclick = function () {
    fetch('/api/query-history').then(function (r) { return r.json(); }).then(function (j) {
      var items = j.result.queryHistory;
      var d = el('div', 'drawer');
      d.innerHTML = '<div class="modal-h"><h3>' + ic(I.history) + ' Query history</h3><button class="btn-icon" data-close>' + ic(I.x) + '</button></div><div class="modal-b"><div class="ex-hist">' +
        items.map(function (h, i) { var q = h.queries[0], txt = q.rawSql || q.expr || '', dn = (dss.filter(function (x) { return x.uid === h.datasourceUid; })[0] || {}).name || h.datasourceUid;
          return '<div class="h"><div style="flex:1"><div class="muted small">' + esc(dn) + ' · ' + fmtDate(h.createdAt * 1000, false) + (h.starred ? ' · ★' : '') + '</div><pre>' + esc(txt) + '</pre></div>' +
            '<button class="btn btn-secondary btn-sm" data-h="' + i + '">Run query</button></div>'; }).join('') + '</div></div>';
      document.body.appendChild(d);
      d.addEventListener('click', function (e) {
        if (e.target.closest('[data-close]')) d.remove();
        var b = e.target.closest('[data-h]'); if (!b) return;
        var h = items[+b.dataset.h], nd = dss.filter(function (x) { return x.uid === h.datasourceUid; })[0] || ds;
        ds = nd; $('select', picker).value = ds.uid; var q = h.queries[0];
        state.queries = [ds.type === 'mysql' ? {refId: 'A', rawSql: q.rawSql, format: 'table'} : {refId: 'A', expr: q.expr, legendFormat: '', range: true}];
        renderQueries(); pushUrl(); d.remove(); run();
      });
    });
  };
  var res = $('#exResults');
  function run() {
    collect();
    var qs = state.queries.filter(function (q) { return (q.rawSql || q.expr || q.scenarioId || '').trim(); }).map(function (q) { var x = JSON.parse(JSON.stringify(q)); x.datasource = {uid: ds.uid, type: ds.type}; return x; });
    if (!qs.length) return;
    res.innerHTML = '<div class="ex-card"><div class="panel-load"></div><div class="ex-card-b muted">Loading…</div></div>';
    runQueries(qs, state.range, Math.max(200, res.clientWidth || 800)).then(function (r) {
      last = r;
      var frames = [], errs = [], notices = [];
      Object.keys(r.res.results || {}).forEach(function (k) { var x = r.res.results[k]; if (x.error) errs.push(k + ': ' + x.error); (x.frames || []).forEach(function (f) { frames.push(f); }); });
      var html = errs.map(function (e) { return '<div class="alert alert-error">' + esc(e) + '</div>'; }).join('');
      var ts = frames.filter(function (f) { return fieldsOf(f).some(function (x) { return x.type === 'time'; }) && fieldsOf(f).some(function (x) { return x.type === 'number'; }); });
      var tabular = frames.filter(function (f) { return fieldsOf(f).length; });
      var affected = frames.filter(function (f) { return !fieldsOf(f).length && f.schema.meta && f.schema.meta.custom; });
      affected.forEach(function (f) { html += '<div class="alert alert-success">Query OK, ' + f.schema.meta.custom.rowsAffected + ' row(s) affected (' + (f.schema.meta.stats[0].value) + ' ms)</div>'; });
      frames.forEach(function (f) { ((f.schema.meta || {}).notices || []).forEach(function (n) { notices.push(n.text); }); });
      if (ts.length) html += '<div class="ex-card"><div class="ex-card-h">Graph<span class="tb-spacer"></span><span class="muted small">' + ts.length + ' series</span></div><div class="ex-card-b"><div class="ex-graph" id="exG"></div></div></div>';
      if (tabular.length) {
        var nrows = valsOf(tabular[0])[0] ? valsOf(tabular[0])[0].length : 0;
        html += '<div class="ex-card"><div class="ex-card-h">Table' + (tabular.length > 1 ? ' <select id="exFr" style="width:auto;height:26px;margin-left:8px">' + tabular.map(function (f, i) { return '<option value="' + i + '">' + esc(f.schema.name || f.schema.refId + ' ' + (i + 1)) + '</option>'; }).join('') + '</select>' : '') +
          '<span class="tb-spacer"></span><span class="muted small" id="exRows">' + nrows + ' rows</span></div><div class="ex-card-b" id="exT"></div></div>';
      }
      if (!frames.length && !errs.length) html += '<div class="ex-card"><div class="ex-card-b muted">No data</div></div>';
      res.innerHTML = html;
      if (ts.length) drawTimeseries($('#exG'), toSeries(ts), {fieldConfig: {defaults: {custom: {fillOpacity: 10, lineWidth: 1}}}, options: {legend: {displayMode: 'list', placement: 'bottom', calcs: []}}},
        {f: parseT(state.range.from), t: parseT(state.range.to, true)}, function (a, b) { state.range = {from: String(a), to: String(b)}; pushUrl(); location.reload(); });
      if (tabular.length) {
        var showT = function (i) { var f = tabular[i]; drawTable($('#exT'), [f], {fieldConfig: {defaults: {}}, options: {}}); $('#exRows').textContent = ((valsOf(f)[0] || []).length) + ' rows'; };
        showT(0); var sel = $('#exFr'); if (sel) sel.onchange = function () { showT(+sel.value); };
      }
    });
  }
  renderQueries();
  if (!res.innerHTML.trim()) run();
}

/* ---------------------------------------------------------- small pages */
function filterRows(inputSel, rowSel, textOf) {
  var i = $(inputSel); if (!i) return;
  i.addEventListener('input', function () { var q = i.value.toLowerCase(); $$(rowSel).forEach(function (r) { r.style.display = textOf(r).indexOf(q) >= 0 ? '' : 'none'; }); });
}
if (P.page === 'browse') {
  $$('.b-folder').forEach(function (f) {
    f.querySelector('.fold-tog').onclick = function () { f.classList.toggle('open'); var on = f.classList.contains('open');
      $$('.fold-child[data-folder="' + f.dataset.folder + '"]').forEach(function (r) { r.style.display = on ? '' : 'none'; }); };
  });
  var bs = $('#bSearch'), bt = $('#bTag');
  function bf() {
    var q = bs.value.toLowerCase(), tag = bt.value, any = q || tag;
    $$('.b-row').forEach(function (r) { var ok = (!q || r.dataset.title.indexOf(q) >= 0) && (!tag || r.dataset.tags.split(',').indexOf(tag) >= 0); r.style.display = (any ? ok : !r.classList.contains('fold-child')) ? '' : 'none'; });
    $$('.b-folder').forEach(function (f) { f.style.display = any ? 'none' : ''; f.classList.remove('open'); });
  }
  bs.addEventListener('input', bf); bt.addEventListener('change', bf);
  document.addEventListener('click', function (e) { var t = e.target.closest('.tag'); if (t) { bt.value = t.dataset.tag; bf(); } });
  $('#bStarred').onchange = function () { location.href = this.checked ? '/dashboards?starred=true' : '/dashboards'; };
}
if (P.page === 'plugins') {
  var pf = function () { var q = $('#pSearch').value.toLowerCase(), t = $('#pType').value;
    $$('.plugin-card').forEach(function (c) { c.style.display = (c.dataset.name.indexOf(q) >= 0 && (!t || c.dataset.type === t)) ? '' : 'none'; }); };
  $('#pSearch').addEventListener('input', pf); $('#pType').addEventListener('change', pf);
}
if (P.page === 'dslist') filterRows('#dsSearch', '.ds-card', function (r) { return r.textContent.toLowerCase(); });
if (P.page === 'users') filterRows('#uSearch', '.users tbody tr', function (r) { return r.textContent.toLowerCase(); });
if (P.page === 'dsnew') $$('[data-add]').forEach(function (c) { c.onclick = function () {
  modal('Add data source', '<div class="alert alert-info">' + ic(I.info) + ' Data sources on this instance are provisioned from <code>/etc/grafana/provisioning/datasources</code>. Ask the Infrastructure team to add a new connection.</div>'); }; });
if (P.page === 'alerts') {
  var stF = '', rs = $('#ruleSearch');
  var af = function () { var q = rs.value.toLowerCase(); $$('.rule').forEach(function (r) { r.style.display = (r.textContent.toLowerCase().indexOf(q) >= 0 && (!stF || r.dataset.state === stF)) ? '' : 'none'; }); };
  rs.addEventListener('input', af);
  $$('#ruleState button').forEach(function (b) { b.onclick = function () { $$('#ruleState button').forEach(function (x) { x.classList.remove('on'); }); b.classList.add('on'); stF = b.dataset.s; af(); }; });
}
if (P.page === 'dsedit') {
  $('#dsTest').onclick = function () {
    var b = this, out = $('#dsTestResult'); b.disabled = true; out.innerHTML = '<div class="alert">Testing...</div>';
    fetch('/api/datasources/uid/' + P.uid + '/health').then(function (r) { return r.json().then(function (j) { return [r.status, j]; }); }).then(function (x) {
      b.disabled = false;
      out.innerHTML = '<div class="alert ' + (x[0] === 200 ? 'alert-success' : 'alert-error') + '">' + ic(x[0] === 200 ? '<path d="m5 12 5 5 9-10"/>' : I.x) + ' <div>' + esc(x[1].message) +
        (x[0] === 200 && P.uid === 'zbx-mysql' ? '<div class="muted small">Next, you can start to visualize data by building a dashboard, or by querying data in the <a href="/explore">Explore view</a>.</div>' : '') + '</div></div>';
    });
  };
}
if (P.page === 'profile') {
  var f = $('#prefsForm'), prefs = {};
  $$('.seg[data-pref] button', f).forEach(function (b) { b.onclick = function () { var s = b.parentNode; $$('button', s).forEach(function (x) { x.classList.remove('on'); }); b.classList.add('on'); prefs[s.dataset.pref] = b.dataset.v; }; });
  f.addEventListener('submit', function (e) {
    e.preventDefault();
    $$('select[name]', f).forEach(function (s) { if (s.name !== 'language') prefs[s.name] = s.value; });
    api('PUT', '/api/user/preferences', prefs).then(function () { toast('Preferences updated', 'ok'); setTimeout(function () { location.reload(); }, 400); });
  });
}
if (P.page === 'dashboard') Dashboard();
if (P.page === 'explore') Explore();
})();
