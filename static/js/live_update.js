
(function () {
  const slug = document.body.dataset.slug;
  if (!slug) return;

  const indicator = document.getElementById('live-indicator');
  let failCount = 0;

  async function fetchLive() {
    try {
      const res = await fetch(`/api/turnier/${slug}/live`);
      if (!res.ok) throw new Error('fetch failed');
      const data = await res.json();
      failCount = 0;
      updateMatches(data.matches);
      updateStandings(data.standings);
      if (indicator) indicator.style.display = 'inline-flex';
    } catch (e) {
      failCount++;
      if (failCount > 3 && indicator) indicator.style.display = 'none';
    }
  }

  function updateMatches(matches) {
    matches.forEach(m => {
      const row = document.querySelector(`[data-match-id="${m.id}"]`);
      if (!row) return;

      const scoreEl = row.querySelector('.match-score');
      if (scoreEl) {
        if (m.score_a !== null && m.score_b !== null) {
          scoreEl.textContent = `${m.score_a} : ${m.score_b}`;
        }
      }

      const badgeEl = row.querySelector('.badge');
      if (badgeEl) {
        badgeEl.className = `badge badge-${m.status}`;
        const dot = badgeEl.querySelector('.badge-dot');
        const label = badgeEl.querySelector('.badge-label');
        if (dot) dot.className = `badge-dot`;
        const labels = { pending: 'Ausstehend', active: 'Läuft', finished: 'Beendet' };
        if (label) label.textContent = labels[m.status] || m.status;
      }

      row.classList.remove('match-active', 'match-finished', 'match-pending');
      if (m.status === 'active') row.classList.add('match-active');
      else if (m.status === 'finished') row.classList.add('match-finished');
    });
  }

  function updateStandings(standings) {
    Object.entries(standings).forEach(([field, entries]) => {
      const tbody = document.querySelector(`[data-standings-field="${field}"]`);
      if (!tbody) return;
      entries.forEach(entry => {
        const row = tbody.querySelector(`[data-team-id="${entry.team_id}"]`);
        if (!row) return;
        const cells = row.querySelectorAll('td');
        if (cells.length >= 7) {
          cells[0].textContent = entry.rank;
          cells[2].textContent = entry.played;
          cells[3].textContent = entry.wins;
          cells[4].textContent = entry.losses;
          cells[5].textContent = (entry.diff > 0 ? '+' : '') + entry.diff;
          cells[6].textContent = entry.points;
        }
        row.classList.remove('promotes', 'relegates');
        if (entry.promotes) row.classList.add('promotes');
        else row.classList.add('relegates');
      });
    });
  }

  fetchLive();
  setInterval(fetchLive, 30000);

  // Tabs
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const content = document.getElementById(target);
      if (content) content.classList.add('active');
    });
  });
})();

// Hamburger
(function () {
  const btn = document.getElementById('hamburger');
  const nav = document.getElementById('mobile-nav');
  if (!btn || !nav) return;
  btn.addEventListener('click', () => {
    btn.classList.toggle('open');
    nav.classList.toggle('open');
  });
  nav.querySelectorAll('a').forEach(a => {
    a.addEventListener('click', () => {
      btn.classList.remove('open');
      nav.classList.remove('open');
    });
  });
})();
