/* ═══════════════════════════════════════════════════
   JobLab · 暗夜星图 SPA
   视图切换 / 对话 / 雷达 / 研究 / 用户中心
   ═══════════════════════════════════════════════════ */

// ── 星空粒子 ──
(function stars(){
  const c=document.getElementById('starCanvas'),ctx=c.getContext('2d');
  let w,h,particles=[];
  function resize(){w=c.width=window.innerWidth;h=c.height=window.innerHeight;}
  resize();window.addEventListener('resize',resize);
  for(let i=0;i<80;i++)particles.push({x:Math.random()*w,y:Math.random()*h,r:Math.random()*1.2+0.3,a:Math.random()*0.5+0.2,s:Math.random()*0.3+0.1});
  function draw(){
    ctx.clearRect(0,0,w,h);
    for(const p of particles){
      ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.fillStyle=`rgba(255,255,255,${p.a})`;ctx.fill();
      p.y-=p.s;if(p.y<-5){p.y=h+5;p.x=Math.random()*w;}
    }
    requestAnimationFrame(draw);
  }
  draw();
})();

// ── 工具 ──
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function fmt(s,id){
  // 先转义防止 XSS，再安全替换标记格式
  let t=esc(s);
  return t
    .replace(/\n/g,'<br>')
    .replace(/\[(\d+)\]/g,'<sup class="cite-badge" data-cite="$1">[$1]</sup>')
    .replace(/~~([^~]+)~~/g,'<del class="unverified">$1</del>');
}

// ── 状态 ──
let threadId=crypto.randomUUID(),userId=parseInt(localStorage.getItem('js_user_id')||'0');
let currentView='chat';
let allMessages=[];
const convMessageCache=new Map();

// ── API ──
const api={
  async chat(msg,tid){const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg,thread_id:tid,user_id:userId})});return r.json();},
  async users(){const r=await fetch('/users');const d=await r.json();return d.users||[];},
  async deleteUser(uid){const r=await fetch('/user/'+uid,{method:'DELETE'});return r.json();},
  async deleteConversation(tid){const r=await fetch('/conversation/'+encodeURIComponent(tid)+'?user_id='+userId,{method:'DELETE'});return r.json();},
  async conversations(uid){const r=await fetch('/conversations?user_id='+uid);const d=await r.json();return d.conversations||[];},
  async analyzedJobs(){const r=await fetch('/skill_rank/_jobs');const d=await r.json();return d.jobs||[];},
  async skillRank(job,n=15){const r=await fetch('/skill_rank/'+encodeURIComponent(job)+'?top_n='+n);return r.json();},
  async skillGap(job,userSkills,n=15){const r=await fetch('/skill_gap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_name:job,user_skills:userSkills,top_n:n})});return r.json();},
  async convMsgs(tid){const r=await fetch('/conversation/'+encodeURIComponent(tid));const d=await r.json();return d.messages||[];},
  async stats(){const r=await fetch('/stats');return r.json();},
  async analyzeJob(job){const r=await fetch('/analyze_job',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_name:job})});return r.json();},
  async task(taskId){const r=await fetch('/task/'+taskId);return r.json();},
};

function lastThreadKey(uid=userId){return 'last_thread_id_'+uid;}
function savedUsers(){
  try{return JSON.parse(localStorage.getItem('js_saved_users')||'[]');}catch(_){return[];}
}
function setSavedUsers(users){
  localStorage.setItem('js_saved_users',JSON.stringify(users));
}
function removeSavedUser(uid){
  setSavedUsers(savedUsers().filter(u=>u.id!==uid));
}
async function loadConversationMessages(tid,{fresh=false}={}){
  if(!fresh&&convMessageCache.has(tid))return convMessageCache.get(tid);
  const msgs=await api.convMsgs(tid);
  convMessageCache.set(tid,msgs);
  return msgs;
}

// ── DOM ──
const $=id=>document.getElementById(id);
const el={
  chatInput:$('chatInput'),btnSend:$('btnSend'),msgList:$('messageList'),
  convList:$('convList'),btnNewChat:$('btnNewChat'),
  radarInput:$('radarInput'),btnRadarSearch:$('btnRadarSearch'),radarQuickTags:$('radarQuickTags'),radarBody:$('radarBody'),
  gapJobInput:$('gapJobInput'),btnGapLoad:$('btnGapLoad'),gapQuickTags:$('gapQuickTags'),gapSkillList:$('gapSkillList'),
  gapMarketMeta:$('gapMarketMeta'),gapExtraInput:$('gapExtraInput'),btnGapAnalyze:$('btnGapAnalyze'),btnGapClear:$('btnGapClear'),gapResult:$('gapResult'),
  researchInput:$('researchInput'),btnResearch:$('btnResearch'),researchTimeline:$('researchTimeline'),researchBody:$('researchBody'),
  userAvatar:$('userAvatar'),userName:$('userName'),userMeta:$('userMeta'),userStats:$('userStats'),
  insightContent:$('insightContent'),toastContainer:$('toastContainer'),
};

// ── 视图切换 ──
function switchView(v){
  currentView=v;
  document.querySelectorAll('.nav-icon').forEach(b=>b.classList.toggle('active',b.dataset.view===v));
  document.querySelectorAll('.view').forEach(vw=>vw.classList.remove('active'));
  const viewMap={chat:'viewChat',radar:'viewRadar',gap:'viewGap',research:'viewResearch',user:'viewUser'};
  const tgt=document.getElementById(viewMap[v]||'viewChat');
  if(tgt)tgt.classList.add('active');
  if(v==='radar')loadRadarQuickTags();
  if(v==='gap')loadGapQuickTags();
  if(v==='user')loadUserCenter();
}
document.querySelectorAll('.nav-icon').forEach(b=>b.addEventListener('click',()=>switchView(b.dataset.view)));

// ── Toast ──
function toast(msg){const d=document.createElement('div');d.className='toast';d.textContent=msg;el.toastContainer.appendChild(d);setTimeout(()=>{d.style.opacity='0';setTimeout(()=>d.remove(),300);},3000);}

// ═══════════════════════════════════════════════
// 视图1: 智能对话
// ═══════════════════════════════════════════════
async function sendMessage(){
  const text=el.chatInput.value.trim();if(!text)return;
  el.chatInput.value='';el.btnSend.disabled=true;
  addMsg('user',esc(text));
  const loadDiv=addLoading();
  try{
    // 1. 提交异步任务
    const submit=await api.chat(text,threadId);
    if(!submit.async){throw new Error('服务器未返回任务ID');}
    threadId=submit.thread_id;
    const taskId=submit.task_id;

    // 2. 轮询直到完成
    let result=null;
    for(let i=0;i<150;i++){  // 最多5分钟(150×2s)
      await new Promise(r=>setTimeout(r,2000));
      const poll=await fetch('/task/'+taskId).then(r=>r.json());
      if(poll.code!==200)break;
      const t=poll.task;
      loadDiv.textContent=t.progress||'处理中...';
      if(t.finished){
        result=t.result;
        break;
      }
    }
    loadDiv.remove();

    if(!result){throw new Error('任务未完成');}
    if(result.response.includes('共完成')&&result.knowledge?.length){
      renderResearchInline(result.response,result.knowledge);
    }else{
      addMsg('assistant',fmt(result.response));
    }
    allMessages.push({role:'user',content:text},{role:'assistant',content:result.response});
    convMessageCache.set(threadId,allMessages);
    localStorage.setItem(lastThreadKey(),threadId);
    refreshSidebar();
    updateInsight(result);
  }catch(e){loadDiv.remove();addMsg('assistant','请求出错: '+e.message);}
  el.btnSend.disabled=false;el.chatInput.focus();
}

function addMsg(role,content){
  const d=document.createElement('div');d.className='msg msg-'+role;d.innerHTML=content;el.msgList.appendChild(d);el.msgList.scrollTop=el.msgList.scrollHeight;
}
function addLoading(){
  const d=document.createElement('div');d.className='msg-loading';el.msgList.appendChild(d);el.msgList.scrollTop=el.msgList.scrollHeight;return d;
}
function renderResearchInline(summary,cards){
  const c=document.createElement('div');c.className='research-container';
  c.innerHTML='<div class="research-header">◇ 求职研究报告</div><div class="research-grid"></div>';
  const grid=c.querySelector('.research-grid');
  const cats={技能:'skill',薪资:'salary',公司:'company',面试:'interview'};
  cards.forEach((card,i)=>{
    const lines=card.split('\n'),title=lines[0].replace('## ',''),items=lines.filter(l=>l.startsWith('- ')),src=lines.find(l=>l.startsWith('*'));
    const cat=Object.entries(cats).find(([k])=>title.includes(k))?.[1]||'default';
    const elCard=document.createElement('div');elCard.className='research-card cat-'+cat;elCard.style.animationDelay=(i*0.08)+'s';
    elCard.innerHTML='<div class="rc-title">'+esc(title)+'</div><div class="rc-items">'+items.map(it=>'<span class="rc-item">'+esc(it.replace('- ',''))+'</span>').join('')+'</div>'+(src?'<div class="rc-source">'+esc(src.replace(/\*/g,''))+'</div>':'');
    grid.appendChild(elCard);
  });
  el.msgList.appendChild(c);el.msgList.scrollTop=el.msgList.scrollHeight;
}

async function switchConv(tid){
  threadId=tid;el.msgList.innerHTML='';
  localStorage.setItem(lastThreadKey(),tid);
  allMessages=await loadConversationMessages(tid,{fresh:true});
  if(!allMessages.length){
    localStorage.removeItem(lastThreadKey());
    threadId=crypto.randomUUID();
    el.msgList.innerHTML='<div style="text-align:center;margin:auto;padding:2rem;color:var(--text-muted);font-size:0.82rem;">该会话没有可恢复的消息</div>';
    refreshSidebar();
    return;
  }
  allMessages.forEach(m=>addMsg(m.role,fmt(m.content)));
  refreshSidebar();
}

async function deleteConversation(tid){
  if(!tid)return;
  const row=document.querySelector('.conv-item-wrap[data-tid="'+tid+'"]');
  if(row)row.remove();
  convMessageCache.delete(tid);
  if(localStorage.getItem(lastThreadKey())===tid)localStorage.removeItem(lastThreadKey());

  if(tid===threadId){
    threadId=crypto.randomUUID();
    allMessages=[];
    el.msgList.innerHTML='<div style="text-align:center;margin:auto;padding:2rem;color:var(--text-muted);font-size:0.82rem;line-height:1.8;">'
      +'<div style="font-size:1.5rem;margin-bottom:0.5rem;">◇</div>'
      +'<div>新对话已准备好</div>'
      +'</div>';
  }

  try{
    await api.deleteConversation(tid);
    await refreshSidebar();
    toast('已删除对话');
  }catch(e){
    await refreshSidebar();
    toast('删除失败: '+e.message);
  }
}

function updateInsight(result){
  if(!result||!result.knowledge)return;
  let h='<div style="font-weight:600;font-size:0.72rem;margin-bottom:0.5rem;">情报</div>';
  result.knowledge.slice(0,3).forEach(k=>{h+='<div style="margin-bottom:0.4rem;font-size:0.65rem;">'+esc(k.substring(0,150))+'</div>';});
  el.insightContent.innerHTML=h;
}

// ═══════════════════════════════════════════════
// 视图2: 技能雷达
// ═══════════════════════════════════════════════
async function loadRadarQuickTags(){
  const jobs=await api.analyzedJobs();if(!jobs.length)return;
  el.radarQuickTags.innerHTML=jobs.slice(0,8).map(j=>'<span class="quick-tag" data-job="'+esc(j)+'">'+esc(j)+'</span>').join('');
  el.radarQuickTags.querySelectorAll('.quick-tag').forEach(t=>t.addEventListener('click',()=>{el.radarInput.value=t.dataset.job;runRadar();}));
}
async function runRadar(){
  const job=el.radarInput.value.trim();if(!job)return;
  el.radarBody.style.alignItems='center';el.radarBody.style.justifyContent='center';
  el.radarBody.innerHTML='<div class="msg-loading"></div>';
  const result=await fetch('/skill_rank/'+encodeURIComponent(job)+'?top_n=12');
  const resData=await result.json();
  const skills=resData.data||[];
  const total=resData.total_jds||0;
  const lastUpdate=resData.last_update||'';
  if(!skills.length){el.radarBody.style.alignItems='center';el.radarBody.style.justifyContent='center';el.radarBody.innerHTML='<div class="radar-empty">未找到该岗位数据，先在对话中分析它</div>';return;}
  const max=skills[0]?.count||1;
  let h='<div class="radar-results"><div class="radar-chart-container"><canvas id="radarCanvas" width="240" height="240"></canvas></div><div class="radar-ranking"><div class="radar-job-title">'+esc(job)+' 技能雷达</div>';
  skills.forEach((s,i)=>{
    const count=Number(s.count)||0;
    const pct=max>0?Math.min(Math.round(count/max*100),100):0;
    const cls=pct>60?'hot':pct>30?'warm':'cool';
    const trend='flat';
    const trendIcon={up:'↑',down:'↓',flat:'→'},trendCls={up:'up',down:'down',flat:'flat'};
    h+='<div class="rank-row-radar"><span class="rank-num">#'+(i+1)+'</span><span class="rank-skill">'+esc(s.skill)+'</span><span class="rank-bar-wrap"><span class="rank-bar-inner '+cls+'" style="width:'+pct+'%"></span></span><span class="rank-count-text">'+count+'次</span><span class="rank-trend '+trendCls[trend]+'">'+trendIcon[trend]+'</span></div>';
  });
  h+='</div></div>';
  // 数据来源：total_jds>0 才展示具体数字，否则不展示
  if(total||lastUpdate){
    const parts=[];
    if(total)parts.push('基于 <b>'+total+'</b> 条JD');
    if(lastUpdate)parts.push('更新于 '+lastUpdate);
    h+='<div class="radar-source-bar">'+parts.join(' · ')+'</div>';
  }
  el.radarBody.innerHTML=h;
  el.radarBody.style.alignItems='flex-start';el.radarBody.style.justifyContent='flex-start';
  drawRadarChart(skills.slice(0,8),max);
}
function drawRadarChart(skills,max){
  const cv=document.getElementById('radarCanvas');if(!cv)return;
  const ctx=cv.getContext('2d'),cx=120,cy=120,r=90,n=skills.length;
  ctx.clearRect(0,0,240,240);
  // 网格
  for(let l=1;l<=4;l++){ctx.beginPath();for(let i=0;i<n;i++){const a=Math.PI*2/n*i-Math.PI/2;const x=cx+Math.cos(a)*r*l/4,y=cy+Math.sin(a)*r*l/4;i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);}ctx.closePath();ctx.strokeStyle='rgba(255,255,255,0.06)';ctx.stroke();}
  // 轴线
  for(let i=0;i<n;i++){const a=Math.PI*2/n*i-Math.PI/2;ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(cx+Math.cos(a)*r,cy+Math.sin(a)*r);ctx.strokeStyle='rgba(255,255,255,0.04)';ctx.stroke();}
  // 数据区域
  ctx.beginPath();
  for(let i=0;i<n;i++){const v=skills[i].count/max,a=Math.PI*2/n*i-Math.PI/2,x=cx+Math.cos(a)*r*v,y=cy+Math.sin(a)*r*v;i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);}
  ctx.closePath();ctx.fillStyle='rgba(59,130,246,0.12)';ctx.fill();ctx.strokeStyle='#3b82f6';ctx.lineWidth=1.5;ctx.stroke();
  // 顶点 & 标签
  for(let i=0;i<n;i++){const v=skills[i].count/max,a=Math.PI*2/n*i-Math.PI/2,x=cx+Math.cos(a)*r*v,y=cy+Math.sin(a)*r*v;ctx.beginPath();ctx.arc(x,y,3,0,Math.PI*2);ctx.fillStyle='#3b82f6';ctx.fill();const lx=cx+Math.cos(a)*(r+20),ly=cy+Math.sin(a)*(r+20);ctx.fillStyle='#e8eaed';ctx.font='9px Inter,Noto Sans SC';ctx.textAlign='center';ctx.fillText(skills[i].skill.slice(0,6),lx,ly);}
}
el.btnRadarSearch.addEventListener('click',runRadar);
el.radarInput.addEventListener('keydown',e=>{if(e.key==='Enter')runRadar();});

// ── 雷达标签折叠 ──
$('radarTagsToggle').addEventListener('click',()=>{
  const tags=$('radarQuickTags');
  const toggle=$('radarTagsToggle');
  tags.classList.toggle('collapsed');
  toggle.classList.toggle('open');
});

// ═══════════════════════════════════════════════
// 视图3: 技能差距
// ═══════════════════════════════════════════════
let gapMarketSkills=[],gapTotalJds=0,gapCurrentJob='';

function normalizeSkillText(text){
  return String(text||'')
    .split(/[,\n，、;；]+/)
    .map(s=>s.trim())
    .filter(Boolean);
}
function skillTitle(item){return typeof item==='string'?item:(item?.skill||'');}
function marketRate(item,total=gapTotalJds){
  const count=Number(item?.count)||0;
  const base=Number(item?.total_jds)||Number(total)||0;
  return base>0?Math.round(count/base*100):0;
}
function priorityClass(rate){
  if(rate>=60)return 'high';
  if(rate>=40)return 'mid';
  return 'low';
}
async function loadGapQuickTags(){
  if(!el.gapQuickTags)return;
  const jobs=await api.analyzedJobs();if(!jobs.length)return;
  el.gapQuickTags.innerHTML=jobs.slice(0,10).map(j=>'<span class="quick-tag" data-job="'+esc(j)+'">'+esc(j)+'</span>').join('');
  el.gapQuickTags.querySelectorAll('.quick-tag').forEach(t=>t.addEventListener('click',()=>{el.gapJobInput.value=t.dataset.job;loadGapMarketSkills();}));
}
async function loadGapMarketSkills(){
  const job=el.gapJobInput.value.trim();if(!job)return;
  gapCurrentJob=job;
  el.btnGapLoad.disabled=true;
  el.gapSkillList.innerHTML='<div class="msg-loading"></div>';
  el.gapResult.innerHTML='<div class="gap-result-empty">差距结果将在这里显示</div>';
  try{
    const res=await api.skillRank(job,15);
    gapMarketSkills=res.data||[];
    gapTotalJds=Number(res.total_jds)||Number(gapMarketSkills[0]?.total_jds)||0;
    renderGapSkillList(res.last_update||'');
  }catch(e){
    el.gapSkillList.innerHTML='<div class="radar-empty">请求出错: '+esc(e.message)+'</div>';
  }finally{
    el.btnGapLoad.disabled=false;
  }
}
async function triggerGapAutoAnalyze(job){
  el.gapSkillList.innerHTML='<div class="msg-loading"></div><div style="text-align:center;margin-top:0.5rem;font-size:0.72rem;color:var(--text-dim);">正在分析「'+esc(job)+'」，首次分析可能需要 3-5 分钟...</div>';
  try{
    const submit=await api.analyzeJob(job);
    if(!submit.task_id)throw new Error('服务器未返回任务ID');
    const taskId=submit.task_id;
    let result=null;
    for(let i=0;i<180;i++){  // 最多6分钟(180×2s)
      await new Promise(r=>setTimeout(r,2000));
      const poll=await api.task(taskId);
      if(poll.code!==200)break;
      const t=poll.task;
      const progressEl=el.gapSkillList.querySelector('.msg-loading');
      if(progressEl)progressEl.textContent=t.progress||'分析中...';
      if(t.finished){
        result=t.result;
        break;
      }
    }
    if(!result)throw new Error('分析超时，请稍后重试');
    // 分析完成，重新加载技能列表
    toast('「'+job+'」分析完成');
    await loadGapMarketSkills();
  }catch(e){
    el.gapSkillList.innerHTML='<div class="radar-empty">分析失败: '+esc(e.message)+'</div>';
  }
}
function renderGapSkillList(lastUpdate){
  if(!gapMarketSkills.length){
    el.gapMarketMeta.textContent='暂无数据';
    el.gapSkillList.innerHTML='<div class="radar-empty" style="text-align:center;line-height:2;">'
      +'<div style="font-size:1.5rem;margin-bottom:0.5rem;">📭</div>'
      +'<div>「'+esc(gapCurrentJob)+'」暂无技能数据</div>'
      +'<div style="margin-top:0.8rem;"><button id="btnGapAutoAnalyze" style="padding:0.5rem 1.2rem;border-radius:var(--radius);border:1px solid var(--blue);background:transparent;color:var(--blue);cursor:pointer;font-size:0.75rem;">立即分析岗位</button></div>'
      +'</div>';
    const btn=$('btnGapAutoAnalyze');
    if(btn)btn.addEventListener('click',()=>triggerGapAutoAnalyze(gapCurrentJob));
    return;
  }
  const meta=[];
  if(gapTotalJds)meta.push(gapTotalJds+' 条 JD');
  if(lastUpdate)meta.push('更新 '+lastUpdate);
  el.gapMarketMeta.textContent=meta.join(' · ')||gapCurrentJob;
  el.gapSkillList.innerHTML=gapMarketSkills.map((s,i)=>{
    const rate=marketRate(s);
    const cls=priorityClass(rate);
    return '<label class="gap-skill-row">'
      +'<input type="checkbox" class="gap-skill-check" data-idx="'+i+'">'
      +'<span class="gap-skill-main"><span class="gap-skill-name">'+esc(s.skill)+'</span><span class="gap-skill-bar"><span style="width:'+Math.max(rate,4)+'%"></span></span></span>'
      +'<span class="gap-skill-rate '+cls+'">'+rate+'%</span>'
      +'</label>';
  }).join('');
}
function collectGapSkills(){
  const selected=[...el.gapSkillList.querySelectorAll('.gap-skill-check:checked')]
    .map(input=>gapMarketSkills[Number(input.dataset.idx)]?.skill)
    .filter(Boolean);
  const extra=normalizeSkillText(el.gapExtraInput.value);
  return [...new Set([...selected,...extra])];
}
async function runGapAnalysis(){
  const job=el.gapJobInput.value.trim();if(!job)return;
  const userSkills=collectGapSkills();
  el.btnGapAnalyze.disabled=true;
  el.gapResult.innerHTML='<div class="msg-loading"></div>';
  try{
    const result=await api.skillGap(job,userSkills,15);
    if(result.code&&result.code!==200)throw new Error(result.detail||'分析失败');
    renderGapResult(result);
  }catch(e){
    el.gapResult.innerHTML='<div class="radar-empty">请求出错: '+esc(e.message)+'</div>';
  }finally{
    el.btnGapAnalyze.disabled=false;
  }
}
function renderGapResult(result){
  const ratio=Number(result.coverage_ratio)||0;
  const pct=Math.round(ratio*100);
  const status=ratio>=0.7?'竞争力强':ratio>=0.4?'需要提升':'差距较大';
  const matched=result.matched_skills||[];
  const missing=result.missing_skills||[];
  const priority=result.priority_order||[];
  const list=(items,cls)=>items.length?items.map(item=>{
    const name=skillTitle(item);
    const rate=typeof item==='string'?0:marketRate(item);
    const rateText=rate?'<span>'+rate+'%</span>':'';
    return '<li><span>'+esc(name)+'</span>'+rateText+'</li>';
  }).join(''):'<li class="gap-muted">暂无</li>';

  el.gapResult.innerHTML='<div class="gap-score">'
    +'<div><div class="gap-label">匹配度</div><div class="gap-score-num">'+pct+'%</div></div>'
    +'<span class="gap-status '+priorityClass(pct)+'">'+status+'</span>'
    +'</div>'
    +'<div class="gap-progress"><span style="width:'+Math.min(Math.max(pct,3),100)+'%"></span></div>'
    +'<div class="gap-summary">'+esc(result.summary||'暂无摘要')+'</div>'
    +'<div class="gap-result-grid">'
    +'<div class="gap-result-block matched"><div class="gap-block-title">已匹配</div><ul>'+list(matched,'matched')+'</ul></div>'
    +'<div class="gap-result-block missing"><div class="gap-block-title">待补齐</div><ul>'+list(missing,'missing')+'</ul></div>'
    +'</div>'
    +'<div class="gap-priority"><div class="gap-block-title">学习优先级</div><div class="gap-priority-tags">'
    +(priority.length?priority.map((p,i)=>'<span>'+(i+1)+'. '+esc(p)+'</span>').join(''):'<span>暂无</span>')
    +'</div></div>';
}

el.btnGapLoad.addEventListener('click',loadGapMarketSkills);
el.gapJobInput.addEventListener('keydown',e=>{if(e.key==='Enter')loadGapMarketSkills();});
el.btnGapAnalyze.addEventListener('click',runGapAnalysis);
el.btnGapClear.addEventListener('click',()=>{
  el.gapSkillList.querySelectorAll('.gap-skill-check').forEach(c=>{c.checked=false;});
  el.gapExtraInput.value='';
});
$('gapTagsToggle').addEventListener('click',()=>{
  const tags=$('gapQuickTags');
  const toggle=$('gapTagsToggle');
  tags.classList.toggle('collapsed');
  toggle.classList.toggle('open');
});

// ═══════════════════════════════════════════════
// 视图4: 深度研究
// ═══════════════════════════════════════════════
el.btnResearch.addEventListener('click',async()=>{
  const text=el.researchInput.value.trim();if(!text)return;
  el.researchTimeline.innerHTML='<span style="color:var(--green)">拆解需求</span> → <span style="color:var(--blue)">并行执行中...</span> → 聚合结果';
  el.researchBody.innerHTML='<div class="msg-loading"></div>';
  try{
    // 直调 /research 端点，绕过 ChatAgent，直接走研究流程
    const result=await fetch('/research',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic:text})}).then(r=>r.json());
    if(result.knowledge?.length){
      el.researchTimeline.innerHTML='<span style="color:var(--green)">拆解需求</span> → <span style="color:var(--green)">并行执行</span> → <span style="color:var(--green)">聚合结果</span>';
      const cats={技能:'skill',薪资:'salary',公司:'company',面试:'interview'};
      let h='<div class="research-grid">';
      result.knowledge.forEach((card,i)=>{
        const lines=card.split('\n'),title=lines[0].replace('## ',''),items=lines.filter(l=>l.startsWith('- ')),src=lines.find(l=>l.startsWith('*'));
        const cat=Object.entries(cats).find(([k])=>title.includes(k))?.[1]||'default';
        h+='<div class="research-card cat-'+cat+'" style="animation-delay:'+(i*0.08)+'s">'
          +'<div class="rc-title">'+esc(title)+'</div>'
          +'<div class="rc-items">'+items.map(it=>'<span class="rc-item">'+esc(it.replace('- ',''))+'</span>').join('')+'</div>'
          +(src?'<div class="rc-source">'+esc(src.replace(/\*/g,''))+'</div>':'')
          +'</div>';
      });
      h+='</div>';
      el.researchBody.innerHTML=h;
    }else{
      el.researchBody.innerHTML='<div class="radar-empty">未获取到研究结果</div>';
    }
    updateInsight(result);
  }catch(e){
    el.researchBody.innerHTML='<div class="radar-empty">请求出错: '+esc(e.message)+'</div>';
  }
});
el.researchInput.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();el.btnResearch.click();}});

// ═══════════════════════════════════════════════
// 视图5: 用户中心
// ═══════════════════════════════════════════════
async function loadUserCenter(){
  const name=localStorage.getItem('js_username')||('用户_'+threadId.slice(0,8));
  el.userName.textContent=name;el.userAvatar.textContent=name[0].toUpperCase();
  el.userMeta.textContent='用户ID: '+userId+' · ID不会因刷新而改变';
  // 统计
  const convs=await api.conversations(userId),jobs=await api.analyzedJobs(),s=await api.stats();
  el.userStats.innerHTML='<div class="stat-card"><div class="stat-num">'+convs.length+'</div><div class="stat-label">对话数</div></div><div class="stat-card"><div class="stat-num">'+jobs.length+'</div><div class="stat-label">分析岗位</div></div><div class="stat-card"><div class="stat-num">'+(s.skill_count||0)+'</div><div class="stat-label">技能库</div></div><div class="stat-card"><div class="stat-num">'+(s.jd_count||0)+'</div><div class="stat-label">JD总量</div></div>';
  // 用户切换列表
  loadUserSwitchList();
}
async function loadUserSwitchList(){
  const list=el.userSwitchList||$('userSwitchList');
  if(!list)return;
  let users=[];
  try{users=await api.users();}catch(_){}
  const saved=savedUsers();
  saved.forEach(s=>{if(!users.find(u=>u.id===s.id))users.push(s);});
  list.innerHTML=users.map(u=>'<div class="user-switch-item'+(u.id===userId?' current':'')+'" data-uid="'+u.id+'" data-username="'+esc(u.username)+'"><span class="user-switch-name">'+esc(u.username)+'</span><button class="btn-user-delete" data-uid="'+u.id+'" title="删除用户">×</button></div>').join('');
  list.querySelectorAll('.user-switch-item').forEach(item=>{item.addEventListener('click',()=>switchUser(parseInt(item.dataset.uid)));});
  list.querySelectorAll('.btn-user-delete').forEach(btn=>btn.addEventListener('click',e=>{e.stopPropagation();deleteUser(parseInt(btn.dataset.uid));}));
}
async function switchUser(uid){
  if(uid===userId)return;
  userId=uid;localStorage.setItem('js_user_id',String(uid));
  const saved=savedUsers();
  const found=saved.find(u=>u.id===uid);
  const row=document.querySelector('.user-switch-item[data-uid="'+uid+'"]');
  const username=found?.username||row?.dataset.username;
  if(username)localStorage.setItem('js_username',username);
  convMessageCache.clear();
  threadId=crypto.randomUUID();allMessages=[];el.msgList.innerHTML='';
  refreshSidebar();loadUserCenter();toast('已切换到 '+ (username||('用户'+uid)));
}
async function deleteUser(uid){
  if(!uid)return;
  const deletingCurrent=uid===userId;
  const row=document.querySelector('.user-switch-item[data-uid="'+uid+'"]');
  if(row)row.remove();
  removeSavedUser(uid);
  localStorage.removeItem(lastThreadKey(uid));
  convMessageCache.clear();

  try{
    const result=await api.deleteUser(uid);
    if(!result.deleted){
      toast('用户不存在或已删除');
    }

    if(deletingCurrent){
      let users=await api.users();
      if(!users.length){
        const r=await fetch('/user');
        const d=await r.json();
        users=[{id:d.user_id,username:d.username}];
      }
      const next=users[0];
      userId=next.id;
      localStorage.setItem('js_user_id',String(next.id));
      localStorage.setItem('js_username',next.username);
      threadId=crypto.randomUUID();
      allMessages=[];
      el.msgList.innerHTML='';
    }

    await refreshSidebar();
    await loadUserCenter();
    toast('已删除用户');
  }catch(e){
    await loadUserCenter();
    toast('删除失败: '+e.message);
  }
}
$('btnAddUser').addEventListener('click',async()=>{
  const name=prompt('输入新用户名（留空则随机）：');if(name===null)return;
  const r=await fetch('/user?username='+encodeURIComponent(name||''));
  const d=await r.json();
  const saved=savedUsers();
  saved.push({id:d.user_id,username:d.username});
  setSavedUsers(saved);
  switchUser(d.user_id);
});

// ═══════════════════════════════════════════════
// 侧边栏
// ═══════════════════════════════════════════════
async function refreshSidebar(){
  if(!userId)return;
  const convs=await api.conversations(userId);
  const checked=await Promise.all(convs.map(async c=>({...c,messages:await loadConversationMessages(c.thread_id)})));
  const visible=checked.filter(c=>c.messages.length>0);
  el.convList.innerHTML=visible.length?visible.map(c=>'<div class="conv-item-wrap'+(c.thread_id===threadId?' active':'')+'" data-tid="'+c.thread_id+'"><button class="conv-item" data-tid="'+c.thread_id+'">'+esc(c.title||'未命名')+'</button><button class="btn-conv-delete" data-tid="'+c.thread_id+'" title="删除对话">×</button></div>').join(''):'<span style="color:var(--text-muted);font-size:0.62rem;padding:0.4rem;">暂无对话</span>';
  el.convList.querySelectorAll('.conv-item').forEach(b=>b.addEventListener('click',()=>switchConv(b.dataset.tid)));
  el.convList.querySelectorAll('.btn-conv-delete').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();deleteConversation(b.dataset.tid);}));
}

// ── 事件 ──
el.btnSend.addEventListener('click',sendMessage);
el.chatInput.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();}});
el.btnNewChat.addEventListener('click',()=>{threadId=crypto.randomUUID();allMessages=[];el.msgList.innerHTML='';localStorage.removeItem(lastThreadKey());refreshSidebar();});

// ── 启动 ──
(async function init(){
  if(!userId){const r=await fetch('/user');const d=await r.json();userId=d.user_id;localStorage.setItem('js_user_id',String(userId));localStorage.setItem('js_username',d.username);}
  const lastTid=localStorage.getItem(lastThreadKey());
  if(lastTid){threadId=lastTid;}
  const msgs=lastTid?await loadConversationMessages(threadId,{fresh:true}):[];
  allMessages=msgs;
  if(lastTid&&!msgs.length){
    localStorage.removeItem(lastThreadKey());
    convMessageCache.delete(lastTid);
    threadId=crypto.randomUUID();
  }
  if(!msgs.length){
    el.msgList.innerHTML='<div style="text-align:center;margin:auto;padding:2rem;color:var(--text-muted);font-size:0.82rem;line-height:1.8;">'
      +'<div style="font-size:1.5rem;margin-bottom:0.5rem;">◇</div>'
      +'<div>欢迎使用 <b style="color:var(--text);">JobLab</b></div>'
      +'<div style="margin-top:0.3rem;">输入岗位名称开始分析，例如：<span style="color:var(--blue);cursor:pointer;" onclick="document.getElementById(\'chatInput\').value=\'Python后端\';">Python后端</span></div>'
      +'</div>';
  }else{
    msgs.forEach(m=>addMsg(m.role,fmt(m.content)));
  }
  refreshSidebar();el.chatInput.focus();
})();
