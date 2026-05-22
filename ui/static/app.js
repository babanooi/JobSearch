/* ═══════════════════════════════════════════════════
   JobSearch · Chat SPA
   对话逻辑 / API 调用 / DOM 渲染
   ═══════════════════════════════════════════════════ */

// ── 持久化助手 ──
function saveThreadMsgs(tid, msgs) {
  try { localStorage.setItem(`msgs_${tid}`, JSON.stringify(msgs)); } catch(_) {}
}
function loadThreadMsgs(tid) {
  try {
    const raw = localStorage.getItem(`msgs_${tid}`);
    return raw ? JSON.parse(raw) : [];
  } catch(_) { return []; }
}

// ── 状态 ──
let threadId = crypto.randomUUID();
let userId   = parseInt(localStorage.getItem('js_user_id') || '0');
let messages = loadThreadMsgs(threadId);

// ── DOM ──
const el = {
  userTag:    document.getElementById('userTag'),
  convList:   document.getElementById('convList'),
  jobList:    document.getElementById('jobList'),
  chatInput:  document.getElementById('chatInput'),
  btnSend:    document.getElementById('btnSend'),
  btnNewChat: document.getElementById('btnNewChat'),
  userArea:   document.getElementById('userArea'),
  userDropdown: document.getElementById('userDropdown'),
  userList:   document.getElementById('userList'),
  btnNewUser: document.getElementById('btnNewUser'),
  msgList:    document.getElementById('messageList'),
};

// ── API ──
const api = {
  async chat(message, tid) {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, thread_id: tid, user_id: userId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  },
  async conversations(uid) {
    const res = await fetch(`/conversations?user_id=${uid}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.conversations || [];
  },
  async analyzedJobs() {
    const res = await fetch('/skill_rank/_jobs');
    if (!res.ok) return [];
    const data = await res.json();
    return data.jobs || [];
  },
  async skillRank(jobName, topN = 15) {
    const res = await fetch(`/skill_rank/${encodeURIComponent(jobName)}?top_n=${topN}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.data || [];
  },
  async conversationMessages(tid) {
    const res = await fetch(`/conversation/${tid}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.messages || [];
  },
};

// ── 渲染 ──
function renderConversations(convs) {
  el.convList.innerHTML = convs.length
    ? convs.map(c => {
        const active = c.thread_id === threadId ? ' active' : '';
        return `<button class="conv-item${active}" data-tid="${c.thread_id}">
          ${active ? '●' : '○'} ${escHtml(c.title || '未命名')} · ${c.updated_at}
        </button>`;
      }).join('')
    : '<span style="color:#8c8278;font-size:0.7rem;">暂无历史对话</span>';

  el.convList.querySelectorAll('.conv-item').forEach(btn => {
    btn.addEventListener('click', () => switchConversation(btn.dataset.tid));
  });
}

function renderJobs(jobs) {
  el.jobList.innerHTML = jobs.length
    ? jobs.map(j => `<span class="job-item clickable" data-job="${escHtml(j)}">· ${escHtml(j)}</span>`).join('')
    : '<span style="color:#8c8278;font-size:0.7rem;">暂无</span>';

  el.jobList.querySelectorAll('.job-item.clickable').forEach(span => {
    span.addEventListener('click', () => showRanking(span.dataset.job));
  });
}

function restoreMessages(msgs) {
  el.msgList.innerHTML = '';
  for (const m of msgs) {
    const div = document.createElement('div');
    div.className = `msg msg-${m.role}`;
    div.innerHTML = m.content.replace(/\n/g, '<br>');
    el.msgList.appendChild(div);
  }
  el.msgList.scrollTop = el.msgList.scrollHeight;
}

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = `msg msg-${role}`;
  div.innerHTML = content.replace(/\n/g, '<br>');
  el.msgList.appendChild(div);
  el.msgList.scrollTop = el.msgList.scrollHeight;
}

function showLoading() {
  const div = document.createElement('div');
  div.className = 'msg-loading';
  div.id = 'loadingIndicator';
  el.msgList.appendChild(div);
  el.msgList.scrollTop = el.msgList.scrollHeight;
}

function hideLoading() {
  const ld = document.getElementById('loadingIndicator');
  if (ld) ld.remove();
}

// ── 对话 ──
async function sendMessage() {
  const text = el.chatInput.value.trim();
  if (!text) return;

  el.chatInput.value = '';
  el.btnSend.disabled = true;

  addMessage('user', text);
  showLoading();

  try {
    const result = await api.chat(text, threadId);
    hideLoading();
    addMessage('assistant', result.response);
    if (result.thread_id) threadId = result.thread_id;

    // 持久化消息到 localStorage（按 thread_id）
    messages.push({ role: 'user', content: text });
    messages.push({ role: 'assistant', content: result.response });
    saveThreadMsgs(threadId, messages);

    refreshSidebar();
  } catch (err) {
    hideLoading();
    addMessage('assistant', `抱歉，请求出错了：${err.message}`);
  }

  el.btnSend.disabled = false;
  el.chatInput.focus();
}

async function switchConversation(tid) {
  saveThreadMsgs(threadId, messages);

  threadId = tid;
  messages = loadThreadMsgs(tid);

  // localStorage 为空时从服务端加载
  if (messages.length === 0) {
    messages = await api.conversationMessages(tid);
    saveThreadMsgs(tid, messages);
  }

  restoreMessages(messages);
  refreshSidebar();
}

// ── 技能类型分类 ──
const SKILL_TAGS = {
  python:['Python','FastAPI','Django','Flask','SQLAlchemy','Celery','Tornado','aiohttp','PyTorch','TensorFlow','Pandas','NumPy','Scrapy','Selenium','Pytest','Jupyter','OpenCV','NLTK','spaCy'],
  java:['Java','Spring','SpringBoot','SpringCloud','MyBatis','MyBatis-Plus','Dubbo','Netty','JPA','Hibernate','Maven','Gradle','Tomcat','Jetty','JUnit','Log4j','Kafka','RabbitMQ','RocketMQ','Zookeeper','Nacos','Sentinel','Seata'],
  js:['JavaScript','TypeScript','Node.js','NodeJS','React','Vue','Vue3','Vue2','Angular','Next.js','Nuxt','Express','Koa','NestJS','Webpack','Vite','Babel','ESLint','Prettier','jQuery','Bootstrap','Tailwind','AntDesign','ElementUI'],
  go:['Go','Golang','Gin','Echo','Beego','gRPC','protobuf'],
  db:['MySQL','PostgreSQL','MongoDB','Redis','ElasticSearch','Elasticsearch','ClickHouse','Oracle','SQLite','Cassandra','HBase','Neo4j','InfluxDB','TiDB','Etcd','Consul'],
  ops:['Docker','Kubernetes','K8s','Linux','AWS','Azure','GCP','CI/CD','Jenkins','GitLabCI','GitHubActions','Ansible','Terraform','Prometheus','Grafana','ELK','Nginx','HAProxy','Istio','Helm'],
  algo:['算法','数据结构','机器学习','深度学习','NLP','CV','推荐系统','排序','搜索','动态规划','贪心','回溯','递归','树','图论','哈希','排序算法'],
  arch:['微服务','分布式','高并发','高可用','DDD','领域驱动','设计模式','系统设计','架构','中台','SaaS','PaaS','Serverless','事件驱动','CQRS','EventSourcing'],
  ai:['AI','LLM','RAG','Agent','大模型','LangChain','LangChain4j','SpringAI','MCP','FunctionCalling','工具调用','Prompt','向量库','Embedding','Rerank','AIGC','Transformer','Attention','RLHF','SFT','LoRA'],
  mobile:['Android','iOS','Flutter','ReactNative','Swift','Kotlin','Objective-C','Dart','小程序','Weex','Cordova'],
  lang:['C++','C#','Rust','Ruby','PHP','Scala','Haskell','Erlang','Elixir','Lua','Shell','Bash','Perl','Matlab','R语言','COBOL','Fortran'],
};

function classifySkill(name) {
  const lower = name.toLowerCase();
  for (const [tag, list] of Object.entries(SKILL_TAGS)) {
    if (list.some(k => k.toLowerCase() === lower)) return tag;
  }
  if (/^(开发|测试|运维|前端|后端|全栈|数据|产品|安全|嵌入式)/.test(name)) return 'role';
  if (/^(多线程|并发|异步|IO|多进程|线程|进程|锁|队列|栈|堆|内存|缓存|性能|调优|排障|监控|日志|安全|加密|认证|授权)/.test(name)) return 'cs';
  return '';
}

const TAG_LABELS = {
  python:'Python 生态', java:'Java 生态', js:'JavaScript', go:'Go',
  db:'数据库/存储', ops:'运维/DevOps', algo:'算法', arch:'架构',
  ai:'AI/大模型', mobile:'移动端', lang:'编程语言', role:'岗位方向', cs:'计算机基础',
};

function heatLevel(pct) { return pct > 50 ? 'hot' : pct > 20 ? 'warm' : 'cool'; }

// ── 技能排名视图 · 热力仪表板 ──
let _rankingAnims = [];

function rankClass(idx, jdPct) {
  if (idx === 0) return 'top1';
  if (idx === 1) return 'top2';
  if (idx === 2) return 'top3';
  return heatLevel(jdPct);
}

async function showRanking(jobName) {
  const skills = await api.skillRank(jobName, 15);
  if (!skills.length) return;

  _rankingAnims.forEach(id => clearTimeout(id));
  _rankingAnims = [];

  const totalJds = skills[0]?.total_jds || 0;
  const lastSeen = skills[0]?.last_seen_at || '';

  let html = `<div class="rk-hero">
    <div class="rk-title">✦ ${escHtml(jobName)} <span class="rk-subtitle">技能热度仪表板</span></div>
    <div class="rk-legend">
      <span><span class="l-dot t1"></span> 高热</span>
      <span><span class="l-dot t2"></span> 中热</span>
      <span><span class="l-dot t3"></span> 温</span>
    </div>
  </div><div class="rk-grid">`;

  for (let i = 0; i < skills.length; i++) {
    const s     = skills[i];
    const jdPct = totalJds ? Math.round((s.count / totalJds) * 100) : 0;
    const barW  = totalJds ? Math.round((s.count / totalJds) * 100) : 0;
    const lvl   = rankClass(i, jdPct);
    const tag   = classifySkill(s.skill);
    const tagLabel = TAG_LABELS[tag] || '';

    html += `<div class="rk-card ${lvl}" data-idx="${i}">
      <div class="rk-rank">${i+1}</div>
      <div class="rk-body">
        <div class="rk-topline">
          <span class="rk-name">${escHtml(s.skill)}</span>
          ${tag ? `<span class="rk-tag tag-${tag}">${tagLabel}</span>` : ''}
          <span class="rk-pct">${jdPct}%</span>
        </div>
        <div class="rk-track">
          <span class="rk-bar" style="width:0%"></span>
        </div>
      </div>
      <div class="rk-count">${s.count}<span>次</span></div>
    </div>`;
  }

  html += `</div>`;

  if (totalJds) {
    html += `<div class="rk-source">基于 <strong>${totalJds}</strong> 条招聘信息的真实统计 · 最近更新 ${lastSeen}</div>`;
  }

  document.getElementById('rankingContent').innerHTML = html;
  document.getElementById('messageList').style.display = 'none';
  document.getElementById('inputArea').style.display = 'none';
  document.getElementById('rankingView').style.display = 'block';

  _rankingAnims.push(setTimeout(() => {
    document.querySelectorAll('.rk-card .rk-bar').forEach((bar, i) => {
      bar.style.width = bar.parentElement?.dataset?.w || `${Math.min(bar.closest('.rk-card')?.querySelector('.rk-pct')?.textContent?.replace('%','') || 0, 100)}%`;
    });
    // 直接用百分比
    document.querySelectorAll('.rk-card').forEach((card, i) => {
      const pctEl = card.querySelector('.rk-pct');
      const bar   = card.querySelector('.rk-bar');
      if (pctEl && bar) {
        const pct = parseInt(pctEl.textContent) || 0;
        setTimeout(() => { bar.style.width = `${pct}%`; }, i * 60);
      }
    });
  }, 150));
}

document.getElementById('btnBackToChat').addEventListener('click', () => {
  document.getElementById('rankingView').style.display = 'none';
  document.getElementById('messageList').style.display = '';
  document.getElementById('inputArea').style.display = '';
});

// ── 侧边栏 ──
async function refreshSidebar() {
  if (!userId) return;
  try {
    const [convs, jobs] = await Promise.all([
      api.conversations(userId),
      api.analyzedJobs(),
    ]);
    renderConversations(convs);
    renderJobs(jobs);
  } catch (_) {}
}

// ── 事件 ──
el.btnSend.addEventListener('click', sendMessage);
el.chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
el.btnNewChat.addEventListener('click', () => {
  saveThreadMsgs(threadId, messages);
  threadId = crypto.randomUUID();
  messages = [];
  el.msgList.innerHTML = '';
  refreshSidebar();
});

// ── 用户下拉切换 ──
let savedUsers = JSON.parse(localStorage.getItem('js_saved_users') || '[]');

el.userArea.addEventListener('click', (e) => {
  e.stopPropagation();
  el.userArea.classList.toggle('open');
  if (el.userArea.classList.contains('open')) renderUserList();
});
document.addEventListener('click', () => el.userArea.classList.remove('open'));

async function renderUserList() {
  // 合并本地已保存用户 + 服务端用户
  let allUsers = [...savedUsers];
  try {
    const res = await fetch('/users');
    const data = await res.json();
    for (const u of (data.users || [])) {
      if (!allUsers.find(x => x.id === u.id)) {
        allUsers.push(u);
      }
    }
  } catch (_) {}

  el.userList.innerHTML = allUsers.map(u =>
    `<button class="user-dropdown-item${u.id === userId ? ' active' : ''}" data-uid="${u.id}">
      ${u.id === userId ? '' : '  '}${escHtml(u.username)}
    </button>`
  ).join('');

  el.userList.querySelectorAll('.user-dropdown-item').forEach(btn => {
    btn.addEventListener('click', () => switchUser(parseInt(btn.dataset.uid)));
  });
}

async function switchUser(uid) {
  if (uid === userId) { el.userArea.classList.remove('open'); return; }
  // 注册到本地列表
  if (!savedUsers.find(u => u.id === uid)) {
    // 从服务端确认
    try {
      const res = await fetch('/users');
      const data = await res.json();
      const found = (data.users || []).find(u => u.id === uid);
      if (found) savedUsers.push(found);
    } catch (_) {}
  }
  localStorage.setItem('js_saved_users', JSON.stringify(savedUsers));
  localStorage.setItem('js_user_id', String(uid));
  userId = uid;
  el.userTag.textContent = savedUsers.find(u => u.id === uid)?.username || `用户_${uid}`;
  threadId = crypto.randomUUID();
  messages = [];
  el.msgList.innerHTML = '';
  el.userArea.classList.remove('open');
  refreshSidebar();
}

el.btnNewUser.addEventListener('click', async () => {
  const newName = prompt('输入新用户名（留空则随机生成）：');
  if (newName === null) return;
  const res = await fetch(`/user?username=${encodeURIComponent(newName || '')}`);
  const data = await res.json();
  savedUsers.push({ id: data.user_id, username: data.username });
  localStorage.setItem('js_saved_users', JSON.stringify(savedUsers));
  await switchUser(data.user_id);
});

// ── 工具 ──
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ── 启动 ──
(async function init() {
  if (!userId) {
    try {
      const res = await fetch('/user');
      const data = await res.json();
      userId = data.user_id;
      localStorage.setItem('js_user_id', String(userId));
      el.userTag.textContent = data.username;
    } catch (_) {
      userId = 0;
    }
  } else {
    el.userTag.textContent = `用户_${localStorage.getItem('js_user_id')?.slice(0, 8) || '?'}`;
  }
  // 恢复当前对话的消息
  restoreMessages(messages);
  refreshSidebar();
  el.chatInput.focus();
})();
