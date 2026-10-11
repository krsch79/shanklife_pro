(() => {
  const panel = document.querySelector('[data-trackman-state]');
  if (!panel) return;
  let state = panel.dataset.trackmanState;
  let delay = 5000;
  const active = () => ['authorizing', 'starting', 'syncing'].includes(state);
  const poll = async () => {
    try {
      if (state === 'authorizing') {
        const response = await fetch(panel.dataset.pollUrl, {method: 'POST', credentials: 'same-origin', headers: {'X-CSRF-Token': panel.dataset.csrf}});
        const data = await response.json();
        delay = Math.max(data.interval || 5, 5) * 1000;
        if (['connected', 'expired', 'denied'].includes(data.state)) { location.reload(); return; }
      }
      const response = await fetch(panel.dataset.statusUrl, {credentials: 'same-origin', cache: 'no-store'});
      if (!response.ok) throw new Error('status');
      const data = await response.json();
      document.getElementById('trackman-status').textContent = data.message || '';
      state = data.state;
      if (!active()) { location.reload(); return; }
    } catch (_) { document.getElementById('trackman-status').textContent = 'Venter på forbindelse. Prøver igjen …'; delay = 10000; }
    if (active()) setTimeout(poll, delay);
  };
  if (active()) setTimeout(poll, delay);
})();
