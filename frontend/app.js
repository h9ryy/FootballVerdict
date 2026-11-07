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
const CONTACT = '@твой_контакт'; // ЗАМЕНИ на свой Telegram-ник или почту

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

function show(...nodes) { view.replaceChildren(...nodes.flat()); }

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
  const chk = h('input', { type: 'checkbox' });
  const err = h('div', { class: 'err' });
  show(
    h('h1', {}, 'Добро пожаловать'),
    h('div', { class: 'card' },
      h('p', {}, 'Придумай ник. Больше мы ничего не просим: имя и данные из Telegram не сохраняются.'),
      input,
      h('label', { class: 'chk' }, chk,
        'Мне есть 18 лет. Я понимаю, что здесь только прогнозы: без денег и призов, очки виртуальные.'),
      err,
      h('button', { class: 'back', onclick: about }, 'Условия и правила'),
      h('button', { class: 'btn', onclick: async () => {
        try {
          me = await api('/me/nickname', {
            method: 'PUT',
            body: JSON.stringify({ nickname: input.value, adult: chk.checked }),
          });
          home();
        } catch (e) { err.textContent = e.message; }
      } }, 'Начать')
    )
  );
}

/* ---------- лиги ---------- */

const home = safe(async () => {
  setTab('home');
  const list = await api('/leagues');
  show(
    h('h1', {}, 'Лиги'),
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
    items.push(matchCard(m));
  });

  show(
    h('button', { class: 'back', onclick: home }, '← Лиги'),
    h('div', { class: 'toprow' },
      h('button', { class: 'arrow', onclick: () => md > 1 && league(code, name, md - 1) }, '‹'),
      h('div', { class: 'ttl' }, h('h1', {}, name), h('div', { class: 'dim' }, `Тур ${md}`)),
      h('button', { class: 'arrow', onclick: () => league(code, name, md + 1) }, '›')),
    items.length ? items : h('p', { class: 'dim center' }, 'В этом туре нет матчей.')
  );
});

function matchCard(m) {
  const kick = new Date(m.kickoff);
  const labels = { H: 'П1', D: 'Ничья', A: 'П2' };
  const chip = h('span', { class: 'chip' });

  const segs = ['H', 'D', 'A'].map(k => {
    const b = h('button', { class: 'segb', disabled: m.locked }, labels[k]);
    b.dataset.k = k;
    b.addEventListener('click', async () => {
      try {
        await api('/predictions', { method: 'POST', body: JSON.stringify({ match_id: m.id, pick: k }) });
        m.pick = k;
        paint();
      } catch (e) { alert(e.message); }
    });
    return b;
  });

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
    } else if (m.locked) {
      if (m.pick) { text = 'Ждём итог'; cls = 'live'; }
      else { text = 'Приём закрыт'; }
    } else {
      if (m.pick) { text = 'Ждёт матча'; cls = 'wait'; }
      else { text = 'Сделай прогноз'; }
    }
    chip.className = 'chip ' + cls;
    chip.textContent = text;
  }
  paint();

  return h('div', { class: 'card match' },
    h('div', { class: 'mtop' },
      h('div', { class: 'time' }, timeStr(kick)),
      h('div', { class: 'teams2' },
        h('div', {}, shortName(m.home)),
        h('div', {}, shortName(m.away))),
      chip),
    h('div', { class: 'seg' }, segs));
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

/* ---------- профиль ---------- */

const profile = safe(async () => {
  setTab('profile');
  me = await api('/me');
  const hist = await api('/me/predictions');
  const labels = { H: 'П1', D: 'Ничья', A: 'П2' };
  show(
    h('h1', {}, me.nickname),
    h('div', { class: 'card' },
      h('div', { class: 'dim' }, 'Очки'),
      h('div', { class: 'stat' }, String(me.points)),
      h('div', { class: 'dim' },
        `Винрейт ${me.winrate}% · угадано ${me.correct} из ${me.total} · серия ${me.streak} (лучшая ${me.best_streak})`)),
    h('div', { class: 'card' },
      h('b', {}, 'Последние прогнозы'),
      hist.length
        ? hist.map(p => h('div', { class: 'rank' },
            h('span', {}, `${shortName(p.home)} — ${shortName(p.away)}`),
            h('span', { class: 'dim' }, p.result ? (p.points ? `+${p.points}` : '0') : labels[p.pick])))
        : h('div', { class: 'dim' }, 'Ты ещё не делал прогнозов.')),
    h('p', { class: 'dim' }, 'Только прогнозы. Без денег и призов, очки виртуальные и не выводятся. 18+'),
    h('p', { class: 'dim' }, 'Football data provided by the Football-Data.org API'),
    h('button', { class: 'btn gap', onclick: about }, 'О проекте и правила (18+)'),
    h('button', { class: 'btn danger', onclick: async () => {
      if (confirm('Удалить аккаунт и все прогнозы? Это необратимо.')) {
        await api('/me', { method: 'DELETE' });
        tg ? tg.close() : location.reload();
      }
    } }, 'Удалить мои данные')
  );
});

/* ---------- о проекте ---------- */

function about() {
  setTab('profile');
  const back = (me && me.nickname) ? profile : onboarding;
  const block = (title, ...lines) =>
    h('div', { class: 'card' }, h('b', {}, title), lines.map(t => h('p', { class: 'dim law' }, t)));
  show(
    h('button', { class: 'back', onclick: back }, '← Назад'),
    h('h1', {}, 'О проекте'),
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
      'Мы храним только придуманный вами ник, технический идентификатор Telegram (нужен для входа), ваши прогнозы и очки. Имя, номер телефона и фото из Telegram не сохраняются.',
      'Данные можно удалить в любой момент: Профиль → «Удалить мои данные».'),
    block('Связь', 'Вопросы и обращения: ' + CONTACT)
  );
}

/* ---------- запуск ---------- */

document.querySelectorAll('#nav button').forEach(b => b.addEventListener('click', () => {
  if (!me || !me.nickname) return onboarding();
  ({ home, rating, profile })[b.dataset.tab]();
}));

(async () => {
  try {
    const cfg = await api('/config');
    document.title = cfg.app_name;
    me = await api('/me');
    me.nickname ? home() : onboarding();
  } catch (e) {
    show(h('p', { class: 'err' }, e.message));
  }
})();