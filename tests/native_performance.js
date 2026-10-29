// Injected by the debug-only Tauri hook; all requests use the actual Rust IPC.
(async () => {
  const config = window.__FLEET_PERFORMANCE_CONFIG__;
  const intervalMs = 20;
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const invoke = (command, args = {}) => window.__TAURI_INTERNALS__.invoke(command, args);
  const checks = [];
  const assert = (value, message) => { if (!value) throw new Error(message); checks.push(message); };
  const quantile = (values, fraction) => [...values].sort((a, b) => a - b)[Math.ceil(values.length * fraction) - 1];
  const summarize = values => ({count:values.length, p95_ms:quantile(values,.95), max_ms:Math.max(...values)});
  const acceptable = stats => stats.count >= 3 && stats.p95_ms < 100 && stats.max_ms < 500;
  const wait = async (read, label) => {
    const until = performance.now() + 15000;
    while (performance.now() < until) { if (read()) return; await pause(30); }
    throw new Error('Timed out: ' + label);
  };
  const button = label => [...document.querySelectorAll('button')].find(item => item.textContent.trim() === label && item.getBoundingClientRect().width);

  // Include the first timer after completion: otherwise a synchronous block could
  // finish before its delayed callback runs and falsely appear responsive.
  const measure = async task => {
    const timerLag = [];
    const frameIntervals = [];
    let lastTimer = performance.now();
    let lastFrame = null;
    let active = true;
    let frameId;
    const timerId = setInterval(() => {
      const now = performance.now();
      timerLag.push(Math.max(0, now - lastTimer - intervalMs));
      lastTimer = now;
    }, intervalMs);
    const frame = now => {
      if (lastFrame !== null) frameIntervals.push(now - lastFrame);
      lastFrame = now;
      if (active) frameId = requestAnimationFrame(frame);
    };
    frameId = requestAnimationFrame(frame);
    const started = performance.now();
    try {
      const result = await task();
      const taskMs = performance.now() - started;
      await pause(intervalMs * 2);
      return {task_ms:taskMs, timer_lag_ms:timerLag, frame_intervals_ms:frameIntervals,
        timer:summarize(timerLag), frames:summarize(frameIntervals), result};
    } finally {
      active = false;
      clearInterval(timerId);
      cancelAnimationFrame(frameId);
    }
  };

  let control;
  const requests = [];
  try {
    await wait(() => button('Codex') && document.querySelector('main'), 'actual native application');
    assert(document.body.textContent.includes('Agent Fleet'), 'Actual native application rendered');
    assert(document.visibilityState === 'visible', 'Native WebView is visible during measurement');
    const initial = await invoke('initial_config');
    assert(initial.version === config.expectedVersion, 'Native application version matches selected CLI');
    await pause(300); // Startup is deliberately outside the measured window.

    control = await measure(async () => {
      await pause(80);
      const until = performance.now() + 700;
      while (performance.now() < until) { /* Deliberate main-thread blocking control. */ }
    });
    assert(!acceptable(control.timer) && control.timer.max_ms >= 500,
      'The same timer instrument rejects the deliberate main-thread block');
    await pause(200);

    for (let index = 0; index < 3; index += 1) {
      const label = ['Codex', 'Claude', 'Alle Accounts'][index];
      let interactionMs = null;
      let interaction;
      const sample = await measure(async () => {
        let settled = false;
        const pending = invoke('fleet_request', {target:config.remote, argv:['status']})
          .finally(() => { settled = true; });
        interaction = (async () => {
          await pause(100);
          assert(!settled, 'Real delayed SSH request remains in flight during interaction ' + (index + 1));
          const started = performance.now();
          button(label).click();
          await wait(() => button(label).getAttribute('aria-current') === 'page', 'provider filter response');
          interactionMs = performance.now() - started;
          assert(!settled, 'Visible React filter changed before SSH completed ' + (index + 1));
        })();
        const [data] = await Promise.all([pending, interaction]);
        return {version:data.version, accounts:Array.isArray(data.accounts) ? data.accounts.length : null};
      });
      sample.interaction_ms = interactionMs;
      requests.push(sample);
      assert(sample.result.version === config.expectedVersion, 'Real remote Rust status reply received ' + (index + 1));
      assert(sample.task_ms >= config.delayMs, 'Observed real SSH delay is at least the configured delay ' + (index + 1));
      assert(sample.timer.count >= 50 && sample.frames.count >= 50, 'Timers and frames progressed throughout delayed request ' + (index + 1));
      assert(acceptable(sample.timer), 'Event-loop timer budget passed ' + (index + 1));
      assert(acceptable(sample.frames), 'Native frame interval budget passed ' + (index + 1));
      assert(sample.interaction_ms < 500, 'Visible filter interaction stayed below 500 ms ' + (index + 1));
    }
    const timerLag = requests.flatMap(sample => sample.timer_lag_ms);
    const frameIntervals = requests.flatMap(sample => sample.frame_intervals_ms);
    const timer = summarize(timerLag);
    assert(acceptable(timer), 'Combined native event-loop p95/max budgets passed');
    assert(acceptable(summarize(frameIntervals)), 'Combined native frame p95/max budgets passed');
    await invoke('test_report', {result:{passed:true, platform:'macOS WKWebView + actual Rust IPC + real SSH',
      quantile:'nearest-rank ceil(p*n), samples sorted ascending', interval_ms:intervalMs,
      measurement_window:'request start through first scheduled callbacks after completion; excludes startup',
      control, requests, timer, frames:summarize(frameIntervals), checks}});
  } catch (error) {
    await invoke('test_report', {result:{passed:false, error:String(error), checks, control, requests}});
  }
})();
