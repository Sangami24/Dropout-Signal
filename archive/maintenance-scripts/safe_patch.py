import codecs
import re

with codecs.open('app.py', 'r', 'utf-8') as f:
    text = f.read()

# 1. Update demoCall
demo_pattern = r"await new Promise\(r => setTimeout\(r, 1500\)\);\s*toast\('Following up via WhatsApp\.\.\.', 'info'\);\s*document\.querySelector\('\[data-page=\"whatsapp\"\]'\)\.click\(\);"
demo_replacement = """await new Promise(r => setTimeout(r, 1500));
    if (typeof showStudent === 'function') {
        showStudent('STU-DEMO');
        await new Promise(r => setTimeout(r, 5000));
        const closeBtn = document.querySelector('.modal-close');
        if (closeBtn) closeBtn.click();
    }
    await new Promise(r => setTimeout(r, 500));
    toast('Following up via WhatsApp...', 'info');
    document.querySelector('[data-page="whatsapp"]').click();"""
text = re.sub(demo_pattern, demo_replacement, text)

# 2. Update Risk Overview select
select_pattern = r"<select onchange=\"updateRiskFactors\(this\.value\)\"><option value=\"this_sem\">This Semester</option><option value=\"last_sem\">Last Semester</option><option value=\"this_year\">This Year</option></select>"
select_replacement = "<select onchange=\"updateRiskOverview(this.value)\"><option value=\"this_sem\">This Semester</option><option value=\"this_month\">This Month</option><option value=\"last_sem\">Last Semester</option><option value=\"this_year\">This Year</option></select>"
text = re.sub(select_pattern, select_replacement, text)

# 3. Inject updateRiskOverview
# Inject into Admin Dashboard script tag
admin_js_injection = """
window.updateRiskOverview = function(val) {
    if (typeof updateRiskFactors === 'function') updateRiskFactors(val);
    const charts = {
        'this_month': {high: 42, med: 310, low: 1045, total: 1397, stops: '#ef4444 0 3.0%,#f59e0b 3.0% 25.2%,#22c55e 25.2% 100%'},
        'this_sem': {high: 142, med: 875, low: 3483, total: 4500, stops: '#ef4444 0 3.16%,#f59e0b 3.16% 22.61%,#22c55e 22.61% 100%'},
        'last_sem': {high: 120, med: 750, low: 3600, total: 4470, stops: '#ef4444 0 2.68%,#f59e0b 2.68% 19.46%,#22c55e 19.46% 100%'},
        'this_year': {high: 262, med: 1625, low: 7083, total: 8970, stops: '#ef4444 0 2.92%,#f59e0b 2.92% 21.04%,#22c55e 21.04% 100%'}
    };
    const c = charts[val] || charts['this_sem'];
    const el = document.getElementById('tier-chart');
    if(el) {
        el.innerHTML = `<div class="d-chart-container"><div class="admin-risk-donut" style="background:conic-gradient(${c.stops})"><div class="admin-risk-hole"><strong>${c.total.toLocaleString()}</strong><span>students</span></div></div></div>
        <div class="d-legend">
            <div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:#ef4444"></span>High risk</span><strong>${c.high.toLocaleString()}</strong></div>
            <div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:#f59e0b"></span>Medium risk</span><strong>${c.med.toLocaleString()}</strong></div>
            <div class="dl-item"><span class="dl-left"><span class="dl-dot" style="background:#22c55e"></span>Low risk</span><strong>${c.low.toLocaleString()}</strong></div>
        </div>`;
    }
};
window.loadAdminAtRisk=async function()"""
text = re.sub(r"window\.loadAdminAtRisk=async function\(\)", admin_js_injection, text)

# 4. Update Risk Trend function to handle monthly
trend_pattern = r"function updateRiskTrend\(val\) \{[\s\S]*?\}\s*function "
admin_trend_logic = """function updateRiskTrend(val) {
    const svg = document.getElementById('risk-trend-svg');
    if (!svg) return;
    const labels = val === 'monthly' ? ['Jan','Feb','Mar','Apr','May','Jun'] : ['Apr 28','May 5','May 12','May 19','May 26','Jun 2'];
    const s1 = val === 'monthly' ? "40,30 110,45 180,35 250,55 320,40 390,60 460,45 500,40" : "40,50 110,35 180,45 250,25 320,40 390,30 460,45 500,50";
    const s2 = val === 'monthly' ? "40,90 110,105 180,95 250,115 320,100 390,120 460,105 500,100" : "40,110 110,95 180,105 250,85 320,100 390,90 460,105 500,110";
    const s3 = val === 'monthly' ? "40,160 110,145 180,155 250,135 320,150 390,130 460,145 500,160" : "40,140 110,155 180,145 250,165 320,150 390,170 460,155 500,140";
    svg.innerHTML = `
        <line x1="40" y1="10" x2="500" y2="10" stroke="var(--border)" stroke-dasharray="4"/>
        <line x1="40" y1="60" x2="500" y2="60" stroke="var(--border)" stroke-dasharray="4"/>
        <line x1="40" y1="110" x2="500" y2="110" stroke="var(--border)" stroke-dasharray="4"/>
        <line x1="40" y1="160" x2="500" y2="160" stroke="var(--border)" stroke-dasharray="4"/>
        <text x="30" y="15" fill="var(--text3)" font-size="10" text-anchor="end">400</text>
        <text x="30" y="65" fill="var(--text3)" font-size="10" text-anchor="end">300</text>
        <text x="30" y="115" fill="var(--text3)" font-size="10" text-anchor="end">200</text>
        <text x="30" y="165" fill="var(--text3)" font-size="10" text-anchor="end">100</text>
        <polyline points="${s1}" fill="none" stroke="var(--green)" stroke-width="2"/>
        <polyline points="${s2}" fill="none" stroke="var(--amber)" stroke-width="2"/>
        <polyline points="${s3}" fill="none" stroke="var(--red)" stroke-width="2"/>
        ${labels.map((x,i)=>\`<text x="${[40,110,180,250,320,390][i]}" y="185" fill="var(--text3)" font-size="10" text-anchor="middle">${x}</text>\`).join('')}
    `;
}
function """
text = re.sub(trend_pattern, admin_trend_logic, text, count=1)

with codecs.open('app.py', 'w', 'utf-8') as f:
    f.write(text)

with codecs.open('patch_success.txt', 'w', 'utf-8') as f:
    f.write('Patch successful')
