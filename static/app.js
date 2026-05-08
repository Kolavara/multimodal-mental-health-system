// ── Theme Management ──
function initTheme() {
  const stored = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', stored);
}
initTheme();

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', current);
  localStorage.setItem('theme', current);
  // Optional: trigger chart updates if they need color adjustments (Chart.js handles CSS var changes decently, but forcing update helps)
  if(typeof severityChart !== 'undefined' && severityChart) severityChart.update();
  if(typeof riskTrendChart !== 'undefined' && riskTrendChart) riskTrendChart.update();
  if(typeof adminTrendChart !== 'undefined' && adminTrendChart) adminTrendChart.update();
}

// ── State ──
let token = localStorage.getItem('token');
let user = JSON.parse(localStorage.getItem('user')||'null');
let ws = null;
let videoStream = null;
let frameInterval = null;
let timerInterval = null;
let sessionStart = 0;

// ── Voice Recording State ──
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// ── Auth ──
function switchAuthTab(tab) {
  document.getElementById('login-form').classList.toggle('hidden', tab!=='login');
  document.getElementById('register-form').classList.toggle('hidden', tab!=='register');
  document.querySelectorAll('#auth-tabs .tab-btn').forEach((b,i)=>b.classList.toggle('active', (tab==='login'?i===0:i===1)));
}

async function doLogin() {
  const u=document.getElementById('login-username').value, p=document.getElementById('login-password').value;
  try {
    const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    const d=await r.json();
    if(!r.ok) throw new Error(d.detail||'Login failed');
    token=d.token; user=d.user;
    localStorage.setItem('token',token); localStorage.setItem('user',JSON.stringify(user));
    enterApp();
  } catch(e) { const el=document.getElementById('login-error'); el.textContent=e.message; el.classList.remove('hidden'); }
}

async function doRegister() {
  const n=document.getElementById('reg-name').value, u=document.getElementById('reg-username').value, p=document.getElementById('reg-password').value;
  try {
    const r=await fetch('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p,display_name:n})});
    const d=await r.json();
    if(!r.ok) throw new Error(d.detail||'Registration failed');
    document.getElementById('reg-success').textContent='Account created! Switch to Login.'; document.getElementById('reg-success').classList.remove('hidden');
    document.getElementById('reg-error').classList.add('hidden');
  } catch(e) { document.getElementById('reg-error').textContent=e.message; document.getElementById('reg-error').classList.remove('hidden'); }
}

function quickLogin(u,p) { document.getElementById('login-username').value=u; document.getElementById('login-password').value=p; doLogin(); }
function doLogout() { localStorage.clear(); token=null; user=null; if(ws){ws.close();ws=null;} if(videoStream){videoStream.getTracks().forEach(t=>t.stop());} clearInterval(frameInterval); clearInterval(timerInterval); location.reload(); }

// ── App Entry ──
function enterApp() {
  document.getElementById('login-page').classList.remove('active');
  document.getElementById('app-shell').classList.remove('hidden');
  document.getElementById('sidebar-name').textContent=user.display_name;
  document.getElementById('sidebar-role').textContent=user.role;
  document.getElementById('sidebar-session-title').textContent = user.role === 'admin' ? 'Administrator' : 'Patient Session';
  // Hide nav items based on role
  const navs=document.querySelectorAll('.nav-item');
  if(user.role==='admin') { 
    navs.forEach(n=>{const p=n.dataset.page; if(p!=='admin')n.style.display='none';}); 
    document.getElementById('patient-controls').style.display='none';
    navigate('admin'); 
  }
  else { 
    navs.forEach(n=>{const p=n.dataset.page; if(p==='admin')n.style.display='none';}); 
    navigate('psychologist'); 
    // Don't auto-start session — wait for user to click "Start Session"
  }
}

function startSession() {
  // Show immediate feedback
  addChatMsg('system', '🔗 Connecting to clinical session...');
  // Swap buttons
  document.getElementById('start-session-btn').classList.add('hidden');
  document.getElementById('end-session-sidebar-btn').classList.remove('hidden');
  connectWS();
}

// ── Routing ──
function navigate(page) {
  document.querySelectorAll('.main-content .page').forEach(p=>p.classList.remove('active'));
  const el=document.getElementById('page-'+page); if(el)el.classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.page===page));
  if(page==='reports') loadReports();
  if(page==='admin') loadAdmin();
  if(page==='psychiatrist') initPsychiatristForm();
}

function updateTimer() {
  const s=Math.floor((Date.now()-sessionStart)/1000), h=Math.floor(s/3600), m=Math.floor((s%3600)/60), sec=s%60;
  document.getElementById('session-timer').textContent=[h,m,sec].map(v=>String(v).padStart(2,'0')).join(':');
}

// ── WebSocket ──
function connectWS() {
  if (ws && ws.readyState <= 1) { ws.close(); }
  const proto=location.protocol==='https:'?'wss':'ws';
  ws=new WebSocket(`${proto}://${location.host}/ws/session?token=${token}`);
  ws.onopen=()=>{
    sessionStart = Date.now();
    timerInterval = setInterval(updateTimer, 1000);
  };
  ws.onmessage=e=>{
    const msg=JSON.parse(e.data);
    if(msg.type==='status') addChatMsg('system','⏳ '+msg.message);
    else if(msg.type==='init_complete') addChatMsg('system','✅ Engines ready.');
    else if(msg.type==='chat_response') { addChatMsg('assistant',msg.message); document.getElementById('chat-agent-label').innerHTML='💬 Clinical Interaction — '+(msg.agent||'Psychologist').charAt(0).toUpperCase()+(msg.agent||'psychologist').slice(1)+' Active'; }
    else if(msg.type==='chat_restore') { addChatMsg('user',msg.message); }
    else if(msg.type==='voice_result') handleVoiceResult(msg);
    else if(msg.type==='telemetry') updateTelemetry(msg);
    else if(msg.type==='facial') updateFacialOverlay(msg);
    else if(msg.type==='evaluation') showEvaluation(msg);
    else if(msg.type==='halted') { addChatMsg('system','🚨 HALTED: '+msg.reason); }
    else if(msg.type==='error') addChatMsg('system','⚠️ '+msg.message);
  };
  ws.onerror=(err)=>{
    console.error('WebSocket error:', err);
    addChatMsg('system','⚠️ Connection error. Please try again.');
    document.getElementById('start-session-btn').classList.remove('hidden');
    document.getElementById('end-session-sidebar-btn').classList.add('hidden');
  };
  ws.onclose=()=>{ addChatMsg('system','Connection closed.'); };
}

// ── Chat ──
function addChatMsg(role, text) {
  const div=document.createElement('div');
  div.className='chat-msg '+(role==='user'?'user':'assistant');
  div.innerHTML='<div class="msg-label">'+(role==='user'?'You':role==='system'?'System':'🧠 AI')+'</div>'+text.replace(/\n/g,'<br>');
  const c=document.getElementById('chat-messages'); c.appendChild(div); c.scrollTop=c.scrollHeight;
}

function sendChat() {
  const inp=document.getElementById('chat-input'), msg=inp.value.trim();
  if(!msg||!ws||ws.readyState!==1)return;
  addChatMsg('user',msg); ws.send(JSON.stringify({type:'chat',message:msg})); inp.value='';
}

// ── Voice Recording ──
function toggleMic() {
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
    audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = () => {
      // Stop all audio tracks
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      sendVoiceMessage(blob);
    };

    mediaRecorder.start();
    isRecording = true;
    const micBtn = document.getElementById('mic-btn');
    micBtn.classList.add('recording');
    micBtn.textContent = '⏹';
    micBtn.title = 'Recording... Click to stop & send';
    // Show recording indicator in chat
    addChatMsg('system', '<div class="voice-processing">🎤 Recording... <div class="dot-pulse"><span></span><span></span><span></span></div></div>');
  } catch (err) {
    console.error('Mic access denied:', err);
    addChatMsg('system', '⚠️ Microphone access denied. Please allow microphone permissions.');
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
  isRecording = false;
  const micBtn = document.getElementById('mic-btn');
  micBtn.classList.remove('recording');
  micBtn.textContent = '🎤';
  micBtn.title = 'Click to record voice';
  // Immediately remove the "Recording..." indicator
  removeVoiceIndicators();
}

function removeVoiceIndicators() {
  const chatContainer = document.getElementById('chat-messages');
  chatContainer.querySelectorAll('.voice-processing').forEach(el => {
    const msgDiv = el.closest('.chat-msg');
    if (msgDiv) msgDiv.remove();
  });
}

function sendVoiceMessage(blob) {
  if (!ws || ws.readyState !== 1) {
    addChatMsg('system', '⚠️ Not connected. Cannot send voice message.');
    return;
  }
  // Show processing indicator
  addChatMsg('system', '<div class="voice-processing">🔄 Analyzing voice & prosody... <div class="dot-pulse"><span></span><span></span><span></span></div></div>');

  const reader = new FileReader();
  reader.onloadend = () => {
    const base64 = reader.result.split(',')[1];
    ws.send(JSON.stringify({ type: 'voice', data: base64 }));
  };
  reader.readAsDataURL(blob);
}

function handleVoiceResult(msg) {
  // Remove ALL voice-processing indicators from the chat
  removeVoiceIndicators();

  if (msg.error) {
    addChatMsg('system', '⚠️ ' + msg.error);
    return;
  }

  // Display transcribed text as user message with prosody badge
  const transcript = msg.transcript || '';
  const prosody = msg.prosody || {};
  const distress = msg.speech_distress || 0;

  let prosodyHtml = '';
  if (prosody.pitch_mean) {
    prosodyHtml = '<div class="prosody-badge">' +
      '🎤 Voice Analyzed | ' +
      'Pitch: ' + prosody.pitch_mean.toFixed(0) + 'Hz | ' +
      'Rate: ' + (prosody.speech_rate_wps || 0).toFixed(1) + ' wps | ' +
      'Distress: ' + (distress * 100).toFixed(0) + '%' +
      '</div>';
  }

  const div = document.createElement('div');
  div.className = 'chat-msg user';
  div.innerHTML = '<div class="msg-label">You 🎤</div>' +
    transcript.replace(/\n/g, '<br>') + prosodyHtml;
  const c = document.getElementById('chat-messages');
  c.appendChild(div);
  c.scrollTop = c.scrollHeight;
}

function endSession() { 
  if(ws&&ws.readyState===1) {
    clearInterval(timerInterval);
    ws.send(JSON.stringify({type:'end_session'})); 
  }
}
function emergencyHalt() { if(ws&&ws.readyState===1) ws.send(JSON.stringify({type:'halt'})); }

// ── Telemetry ──
let severityChart = null;
let sevHistory = [];
let sevLabels = [];
let sevUpdateCounter = 0;

function initSeverityChart() {
  const ctx = document.getElementById('severity-chart');
  if (!ctx) return;
  severityChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: sevLabels,
      datasets: [{
        label: 'Severity',
        data: sevHistory,
        borderColor: '#6366f1',
        backgroundColor: 'rgba(99, 102, 241, 0.1)',
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHitRadius: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { min: 0, max: 1, ticks: { stepSize: 0.25, color: '#94a3b8', font: { size: 10 } }, grid: { color: 'rgba(148,163,184,0.1)' } }
      }
    }
  });
}

function updateTelemetry(d) {
  const sev=d.severity||0, avg=d.avg_severity||0, f=d.facial||{};
  document.getElementById('tel-distress').textContent=sev.toFixed(2);
  document.getElementById('tel-distress-bar').style.width=(sev*100)+'%';
  document.getElementById('tel-avg-risk').textContent=(avg*100).toFixed(1)+'%';
  document.getElementById('tel-avg-bar').style.width=(avg*100)+'%';
  const em=f.dominant_emotion||'—';
  document.getElementById('tel-emotion').textContent=em.charAt(0).toUpperCase()+em.slice(1);
  document.getElementById('tel-valence').textContent=(f.facial_valence||0).toFixed(2);
  document.getElementById('tel-eye').textContent=((f.eye_contact_ratio||0)*100).toFixed(0)+'%';
  document.getElementById('tel-blink').textContent=(f.blink_rate||0).toFixed(1);
  document.getElementById('vid-severity').textContent='Severity: '+sev.toFixed(2);
  document.getElementById('vid-emotion').textContent='Emotion: '+(em.charAt(0).toUpperCase()+em.slice(1));
  // Safety
  if(d.halted) {
    // Show halt indicator in Psychologist page if needed, or just chat
    addChatMsg('system', '🚨 SYSTEM IS HALTED: ' + d.halt_reason);
  }
  // Severity trend chart (update every ~2s = every 4th telemetry push at 500ms interval)
  sevUpdateCounter++;
  if(sevUpdateCounter % 4 === 0) {
    if(!severityChart) initSeverityChart();
    const elapsed = Math.floor((Date.now()-sessionStart)/1000);
    const mins = Math.floor(elapsed/60);
    const secs = elapsed%60;
    sevLabels.push(mins+':'+String(secs).padStart(2,'0'));
    sevHistory.push(sev);
    if(sevHistory.length > 60) { sevHistory.shift(); sevLabels.shift(); }
    if(severityChart) severityChart.update('none');
  }
}

function resetSafety() { if(ws&&ws.readyState===1) ws.send(JSON.stringify({type:'reset'})); }

function updateFacialOverlay(d) { /* facial data already handled via telemetry */ }

// ── Video ──
let videoRunning = false;

async function startVideo() {
  if (videoRunning) {
    // Stop video
    if (frameInterval) { clearInterval(frameInterval); frameInterval = null; }
    if (videoStream) { videoStream.getTracks().forEach(t => t.stop()); videoStream = null; }
    document.getElementById('local-video').srcObject = null;
    document.getElementById('start-video-btn').textContent = '▶ Start';
    videoRunning = false;
    return;
  }
  try {
    videoStream = await navigator.mediaDevices.getUserMedia({video:{width:640,height:480},audio:false});
    document.getElementById('local-video').srcObject = videoStream;
    const devices = await navigator.mediaDevices.enumerateDevices();
    const sel = document.getElementById('camera-select'); sel.innerHTML = '';
    devices.filter(d => d.kind === 'videoinput').forEach(d => { const o = document.createElement('option'); o.value = d.deviceId; o.text = d.label || 'Camera'; sel.add(o); });
    document.getElementById('start-video-btn').textContent = '⏸ Stop';
    videoRunning = true;
    const canvas = document.getElementById('video-canvas'), ctx = canvas.getContext('2d');
    canvas.width = 640; canvas.height = 480;
    frameInterval = setInterval(() => {
      if (!ws || ws.readyState !== 1) return;
      const video = document.getElementById('local-video');
      ctx.drawImage(video, 0, 0, 640, 480);
      const jpeg = canvas.toDataURL('image/jpeg', 0.5).split(',')[1];
      ws.send(JSON.stringify({type:'frame', data:jpeg}));
    }, 200);
  } catch(e) { alert('Camera error: ' + e.message); }
}

// ── Evaluation ──
function renderMarkdown(text) {
  // Simple markdown: **bold**, newlines → <br>
  return (text||'').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
}

function showEvaluation(d) {
  const el=document.getElementById('evaluation-result'); el.classList.remove('hidden');
  let html = '';

  // Severity + Disorder metrics at top
  html += '<div class="grid-2 mb-3">';
  html += '<div class="metric-card"><div class="metric-label">Avg Severity</div><div class="metric-value">'+(d.avg_severity*100).toFixed(1)+'%</div></div>';
  html += '<div class="metric-card"><div class="metric-label">Likely Disorder</div><div class="metric-value">'+(d.disorder||'Unknown')+'</div></div>';
  html += '</div>';

  // Multimodal Clinical Analysis — the main output
  html += '<div class="neu-card" style="border-left:4px solid var(--accent-primary);margin-bottom:1.5rem">';
  html += '<p class="section-header">🧬 Multimodal Clinical Analysis</p>';
  html += '<div style="line-height:1.8;color:var(--text-primary)">'+renderMarkdown(d.session_summary)+'</div>';
  html += '</div>';

  // Collapsible raw detail sections
  html += '<details class="expander mt-2"><summary>🎭 Facial Analysis (Raw)</summary><div class="expander-content"><p>'+(d.facial||'No facial data.')+'</p></div></details>';
  html += '<details class="expander"><summary>🎤 Speech Analysis (Raw)</summary><div class="expander-content"><p>'+(d.speech||'No speech data.')+'</p></div></details>';
  html += '<details class="expander"><summary>💬 Conversation Analysis (Raw)</summary><div class="expander-content"><p>'+(d.conversation||'No conversation data.')+'</p></div></details>';
  html += '<details class="expander"><summary>📋 Agent Conclusion (Raw)</summary><div class="expander-content"><p>'+(d.conclusion||'No conclusion.')+'</p></div></details>';

  document.getElementById('eval-content').innerHTML = html;
  window._evalData=d;
}

// ── Reports Page ──
let riskTrendChart = null;

async function loadReports() {
  const el=document.getElementById('reports-content'), ld=document.getElementById('reports-loading');
  try {
    const r=await fetch('/api/reports',{headers:{Authorization:'Bearer '+token}});
    const reports=await r.json(); ld.classList.add('hidden'); el.classList.remove('hidden');
    if(!reports.length){el.innerHTML='<div class="neu-card"><div class="alert alert-info">📭 No reports yet. Complete a session and click "End Session & Evaluate" to generate your first report.</div></div>';return;}

    // Calculate stats
    const total = reports.length;
    const avgRisk = reports.reduce((a,r)=>a+(r.avg_severity||0),0)/total;
    const riskLabel = avgRisk>=0.7?'HIGH':avgRisk>=0.3?'MODERATE':'LOW';
    const latestDate = (reports[0].timestamp||'').split('T')[0];
    const psychCount = reports.filter(r=>r.psychologist_conclusion).length;
    const integratedCount = reports.filter(r=>r.integrated_summary).length;

    let html = '<div class="neu-card"><p class="section-header">📊 Your Summary</p>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;">';

    // Left: metrics
    html += '<div>';
    html += '<div class="grid-2 gap-2">';
    html += '<div class="metric-card"><div class="metric-label">Total Sessions</div><div class="metric-value">'+total+'</div></div>';
    html += '<div class="metric-card"><div class="metric-label">Avg Risk Level</div><div class="metric-value">'+riskLabel+' ('+Math.round(avgRisk*100)+'%)</div></div>';
    html += '<div class="metric-card"><div class="metric-label">Last Visit</div><div class="metric-value">'+latestDate+'</div></div>';
    html += '<div class="metric-card"><div class="metric-label">Integrated Reports</div><div class="metric-value">'+integratedCount+'</div></div>';
    html += '</div>';
    // Analysis breakdown dots
    html += '<div style="display:flex;gap:1.5rem;margin-top:0.75rem;flex-wrap:wrap;">';
    html += '<div style="display:flex;align-items:center;gap:0.4rem;"><span style="width:10px;height:10px;border-radius:50%;background:#48BB78;display:inline-block;"></span><span class="text-xs text-muted">Psychologist: <strong>'+psychCount+'</strong></span></div>';
    html += '<div style="display:flex;align-items:center;gap:0.4rem;"><span style="width:10px;height:10px;border-radius:50%;background:#9F7AEA;display:inline-block;"></span><span class="text-xs text-muted">Integrated: <strong>'+integratedCount+'</strong></span></div>';
    html += '</div>';
    html += '</div>';

    // Right: chart
    html += '<div style="position:relative;height:200px;"><canvas id="risk-trend-chart"></canvas></div>';
    html += '</div></div>';

    // Report cards
    html+='<h3 class="mb-2">📋 All Reports ('+reports.length+')</h3>';
    reports.forEach((rp,i)=>{
      const sev=rp.avg_severity||0, sevL=sev>=0.7?'HIGH':sev>=0.3?'MODERATE':'LOW', sevC=sev>=0.7?'sev-high':sev>=0.3?'sev-moderate':'sev-low';
      html+='<div class="report-card"><div class="report-header"><div><span class="text-xs text-muted" style="text-transform:uppercase;letter-spacing:0.08em">Session #'+(reports.length-i)+'</span><h4>📅 '+(rp.timestamp||'').replace('T',' ').slice(0,19)+'</h4></div><div class="flex gap-1"><span class="badge-pill '+sevC+'">'+sevL+' ('+(sev*100).toFixed(0)+'%)</span></div></div>';
      html+='<div style="margin-top:0.5rem">'+(rp.psychologist_conclusion?'<span class="badge badge-green">🧠 Psychologist ✓</span>':'')+(rp.integrated_summary?'<span class="badge badge-purple">🧬 Integrated ✓</span>':'')+'</div>';
      html+='<details class="expander mt-2"><summary>🧠 Psychologist Findings</summary><div class="expander-content">'+(rp.psychologist_conclusion?'<p><strong>Facial:</strong> '+(rp.psychologist_facial||'N/A')+'</p><p><strong>Speech:</strong> '+(rp.psychologist_speech||'N/A')+'</p><p><strong>Conversation:</strong> '+(rp.psychologist_conversation||'N/A')+'</p><p><strong>Conclusion:</strong> '+rp.psychologist_conclusion+'</p>':'<p class="text-muted">No data.</p>')+'</div></details>';
      
      // Psychiatrist Findings
      let psychHtml = '<p class="text-muted">No psychiatric lab data.</p>';
      try {
        let hasData = false;
        let htmlParts = [];
        
        // Show abnormalities
        const ab = typeof rp.psychiatrist_abnormalities === 'string' ? JSON.parse(rp.psychiatrist_abnormalities) : rp.psychiatrist_abnormalities;
        if(ab && ab.length) {
          hasData = true;
          htmlParts.push('<p class="text-sm font-semibold mb-1" style="color:var(--error-color)">Abnormal Findings:</p>');
          htmlParts.push(ab.map(a => `<div class="mb-2 pl-2" style="border-left: 2px solid var(--error-color)"><strong>⚠️ ${a.param}: ${a.value}</strong><br><span class="text-xs">Disorder: ${a.disorder}</span><br><span class="text-xs">Solution: ${a.solution}</span></div>`).join(''));
        }
        
        // Show normal params
        const pa = typeof rp.psychiatrist_params === 'string' ? JSON.parse(rp.psychiatrist_params) : rp.psychiatrist_params;
        if(pa && Object.keys(pa).length) {
          hasData = true;
          // Filter out the ones that are already in abnormalities
          const abKeys = (ab || []).map(a => a.param);
          const normalKeys = Object.keys(pa).filter(k => !abKeys.includes(k));
          
          if (normalKeys.length > 0) {
              if (htmlParts.length > 0) htmlParts.push('<div class="mt-3"></div>');
              htmlParts.push('<p class="text-sm font-semibold mb-1" style="color:var(--success-color)">Normal Findings:</p>');
              htmlParts.push('<div class="grid-2 gap-1">');
              normalKeys.forEach(k => {
                  htmlParts.push(`<div class="text-sm">✅ <strong>${k}</strong>: ${pa[k]}</div>`);
              });
              htmlParts.push('</div>');
          }
        }
        
        if (hasData) psychHtml = htmlParts.join('');
      } catch(e) {}
      html+='<details class="expander"><summary>⚕️ Psychiatrist Findings</summary><div class="expander-content">'+psychHtml+'</div></details>';
      
      html+='<details class="expander"><summary>🧬 Integrated Summary</summary><div class="expander-content">'+(rp.integrated_summary||'<p class="text-muted">No integrated summary.</p>')+'</div></details></div>';
    });
    el.innerHTML=html;

    // Render risk trend chart
    setTimeout(()=>{
      const ctx = document.getElementById('risk-trend-chart');
      if(!ctx) return;
      // Reports are newest-first, reverse for chronological order
      const reversed = [...reports].reverse();
      const labels = reversed.map((_,i)=>'#'+(i+1));
      const data = reversed.map(r=>Math.round((r.avg_severity||0)*100));

      if(riskTrendChart) riskTrendChart.destroy();
      riskTrendChart = new Chart(ctx, {
        type:'line',
        data:{
          labels,
          datasets:[{
            label:'Risk %',
            data,
            borderColor:'#667eea',
            backgroundColor:'rgba(102,126,234,0.08)',
            borderWidth:2.5,
            fill:true,
            tension:0.3,
            pointRadius:4,
            pointBackgroundColor:'#667eea',
            pointHoverRadius:6,
          }]
        },
        options:{
          responsive:true,
          maintainAspectRatio:false,
          plugins:{
            legend:{display:false},
            title:{display:true,text:'Risk Level Trend',color:'#4A5568',font:{size:12}},
            annotation: undefined,
          },
          scales:{
            x:{title:{display:true,text:'Session #',font:{size:10},color:'#94a3b8'},ticks:{font:{size:9},color:'#94a3b8'},grid:{display:false}},
            y:{min:0,max:100,title:{display:true,text:'Risk %',font:{size:10},color:'#94a3b8'},ticks:{stepSize:25,font:{size:9},color:'#94a3b8'},grid:{color:'rgba(226,232,240,0.3)'}},
          },
        },
        plugins:[{
          id:'thresholdLine',
          afterDraw(chart){
            const yScale=chart.scales.y;
            const y=yScale.getPixelForValue(70);
            const ctx2=chart.ctx;
            ctx2.save();
            ctx2.setLineDash([4,3]);
            ctx2.strokeStyle='rgba(229,62,62,0.45)';
            ctx2.lineWidth=1.5;
            ctx2.beginPath();
            ctx2.moveTo(chart.chartArea.left,y);
            ctx2.lineTo(chart.chartArea.right,y);
            ctx2.stroke();
            ctx2.restore();
          }
        }]
      });
    },50);
  } catch(e){el.innerHTML='<div class="alert alert-error">'+e.message+'</div>'; ld.classList.add('hidden'); el.classList.remove('hidden');}
}

// ── Admin Page ──
async function loadAdmin() {
  const el=document.getElementById('admin-content'), ld=document.getElementById('admin-loading');
  try {
    const r=await fetch('/api/admin/users',{headers:{Authorization:'Bearer '+token}});
    if(!r.ok) throw new Error('Admin access denied');
    const users=await r.json(); ld.classList.add('hidden'); el.classList.remove('hidden');
    if(!users.length){el.innerHTML='<div class="neu-card"><div class="alert alert-info">No patients found.</div></div>';return;}
    el.innerHTML='<h3 class="mb-2">👥 Registered Patients ('+users.length+')</h3><div class="grid-3" id="admin-grid"></div><div id="admin-detail" class="hidden"></div>';
    const grid=document.getElementById('admin-grid');
    users.forEach(u=>{
      const sev=u.latest_report?.avg_severity||0, sevL=sev>=0.7?'HIGH':sev>=0.3?'MODERATE':'LOW', sevC=sev>=0.7?'var(--accent-danger)':sev>=0.3?'#D69E2E':'var(--accent-success)';
      grid.innerHTML+='<div class="patient-card"><div><div class="avatar">👤</div><h4>'+u.display_name+'</h4><p class="text-xs text-muted">@'+u.username+'</p></div><div class="mt-2"><div class="flex justify-between mb-1"><div><span class="text-xs text-muted">SESSIONS</span><br><strong>'+(u.report_count||0)+'</strong></div><div><span class="text-xs text-muted">RISK</span><br><strong style="color:'+sevC+'">'+sevL+'</strong></div></div></div><button class="btn btn-full mt-2" onclick="viewPatient('+u.id+',\''+u.display_name+'\')">View Reports</button></div>';
    });
  } catch(e){el.innerHTML='<div class="alert alert-error">'+e.message+'</div>'; ld.classList.add('hidden'); el.classList.remove('hidden');}
}

let adminTrendChart = null;

async function viewPatient(uid,name) {
  document.getElementById('admin-grid').classList.add('hidden');
  const det=document.getElementById('admin-detail'); det.classList.remove('hidden');
  det.innerHTML='<button class="btn mb-2" onclick="backToGrid()">← Back</button><h3>'+name+'\'s Reports</h3><div class="spinner"></div>';
  const r=await fetch('/api/admin/user/'+uid+'/reports',{headers:{Authorization:'Bearer '+token}});
  const reports=await r.json();

  // Calculate stats
  const total = reports.length;
  const avgRisk = total ? reports.reduce((a,r)=>a+(r.avg_severity||0),0)/total : 0;
  const riskLabel = avgRisk>=0.7?'HIGH':avgRisk>=0.3?'MODERATE':'LOW';
  const latestDate = total ? (reports[0].timestamp||'').split('T')[0] : '—';
  const psychCount = reports.filter(r=>r.psychologist_conclusion).length;
  const integratedCount = reports.filter(r=>r.integrated_summary).length;

  let html='<button class="btn mb-2" onclick="backToGrid()">← Back</button><h3 class="mb-2">'+name+'\'s Reports ('+reports.length+')</h3>';

  // Summary card
  if(total) {
    html += '<div class="neu-card"><p class="section-header">📊 Patient Summary</p>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;">';
    // Left: metrics
    html += '<div>';
    html += '<div class="grid-2 gap-2">';
    html += '<div class="metric-card"><div class="metric-label">Total Sessions</div><div class="metric-value">'+total+'</div></div>';
    html += '<div class="metric-card"><div class="metric-label">Avg Risk Level</div><div class="metric-value">'+riskLabel+' ('+Math.round(avgRisk*100)+'%)</div></div>';
    html += '<div class="metric-card"><div class="metric-label">Last Visit</div><div class="metric-value">'+latestDate+'</div></div>';
    html += '<div class="metric-card"><div class="metric-label">Integrated Reports</div><div class="metric-value">'+integratedCount+'</div></div>';
    html += '</div>';
    html += '<div style="display:flex;gap:1.5rem;margin-top:0.75rem;flex-wrap:wrap;">';
    html += '<div style="display:flex;align-items:center;gap:0.4rem;"><span style="width:10px;height:10px;border-radius:50%;background:#48BB78;display:inline-block;"></span><span class="text-xs text-muted">Psychologist: <strong>'+psychCount+'</strong></span></div>';
    html += '<div style="display:flex;align-items:center;gap:0.4rem;"><span style="width:10px;height:10px;border-radius:50%;background:#9F7AEA;display:inline-block;"></span><span class="text-xs text-muted">Integrated: <strong>'+integratedCount+'</strong></span></div>';
    html += '</div>';
    html += '</div>';
    // Right: chart
    html += '<div style="position:relative;height:200px;"><canvas id="admin-risk-trend-chart"></canvas></div>';
    html += '</div></div>';
  }

  // Report cards
  reports.forEach((rp,i)=>{
    const sev=rp.avg_severity||0, sevL=sev>=0.7?'HIGH':sev>=0.3?'MODERATE':'LOW', sevC=sev>=0.7?'sev-high':sev>=0.3?'sev-moderate':'sev-low';
    html+='<div class="report-card"><div class="report-header"><div><span class="text-xs text-muted" style="text-transform:uppercase;letter-spacing:0.08em">Session #'+(reports.length-i)+'</span><h4>📅 '+(rp.timestamp||'').replace('T',' ').slice(0,19)+'</h4></div><div class="flex gap-1"><span class="badge-pill '+sevC+'">'+sevL+' ('+(sev*100).toFixed(0)+'%)</span></div></div>';
    html+='<div style="margin-top:0.5rem">'+(rp.psychologist_conclusion?'<span class="badge badge-green">🧠 Psychologist ✓</span>':'')+(rp.integrated_summary?'<span class="badge badge-purple">🧬 Integrated ✓</span>':'')+'</div>';
    html+='<details class="expander mt-2"><summary>🧠 Psychologist Findings</summary><div class="expander-content">'+(rp.psychologist_conclusion?'<p><strong>Facial:</strong> '+(rp.psychologist_facial||'N/A')+'</p><p><strong>Speech:</strong> '+(rp.psychologist_speech||'N/A')+'</p><p><strong>Conversation:</strong> '+(rp.psychologist_conversation||'N/A')+'</p><p><strong>Conclusion:</strong> '+rp.psychologist_conclusion+'</p>':'<p class="text-muted">No data.</p>')+'</div></details>';
    
    // Psychiatrist Findings
    let psychHtml = '<p class="text-muted">No psychiatric lab data.</p>';
    try {
      let hasData = false;
      let htmlParts = [];
      
      const ab = typeof rp.psychiatrist_abnormalities === 'string' ? JSON.parse(rp.psychiatrist_abnormalities) : rp.psychiatrist_abnormalities;
      if(ab && ab.length) {
        hasData = true;
        htmlParts.push('<p class="text-sm font-semibold mb-1" style="color:var(--error-color)">Abnormal Findings:</p>');
        htmlParts.push(ab.map(a => `<div class="mb-2 pl-2" style="border-left: 2px solid var(--error-color)"><strong>⚠️ ${a.param}: ${a.value}</strong><br><span class="text-xs">Disorder: ${a.disorder}</span><br><span class="text-xs">Solution: ${a.solution}</span></div>`).join(''));
      }
      
      const pa = typeof rp.psychiatrist_params === 'string' ? JSON.parse(rp.psychiatrist_params) : rp.psychiatrist_params;
      if(pa && Object.keys(pa).length) {
        hasData = true;
        const abKeys = (ab || []).map(a => a.param);
        const normalKeys = Object.keys(pa).filter(k => !abKeys.includes(k));
        
        if (normalKeys.length > 0) {
            if (htmlParts.length > 0) htmlParts.push('<div class="mt-3"></div>');
            htmlParts.push('<p class="text-sm font-semibold mb-1" style="color:var(--success-color)">Normal Findings:</p>');
            htmlParts.push('<div class="grid-2 gap-1">');
            normalKeys.forEach(k => {
                htmlParts.push(`<div class="text-sm">✅ <strong>${k}</strong>: ${pa[k]}</div>`);
            });
            htmlParts.push('</div>');
        }
      }
      
      if (hasData) psychHtml = htmlParts.join('');
    } catch(e) {}
    html+='<details class="expander"><summary>⚕️ Psychiatrist Findings</summary><div class="expander-content">'+psychHtml+'</div></details>';
    
    html+='<details class="expander"><summary>🧬 Integrated Summary</summary><div class="expander-content">'+(rp.integrated_summary||'<p class="text-muted">No integrated summary.</p>')+'</div></details></div>';
  });
  det.innerHTML=html;

  // Render admin risk trend chart
  if(total) {
    setTimeout(()=>{
      const ctx = document.getElementById('admin-risk-trend-chart');
      if(!ctx) return;
      const reversed = [...reports].reverse();
      const labels = reversed.map((_,i)=>'#'+(i+1));
      const data = reversed.map(r=>Math.round((r.avg_severity||0)*100));

      if(adminTrendChart) adminTrendChart.destroy();
      adminTrendChart = new Chart(ctx, {
        type:'line',
        data:{
          labels,
          datasets:[{
            label:'Risk %',
            data,
            borderColor:'#667eea',
            backgroundColor:'rgba(102,126,234,0.08)',
            borderWidth:2.5,
            fill:true,
            tension:0.3,
            pointRadius:4,
            pointBackgroundColor:'#667eea',
            pointHoverRadius:6,
          }]
        },
        options:{
          responsive:true,
          maintainAspectRatio:false,
          plugins:{
            legend:{display:false},
            title:{display:true,text:'Risk Level Trend',color:'#4A5568',font:{size:12}},
          },
          scales:{
            x:{title:{display:true,text:'Session #',font:{size:10},color:'#94a3b8'},ticks:{font:{size:9},color:'#94a3b8'},grid:{display:false}},
            y:{min:0,max:100,title:{display:true,text:'Risk %',font:{size:10},color:'#94a3b8'},ticks:{stepSize:25,font:{size:9},color:'#94a3b8'},grid:{color:'rgba(226,232,240,0.3)'}},
          },
        },
        plugins:[{
          id:'thresholdLine',
          afterDraw(chart){
            const yScale=chart.scales.y;
            const y=yScale.getPixelForValue(70);
            const ctx2=chart.ctx;
            ctx2.save();
            ctx2.setLineDash([4,3]);
            ctx2.strokeStyle='rgba(229,62,62,0.45)';
            ctx2.lineWidth=1.5;
            ctx2.beginPath();
            ctx2.moveTo(chart.chartArea.left,y);
            ctx2.lineTo(chart.chartArea.right,y);
            ctx2.stroke();
            ctx2.restore();
          }
        }]
      });
    },50);
  }
}

function backToGrid(){document.getElementById('admin-grid').classList.remove('hidden');document.getElementById('admin-detail').classList.add('hidden');}

// ── Psychiatrist ──
const PARAMS=['Cortisol_AM','TSH','PHQ-9','GAD-7','MADRS','YMRS','PANSS','PCL-5','CAGE-AID'];
const RANGES={Cortisol_AM:[5,25],TSH:[0.4,4],'PHQ-9':[0,4],'GAD-7':[0,4],MADRS:[0,6],YMRS:[0,12],PANSS:[30,60],'PCL-5':[0,30],'CAGE-AID':[0,0]};
let psychData=null;

function initPsychiatristForm(){
  const el=document.getElementById('manual-params');
  if(el.children.length)return;
  PARAMS.forEach(p=>{const r=RANGES[p]; el.innerHTML+='<div class="number-input"><label>'+p+' (Normal: '+r[0]+'–'+r[1]+')</label><input type="number" id="param-'+p+'" class="input-field" value="0" min="0" max="200" step="0.1"></div>';});
  // Show integrated section if we have eval data but no psych data yet
  checkShowIntegratedSection();
}

async function uploadPDF(){
  const f=document.getElementById('pdf-upload').files[0]; if(!f)return;
  const nameEl=document.getElementById('file-name');
  nameEl.textContent='Selected: '+f.name; nameEl.classList.remove('hidden');
  const fd=new FormData(); fd.append('file',f);
  const r=await fetch('/api/psychiatrist/analyze-pdf',{method:'POST',headers:{Authorization:'Bearer '+token},body:fd});
  const d=await r.json(); if(d.error){alert(d.error);return;} psychData=d; showPsychResults(d);
}

async function analyzeManual(){
  const data={}; PARAMS.forEach(p=>{const v=parseFloat(document.getElementById('param-'+p).value); if(v>0)data[p]=v;});
  if(!Object.keys(data).length){alert('Enter at least one value');return;}
  const r=await fetch('/api/psychiatrist/analyze-manual',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(data)});
  psychData=await r.json(); showPsychResults(psychData);
}

function showPsychResults(d){
  // ── Diagnostic Summary metrics ──
  document.getElementById('psych-results').classList.remove('hidden');
  document.getElementById('psych-count').textContent=Object.keys(d.params).length;
  document.getElementById('psych-abnormal').textContent=d.abnormal.length;
  const riskLevel = d.abnormal.length>=3?'HIGH':d.abnormal.length>=1?'MODERATE':'LOW';
  document.getElementById('psych-risk').textContent=riskLevel;

  // ── Abnormalities with severity bars ──
  let abHtml='';
  if(d.abnormal.length){
    abHtml='<div class="neu-card"><p class="section-header">🚨 Abnormalities Detected</p>';
    d.abnormal.forEach(a=>{
      const range = a.max - a.min + 0.000001;
      const deviation = Math.min(Math.abs(a.value - a.max) / range, 1.0);
      abHtml+='<details class="expander" open><summary>⚠️ '+a.param+' — Value: '+a.value+' (Normal: '+a.min+'–'+a.max+')</summary><div class="expander-content">';
      abHtml+='<p><strong>Likely Disorder(s):</strong> '+a.disorder+'</p>';
      abHtml+='<p><strong>Recommended Action:</strong> '+a.solution+'</p>';
      abHtml+='<div class="text-xs text-muted mt-1 mb-1">Deviation Severity: '+(deviation*100).toFixed(0)+'%</div>';
      abHtml+='<div class="progress-bar"><div class="progress-fill" style="width:'+(deviation*100)+'%;background:'+(deviation>=0.7?'var(--accent-danger)':deviation>=0.3?'#D69E2E':'var(--accent-success)')+'"></div></div>';
      abHtml+='</div></details>';
    });
    abHtml+='</div>';
  }
  document.getElementById('psych-abnormal-list').innerHTML=abHtml;

  // ── Normal Parameters ──
  let normHtml='';
  if(d.normal && d.normal.length){
    normHtml='<div class="neu-card"><p class="section-header">✅ Parameters Within Normal Limits</p>';
    d.normal.forEach(n=>{
      normHtml+='<p class="text-sm text-muted" style="margin-bottom:0.35rem">✓ <strong>'+n.param+'</strong> — '+n.value+' (Normal: '+n.min+'–'+n.max+')</p>';
    });
    normHtml+='</div>';
  }
  document.getElementById('psych-normal-list').innerHTML=normHtml;

  // ── Show integrated section ──
  checkShowIntegratedSection();
}

function checkShowIntegratedSection(){
  const hasEval=!!window._evalData;
  const hasData=!!psychData;
  if(!hasEval && !hasData) return;

  const el=document.getElementById('psych-integrated');
  el.classList.remove('hidden');

  // Source badges
  let srcHtml='';
  if(hasEval) srcHtml+='<span class="badge badge-green">🧠 Psychological Session</span> ';
  if(hasData) srcHtml+='<span class="badge badge-blue">⚕️ Psychiatric Lab Data</span>';
  document.getElementById('psych-sources').innerHTML=srcHtml;

  // Source data previews
  let previewHtml='<h4 class="mt-2">🧠 Psychologist Session Evaluation</h4>';
  if(hasEval){
    previewHtml+='<details class="expander"><summary>View Psychologist Findings</summary><div class="expander-content">';
    previewHtml+='<p>'+(window._evalData.facial||'N/A')+'</p>';
    previewHtml+='<p>'+(window._evalData.speech||'N/A')+'</p>';
    previewHtml+='<p>'+(window._evalData.conversation||'N/A')+'</p>';
    previewHtml+='<p><strong>Agent Conclusion:</strong> '+(window._evalData.conclusion||'N/A')+'</p>';
    previewHtml+='</div></details>';
  } else {
    previewHtml+='<div class="alert alert-info">No psychologist session data. You can still generate a diagnosis from psychiatric data alone.</div>';
  }

  previewHtml+='<h4 class="mt-2">⚕️ Psychiatrist Lab/Scale Report</h4>';
  if(hasData && psychData.abnormal){
    previewHtml+='<details class="expander"><summary>View Psychiatrist Findings</summary><div class="expander-content">';
    (psychData.abnormal||[]).forEach(a=>{previewHtml+='<p class="text-sm text-muted">- '+a.param+': '+a.value+' (Normal: '+a.min+'–'+a.max+') → '+a.disorder+'</p>';});
    (psychData.normal||[]).forEach(n=>{previewHtml+='<p class="text-sm text-muted">- '+n.param+': '+n.value+' (Normal: '+n.min+'–'+n.max+') → Within normal limits</p>';});
    previewHtml+='</div></details>';
  } else {
    previewHtml+='<div class="alert alert-info">No psychiatric lab data. You can still generate a diagnosis from the psychological session alone.</div>';
  }

  previewHtml+='<p class="text-xs text-muted mt-2"><strong>Active data sources:</strong> '+(hasEval?'🧠 Psychological Session':'')+(hasEval&&hasData?' + ':'')+(hasData?'⚕️ Psychiatric Lab Data':'')+'</p>';

  // Insert previews before the generate button
  let existingPreview = document.getElementById('psych-source-previews');
  if(!existingPreview){
    existingPreview = document.createElement('div');
    existingPreview.id = 'psych-source-previews';
    document.getElementById('psych-sources').after(existingPreview);
  }
  existingPreview.innerHTML = previewHtml;
}

async function generateIntegrated(){
  const hasEval=!!window._evalData, hasData=!!psychData;
  if(!hasEval && !hasData){alert('No data available for integration.');return;}
  const body={has_psychological:hasEval,has_psychiatric:hasData,psychologist_text:hasEval?('Facial: '+(window._evalData.facial||'')+'\nSpeech: '+(window._evalData.speech||'')+'\nConversation: '+(window._evalData.conversation||'')+'\nConclusion: '+(window._evalData.conclusion||'')):'',psychiatrist_text:hasData?[...(psychData.abnormal||[]).map(a=>a.param+': '+a.value+' (Normal: '+a.min+'–'+a.max+') → '+a.disorder),...(psychData.normal||[]).map(n=>n.param+': '+n.value+' → Within normal limits')].join('\n'):'',abnormal:psychData?.abnormal||[],normal:psychData?.normal||[],params:psychData?.params||{},report_id:window._evalData?.report_id||null,psych_severity:window._evalData?.avg_severity||0,evaluation:window._evalData||{}};
  document.getElementById('psych-integrated-result').innerHTML='<div class="spinner"></div><p class="text-center text-muted">🧬 Generating integrated clinical summary...</p>';
  document.getElementById('psych-integrated-result').classList.remove('hidden');
  try {
    const r=await fetch('/api/psychiatrist/integrate',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok) throw new Error(d.detail||'Failed');
    document.getElementById('psych-integrated-result').innerHTML='<hr><h4>🩺 Integrated Clinical Assessment</h4><div style="white-space:pre-wrap;line-height:1.7">'+d.summary+'</div>';
  } catch(e) {
    document.getElementById('psych-integrated-result').innerHTML='<div class="alert alert-error">⚠️ Failed to generate summary: '+e.message+'</div>';
  }
}

// ── Init ──
if(token&&user) enterApp(); 

