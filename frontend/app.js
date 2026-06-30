// ── Config ────────────────────────────────────────────────────────────────
const API = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1')
  ? window.location.origin.replace(/:\d+$/, ':8000')
  : window.location.origin;

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
const messagesEl  = document.getElementById('messages');
const inputEl     = document.getElementById('chatInput');
const sendBtn     = document.getElementById('sendBtn');
const emptyState  = document.getElementById('emptyState');
const sessionInfo = document.getElementById('sessionInfo');
const studentSel  = document.getElementById('studentSelect');
const newChatBtn  = document.getElementById('newChatBtn');

// ── Init ──────────────────────────────────────────────────────────────────
(function init() {
  studentSel.value = studentId;
  updateStudentUI(studentId);
  updateSessionUI();

  if (sessionId) {
    loadHistory();
  }

  // auto-resize textarea
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
  });

  newChatBtn.addEventListener('click', startNewChat);

  document.querySelectorAll('.quick-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const q = btn.dataset.q;
      inputEl.value = q;
      inputEl.dispatchEvent(new Event('input'));
      inputEl.focus();
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
    ? `Session: ${sessionId.slice(0, 8)}…`
    : 'No active session';
}

function startNewChat() {
  sessionId = null;
  localStorage.removeItem('erp_session');
  updateSessionUI();
  messagesEl.innerHTML = '';
  messagesEl.appendChild(emptyState);
  emptyState.style.display = 'flex';
}

// ── History ───────────────────────────────────────────────────────────────
async function loadHistory() {
  try {
    const res = await fetch(`${API}/chat/history?session_id=${sessionId}`);
    if (!res.ok) { sessionId = null; updateSessionUI(); return; }
    const data = await res.json();
    if (data.messages && data.messages.length > 0) {
      emptyState.style.display = 'none';
      data.messages.forEach(m => {
        if (m.role === 'user') appendUserMsg(m.content);
        else if (m.role === 'assistant') appendAIMsg(m.content, {
          intent: m.intent,
          tools: m.tools_used,
        });
      });
      scrollToBottom();
    }
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

  } catch (err) {
    loadingEl.remove();
    appendErrorMsg(err.message || 'Could not reach the ERP server. Is it running on port 8000?');
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
  if (meta.intent) {
    metaHtml += `<span class="meta-intent">${escHtml(meta.intent)}</span>`;
  }
  if (meta.tools && meta.tools.length) {
    meta.tools.forEach(t => {
      metaHtml += `<span class="meta-tool">${escHtml(t)}</span>`;
    });
  }
  if (meta.plan) {
    metaHtml += `<button class="plan-toggle" onclick="togglePlan(this)">show plan</button>`;
  }
  if (meta.time != null) {
    metaHtml += `<span class="meta-time">${meta.time.toFixed(0)} ms</span>`;
  }

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
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function scrollToBottom() {
  const wrap = document.getElementById('messagesWrap');
  requestAnimationFrame(() => { wrap.scrollTop = wrap.scrollHeight; });
}
