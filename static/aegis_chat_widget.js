/**
 * AEGIS Chat Widget — Observatoire ORBITAL-CHOHRA
 * Floating chatbot powered by Claude AI (Anthropic)
 */
(function () {
  'use strict';

  if (window.__aegisChatLoaded) return;
  window.__aegisChatLoaded = true;

  /* ── Styles ─────────────────────────────────────────── */
  const CSS = `
#aegis-fab {
  position: fixed; bottom: 28px; right: 28px; z-index: 9999;
  width: 58px; height: 58px; border-radius: 50%;
  background: linear-gradient(135deg, #4a0080 0%, #9b30d0 100%);
  border: 2px solid #d4a0ff; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; box-shadow: 0 0 20px rgba(212,160,255,0.5);
  transition: transform .2s, box-shadow .2s;
  user-select: none;
}
#aegis-fab:hover { transform: scale(1.1); box-shadow: 0 0 30px rgba(212,160,255,0.8); }
#aegis-fab .aegis-fab-label {
  position: absolute; bottom: -20px; left: 50%; transform: translateX(-50%);
  font-size: 9px; color: #d4a0ff; font-family: 'Orbitron', monospace;
  letter-spacing: 1px; white-space: nowrap;
}

#aegis-chat-window {
  position: fixed; bottom: 100px; right: 28px; z-index: 9998;
  width: 350px; height: 480px;
  background: #0a0d1a; border: 1px solid #d4a0ff;
  border-radius: 14px; display: none; flex-direction: column;
  box-shadow: 0 0 40px rgba(212,160,255,0.3), 0 8px 32px rgba(0,0,0,0.7);
  font-family: 'Inter', 'Segoe UI', sans-serif;
  overflow: hidden;
}
#aegis-chat-window.open { display: flex; }

.aegis-header {
  background: linear-gradient(90deg, #1a0030 0%, #2a0050 100%);
  border-bottom: 1px solid rgba(212,160,255,0.3);
  padding: 12px 14px; display: flex; align-items: center; gap: 10px;
  flex-shrink: 0;
}
.aegis-header-icon { font-size: 18px; }
.aegis-header-info { flex: 1; }
.aegis-header-title { font-size: 12px; color: #d4a0ff; font-weight: 700; letter-spacing: 2px; }
.aegis-header-sub { font-size: 9px; color: #8866aa; letter-spacing: 1px; margin-top: 2px; }
.aegis-header-dot { width: 8px; height: 8px; border-radius: 50%; background: #00ff88; box-shadow: 0 0 6px #00ff88; animation: pulse 2s infinite; }
.aegis-close { cursor: pointer; color: #8866aa; font-size: 16px; padding: 2px 6px; border-radius: 4px; transition: color .2s; }
.aegis-close:hover { color: #d4a0ff; }

.aegis-messages {
  flex: 1; overflow-y: auto; padding: 12px; display: flex;
  flex-direction: column; gap: 10px; scroll-behavior: smooth;
}
.aegis-messages::-webkit-scrollbar { width: 4px; }
.aegis-messages::-webkit-scrollbar-track { background: transparent; }
.aegis-messages::-webkit-scrollbar-thumb { background: rgba(212,160,255,0.3); border-radius: 2px; }

.aegis-msg {
  max-width: 88%; padding: 9px 13px; border-radius: 12px;
  font-size: 12px; line-height: 1.6; word-break: break-word;
}
.aegis-msg.user {
  align-self: flex-end;
  background: linear-gradient(135deg, #3a0060, #6a20a0);
  color: #f0e0ff; border-bottom-right-radius: 3px;
}
.aegis-msg.assistant {
  align-self: flex-start;
  background: rgba(212,160,255,0.08);
  border: 1px solid rgba(212,160,255,0.2);
  color: #d8c8f0; border-bottom-left-radius: 3px;
}
.aegis-msg.assistant .aegis-badge {
  display: inline-block; font-size: 8px; color: #9966cc;
  letter-spacing: 1px; margin-bottom: 4px;
}

.aegis-typing {
  align-self: flex-start; padding: 10px 14px;
  background: rgba(212,160,255,0.06); border: 1px solid rgba(212,160,255,0.15);
  border-radius: 12px; border-bottom-left-radius: 3px;
  display: none; align-items: center; gap: 5px;
}
.aegis-typing.show { display: flex; }
.aegis-typing span {
  width: 6px; height: 6px; border-radius: 50%;
  background: #d4a0ff; display: inline-block;
  animation: aegis-bounce 1.2s infinite;
}
.aegis-typing span:nth-child(2) { animation-delay: .2s; }
.aegis-typing span:nth-child(3) { animation-delay: .4s; }

.aegis-quick-btns {
  padding: 0 12px 10px; display: flex; gap: 6px; flex-wrap: wrap; flex-shrink: 0;
}
.aegis-quick-btn {
  font-size: 10px; padding: 5px 10px; border-radius: 20px;
  border: 1px solid rgba(212,160,255,0.35); background: rgba(212,160,255,0.06);
  color: #c0a0e0; cursor: pointer; transition: all .2s; white-space: nowrap;
}
.aegis-quick-btn:hover { background: rgba(212,160,255,0.18); color: #e8c8ff; border-color: #d4a0ff; }

.aegis-input-row {
  border-top: 1px solid rgba(212,160,255,0.2);
  padding: 10px 12px; display: flex; gap: 8px; align-items: center; flex-shrink: 0;
  background: rgba(10,5,25,0.8);
}
#aegis-input {
  flex: 1; background: rgba(212,160,255,0.07); border: 1px solid rgba(212,160,255,0.25);
  border-radius: 20px; color: #e8d8ff; font-size: 12px;
  padding: 8px 14px; outline: none; transition: border-color .2s;
  font-family: inherit;
}
#aegis-input::placeholder { color: #7755aa; }
#aegis-input:focus { border-color: #d4a0ff; }
#aegis-send {
  width: 34px; height: 34px; border-radius: 50%;
  background: linear-gradient(135deg, #6a20a0, #d4a0ff);
  border: none; cursor: pointer; display: flex; align-items: center;
  justify-content: center; font-size: 14px; flex-shrink: 0;
  transition: transform .2s, box-shadow .2s;
}
#aegis-send:hover { transform: scale(1.1); box-shadow: 0 0 12px rgba(212,160,255,0.6); }
#aegis-send:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }

@keyframes aegis-bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-6px)} }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

@media (max-width: 480px) {
  #aegis-chat-window { width: calc(100vw - 20px); right: 10px; bottom: 90px; height: 60vh; }
  #aegis-fab { bottom: 18px; right: 18px; }
}
`;

  /* ── Injecter CSS ────────────────────────────────────── */
  const style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);

  /* ── HTML ────────────────────────────────────────────── */
  const fab = document.createElement('div');
  fab.id = 'aegis-fab';
  fab.innerHTML = '🧠<span class="aegis-fab-label">AEGIS</span>';

  const win = document.createElement('div');
  win.id = 'aegis-chat-window';
  win.innerHTML = `
<div class="aegis-header">
  <div class="aegis-header-icon">🔭</div>
  <div class="aegis-header-info">
    <div class="aegis-header-title">AEGIS · IA ASTRONOMIQUE</div>
    <div class="aegis-header-sub">ORBITAL-CHOHRA · Tlemcen, Algérie</div>
  </div>
  <div class="aegis-header-dot"></div>
  <div class="aegis-close" id="aegis-close-btn">✕</div>
</div>
<div class="aegis-messages" id="aegis-messages">
  <div class="aegis-typing show" id="aegis-typing">
    <span></span><span></span><span></span>
  </div>
</div>
<div class="aegis-quick-btns" id="aegis-quick-btns">
  <button class="aegis-quick-btn" data-q="Où est l'ISS en ce moment ?">🛸 Où est l'ISS ?</button>
  <button class="aegis-quick-btn" data-q="Quelle est la météo spatiale actuelle ?">☀️ Météo spatiale ?</button>
  <button class="aegis-quick-btn" data-q="Décris l'image APOD du jour.">🌌 APOD du jour ?</button>
  <button class="aegis-quick-btn" data-q="Quelle nébuleuse est la plus proche de la Terre ?">🌀 Nébuleuse proche ?</button>
</div>
<div class="aegis-input-row">
  <input id="aegis-input" type="text" placeholder="Posez votre question astronomique…" maxlength="500" autocomplete="off">
  <button id="aegis-send">➤</button>
</div>
`;

  document.body.appendChild(fab);
  document.body.appendChild(win);

  /* ── State ───────────────────────────────────────────── */
  let history = [];
  let busy = false;

  /* ── DOM refs ────────────────────────────────────────── */
  const msgs    = document.getElementById('aegis-messages');
  const input   = document.getElementById('aegis-input');
  const sendBtn = document.getElementById('aegis-send');
  const typing  = document.getElementById('aegis-typing');

  /* ── Helpers ─────────────────────────────────────────── */
  function addMsg(role, text) {
    const el = document.createElement('div');
    el.className = 'aegis-msg ' + role;
    if (role === 'assistant') {
      el.innerHTML = '<div class="aegis-badge">🧠 AEGIS</div><div>' + escHtml(text) + '</div>';
    } else {
      el.textContent = text;
    }
    msgs.insertBefore(el, typing);
    msgs.scrollTop = msgs.scrollHeight;
    return el;
  }

  function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
  }

  function setTyping(show) {
    typing.className = 'aegis-typing' + (show ? ' show' : '');
    if (show) msgs.scrollTop = msgs.scrollHeight;
  }

  function setBusy(b) {
    busy = b;
    sendBtn.disabled = b;
    input.disabled = b;
  }

  /* ── Welcome message (after short delay) ────────────── */
  setTimeout(function () {
    setTyping(false);
    addMsg('assistant',
      'Bonjour ! Je suis AEGIS, votre assistant astronomique.\n' +
      'Posez-moi vos questions sur l\'univers, l\'ISS, les nébuleuses, ' +
      'les exoplanètes ou la météo spatiale… 🌌'
    );
  }, 800);

  /* ── Send message ────────────────────────────────────── */
  async function send(question) {
    const q = (question || input.value).trim();
    if (!q || busy) return;
    input.value = '';
    addMsg('user', q);
    setBusy(true);
    setTyping(true);
    // Hide quick buttons after first real interaction
    const qbtns = document.getElementById('aegis-quick-btns');
    if (qbtns) qbtns.style.display = 'none';

    try {
      const resp = await fetch('/api/aegis/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: q, history: history.slice(-6) })
      });
      const data = await resp.json();
      setTyping(false);
      const replyText = data.ok ? data.response : (data.error || 'Erreur de connexion à AEGIS.');
      addMsg('assistant', replyText);
      if (data.ok) {
        history.push({ role: 'user', content: q });
        history.push({ role: 'assistant', content: replyText });
        if (history.length > 12) history = history.slice(-12);
      }
    } catch (e) {
      setTyping(false);
      addMsg('assistant', 'Connexion impossible. Vérifiez votre réseau.');
    }
    setBusy(false);
  }

  /* ── Events ──────────────────────────────────────────── */
  fab.addEventListener('click', function () {
    win.classList.toggle('open');
    if (win.classList.contains('open')) {
      setTimeout(function () { input.focus(); }, 100);
    }
  });

  document.getElementById('aegis-close-btn').addEventListener('click', function () {
    win.classList.remove('open');
  });

  sendBtn.addEventListener('click', function () { send(); });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });

  document.querySelectorAll('.aegis-quick-btn').forEach(function (btn) {
    btn.addEventListener('click', function () { send(btn.dataset.q); });
  });

})();
