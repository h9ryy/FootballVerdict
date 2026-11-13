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

/* ---------- избранное ---------- */

const favs = safe(async () => {
  setTab('favs');
  const d = await api('/favorites/matches');

  const chips = d.teams.map(name => h('span', { class: 'tchip' },
    shortName(name),
    h('button', { 'aria-label': 'Убрать ' + shortName(name), onclick: async () => {
      try {
        await api('/favorites?team=' + encodeURIComponent(name), { method: 'DELETE' });
        favs();
      } catch (e) { alert(e.message); }
    } }, '×')));

  const items = [];
  let lastDay = '';
  d.matches.forEach(m => {
    const label = dayLabel(new Date(m.kickoff));
    if (label !== lastDay) { items.push(h('div', { class: 'day' }, label)); lastDay = label; }
    items.push(matchCard(m, d.exact_bonus));
  });

  show(
    h('h1', {}, 'Избранное'),
    h('button', { class: 'btn gap', onclick: teamPicker },
      d.teams.length ? 'Добавить команды' : 'Выбрать команды'),
    d.teams.length
      ? [h('div', { class: 'chips' }, chips),
         h('p', { class: 'dim' }, 'Показываем ближайший матч каждой команды.'),
         items.length ? items : h('p', { class: 'dim center' }, 'У твоих команд пока нет ближайших матчей.')]
      : h('p', { class: 'dim center' }, 'Добавь команды, и здесь появятся их ближайшие матчи.')
  );
});

// поиск: без регистра, без «ё» и значков над буквами (Atlético = atletico)
const norm = s => String(s).toLowerCase().replace(/ё/g, 'е').normalize('NFD').replace(/[\u0300-\u036f]/g, '');

// названия лиг, как их отдаёт сервер, и то, что человек может ввести
const LEAGUE_ALIASES = {
  'Премьер-лига': ['премьер-лига', 'премьер лига', 'апл', 'англия', 'английская', 'premier league', 'epl', 'pl', 'england'],
  'Ла Лига': ['ла лига', 'ла-лига', 'испания', 'испанская', 'la liga', 'laliga', 'spain'],
  'Серия А': ['серия а', 'серия a', 'италия', 'итальянская', 'serie a', 'italy'],
  'Бундеслига': ['бундеслига', 'германия', 'немецкая', 'bundesliga', 'germany'],
  'Лига 1': ['лига 1', 'франция', 'французская', 'ligue 1', 'ligue1', 'france'],
  'Лига чемпионов': ['лига чемпионов', 'лч', 'champions league', 'ucl', 'cl'],
};

// русские названия клубов: ключ = короткое имя, как оно показывается в списке
const TEAM_RU = {
  'Arsenal': 'Арсенал', 'Aston Villa': 'Астон Вилла', 'Bournemouth': 'Борнмут', 'Brentford': 'Брентфорд',
  'Brighton': 'Брайтон', 'Burnley': 'Бернли', 'Chelsea': 'Челси', 'Crystal Palace': 'Кристал Пэлас',
  'Everton': 'Эвертон', 'Fulham': 'Фулхэм', 'Leeds': 'Лидс', 'Liverpool': 'Ливерпуль',
  'Man City': 'Манчестер Сити', 'Man United': 'Манчестер Юнайтед', 'Newcastle': 'Ньюкасл',
  'Nottingham': 'Ноттингем Форест', 'Sunderland': 'Сандерленд', 'Tottenham': 'Тоттенхэм', 'West Ham': 'Вест Хэм',
  'Wolves': 'Вулверхэмптон Вулвз',
  'Real Madrid': 'Реал Мадрид', 'Barcelona': 'Барселона', 'Atlético': 'Атлетико Мадрид', 'Sevilla': 'Севилья',
  'Valencia': 'Валенсия', 'Villarreal': 'Вильярреал', 'Betis': 'Бетис', 'Real Sociedad': 'Реал Сосьедад',
  'Athletic Club': 'Атлетик Бильбао', 'Getafe': 'Хетафе', 'Girona': 'Жирона', 'Osasuna': 'Осасуна',
  'Celta': 'Сельта', 'Mallorca': 'Мальорка', 'Rayo': 'Райо Вальекано', 'Espanyol': 'Эспаньол',
  'Alavés': 'Алавес', 'Elche': 'Эльче', 'Levante': 'Леванте', 'Real Oviedo': 'Овьедо',
  'Juventus': 'Ювентус', 'Inter': 'Интер', 'Milan': 'Милан', 'Napoli': 'Наполи', 'Roma': 'Рома',
  'Lazio': 'Лацио', 'Atalanta': 'Аталанта', 'Fiorentina': 'Фиорентина', 'Bologna': 'Болонья',
  'Torino': 'Торино', 'Genoa': 'Дженоа', 'Udinese': 'Удинезе', 'Sassuolo': 'Сассуоло', 'Parma': 'Парма',
  'Cagliari': 'Кальяри', 'Lecce': 'Лечче', 'Verona': 'Верона', 'Como': 'Комо', 'Cremonese': 'Кремонезе', 'Pisa': 'Пиза',
  'Bayern': 'Бавария', 'Dortmund': 'Боруссия Дортмунд', 'Leverkusen': 'Байер Леверкузен',
  'RB Leipzig': 'РБ Лейпциг', 'Stuttgart': 'Штутгарт', 'Frankfurt': 'Айнтрахт Франкфурт',
  'Wolfsburg': 'Вольфсбург', 'Freiburg': 'Фрайбург', 'Mainz': 'Майнц', 'Hoffenheim': 'Хоффенхайм',
  'Union Berlin': 'Унион Берлин', 'Werder': 'Вердер Бремен', 'Augsburg': 'Аугсбург', 'Köln': 'Кёльн',
  'St. Pauli': 'Санкт-Паули', "M'gladbach": 'Боруссия Мёнхенгладбах', 'Heidenheim': 'Хайденхайм', 'Hamburg': 'Гамбург',
  'PSG': 'ПСЖ Пари Сен-Жермен', 'Marseille': 'Марсель', 'Lyon': 'Лион', 'Monaco': 'Монако', 'Lille': 'Лилль',
  'Nice': 'Ницца', 'Lens': 'Ланс', 'Rennes': 'Ренн', 'Strasbourg': 'Страсбур', 'Nantes': 'Нант',
  'Toulouse': 'Тулуза', 'Brest': 'Брест', 'Auxerre': 'Осер', 'Angers': 'Анже', 'Lorient': 'Лорьян',
  'Metz': 'Метц', 'Paris': 'Пари', 'Le Havre': 'Гавр',
  'Benfica': 'Бенфика', 'Sporting': 'Спортинг', 'Ajax': 'Аякс', 'Galatasaray': 'Галатасарай',
  'Brugge': 'Брюгге', 'PSV': 'ПСВ Эйндховен', 'Celtic': 'Селтик', 'Porto': 'Порту',
};

function teamMatches(t, q) {
  const hay = [t.name, shortName(t.name), TEAM_RU[shortName(t.name)] || ''].map(norm);
  if (hay.some(x => x.includes(q))) return true;
  const la = (LEAGUE_ALIASES[t.league] || [t.league]).map(norm);
  return q.length >= 2 && la.some(a => a.includes(q));   // поиск по лиге: показать все её команды
}

const teamPicker = safe(async () => {
  setTab('favs');
  const all = await api('/teams');
  const search = h('input', { type: 'text', placeholder: 'Поиск команды' });
  const box = h('div', {});

  function teamRow(t) {
    const star = h('button', { class: 'star' + (t.fav ? ' on' : '') }, t.fav ? '★' : '☆');
    star.addEventListener('click', async () => {
      try {
        if (t.fav) await api('/favorites?team=' + encodeURIComponent(t.name), { method: 'DELETE' });
        else await api('/favorites', { method: 'POST', body: JSON.stringify({ team: t.name }) });
        t.fav = !t.fav;
        star.className = 'star' + (t.fav ? ' on' : '');
        star.textContent = t.fav ? '★' : '☆';
      } catch (e) { alert(e.message); }
    });
    return h('div', { class: 'card trow' }, h('span', { class: 'teams' }, shortName(t.name)), star);
  }

  function paintList() {
    const q = norm(search.value.trim());
    const groups = new Map();
    all.filter(t => !q || teamMatches(t, q))
       .forEach(t => {
         if (!groups.has(t.league)) groups.set(t.league, []);
         groups.get(t.league).push(t);
       });
    const nodes = [];
    groups.forEach((teams, league) => {
      nodes.push(h('div', { class: 'day' }, league));
      teams.sort((a, b) => shortName(a.name).localeCompare(shortName(b.name)))
           .forEach(t => nodes.push(teamRow(t)));
    });
    box.replaceChildren(...(nodes.length ? nodes : [h('p', { class: 'dim center' }, 'Ничего не найдено')]));
  }
  search.addEventListener('input', paintList);
  paintList();

  show(
    h('button', { class: 'back', onclick: favs }, '← Избранное'),
    h('h1', {}, 'Выбор команд'),
    search,
    box
  );
});

// горизонтальная строка: тянется мышью, листается колесом (на телефоне работает обычный свайп)
function dragScroll(el) {
  let down = false, moved = false, startX = 0, startLeft = 0;
  el.addEventListener('pointerdown', e => {
    if (e.pointerType === 'touch') return;      // пальцем браузер листает сам
    down = true; moved = false; startX = e.clientX; startLeft = el.scrollLeft;
  });
  window.addEventListener('pointermove', e => {
    if (!down) return;
    const dx = e.clientX - startX;
    if (Math.abs(dx) > 5) { moved = true; el.classList.add('drag'); }
    if (moved) el.scrollLeft = startLeft - dx;
  });
  window.addEventListener('pointerup', () => { down = false; el.classList.remove('drag'); });
  el.addEventListener('click', e => { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);
  el.addEventListener('wheel', e => {
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { el.scrollLeft += e.deltaY; e.preventDefault(); }
  }, { passive: false });
}

const ratingState = { period: 'all', league: '' };
const PERIODS = [['week', 'Неделя'], ['month', 'Месяц'], ['all', 'Всё время']];

const rating = safe(async () => {
  setTab('rating');
  const qs = `?period=${ratingState.period}` + (ratingState.league ? `&league=${ratingState.league}` : '');
  const d = await api('/leaderboard' + qs);
  const mine = d.me;
  const inTop = d.rows.some(r => r.me);

  const seg = h('div', { class: 'seg' }, PERIODS.map(([k, name]) =>
    h('button', { class: 'segb' + (ratingState.period === k ? ' on' : ''), onclick: () => {
      ratingState.period = k; rating();
    } }, name)));

  const lgs = h('div', { class: 'lgs' }, [['', 'Все лиги'], ...d.leagues.map(l => [l.code, l.name])].map(([code, name]) =>
    h('button', { class: 'lchip' + (ratingState.league === code ? ' on' : ''), onclick: () => {
      ratingState.league = code; rating();
    } }, name)));
  dragScroll(lgs);

  let mineCard;
  if (mine.place) {
    mineCard = h('div', { class: 'card' },
      h('div', { class: 'dim' }, 'Твоё место'),
      h('div', { class: 'stat' }, `#${mine.place}`),
      h('div', { class: 'dim' }, `${mine.points} очков · ${mine.winrate}%`));
  } else {
    const left = Math.max(d.min_games - mine.total, 0);
    mineCard = h('div', { class: 'card' },
      h('div', { class: 'dim' }, `Чтобы попасть сюда, нужно ${d.min_games}+ прогнозов с итогом. Тебе осталось: ${left}.`));
  }

  const list = d.rows.map(r => h('div', { class: 'rank' },
    h('span', { style: r.me ? 'font-weight:800;color:var(--neon)' : null }, `${r.place}. ${r.nickname}`),
    h('span', {}, `${r.points} · ${r.winrate}%`)));
  if (mine.place && !inTop) {
    list.push(h('div', { class: 'rank' },
      h('span', { style: 'font-weight:800;color:var(--neon)' }, `${mine.place}. ты`),
      h('span', {}, `${mine.points} · ${mine.winrate}%`)));
  }

  const filtered = d.period !== 'all' || d.league;
  show(
    h('h1', {}, 'Рейтинг'),
    seg,
    lgs,
    h('p', { class: 'dim' }, `В рейтинге игроки с ${d.min_games}+ прогнозами. При равных очках выше тот, у кого больше процент угаданных.`
      + (filtered ? ' Здесь считаются очки за прогнозы; бонус серии дня учитывается только в общем рейтинге за всё время.' : '')),
    mineCard,
    list.length ? h('div', { class: 'card' }, list) : ''
  );

  const active = lgs.querySelector('.on');
  if (active) lgs.scrollLeft = active.offsetLeft - 12;   // выбранная лига остаётся на виду
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

  // ждущие матча: карточки сгруппированы по дням, пустые группы убираются
  const pendingBox = h('div', {});
  const pendingHead = h('div', {},
    h('div', { class: 'day' }, 'Ждут матча'),
    h('p', { class: 'dim' }, 'Пока матч не начался, прогноз и счёт можно поменять прямо здесь.'),
    pendingBox);
  let curLabel = '';
  let curBox = null;
  first.pending.forEach(it => {
    const label = dayLabel(new Date(it.kickoff));
    if (label !== curLabel) {
      curLabel = label;
      curBox = h('div', {}, h('div', { class: 'day' }, label));
      pendingBox.append(curBox);
    }
    const box = curBox;
    const card = matchCard({ ...it, id: it.match_id }, first.exact_bonus, () => {
      card.remove();
      if (!box.querySelector('.card')) box.remove();                  // день без карточек
      if (!pendingBox.children.length) pendingHead.remove();          // весь блок «Ждут матча»
    });
    box.append(card);
  });

  show(
    h('h1', {}, 'История'),
    (!first.pending.length && !first.done.length)
      ? h('div', { class: 'card' }, h('span', { class: 'dim' }, 'Здесь появятся твои прогнозы. Выбери матч на экране «Лиги».'))
      : '',
    first.pending.length ? pendingHead : '',
    first.done.length ? [h('div', { class: 'day' }, 'Сыграно'), doneBox, moreBtn] : ''
  );
});

/* ---------- звания и значки (рисуем сами, из простых фигур) ---------- */

const BADGES = {
  debut: '<svg viewBox="0 0 48 48"><defs><linearGradient id="gdb" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4a4a58"/><stop offset="1" stop-color="#2c2c36"/></linearGradient></defs><circle cx="24" cy="24" r="19" fill="none" stroke="#6b6b7b" stroke-width="1.5" stroke-dasharray="3 3"/><circle cx="24" cy="24" r="15" fill="url(#gdb)" stroke="#b4b4c2" stroke-width="2"/><path d="M17 27l7-7 7 7" fill="none" stroke="#ececf2" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M17 33h14" stroke="#9a9aa8" stroke-width="2.5" stroke-linecap="round"/></svg>',
  znatok: '<svg viewBox="0 0 48 48"><defs><linearGradient id="gzn" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2b5a96"/><stop offset="1" stop-color="#16294a"/></linearGradient></defs><path d="M24 5l15 5.5v11.5c0 9.5-6.5 16-15 21C15.500 38 9 31.500 9 22V10.500z" fill="url(#gzn)" stroke="#60a5fa" stroke-width="2" stroke-linejoin="round"/><path d="M24 9.500l11 4v8.500c0 7-4.500 12-11 16-6.500-4-11-9-11-16v-8.500z" fill="none" stroke="#93c5fd" stroke-opacity=".5" stroke-width="1"/><polygon points="24,14 26.2,19 31.500,19.400 27.400,22.900 28.800,28 24,25.200 19.200,28 20.600,22.900 16.500,19.400 21.800,19" fill="#bfdbfe"/><path d="M19 32l5 3 5-3" fill="none" stroke="#60a5fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',analitik: '<svg viewBox="0 0 48 48"><path d="M24 5l16 19-16 19L8 24z" fill="#3b1d63" stroke="#a855f7" stroke-width="2" stroke-linejoin="round"/><path d="M24 14l8 10-8 10-8-10z" fill="#a855f7" fill-opacity=".55"/><path d="M8 24h32" stroke="#a855f7" stroke-width="1.5"/></svg>',
  strateg: '<svg viewBox="0 0 48 48"><polygon points="24,4 41,14 41,34 24,44 7,34 7,14" fill="#4a3a10" stroke="#fbbf24" stroke-width="2" stroke-linejoin="round"/><path d="M15 31l-1-11 6 5 4-9 4 9 6-5-1 11z" fill="#fbbf24"/></svg>',
  oracle: '<svg viewBox="0 0 48 48"><path d="M24 2v5M24 41v5M2 24h5M41 24h5M8.5 8.5l3.5 3.5M39.5 8.5L36 12M8.5 39.5L12 36M39.5 39.5L36 36" stroke="#e0115f" stroke-width="2" stroke-linecap="round"/><polygon points="24,9 34,21 24,39 14,21" fill="#7a0a35" stroke="#e0115f" stroke-width="2" stroke-linejoin="round"/><circle cx="24" cy="22" r="4" fill="#ffd1e0"/></svg>',
};

function badge(key, size = 40) {
  const s = h('span', { class: 'badge' });
  s.style.width = s.style.height = size + 'px';
  s.innerHTML = BADGES[key] || '';   // строки выше написаны нами, пользовательских данных тут нет
  return s;
}

function rankCard(r) {
  const bar = h('div', { class: 'bar' }, h('div', {}));
  bar.firstChild.style.width = r.progress + '%';
  return h('div', { class: 'card rank-card link', onclick: ranksTab },
    badge(r.key, 60),
    h('div', { class: 'rinfo' },
      h('div', { class: 'rname' }, r.name),
      r.next
        ? [bar, h('div', { class: 'dim' }, `До «${r.next}»: ещё ${r.to_next} очков`)]
        : h('div', { class: 'dim' }, 'Высшее звание')));
}

const ranksTab = safe(async () => {
  setTab('ranks');
  const d = await api('/ranks');
  const pts = d.points;
  let cur = 0;
  d.ranks.forEach((r, i) => { if (pts >= r.need) cur = i; });

  const track = h('div', { class: 'rtrack' });
  const dots = d.ranks.map((_, i) => h('button', { class: 'dot', 'aria-label': 'Звание ' + (i + 1), onclick: () => goTo(i) }));

  d.ranks.forEach((r, i) => {
    const reached = pts >= r.need;
    let chipText, chipCls;
    if (reached && i === cur) { chipText = 'Твоё звание'; chipCls = 'ok'; }
    else if (reached) { chipText = 'Получено'; chipCls = ''; }
    else if (i === cur + 1) { chipText = 'Следующее звание'; chipCls = 'wait'; }
    else { chipText = 'Пока закрыто'; chipCls = ''; }

    const body = [
      badge(r.key, 120),
      h('div', { class: 'rname' }, r.name),
      h('div', { class: 'dim' }, r.need === 0 ? 'С первых очков' : `От ${r.need} очков`),
      h('span', { class: 'chip ' + chipCls }, chipText),
    ];
    if (!reached) {
      body.push(h('div', { class: 'dim' }, `Ещё ${r.need - pts} очков`));
      if (i === cur + 1) {                       // полоса прогресса только до ближайшего звания
        const from = d.ranks[cur].need;
        const bar = h('div', { class: 'bar' }, h('div', {}));
        bar.firstChild.style.width = Math.max(0, Math.min(100, Math.round((pts - from) / (r.need - from) * 100))) + '%';
        body.splice(4, 0, bar);
      }
    } else if (i === d.ranks.length - 1) {
      body.push(h('div', { class: 'dim' }, 'Высшее звание'));
    }
    track.append(h('div', { class: 'rslide' + (reached ? '' : ' locked') }, h('div', { class: 'card' }, body)));
  });

  const index = () => Math.round(track.scrollLeft / track.clientWidth);
  function paintDots() { const k = index(); dots.forEach((dot, i) => dot.classList.toggle('on', i === k)); }
  function goTo(i) {
    const k = Math.max(0, Math.min(d.ranks.length - 1, i));
    track.scrollTo({ left: k * track.clientWidth, behavior: 'smooth' });
  }
  track.addEventListener('scroll', paintDots);

  show(
    h('h1', {}, 'Звания'),
    h('p', { class: 'dim' }, `Твои очки: ${pts}. Листай, чтобы увидеть все звания. Звание не падает: очки не отнимаются.`),
    track,
    h('div', { class: 'rnav' },
      h('button', { class: 'arrow', onclick: () => goTo(index() - 1) }, '‹'),
      h('div', { class: 'dots' }, dots),
      h('button', { class: 'arrow', onclick: () => goTo(index() + 1) }, '›'))
  );
  track.scrollLeft = cur * track.clientWidth;   // сразу открываем текущее звание
  paintDots();
});

/* ---------- профиль ---------- */

const profile = safe(async () => {
  setTab('profile');
  me = await api('/me');
  paintTop();

  const notify = h('input', { type: 'checkbox' });
  notify.checked = !!me.notify;
  notify.addEventListener('change', async () => {
    try {
      const r = await api('/me/notify', { method: 'POST', body: JSON.stringify({ enabled: notify.checked }) });
      me.notify = r.notify;
    } catch (e) { notify.checked = !notify.checked; alert(e.message); }
  });

  show(
    h('h1', {}, me.nickname),
    rankCard(me.rank),
    h('div', { class: 'card' },
      h('div', { class: 'dim' }, 'Очки'),
      h('div', { class: 'stat' }, String(me.points)),
      h('div', { class: 'dim' },
        `Винрейт ${me.winrate}% · угадано ${me.correct} из ${me.total} · стрик ${me.streak} (лучший ${me.best_streak})`)),
    h('div', { class: 'card' },
      h('label', { class: 'chk', style: 'margin:0 0 6px' }, notify, h('span', {}, 'Напоминать о матчах избранных команд')),
      h('p', { class: 'dim', style: 'margin:0' },
        'Не чаще раза в день в чате с ботом, только если сегодня играет твоя избранная команда и на матч нет прогноза. Выключено по умолчанию. Нужно, чтобы ты запускал бота (/start).')),
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
      'Серия дня: выбери 3–5 матчей ближайших двух суток. Угаданы все: 3 матча +20, 4 матча +35, 5 матчей +60. После сбора прогнозы на эти матчи менять нельзя. Если угадан не каждый, бонуса нет, но обычные очки остаются.',
      'Рейтинг можно смотреть за неделю, месяц и всё время, а также по каждой лиге. В рейтингах за период считаются очки за прогнозы, бонус серии дня входит только в общий рейтинг.'),
    block('Звания',
      'Звание зависит от всех набранных очков и не падает: Дебютант (0), Знаток (300), Аналитик (1000), Стратег (2000), Оракул (4000).'),
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
      'Мы храним только ваш ID в Telegram, придуманный ник, прогнозы, очки, статистику, список избранных команд и ваш выбор насчёт напоминаний. Имя, телефон, почту и фото мы не собираем.',
      'Ваш ник, очки и процент угаданных прогнозов видны другим игрокам в рейтинге. Telegram-username не показывается.',
      'Удалить данные можно в любой момент: Профиль → «Удалить мои данные».',
      'Если не заходить в приложение больше года, аккаунт удаляется автоматически.',
      'Напоминания в боте приходят только тем, кто сам их включил (Профиль или команда /notify), не чаще раза в день, и отключаются в любой момент.'),
    block('Связь', 'Вопросы и обращения: ' + CONTACT)
  );
}


/* ---------- запуск ---------- */

function go(tab) {
  if (!me || !me.registered) return onboarding();
    ({ home, rating, history: historyTab, profile, favs, ranks: ranksTab })[tab]();
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