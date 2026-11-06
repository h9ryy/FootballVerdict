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
  show(
    h('button', { class: 'back', onclick: home }, '← Лиги'),
    h('div', { class: 'row' },
      h('button', { class: 'arrow', onclick: () => md > 1 && league(code, name, md - 1) }, '‹'),
      h('h1', {}, `${name} · тур ${md}`),
      h('button', { class: 'arrow', onclick: () => league(code, name, md + 1) }, '›')),
    d.matches.length
      ? d.matches.map(matchCard)
      : h('p', { class: 'dim center' }, 'В этом туре нет матчей.')
  );
});

function matchCard(m) {
  const when = new Date(m.kickoff).toLocaleString('ru-RU',
    { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  const labels = { H: 'П1', D: 'Ничья', A: 'П2' };

  const btns = ['H', 'D', 'A'].map(k => {
    const b = h('button', { class: 'pick', disabled: m.locked }, labels[k]);
    b.paint = () => {
      b.className = 'pick' + (m.pick === k ? ' active' : '');
      if (m.result && m.pick === k) b.classList.add(k === m.result ? 'right' : 'wrong');
    };
    b.paint();
    b.addEventListener('click', async () => {
      try {
        await api('/predictions', { method: 'POST', body: JSON.stringify({ match_id: m.id, pick: k }) });
        m.pick = k;
        btns.forEach(x => x.paint());
      } catch (e) { alert(e.message); }
    });
    return b;
  });

  let status = when;
  if (m.result) status = 'Завершён · исход: ' + labels[m.result];
  else if (m.locked) status = 'Приём прогнозов закрыт';

  return h('div', { class: 'card' },
    h('div', { class: 'teams' }, `${m.home} — ${m.away}`),
    h('div', { class: 'dim' }, status),
    h('div', { class: 'picks' }, btns)
  );
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
            h('span', {}, `${p.home} — ${p.away}`),
            h('span', { class: 'dim' }, p.result ? (p.points ? `+${p.points}` : '0') : labels[p.pick])))
        : h('div', { class: 'dim' }, 'Ты ещё не делал прогнозов.')),
    h('p', { class: 'dim' }, 'Только прогнозы. Без денег и призов, очки виртуальные и не выводятся. 18+'),
    h('p', { class: 'dim' }, 'Football data provided by the Football-Data.org API'),
    h('button', { class: 'btn danger', onclick: async () => {
      if (confirm('Удалить аккаунт и все прогнозы? Это необратимо.')) {
        await api('/me', { method: 'DELETE' });
        tg ? tg.close() : location.reload();
      }
    } }, 'Удалить мои данные')
  );
});

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