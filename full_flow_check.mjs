import {mkdirSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';

const baseUrl = process.env.DROPOUT_SIGNAL_BROWSER_BASE;
const debugPort = process.env.DROPOUT_SIGNAL_DEBUG_PORT;
const counselorCookie = process.env.DROPOUT_SIGNAL_COUNSELOR_COOKIE;
const adminCookie = process.env.DROPOUT_SIGNAL_ADMIN_COOKIE;
const screenshotDir = process.env.DROPOUT_SIGNAL_SCREENSHOT_DIR;
const uploadCsvPath = process.env.DROPOUT_SIGNAL_UPLOAD_CSV;

function assert(condition, detail) {
  if (!condition) throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
}

async function waitFor(label, read, predicate = Boolean, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  let last;
  while (Date.now() < deadline) {
    try {
      last = await read();
      if (predicate(last)) return last;
    } catch (error) {
      last = error?.message || String(error);
    }
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  throw new Error(`Timed out waiting for ${label}; last=${JSON.stringify(last)}`);
}

class DevTools {
  constructor(url) {
    this.url = url;
    this.nextId = 0;
    this.pending = new Map();
    this.consoleErrors = [];
  }
  async connect() {
    this.socket = new WebSocket(this.url);
    this.socket.addEventListener('message', event => {
      const message = JSON.parse(typeof event.data === 'string' ? event.data : Buffer.from(event.data).toString('utf8'));
      if (message.id && this.pending.has(message.id)) {
        const {resolve, reject} = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(JSON.stringify(message.error)));
        else resolve(message.result || {});
        return;
      }
      if (message.method === 'Runtime.exceptionThrown') this.consoleErrors.push(message.params?.exceptionDetails?.text || 'Runtime exception');
      if (message.method === 'Log.entryAdded' && message.params?.entry?.level === 'error') this.consoleErrors.push(message.params.entry.text);
    });
    await Promise.race([
      new Promise((resolve, reject) => {
        this.socket.addEventListener('open', resolve, {once: true});
        this.socket.addEventListener('error', reject, {once: true});
      }),
      new Promise((_, reject) => setTimeout(() => reject(new Error('DevTools connection timed out')), 6000)),
    ]);
  }
  call(method, params = {}) {
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`DevTools command timed out: ${method}`));
      }, 15000);
      this.pending.set(id, {
        resolve: value => { clearTimeout(timer); resolve(value); },
        reject: error => { clearTimeout(timer); reject(error); },
      });
      this.socket.send(JSON.stringify({id, method, params}));
    });
  }
  async evaluate(expression) {
    const result = await this.call('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true, userGesture: true});
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || JSON.stringify(result.exceptionDetails));
    if (result.result?.subtype === 'error') throw new Error(result.result.description || 'Browser JavaScript failed');
    return result.result?.value;
  }
}

async function postForm(path, values) {
  const response = await fetch(baseUrl + path, {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: new URLSearchParams(values),
  });
  return {status: response.status, text: await response.text()};
}

async function newPage(devtools, role, cookie, path) {
  await devtools.call('Network.setCookie', {name: 'session', value: cookie, url: baseUrl, httpOnly: true});
  await devtools.call('Page.navigate', {url: baseUrl + path});
  await waitFor(`${role} dashboard`, () => devtools.evaluate("document.readyState === 'complete' && !!document.querySelector('.page')"));
  await new Promise(resolve => setTimeout(resolve, 1700));
  const identity = await devtools.evaluate(`({path:location.pathname,pages:document.querySelectorAll('.page').length,renderer:document.querySelectorAll('#authoritative-dashboard-ui').length})`);
  assert(identity.path === path && identity.pages > 0 && identity.renderer === 1, {role, identity});
  console.log(`PASS ${role} dashboard loaded`, identity);
}

async function activateContaining(devtools, selector) {
  return devtools.evaluate(`(() => {
    const node=document.querySelector(${JSON.stringify(selector)});
    const page=node?.closest('.page');
    if(!node||!page)return null;
    document.querySelectorAll('.page.active').forEach(item=>item.classList.remove('active'));
    page.classList.add('active');
    return page.id;
  })()`);
}

async function layoutCheck(devtools, label) {
  const result = await devtools.evaluate(`(() => {
    const active=document.querySelector('.page.active');
    const visible=node=>{const s=getComputedStyle(node);return s.display!=='none'&&s.visibility!=='hidden'&&node.getClientRects().length>0};
    const offenders=[...document.querySelectorAll('body *')].filter(visible).map(node=>{const r=node.getBoundingClientRect();return {tag:node.tagName,id:node.id,cls:String(node.className||'').slice(0,80),parent:String(node.parentElement?.className||node.parentElement?.id||'').slice(0,100),grandparent:String(node.parentElement?.parentElement?.className||node.parentElement?.parentElement?.id||'').slice(0,100),left:Math.round(r.left),right:Math.round(r.right),width:Math.round(r.width),scrollWidth:node.scrollWidth,clientWidth:node.clientWidth}}).filter(item=>item.right>innerWidth+3||item.left < -3).slice(0,8);
    const describe=selector=>{const node=document.querySelector(selector);if(!node)return null;const r=node.getBoundingClientRect(),s=getComputedStyle(node);return {selector,left:r.left,right:r.right,width:r.width,marginLeft:s.marginLeft,paddingLeft:s.paddingLeft,paddingRight:s.paddingRight,boxSizing:s.boxSizing,flex:s.flex};};
    return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,active:active?.id||'',main:describe('.main'),topbar:describe('.topbar'),actions:describe('.topbar-actions'),offenders};
  })()`);
  assert(result.documentWidth <= result.viewport + 2 && result.bodyWidth <= result.viewport + 2 && !result.offenders.length, {label, ...result});
  return result;
}

async function validateResponsive(devtools, label) {
  for (const width of [1440, 1024, 768, 390]) {
    await devtools.call('Emulation.setDeviceMetricsOverride', {width, height: 1000, deviceScaleFactor: 1, mobile: width < 600});
    await new Promise(resolve => setTimeout(resolve, 180));
    await layoutCheck(devtools, `${label}-${width}`);
  }
  await devtools.call('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
  console.log(`PASS ${label} responsive layouts at 1440/1024/768/390`);
}

async function validateSummaryCards(devtools, gridSelector, role) {
  const pageId = await activateContaining(devtools, gridSelector);
  assert(pageId, `${role} summary page was not found`);
  await waitFor(`${role} summary cards`, () => devtools.evaluate(`document.querySelectorAll(${JSON.stringify(gridSelector + ' .summary-person')}).length`), count => count >= 3);
  const cards = await devtools.evaluate(`(() => {
    const grid=document.querySelector(${JSON.stringify(gridSelector)});
    return [...grid.querySelectorAll('.summary-person')].slice(0,8).map(card=>{const style=getComputedStyle(card),rect=card.getBoundingClientRect();return {name:card.innerText.trim(),borderWidth:style.borderTopWidth,borderStyle:style.borderTopStyle,borderColor:style.borderTopColor,radius:style.borderRadius,width:rect.width,height:rect.height,role:card.getAttribute('role'),tabindex:card.getAttribute('tabindex')}});
  })()`);
  assert(cards.length >= 3 && cards.every(card => parseFloat(card.borderWidth) >= 1 && card.borderStyle !== 'none' && card.width >= 150 && card.height >= 60 && card.role === 'button' && card.tabindex === '0'), {role, cards});
  const modal = await devtools.evaluate(`(() => {const card=document.querySelector(${JSON.stringify(gridSelector + ' .summary-person')});card.click();const modal=document.getElementById('operation-action-modal');return {title:modal?.querySelector('h2')?.textContent||'',text:modal?.innerText||'',facts:modal?.querySelectorAll('.student-summary-facts>div').length||0};})()`);
  assert(modal.title && modal.facts >= 8 && /ML dropout probability/i.test(modal.text) && /AI confidence/i.test(modal.text) && /Fused final score/i.test(modal.text), {role, modal});
  await devtools.evaluate("document.getElementById('operation-action-modal')?.remove()");
  console.log(`PASS ${role} AI Student Summary uses bordered interactive cards`, cards[0]);
  await validateResponsive(devtools, `${role}-summary`);
}

async function validateAllPages(devtools, role) {
  const ids = await devtools.evaluate(`[...document.querySelectorAll('.page')].map(page=>page.id).filter(Boolean)`);
  assert(ids.length >= 5, {role, ids});
  for (const id of ids) {
    await devtools.evaluate(`document.querySelectorAll('.page.active').forEach(page=>page.classList.remove('active'));document.getElementById(${JSON.stringify(id)}).classList.add('active')`);
    await new Promise(resolve => setTimeout(resolve, 35));
    await layoutCheck(devtools, `${role}-${id}`);
  }
  console.log(`PASS ${role} all ${ids.length} pages have no horizontal viewport breakage`);
}

async function validateApi(devtools) {
  const result = await devtools.evaluate(`(async()=>{
    const paths=['/api/health','/api/dataset/status','/api/model-metrics','/api/stats','/api/students?limit=5','/api/all-students','/api/tables','/api/fairness','/api/dataset/experience','/api/dataset/insights','/api/transcripts','/whatsapp/conversations'];
    const responses=[];
    for(const path of paths){const response=await fetch(path,{cache:'no-store'});let body={};try{body=await response.json()}catch{}responses.push({path,status:response.status,body});}
    return responses;
  })()`);
  assert(result.every(item => item.status === 200), result.map(({path,status})=>({path,status})));
  const status = result.find(item => item.path === '/api/dataset/status').body;
  const metrics = result.find(item => item.path === '/api/model-metrics').body;
  assert(status.dataset_loaded && Number(status.record_count) === 4424, status);
  assert(metrics.dataset_loaded && metrics.ensemble?.quality_gate?.passed && Number(metrics.ensemble?.metrics?.accuracy) >= .88 && (metrics.training_history?.points || []).length === 10, metrics);
  console.log('PASS read-only API surface and active model metadata', {records: status.record_count, accuracy: metrics.ensemble.metrics.accuracy, history: metrics.training_history.points.length});
}

async function validateBrowserUpload(devtools) {
  assert(uploadCsvPath, 'DROPOUT_SIGNAL_UPLOAD_CSV is required for browser upload testing');
  const resetControl = await devtools.evaluate(`(() => {
    const button=[...document.querySelectorAll('button')].find(node => /^reset dataset$/i.test(node.textContent.trim()));
    if (!button) return null;
    window.confirm=()=>true;
    button.click();
    return {owned:button.dataset.explicitResetOwned||'', disabled:button.disabled};
  })()`);
  assert(resetControl?.owned === 'true', resetControl);
  await waitFor('empty dataset dashboard state', () => devtools.evaluate("fetch('/api/dataset/status',{cache:'no-store'}).then(response=>response.json())"), value => value && !value.dataset_loaded);
  const emptyPresentation = await waitFor('clean empty dashboard presentation', () => devtools.evaluate(`(() => ({
    hasBrokenBadge: /[–-]\\s*predicted dropouts/i.test(document.body.innerText),
    visibleBadges: [...document.querySelectorAll('.risk-fixed-badge')].filter(node => !node.hidden && getComputedStyle(node).display !== 'none').map(node => node.textContent),
  }))()`), value => !value.hasBrokenBadge && !value.visibleBadges.length);
  assert(!emptyPresentation.hasBrokenBadge && !emptyPresentation.visibleBadges.length, emptyPresentation);
  await waitFor('dataset upload input', () => devtools.evaluate("!!document.getElementById('dataset-file-input')"));
  const ownedInput = await devtools.evaluate("document.getElementById('dataset-file-input')?.dataset.backgroundOwned || ''");
  assert(ownedInput === 'true', 'The retired synchronous upload listener still owns the dataset input');
  const remote = await devtools.call('Runtime.evaluate', {
    expression: "document.getElementById('dataset-file-input')",
    returnByValue: false,
  });
  const objectId = remote.result?.objectId;
  assert(objectId, 'Could not resolve the live dataset upload input');
  await devtools.call('DOM.setFileInputFiles', {files: [uploadCsvPath], objectId});
  const job = await waitFor('browser upload accepted', () => devtools.evaluate(`(() => {
    try { return JSON.parse(localStorage.getItem('dropout-signal-background-upload') || 'null'); }
    catch (_) { return null; }
  })()`), value => value?.id && ['queued', 'processing', 'uploading'].includes(value.state), 30000);
  const liveOverlay = await waitFor('server-authoritative upload overlay', () => devtools.evaluate(`(() => {
    const overlay = document.getElementById('dataset-training-overlay');
    return overlay ? {owned: overlay.dataset.backgroundUpload, text: overlay.innerText} : null;
  })()`), value => value?.owned === 'true');
  assert(!/Training Logistic Regression/i.test(liveOverlay.text), liveOverlay);
  const terminal = await waitFor('browser upload training completion', () => devtools.evaluate(`(async () => {
    const response = await fetch('/api/dataset/upload-status?job_id=${encodeURIComponent(job.id)}', {cache:'no-store'});
    if (!response.ok) return {status: response.status};
    return response.json();
  })()`), value => value?.state === 'complete' || value?.state === 'failed' || value?.state === 'canceled', 420000);
  assert(terminal.state === 'complete' && terminal.status?.dataset_loaded, terminal);
  await waitFor('activated browser dataset', () => devtools.evaluate("fetch('/api/dataset/status').then(response => response.json())"), value => value?.dataset_loaded && value.record_count === 4424, 30000);
  const overlay = await devtools.evaluate("document.getElementById('dataset-training-overlay')?.innerText || ''");
  assert(!/failed|canceled/i.test(overlay), {terminal, overlay});
  await devtools.evaluate("window.__fullFlowPreReloadDocument = true");
  await devtools.call('Page.reload', {ignoreCache:true});
  await waitFor('new dashboard document after browser refresh', () => devtools.evaluate("typeof window.__fullFlowPreReloadDocument === 'undefined' && document.readyState === 'complete' && !!document.querySelector('.page')"));
  await new Promise(resolve => setTimeout(resolve, 1200));
  const persisted = await waitFor('active dataset survives refresh', () => devtools.evaluate("fetch('/api/dataset/status',{cache:'no-store'}).then(response=>response.json())"), value => value?.dataset_loaded && value.record_count === 4424, 30000);
  const refreshedUi = await devtools.evaluate(`(() => ({
    brokenBadge: /[–-]\\s*predicted dropouts/i.test(document.body.innerText),
    ownedInput: document.getElementById('dataset-file-input')?.dataset.backgroundOwned || '',
    overlayCount: document.querySelectorAll('#dataset-training-overlay').length,
  }))()`);
  assert(!refreshedUi.brokenBadge && refreshedUi.ownedInput === 'true' && refreshedUi.overlayCount === 0, {persisted, refreshedUi});
  console.log('PASS real browser CSV upload, background four-model training, and cohort activation', {job: job.id, records: terminal.status.record_count});
  console.log('PASS active dataset survives browser refresh with no stale progress or broken risk badge');
}

async function validateModelEvidence(devtools) {
  const pageId = await activateContaining(devtools, '#page-model-evidence');
  assert(pageId, 'Model evidence page was not found');
  await devtools.evaluate("window.selectDataLayer?.('model')");
  const evidence = await waitFor('training evidence charts', () => devtools.evaluate(`(() => {const panel=document.getElementById('runtime-training-evidence');return panel?{text:panel.innerText,charts:panel.querySelectorAll('svg').length,lines:panel.querySelectorAll('polyline').length}:null;})()`), value => value?.charts === 2 && value.lines === 4);
  assert(/Ensemble accuracy/i.test(evidence.text) && /Model Accuracy/i.test(evidence.text) && /Model Loss/i.test(evidence.text) && /Quality gate\s*Passed/i.test(evidence.text), evidence);
  const staleLoading = await devtools.evaluate("/loading model evidence/i.test(document.getElementById('page-model-evidence')?.innerText || '')");
  assert(!staleLoading, 'The completed model evidence view still contains its loading placeholder');
  console.log('PASS real per-dataset accuracy/loss evidence rendered', {charts:evidence.charts, lines:evidence.lines});
}

async function simulateLanguage(callSid, name, languageSpeech, expectedCode) {
  const welcome = await postForm(`/voice/welcome?student_id=${encodeURIComponent(callSid)}&student_name=${encodeURIComponent(name)}&ml_risk=0.55`, {CallSid:callSid,To:'+15550123456'});
  assert(welcome.status === 200 && /Which language do you prefer/i.test(welcome.text), welcome);
  const language = await postForm(`/voice/language?sid=${encodeURIComponent(callSid)}`, {CallSid:callSid,SpeechResult:languageSpeech,Confidence:'0.96'});
  assert(language.status === 200 && language.text.includes(`language=\"${expectedCode}\"`), {expectedCode, response:language.text});
  const state = await fetch(baseUrl + '/api/transcripts').then(response => response.json());
  const session = state.sessions[callSid];
  assert(session.language_code === expectedCode && session.questions.length === 4, session);
  return session;
}

async function validateVoiceFlow() {
  const completeAnswers = async (callSid, answers) => {
    for (let index=0; index<answers.length; index++) {
      const response = await postForm(`/voice/respond?q=${index}&sid=${encodeURIComponent(callSid)}`, {CallSid:callSid,SpeechResult:answers[index],Confidence:'0.94'});
      assert(response.status === 200, response);
    }
    const state = await fetch(baseUrl + '/api/transcripts').then(response => response.json());
    return state.sessions[callSid];
  };
  const retrySid = 'CA-LANGUAGE-RETRY';
  await postForm(`/voice/welcome?student_id=RETRY&student_name=Retry%20Student&ml_risk=0.5`, {CallSid:retrySid,To:'+15550123456'});
  const retry = await postForm(`/voice/language?sid=${retrySid}&nospeech=1`, {CallSid:retrySid});
  assert(/did not hear that properly/i.test(retry.text), retry.text);
  await simulateLanguage('CA-ENGLISH', 'English Student', 'English', 'en-IN');
  await simulateLanguage('CA-HINDI', 'Hindi Student', 'हिंदी', 'hi-IN');
  await simulateLanguage('CA-KANNADA', 'Kannada Student', 'ಕನ್ನಡ', 'kn-IN');

  const noSpeech = await postForm('/voice/respond?q=0&sid=CA-ENGLISH&nospeech=1', {CallSid:'CA-ENGLISH'});
  assert(/Could you please repeat your answer/i.test(noSpeech.text), noSpeech.text);
  let state = await fetch(baseUrl + '/api/transcripts').then(response => response.json());
  assert(Object.keys(state.sessions['CA-ENGLISH'].answers).length === 0, state.sessions['CA-ENGLISH']);

  const positive = [
    'Everything is going great and my studies are manageable.',
    'Attendance is good and there are no problems.',
    'I am confident and enjoying the coursework.',
    'I am excited to continue and graduate.',
  ];
  const completed = await completeAnswers('CA-ENGLISH', positive);
  assert(completed.status === 'completed' && Object.keys(completed.answers).length === 4 && completed.risk_tier === 'LOW' && completed.ai_confidence > 0 && completed.fused_risk_score < .4, completed);

  const hindi = await completeAnswers('CA-HINDI', [
    'मेरी पढ़ाई अच्छी और ठीक चल रही है।',
    'मैं उत्साहित हूँ और सब ठीक है।',
    'मैं पढ़ाई जारी रखना चाहता हूँ।',
    'कॉलेज का अनुभव अच्छा है।',
  ]);
  assert(hindi.status === 'completed' && Object.keys(hindi.answers).length === 4 && hindi.language_code === 'hi-IN', hindi);

  const kannada = await completeAnswers('CA-KANNADA', [
    'ಓದು ತುಂಬಾ ಕಷ್ಟವಾಗಿದೆ ಮತ್ತು ಒತ್ತಡ ಇದೆ.',
    'ಶುಲ್ಕ ಮತ್ತು ಗೈರು ಹಾಜರಿ ಸಮಸ್ಯೆಯಾಗಿದೆ.',
    'ನಾನು ಕಾಲೇಜು ಬಿಡುವ ಬಗ್ಗೆ ಯೋಚಿಸುತ್ತಿದ್ದೇನೆ.',
    'ಮುಂದುವರಿಸುವುದು ಕಷ್ಟ, ನಾನು ಓದು ಬಿಡಬಹುದು.',
  ]);
  assert(kannada.status === 'completed' && Object.keys(kannada.answers).length === 4 && kannada.language_code === 'kn-IN' && kannada.risk_tier === 'HIGH', kannada);

  await simulateLanguage('CA-MEDIUM', 'Medium Student', 'English', 'en-IN');
  const medium = await completeAnswers('CA-MEDIUM', [
    'This semester has had a mixture of different experiences.',
    'My schedule changes from week to week.',
    'I am considering which resources might be useful.',
    'I have not decided what I want next semester.',
  ]);
  assert(medium.status === 'completed' && Object.keys(medium.answers).length === 4 && medium.risk_tier === 'MEDIUM', medium);
  console.log('PASS complete English/Hindi/Kannada spoken-answer flows and actual fused LOW/MEDIUM/HIGH outcomes');
}

async function validateRandomCalls(devtools) {
  const calls = await devtools.evaluate(`(async()=>{const rows=[];for(let i=0;i<8;i++){const response=await fetch('/api/manual-call',{method:'POST'});rows.push(await response.json());}return rows;})()`);
  assert(calls.every(call => call.student_id && call.student_name && call.call_sid && !call.error), calls);
  assert(new Set(calls.map(call => call.student_id)).size >= 2 && calls.every(call => call.student_name !== 'Achal Sangami'), calls);
  assert(calls.every(call => call.academic_profile?.attendance_rate && call.academic_profile?.lowest_subject), calls);
  console.log('PASS random scored-student selection and academic call context', calls.slice(0,3).map(call=>({id:call.student_id,name:call.student_name,tier:call.risk_tier})));
}

async function screenshot(devtools, filename) {
  mkdirSync(screenshotDir, {recursive:true});
  const capture = await devtools.call('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
  writeFileSync(join(screenshotDir, filename), Buffer.from(capture.data, 'base64'));
}

async function main() {
  console.log('START full system browser regression');
  const targets = await waitFor('Chrome target', async () => fetch(`http://127.0.0.1:${debugPort}/json`).then(response => response.json()), list => list.some(item => item.type === 'page'));
  const target = targets.find(item => item.type === 'page');
  const devtools = new DevTools(target.webSocketDebuggerUrl);
  await devtools.connect();
  for (const domain of ['Page.enable','Runtime.enable','Log.enable','Network.enable']) await devtools.call(domain);
  await devtools.call('Emulation.setDeviceMetricsOverride', {width:1440,height:1000,deviceScaleFactor:1,mobile:false});

  await newPage(devtools, 'counselor', counselorCookie, '/counselor');
  await validateBrowserUpload(devtools);
  await validateApi(devtools);
  await validateSummaryCards(devtools, '#summary-students', 'counselor');
  await validateRandomCalls(devtools);
  await validateAllPages(devtools, 'counselor');

  await newPage(devtools, 'admin', adminCookie, '/admin');
  await validateSummaryCards(devtools, '#admin-summary-grid', 'admin');
  await screenshot(devtools, 'admin-student-summary-cards.png');
  await validateModelEvidence(devtools);
  await screenshot(devtools, 'admin-model-evidence.png');
  await validateAllPages(devtools, 'admin');

  await validateVoiceFlow();
  const meaningfulErrors = devtools.consoleErrors.filter(error => !/favicon|Failed to load resource.*404/i.test(error));
  assert(!meaningfulErrors.length, {consoleErrors: meaningfulErrors});
  console.log('PASS no uncaught browser JavaScript or console errors');
  console.log('PASS FULL SYSTEM BROWSER REGRESSION');
  devtools.socket.close();
}

main().catch(error => {
  console.error(error?.stack || error);
  process.exit(1);
});
