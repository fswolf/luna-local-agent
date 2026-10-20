// Floating windows for the debug page (the debug panel, the pose studio):
// drag by the title bar, resize from the corner, ▾ folds it to its title bar,
// – tucks it into the dock at the bottom left (click its tab to bring it
// back). Where each one was, how big, folded or tucked away: all remembered.

const load = k => { try { return JSON.parse(localStorage.getItem('luna.panel.' + k)); } catch (_) { return null; } };
const save = (k, v) => { try { localStorage.setItem('luna.panel.' + k, JSON.stringify(v)); } catch (_) {} };

function dock() {
  let d = document.getElementById('dock');
  if (!d) {
    d = Object.assign(document.createElement('div'), { id: 'dock' });
    document.body.appendChild(d);
  }
  return d;
}

// panel: the window; bar: its title bar; key: what to remember it as
// ('box' for the debug panel, so its old saved place still counts)
export function makeWindow(panel, bar, key, title) {
  const pre = key === 'box' ? '' : key + '.';
  const box = load(key === 'box' ? 'box' : key + '.box');
  if (box) Object.assign(panel.style, { left: box.left, top: box.top, width: box.width, height: box.height });
  const keep = () => {
    if (panel.classList.contains('folded') || panel.classList.contains('tucked')) return;   // not its real size
    save(key === 'box' ? 'box' : key + '.box', { left: panel.style.left, top: panel.style.top,
                                                  width: panel.offsetWidth + 'px', height: panel.offsetHeight + 'px' });
  };
  new ResizeObserver(keep).observe(panel);

  // the buttons, at the right of the title bar
  const btns = Object.assign(document.createElement('span'), { className: 'wbtns' });
  const fold = Object.assign(document.createElement('button'), { textContent: '▾', title: 'fold to the title bar' });
  const tuck = Object.assign(document.createElement('button'), { textContent: '–', title: 'tuck into the dock (bottom left)' });
  btns.append(fold, tuck);
  bar.appendChild(btns);
  const tab = Object.assign(document.createElement('button'), { textContent: title, className: 'docktab', title: 'bring it back' });

  let height = '';
  function setFolded(on) {
    if (on && !panel.classList.contains('folded')) { height = panel.style.height; panel.style.height = ''; }
    if (!on && panel.classList.contains('folded')) panel.style.height = height || panel.style.height;
    panel.classList.toggle('folded', on);
    fold.textContent = on ? '▸' : '▾';
    save(pre + 'folded', on);
  }
  function setTucked(on) {
    panel.classList.toggle('tucked', on);
    if (on) dock().appendChild(tab); else tab.remove();
    save(pre + 'tucked', on);
  }
  for (const b of [fold, tuck]) b.addEventListener('pointerdown', e => e.stopPropagation());   // not a drag
  fold.onclick = () => setFolded(!panel.classList.contains('folded'));
  tuck.onclick = () => setTucked(true);
  tab.onclick = () => setTucked(false);
  if (load(pre + 'folded')) setFolded(true);
  if (load(pre + 'tucked')) setTucked(true);

  bar.addEventListener('pointerdown', e => {
    if (e.target.closest('button, input, select')) return;
    const x0 = e.clientX - panel.offsetLeft, y0 = e.clientY - panel.offsetTop;
    bar.setPointerCapture(e.pointerId);
    const move = ev => {
      panel.style.left = Math.max(0, Math.min(innerWidth - 60, ev.clientX - x0)) + 'px';
      panel.style.top = Math.max(0, Math.min(innerHeight - 30, ev.clientY - y0)) + 'px';
    };
    const up = () => { bar.removeEventListener('pointermove', move); keep(); };
    bar.addEventListener('pointermove', move);
    bar.addEventListener('pointerup', up, { once: true });
  });
  for (const d of panel.querySelectorAll('details[data-key]')) {
    d.open = !!load('open.' + d.dataset.key);
    d.addEventListener('toggle', () => save('open.' + d.dataset.key, d.open));
  }
  return { fold: setFolded, tuck: setTucked, show() { setTucked(false); setFolded(false); } };
}
