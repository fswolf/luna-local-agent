// Her header, the same on every page the live monitor serves (web/livefeed.py
// puts this script at the top of each one): her logo opening every page, her
// name and mood, what she's doing in the middle, and Online opening what she's
// running on. Served by web/chat_web.py with the page list filled in.
// The chat page feeds it from its own updates (lunaHead.update); anywhere
// else it keeps itself up to date from /chat/state.
(() => {
  const NAV = __NAV__;
  const here = location.pathname;
  const css = `
#luna-head,#luna-head *{box-sizing:border-box}
#luna-head{flex:none;position:relative;z-index:50;border-bottom:1px solid #3a2d55;background:#1a1328;color:#ece6f7;
font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;text-align:left}
#luna-head button{all:unset;box-sizing:border-box;cursor:pointer}
#luna-head .lh-top{max-width:860px;margin:0 auto;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:12px;
padding:10px 16px;position:relative}
#luna-head .lh-id{display:flex;align-items:center;gap:12px;min-width:0}
#luna-head .lh-name{color:#ff87d7;font-size:19px;font-weight:700}
#luna-head .lh-logo{flex:none;width:44px;height:44px;border-radius:50%;background:#fff;box-shadow:0 0 0 2px transparent;transition:box-shadow .15s}
#luna-head .lh-logo img{width:100%;height:100%;display:block;border-radius:50%}
#luna-head .lh-logo:hover,#luna-head .lh-logo[aria-expanded=true]{box-shadow:0 0 0 2px #ff87d7}
#luna-head .lh-mood{color:#a49bc0;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
#luna-head .lh-mood b{color:#ff87d7;font-weight:500}
#luna-head .lh-status{justify-self:center;color:#ece6f7;font-size:12.5px;background:#2a2040;border:1px solid #3a2d55;border-radius:999px;
padding:2px 10px;white-space:nowrap;text-decoration:none}
#luna-head .lh-status:empty{visibility:hidden}
#luna-head a.lh-status:hover{border-color:#ff87d7}
#luna-head .lh-online{justify-self:end;display:flex;align-items:center;gap:7px;border:1px solid transparent;border-radius:999px;
padding:4px 11px;font-size:13px}
#luna-head .lh-online:hover,#luna-head .lh-online[aria-expanded=true]{background:#2a2040;border-color:#3a2d55}
#luna-head .lh-online i{width:9px;height:9px;border-radius:50%;background:#7be0a8;box-shadow:0 0 6px #7be0a8}
#luna-head.away .lh-online i{background:#ff8fa3;box-shadow:0 0 6px #ff8fa3}
#luna-head .lh-drop{position:absolute;top:58px;z-index:60;background:#1a1328;border:1px solid #3a2d55;border-radius:14px;
box-shadow:0 12px 32px #0009;display:none;max-width:min(440px,calc(100vw - 32px));max-height:calc(100vh - 80px);overflow-y:auto}
#luna-head .lh-drop.on{display:block}
#luna-head .lh-pages{left:16px;min-width:250px;padding:6px 0}
#luna-head .lh-pages .lh-h{padding:8px 18px 10px;border-bottom:1px solid #3a2d55;margin-bottom:6px;color:#ff87d7;font-size:18px;font-weight:700}
#luna-head .lh-pages a,#luna-head .lh-pages button{display:flex;align-items:center;gap:14px;width:100%;padding:10px 18px;color:#ece6f7;
text-decoration:none;font-size:15px}
#luna-head .lh-pages a:hover,#luna-head .lh-pages button:hover{background:#2a2040}
#luna-head .lh-pages hr{border:0;border-top:1px solid #3a2d55;margin:6px 0;height:0}
#luna-head .lh-pages svg{width:20px;height:20px;flex:none;fill:none;stroke:#a49bc0;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
#luna-head .lh-pages .on{color:#ff87d7}#luna-head .lh-pages .on svg{stroke:#ff87d7}
#luna-head .lh-info{right:16px;min-width:260px;padding:12px 18px}
#luna-head .lh-info table{border-collapse:collapse;font-size:13px;width:100%}
#luna-head .lh-info td{padding:2px 0;vertical-align:top;border:0;background:none}
#luna-head .lh-info td:first-child{color:#a49bc0;padding-right:14px;white-space:nowrap}
#luna-head .lh-info td:last-child{overflow-wrap:anywhere}
#luna-ctx{position:fixed;z-index:9999;min-width:180px;background:#1a1328;border:1px solid #3a2d55;border-radius:10px;
box-shadow:0 10px 28px #0009;padding:5px 0;font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;display:none}
#luna-ctx.on{display:block}
#luna-ctx button{all:unset;box-sizing:border-box;display:flex;justify-content:space-between;gap:24px;width:100%;padding:7px 14px;
color:#ece6f7;cursor:pointer}
#luna-ctx button:hover:not([disabled]){background:#2a2040}
#luna-ctx button[disabled]{color:#5d5378;cursor:default}
#luna-ctx kbd{font:12px system-ui,sans-serif;color:#a49bc0}
@media print{#luna-head,#luna-ctx{display:none}}`;
  const ICONS = {
    Chat: '<path d="M4 5h16v11H9l-5 4z"/>',
    Portrait: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>',
    'Pose studio': '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    Settings: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    'Live monitor': '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
    Thoughts: '<path d="M7 16a4 4 0 0 1-.5-8A5 5 0 0 1 16 6.5a4 4 0 0 1 1 9.5z"/><circle cx="8" cy="20" r="1.2"/>',
    Memory: '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h11"/>',
    Exit: '<path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4M10 16l-4-4 4-4M6 12h10"/>',
    Help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17h.01"/>',
  };
  const OTHER = '<circle cx="12" cy="12" r="8"/><path d="M12 8v8M8 12h8"/>';
  const onChat = here.startsWith('/chat/');

  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);
  const head = document.createElement('div');
  head.id = 'luna-head';
  head.innerHTML = `<div class=lh-top>
    <div class=lh-id><button class=lh-logo title="her pages" aria-haspopup=true aria-expanded=false><img src="/chat/logo.png" alt="Luna"></button>
    <span class=lh-name>Luna</span><span class=lh-mood title="her mood right now">mood: <b></b></span></div>
    <${onChat ? 'span' : 'a href="/chat/" title="to the chat"'} class=lh-status></${onChat ? 'span' : 'a'}>
    <button class=lh-online title="what she's running on" aria-haspopup=true aria-expanded=false><i></i><span>Online</span></button>
    <div class="lh-drop lh-pages" role=menu><div class=lh-h>Luna</div></div>
    <div class="lh-drop lh-info"><table></table></div></div>`;
  const at = document.currentScript;      // right after <body>, so the header comes first
  if (at && at.parentNode === document.body) at.after(head); else document.body.prepend(head);
  // edge to edge and flush with the top, even on a page whose body has padding
  // or a max width (the memory page)
  function fit() {
    head.style.margin = head.style.width = '';
    const r = head.getBoundingClientRect(), page = document.documentElement.clientWidth;
    if (r.left || r.width !== page) { head.style.marginLeft = -r.left + 'px'; head.style.width = page + 'px'; }
    const top = r.top + scrollY;
    if (top) { head.style.marginTop = -top + 'px'; head.style.marginBottom = top + 'px'; }   // keep the page's own space under it
  }
  fit();
  addEventListener('resize', fit);
  const $ = s => head.querySelector(s);
  const pages = $('.lh-pages'), info = $('.lh-info'), logo = $('.lh-logo'), online = $('.lh-online');

  // --- her pages ------------------------------------------------------------
  const say = text => fetch('/chat/say', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                         body: JSON.stringify({text})}).catch(() => {});
  function item(label, el, on) {
    el.innerHTML = `<svg viewBox="0 0 24 24">${ICONS[label] || OTHER}</svg>`;
    el.append(label); el.setAttribute('role', 'menuitem');
    if (on) el.className = 'on';
    pages.appendChild(el);
    return el;
  }
  // her windows (chat, portrait, pose studio, live monitor), a line, her pages, help last,
  // a line, then Exit
  const rule = () => pages.appendChild(document.createElement('hr'));
  const own = n => n[0] === 'Chat' || n[2];       // the ones with windows of their own
  const order = [...NAV.filter(own), ...NAV.filter(n => !own(n) && n[0] !== 'Help'), ...NAV.filter(n => n[0] === 'Help')];
  const lastOwn = NAV.filter(own).pop()[0];
  for (const [label, href, command, title] of order) {
    if (command) {      // portrait, pose studio and the live monitor open windows of their own
      const b = item(label, document.createElement('button'));
      b.title = title || '';
      b.onclick = () => { say(command); open_(pages, false); };
    } else {
      const path = href.split('?')[0];
      item(label, Object.assign(document.createElement('a'), {href}), path === '/' ? here === '/' : here.startsWith(path));
    }
    if (label === lastOwn) rule();
  }
  rule();
  // Exit: /quit, the same as typing it; a second click within a few seconds, so a slip doesn't end her
  const exit = item('Exit', document.createElement('button'));
  exit.title = 'quit Luna';
  let armed = null;
  exit.onclick = ev => {
    ev.stopPropagation();
    if (armed) { clearTimeout(armed); say('/quit'); exit.lastChild.textContent = 'Exit'; armed = null; open_(pages, false); return; }
    exit.lastChild.textContent = 'Exit - click again to quit her';
    armed = setTimeout(() => { exit.lastChild.textContent = 'Exit'; armed = null; }, 4000);
  };
  function open_(drop, on) {
    drop.classList.toggle('on', on);
    (drop === pages ? logo : online).setAttribute('aria-expanded', on);
  }
  logo.onclick = ev => { ev.stopPropagation(); open_(info, false); open_(pages, !pages.classList.contains('on')); };
  online.onclick = ev => { ev.stopPropagation(); open_(pages, false); open_(info, !info.classList.contains('on')); };
  addEventListener('click', ev => {
    if (!pages.contains(ev.target)) open_(pages, false);
    if (!info.contains(ev.target)) open_(info, false);
  });
  addEventListener('keydown', ev => { if (ev.key === 'Escape') { open_(pages, false); open_(info, false); } });

  // --- what she's doing -----------------------------------------------------
  function update(s) {
    const name = s.name || 'Luna';
    $('.lh-name').textContent = $('.lh-h').textContent = name;
    $('.lh-status').textContent = s.status && s.status !== 'Idle' ? s.status : '';
    $('.lh-mood b').textContent = s.mood || '';
    $('.lh-mood').style.visibility = s.mood ? '' : 'hidden';
    $('.lh-info table').replaceChildren(...(s.rows || []).map(([k, val]) => {
      const tr = document.createElement('tr');
      tr.append(Object.assign(document.createElement('td'), {textContent: k}),
                Object.assign(document.createElement('td'), {textContent: val}));
      return tr;
    }));
  }
  function reachable(yes) {
    head.classList.toggle('away', !yes);
    $('.lh-online span').textContent = yes ? 'Online' : 'Offline';
  }
  window.lunaHead = {update, reachable, fed: false};

  // --- right click: copy, paste, select all, in her colours ------------------
  // Shift + right click still gives the browser's own menu.
  const ctx = document.createElement('div');
  ctx.id = 'luna-ctx';
  const mac = /Mac/.test(navigator.platform);
  const key = k => (mac ? '⌘' : 'Ctrl+') + k;
  ctx.innerHTML = `<button data-do=link>Copy link</button><button data-do=copy>Copy<kbd>${key('C')}</kbd></button>
    <button data-do=paste>Paste<kbd>${key('V')}</kbd></button>
    <button data-do=all>Select all<kbd>${key('A')}</kbd></button>`;
  // last in the body, once the page is all there (now, the body is only this script and the header)
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', () => document.body.appendChild(ctx));
  else document.body.appendChild(ctx);
  let field = null, link = null;      // the text box or the link right-clicked, if any
  const editable = el => el && (el.isContentEditable ||
    (el.tagName === 'TEXTAREA') || (el.tagName === 'INPUT' && /^(text|search|url|tel|password)$/i.test(el.type)));
  const picked = () => field && !field.isContentEditable
    ? field.value.slice(field.selectionStart, field.selectionEnd) : String(getSelection());
  const hide = () => ctx.classList.remove('on');
  addEventListener('contextmenu', ev => {
    if (ev.shiftKey) return;
    ev.preventDefault();
    field = editable(ev.target) ? ev.target : null;
    link = ev.target.closest && ev.target.closest('a[href]');
    ctx.querySelector('[data-do=link]').style.display = link ? '' : 'none';
    ctx.querySelector('[data-do=copy]').disabled = !picked();
    ctx.querySelector('[data-do=paste]').disabled = !field || field.readOnly || field.disabled || !navigator.clipboard;
    ctx.classList.add('on');
    const w = ctx.offsetWidth, h = ctx.offsetHeight;
    ctx.style.left = Math.min(ev.clientX, innerWidth - w - 4) + 'px';
    ctx.style.top = Math.min(ev.clientY, innerHeight - h - 4) + 'px';
  });
  addEventListener('mousedown', ev => { if (!ctx.contains(ev.target)) hide(); }, true);
  addEventListener('keydown', ev => { if (ev.key === 'Escape') hide(); });
  addEventListener('blur', hide);
  addEventListener('scroll', hide, true);
  ctx.addEventListener('mousedown', ev => ev.preventDefault());   // keep the selection and the caret where they are
  ctx.addEventListener('click', async ev => {
    const b = ev.target.closest('button');
    if (!b || b.disabled) return;
    hide();
    if (b.dataset.do === 'copy' || b.dataset.do === 'link') {
      const text = b.dataset.do === 'link' ? link.href : picked();
      try { await navigator.clipboard.writeText(text); } catch (e) { document.execCommand('copy'); }
    } else if (b.dataset.do === 'paste') {
      let text = '';
      try { text = await navigator.clipboard.readText(); } catch (e) { return; }   // the browser said no
      field.focus();
      // insertText keeps Ctrl+Z working and fires input, so the chat box grows
      if (!document.execCommand('insertText', false, text) && !field.isContentEditable) {
        field.setRangeText(text, field.selectionStart, field.selectionEnd, 'end');
        field.dispatchEvent(new Event('input', {bubbles: true}));
      }
    } else if (field) {
      field.focus();
      field.isContentEditable ? document.execCommand('selectAll') : field.select();
    } else {
      // the page's own content, never her header: the conversation in the chat,
      // a page's main part, else everything after the header
      const area = document.querySelector('#list') || document.querySelector('main');
      const range = document.createRange();
      if (area) range.selectNodeContents(area);
      else { range.setStartAfter(head); range.setEndBefore(ctx); }      // the menu is last in the body
      getSelection().removeAllRanges();
      getSelection().addRange(range);
    }
  });

  // anywhere but the chat: keep up by itself, waiting for a change each time
  addEventListener('DOMContentLoaded', async () => {
    if (window.lunaHead.fed) return;
    let v = null;
    for (;;) {
      try {
        const r = await fetch('/chat/state?head=1' + (v === null ? '' : `&v=${v}`), {cache: 'no-store'});
        if (!r.ok) throw new Error(r.status);
        const s = await r.json();
        v = s.v; update(s); reachable(true);
      } catch (e) {
        reachable(false);
        await new Promise(res => setTimeout(res, 3000));
      }
    }
  });
})();
