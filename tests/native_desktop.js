// Injected only by a debug-only native acceptance hook. Uses real Rust IPC.
(async () => {
  const checks = [];
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  const invoke = (command, args = {}) => window.__TAURI_INTERNALS__.invoke(command, args);
  const assert = (value, message) => { if (!value) throw new Error(message); checks.push(message); };
  const wait = async (read, label) => {
    const until = Date.now() + 15000;
    while (Date.now() < until) { const value = read(); if (value) return value; await delay(60); }
    throw new Error('Timed out: ' + label);
  };
  const button = (name) => [...document.querySelectorAll('button')].find(b => (b.getAttribute('aria-label') || b.textContent.trim()) === name && b.getBoundingClientRect().width);
  const click = async name => { (await wait(() => button(name), name)).click(); await delay(150); };
  const setInput = (input, value) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', {bubbles:true}));
    input.dispatchEvent(new Event('change', {bubbles:true}));
  };
  try {
    await wait(() => document.querySelectorAll('article.card').length >= 3, 'legacy account cards');
    assert(document.body.textContent.includes('Agent Fleet'), 'Product name rendered in native WebView');
    assert(!document.body.textContent.includes('Vorschaudaten'), 'Production transport has no demo fallback');
    assert(document.querySelectorAll('article.card').length >= 3, 'Existing profiles rendered from legacy SQLite');
    await wait(() => [...document.querySelectorAll('h3')].some(h => h.textContent === 'Claude CLI · Standardanmeldung'), 'automatic native Claude discovery');
    const discovered = await invoke('fleet_request', {target:null, argv:['overview']});
    const defaultAccount = discovered.accounts.find(a => a.auth_mode === 'native_default');
    assert(defaultAccount?.connected && defaultAccount?.enabled, 'Existing CLI login is discovered and enabled automatically');
    await click('Details zu Claude CLI · Standardanmeldung');
    assert(document.body.textContent.includes('Anmeldung wird von deiner normalen Claude-CLI verwaltet'), 'Default login ownership and shared logout are visible');
    assert(button('Erneut anmelden') === undefined && button('Für Aufträge deaktivieren') !== undefined, 'Default CLI login has scheduling control without global reauthentication');
    await click('Zurück');
    assert(document.documentElement.scrollWidth <= window.innerWidth + 2, 'Native overview has no horizontal overflow');
    const accounts = await invoke('fleet_request', {target:null, argv:['overview']});
    for (const account of accounts.accounts.filter(a => a.connected)) {
      const window = account.windows.find(w => w.minutes === 300 && w.used !== null);
      if (!window) continue;
      const card = [...document.querySelectorAll('article.card')].find(c => c.querySelector('h3')?.textContent === account.name);
      assert(card?.querySelector('[role="img"]')?.getAttribute('aria-label')?.startsWith((100-window.used)+' % frei'), 'Rust quota matches native UI percentage for '+account.name);
    }
    const rows = new Map();
    for (const card of document.querySelectorAll('article.card')) {
      const row = Math.round(card.getBoundingClientRect().top);
      const ring = card.querySelector('[role="img"]');
      if (ring) rows.set(row, [...(rows.get(row) || []), Math.round(ring.getBoundingClientRect().top)]);
    }
    assert([...rows.values()].every(tops => Math.max(...tops)-Math.min(...tops) <= 2), 'Native quota circles stay aligned within each grid row');
    const original = await invoke('fleet_request', {target:null, argv:['job','list']});
    assert(original.length === 1, 'Real Rust IPC reads existing queue');
    const detail = await invoke('fleet_request', {target:null, argv:['job','get', original[0].id]});
    assert(detail.result === 'Preserved report from legacy database', 'Real Rust IPC preserves existing result');
    let refused = false;
    try { await invoke('fleet_request', {target:null, argv:['work','--once']}); } catch { refused = true; }
    assert(refused, 'WebView cannot start a worker');
    refused = false;
    try { await invoke('open_login_url', {url:'https://claude.com.attacker.invalid/'}); } catch { refused = true; }
    assert(refused, 'Native bridge rejects unofficial login URLs');
    // Keep overview visible long enough for an actual window capture.
    await delay(13000);
    await click('Claude');
    await wait(() => document.querySelectorAll('article.card').length === 2, 'Claude provider filter');
    assert([...document.querySelectorAll('article.card')].some(card => card.textContent.includes('team')), 'Provider filter retains the separate managed Claude profile');
    await click('Alle Accounts');
    const search = await wait(() => document.querySelector('[aria-label="Accounts durchsuchen"]'), 'search');
    setInput(search, 'nothing-matches-native-fixture');
    await wait(() => document.body.textContent.includes('Keine passenden Accounts'), 'empty search state');
    assert(document.querySelectorAll('article.card').length === 0, 'Search empty state hides unrelated cards');
    setInput(search, '');
    await wait(() => document.querySelectorAll('article.card').length >= 3, 'clear search');
    const details = [...document.querySelectorAll('button')].find(b => b.getAttribute('aria-label')?.startsWith('Details zu '));
    details.click();
    await wait(() => document.body.textContent.includes('Gemeldete Limits'), 'account details');
    assert(document.body.textContent.includes('Profil'), 'Account details show native profile metadata');
    await click('Zurück');
    await click('Account hinzufügen');
    await wait(() => document.querySelector('#login-name'), 'native login form');
    assert(document.querySelector('#login-name') !== null, 'Integrated native login form is reachable');
    assert(!document.body.textContent.includes('Neuer Auftrag'), 'Desktop does not add a task composer');
    await click('Zurück');
    const showAll = [...document.querySelectorAll('label')].find(label => label.textContent.trim() === 'Alle Profile anzeigen')?.querySelector('input');
    assert(showAll !== null && showAll !== undefined, 'All-profiles control available');
    if (!showAll.checked) showAll.click();
    await click('login-codex anmelden');
    await click('Anmeldung starten');
    const device = await wait(() => document.querySelector('#device-code'), 'real native device-code login');
    assert(device.value === 'ABCD-EFGHI', 'Native Codex device code reaches the actual UI');
    assert(button('Im Browser anmelden') !== undefined, 'Official login browser action is available');
    await click('Anmeldung abbrechen');
    await wait(() => button('Erneut versuchen'), 'native login cancellation');
    let profiles = await invoke('fleet_request', {target:null, argv:['profile','list']});
    assert(!profiles.find(p => p.name === 'login-codex').enabled, 'Cancelled native login leaves the account disabled');
    await click('Zurück');
    await click('login-claude anmelden');
    await click('Anmeldung starten');
    const code = await wait(() => document.querySelector('#login-code'), 'real native Claude code input');
    assert(code.type === 'password', 'Native Claude authorization input is masked');
    setInput(code, 'fixture-rejected-code');
    await click('Anmeldung abschließen');
    await wait(() => document.querySelector('.login-message')?.textContent.includes('nicht akzeptiert'), 'safe native Claude rejection feedback');
    const corrected = await wait(() => document.querySelector('#login-code:not(:disabled)'), 'retryable native Claude code input');
    assert(corrected.type === 'password', 'Rejected native code returns a masked editable input');
    assert(document.body.textContent.includes('vollständigen Code'), 'Native rejection explains how to retry');
    assert(!document.body.textContent.includes('fixture-rejected-code'), 'Native rejection never exposes the submitted code');
    profiles = await invoke('fleet_request', {target:null, argv:['profile','list']});
    assert(!profiles.find(p => p.name === 'login-claude').enabled, 'Rejected native login does not enable the profile');
    assert(button('Zur Übersicht') === undefined, 'Rejected native login is not reported as success');
    setInput(corrected, 'fixture-authorized-code');
    await click('Anmeldung abschließen');
    await wait(() => button('Zur Übersicht'), 'provider-confirmed native Claude login');
    profiles = await invoke('fleet_request', {target:null, argv:['profile','list']});
    assert(Boolean(profiles.find(p => p.name === 'login-claude').enabled), 'Provider-confirmed Claude login enables the existing profile');
    await click('Zur Übersicht');
    const finalAccounts = await invoke('fleet_request', {target:null, argv:['overview','--refresh']});
    assert(finalAccounts.accounts.filter(a => a.auth_mode === 'native_default').length === 1, 'Additional native login leaves exactly one connected default reference');
    assert(finalAccounts.accounts.find(a => a.auth_mode === 'native_default')?.connected, 'Additional Claude login preserves the original default CLI authentication');
    await invoke('test_report', {result:{passed:true, platform:'macOS WKWebView + Rust IPC', checks, viewport:{width:innerWidth,height:innerHeight}}});
  } catch (error) {
    await invoke('test_report', {result:{passed:false, checks, error:String(error), text:document.body.innerText.slice(0,6000)}});
  }
})();
