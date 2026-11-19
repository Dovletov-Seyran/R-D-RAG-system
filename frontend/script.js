const API_URL = 'http://localhost:8000';
let pendingChatId = null;
const STORAGE_KEY = 'iu5_ai_chats_v2';
const AUTH_KEY = 'iu5_ai_auth_v2';

const authScreen = document.getElementById('authScreen');
const app = document.getElementById('app');
const loginForm = document.getElementById('loginForm');
const loginInput = document.getElementById('loginInput');
const passwordInput = document.getElementById('passwordInput');
const loginError = document.getElementById('loginError');
const logoutButton = document.getElementById('logoutButton');
const newChatButton = document.getElementById('newChatButton');
const chatHistory = document.getElementById('chatHistory');
const welcomeScreen = document.getElementById('welcomeScreen');
const messagesEl = document.getElementById('messages');
const messageForm = document.getElementById('messageForm');
const messageInput = document.getElementById('messageInput');
const chatArea = document.getElementById('chatArea');
const topbarTitle = document.getElementById('topbarTitle');
const mobileMenuButton = document.getElementById('mobileMenuButton');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');

let chats = loadChats();
let activeChatId = chats[0]?.id ?? null;

function loadChats() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; }
  catch { return []; }
}

function saveChats() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
}

function showApp() {
  authScreen.classList.add('hidden');
  app.classList.remove('hidden');
  render();
}

function showAuth() {
  app.classList.add('hidden');
  authScreen.classList.remove('hidden');
  loginInput.focus();
}

if (sessionStorage.getItem(AUTH_KEY) === '1') showApp();
else showAuth();

loginForm.addEventListener('submit', (event) => {
  event.preventDefault();
  if (loginInput.value.trim() === 'admin' && passwordInput.value === 'admin') {
    sessionStorage.setItem(AUTH_KEY, '1');
    loginError.textContent = '';
    showApp();
  } else {
    loginError.textContent = 'Неверный логин или пароль';
  }
});

logoutButton.addEventListener('click', () => {
  sessionStorage.removeItem(AUTH_KEY);
  passwordInput.value = '';
  closeSidebar();
  showAuth();
});

newChatButton.addEventListener('click', () => {
  activeChatId = null;
  render();
  closeSidebar();
  messageInput.focus();
});

function createChat(firstMessage) {
  const chat = {
    id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
    title: firstMessage.slice(0, 42) || 'Новый диалог',
    createdAt: Date.now(),
    messages: []
  };
  chats.unshift(chat);
  activeChatId = chat.id;
  saveChats();
  return chat;
}

function getActiveChat() {
  return chats.find(chat => chat.id === activeChatId) || null;
}

function render() {
  showChatScreen();
  renderHistory();
  renderMessages();
}

function renderHistory() {
  chatHistory.innerHTML = '';
  if (!chats.length) {
    chatHistory.innerHTML = '<div style="padding:12px;color:rgba(255,255,255,.28);font-size:10px;line-height:1.5">История появится после первого сообщения.</div>';
    return;
  }

  chats.forEach(chat => {
    const item = document.createElement('button');
    item.className = `history-item ${chat.id === activeChatId ? 'active' : ''}`;
    item.innerHTML = `
      <span class="bubble-icon">◫</span>
      <span class="history-title"></span>
      <span class="delete-chat" title="Удалить диалог">×</span>
    `;
    item.querySelector('.history-title').textContent = chat.title;
    item.addEventListener('click', (event) => {
      if (event.target.classList.contains('delete-chat')) return;
      activeChatId = chat.id;
      render();
      closeSidebar();
    });
    item.querySelector('.delete-chat').addEventListener('click', (event) => {
      event.stopPropagation();
      chats = chats.filter(item => item.id !== chat.id);
      if (activeChatId === chat.id) activeChatId = chats[0]?.id ?? null;
      saveChats();
      render();
    });
    chatHistory.appendChild(item);
  });
}

function renderMessages() {
  const chat = getActiveChat();
  messagesEl.innerHTML = '';
  const hasMessages = Boolean(chat?.messages.length);
  welcomeScreen.classList.toggle('hidden', hasMessages);
  topbarTitle.textContent = chat?.title || 'Новый диалог';

  if (!chat) return;
  chat.messages.forEach(message => appendMessage(message, false));
  if (pendingChatId === chat.id) showTyping();
  requestAnimationFrame(scrollToBottom);
}

function appendMessage(message, shouldScroll = true) {
  const row = document.createElement('div');
  row.className = `message ${message.role}`;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = message.role === 'user' ? 'A' : 'AI';

  const content = document.createElement('div');
  content.className = 'message-content';
  const role = document.createElement('div');
  role.className = 'message-role';
  role.textContent = message.role === 'user' ? 'ВЫ' : 'АССИСТЕНТ ИУ-5';
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = message.text;
  if (message.finish_reason === 'no_context') {
    row.classList.add('no-context');
    role.textContent = 'НЕТ ИНФОРМАЦИИ В МАТЕРИАЛАХ';
  }
  if (message.isError) row.classList.add('message-error');
  content.append(role, bubble);

  if (message.sources?.length) {
    const sources = document.createElement('div');
    sources.className = 'sources';
    sources.textContent = `Источник: ${message.sources.join(', ')}`;
    content.appendChild(sources);
  }

  row.append(avatar, content);
  messagesEl.appendChild(row);
  if (shouldScroll) scrollToBottom();
}

function showTyping() {
  const row = document.createElement('div');
  row.className = 'message assistant typing';
  row.id = 'typingIndicator';
  row.innerHTML = `
    <div class="message-avatar">AI</div>
    <div class="message-content">
      <div class="message-role">АССИСТЕНТ ИУ-5</div>
      <div class="message-bubble"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>
    </div>`;
  messagesEl.appendChild(row);
  scrollToBottom();
}

function removeTyping() {
  document.getElementById('typingIndicator')?.remove();
}

function scrollToBottom() {
  chatArea.scrollTop = chatArea.scrollHeight;
}

function autoResize() {
  messageInput.style.height = 'auto';
  messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
}
messageInput.addEventListener('input', autoResize);
messageInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    messageForm.requestSubmit();
  }
});

messageForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text || text.length > 2000 || pendingChatId) return;

  let chat = getActiveChat();
  if (!chat) chat = createChat(text);

  pendingChatId = chat.id;
  document.getElementById('sendButton').disabled = true;
  const userMessage = { role: 'user', text, createdAt: Date.now() };
  chat.messages.push(userMessage);
  saveChats();

  welcomeScreen.classList.add('hidden');
  topbarTitle.textContent = chat.title;
  appendMessage(userMessage);
  renderHistory();

  messageInput.value = '';
  autoResize();
  showTyping();

  try {
    const reply = await askAssistant(text, chat);
    removeTyping();
    const assistantMessage = {
      role: 'assistant',
      text: reply.text,
      sources: reply.sources || [],
      finish_reason: reply.finish_reason,
      createdAt: Date.now()
    };
    chat.messages.push(assistantMessage);
    saveChats();
    if (activeChatId === chat.id) appendMessage(assistantMessage);
  } catch (error) {
    removeTyping();
    chat.messages.push({ role: 'assistant', text: error.message, isError: true });
    saveChats();
    if (activeChatId === chat.id) renderMessages();
  } finally {
    pendingChatId = null;
    removeTyping();
    document.getElementById('sendButton').disabled = false;
  }
});

async function askAssistant(question, chat) {
  const reply = await apiRequest('/api/chat', {
    method: 'POST',
    body: JSON.stringify({message: question, history: chat.messages.slice(0, -1).filter(m => !m.isError).slice(-6).map(({role, text, createdAt}) => ({role, text, createdAt}))})
  });
  if (typeof reply.text !== 'string' || !Array.isArray(reply.sources) || !reply.sources.every(s => typeof s === 'string') || !['ok', 'no_context'].includes(reply.finish_reason)) {
    throw new Error('Сервер вернул ответ в неизвестном формате.');
  }
  return reply;
}

async function apiRequest(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120000);
  try {
    const response = await fetch(API_URL + path, {...options, headers: {'Content-Type': 'application/json'}, signal: controller.signal});
    if (!response.ok) {
      const errors = {400: 'Проверьте параметры запроса (вопрос — до 2000 символов).', 503: 'Модель или индекс недоступны. Попробуйте позже.', 500: 'Ошибка сервера. Попробуйте ещё раз.', 409: 'Benchmark уже запущен. Дождитесь окончания текущего прогона.', 404: 'Прогон не найден на сервере.'};
      throw new Error(errors[response.status] || `Ошибка сервера: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Сервер не ответил за 2 минуты. Проверьте его состояние.');
    if (error instanceof TypeError) throw new Error('Не удалось подключиться к API. Проверьте запуск backend и CORS.');
    throw error;
  } finally { clearTimeout(timeout); }
}

function showChatScreen() {
  document.getElementById('benchmarkScreen').classList.add('hidden');
  chatArea.classList.remove('hidden');
  document.querySelector('.composer-wrap').classList.remove('hidden');
}

document.querySelectorAll('.suggestion').forEach(button => {
  button.addEventListener('click', () => {
    messageInput.value = button.dataset.prompt;
    autoResize();
    messageInput.focus();
  });
});

mobileMenuButton.addEventListener('click', () => {
  sidebar.classList.add('open');
  sidebarOverlay.classList.add('show');
});
sidebarOverlay.addEventListener('click', closeSidebar);
function closeSidebar() {
  sidebar.classList.remove('open');
  sidebarOverlay.classList.remove('show');
}

const benchmarkScreen = document.getElementById('benchmarkScreen');
const benchmarkStatus = document.getElementById('benchmarkStatus');
const benchmarkRun = document.getElementById('benchmarkRun');
const benchmarkExample = document.getElementById('benchmarkExample');
document.getElementById('benchmarkButton').addEventListener('click', () => {
  chatArea.classList.add('hidden');
  document.querySelector('.composer-wrap').classList.add('hidden');
  benchmarkScreen.classList.remove('hidden');
  topbarTitle.textContent = 'Benchmark';
  closeSidebar();
});
function resetBenchmark() {
  document.getElementById('benchmarkMetrics').replaceChildren();
  document.getElementById('benchmarkRows').replaceChildren();
}
function renderBenchmark(result) {
  resetBenchmark();
  const metrics = result.metrics || {};
  for (const [key, label] of [['recall_at_k', `Recall@${result.params.k}`], ['mrr_at_k', `MRR@${result.params.k}`], ['accuracy', 'Accuracy'], ['correct_rejection_rate', 'Correct Rejection Rate']]) {
    const card = document.createElement('div'); card.className = 'metric-card';
    const title = document.createElement('span'); title.textContent = label;
    const value = document.createElement('strong');
    value.textContent = typeof metrics[key] === 'number' ? (metrics[key] * 100).toFixed(1) + '%' : 'Не рассчитано';
    card.append(title, value); document.getElementById('benchmarkMetrics').append(card);
  }
  for (const question of result.questions || []) {
    const row = document.createElement('tr');
    const values = [question.id, question.type === 'trap' ? 'Ловушка' : 'Обычный', question.query, (question.relevant_doc_ids || []).join(', ') || '—', '', question.answer || '—', question.correct == null ? 'Не оценено' : question.correct ? '✓ Верно' : '✗ Неверно'];
    values.forEach((value, index) => {
      const cell = document.createElement('td'); cell.textContent = value;
      if (index === 4) for (const id of question.retrieved_doc_ids || []) {
        const badge = document.createElement('span'); badge.textContent = id;
        badge.className = (question.relevant_doc_ids || []).includes(id) ? 'doc-badge relevant' : 'doc-badge'; cell.append(badge);
      }
      row.append(cell);
    });
    document.getElementById('benchmarkRows').append(row);
  }
}
let benchmarkBusy = false;
function setBenchmarkBusy(busy) {
  benchmarkBusy = busy;
  for (const id of ['benchmarkRun', 'benchmarkExample', 'benchmarkMode', 'benchmarkK']) document.getElementById(id).disabled = busy;
}
document.getElementById('benchmarkForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (benchmarkBusy) return;
  const k = Number(document.getElementById('benchmarkK').value);
  if (!Number.isSafeInteger(k) || k < 1) return;
  setBenchmarkBusy(true); resetBenchmark();
  benchmarkStatus.textContent = 'Запускаем проверку на сервере…';
  try {
    const started = await apiRequest('/api/benchmark/run', {method: 'POST', body: JSON.stringify({k, mode: document.getElementById('benchmarkMode').value})});
    if (!started.run_id) throw new Error('Сервер не вернул номер прогона.');
    const deadline = Date.now() + 30 * 60 * 1000;
    while (true) {
      const result = await apiRequest('/api/benchmark/runs/' + encodeURIComponent(started.run_id));
      if (result.status === 'error') throw new Error('Benchmark завершился с ошибкой. Проверьте журнал backend.');
      if (result.status === 'done') {
        renderBenchmark(result);
        benchmarkStatus.textContent = `Готово · ${result.progress?.done ?? result.questions.length} вопросов · ${result.params.mode} · k = ${result.params.k}`;
        break;
      }
      if (result.status !== 'running') throw new Error('Неизвестный статус прогона.');
      benchmarkStatus.textContent = `Выполнено вопросов: ${result.progress?.done ?? 0} из ${result.progress?.total ?? 15}`;
      if (Date.now() > deadline) throw new Error('Ожидание превысило 30 минут. Прогон может продолжаться на сервере.');
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
  } catch (error) { benchmarkStatus.textContent = error.message; }
  finally { setBenchmarkBusy(false); }
});
benchmarkExample.addEventListener('click', async () => {
  if (benchmarkBusy) return;
  setBenchmarkBusy(true); resetBenchmark();
  try {
    const response = await fetch('mock/benchmark-result.json');
    if (!response.ok) throw new Error('Не удалось загрузить пример.');
    renderBenchmark(await response.json());
    benchmarkStatus.textContent = 'ДЕМО · пример отображения, не результат запуска. Для проверки используйте «Запустить».';
  } catch (error) { benchmarkStatus.textContent = error.message; }
  finally { setBenchmarkBusy(false); }
});
