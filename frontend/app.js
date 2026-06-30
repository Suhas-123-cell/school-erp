// ── Config ────────────────────────────────────────────────────────────────
const API = (window.location.port === '8000' || window.location.port === '')
  ? window.location.origin
  : window.location.origin.replace(/:\d+$/, ':8000');

const STUDENTS = {
  S001: { name: 'Arjun Sharma', cls: '10-A', roll: 12, initial: 'A' },
  S002: { name: 'Priya Nair',   cls: '10-A', roll: 18, initial: 'P' },
  S003: { name: 'Rohan Mehta',  cls: '10-B', roll: 5,  initial: 'R' },
};

// ── State ─────────────────────────────────────────────────────────────────
let sessionId = localStorage.getItem('erp_session') || null;
let studentId = localStorage.getItem('erp_student') || 'S001';
let isLoading = false;

// ── DOM refs ───────────────────────────────────────────────────────────────
const messagesEl   = document.getElementById('messages');
const inputEl      = document.getElementById('chatInput');
const sendBtn      = document.getElementById('sendBtn');
const emptyState   = document.getElementById('emptyState');
const sessionInfo  = document.getElementById('sessionInfo');
const studentSel   = document.getElementById('studentSelect');
const newChatBtn   = document.getElementById('newChatBtn');
const sessionsEl   = document.getElementById('sessionsList');

// ── Init ──────────────────────────────────────────────────────────────────
(function init() {
  studentSel.value = studentId;
  updateStudentUI(studentId);
  updateSessionUI();
  loadSessions();

  if (sessionId) loadHistory(sessionId);

  inputEl.addEventListener('input', () => {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
    sendBtn.disabled = inputEl.value.trim().length === 0;
  });

  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled && !isLoading) sendMessage();
    }
  });

  sendBtn.addEventListener('click', () => {
    if (!sendBtn.disabled && !isLoading) sendMessage();
  });

  studentSel.addEventListener('change', () => {
    studentId = studentSel.value;
    localStorage.setItem('erp_student', studentId);
    updateStudentUI(studentId);
    startNewChat();
    loadSessions();
  });

  newChatBtn.addEventListener('click', () => {
    startNewChat();
  });

  document.querySelectorAll('.quick-item').forEach(btn => {
    btn.addEventListener('click', () => {
      inputEl.value = btn.dataset.q;
      inputEl.dispatchEvent(new Event('input'));
      sendMessage();
    });
  });
})();

// ── Student UI ────────────────────────────────────────────────────────────
function updateStudentUI(id) {
  const s = STUDENTS[id] || STUDENTS.S001;
  document.getElementById('studentName').textContent = s.name;
  document.getElementById('studentMeta').textContent = `Class ${s.cls} · Roll ${s.roll}`;
  document.getElementById('studentAvatar').textContent = s.initial;
}

function updateSessionUI() {
  sessionInfo.textContent = sessionId
    ? `Session · ${sessionId.slice(0, 8)}…`
    : 'No active session';
}

// ── Session list ──────────────────────────────────────────────────────────
async function loadSessions() {
  try {
    const res = await fetch(`${API}/chat/sessions?student_id=${studentId}`);
    if (!res.ok) return;
    const data = await res.json();
    renderSessions(data.sessions || []);
  } catch (_) {}
}

function renderSessions(sessions) {
  if (!sessions.length) {
    sessionsEl.innerHTML = '<div class="sessions-empty">No history yet</div>';
    return;
  }
  sessionsEl.innerHTML = sessions.map(s => {
    const preview = s.first_message
      ? s.first_message.slice(0, 42) + (s.first_message.length > 42 ? '…' : '')
      : 'Conversation';
    const time = formatTime(s.last_at);
    const active = s.session_id === sessionId ? ' active' : '';
    return `<button class="session-item${active}" onclick="switchToSession('${s.session_id}')">
      <div class="session-preview">${escHtml(preview)}</div>
      <div class="session-time">${time}</div>
      <span class="session-del" onclick="deleteSession(event,'${s.session_id}')" title="Remove">
        <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M2 3h8M5 3V2h2v1M4.5 9.5l-.5-5M7.5 9.5l.5-5M3 3l.5 7h5L9 3"/></svg>
      </span>
    </button>`;
  }).join('');
}


async function deleteSession(e, sid) {
  e.stopPropagation();
  if (!confirm('Delete this conversation?')) return;
  try {
    const res = await fetch(`${API}/chat/history?session_id=${sid}`, { method: 'DELETE' });
    if (!res.ok) throw new Error();
    if (sid === sessionId) startNewChat();
    loadSessions();
  } catch (_) {}
}

async function switchToSession(id) {
  if (id === sessionId) return;
  sessionId = id;
  localStorage.setItem('erp_session', id);
  updateSessionUI();
  clearMessages();
  await loadHistory(id);
  renderSessions(await fetchSessions());
}

async function fetchSessions() {
  try {
    const res = await fetch(`${API}/chat/sessions?student_id=${studentId}`);
    if (!res.ok) return [];
    return (await res.json()).sessions || [];
  } catch (_) { return []; }
}

function startNewChat() {
  sessionId = null;
  localStorage.removeItem('erp_session');
  updateSessionUI();
  clearMessages();
  renderSessions(Array.from(sessionsEl.querySelectorAll('.session-item')).map(el => ({
    session_id: el.getAttribute('onclick').match(/'([^']+)'/)[1],
    first_message: el.querySelector('.session-preview').textContent,
    last_at: el.querySelector('.session-time').textContent,
    student_id: studentId,
  })));
}

function clearMessages() {
  messagesEl.innerHTML = '';
  messagesEl.appendChild(emptyState);
  emptyState.style.display = '';
}

// ── History load ──────────────────────────────────────────────────────────
async function loadHistory(sid) {
  try {
    const res = await fetch(`${API}/chat/history?session_id=${sid}`);
    if (!res.ok) {
      if (res.status === 404) {
        sessionId = null;
        localStorage.removeItem('erp_session');
        updateSessionUI();
      }
      return;
    }
    const data = await res.json();
    if (!data.messages || data.messages.length === 0) return;
    emptyState.style.display = 'none';
    data.messages.forEach(m => {
      if (m.role === 'user') appendUserMsg(m.content);
      else if (m.role === 'assistant') appendAIMsg(m.content, {
        intent: m.intent,
        tools: m.tools_used,
      });
    });
    scrollToBottom();
  } catch (_) {}
}

// ── Send ──────────────────────────────────────────────────────────────────
async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || isLoading) return;

  isLoading = true;
  sendBtn.disabled = true;
  inputEl.value = '';
  inputEl.style.height = 'auto';

  emptyState.style.display = 'none';
  appendUserMsg(text);
  const loadingEl = appendLoading();
  scrollToBottom();

  try {
    const res = await fetch(`${API}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, student_id: studentId, session_id: sessionId }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    sessionId = data.session_id;
    localStorage.setItem('erp_session', sessionId);
    updateSessionUI();

    loadingEl.remove();
    appendAIMsg(data.response, {
      intent: data.intent,
      tools: data.tools_used,
      plan: data.execution_plan,
      time: data.execution_time_ms,
    });

    loadSessions();

  } catch (err) {
    loadingEl.remove();
    appendErrorMsg(err.message || 'Could not reach the ERP server.');
  } finally {
    isLoading = false;
    sendBtn.disabled = inputEl.value.trim().length === 0;
    scrollToBottom();
  }
}

// ── Render helpers ────────────────────────────────────────────────────────
function appendUserMsg(text) {
  const row = el('div', 'msg-row user');
  row.innerHTML = `
    <div class="msg-sender">You</div>
    <div class="msg-bubble">${escHtml(text)}</div>
  `;
  messagesEl.appendChild(row);
}

function appendAIMsg(text, meta = {}) {
  const row = el('div', 'msg-row ai');
  const rendered = typeof marked !== 'undefined'
    ? marked.parse(text || '')
    : escHtml(text || '').replace(/\n/g, '<br>');

  let metaHtml = '';
  if (meta.intent) metaHtml += `<span class="meta-intent">${escHtml(meta.intent)}</span>`;
  if (meta.tools && meta.tools.length)
    meta.tools.forEach(t => { metaHtml += `<span class="meta-tool">${escHtml(t)}</span>`; });
  if (meta.plan) metaHtml += `<button class="plan-toggle" onclick="togglePlan(this)">show plan</button>`;
  if (meta.time != null) metaHtml += `<span class="meta-time">${meta.time.toFixed(0)} ms</span>`;

  row.innerHTML = `
    <div class="msg-sender">ERP Assistant</div>
    <div class="msg-bubble">${rendered}</div>
    ${metaHtml ? `<div class="msg-meta">${metaHtml}</div>` : ''}
    ${meta.plan ? `<div class="plan-box" style="display:none">${escHtml(meta.plan)}</div>` : ''}
  `;
  messagesEl.appendChild(row);
}

function appendLoading() {
  const row = el('div', 'msg-row ai msg-loading');
  row.innerHTML = `
    <div class="msg-sender">ERP Assistant</div>
    <div class="msg-bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>
  `;
  messagesEl.appendChild(row);
  return row;
}

function appendErrorMsg(msg) {
  const row = el('div', 'msg-row ai msg-error');
  row.innerHTML = `
    <div class="msg-sender">Error</div>
    <div class="msg-bubble">${escHtml(msg)}</div>
  `;
  messagesEl.appendChild(row);
}

// ── Plan toggle ───────────────────────────────────────────────────────────
function togglePlan(btn) {
  const planBox = btn.closest('.msg-row').querySelector('.plan-box');
  if (!planBox) return;
  const shown = planBox.style.display !== 'none';
  planBox.style.display = shown ? 'none' : 'block';
  btn.textContent = shown ? 'show plan' : 'hide plan';
}

// ── Utils ─────────────────────────────────────────────────────────────────
function el(tag, cls) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function scrollToBottom() {
  const wrap = document.getElementById('messagesWrap');
  requestAnimationFrame(() => { wrap.scrollTop = wrap.scrollHeight; });
}

function formatTime(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z');
    const now = new Date();
    const diffDays = Math.floor((now - d) / 86400000);
    if (diffDays === 0) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return d.toLocaleDateString([], { weekday: 'short' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  } catch (_) { return iso.slice(0, 10); }
}

// ── Students modal ────────────────────────────────────────────────────────
document.getElementById('studentsBtn').addEventListener('click', openStudents);

function openStudents() {
  document.getElementById('modalOverlay').classList.add('open');
  fetchAndRenderStudentCards();
}

function closeStudents() {
  document.getElementById('modalOverlay').classList.remove('open');
  document.getElementById('formMsg').textContent = '';
  document.getElementById('studentForm').reset();
}

function handleOverlayClick(e) {
  if (e.target === document.getElementById('modalOverlay')) closeStudents();
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeStudents();
});

async function fetchAndRenderStudentCards() {
  const container = document.getElementById('studentCards');
  const sub = document.getElementById('modalSub');
  try {
    const res = await fetch(`${API}/students`);
    const students = await res.json();
    sub.textContent = `${students.length} student${students.length !== 1 ? 's' : ''} enrolled`;
    container.innerHTML = students.map(s => `
      <div class="s-card" id="sc-${s.student_id}">
        <div class="s-card-avatar">${s.name.charAt(0)}</div>
        <div class="s-card-info">
          <div class="s-card-name">${escHtml(s.name)}</div>
          <div class="s-card-meta">Class ${escHtml(s.class || '')} · Roll ${s.roll_number}</div>
        </div>
        <div class="s-card-id">${s.student_id}</div>
      </div>
    `).join('');

    // Also refresh the chat dropdown
    refreshChatDropdown(students);
  } catch (err) {
    container.innerHTML = `<div class="card-loading" style="color:var(--red)">Failed to load</div>`;
  }
}

function refreshChatDropdown(students) {
  const sel = document.getElementById('studentSelect');
  const current = sel.value;
  sel.innerHTML = students.map(s =>
    `<option value="${s.student_id}">${s.student_id} — ${escHtml(s.name)}</option>`
  ).join('');
  sel.value = current;
  // Update STUDENTS lookup
  students.forEach(s => {
    STUDENTS[s.student_id] = {
      name: s.name,
      cls: s.class || '',
      roll: s.roll_number,
      initial: s.name.charAt(0),
    };
  });
}

document.getElementById('studentForm').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = e.target.querySelector('.submit-btn');
  const msg = document.getElementById('formMsg');
  const fd = new FormData(e.target);
  const payload = Object.fromEntries(fd.entries());
  payload.roll_number = parseInt(payload.roll_number, 10);

  btn.disabled = true;
  btn.textContent = 'Adding…';
  msg.className = 'form-msg';
  msg.textContent = '';

  try {
    const res = await fetch(`${API}/students`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to add student');

    msg.className = 'form-msg success';
    msg.textContent = `✓ ${data.name} added as ${data.student_id}`;
    e.target.reset();

    // Prepend new card with animation
    const container = document.getElementById('studentCards');
    const card = document.createElement('div');
    card.className = 's-card';
    card.id = `sc-${data.student_id}`;
    card.innerHTML = `
      <div class="s-card-avatar new">${data.name.charAt(0)}</div>
      <div class="s-card-info">
        <div class="s-card-name">${escHtml(data.name)}</div>
        <div class="s-card-meta">Class ${escHtml(data.class || '')} · Roll ${data.roll_number}</div>
      </div>
      <div class="s-card-id">${data.student_id}</div>
    `;
    container.prepend(card);

    const sub = document.getElementById('modalSub');
    const count = container.querySelectorAll('.s-card').length;
    sub.textContent = `${count} student${count !== 1 ? 's' : ''} enrolled`;

    STUDENTS[data.student_id] = {
      name: data.name, cls: data.class || '',
      roll: data.roll_number, initial: data.name.charAt(0),
    };
    const sel = document.getElementById('studentSelect');
    const opt = document.createElement('option');
    opt.value = data.student_id;
    opt.textContent = `${data.student_id} — ${data.name}`;
    sel.appendChild(opt);

  } catch (err) {
    msg.className = 'form-msg error';
    msg.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Add Student';
  }
});
