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
  if (!text) return;

  let chat = getActiveChat();
  if (!chat) chat = createChat(text);

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
      createdAt: Date.now()
    };
    chat.messages.push(assistantMessage);
    saveChats();
    appendMessage(assistantMessage);
  } catch (error) {
    removeTyping();
    appendMessage({ role: 'assistant', text: 'Не удалось получить ответ. Проверьте подключение к серверу.' });
    console.error(error);
  }
});

async function askAssistant(question, chat) {
  // ================================================================
  // ТОЧКА ПОДКЛЮЧЕНИЯ ВАШЕГО БЭКЕНДА / RAG / LLM.
  // Когда API будет готов, удалите демо-блок ниже и используйте, например:
  //
  // const response = await fetch('http://localhost:8000/api/chat', {
  //   method: 'POST',
  //   headers: { 'Content-Type': 'application/json' },
  //   body: JSON.stringify({
  //     message: question,
  //     history: chat.messages
  //   })
  // });
  // if (!response.ok) throw new Error('API error');
  // return await response.json();
  // Ожидаемый ответ: { text: '...', sources: ['Методичка ЛР1, стр. 5'] }
  // ================================================================

  await new Promise(resolve => setTimeout(resolve, 750));
  return {
    text: `Демо-ответ на запрос: «${question}»\n\nСейчас работает только фронтенд. После подключения серверной части здесь появится ответ модели на основе методических материалов кафедры.`,
    sources: ['демонстрационный режим']
  };
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
