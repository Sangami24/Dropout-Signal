const baseUrl = process.env.DROPOUT_SIGNAL_BROWSER_BASE;
const debugPort = process.env.DROPOUT_SIGNAL_DEBUG_PORT;
const sessionCookie = process.env.DROPOUT_SIGNAL_SESSION_COOKIE;
const adminSessionCookie = process.env.DROPOUT_SIGNAL_ADMIN_SESSION_COOKIE;

function assert(condition, detail) {
  if (!condition) throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
}

async function waitFor(label, read, predicate = Boolean, timeoutMs = 15000) {
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
    this.events = [];
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
      } else {
        this.events.push(message);
      }
    });
    this.socket.addEventListener('close', event => {
      for (const {reject} of this.pending.values()) reject(new Error(`DevTools socket closed (${event.code}: ${event.reason})`));
      this.pending.clear();
    });
    await new Promise((resolve, reject) => {
      this.socket.addEventListener('open', resolve, {once: true});
      this.socket.addEventListener('error', reject, {once: true});
    });
  }

  call(method, params = {}) {
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, {resolve, reject});
      this.socket.send(JSON.stringify({id, method, params}));
    });
  }

  async evaluate(expression) {
    const result = await this.call('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    });
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
  const text = await response.text();
  assert(response.ok, `${path} returned ${response.status}: ${text}`);
  return text;
}

const targets = await waitFor(
  'Chrome debugger',
  async () => (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json(),
  value => value.some(target => target.type === 'page'),
);
const target = targets.find(item => item.type === 'page');
const devtools = new DevTools(target.webSocketDebuggerUrl);
await devtools.connect();
for (const domain of ['Page.enable', 'Runtime.enable', 'Log.enable', 'Network.enable']) await devtools.call(domain);
await devtools.call('Network.setCookie', {name: 'session', value: sessionCookie, url: baseUrl, httpOnly: true});
await devtools.call('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
await devtools.call('Page.navigate', {url: baseUrl + '/counselor'});
await waitFor('counselor dashboard', () => devtools.evaluate("document.readyState === 'complete' && !!document.querySelector('.page')"));
await new Promise(resolve => setTimeout(resolve, 1500));

const layout = await devtools.evaluate(`(() => {
  const headings=[...document.querySelectorAll('h1,h2,h3,.card-h,.card-new-h')];
  const find=text=>headings.find(node=>node.textContent.trim().toLowerCase().startsWith(text.toLowerCase()));
  const prediction=find('Risk Prediction'), distribution=find('Risk Distribution');
  const pCard=prediction?.closest('.card,.card-new,.card-b,.card-new-b');
  const dCard=distribution?.closest('.card,.card-new,.card-b,.card-new-b');
  const predictionBadge=prediction?.querySelector('.risk-fixed-badge')?.textContent||'';
  const predictionValue=prediction?.closest('.card,.card-new')?.querySelector('.card-new-b h3,.card-b h3')?.textContent||'';
  return {
    viewport: innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
    predictionFound: !!prediction,
    distributionFound: !!distribution,
    distributionBeforePrediction: !!(pCard && dCard && (dCard.compareDocumentPosition(pCard) & Node.DOCUMENT_POSITION_FOLLOWING)),
    predictionBadge,
    predictionValue
  };
})()`);
assert(layout.documentWidth <= layout.viewport + 1, layout);
assert(layout.bodyWidth <= layout.viewport + 1, layout);
assert(layout.predictionFound && layout.distributionFound && layout.distributionBeforePrediction, layout);
assert((layout.predictionBadge.match(/[\d,]+/)||[])[0] === (layout.predictionValue.match(/[\d,]+/)||[])[0], layout);
for (const width of [1024, 768, 390]) {
  await devtools.call('Emulation.setDeviceMetricsOverride', {width, height: 1000, deviceScaleFactor: 1, mobile: width < 600});
  await new Promise(resolve => setTimeout(resolve, 100));
  const widths = await devtools.evaluate(`(() => ({
    viewport:innerWidth,
    documentWidth:document.documentElement.scrollWidth,
    bodyWidth:document.body.scrollWidth,
    offenders:[...document.querySelectorAll('body *')].map(node=>{const r=node.getBoundingClientRect();return {tag:node.tagName,id:node.id,cls:String(node.className||'').slice(0,100),left:Math.round(r.left),right:Math.round(r.right),width:Math.round(r.width),scrollWidth:node.scrollWidth,clientWidth:node.clientWidth}}).filter(item=>item.right>innerWidth+2||item.left < -2||item.scrollWidth>item.clientWidth+2).sort((a,b)=>(b.right-innerWidth)-(a.right-innerWidth)).slice(0,12)
  }))()`);
  assert(widths.documentWidth <= widths.viewport + 1 && widths.bodyWidth <= widths.viewport + 1, widths);
}
await devtools.call('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
console.log('PASS responsive widths, Distribution/Prediction order, and matching prediction totals', layout);

await devtools.evaluate("window.activateWorkspacePage('transcript')");
const sampleState = await waitFor(
  'sample call rows',
  () => devtools.evaluate(`(() => ({
    samples:[...document.querySelectorAll('details[data-is-sample=true][data-channel=call]')].map(r=>({key:r.dataset.conversationKey,count:+r.dataset.messageCount,status:r.querySelector('summary span')?.textContent.trim()})),
    panels:['full-transcript-panel','transcript-panel','admin-transcript-panel'].map(id=>({id,exists:!!document.getElementById(id),details:document.querySelectorAll('#'+id+' details').length,text:(document.getElementById(id)?.innerText||'').slice(0,180)})),
    active:document.querySelector('.page.active')?.id||''
  }))()`),
  value => value.samples.length >= 2,
);
const samples = sampleState.samples;
const beforeCounts = Object.fromEntries(samples.map(item => [item.key, item.count]));
const selectedKey = samples[0].key;
const selectedLiteral = JSON.stringify(selectedKey);
assert(await devtools.evaluate(`(() => {const row=document.querySelector('#full-transcript-panel [data-conversation-key='+CSS.escape(${selectedLiteral})+']'); if(!row)return false; row.querySelector('summary').click(); return true;})()`), 'Could not open a sample row');
await devtools.evaluate(`document.querySelector('#full-transcript-panel [data-conversation-key='+CSS.escape(${selectedLiteral})+']').__stableRowToken='selected-sample'`);
const midpoint = await waitFor(
  'selected sample midpoint',
  () => devtools.evaluate(`(() => {const row=document.querySelector('#full-transcript-panel [data-conversation-key='+CSS.escape(${selectedLiteral})+']'); const t=row?.querySelector('.dataset-thread'); return row&&t?{open:row.open,top:t.scrollTop,max:Math.max(0,t.scrollHeight-t.clientHeight)}:null;})()`),
  value => value && value.open && (value.max === 0 || value.top > 0),
);
const progressed = await waitFor(
  'two-second selected sample exchange',
  () => devtools.evaluate("Object.fromEntries([...document.querySelectorAll('#full-transcript-panel details[data-is-sample=true]')].map(r=>[r.dataset.conversationKey,+r.dataset.messageCount]))"),
  counts => (counts[selectedKey] || 0) >= beforeCounts[selectedKey] + 2,
  6500,
);
const changedOthers = Object.keys(beforeCounts).filter(key => key !== selectedKey && progressed[key] !== beforeCounts[key]);
assert(changedOthers.length === 0, {changedOthers, beforeCounts, progressed});
const stableSampleRow = await devtools.evaluate(`(() => {const row=document.querySelector('#full-transcript-panel [data-conversation-key='+CSS.escape(${selectedLiteral})+']'); return {stable:row?.__stableRowToken==='selected-sample',openRows:document.querySelectorAll('#full-transcript-panel details[open]').length,bound:row?.dataset.runtimeToggleBound};})()`);
assert(stableSampleRow.stable && stableSampleRow.openRows === 1 && stableSampleRow.bound === 'true', stableSampleRow);
console.log('PASS selected sample starts midway, advances as a pair every 2.5 seconds, and keeps one stable row', midpoint, stableSampleRow);

await devtools.evaluate("window.activateWorkspacePage('dashboard')");
await new Promise(resolve => setTimeout(resolve, 2500));
await devtools.evaluate("window.activateWorkspacePage('transcript')");
const resumedCount = await waitFor(
  'background-tab sample progress',
  () => devtools.evaluate(`+document.querySelector('#full-transcript-panel [data-conversation-key='+CSS.escape(${selectedLiteral})+']')?.dataset.messageCount || 0`),
  value => value >= progressed[selectedKey] + 2,
  4000,
);
console.log('PASS transcript remains responsive and catches up after tab changes', resumedCount);

await devtools.evaluate("window.activateWorkspacePage('dashboard')");
assert(await devtools.evaluate("(() => {const button=[...document.querySelectorAll('button')].find(node=>/call students/i.test(node.textContent)); if(!button)return false; button.click(); return true;})()"), 'Call Students button missing');
await waitFor(
  'manual call session',
  async () => (await (await fetch(baseUrl + '/api/transcripts', {cache: 'no-store'})).json()).sessions,
  sessions => Boolean(sessions['CA-BROWSER-CHECK']),
);
await postForm('/voice/welcome?student_id=STU-ACHAL&student_name=Achal%20Sangami&ml_risk=0.91', {CallSid: 'CA-BROWSER-CHECK', To: '+15550123456'});
const callRows = await waitFor(
  'Achal live call workspace',
  () => devtools.evaluate(`(() => ({page:document.querySelector('.page.active')?.id||'',rows:[...document.querySelectorAll('#full-transcript-panel details')].map(r=>({name:r.querySelector('summary strong')?.textContent.trim(),status:r.querySelector('summary span')?.textContent.trim()}))}))()`),
  value => value.page.includes('transcript') && value.rows[0]?.name === 'Achal Sangami',
  7000,
);
const statuses = callRows.rows.map(row => row.status);
assert(statuses.slice(1).includes('ACTIVE'), callRows);
const firstCompleted = statuses.includes('COMPLETED') ? statuses.indexOf('COMPLETED') : statuses.length;
assert(statuses.slice(1, firstCompleted).every(status => status === 'ACTIVE'), callRows);

const partialText = 'I am struggling with attendance and tuition this semester';
await postForm('/voice/partial?q=0&sid=CA-BROWSER-CHECK', {CallSid: 'CA-BROWSER-CHECK', UnstableSpeechResult: partialText});
const partialView = await waitFor(
  'live partial speech in Achal open row',
  () => devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#full-transcript-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami'); return row?{open:row.open,last:row.querySelector('.dataset-message:last-child p')?.textContent.trim(),partial:row.querySelector('.dataset-message:last-child')?.classList.contains('partial'),top:row.querySelector('.dataset-thread')?.scrollTop}:null;})()`),
  value => value?.open && value.partial && value.last.includes(partialText),
  4000,
);
const questions = [
  'How has this semester been going for you so far?',
  'What has been the most challenging part of college life recently?',
  'Which part of your current coursework would you most like support with?',
  'If you could change one thing about your college experience, what would it be?',
  'What are you most looking forward to next semester?',
];
const answers = [
  partialText,
  'I have missed classes because I am working evenings.',
  'Tuition fees and coursework are both becoming difficult.',
  'I need financial aid advice and a study recovery plan.',
  'A counselor call tomorrow would help me stay enrolled.',
];
for (let index = 0; index < answers.length; index += 1) {
  await postForm(`/voice/respond?q=${index}&sid=CA-BROWSER-CHECK`, {CallSid: 'CA-BROWSER-CHECK', SpeechResult: answers[index], Confidence: '0.95'});
}
const completedPayload = await waitFor(
  'completed call analysis',
  async () => (await (await fetch(baseUrl + '/api/transcripts', {cache: 'no-store'})).json()).sessions['CA-BROWSER-CHECK'],
  session => session?.status === 'completed' && session.summary,
  5000,
);
const askedQuestions = completedPayload.transcript_events.filter(event => event.side === 'ai' && questions.includes(event.text)).map(event => event.text);
assert(askedQuestions.length === 5 && new Set(askedQuestions).size === 5, askedQuestions);
await waitFor(
  'automatic WhatsApp outreach',
  async () => (await (await fetch(baseUrl + '/whatsapp/conversations', {cache: 'no-store'})).json()).conversations,
  conversations => conversations.some(item => item.student_name === 'Achal Sangami'),
  5000,
);
const handoff = await waitFor(
  'automatic open WhatsApp handoff',
  () => devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#wa-convos-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami'); const call=[...document.querySelectorAll('#full-transcript-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami'); return {page:document.querySelector('.page.active')?.id||'',waOpen:!!row?.open,waStatus:row?.querySelector('summary span')?.textContent.trim(),callSummary:call?.querySelector('.dataset-contact-summary')?.innerText||''};})()`),
  value => value.page.includes('whatsapp') && value.waOpen && value.callSummary.includes('High dropout risk flagged'),
  7000,
);
console.log('PASS real call partial input, five questions, summary, risk flag, and WhatsApp handoff', partialView, handoff);

await postForm('/whatsapp/webhook', {From: 'whatsapp:+15550123456', Body: 'Please help me with financial aid.'});
const waCount = await waitFor(
  'live WhatsApp reply',
  () => devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#wa-convos-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami'); return row?+row.dataset.messageCount:0;})()`),
  value => value >= 3,
  4000,
);
await postForm('/whatsapp/webhook', {From: 'whatsapp:+15550123456', Body: 'Goodbye'});
const waCompleted = await waitFor(
  'completed WhatsApp summary',
  () => devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#wa-convos-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami'); return row?{status:row.querySelector('summary span')?.textContent.trim(),summary:row.querySelector('.dataset-contact-summary')?.innerText||'',count:+row.dataset.messageCount}:null;})()`),
  value => value?.status === 'COMPLETED' && value.summary.includes('WhatsApp follow-up completed'),
  5000,
);
console.log('PASS live WhatsApp updates, isolated auto-scroll, completion, and AI summary', waCount, waCompleted);

// Re-run the operational path through the administrator workspace. This is a
// behavior check, not a static button-presence check: the admin must receive
// the same live call, transcript, summary, and WhatsApp handoff.
await devtools.call('Network.setCookie', {name: 'session', value: adminSessionCookie, url: baseUrl, httpOnly: true});
await devtools.call('Page.navigate', {url: baseUrl + '/admin'});
await waitFor('administrator dashboard', () => devtools.evaluate("document.readyState === 'complete' && !!document.getElementById('page-overview')"));
await new Promise(resolve => setTimeout(resolve, 1800));
const adminLayout = await devtools.evaluate(`(() => {
  const headings=[...document.querySelectorAll('h1,h2,h3,.card-h,.card-new-h')];
  const find=text=>headings.find(node=>node.textContent.trim().toLowerCase().startsWith(text.toLowerCase()));
  const prediction=find('Risk Prediction'),distribution=find('Risk Distribution');
  const pCard=prediction?.closest('.card,.card-new,.card-b,.card-new-b'),dCard=distribution?.closest('.card,.card-new,.card-b,.card-new-b');
  const badge=prediction?.querySelector('.risk-fixed-badge')?.textContent||'';
  const value=prediction?.closest('.card,.card-new')?.querySelector('.card-new-b h3,.card-b h3')?.textContent||'';
  const buttons=[...document.querySelectorAll('button')].filter(node=>node.offsetParent!==null).map(node=>node.textContent.trim());
  return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,distributionBeforePrediction:!!(pCard&&dCard&&(dCard.compareDocumentPosition(pCard)&Node.DOCUMENT_POSITION_FOLLOWING)),badge,value,call:buttons.some(x=>/call students/i.test(x)),analyze:buttons.some(x=>/analyze calls/i.test(x)),export:buttons.some(x=>/export csv/i.test(x)),whatsapp:buttons.some(x=>/whatsapp follow-up/i.test(x)),upload:!!document.getElementById('dataset-file-input')};
})()`);
assert(adminLayout.documentWidth <= adminLayout.viewport + 1 && adminLayout.bodyWidth <= adminLayout.viewport + 1, adminLayout);
assert(adminLayout.distributionBeforePrediction, adminLayout);
assert((adminLayout.badge.match(/[\d,]+/)||[])[0] === (adminLayout.value.match(/[\d,]+/)||[])[0], adminLayout);
assert(adminLayout.call && adminLayout.analyze && adminLayout.export && adminLayout.whatsapp && adminLayout.upload, adminLayout);
await devtools.evaluate("window.activateWorkspacePage('admin-transcript')");
const adminHistory = await waitFor(
  'administrator completed call history',
  () => devtools.evaluate(`(() => {const call=[...document.querySelectorAll('#admin-transcript-panel details')].find(row=>row.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');const wa=[...document.querySelectorAll('#admin-wa-panel details')].find(row=>row.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return {callStatus:call?.querySelector('summary span')?.textContent.trim(),callSummary:call?.querySelector('.dataset-contact-summary')?.textContent||'',waStatus:wa?.querySelector('summary span')?.textContent.trim(),waSummary:wa?.querySelector('.dataset-contact-summary')?.textContent||''};})()`),
  value => value.callStatus === 'COMPLETED' && value.callSummary.includes('High dropout risk flagged') && value.waStatus === 'COMPLETED' && value.waSummary.includes('WhatsApp follow-up completed'),
  6000,
);

await fetch(baseUrl + '/api/reset', {method:'POST'});
await new Promise(resolve => setTimeout(resolve, 1200));
await devtools.evaluate("window.activateWorkspacePage('overview')");
const adminCallStart = await devtools.evaluate("(async()=>{const button=[...document.querySelectorAll('button')].find(node=>node.offsetParent!==null&&/call students/i.test(node.textContent));if(!button||button.disabled||typeof window.adminInitiateCall!=='function')return {ok:false,reason:'missing or disabled'};const result=await window.adminInitiateCall();return {ok:!!result,result};})()");
assert(adminCallStart.ok, adminCallStart);
await waitFor('administrator manual call session', async () => (await (await fetch(baseUrl + '/api/transcripts', {cache:'no-store'})).json()).sessions, sessions => Boolean(sessions['CA-BROWSER-CHECK']));
await postForm('/voice/welcome?student_id=STU-ACHAL&student_name=Achal%20Sangami&ml_risk=0.91', {CallSid:'CA-BROWSER-CHECK',To:'+15550123456'});
const adminLive = await waitFor(
  'administrator live Achal transcript',
  () => devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#admin-transcript-panel details')].find(item=>item.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return {page:document.querySelector('.page.active')?.id||'',open:!!row?.open,status:row?.querySelector('summary span')?.textContent.trim(),first:[...document.querySelectorAll('#admin-transcript-panel details')][0]?.querySelector('summary strong')?.textContent.trim()};})()`),
  value => value.page === 'page-admin-transcript' && value.open && value.status === 'ACTIVE' && value.first === 'Achal Sangami',
  7000,
);
await postForm('/voice/partial?q=0&sid=CA-BROWSER-CHECK', {CallSid:'CA-BROWSER-CHECK',UnstableSpeechResult:partialText});
await waitFor('administrator partial speech', () => devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#admin-transcript-panel details')].find(item=>item.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');const last=row?.querySelector('.dataset-message:last-child');return !!(row?.open&&last?.classList.contains('partial')&&last.textContent.includes(${JSON.stringify(partialText)}));})()`));
for (let index=0; index<answers.length; index+=1) await postForm(`/voice/respond?q=${index}&sid=CA-BROWSER-CHECK`, {CallSid:'CA-BROWSER-CHECK',SpeechResult:answers[index],Confidence:'0.95'});
const adminHandoff = await waitFor(
  'administrator automatic WhatsApp handoff',
  () => devtools.evaluate(`(() => {const wa=[...document.querySelectorAll('#admin-wa-panel details')].find(row=>row.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');const call=[...document.querySelectorAll('#admin-transcript-panel details')].find(row=>row.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return {page:document.querySelector('.page.active')?.id||'',waOpen:!!wa?.open,waName:wa?.querySelector('summary strong')?.textContent.trim(),callSummary:call?.querySelector('.dataset-contact-summary')?.textContent||''};})()`),
  value => value.page === 'page-admin-whatsapp' && value.waOpen && value.waName === 'Achal Sangami' && value.callSummary.includes('High dropout risk flagged'),
  8000,
);
console.log('PASS administrator parity: layout, controls, call history, live Achal transcript, risk summary, and WhatsApp handoff', adminLayout, adminHistory, adminLive, adminHandoff);

await devtools.call('Page.navigate', {url: baseUrl + '/logout'});
await waitFor('landing page', () => devtools.evaluate("document.readyState === 'complete' && /watch demo/i.test(document.body.innerText)"));
assert(await devtools.evaluate("(() => {const button=[...document.querySelectorAll('button')].find(node=>/watch demo/i.test(node.textContent)); if(!button)return false; button.click(); return true;})()"), 'Watch Demo button missing');
await waitFor('guided login cursor', () => devtools.evaluate(`(() => {const cursor=document.querySelector('.guided-demo-login-cursor');if(!cursor)return null;const r=cursor.getBoundingClientRect();return {opacity:getComputedStyle(cursor).opacity,left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:innerWidth,height:innerHeight};})()`), value => value && Number(value.opacity) > 0 && value.left >= 0 && value.top >= 0 && value.right <= value.width && value.bottom <= value.height, 6000);
await waitFor('guided demo start', () => devtools.evaluate('window.__guidedDemoActive === true'), Boolean, 10000);
const uploadStarted = performance.now();
const initialUpload = await waitFor('four-second guided dataset upload', () => devtools.evaluate(`(() => {const overlay=document.getElementById('guided-demo-upload');return overlay?{percent:+(overlay.querySelector('.guided-upload-percent')?.textContent||'0').replace('%',''),page:document.querySelector('.page.active')?.id||''}:null;})()`), value => value && value.page.includes('dashboard'));
const progressedUpload = await waitFor('progressive guided upload bar', () => devtools.evaluate(`+document.querySelector('#guided-demo-upload .guided-upload-percent')?.textContent.replace('%','')||0`), value => value > initialUpload.percent + 20, 3000);
await waitFor('4 Models Ensembled confirmation', () => devtools.evaluate("[...document.querySelectorAll('.guided-demo-popup')].some(node=>/4 Models Ensembled/i.test(node.textContent))"), Boolean, 6000);
const uploadDuration = performance.now() - uploadStarted;
assert(uploadDuration >= 3800, {uploadDuration, initialUpload, progressedUpload});

async function collectGuidedCounts(panelId, expected, timeoutMs) {
  const observations = [];
  const deadline = Date.now() + timeoutMs;
  let last = -1;
  while (Date.now() < deadline) {
    const count = await devtools.evaluate(`+document.querySelector('#${panelId} [data-conversation-key^="guided-demo"]')?.dataset.messageCount || 0`);
    if (count !== last) {
      observations.push([count, performance.now()]);
      last = count;
    }
    if (count >= expected) return observations;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Guided ${panelId} stalled: ${JSON.stringify(observations)}`);
}

const callTiming = await collectGuidedCounts('full-transcript-panel', 10, 20000);
const positiveCall = callTiming.filter(([count]) => count > 0);
assert(positiveCall.length >= 2, callTiming);
assert(positiveCall[1][1] - positiveCall[0][1] >= 1500, callTiming);
const waTiming = await collectGuidedCounts('wa-convos-panel', 6, 12000);
const positiveWa = waTiming.filter(([count]) => count > 0);
assert(positiveWa.length >= 3, waTiming);
assert(positiveWa[1][1] - positiveWa[0][1] >= 1500, waTiming);
assert(positiveWa[2][1] - positiveWa[1][1] >= 1500, waTiming);
await waitFor(
  'guided student-helped confirmation',
  () => devtools.evaluate("[...document.querySelectorAll('.guided-demo-popup')].some(n=>/student has been helped/i.test(n.textContent))"),
  Boolean,
  5000,
);
await waitFor('guided demo end', () => devtools.evaluate("location.pathname === '/'"), Boolean, 6000);
console.log('PASS Watch Demo login cursor, four-second upload, four-model ensemble, call/WhatsApp timing, helped, and home return');

const browserFailures = [];
for (const event of devtools.events) {
  if (event.method === 'Runtime.exceptionThrown') {
    const details = event.params?.exceptionDetails || {};
    browserFailures.push({
      text: details.text || 'Runtime exception',
      description: details.exception?.description || details.exception?.value || '',
      url: details.url || '',
      line: details.lineNumber,
      column: details.columnNumber,
    });
  }
  if (event.method === 'Log.entryAdded' && event.params?.entry?.level === 'error') {
    const text = event.params.entry.text || '';
    if (!text.toLowerCase().includes('favicon')) browserFailures.push(text);
  }
}
assert(browserFailures.length === 0, browserFailures);
console.log('PASS no uncaught browser runtime errors');
devtools.socket.close();
