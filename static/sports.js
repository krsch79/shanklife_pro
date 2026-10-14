/* Small enhancements over server-rendered forms. Score is never defaulted to par. */
(() => {
  document.querySelectorAll('[data-progressive-players]').forEach(group => {
    const slots = [...group.querySelectorAll('.player-slot[data-slot]')];
    slots.forEach(slot => { const select = slot.querySelector('.player-select'); slot.hidden = Number(slot.dataset.slot) > 1 && !select?.value; });
    const add = document.createElement('button'); add.type = 'button'; add.className = 'button secondary'; add.textContent = 'Legg til spiller';
    const update = () => { add.hidden = !slots.some(slot => slot.hidden); };
    add.addEventListener('click', () => { const slot = slots.find(slot => slot.hidden); if (slot) { slot.hidden = false; slot.querySelector('.player-select')?.focus(); } update(); });
    group.after(add); update();
  });
  const form = document.getElementById('hole-entry-form');
  if (form) {
    form.querySelectorAll('select[name^="score_"]').forEach(select => {
      if (select.disabled) return;
      const par = Number(document.querySelector('.hole-info-strip > div:nth-child(2) strong')?.textContent);
      if (!Number.isInteger(par)) return;
      const controls = document.createElement('div'); controls.className = 'sports-score-controls';
      const allowed = [...select.options].map(o => Number(o.value)).filter(n => n > 0);
      const buttons = [];
      const set = value => { if (![...select.options].some(o => o.value === String(value))) return; select.value = String(value); select.dispatchEvent(new Event('change', {bubbles: true})); update(); };
      const update = () => buttons.forEach(b => b.setAttribute('aria-pressed', String(select.value !== '' && Number(select.value) === Number(b.dataset.score))));
      const add = (label, value, step) => {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
        if (step) { button.dataset.step = String(step); button.setAttribute('aria-label', step < 0 ? 'Ett slag mindre' : 'Ett slag mer'); }
        else { button.dataset.score = String(value); button.setAttribute('aria-pressed', 'false'); buttons.push(button); }
        button.addEventListener('click', () => { const selected = select.value === '' ? par : Number(select.value); set(step ? Math.max(Math.min(...allowed), Math.min(Math.max(...allowed), selected + step)) : value); });
        controls.append(button);
      };
      add('−', null, -1); add(`Birdie · ${par - 1}`, par - 1); add(`Par · ${par}`, par); add(`Bogey · ${par + 1}`, par + 1); add('+', null, 1);
      (select.closest('label') || select).insertAdjacentElement('afterend', controls);
      select.addEventListener('change', update); update();
    });
    const note = document.createElement('p'); note.className = 'sports-submit-note'; note.setAttribute('role', 'status');
    note.textContent = 'Endringer lagres på serveren når du velger Lagre eller bytter hull. Nettforbindelse kreves.';
    form.append(note);
    form.addEventListener('change', () => { note.textContent = 'Endret på dette hullet. Velg Lagre eller Neste hull for å lagre på serveren.'; });
    form.addEventListener('submit', async event => {
      if (event.defaultPrevented) return;
      event.preventDefault();
      if (form.dataset.sportsSaving) return;
      form.dataset.sportsSaving = '1';
      const payload = new FormData(form);
      if (event.submitter?.name) payload.append(event.submitter.name, event.submitter.value);
      note.textContent = 'Sender endringene til serveren …';
      note.setAttribute('role', 'status');
      const reset = () => {
        delete form.dataset.sportsSaving; delete form.dataset.loadingSubmitted;
        document.querySelectorAll('.submit-is-loading').forEach(button => { button.removeAttribute('aria-disabled'); button.classList.remove('submit-is-loading'); });
        const popup = document.getElementById('loading-popup'); popup?.classList.remove('is-visible'); popup?.setAttribute('aria-hidden', 'true');
      };
      try {
        const response = await fetch(form.action, {method: 'POST', body: payload, credentials: 'same-origin'});
        if (!response.ok) throw new Error(`Serveren kunne ikke bekrefte lagringen (${response.status}).`);
        if (new URL(response.url).pathname === '/login') throw new Error('Økten er utløpt. Logg inn på nytt i en annen fane og prøv igjen.');
        const html = new DOMParser().parseFromString(await response.text(), 'text/html');
        const errors = [...html.querySelectorAll('.flash-error')].map(e => e.textContent.trim());
        if (errors.length) throw new Error(errors.join(' '));
        note.textContent = 'Bekreftet på serveren.';
        window.location.assign(response.url);
      } catch (error) {
        reset(); note.setAttribute('role', 'alert');
        note.textContent = `${error.message || 'Forbindelsen ble brutt.'} Valgene dine er beholdt på denne siden. Prøv Lagre igjen når forbindelsen er tilbake.`;
        note.scrollIntoView({block: 'nearest'});
      }
    });
  }
  // Safari back/forward cache must not keep a successful form disabled or a blocking overlay open.
  window.addEventListener('pageshow', () => {
    document.querySelectorAll('form[data-loading-submitted]').forEach(form => delete form.dataset.loadingSubmitted);
    document.querySelectorAll('.submit-is-loading').forEach(button => { button.removeAttribute('aria-disabled'); button.classList.remove('submit-is-loading'); });
    const popup = document.getElementById('loading-popup'); popup?.classList.remove('is-visible'); popup?.setAttribute('aria-hidden', 'true');
  });
})();
