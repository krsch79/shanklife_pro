/* Private, online-only workspace. No credentials or booking state in browser storage. */
(() => {
  const root = document.getElementById('starttider');
  if (!root) return;
  const $ = s => root.querySelector(s), $$ = s => [...root.querySelectorAll(s)];
  const base = root.dataset.base, csrf = root.dataset.csrf;
  const form = $('#st-search'), dialog = $('#st-dialog'), content = $('#st-dialog-content');
  let state = JSON.parse($('#starttider-initial').textContent), options = [], selected = [...state.draft.player_refs];
  let unresolved = [...(state.draft.unresolved_names || [])], bookings = [], jobs = [], page = 1, pageMore = false;
  let queue = Promise.resolve(), savingTimer, dirty = false, pendingSlot = null, showAll = false, activeTab = 'find';
  let chosenCourses = [...state.draft.courses], courseOptions = JSON.parse($('#st-course-options').textContent), catalogLoaded = false, catalogLoading = false, courseIndex = -1;
  let courseNotice = '', courseRetry = false, controlsLocked = false, activeClub = null, resourceCourses = [], resourceLoading = false, clubRequest = 0;
  let slotsShown = 20, inFlight = false, picking = false, picked = ['self'], lookupRows = [], lookupBusy = false, pickerVersion = 0;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const when = value => {
    if (!value) return '';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? value : new Intl.DateTimeFormat('nb-NO', {dateStyle:'short',timeStyle:'short'}).format(d);
  };
  const day = value => {
    if (!value) return '';
    const d = new Date(value + 'T12:00:00');
    return Number.isNaN(d.getTime()) ? value : new Intl.DateTimeFormat('nb-NO', {weekday:'short',day:'numeric',month:'short'}).format(d);
  };
  function message(text, error = false) {
    const el = $('#st-message'); el.textContent = text || ''; el.hidden = !text; el.dataset.error = String(error);
    if (dialog.open) $('#st-dialog-status').textContent = error ? text : '';
  }
  function currentDraft() {
    return {courses:[...chosenCourses], date:form.elements.date.value,
      time_from:form.elements.time_from.value, time_to:form.elements.time_to.value, players:Number(form.elements.players.value),
      player_refs:[...selected], unresolved_names:[...unresolved]};
  }
  function fill(draft) {
    ['date','time_from','time_to','players'].forEach(k => form.elements[k].value = draft[k]);
    chosenCourses = [...draft.courses]; $('#st-course-query').value = ''; activeClub = null; resourceCourses = []; resourceLoading = false; clubRequest++; renderCourses();
    selected = [...draft.player_refs]; unresolved = [...(draft.unresolved_names || [])]; labels();
  }
  const courseKey = name => name.normalize('NFC').toLocaleLowerCase('nb').trim().replace(/\s+golfklubb$/, '');
  function courseMatches() {
    const query = $('#st-course-query').value.normalize('NFC').trim().toLocaleLowerCase('nb');
    if (activeClub) return resourceCourses.filter(name => !chosenCourses.some(c => courseKey(c) === courseKey(name)));
    return query ? courseOptions.filter(name => name.toLocaleLowerCase('nb').startsWith(query)).sort((a,b) => a.localeCompare(b,'nb')) : [];
  }
  function renderCourses() {
    if (controlsLocked) return;
    const input = $('#st-course-query'), matches = courseMatches(), list = $('#st-course-matches');
    input.required = !chosenCourses.length; input.setCustomValidity('');
    $('#st-chosen-courses').innerHTML = chosenCourses.map((name,i) => `<span class="st-course-chip" role="listitem"><span>${esc(name)}</span><button type="button" data-command="remove-course" data-index="${i}" aria-label="Fjern ${esc(name)}">×</button></span>`).join('');
    list.innerHTML = matches.map((name,i) => `<button type="button" id="st-course-option-${i}" role="option" aria-selected="${i === courseIndex}" data-command="${activeClub ? 'add-course' : 'open-club'}" data-course="${esc(name)}" ${chosenCourses.length >= 8 ? 'disabled' : ''}>${esc(name)}<span aria-hidden="true">${activeClub ? '＋' : '→'}</span></button>`).join('');
    const expanded = !!input.value.trim() && matches.length > 0 && document.activeElement === input;
    list.hidden = !expanded; input.setAttribute('aria-expanded',String(expanded));
    if (expanded && courseIndex >= 0 && courseIndex < matches.length) input.setAttribute('aria-activedescendant','st-course-option-' + courseIndex);
    else input.removeAttribute('aria-activedescendant');
    $('#st-course-status').textContent = resourceLoading ? 'Henter baner hos ' + activeClub + ' …' : activeClub ? (matches.length ? 'Velg en konkret bane/sløyfe hos ' + activeClub + '. GolfBox avgjør bookingtilgangen.' : 'Alle banene hos denne klubben er allerede valgt.') : catalogLoading ? 'Henter baner fra GolfBox …' : chosenCourses.length >= 8 ? '8 baner er valgt. Fjern en bane for å legge til en annen.' : input.value.trim() ? (matches.length ? `${matches.length} ${matches.length === 1 ? 'bane' : 'baner'} begynner med «${input.value.trim()}».` : 'Ingen flere baner begynner slik.') + (courseNotice ? ' ' + courseNotice : '') : courseNotice;
    $('#st-course-retry').hidden = !courseRetry;
  }
  async function loadCourses(refresh = false) {
    if (catalogLoading || (catalogLoaded && !refresh)) return;
    catalogLoading = true; renderCourses();
    try {
      const data = await read('courses',refresh ? '&refresh=1' : '');
      courseOptions = data.courses; catalogLoaded = true; courseNotice = data.message || ''; courseRetry = data.status !== 'ok';
    } catch (error) { courseNotice = error.message + ' Et begrenset utvalg vises.'; courseRetry = true; }
    finally { catalogLoading = false; courseIndex = -1; renderCourses(); }
  }
  async function openClub(name) {
    const version = ++clubRequest;
    activeClub = name; resourceCourses = []; resourceLoading = true; courseIndex = -1;
    $('#st-course-query').value = name; $('#st-course-query').focus(); renderCourses();
    try {
      const data = await read('course_resources','&club=' + encodeURIComponent(name));
      if (version !== clubRequest) return;
      resourceCourses = data.courses;
      if (resourceCourses.length === 1) { addCourse(resourceCourses[0]); return; }
    } catch (error) {
      if (version !== clubRequest) return;
      activeClub = null; courseNotice = error.message;
    } finally {
      if (version === clubRequest) { resourceLoading = false; renderCourses(); }
    }
  }
  function addCourse(name) {
    if (chosenCourses.length >= 8 || chosenCourses.some(c => courseKey(c) === courseKey(name))) return;
    if (activeClub) chosenCourses = chosenCourses.filter(c => courseKey(c) !== courseKey(activeClub));
    chosenCourses.push(name); $('#st-course-query').value = ''; courseIndex = -1; activeClub = null; resourceCourses = []; resourceLoading = false; clubRequest++;
    $('#st-course-query').focus(); renderCourses(); changed();
  }
  function labels() {
    return selected.map(ref => ref === 'self' ? root.dataset.selfName + ' (deg)' : options.find(p => p.ref === ref)?.name || ref.slice(2)).join(', ');
  }
  function disable(value, light = false) {
    inFlight = value;
    if (light) return;
    controlsLocked = value;
    $$('button:not([role="tab"]), input, select, textarea').forEach(el => {
      if (value) { el.dataset.wasDisabled = String(el.disabled); el.disabled = true; }
      else if (el.dataset.wasDisabled !== undefined) { el.disabled = el.dataset.wasDisabled === 'true'; delete el.dataset.wasDisabled; }
    });
    if (!value) renderCourses();
  }
  async function read(kind, extra = '') {
    const response = await fetch(`${base}/data?kind=${kind}${extra}`, {credentials:'same-origin',cache:'no-store'});
    if (new URL(response.url).pathname === '/login') throw new Error('Økten er utløpt. Logg inn på nytt og åpne Starttider igjen.');
    if (!response.ok) { const data = response.headers.get('content-type')?.includes('application/json') ? await response.json() : {}; throw new Error(data.message || 'Kunne ikke hente visningen. Prøv igjen.'); }
    if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Kunne ikke hente visningen. Prøv igjen.');
    return response.json();
  }
  function run(action, payload = {}, light = false) {
    clearTimeout(savingTimer);
    const task = async () => {
      disable(true, light);
      if (!light) message(action === 'confirm' ? 'Sender den bekreftede handlingen til GolfBox …' : action === 'search' ? 'Henter ledige tider fra GolfBox …' : action === 'interpret' ? 'Tolker endringen i søket …' : 'Kontrollerer valgene …');
      try {
        const response = await fetch(`${base}/action`, {method:'POST',credentials:'same-origin',cache:'no-store',
          headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify({action,revision:state.revision,...payload})});
        if (!response.headers.get('content-type')?.includes('application/json')) throw new Error(new URL(response.url).pathname === '/login' ? 'Økten er utløpt. Feltene er beholdt. Logg inn på nytt før du fortsetter.' : `Tjenesten kunne ikke bekrefte svaret (${response.status}). Feltene er beholdt. Prøv søket igjen; ved booking må du først kontrollere Mine tider.`);
        const data = await response.json();
        if (data.revision !== undefined) state = data;
        if (!response.ok) {
          if (response.status === 409) $('#st-conflict').hidden = false;
          throw new Error(data.message || 'Handlingen kunne ikke utføres.');
        }
        $('#st-conflict').hidden = true;
        if (!light) { dirty = false; fill(state.draft); }
        if (action === 'interpret') { dirty = false; $('#st-prompt').value = ''; }
        $('#st-draft-status').textContent = 'Søket er lagret';
        if (!light) message(state.message || (action === 'search' ? 'Søket er oppdatert.' : ''), false);
        renderResults(); renderChat();
        if (state.review && (action.startsWith('review_') || action === 'confirm')) showReview();
        if (action === 'confirm') {
          if (!state.review) dialog.close();
          renderOutcome(); loadJobs(); loadBookings(true);
        }
        return true;
      } catch (error) {
        message(error.message || 'Forbindelsen ble brutt. Kontroller status før du sender en booking på nytt.', true);
        $('#st-draft-status').textContent = 'Endringene er ikke bekreftet lagret';
        if (action === 'review_slot' && $('#st-people')) picking = true;
        return false;
      } finally { disable(false, light); }
    };
    const next = queue.then(task, task); queue = next; return next;
  }
  function renderResults() {
    const r = state.result, target = $('#st-results');
    $('#st-fetched').textContent = r?.fetched_at && !dirty ? 'Hentet ' + when(r.fetched_at) : '';
    if (dirty || !r) {
      $('#st-results-title').textContent = dirty ? 'Søket er endret.' : 'Klar for neste runde?';
      target.innerHTML = '<div class="st-empty"><p>' + (dirty ? 'Søk på nytt for å vise tider som passer de nye valgene.' : 'Velg bane, dato og tidsrom for å finne ledige tider.') + '</p></div>';
      return;
    }
    const slots = r.available_slots || [];
    $('#st-results-title').textContent = r.status === 'ok' ? `${slots.length} ${slots.length === 1 ? 'tid' : 'tider'} · ${day(state.draft.date)}` : 'Søket kunne ikke fullføres';
    if (r.status !== 'ok') {
      target.innerHTML = `<div class="st-notice"><p>${esc(r.message || r.next_step || 'GolfBox er ikke tilgjengelig akkurat nå.')}</p><a href="/me">Kontroller GolfBox-tilkoblingen ↗</a></div>`;
      return;
    }
    if (!slots.length) {
      target.innerHTML = '<div class="st-empty"><h4>Ingen ledige tider i dette søket.</h4><p>Utvid tidsrommet, velg en annen bane, eller opprett et oppdrag som følger med.</p></div>';
      return;
    }
    target.innerHTML = (r.message ? `<p class="st-help">${esc(r.message)}</p>` : '') + '<div class="st-result-list">' + slots.slice(0,slotsShown).map((s,i) =>
      `<article class="st-slot"><time>${esc(s.time)}</time><div><strong>${esc(s.course)}</strong><p>${esc(day(s.date))} · ${esc(s.available_spots)} ledige plasser</p></div>${r.booking_enabled && s.club_guid && s.resource_guid ? `<button type="button" class="button secondary" data-command="slot" data-index="${i}">Velg tid</button>` : '<span class="st-help">Booking støttes ikke her</span>'}</article>`).join('') + '</div>' +
      (slots.length > slotsShown ? '<button type="button" class="st-link" data-command="more-slots">Vis flere tider</button>' : '') + '<p class="st-help">Ingen plasser holdes av før du bekrefter.</p>';
  }
  function renderChat() {
    const items = state.chat || [];
    $('#st-chat').innerHTML = items.length ? '<details class="st-chat-history"><summary>Tidligere meldinger (' + items.length + ')</summary>' + items.map(m => `<p><strong>Du:</strong> ${esc(m.text)}<br>${esc(m.reply)}</p>`).join('') + '</details>' : '';
  }
  function showDialog(title, html) {
    $('#st-dialog-title').textContent = title; content.innerHTML = html; $('#st-dialog-status').textContent = '';
    if (!dialog.open) dialog.showModal();
  }
  function showReview() {
    const r = state.review;
    const titles = {booking:'Bekreft starttiden.',watch:'Aktiver overvåking.',scheduled:'Bekreft engangsforsøket.',recurring:'Bekreft ukentlig oppdrag.',cancel:'Avbestill starttiden?',stop:'Stoppe oppdraget?'};
    const buttons = {booking:'Bekreft booking',watch:'Aktiver overvåking',scheduled:'Aktiver engangsforsøk',recurring:'Aktiver ukentlig oppdrag',cancel:'Bekreft avbestilling',stop:'Stopp oppdrag'};
    showDialog(titles[r.kind] || 'Kontroller valgene.', `<dl class="st-facts"><dt>Bane</dt><dd>${esc(r.course)}</dd><dt>Spilledato</dt><dd>${esc(r.date)}</dd><dt>Klokken</dt><dd>${esc(r.time)}</dd><dt>Spillere</dt><dd>${esc((r.players || []).join(', '))}</dd></dl>${r.memberships?.length ? '<p class="st-help"><strong>Medlemskap som brukes</strong><br>' + r.memberships.map(m => esc(m.name) + ' · ' + esc(m.club) + ' · ' + esc(m.member_number)).join('<br>') + '</p>' : ''}<p class="st-help">${esc(r.message)}</p><p class="st-help">Oppsummeringen gjelder til ${esc(when(r.expires_at))}.</p><div class="st-inline"><button type="button" class="button st-primary" data-command="confirm">${buttons[r.kind]}</button><button type="button" class="button secondary" data-command="dismiss">Tilbake</button></div>`);
  }
  function renderOutcome() {
    const result = state.outcome;
    if (!result) return;
    const uncertain = result.status === 'booking_unverified';
    const success = ['booking_created','scheduled_booking_created','recurring_booking_created','watch_booking_created','booking_cancelled','scheduled_booking_cancelled'].includes(result.status);
    message((uncertain ? 'Uavklart resultat. ' : '') + (result.message || 'Handlingen er behandlet.'), !success && result.status !== 'confirmation_required');
  }
  function tab(key) {
    activeTab = key;
    $$('[data-tab]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === key)));
    $$('[role=tabpanel]').forEach(p => p.hidden = p.id !== 'st-panel-' + key);
    history.replaceState(null, '', '#' + key);
    if (key === 'mine') loadBookings(); if (key === 'auto') loadJobs(); if (key === 'history') loadHistory();
  }
  async function loadFavorites() {
    const data = await read('favorites'); options = [...data.players, ...options.filter(p => p.ref.startsWith('m:') && !data.players.some(o => memberKey(o.ref) === memberKey(p.ref)))]; labels();
    return data;
  }
  const memberKey = ref => ref === 'self' ? ref : ref.slice(2);
  const isPicked = ref => picked.some(r => memberKey(r) === memberKey(ref));
  function personRow(p) {
    const full = picked.length >= Number(form.elements.players.value);
    return `<label class="st-favorite"><span class="st-avatar" aria-hidden="true">${esc(p.name.slice(0,1))}</span><span class="st-person"><strong>${esc(p.name)}</strong><small>${esc(p.club)} · ${esc(p.member_number)}</small></span><input type="checkbox" data-person="${esc(p.ref)}" ${isPicked(p.ref) ? 'checked' : ''} ${full && !isPicked(p.ref) ? 'disabled' : ''} aria-label="${esc(p.name + ', ' + p.club + ', ' + p.member_number)}"></label>`;
  }
  function renderPeople(filter = $('#st-people-search')?.value || '') {
    if (!picking || !$('#st-people')) return;
    const query = filter.toLocaleLowerCase('nb'), recent = state.recent_refs || [];
    const filtered = options.filter(p => p.ref.startsWith('f:') && (p.name + ' ' + p.member_number + ' ' + p.club).toLocaleLowerCase('nb').includes(query));
    const ordered = [...filtered].sort((a,b) => Number(isPicked(b.ref)) - Number(isPicked(a.ref)) || Number(recent.includes(b.ref)) - Number(recent.includes(a.ref)));
    const rows = showAll || query ? ordered : ordered.slice(0,5);
    $('#st-people').innerHTML = rows.map(personRow).join('') || '<p class="st-help">Ingen favoritter passer. Søk i GolfBox for å finne flere spillere.</p>';
    $('#st-lookup-results').innerHTML = lookupRows.map(personRow).join('');
    const companions = picked.filter(r => r !== 'self');
    $('#st-chosen').innerHTML = companions.map((ref,i) => {
      const p = options.find(p => p.ref === ref);
      return `<div class="st-chosen-row"><span><small>SPILLER ${i + 2}</small><strong>${esc(p?.name || ref.slice(2))}</strong><small>${esc(p?.club || '')} · ${esc(p?.member_number || ref.slice(2))}</small></span><button type="button" class="st-link" data-command="remove-person" data-ref="${esc(ref)}" aria-label="Fjern ${esc(p?.name || ref.slice(2))}">Fjern</button></div>`;
    }).join('');
    const remaining = Number(form.elements.players.value) - picked.length;
    $('#st-selected').textContent = remaining ? `${picked.length} av ${form.elements.players.value} valgt · velg ${remaining} til` : picked.length === 1 ? 'Spiller 1 er valgt' : `Alle ${picked.length} spillere er valgt`;
    $('#st-people-done').disabled = remaining !== 0 || lookupBusy;
    $('#st-people-done').textContent = pendingSlot === null ? 'Fortsett til oppdrag →' : 'Kontroller booking →';
  }
  async function players() {
    const version = ++pickerVersion;
    showDialog('Hvem blir med?', '<p>Henter dine favoritter …</p>');
    try {
      const data = await loadFavorites();
      if (version !== pickerVersion || !dialog.open) return;
      // Retain verified directory choices for this picker session.
      options = [...options, ...lookupRows.filter(p => !options.some(o => memberKey(o.ref) === memberKey(p.ref)))];
      const slot = pendingSlot === null ? null : state.result?.available_slots[pendingSlot];
      showDialog('Hvem blir med?', `<p class="st-help">${slot ? esc(slot.course) + ' · ' + esc(day(slot.date)) + ' · kl. ' + esc(slot.time) : 'Velg spillere til oppdraget'} · ${form.elements.players.value} ${Number(form.elements.players.value) === 1 ? 'spiller' : 'spillere'}</p><div class="st-self"><span class="st-avatar" aria-hidden="true">1</span><span><small>SPILLER 1 · DEG</small><strong>${esc(root.dataset.selfName)}</strong><small>Alltid med i bookingen</small></span><span aria-hidden="true">✓</span></div><div id="st-chosen"></div><div id="st-selected" class="st-selected" role="status"></div>${Number(form.elements.players.value) > 1 ? `<label class="st-field">Finn medspillere<input type="text" id="st-people-search" maxlength="100" placeholder="Navn eller medlemsnummer" autocomplete="off"></label><button type="button" class="button secondary" data-command="lookup-players">Søk i GolfBox</button><p id="st-lookup-status" class="st-help" role="status"></p><div id="st-lookup-results"></div><h4 class="st-favorites-title">Dine favoritter</h4><div id="st-people"></div><div class="st-inline st-pick-toolbar"><button type="button" class="st-link" data-command="all-people">Vis alle favoritter (${options.filter(p => p.ref.startsWith('f:')).length})</button><button type="button" class="st-link" data-command="sync">Oppdater fra GolfBox</button></div><p class="st-help">${data.fetched_at ? 'Sist hentet ' + esc(when(data.fetched_at)) : 'Ingen favoritter hentet ennå.'}</p>` : '<div id="st-people" hidden></div><div id="st-lookup-results" hidden></div>'}<div class="st-inline"><button type="button" id="st-people-done" class="button st-primary" data-command="players-done">Kontroller booking →</button></div><p class="st-help">Ingen plasser reserveres før siste bekreftelse.</p>`);
      renderPeople();
    } catch (error) { if (version === pickerVersion) $('#st-dialog-status').textContent = error.message; }
  }
  async function lookupPlayers() {
    if (lookupBusy) return;
    const query = $('#st-people-search').value.trim(), version = pickerVersion;
    if (query.length < 2) { $('#st-lookup-status').textContent = 'Skriv minst to tegn eller et medlemsnummer.'; return; }
    lookupBusy = true; $('[data-command="lookup-players"]').disabled = true;
    $('#st-lookup-status').textContent = 'Søker i GolfBox …'; lookupRows = []; renderPeople();
    try {
      const response = await fetch(`${base}/players`, {method:'POST', credentials:'same-origin', cache:'no-store',
        headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({query})});
      if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Kunne ikke hente spillere. Kontroller innloggingen og prøv igjen.');
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Spillersøket feilet. Prøv igjen.');
      if (version !== pickerVersion || !picking) return;
      lookupRows = data.players;
      for (const p of lookupRows) if (!options.some(o => memberKey(o.ref) === memberKey(p.ref))) options.push(p);
      $('#st-lookup-status').textContent = lookupRows.length ? `${lookupRows.length} treff i GolfBox · velg riktig navn og klubb` : 'Ingen treff på andre spillere. Prøv fullt navn eller medlemsnummer.';
    } catch (error) {
      if (version === pickerVersion && picking) $('#st-lookup-status').textContent = error.message;
    } finally {
      if (version === pickerVersion && picking) { lookupBusy = false; $('[data-command="lookup-players"]').disabled = false; renderPeople(); }
    }
  }
  function openPlayers(index = null) {
    clearTimeout(savingTimer); pendingSlot = index; picking = true; lookupBusy = false; showAll = false;
    picked = ['self']; lookupRows = []; players();
  }
  async function loadBookings(refresh = false) {
    try {
      const data = await read('bookings', refresh ? '&refresh=1' : ''); bookings = data.bookings || [];
      $('[data-count=mine]').textContent = data.status === 'ok' ? ' ' + bookings.length : '';
      const issue = data.status !== 'ok' ? `<div class="st-notice"><p>${esc(data.message || 'Kunne ikke hente bookinger.')}</p><a href="/me">Kontroller tilkoblingen ↗</a>${data.stale ? '<p class="st-help">Sist kjente tider vises under. De kan være endret i GolfBox.</p>' : ''}</div>` : '';
      $('#st-bookings').innerHTML = issue + (data.fetched_at ? `<p class="st-help">Sist hentet ${esc(when(data.fetched_at))}</p>` : '') + bookings.map((b,i) => `<article class="st-card"><div class="st-card-heading"><div><p class="eyebrow">${esc(b.date)}</p><h4>${esc(b.time)} · ${esc(b.course || b.club)}</h4></div><span class="st-tag">${data.stale ? 'Sist kjent reservasjon' : 'Bekreftet i GolfBox'}</span></div><p>${esc((b.players || []).join(', '))}</p>${b.can_cancel && data.status === 'ok' ? `<button type="button" class="st-link" data-command="cancel" data-index="${i}">Avbestill ↗</button>` : '<p class="st-help">Avbestilling er ikke tilgjengelig her akkurat nå.</p>'}</article>`).join('') + (!bookings.length && data.status === 'ok' ? '<div class="st-empty"><h4>Ingen kommende starttider.</h4><p>Finn din neste runde under Finn tid.</p></div>' : '');
      const next = bookings[0];
      $('#st-next').hidden = !next || data.status !== 'ok';
      if (next) $('#st-next').innerHTML = `<p><small>NESTE BOOKING</small><br><strong>${esc(next.date)} · ${esc(next.time)} · ${esc(next.course || next.club)}</strong></p><button type="button" class="st-link" data-command="mine">Se tiden →</button>`;
    } catch (error) { $('#st-bookings').innerHTML = `<div class="st-notice">${esc(error.message)}</div>`; }
  }
  const types = {scheduled:'Engangsforsøk',recurring:'Ukentlig oppdrag',watch:'Overvåking'};
  async function loadJobs() {
    try {
      jobs = (await read('jobs')).jobs;
      $('[data-count=auto]').textContent = ' ' + jobs.length;
      $('#st-jobs').innerHTML = jobs.length ? jobs.map((j,i) => `<article class="st-card"><div class="st-card-heading"><div><p class="eyebrow">${types[j.type] || 'Oppdrag'}</p><h4>${esc(j.course)} · ${esc(j.play_date)}</h4></div><span class="st-tag">${j.type === 'watch' ? 'Følger med' : 'Venter på kjøring'}</span></div><p>${esc(j.play_time)} · ${esc(j.players.join(', '))}</p><p class="st-help">${esc(j.schedule_label || '')} Neste forsøk: ${esc(j.execute_at)} · Europe/Oslo</p><p class="st-help">${j.last_run_at ? "Siste forsøk: " + esc(when(j.last_run_at)) + ". " : ""}${esc(j.last_message || "")}<br>Kan booke uten ny bekreftelse. ${j.type === 'watch' ? 'Sjekker hvert 5. minutt frem til slutten av tidsrommet.' : ''}</p><div class="st-inline"><button type="button" class="st-link" data-command="job-log">Se hendelser ↗</button>${j.can_cancel ? `<button type="button" class="st-link" data-command="stop" data-index="${i}">Stopp oppdrag</button>` : '<span class="st-help">Kan ikke stoppes nå.</span>'}</div></article>`).join('') : '<div class="st-empty"><h4>Ingen aktive oppdrag.</h4><p>Du kan følge med på ledige tider, bestille et engangsforsøk eller lage et ukentlig oppdrag.</p></div>';
    } catch (error) { $('#st-jobs').innerHTML = `<p>${esc(error.message)}</p>`; }
  }
  async function loadHistory() {
    try {
      const data = await read('history', '&page=' + page); pageMore = data.has_more;
      $('#st-history').innerHTML = data.history.length ? data.history.map(h => `<article class="st-history-row"><span class="st-help">${esc(h.history_at)}</span><div><strong>${esc(h.course)} · ${esc(h.play_time)}</strong><p>${esc(h.play_date)} · ${esc(h.players.join(', '))}</p><span class="st-tag">${esc(h.type_label)} · ${esc(h.status_label)}</span></div><a href="${esc(h.url)}">Se hendelser ↗</a></article>`).join('') : '<div class="st-empty"><p>Ingen hendelser på denne siden.</p></div>';
      $('#st-page-label').textContent = 'Side ' + page;
      $('[data-command=history-prev]').disabled = page <= 1; $('[data-command=history-next]').disabled = !pageMore;
    } catch (error) { $('#st-history').textContent = error.message; }
  }
  function jobDialog() {
    pendingSlot = null;
    const d = currentDraft();
    showDialog('Et oppdrag. Tydelige rammer.', `<p class="st-help">Bruker bane, spilledato, tidsrom og spillere fra søket ditt. Kontroller disse før du fortsetter.</p><label class="st-field">Oppdragstype<select id="st-job-kind"><option value="watch">Følg med på ledige tider</option><option value="scheduled">Book når booking åpner</option><option value="recurring">Fast ukentlig oppdrag</option></select></label><dl class="st-facts"><dt>Bane</dt><dd>${esc(d.courses.join(', '))}</dd><dt>Spilledato</dt><dd>${esc(d.date)}</dd><dt>Tidsrom</dt><dd>${esc(d.time_from)}–${esc(d.time_to)}</dd><dt>Valgt</dt><dd>${esc(labels())}</dd></dl><div id="st-job-fields"></div><div class="st-inline"><button type="button" class="button" data-command="review-job">Kontroller oppdrag →</button></div>`);
    jobFields();
  }
  function jobFields() {
    const kind = $('#st-job-kind').value;
    const days = ['mandag','tirsdag','onsdag','torsdag','fredag','lørdag','søndag'];
    $('#st-job-fields').innerHTML = kind === 'watch' ? '<p class="st-help">Sjekker hvert 5. minutt og kan booke automatisk frem til slutten av tidsrommet. Må aktiveres på neste steg.</p>' : kind === 'scheduled' ? '<label class="st-field">Kjør forsøket · Europe/Oslo<input type="datetime-local" id="st-execute-at" required></label><p class="st-help">Ett forsøk på starttiden «Fra klokken». Velg når booking åpner hos klubben.</p>' : `<label class="st-field">Forsøk hver<select id="st-weekday">${days.map((d,i) => `<option value="${i}">${d}</option>`).join('')}</select></label><label class="st-field">Kjør klokken · Europe/Oslo<input type="time" id="st-execute-time" value="07:00"></label><label class="st-field">Regel for neste spilledag<select id="st-weeks">${["Første spilledag, også samme dag","Første spilledag, neste uke ved samme ukedag","Én senere ukentlig forekomst","To senere ukentlige forekomster","Tre senere ukentlige forekomster"].map((text,n) => `<option value="${n}">${text}</option>`).join('')}</select></label><p class="st-help">Spilleukedagen tas fra datoen i søket. Oppdraget gjelder til du stopper det.</p>`;
  }
  function changed() {
    selected = ['self']; unresolved = [];
    dirty = true; renderResults(); $('#st-draft-status').textContent = 'Lagrer søket …';
    clearTimeout(savingTimer);
    savingTimer = setTimeout(() => { if (form.checkValidity()) run('draft', {draft:currentDraft()}, true); }, 700);
  }
  form.addEventListener('submit', event => { event.preventDefault();
    if ($('#st-course-query').value.trim()) { $('#st-course-query').setCustomValidity('Klikk på en bane i trefflisten for å legge den til.'); $('#st-course-query').reportValidity(); return; }
    slotsShown = 20; selected = ['self']; unresolved = []; run('search',{draft:currentDraft()}); });
  form.addEventListener('change', event => { if (event.target.name) changed(); });
  form.addEventListener('input', event => { if (event.target.name) changed(); });
  $('#st-course-query').addEventListener('focus', () => { renderCourses(); loadCourses(); });
  $('#st-course-query').addEventListener('input', () => { clubRequest++; activeClub = null; resourceCourses = []; resourceLoading = false; courseIndex = -1; renderCourses(); });
  $('#st-course-query').addEventListener('blur', () => { $('#st-course-matches').hidden = true; $('#st-course-query').setAttribute('aria-expanded','false'); });
  $('#st-course-matches').addEventListener('pointerdown', event => { if (event.target.closest('button')) event.preventDefault(); });
  $('#st-course-query').addEventListener('keydown', event => {
    const matches = courseMatches();
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); courseIndex = matches.length ? (courseIndex < 0 ? (event.key === 'ArrowDown' ? 0 : matches.length - 1) : (courseIndex + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length) : -1; renderCourses();
      if (courseIndex >= 0) $('#st-course-option-' + courseIndex).scrollIntoView({block:'nearest'});
    } else if (event.key === 'Enter') {
      event.preventDefault(); if (courseIndex >= 0 && matches[courseIndex]) { if (activeClub) addCourse(matches[courseIndex]); else openClub(matches[courseIndex]); }
    } else if (event.key === 'Escape') { event.preventDefault(); $('#st-course-matches').hidden = true; event.target.setAttribute('aria-expanded','false'); event.target.removeAttribute('aria-activedescendant'); courseIndex = -1; }
  });
  root.addEventListener('input', event => { if (event.target.id === 'st-people-search') renderPeople(event.target.value); });
  root.addEventListener('keydown', event => { if (event.target.id === 'st-people-search' && event.key === 'Enter') { event.preventDefault(); lookupPlayers(); } });
  dialog.addEventListener('close', () => { picking = false; pickerVersion++; lookupBusy = false; pendingSlot = null; });
  root.addEventListener('change', event => {
    if (event.target.matches('[data-person]')) {
      const ref = event.target.dataset.person;
      if (event.target.checked) {
        if (picked.length >= Number(form.elements.players.value)) { event.target.checked = false; return; }
        if (!isPicked(ref)) picked.push(ref);
      } else picked = picked.filter(r => memberKey(r) !== memberKey(ref));
      renderPeople();
    }
    if (event.target.id === 'st-job-kind') jobFields();
  });
  root.addEventListener('click', async event => {
    const b = event.target.closest('button'); if (!b || b.disabled) return;
    if (b.dataset.tab) { tab(b.dataset.tab); return; }
    const command = b.dataset.command; if (!command) return;
    if (command === 'open-club') { openClub(b.dataset.course); return; }
    if (command === 'add-course') { addCourse(b.dataset.course); return; }
    if (command === 'remove-course') { chosenCourses.splice(Number(b.dataset.index),1); courseIndex = -1; renderCourses(); changed(); return; }
    if (command === 'retry-courses') { $('#st-course-query').focus(); loadCourses(true); return; }
    if (command === 'close') { dialog.close(); pendingSlot = null; return; }
    if (command === 'all-people') { showAll = true; renderPeople(); return; }
    if (command === 'lookup-players') { lookupPlayers(); return; }
    if (command === 'remove-person') { picked = picked.filter(r => r !== b.dataset.ref); renderPeople(); return; }
    if (command === 'players-done') {
      if (picked.length !== Number(form.elements.players.value) || lookupBusy) return;
      const index = pendingSlot;
      selected = [...picked]; unresolved = []; picking = false;
      // Keep the dialog open while moving to review; close events cancel a picker.
      if (index !== null) run('review_slot',{index,draft:currentDraft()});
      else jobDialog();
      return;
    }
    if (command === 'sync') {
      const keep = [...picked];
      if (await run('sync_favorites')) { picked = keep; await players(); }
      return;
    }
    if (command === 'reset') { if (await run('reset')) { selected = [...state.draft.player_refs]; dirty = false; fill(state.draft); renderResults(); } return; }
    if (command === 'reload') {
      try { state = await read('state'); dirty = false; fill(state.draft); renderResults(); $('#st-conflict').hidden = true; message('Gjeldende søk er hentet.'); } catch (e) { message(e.message,true); } return;
    }
    if (command === 'interpret' || command === 'later') {
      const prompt = command === 'later' ? 'heller etter 17' : $('#st-prompt').value;
      run('interpret',{prompt,draft:currentDraft()}); return;
    }
    if (command === 'slot') {
      if (dirty || inFlight) { message('Søket er endret. Hent nye tider før du velger.',true); return; }
      const index = Number(b.dataset.index);
      openPlayers(index); return;
    }
    if (command === 'confirm') { if (state.review) run('confirm',{id:state.review.id}); return; }
    if (command === 'dismiss') { dialog.close(); run('dismiss'); return; }
    if (command === 'more-slots') { slotsShown += 20; renderResults(); return; }
    if (command === 'mine') { tab('mine'); return; }
    if (command === 'refresh-bookings') { loadBookings(true); return; }
    if (command === 'new-job') { openPlayers(); return; }
    if (command === 'review-job') {
      const kind = $('#st-job-kind').value;
      run('review_job',{draft:currentDraft(),job:{kind,execute_at:$('#st-execute-at')?.value,
        weekday:$('#st-weekday')?.value,execute_time:$('#st-execute-time')?.value,weeks_ahead:$('#st-weeks')?.value}}); return;
    }
    if (command === 'cancel') { run('review_cancel',{index:Number(b.dataset.index)}); return; }
    if (command === 'stop') { const j = jobs[Number(b.dataset.index)]; run('review_stop',{id:j.id,type:j.type}); return; }
    if (command === 'job-log' || command === 'refresh-history') { page = 1; tab('history'); return; }
    if (command === 'history-prev' || command === 'history-next') { page += command === 'history-prev' ? -1 : 1; loadHistory(); }
  });
  $$('[role=tab]').forEach((b,i,buttons) => b.addEventListener('keydown', e => {
    const delta = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (delta) { e.preventDefault(); const next = buttons[(i + delta + buttons.length) % buttons.length]; next.focus(); tab(next.dataset.tab); }
  }));
  fill(state.draft); renderResults(); renderChat(); renderOutcome();
  if (state.review) showReview();
  loadJobs(); loadBookings();
  const firstTab = location.hash.slice(1); if (['mine','auto','history'].includes(firstTab)) tab(firstTab);
})();
