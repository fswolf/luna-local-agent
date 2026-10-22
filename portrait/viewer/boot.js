// Picks the renderer for whatever model config.json names:
//   *.model3.json  -> Live2D (live2d.js)
//   *.vrm / *.glb  -> 3D (portrait.js)

const cfg = await fetch('config.json' + location.search).then(r => r.json()).catch(() => ({}));
const model = cfg.model || '';

// What's behind her (portrait.background): your pick in /settings, live.
// "" her usual gradient, "none" see-through, a colour, or a picture in
// portrait/backgrounds/. ?bg=transparent (OBS) and the fans keep their own.
window.lunaBackground = value => {
  const b = document.body, v = String(value || '').trim();
  b.classList.remove('custom-bg', 'solid', 'clear');
  b.style.removeProperty('--user-bg');
  if (!v) return;
  b.classList.add('custom-bg');
  if (v === 'none') b.classList.add('clear');
  else if (/^#[0-9a-f]{3}([0-9a-f]{3})?$/i.test(v)) { b.classList.add('solid'); b.style.setProperty('--user-bg', v); }
  else b.style.setProperty('--user-bg', `url("backgrounds/${encodeURIComponent(v)}")`);
};
window.lunaBackground(cfg.background);
const note = document.getElementById('note');

if (!model) {
  note.textContent = 'no portrait model - put one in portrait/models/ and set portrait.model (see docs/portrait.md)';
  throw new Error('no portrait model');
}

function script(src) {
  return new Promise((ok, fail) => {
    const s = document.createElement('script');
    s.src = src;
    s.onload = ok;
    s.onerror = fail;
    document.head.appendChild(s);
  });
}

// The debug page: a picker for every model in portrait/models. It
// previews (?model=...); it doesn't change which one Luna uses.
if (new URLSearchParams(location.search).get('debug')) {
  document.body.classList.add('debug');   // now, so a model that won't load can still be switched away from
  panelLayout();
  const pick = document.getElementById('dmodel');
  fetch('models.json').then(r => r.json()).then(list => {
    for (const m of list) pick.add(new Option(m.replace(/^models\//, ''), m, false, m === model));
    pick.onchange = () => setParam('model', pick.value);
  }).catch(() => {});

  // view: crop, background, hologram, demo - each one a page option
  const q = new URLSearchParams(location.search), box = document.getElementById('dview');
  const frame = document.createElement('select');
  for (const [v, label] of [['', 'bust'], ['face', 'face'], ['full', 'full body']])
    frame.add(new Option(label, v, false, (q.get('frame') || '') === v));
  frame.onchange = () => {   // live once she's up: no reload, so the pose studio and windows stay as they are
    if (!window.portrait?.setFrame) return setParam('frame', frame.value);
    window.portrait.setFrame(frame.value || 'bust');
    const q = new URLSearchParams(location.search);
    if (frame.value) q.set('frame', frame.value); else q.delete('frame');
    history.replaceState(null, '', '?' + q.toString());
  };
  box.appendChild(frame);
  const toggle = (label, key, on) => {
    const b = document.createElement('button');
    b.textContent = `${label}: ${on ? 'on' : 'off'}`;
    if (on) b.style.borderColor = 'var(--accent)';
    b.onclick = () => setParam(key, on ? '' : (key === 'bg' ? 'transparent' : '1'));
    box.appendChild(b);
  };
  toggle('hologram', 'holo', q.get('holo') === '1');
  toggle('see-through', 'bg', q.get('bg') === 'transparent');
  toggle('demo', 'demo', !!q.get('demo'));
}

// The debug panel: drag it by its title bar, resize it from its corner,
// fold it or tuck it into the dock (windows.js). Where it was comes back on reload.
async function panelLayout() {
  const { makeWindow } = await import('./windows.js');
  makeWindow(document.getElementById('debug'), document.getElementById('dbar'), 'box', 'debug');
}

function setParam(key, value) {
  const q = new URLSearchParams(location.search);
  if (value) q.set(key, value); else q.delete(key);
  location.search = q.toString();
}

// h hides and shows the debug windows, to see the model unobstructed (not while typing)
addEventListener('keydown', e => {
  if (e.key === 'h' && new URLSearchParams(location.search).get('debug') && !/^(SELECT|INPUT|TEXTAREA)$/.test(e.target.tagName))
    document.body.classList.toggle('debug');
});

if (model.endsWith('.model3.json')) {
  // Live2D's Cubism Core: a local copy if there is one (portrait/viewer/vendor/,
  // get it with get_cubism_core.sh for offline use), otherwise Live2D's CDN.
  try {
    await script('vendor/live2dcubismcore.min.js');
  } catch (_) {
    try {
      await script('https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js');
    } catch (e) {
      note.textContent = "couldn't load Live2D's Cubism Core - run portrait/viewer/vendor/get_cubism_core.sh";
      throw e;
    }
  }
  await import('./live2d.js');
} else {
  await import('./portrait.js');
}

// portrait.model named a file that isn't there and the server fell back
// to Sigewinne: say so for a few seconds, once the model is up.
if (cfg.missing) {
  note.textContent = `couldn't find ${cfg.missing} - showing the default model`;
  note.classList.remove('hidden');
  setTimeout(() => note.classList.add('hidden'), 8000);
}
