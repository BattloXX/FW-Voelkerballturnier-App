
(function () {
  // Stepper inputs
  document.querySelectorAll('.stepper-group').forEach(group => {
    const input = group.querySelector('.result-input');
    const plus = group.querySelector('.stepper-btn.plus');
    const minus = group.querySelector('.stepper-btn.minus');
    if (!input) return;
    if (plus) plus.addEventListener('click', () => { input.value = Math.max(0, (parseInt(input.value) || 0) + 1); });
    if (minus) minus.addEventListener('click', () => { input.value = Math.max(0, (parseInt(input.value) || 0) - 1); });
  });

  // Confirmation dialog
  const submitBtn = document.getElementById('submit-result-btn');
  const overlay = document.getElementById('confirmation-overlay');
  const confirmBtn = document.getElementById('confirm-result-btn');
  const cancelBtn = document.getElementById('cancel-result-btn');
  const confirmScoreA = document.getElementById('confirm-score-a');
  const confirmScoreB = document.getElementById('confirm-score-b');
  const confirmNameA = document.getElementById('confirm-name-a');
  const confirmNameB = document.getElementById('confirm-name-b');
  const inputA = document.getElementById('players-a');
  const inputB = document.getElementById('players-b');

  if (submitBtn && overlay) {
    submitBtn.addEventListener('click', () => {
      const a = parseInt(inputA?.value) || 0;
      const b = parseInt(inputB?.value) || 0;
      if (confirmScoreA) confirmScoreA.textContent = a;
      if (confirmScoreB) confirmScoreB.textContent = b;
      overlay.classList.add('open');
    });
  }

  if (cancelBtn && overlay) {
    cancelBtn.addEventListener('click', () => overlay.classList.remove('open'));
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.classList.remove('open'); });
  }

  if (confirmBtn) {
    confirmBtn.addEventListener('click', async () => {
      const matchId = confirmBtn.dataset.matchId;
      const slug = confirmBtn.dataset.slug;
      const a = parseInt(inputA?.value) || 0;
      const b = parseInt(inputB?.value) || 0;

      confirmBtn.disabled = true;
      confirmBtn.textContent = 'Speichern...';

      try {
        const res = await fetch(`/schiri/turnier/${slug}/match/${matchId}/result`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ players_remaining_a: a, players_remaining_b: b })
        });
        if (res.ok) {
          window.location.reload();
        } else {
          alert('Fehler beim Speichern. Bitte erneut versuchen.');
          confirmBtn.disabled = false;
          confirmBtn.textContent = 'Bestätigen';
          overlay.classList.remove('open');
        }
      } catch (e) {
        alert('Netzwerkfehler. Bitte erneut versuchen.');
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Bestätigen';
        overlay.classList.remove('open');
      }
    });
  }

  // Zwischenstand button
  const zwischenstandBtn = document.getElementById('update-zwischenstand-btn');
  if (zwischenstandBtn) {
    zwischenstandBtn.addEventListener('click', async () => {
      const matchId = zwischenstandBtn.dataset.matchId;
      const slug = zwischenstandBtn.dataset.slug;
      const a = parseInt(inputA?.value) || 0;
      const b = parseInt(inputB?.value) || 0;
      const origText = zwischenstandBtn.textContent;
      zwischenstandBtn.disabled = true;
      zwischenstandBtn.textContent = 'Speichern…';
      try {
        const res = await fetch(`/schiri/turnier/${slug}/match/${matchId}/zwischenstand`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ players_remaining_a: a, players_remaining_b: b })
        });
        if (res.ok) {
          zwischenstandBtn.textContent = '✓ Aktualisiert';
          setTimeout(() => {
            zwischenstandBtn.textContent = origText;
            zwischenstandBtn.disabled = false;
          }, 2000);
        } else {
          throw new Error();
        }
      } catch (e) {
        alert('Fehler beim Speichern des Zwischenstands.');
        zwischenstandBtn.textContent = origText;
        zwischenstandBtn.disabled = false;
      }
    });
  }

  // Start match button
  const startBtn = document.getElementById('start-match-btn');
  if (startBtn) {
    startBtn.addEventListener('click', async () => {
      const matchId = startBtn.dataset.matchId;
      const slug = startBtn.dataset.slug;
      startBtn.disabled = true;
      try {
        await fetch(`/schiri/turnier/${slug}/match/${matchId}/start`, { method: 'POST' });
        window.location.reload();
      } catch (e) {
        startBtn.disabled = false;
      }
    });
  }

  // Admin result form
  document.querySelectorAll('.admin-result-form').forEach(form => {
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const matchId = form.dataset.matchId;
      const tournamentId = form.dataset.tournamentId;
      const scoreA = form.querySelector('[name=score_a]')?.value;
      const scoreB = form.querySelector('[name=score_b]')?.value;
      const remA = form.querySelector('[name=players_remaining_a]')?.value;
      const remB = form.querySelector('[name=players_remaining_b]')?.value;

      const res = await fetch(`/admin/turnier/${tournamentId}/match/${matchId}/ergebnis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          score_a: parseInt(scoreA), score_b: parseInt(scoreB),
          players_remaining_a: remA ? parseInt(remA) : null,
          players_remaining_b: remB ? parseInt(remB) : null,
        })
      });
      if (res.ok) {
        const row = form.closest('tr');
        if (row) row.classList.add('match-finished');
        const statusBadge = form.closest('tr')?.querySelector('.badge');
        if (statusBadge) statusBadge.outerHTML = '<span class="badge badge-finished"><span class="badge-dot"></span><span class="badge-label">Beendet</span></span>';
      }
    });
  });
})();
