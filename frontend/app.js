const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  tg.setHeaderColor('#1c1c22');
  tg.setBackgroundColor('#1c1c22');
}

// Для проверки в обычном браузере: открыть /?dev=1 (работает только при DEV_MODE=1 на сервере)
const DEV_ID = new URLSearchParams(location.search).get('dev');
const view = document.getElementById('view');
let me = null;
const CONTACT = '@hehevgsh5'; // ЗАМЕНИ на свой Telegram-ник или почту

const PICK = { H: 'П1', D: 'Ничья', A: 'П2' };

// В Telegram встроенные alert и confirm работают не везде: используем окна самого Telegram
const nativeAlert = window.alert.bind(window);
window.alert = text => {
  if (tg && tg.isVersionAtLeast && tg.isVersionAtLeast('6.2') && tg.showAlert) tg.showAlert(String(text));
  else nativeAlert(text);
};

function askConfirm(text) {
  return new Promise(resolve => {
    if (tg && tg.isVersionAtLeast && tg.isVersionAtLeast('6.2') && tg.showConfirm) tg.showConfirm(text, ok => resolve(!!ok));
    else resolve(window.confirm(text));
  });
}
const SERIES_STATUS = {
  open: ['В игре', 'wait'],
  won: ['Выиграна', 'ok'],
  lost: ['Не вышла', 'bad'],
  void: ['Аннулирована', ''],
};

/* ---------- вспомогательное ---------- */

// безопасная сборка элементов: текст вставляется через textContent, а не как HTML
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([k, v]) => {
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) el.setAttribute(k, v);
  });
  kids.flat().forEach(c => el.append(c instanceof Node ? c : document.createTextNode(c ?? '')));
  return el;
}

function show(...nodes) { view.replaceChildren(...nodes.flat(Infinity)); }

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (tg && tg.initData) headers['X-Init-Data'] = tg.initData;
  if (DEV_ID) headers['X-Dev-User'] = DEV_ID;
  const r = await fetch('/api' + path, { ...opts, headers });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || 'Ошибка запроса');
  return data;
}

function setTab(t) {
  document.querySelectorAll('#nav button').forEach(b => b.classList.toggle('on', b.dataset.tab === t));
  document.getElementById('profileBtn').classList.toggle('on', t === 'profile');
}

// верхняя панель: очки слева, аватар (первая буква ника) справа
const AVATAR_ICON = document.getElementById('profileBtn').innerHTML;
function paintTop() {
  const btn = document.getElementById('profileBtn');
  const pts = document.getElementById('pts');
  if (me && me.registered) {
    btn.textContent = me.nickname.charAt(0).toUpperCase();
    pts.replaceChildren(h('small', {}, 'Очки'), String(me.points));
  } else {
    btn.innerHTML = AVATAR_ICON;
    pts.replaceChildren();
  }
}

// любой экран оборачиваем: при ошибке показываем её, а не белую страницу
function safe(fn) {
  return async (...args) => {
    try { await fn(...args); }
    catch (e) { show(h('p', { class: 'err' }, e.message)); }
  };
}

/* ---------- оформление матчей ---------- */

// короткие названия клубов (если клуба тут нет, лишнее (FC, CF, годы) убирается автоматически)
const SHORT = {
  'Brighton & Hove Albion FC': 'Brighton', 'Manchester United FC': 'Man United',
  'Manchester City FC': 'Man City', 'Tottenham Hotspur FC': 'Tottenham',
  'Newcastle United FC': 'Newcastle', 'Wolverhampton Wanderers FC': 'Wolves',
  'West Ham United FC': 'West Ham', 'Nottingham Forest FC': 'Nottingham',
  'Leeds United FC': 'Leeds', 'LeedsUnited FC': 'Leeds', 'AFC Bournemouth': 'Bournemouth',
  'Club Atlético de Madrid': 'Atlético', 'Real Betis Balompié': 'Betis',
  'Real Sociedad de Fútbol': 'Real Sociedad', 'Rayo Vallecano de Madrid': 'Rayo',
  'RCD Espanyol de Barcelona': 'Espanyol', 'RC Celta de Vigo': 'Celta',
  'Deportivo Alavés': 'Alavés', 'RCD Mallorca': 'Mallorca', 'CA Osasuna': 'Osasuna',
  'FC Internazionale Milano': 'Inter', 'AC Milan': 'Milan', 'SSC Napoli': 'Napoli',
  'ACF Fiorentina': 'Fiorentina', 'Bologna FC 1909': 'Bologna', 'Parma Calcio 1913': 'Parma',
  'US Sassuolo Calcio': 'Sassuolo', 'Hellas Verona FC': 'Verona',
  'FC Bayern München': 'Bayern', 'Bayer 04 Leverkusen': 'Leverkusen',
  'Borussia Mönchengladbach': "M'gladbach", 'Borussia Dortmund': 'Dortmund',
  'Eintracht Frankfurt': 'Frankfurt', '1. FSV Mainz 05': 'Mainz',
  'TSG 1899 Hoffenheim': 'Hoffenheim', '1. FC Union Berlin': 'Union Berlin',
  'SV Werder Bremen': 'Werder', '1. FC Köln': 'Köln', 'FC St. Pauli 1910': 'St. Pauli',
  '1. FC Heidenheim 1846': 'Heidenheim', 'Paris Saint-Germain FC': 'PSG',
  'Olympique de Marseille': 'Marseille', 'Olympique Lyonnais': 'Lyon',
  'AS Monaco FC': 'Monaco', 'Stade Rennais FC 1901': 'Rennes',
  'Sporting Clube de Portugal': 'Sporting', 'SL Benfica': 'Benfica',
  'Club Brugge KV': 'Brugge', 'AFC Ajax': 'Ajax', 'Galatasaray SK': 'Galatasaray',
};

function shortName(n) {
  if (SHORT[n]) return SHORT[n];
  const s = n
    .replace(/^\d+\.\s*/, '')
    .replace(/\b(FC|AFC|CF|BC|SC|SK|KV|FK|UD|AC|AS|SS|US|RC|SV|VfB|VfL|SSC|ACF)\b\.?/g, '')
    .replace(/\b(1[89]\d\d|20\d\d|0\d)\b/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  return s || n;
}

function dayLabel(d) {
  const t = new Date();
  const tomorrow = new Date(); tomorrow.setDate(t.getDate() + 1);
  const yesterday = new Date(); yesterday.setDate(t.getDate() - 1);
  if (d.toDateString() === t.toDateString()) return 'Сегодня';
  if (d.toDateString() === tomorrow.toDateString()) return 'Завтра';
  if (d.toDateString() === yesterday.toDateString()) return 'Вчера';
  const s = d.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function timeStr(d) {
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

/* ---------- первый вход: ник и 18+ ---------- */

function onboarding() {
  setTab('');
  const input = h('input', { type: 'text', placeholder: 'Ник (3–16 символов)', maxlength: 16 });
  const adult = h('input', { type: 'checkbox' });
  const err = h('div', { class: 'err' });
  const start = h('button', { class: 'btn', disabled: true, onclick: async () => {
    try {
      me = await api('/register', {
        method: 'POST',
        body: JSON.stringify({ nickname: input.value, adult: adult.checked }),
      });
      paintTop();
      home();
    } catch (e) { err.textContent = e.message; }
  } }, 'Начать');
  adult.addEventListener('change', () => { start.disabled = !adult.checked; });

  show(
    h('h1', {}, 'Добро пожаловать'),
    h('div', { class: 'card' },
      h('p', {}, 'Придумай ник. Его увидят другие игроки в рейтинге.'),
      input,
      h('label', { class: 'chk' }, adult, h('span', {}, 'Мне есть 18 лет.')),
      h('p', { class: 'dim' }, 'Здесь только прогнозы: без денег и призов, очки виртуальные.'),
      err,
      start
    )
  );
}

/* ---------- серия дня ---------- */

function serMark(sm) {
  const p = PICK[sm.pick] || '';
  if (!sm.result) return p;
  return sm.pick === sm.result ? `${p} ✓` : `${p} ✗`;
}

function seriesCard(ser) {
  const open = ser.series.find(s => s.status === 'open');
  const last = ser.series[0];
  const lines = s => s.matches.map(sm => h('div', { class: 'line' },
    h('span', {}, `${shortName(sm.home)} — ${shortName(sm.away)}`),
    h('span', { class: 'dim' }, serMark(sm))));

  if (open) {
    return h('div', { class: 'card series' },
      h('div', { class: 'head' }, h('b', {}, 'Серия дня'), h('span', { class: 'chip wait' }, 'В игре')),
      lines(open),
      h('div', { class: 'dim' }, `Угадаешь все: +${open.potential} очков`));
  }
  if (ser.can_create) {
    return h('div', { class: 'card series' },
      h('b', {}, 'Серия дня'),
      h('p', { class: 'dim' },
        `Выбери ${ser.min}–${ser.max} матчей ближайших двух суток. Угадаешь все: до +${ser.bonus[ser.max]} очков.`),
      last ? h('p', { class: 'dim' },
        `Прошлая серия: ${SERIES_STATUS[last.status][0]}${last.status === 'won' ? ` +${last.bonus}` : ''}`) : '',
      h('button', { class: 'btn', onclick: () => seriesBuilder(ser) }, 'Собрать серию'));
  }
  if (!last) return '';
  const [txt, cls] = SERIES_STATUS[last.status];
  return h('div', { class: 'card series' },
    h('div', { class: 'head' }, h('b', {}, 'Серия дня'),
      h('span', { class: 'chip ' + cls }, txt + (last.status === 'won' ? ` +${last.bonus}` : ''))),
    lines(last),
    h('div', { class: 'dim' }, 'Новая серия завтра'));
}

function seriesBuilder(ser) {
  setTab('home');
  const chosen = new Set();
  const info = h('div', { class: 'dim center gap' });
  const btn = h('button', { class: 'btn', disabled: true, onclick: async () => {
    if (!(await askConfirm('Собрать серию? Прогнозы на эти матчи после этого нельзя будет менять.'))) return;
    try {
      await api('/series', { method: 'POST', body: JSON.stringify({ match_ids: [...chosen] }) });
      home();
    } catch (e) { alert(e.message); }
  } }, 'Собрать серию');

  const boxes = [];
  const rows = ser.candidates.map(c => {
    const cb = h('input', { type: 'checkbox' });
    boxes.push([cb, c.id]);
    cb.addEventListener('change', () => {
      if (cb.checked) chosen.add(c.id); else chosen.delete(c.id);
      refresh();
    });
    const k = new Date(c.kickoff);
    return h('label', { class: 'cand' }, cb,
      h('div', {},
        h('div', { class: 'teams' }, `${shortName(c.home)} — ${shortName(c.away)}`),
        h('div', { class: 'dim' }, `${dayLabel(k)}, ${timeStr(k)} · твой прогноз: ${PICK[c.pick]}`)));
  });

  function refresh() {
    const n = chosen.size;
    info.textContent = `Выбрано ${n} из ${ser.max}`;
    btn.disabled = !(n >= ser.min && n <= ser.max);
    boxes.forEach(([cb]) => { if (!cb.checked) cb.disabled = n >= ser.max; });
  }
  refresh();

  const bonus = Object.entries(ser.bonus).map(([n, b]) => `${n} → +${b}`).join(' · ');
  show(
    h('button', { class: 'back', onclick: home }, '← Назад'),
    h('h1', {}, 'Серия дня'),
    h('p', { class: 'dim' }, `Угаданы все матчи серии: ${bonus}. Если не угадан хотя бы один, бонуса нет, обычные очки остаются.`),
    rows.length
      ? [info, rows, btn]
      : h('div', { class: 'card' }, h('span', { class: 'dim' },
          `Сначала сделай прогнозы на ${ser.min}–${ser.max} матчей ближайших двух суток: они появятся здесь.`))
  );
}

/* ---------- лиги ---------- */

const home = safe(async () => {
  setTab('home');
  const [list, ser, mine] = await Promise.all([api('/leagues'), api('/series'), api('/me')]);
  me = mine;
  paintTop();
  show(
    h('h1', {}, 'Лиги'),
    seriesCard(ser),
    list.map(l =>
      h('div', { class: 'card link', onclick: () => league(l.code, l.name) },
        h('div', { class: 'row' },
          h('span', { class: 'teams' }, l.name),
          h('span', { class: 'dim' }, l.open + ' матчей')))
    )
  );
});

const league = safe(async (code, name, matchday) => {
  setTab('home');
  const d = await api(`/leagues/${code}/matches` + (matchday ? `?matchday=${matchday}` : ''));
  const md = d.matchday || matchday || 1;

  const items = [];
  let lastDay = '';
  d.matches.forEach(m => {
    const label = dayLabel(new Date(m.kickoff));
    if (label !== lastDay) { items.push(h('div', { class: 'day' }, label)); lastDay = label; }
    items.push(matchCard(m, d.exact_bonus));
  });

  show(
    h('button', { class: 'back', onclick: home }, '← Лиги'),
    h('div', { class: 'toprow' },
      h('button', { class: 'arrow', onclick: () => md > 1 && league(code, name, md - 1) }, '‹'),
      h('div', { class: 'ttl' }, h('h1', {}, name), h('div', { class: 'dim' }, `Тур ${md}`)),
      h('button', { class: 'arrow', onclick: () => league(code, name, md + 1) }, '›')),
    h('p', { class: 'dim center' }, 'Нажми на выбранный исход ещё раз, чтобы отменить прогноз'),
    items.length ? items : h('p', { class: 'dim center' }, 'В этом туре нет матчей.')
  );
});

function matchCard(m, exact, onRemoved) {
  const kick = new Date(m.kickoff);
  const chip = h('span', { class: 'chip' });
  const scoreBox = h('div', { class: 'scorebox' });
  const frozen = () => m.locked || m.in_series;
  let scoreOpen = false;      // открыт ли блок ввода точного счёта
  let draft = [0, 0];         // счёт, который сейчас выбирается кнопками − и +

  const segs = ['H', 'D', 'A'].map(k => {
    const b = h('button', { class: 'segb', disabled: frozen() }, PICK[k]);
    b.dataset.k = k;
    b.addEventListener('click', async () => {
      try {
        if (m.pick === k) {                       // повторное нажатие: отмена прогноза
          await api(`/predictions/${m.id}`, { method: 'DELETE' });
          m.pick = null; m.my_home = null; m.my_away = null;
          if (onRemoved) { onRemoved(); return; }
        } else {
          const r = await api('/predictions', { method: 'POST', body: JSON.stringify({ match_id: m.id, pick: k }) });
          m.pick = r.pick; m.my_home = r.home; m.my_away = r.away;
        }
        scoreOpen = false;
        paint();
      } catch (e) { alert(e.message); }
    });
    return b;
  });

  function stepper(i) {
    const val = h('span', { class: 'sval' }, String(draft[i]));
    const minus = h('button', { class: 'step', onclick: () => { draft[i] = Math.max(0, draft[i] - 1); val.textContent = String(draft[i]); } }, '−');
    const plus = h('button', { class: 'step', onclick: () => { draft[i] = Math.min(9, draft[i] + 1); val.textContent = String(draft[i]); } }, '+');
    return h('div', { class: 'stepper' }, minus, val, plus);
  }

  function paintScore() {
    const hasMine = m.my_home != null && m.my_away != null;
    const hasReal = m.home_goals != null && m.away_goals != null;

    if (frozen()) {
      const parts = [];
      if (hasMine) parts.push(`Твой счёт ${m.my_home}:${m.my_away}`);
      if (m.result && hasReal) parts.push(`Итог ${m.home_goals}:${m.away_goals}`);
      if (m.result && hasMine && hasReal && m.my_home === m.home_goals && m.my_away === m.away_goals) {
        parts.push(`точный счёт +${exact}`);
      }
      scoreBox.replaceChildren(...(parts.length ? [h('div', { class: 'dim' }, parts.join(' · '))] : []));
      return;
    }

    if (scoreOpen) {                              // выбор счёта кнопками − и +
      const save = h('button', { class: 'mini', onclick: async () => {
        try {
          const r = await api('/predictions', { method: 'POST', body: JSON.stringify({ match_id: m.id, home: draft[0], away: draft[1] }) });
          m.pick = r.pick; m.my_home = r.home; m.my_away = r.away;
          scoreOpen = false;
          paint();
        } catch (e) { alert(e.message); }
      } }, 'Сохранить');
      const cancel = h('button', { class: 'mini ghost', onclick: () => { scoreOpen = false; paintScore(); } }, 'Отмена');
      scoreBox.replaceChildren(h('div', { class: 'scorerow' }, stepper(0), ':', stepper(1), save, cancel));
      return;
    }

    if (hasMine) {                                // счёт уже сохранён
      const edit = h('button', { class: 'mini', onclick: () => { draft = [m.my_home, m.my_away]; scoreOpen = true; paintScore(); } }, 'Изменить');
      const clear = h('button', { class: 'mini ghost', onclick: async () => {
        try {
          await api('/predictions', { method: 'POST', body: JSON.stringify({ match_id: m.id, pick: m.pick, clear_score: true }) });
          m.my_home = null; m.my_away = null;
          paint();
        } catch (e) { alert(e.message); }
      } }, '×');
      scoreBox.replaceChildren(h('div', { class: 'scorerow' },
        h('span', { class: 'dim' }, `Твой счёт ${m.my_home}:${m.my_away}`), edit, clear));
      return;
    }

    // по умолчанию счёт скрыт: достаточно выбрать П1, Ничья или П2
    scoreBox.replaceChildren(h('button', { class: 'linkbtn', onclick: () => { draft = [0, 0]; scoreOpen = true; paintScore(); } },
      `+ Точный счёт: ещё +${exact} очков (по желанию)`));
  }

  function paint() {
    segs.forEach(b => {
      const k = b.dataset.k;
      let cls = 'segb';
      if (m.pick === k) cls += m.result ? (k === m.result ? ' right' : ' wrong') : ' on';
      else if (m.result && k === m.result) cls += ' res';
      b.className = cls;
    });

    let text = '';
    let cls = '';
    if (m.status === 'CANCELLED') { text = 'Отменён'; cls = 'bad'; }
    else if (m.status === 'POSTPONED') { text = 'Перенесён'; cls = 'live'; }
    else if (m.result) {
      if (!m.pick) { text = 'Завершён'; }
      else if (m.pick === m.result) { text = 'Угадал'; cls = 'ok'; }
      else { text = 'Не угадал'; cls = 'bad'; }
    } else if (m.in_series) { text = 'В серии дня'; cls = 'wait'; }
    else if (m.locked) {
      if (m.pick) { text = 'Ждём итог'; cls = 'live'; }
      else { text = 'Приём закрыт'; }
    } else {
      if (m.pick) { text = 'Ждёт матча'; cls = 'wait'; }
      else { text = 'Сделай прогноз'; }
    }
    chip.className = 'chip ' + cls;
    chip.textContent = text;
    paintScore();
  }
  paint();

  return h('div', { class: 'card match' },
    h('div', { class: 'mtop' },
      h('div', { class: 'time' }, timeStr(kick)),
      h('div', { class: 'teams2' },
        h('div', {}, shortName(m.home)),
        h('div', {}, shortName(m.away)),
        m.league ? h('div', { class: 'lg' }, m.league) : ''),
      chip),
    h('div', { class: 'seg' }, segs),
    scoreBox);
}

/* ---------- рейтинг ---------- */

const rating = safe(async () => {
  setTab('rating');
  const rows = await api('/leaderboard');
  show(
    h('h1', {}, 'Рейтинг'),
    h('p', { class: 'dim' }, 'В рейтинге игроки с 20+ прогнозами.'),
    h('div', { class: 'card' },
      rows.length
        ? rows.map((r, i) => h('div', { class: 'rank' },
            h('span', {}, `${i + 1}. ${r.nickname}`),
            h('span', {}, `${r.points} · ${r.winrate}%`)))
        : h('span', { class: 'dim' }, 'Пока никто не набрал нужное число прогнозов.'))
  );
});

/* ---------- история ---------- */

function historyRow(it) {
  const k = new Date(it.kickoff);
  const mine = PICK[it.pick] + (it.my_home != null ? ` (${it.my_home}:${it.my_away})` : '');
  const real = it.result && it.home_goals != null ? ` · итог ${it.home_goals}:${it.away_goals}` : '';
  let chip;
  if (it.status === 'CANCELLED') chip = h('span', { class: 'chip bad' }, 'Отменён');
  else if (it.result) {
    const ok = it.pick === it.result;
    chip = h('span', { class: 'chip ' + (ok ? 'ok' : 'bad') }, ok ? `+${it.points || 0}` : '0');
  } else if (it.in_series) chip = h('span', { class: 'chip wait' }, 'В серии');
  else if (it.locked) chip = h('span', { class: 'chip live' }, 'Ждём итог');
  else chip = h('span', { class: 'chip wait' }, 'Ждёт матча');
  return h('div', { class: 'card hrow' },
    h('div', { class: 'hmain' },
      h('div', { class: 'teams' }, `${shortName(it.home)} — ${shortName(it.away)}`),
      h('div', { class: 'dim' }, `${it.league} · ${timeStr(k)} · ${mine}${real}`)),
    chip);
}

function feedNodes(items, state) {
  const out = [];
  items.forEach(it => {
    const label = dayLabel(new Date(it.kickoff));
    if (label !== state.last) { out.push(h('div', { class: 'day' }, label)); state.last = label; }
    out.push(historyRow(it));
  });
  return out;
}

const historyTab = safe(async () => {
  setTab('history');
  const first = await api('/me/predictions');
  let offset = first.done.length;
  const doneState = { last: '' };
  const doneBox = h('div', {});
  const moreBtn = h('button', { class: 'btn', onclick: async () => {
    try {
      const r = await api(`/me/predictions?offset=${offset}`);
      offset += r.done.length;
      doneBox.append(...feedNodes(r.done, doneState));
      moreBtn.style.display = r.has_more ? '' : 'none';
    } catch (e) { alert(e.message); }
  } }, 'Показать ещё');
  doneBox.append(...feedNodes(first.done, doneState));
  moreBtn.style.display = first.has_more ? '' : 'none';

  // ждущие матча: полноценные карточки, прогноз и счёт можно менять прямо здесь
  const pendingNodes = [];
  let lastDay = '';
  first.pending.forEach(it => {
    const label = dayLabel(new Date(it.kickoff));
    if (label !== lastDay) { pendingNodes.push(h('div', { class: 'day' }, label)); lastDay = label; }
    const card = matchCard({ ...it, id: it.match_id }, first.exact_bonus, () => card.remove());
    pendingNodes.push(card);
  });

  show(
    h('h1', {}, 'История'),
    (!first.pending.length && !first.done.length)
      ? h('div', { class: 'card' }, h('span', { class: 'dim' }, 'Здесь появятся твои прогнозы. Выбери матч на экране «Лиги».'))
      : '',
    first.pending.length
      ? [h('div', { class: 'day' }, 'Ждут матча'),
         h('p', { class: 'dim' }, 'Пока матч не начался, прогноз и счёт можно поменять прямо здесь.'),
         pendingNodes]
      : '',
    first.done.length ? [h('div', { class: 'day' }, 'Сыграно'), doneBox, moreBtn] : ''
  );
});

/* ---------- профиль ---------- */

const profile = safe(async () => {
  setTab('profile');
  me = await api('/me');
  paintTop();
  show(
    h('h1', {}, me.nickname),
    h('div', { class: 'card' },
      h('div', { class: 'dim' }, 'Очки'),
      h('div', { class: 'stat' }, String(me.points)),
      h('div', { class: 'dim' },
        `Винрейт ${me.winrate}% · угадано ${me.correct} из ${me.total} · стрик ${me.streak} (лучший ${me.best_streak})`)),
    h('p', { class: 'dim' }, 'Только прогнозы. Без денег и призов, очки виртуальные и не выводятся. 18+'),
    h('p', { class: 'dim' }, 'Football data provided by the Football-Data.org API'),
    h('button', { class: 'btn gap', onclick: about }, 'О проекте и правила (18+)'),
    h('button', { class: 'btn danger', onclick: confirmDelete }, 'Удалить мои данные')
  );
});

/* ---------- удаление аккаунта ---------- */

function confirmDelete() {
  setTab('profile');
  show(
    h('h1', {}, 'Точно удалить аккаунт?'),
    h('div', { class: 'card' },
      h('p', {}, 'Мы навсегда сотрём твой ник, прогнозы, очки и серии. Восстановить их не получится: придётся начинать с нуля.'),
      h('button', { class: 'btn danger gap', onclick: doDelete }, 'Да, удалить навсегда'),
      h('button', { class: 'btn', onclick: profile }, 'Нет, оставить аккаунт'))
  );
}

async function doDelete() {
  try {
    await api('/me', { method: 'DELETE' });
    me = { registered: false };
    paintTop();
    onboarding();
  } catch (e) { alert(e.message); }
}

/* ---------- о проекте ---------- */

function about() {
  setTab('profile');
  const back = (me && me.registered) ? profile : onboarding;
  const block = (title, ...lines) =>
    h('div', { class: 'card' }, h('b', {}, title), lines.map(t => h('p', { class: 'dim law' }, t)));
  show(
    h('button', { class: 'back', onclick: back }, '← Назад'),
    h('h1', {}, 'О проекте'),
    block('Как начисляются очки',
      'Верный исход: 10 очков. Верная ничья: ещё +3.',
      'Точный счёт (по желанию, за 90 минут): ещё +15.',
      'Редкий исход: чем меньше игроков выбрали тот же вариант, тем больше бонус (до +10). Он считается, когда на матч поставили 10 и более игроков.',
      'Стрик (верные прогнозы подряд): 3 — +5, 5 — +10, 10 — +25. За ошибку очки не отнимаются.',
      'Серия дня: выбери 3–5 матчей ближайших двух суток. Угаданы все: 3 матча +20, 4 матча +35, 5 матчей +60. После сбора прогнозы на эти матчи менять нельзя. Если угадан не каждый, бонуса нет, но обычные очки остаются.'),
    block('Только для совершеннолетних (18+)',
      'Сервис предназначен только для лиц, достигших 18 лет. Если вам нет 18, пожалуйста, не пользуйтесь приложением.'),
    block('Это не азартная игра и не ставки',
      'FootballVerdict — бесплатная игра в прогнозы. Здесь нельзя делать ставки, вносить деньги, получать выигрыши или призы. Мы не являемся букмекером и не организуем азартные игры.',
      'Очки виртуальные: у них нет денежной стоимости, их нельзя вывести, обменять, продать или передать.'),
    block('Мы не пропагандируем ставки',
      'Проект не призывает делать ставки на спорт, не рекламирует букмекерские конторы и не содержит ссылок на них. Прогнозы в приложении — развлечение и не являются рекомендацией делать ставки.',
      'Если азартные игры вызывают проблемы у вас или ваших близких, обратитесь к специалисту.'),
    block('Источник данных',
      'Данные о матчах и результатах предоставлены Football-Data.org (football-data.org). Они могут приходить с задержкой или содержать неточности и носят информационный характер.',
      'Названия клубов и турниров принадлежат их правообладателям. Проект с ними не связан и ими не одобрен.'),
    block('Ваши данные',
      'Мы храним только ваш ID в Telegram, придуманный ник, прогнозы, очки и статистику. Имя, телефон, почту и фото мы не собираем.',
      'Ваш ник, очки и процент угаданных прогнозов видны другим игрокам в рейтинге. Telegram-username не показывается.',
      'Удалить данные можно в любой момент: Профиль → «Удалить мои данные».',
      'Если не заходить в приложение больше года, аккаунт удаляется автоматически.'),
    block('Связь', 'Вопросы и обращения: ' + CONTACT)
  );
}

/* ---------- запуск ---------- */

function go(tab) {
  if (!me || !me.registered) return onboarding();
  ({ home, rating, history: historyTab, profile })[tab]();
}

document.querySelectorAll('#nav button, #profileBtn').forEach(b =>
  b.addEventListener('click', () => go(b.dataset.tab)));

(async () => {
  try {
    const cfg = await api('/config');
    document.title = cfg.app_name;
    me = await api('/me');
    paintTop();
    me.registered ? home() : onboarding();
  } catch (e) {
    show(h('p', { class: 'err' }, e.message));
  }
})();