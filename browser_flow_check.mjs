const baseUrl = process.env.DROPOUT_SIGNAL_BROWSER_BASE;
const debugPort = process.env.DROPOUT_SIGNAL_DEBUG_PORT;
const sessionCookie = process.env.DROPOUT_SIGNAL_SESSION_COOKIE;
const adminSessionCookie = process.env.DROPOUT_SIGNAL_ADMIN_SESSION_COOKIE;

process.on('uncaughtException', error => {
  console.error(error?.stack || error);
  process.exit(1);
});
process.on('unhandledRejection', error => {
  console.error(error?.stack || error);
  process.exit(1);
});
console.log('START browser workflow');

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
    await Promise.race([
      new Promise((resolve, reject) => {
        this.socket.addEventListener('open', resolve, {once: true});
        this.socket.addEventListener('error', reject, {once: true});
      }),
      new Promise((_, reject) => setTimeout(() => reject(new Error('DevTools WebSocket connection timed out')), 5000)),
    ]);
  }

  call(method, params = {}) {
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`DevTools command timed out: ${method}`));
      }, 10000);
      this.pending.set(id, {
        resolve: value => { clearTimeout(timer); resolve(value); },
        reject: error => { clearTimeout(timer); reject(error); },
      });
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
  async () => (await fetch(`http://127.0.0.1:${debugPort}/json/list`, {signal:AbortSignal.timeout(1500)})).json(),
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
  const prediction=document.querySelector('.runtime-risk-prediction');
  const distribution=document.querySelector('.runtime-risk-distribution');
  const distributionValues=Object.fromEntries([...distribution?.querySelectorAll('.risk-bar')||[]].map(row=>[row.querySelector('span')?.textContent.trim(),row.querySelector('b')?.textContent.trim()]));
  const predictionValues=Object.fromEntries([...prediction?.querySelectorAll('.pulse-stat')||[]].map(row=>[row.querySelector('span')?.textContent.trim(),row.querySelector('b')?.textContent.trim()]));
  return {
    viewport: innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
    predictionFound: !!prediction,
    distributionFound: !!distribution,
    distributionAbovePrediction: !!(prediction && distribution && distribution.getBoundingClientRect().top < prediction.getBoundingClientRect().top),
    distributionValues,
    predictionValues,
    cards:[...document.querySelectorAll('.card-new')].slice(0,8).map(card=>({heading:card.querySelector('h3')?.textContent.trim(),bodyClass:card.querySelector('.card-new-b')?.firstElementChild?.className||'',bodyText:(card.querySelector('.card-new-b')?.innerText||'').slice(0,90)}))
  };
})()`);
assert(layout.documentWidth <= layout.viewport + 1, layout);
assert(layout.bodyWidth <= layout.viewport + 1, layout);
assert(layout.predictionFound && layout.distributionFound && layout.distributionAbovePrediction, layout);
assert(layout.distributionValues.High === layout.predictionValues['High-confidence review'], layout);
assert(layout.distributionValues.Medium === layout.predictionValues['Proactive watchlist'], layout);
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
console.log('PASS responsive widths, swapped Distribution/Prediction positions, and matching totals', layout);

const emptyExport = await fetch(baseUrl + '/api/operations/export.csv', {cache:'no-store'});
assert(emptyExport.status === 400 && /no calls done yet/i.test(await emptyExport.text()), 'Export should be blocked before calls');

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
  'first sequential selected sample turn',
  () => devtools.evaluate("Object.fromEntries([...document.querySelectorAll('#full-transcript-panel details[data-is-sample=true]')].map(r=>[r.dataset.conversationKey,+r.dataset.messageCount]))"),
  counts => (counts[selectedKey] || 0) === beforeCounts[selectedKey] + 1,
  4500,
);
const progressedAgain = await waitFor(
  'second sequential selected sample turn',
  () => devtools.evaluate("Object.fromEntries([...document.querySelectorAll('#full-transcript-panel details[data-is-sample=true]')].map(r=>[r.dataset.conversationKey,+r.dataset.messageCount]))"),
  counts => (counts[selectedKey] || 0) === beforeCounts[selectedKey] + 2,
  3500,
);
const changedOthers = Object.keys(beforeCounts).filter(key => key !== selectedKey && progressed[key] !== beforeCounts[key]);
assert(changedOthers.length === 0, {changedOthers, beforeCounts, progressed});
const callTurnOrder = await devtools.evaluate(`([...document.querySelectorAll('#full-transcript-panel [data-conversation-key='+CSS.escape(${selectedLiteral})+'] .dataset-message')].slice(0,3).map(node=>node.classList.contains('asha')?'ai':'student'))`);
assert(callTurnOrder.join(',') === 'ai,student,ai', callTurnOrder);
const stableSampleRow = await devtools.evaluate(`(() => {const row=document.querySelector('#full-transcript-panel [data-conversation-key='+CSS.escape(${selectedLiteral})+']'); return {stable:row?.__stableRowToken==='selected-sample',openRows:document.querySelectorAll('#full-transcript-panel details[open]').length,bound:row?.dataset.runtimeToggleBound};})()`);
assert(stableSampleRow.stable && stableSampleRow.openRows === 1 && stableSampleRow.bound === 'true', stableSampleRow);
console.log('PASS selected sample starts midway, advances one alternating turn every 2 seconds, and keeps one stable row', midpoint, stableSampleRow, progressedAgain[selectedKey]);

await devtools.evaluate("window.activateWorkspacePage('dashboard')");
await new Promise(resolve => setTimeout(resolve, 2500));
await devtools.evaluate("window.activateWorkspacePage('transcript')");
const resumedCount = await waitFor(
  'background-tab sample progress',
  () => devtools.evaluate(`+document.querySelector('#full-transcript-panel [data-conversation-key='+CSS.escape(${selectedLiteral})+']')?.dataset.messageCount || 0`),
  value => value >= progressedAgain[selectedKey] + 1,
  4000,
);
console.log('PASS transcript remains responsive and catches up after tab changes', resumedCount);
const waitingSampleKeys = samples.filter(item => item.status === 'COMPLETED').map(item => item.key);
if (waitingSampleKeys.length) {
  await waitFor(
    'selected sample completion',
    () => devtools.evaluate(`document.querySelector('#full-transcript-panel [data-conversation-key='+CSS.escape(${selectedLiteral})+'] summary span')?.textContent.trim()||''`),
    value => value === 'COMPLETED',
    18000,
  );
  const promotedSample = await waitFor(
    'replacement active sample call',
    () => devtools.evaluate(`(() => {const waiting=${JSON.stringify(waitingSampleKeys)};return [...document.querySelectorAll('#full-transcript-panel details[data-is-sample=true]')].find(row=>waiting.includes(row.dataset.conversationKey)&&row.querySelector('summary span')?.textContent.trim()==='ACTIVE')?.dataset.conversationKey||'';})()`),
    Boolean,
    4000,
  );
  console.log('PASS a newly active call replaces a completed sample call', promotedSample);
}

await devtools.evaluate("window.activateWorkspacePage('whatsapp')");
const waSamples = await waitFor(
  'sample WhatsApp rows',
  () => devtools.evaluate(`([...document.querySelectorAll('#wa-convos-panel details[data-is-sample=true]')].map(row=>({key:row.dataset.conversationKey,count:+row.dataset.messageCount,status:row.querySelector('summary span')?.textContent.trim()})))`),
  value => value.length >= 2,
);
const activeWaSample = waSamples.find(item => item.status === 'ACTIVE');
assert(activeWaSample, waSamples);
const activeWaLiteral = JSON.stringify(activeWaSample.key);
assert(await devtools.evaluate(`(() => {const row=document.querySelector('#wa-convos-panel [data-conversation-key='+CSS.escape(${activeWaLiteral})+']');if(!row)return false;row.querySelector('summary').click();return true;})()`), 'Could not open a sample WhatsApp row');
const waSequentialOne = await waitFor(
  'first sequential sample WhatsApp turn',
  () => devtools.evaluate(`+document.querySelector('#wa-convos-panel [data-conversation-key='+CSS.escape(${activeWaLiteral})+']')?.dataset.messageCount||0`),
  value => value === activeWaSample.count + 1,
  4500,
);
const waSequentialTwo = await waitFor(
  'second sequential sample WhatsApp turn',
  () => devtools.evaluate(`+document.querySelector('#wa-convos-panel [data-conversation-key='+CSS.escape(${activeWaLiteral})+']')?.dataset.messageCount||0`),
  value => value === activeWaSample.count + 2,
  3500,
);
const waTurnOrder = await devtools.evaluate(`([...document.querySelectorAll('#wa-convos-panel [data-conversation-key='+CSS.escape(${activeWaLiteral})+'] .dataset-message')].slice(0,3).map(node=>node.classList.contains('asha')?'ai':'student'))`);
assert(waTurnOrder.join(',') === 'ai,student,ai', waTurnOrder);
const waitingWaKeys = waSamples.filter(item => item.status === 'COMPLETED').map(item => item.key);
if (waitingWaKeys.length) {
  await waitFor('sample WhatsApp completion', () => devtools.evaluate(`document.querySelector('#wa-convos-panel [data-conversation-key='+CSS.escape(${activeWaLiteral})+'] summary span')?.textContent.trim()||''`), value => value === 'COMPLETED', 15000);
  await waitFor('replacement active sample WhatsApp', () => devtools.evaluate(`(() => {const waiting=${JSON.stringify(waitingWaKeys)};return [...document.querySelectorAll('#wa-convos-panel details[data-is-sample=true]')].some(row=>waiting.includes(row.dataset.conversationKey)&&row.querySelector('summary span')?.textContent.trim()==='ACTIVE');})()`), Boolean, 4000);
}
console.log('PASS sample WhatsApp advances AI/student turns every 2 seconds and replenishes its active queue', waSequentialOne, waSequentialTwo, waTurnOrder);

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
const beforePartialCount = await devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#full-transcript-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return row?.querySelectorAll('.dataset-message').length||0;})()`);
await postForm('/voice/partial?q=0&sid=CA-BROWSER-CHECK', {CallSid: 'CA-BROWSER-CHECK', UnstableSpeechResult: partialText});
await new Promise(resolve => setTimeout(resolve, 700));
const partialView = await devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#full-transcript-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami'); return row?{open:row.open,count:row.querySelectorAll('.dataset-message').length,hasPartial:!!row.querySelector('.dataset-message.partial'),text:row.innerText}:null;})()`);
assert(partialView?.open && partialView.count === beforePartialCount && !partialView.hasPartial && !partialView.text.includes(partialText), partialView);
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
await postForm('/voice/respond?q=0&sid=CA-BROWSER-CHECK', {CallSid:'CA-BROWSER-CHECK',SpeechResult:answers[0],Confidence:'0.95'});
await waitFor('final answer appears after speech completes', () => devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#full-transcript-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return row?.querySelector('.dataset-message:last-of-type:nth-last-of-type(n)')?row.innerText.includes(${JSON.stringify(partialText)}):false;})()`));
await postForm('/voice/respond?q=0&sid=CA-BROWSER-CHECK', {CallSid:'CA-BROWSER-CHECK',SpeechResult:'stale answer that must not repeat',Confidence:'0.99'});
await new Promise(resolve => setTimeout(resolve, 450));
assert(!(await devtools.evaluate(`document.body.innerText.includes('stale answer that must not repeat')`)), 'A duplicate call webhook repeated an old answer');
for (let index = 1; index < answers.length; index += 1) {
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
const centeredFlag = await waitFor(
  'centered high-risk handoff',
  () => devtools.evaluate(`(() => {const modal=document.getElementById('operation-action-modal');if(!modal||!/flagged Achal Sangami as high risk/i.test(modal.innerText))return window.__lastRiskHandoff||{debug:window.__achalHandoffDebug||null,modal:modal?.innerText||'',page:document.querySelector('.page.active')?.id||''};const r=modal.querySelector('.operation-modal').getBoundingClientRect();return {dx:Math.abs((r.left+r.right)/2-innerWidth/2),dy:Math.abs((r.top+r.bottom)/2-innerHeight/2),debug:window.__achalHandoffDebug};})()`),
  value => value && value.dx < 10 && value.dy < 10,
  5000,
);
const handoff = await waitFor(
  'automatic open WhatsApp handoff',
  () => devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#wa-convos-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami'); const call=[...document.querySelectorAll('#full-transcript-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami'); return {page:document.querySelector('.page.active')?.id||'',waOpen:!!row?.open,waStatus:row?.querySelector('summary span')?.textContent.trim(),callSummary:call?.querySelector('.dataset-contact-summary')?.innerText||''};})()`),
  value => value.page.includes('whatsapp') && value.waOpen && value.callSummary.includes('High dropout risk flagged'),
  7000,
);
await devtools.evaluate("window.activateWorkspacePage('transcript')");
assert(await devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#full-transcript-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');if(!row)return false;row.querySelector('summary').click();return true;})()`), 'Completed Achal call row could not be opened');
const reopenedCall = await waitFor(
  'completed Achal call remains open',
  () => devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#full-transcript-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return row?{open:row.open,status:row.querySelector('summary span')?.textContent.trim(),summary:row.querySelector('.dataset-contact-summary')?.innerText||''}:null;})()`),
  value => value?.open && value.status === 'COMPLETED' && value.summary.toLowerCase().includes('high dropout risk flagged'),
);
await new Promise(resolve => setTimeout(resolve, 1300));
assert(await devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#full-transcript-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return !!row?.open;})()`), 'Completed Achal call closed during refresh');
await devtools.evaluate("window.activateWorkspacePage('whatsapp')");
await waitFor('Achal WhatsApp row after reopening call', () => devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#wa-convos-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');if(!row)return false;if(!row.open)row.querySelector('summary').click();return row.open;})()`));
console.log('PASS real call final-only speech, duplicate suppression, five questions, summary, risk flag, and WhatsApp handoff', partialView, handoff);

await postForm('/whatsapp/webhook', {From: 'whatsapp:+15550123456', Body: 'Please help me with financial aid.', MessageSid:'SM-BROWSER-1'});
const waCount = await waitFor(
  'live WhatsApp reply',
  () => devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#wa-convos-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami'); return row?+row.dataset.messageCount:0;})()`),
  value => value >= 3,
  4000,
);
await postForm('/whatsapp/webhook', {From: 'whatsapp:+15550123456', Body: 'Please help me with financial aid.', MessageSid:'SM-BROWSER-1'});
await new Promise(resolve => setTimeout(resolve, 600));
const afterDuplicateWhatsApp = await devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#wa-convos-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return row?+row.dataset.messageCount:0;})()`);
assert(afterDuplicateWhatsApp === waCount, {waCount,afterDuplicateWhatsApp});
await postForm('/whatsapp/webhook', {From: 'whatsapp:+15550123456', Body: 'Goodbye', MessageSid:'SM-BROWSER-2'});
const waCompleted = await waitFor(
  'completed WhatsApp summary',
  () => devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#wa-convos-panel details')].find(r=>r.querySelector('summary strong')?.textContent.trim()==='Achal Sangami'); return row?{status:row.querySelector('summary span')?.textContent.trim(),summary:row.querySelector('.dataset-contact-summary')?.innerText||'',count:+row.dataset.messageCount}:null;})()`),
  value => value?.status === 'COMPLETED' && value.summary.includes('WhatsApp follow-up completed'),
  5000,
);
console.log('PASS live WhatsApp updates, isolated auto-scroll, completion, and AI summary', waCount, waCompleted);

const counselorSummaryState = await devtools.evaluate(`(() => {const grid=document.getElementById('summary-students');const card=grid?.querySelector('[data-summary-student-id="STU-ACHAL"]');return {summary:card?.querySelector('p')?.textContent.trim()||'',text:card?.innerText||'',cardHtml:(card?.innerHTML||'').slice(0,900),cards:grid?.querySelectorAll('[data-summary-student-id]').length||0,ids:[...(grid?.querySelectorAll('[data-summary-student-id]')||[])].slice(0,4).map(node=>node.dataset.summaryStudentId),html:(grid?.innerHTML||'').slice(0,300)};})()`);
const counselorAchalSummary = counselorSummaryState.summary;
assert(counselorAchalSummary.includes('Call:') && counselorAchalSummary.includes('WhatsApp follow-up completed'), counselorSummaryState);
const exportResponse = await fetch(baseUrl + '/api/operations/export.csv', {cache:'no-store'});
const exportText = await exportResponse.text();
const datasetStatus = await (await fetch(baseUrl + '/api/dataset/status', {cache:'no-store'})).json();
const highRiskCount = Number((datasetStatus.tier_breakdown||[]).find(row=>String(row.final_risk_tier).toUpperCase()==='HIGH')?.cnt||0);
const exportLines = exportText.trim().split(/\r?\n/);
assert(exportResponse.ok && exportLines.length === highRiskCount + 1 && exportLines[1].includes('Achal Sangami'), {status:exportResponse.status,lines:exportLines.length,highRiskCount,first:exportLines[1]});

// Re-run the operational path through the administrator workspace. This is a
// behavior check, not a static button-presence check: the admin must receive
// the same live call, transcript, summary, and WhatsApp handoff.
await devtools.call('Network.setCookie', {name: 'session', value: adminSessionCookie, url: baseUrl, httpOnly: true});
await devtools.call('Page.navigate', {url: baseUrl + '/admin'});
await waitFor('administrator dashboard', () => devtools.evaluate("document.readyState === 'complete' && !!document.getElementById('page-overview')"));
await new Promise(resolve => setTimeout(resolve, 1800));
const adminLayout = await devtools.evaluate(`(() => {
  const prediction=document.querySelector('.runtime-risk-prediction'),distribution=document.querySelector('.runtime-risk-distribution');
  const distributionValues=Object.fromEntries([...(distribution?.querySelectorAll('.risk-bar')||[])].map(row=>[row.querySelector('span')?.textContent.trim(),row.querySelector('b')?.textContent.trim()]));
  const predictionValues=Object.fromEntries([...(prediction?.querySelectorAll('.pulse-stat')||[])].map(row=>[row.querySelector('span')?.textContent.trim(),row.querySelector('b')?.textContent.trim()]));
  const buttons=[...document.querySelectorAll('button')].filter(node=>node.offsetParent!==null).map(node=>node.textContent.trim());
  return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,distributionAbovePrediction:!!(prediction&&distribution&&distribution.getBoundingClientRect().top<prediction.getBoundingClientRect().top),distributionValues,predictionValues,call:buttons.some(x=>/call students/i.test(x)),analyze:buttons.some(x=>/analyze calls/i.test(x)),export:buttons.some(x=>/export csv/i.test(x)),whatsapp:buttons.some(x=>/whatsapp follow-up/i.test(x)),upload:!!document.getElementById('dataset-file-input')};
})()`);
assert(adminLayout.documentWidth <= adminLayout.viewport + 1 && adminLayout.bodyWidth <= adminLayout.viewport + 1, adminLayout);
assert(adminLayout.distributionAbovePrediction, adminLayout);
assert(adminLayout.distributionValues.High === adminLayout.predictionValues['High-confidence review'], adminLayout);
assert(adminLayout.call && adminLayout.analyze && adminLayout.export && adminLayout.whatsapp && adminLayout.upload, adminLayout);
await devtools.evaluate("window.activateWorkspacePage('pipeline')");
const predictionWorkspace = await waitFor('professional administrator risk prediction workspace', () => devtools.evaluate(`(() => {const host=document.getElementById('professional-risk-workspace');return host?{hero:!!host.querySelector('.prediction-hero'),kpis:host.querySelectorAll('.prediction-kpis article').length,rows:host.querySelectorAll('.prediction-table tbody tr').length,width:document.documentElement.scrollWidth,viewport:innerWidth,text:host.innerText}:null;})()`), value => value?.hero && value.kpis === 4 && value.rows > 0);
assert(predictionWorkspace.width <= predictionWorkspace.viewport + 1 && /Decision support/i.test(predictionWorkspace.text), predictionWorkspace);
await devtools.evaluate("window.activateWorkspacePage('admin-transcript')");
const adminHistory = await waitFor(
  'administrator completed call history',
  () => devtools.evaluate(`(() => {const call=[...document.querySelectorAll('#admin-transcript-panel details')].find(row=>row.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');const wa=[...document.querySelectorAll('#admin-wa-panel details')].find(row=>row.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return {callStatus:call?.querySelector('summary span')?.textContent.trim(),callSummary:call?.querySelector('.dataset-contact-summary')?.textContent||'',waStatus:wa?.querySelector('summary span')?.textContent.trim(),waSummary:wa?.querySelector('.dataset-contact-summary')?.textContent||''};})()`),
  value => value.callStatus === 'COMPLETED' && value.callSummary.includes('High dropout risk flagged') && value.waStatus === 'COMPLETED' && value.waSummary.includes('WhatsApp follow-up completed'),
  6000,
);
const adminAchalSummary = await devtools.evaluate(`document.querySelector('#admin-summary-grid [data-summary-student-id="STU-ACHAL"] p')?.textContent.trim()||''`);
assert(adminAchalSummary === counselorAchalSummary, {counselorAchalSummary,adminAchalSummary});
assert(await devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#admin-transcript-panel details')].find(item=>item.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');if(!row)return false;row.querySelector('summary').click();return row.open;})()`), 'Administrator could not open completed Achal transcript');
await new Promise(resolve => setTimeout(resolve, 1300));
assert(await devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#admin-transcript-panel details')].find(item=>item.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return !!row?.open;})()`), 'Administrator completed Achal transcript auto-closed');

await devtools.evaluate("window.activateWorkspacePage('model-evidence')");
const fairness = await waitFor('stable administrator fairness audit', () => devtools.evaluate(`(() => {const body=document.getElementById('fairness-runtime-rows');const wrap=body?.closest('.fairness-table');return body?{rows:body.querySelectorAll('tr').length,statuses:body.querySelectorAll('.fairness-status').length,note:!!wrap?.previousElementSibling?.classList.contains('fairness-audit-note'),width:document.documentElement.scrollWidth,viewport:innerWidth}:null;})()`), value => value?.rows > 0 && value.statuses > 0 && value.note, 8000);
assert(fairness.width <= fairness.viewport + 1, fairness);

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
const adminBeforePartial = await devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#admin-transcript-panel details')].find(item=>item.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return row?.querySelectorAll('.dataset-message').length||0;})()`);
await postForm('/voice/partial?q=0&sid=CA-BROWSER-CHECK', {CallSid:'CA-BROWSER-CHECK',UnstableSpeechResult:partialText});
await new Promise(resolve => setTimeout(resolve, 700));
assert(await devtools.evaluate(`(() => {const row=[...document.querySelectorAll('#admin-transcript-panel details')].find(item=>item.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return row?.querySelectorAll('.dataset-message').length===${adminBeforePartial}&&!row?.querySelector('.dataset-message.partial');})()`), 'Administrator rendered interim speech');
for (let index=0; index<answers.length; index+=1) await postForm(`/voice/respond?q=${index}&sid=CA-BROWSER-CHECK`, {CallSid:'CA-BROWSER-CHECK',SpeechResult:answers[index],Confidence:'0.95'});
const adminHandoff = await waitFor(
  'administrator automatic WhatsApp handoff',
  () => devtools.evaluate(`(() => {const wa=[...document.querySelectorAll('#admin-wa-panel details')].find(row=>row.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');const call=[...document.querySelectorAll('#admin-transcript-panel details')].find(row=>row.querySelector('summary strong')?.textContent.trim()==='Achal Sangami');return {page:document.querySelector('.page.active')?.id||'',waOpen:!!wa?.open,waName:wa?.querySelector('summary strong')?.textContent.trim(),callSummary:call?.querySelector('.dataset-contact-summary')?.textContent||''};})()`),
  value => value.page === 'page-admin-whatsapp' && value.waOpen && value.waName === 'Achal Sangami' && value.callSummary.includes('High dropout risk flagged'),
  8000,
);
console.log('PASS administrator parity: layout, controls, call history, live Achal transcript, risk summary, and WhatsApp handoff', adminLayout, adminHistory, adminLive, adminHandoff);

await devtools.call('Page.reload', {ignoreCache:true});
await waitFor('administrator dashboard after hard refresh', () => devtools.evaluate("document.readyState === 'complete' && !!document.getElementById('page-overview')"));
const clearedOnRefresh = await waitFor(
  'refresh-only workspace reset',
  async () => {
    const status = await (await fetch(baseUrl + '/api/dataset/status', {cache:'no-store'})).json();
    const sessions = await (await fetch(baseUrl + '/api/transcripts', {cache:'no-store'})).json();
    const whatsapp = await (await fetch(baseUrl + '/whatsapp/conversations', {cache:'no-store'})).json();
    return {loaded:!!status.dataset_loaded,calls:Object.keys(sessions.sessions||{}).length,whatsapp:(whatsapp.conversations||[]).length};
  },
  value => !value.loaded && value.calls === 0 && value.whatsapp === 0,
  7000,
);
console.log('PASS hard refresh clears the uploaded cohort and Achal operation state; role switch preserved it beforehand', clearedOnRefresh);

await devtools.call('Page.navigate', {url: baseUrl + '/logout'});
await waitFor('landing page', () => devtools.evaluate("document.readyState === 'complete' && /watch demo/i.test(document.body.innerText)"));
assert(await devtools.evaluate("(() => {const button=[...document.querySelectorAll('button')].find(node=>/watch demo/i.test(node.textContent)); if(!button)return false; button.click(); return true;})()"), 'Watch Demo button missing');
await waitFor('guided login cursor', () => devtools.evaluate(`(() => {const cursor=document.querySelector('.guided-demo-login-cursor');if(!cursor)return null;const r=cursor.getBoundingClientRect();return {opacity:getComputedStyle(cursor).opacity,left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:innerWidth,height:innerHeight};})()`), value => value && Number(value.opacity) > 0 && value.left >= 0 && value.top >= 0 && value.right <= value.width && value.bottom <= value.height, 6000);
await waitFor('guided demo start', () => devtools.evaluate('window.__guidedDemoActive === true'), Boolean, 10000);
const uploadStarted = performance.now();
const initialUpload = await waitFor('four-second guided dataset upload', () => devtools.evaluate(`(() => {const overlay=document.getElementById('guided-demo-upload');return overlay?{percent:+(overlay.querySelector('.guided-upload-percent')?.textContent||'0').replace('%',''),page:document.querySelector('.page.active')?.id||''}:null;})()`), value => value && value.page.includes('dashboard'));
const uploadAppearanceDelay = performance.now() - uploadStarted;
const progressedUpload = await waitFor('progressive guided upload bar', () => devtools.evaluate(`+document.querySelector('#guided-demo-upload .guided-upload-percent')?.textContent.replace('%','')||0`), value => value > initialUpload.percent + 20, 3000);
await waitFor('4 Models Ensembled confirmation', () => devtools.evaluate("[...document.querySelectorAll('.guided-demo-popup')].some(node=>/4 Models Ensembled/i.test(node.textContent))"), Boolean, 6000);
const uploadDuration = performance.now() - uploadStarted;
assert(uploadDuration >= 3800, {uploadDuration, initialUpload, progressedUpload});
assert(uploadAppearanceDelay >= 1900, {uploadAppearanceDelay});

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
assert(positiveCall.length >= 3, callTiming);
assert(positiveCall[1][1] - positiveCall[0][1] >= 1500, callTiming);
assert(positiveCall[2][1] - positiveCall[1][1] >= 1500, callTiming);
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
