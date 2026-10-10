// Picks the renderer for whatever model config.json names:
//   *.model3.json  -> Live2D (live2d.js)
//   *.vrm / *.glb  -> 3D (portrait.js)

const cfg = await fetch('config.json').then(r => r.json()).catch(() => ({}));
const model = cfg.model || '';
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

if (model.endsWith('.model3.json')) {
  // Live2D's Cubism Core: a local copy if there is one (portrait/vendor/,
  // get it with get_cubism_core.sh for offline use), otherwise Live2D's CDN.
  try {
    await script('vendor/live2dcubismcore.min.js');
  } catch (_) {
    try {
      await script('https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js');
    } catch (e) {
      note.textContent = "couldn't load Live2D's Cubism Core - run portrait/vendor/get_cubism_core.sh";
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
