const SKILLS = ['A', 'B', 'C', 'D'];
let problem = null;
let lastResult = null;
let activeTab = 'demand';

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const number = (value, digits = 2) => Number(value).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits});

async function loadDefaults() {
  const response = await fetch('/api/defaults');
  problem = await response.json();
  renderEditors();
  markDefault(true);
  await runModel();
}

function markDefault(isDefault = false) {
  const pill = $('#problem-status');
  pill.textContent = isDefault ? 'DEFAULT' : 'CUSTOM';
  pill.classList.toggle('custom', !isDefault);
}

function renderEditors() {
  renderDemandEditor();
  renderOfficerEditor();
  renderCostEditor();
  renderSolverEditor();
  showTab(activeTab);
}

function renderDemandEditor() {
  const labels = Object.fromEntries(problem.skills.map((skill) => [skill.key, skill.label]));
  $('#demand-editor').innerHTML = `
    <div class="table-scroll"><table class="input-table demand-table">
      <thead><tr><th>Period</th>${SKILLS.map((key) => `<th><b>${key}</b><small>${escapeHtml(labels[key])}</small></th>`).join('')}<th></th></tr></thead>
      <tbody>${problem.periods.map((period, index) => `
        <tr data-period="${escapeHtml(period)}">
          <td><input class="period-name" value="${escapeHtml(period)}" aria-label="Period ${index + 1} name" /></td>
          ${SKILLS.map((key) => `<td><input type="number" min="0" max="100" step="1" data-demand="${key}" value="${problem.demand[period][key]}" aria-label="${escapeHtml(period)} ${key} demand" /></td>`).join('')}
          <td><button class="row-remove" data-remove-period="${index}" aria-label="Remove ${escapeHtml(period)}">×</button></td>
        </tr>`).join('')}
      </tbody>
    </table></div>`;
}

function renderOfficerEditor() {
  $('#officer-editor').innerHTML = `
    <div class="officer-list">${problem.officer_classes.map((item, index) => `
      <article class="officer-row" data-class-index="${index}">
        <div class="class-main"><input class="class-name" value="${escapeHtml(item.name)}" aria-label="Officer class name" /><label>Count <input class="class-count" type="number" min="0" max="100" step="1" value="${item.count}" /></label><button class="row-remove" data-remove-class="${index}" aria-label="Remove ${escapeHtml(item.name)}">×</button></div>
        <div class="skill-toggles">${SKILLS.map((key) => `<label><input type="checkbox" data-class-skill="${key}" ${item.skills.includes(key) ? 'checked' : ''} /><span>${key}</span></label>`).join('')}</div>
      </article>`).join('')}</div>`;
}

function renderCostEditor() {
  $('#cost-editor').innerHTML = `
    <div class="cost-list">${problem.skills.map((skill, index) => `
      <article class="cost-row" data-skill-index="${index}">
        <div class="skill-badge">${skill.key}</div>
        <label>Name<input class="skill-label" value="${escapeHtml(skill.label)}" /></label>
        <label>CV<input class="skill-cv" type="number" min="0.01" max="2" step="0.01" value="${skill.cv}" /></label>
        <label>Open cost<input class="skill-open" type="number" min="0" step="0.1" value="${skill.open_cost}" /></label>
        <label>Shortage penalty<input class="skill-penalty" type="number" min="0" step="0.5" value="${skill.shortage_penalty}" /></label>
      </article>`).join('')}</div>`;
}

function renderSolverEditor() {
  const solver = problem.solver;
  $('#solver-editor').innerHTML = `
    <div class="solver-grid">
      <label>QAE epsilon <span class="tip-wrap"><button class="tip" type="button" aria-label="Explain QAE epsilon">?</button><span class="field-popover" hidden>Target amplitude-estimation precision. Smaller values imply a larger oracle-query budget.</span></span><input data-solver="epsilon_target" type="number" min="0.001" max="0.25" step="0.001" value="${solver.epsilon_target}" /></label>
      <label>Confidence alpha <span class="tip-wrap"><button class="tip" type="button" aria-label="Explain confidence alpha">?</button><span class="field-popover" hidden>Failure-probability parameter retained from the notebook's IQAE setup.</span></span><input data-solver="alpha" type="number" min="0.001" max="0.5" step="0.001" value="${solver.alpha}" /></label>
      <label>Open-cost search weight <span class="tip-wrap"><button class="tip" type="button" aria-label="Explain open-cost search weight">?</button><span class="field-popover" hidden>Weight applied while searching the quadratic surrogate. Final reporting uses the full open cost.</span></span><input data-solver="alpha_open" type="number" min="0" max="10" step="0.01" value="${solver.alpha_open}" /></label>
      <label>One-officer penalty <span class="tip-wrap"><button class="tip" type="button" aria-label="Explain one-officer penalty">?</button><span class="field-popover" hidden>Notebook QUBO penalty shown for parity. This app enforces eligibility and no double-booking directly.</span></span><input data-solver="one_officer_penalty" type="number" min="0" step="1" value="${solver.one_officer_penalty}" /></label>
      <label>Random seed<input data-solver="seed" type="number" min="0" step="1" value="${solver.seed}" /></label>
    </div>
    <div class="probability-editor"><p>Five-scenario probabilities</p><div>${problem.probabilities.map((value, index) => `<label>p${index + 1}<input data-probability="${index}" type="number" min="0" max="1" step="0.05" value="${value}" /></label>`).join('')}</div><small>Must sum to 1. The default is 0.1 / 0.2 / 0.4 / 0.2 / 0.1.</small></div>`;
}

function collectProblem() {
  const updatedPeriods = [];
  const updatedDemand = {};
  document.querySelectorAll('#demand-editor tbody tr').forEach((row) => {
    const period = row.querySelector('.period-name').value.trim();
    updatedPeriods.push(period);
    updatedDemand[period] = Object.fromEntries(SKILLS.map((key) => [key, Number(row.querySelector(`[data-demand="${key}"]`).value)]));
  });
  problem.periods = updatedPeriods;
  problem.demand = updatedDemand;
  problem.officer_classes = [...document.querySelectorAll('.officer-row')].map((row) => ({
    name: row.querySelector('.class-name').value.trim(),
    count: Number(row.querySelector('.class-count').value),
    skills: SKILLS.filter((key) => row.querySelector(`[data-class-skill="${key}"]`).checked),
  }));
  document.querySelectorAll('.cost-row').forEach((row, index) => {
    problem.skills[index].label = row.querySelector('.skill-label').value.trim();
    problem.skills[index].cv = Number(row.querySelector('.skill-cv').value);
    problem.skills[index].open_cost = Number(row.querySelector('.skill-open').value);
    problem.skills[index].shortage_penalty = Number(row.querySelector('.skill-penalty').value);
  });
  document.querySelectorAll('[data-solver]').forEach((input) => { problem.solver[input.dataset.solver] = Number(input.value); });
  document.querySelectorAll('[data-probability]').forEach((input) => { problem.probabilities[Number(input.dataset.probability)] = Number(input.value); });
  return problem;
}

async function runModel() {
  const button = $('#run-button');
  const error = $('#input-error');
  error.hidden = true;
  button.disabled = true;
  button.classList.add('running');
  button.querySelector('span').textContent = 'Solving model…';
  $('#runtime').textContent = 'Computing…';
  if (!lastResult) {
    $('#result-content').className = 'solve-progress';
    $('#result-content').innerHTML = '<div class="spinner" aria-hidden="true"></div><strong>Building the staffing plan…</strong><span>This usually takes a few seconds.</span>';
  }
  try {
    const response = await fetch('/api/solve', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(collectProblem()),
    });
    const rawResponse = await response.text();
    let payload;
    try {
      payload = JSON.parse(rawResponse);
    } catch {
      throw new Error(`The server returned an unreadable response (HTTP ${response.status}). Restart app.py and reload this page.`);
    }
    if (!response.ok) throw new Error(payload.error || 'The model could not be solved.');
    if (!payload.summary || !Array.isArray(payload.period_results)) {
      throw new Error('The server response is missing optimization results. Restart app.py and try again.');
    }
    lastResult = payload;
    renderResults(payload);
  } catch (caught) {
    const message = caught instanceof Error ? caught.message : 'The model could not be solved.';
    error.textContent = message;
    error.hidden = false;
    $('#runtime').textContent = 'Run failed';
    renderRunError(message);
  } finally {
    button.disabled = false;
    button.classList.remove('running');
    button.querySelector('span').textContent = 'Run optimization';
  }
}

function renderRunError(message) {
  $('#result-content').className = '';
  $('#result-content').innerHTML = `
    <article class="run-error-card" role="alert">
      <span>!</span>
      <div><p class="overline">No result yet</p><h3>Optimization could not finish</h3><p>${escapeHtml(message)}</p><button id="retry-run" type="button">Try again</button></div>
    </article>`;
  $('#retry-run').addEventListener('click', runModel);
}

function normalizeVqeView(result) {
  if (result.vqe_view) return result.vqe_view;
  return {
    executed: false,
    status: 'VQE metadata unavailable',
    logical_qubits: null,
    hamiltonian_terms: null,
    reference_exact_loss: result.summary.optimized.total,
    explanation: 'This result came from an older running server. The staffing output is valid, but restart app.py to see problem-specific VQE mapping counts.',
  };
}

function renderResults(result) {
  const summary = result.summary;
  const vqe = normalizeVqeView(result);
  const direction = summary.reduction >= 0 ? 'cuts' : 'increases';
  const accentClass = summary.reduction >= 0 ? '' : 'negative';
  $('#runtime').textContent = `${number(summary.runtime_ms, 0)} ms · ${summary.total_officers} officers`;
  const maxTotal = Math.max(summary.nominal.total, summary.optimized.total, 1);
  const planTableRows = result.period_results.map((period) => `
    <tr><th>${escapeHtml(period.period)}</th>${period.cells.map((cell) => {
      const delta = cell.optimized - cell.nominal;
      return `<td><span>${cell.nominal}</span><b>→</b><strong>${cell.optimized}</strong><small class="${delta > 0 ? 'up' : delta < 0 ? 'down' : ''}">${delta > 0 ? '+' : ''}${delta}</small></td>`;
    }).join('')}<td>${period.idle_officers}</td></tr>`).join('');
  const qaeRows = result.period_results.map((period) => `
    <tr><th>${escapeHtml(period.period)}</th>${period.cells.map((cell) => `<td><strong>${number(cell.qae.estimate, 2)}</strong><small>${cell.qae.confidence_interval.map((v) => number(v, 2)).join('–')}</small></td>`).join('')}</tr>`).join('');
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  const warningHtml = warnings.length ? `<div class="warning-stack">${warnings.map((item) => `<p>${escapeHtml(item)}</p>`).join('')}</div>` : '';

  $('#result-content').className = '';
  $('#result-content').innerHTML = `
    ${warningHtml}
    <article class="hero-result ${accentClass}">
      <div class="result-kicker">Expected loss change</div>
      <div class="big-number">${number(Math.abs(summary.reduction_percent), 1)}<span>%</span></div>
      <p>The optimized plan ${direction} expected loss by <strong>${number(Math.abs(summary.reduction), 2)}</strong> units.</p>
    </article>
    <div class="metric-grid">
      <article><p>Nominal plan</p><strong>${number(summary.nominal.total)}</strong><span>${number(summary.nominal.open_cost)} open + ${number(summary.nominal.shortfall_cost)} risk</span></article>
      <article class="accent"><p>Optimized plan</p><strong>${number(summary.optimized.total)}</strong><span>${number(summary.optimized.open_cost)} open + ${number(summary.optimized.shortfall_cost)} risk</span></article>
      <article><p>Roster utilization</p><strong>${summary.optimized_assignments}</strong><span>officer-period assignments</span></article>
    </div>
    <article class="comparison-card">
      <div class="card-title"><div><p class="overline">Cost composition</p><h3>Nominal vs optimized</h3></div><button class="text-button" data-scroll-vqe>VQE guide ↓</button></div>
      ${costBar('Nominal', summary.nominal, maxTotal)}
      ${costBar('Optimized', summary.optimized, maxTotal)}
      <div class="legend"><span><i></i> Open cost</span><span><b></b> Expected shortfall</span></div>
    </article>
    <article class="vqe-card" id="vqe-panel">
      <div class="vqe-heading">
        <div><span class="vqe-label">VQE VIEW</span><h3>Turn the staffing QUBO into low energy</h3><p>${escapeHtml(vqe.explanation)}</p></div>
        <span class="not-run-badge">${vqe.logical_qubits == null ? 'RESTART SERVER FOR SCALE' : 'EXPLAINER · NOT RUN'}</span>
      </div>
      <div class="vqe-feature-chips"><span>🔁 Hybrid quantum–classical loop</span><span>📏 Measurement-based energy</span><span>🎯 Approximate candidate bitstrings</span></div>
      <div class="vqe-flow" aria-label="VQE optimization loop">
        <article><b>1</b><div><strong>Ansatz</strong><span>Prepare |ψ(θ)〉</span></div></article><i>→</i>
        <article><b>2</b><div><strong>Measure</strong><span>Estimate 〈H〉</span></div></article><i>→</i>
        <article><b>3</b><div><strong>Update</strong><span>Tune θ classically</span></div></article><i>↻</i>
        <article><b>4</b><div><strong>Sample</strong><span>Read bitstrings</span></div></article>
      </div>
      <div class="vqe-output">
        <div class="vqe-scale">
          <p class="overline">This problem as a direct Ising model</p>
          <div><article><strong>${vqe.logical_qubits == null ? '—' : vqe.logical_qubits.toLocaleString()}</strong><span>logical qubits</span></article><article><strong>${vqe.hamiltonian_terms == null ? '—' : vqe.hamiltonian_terms.toLocaleString()}</strong><span>Hamiltonian terms</span></article><article><strong>${number(vqe.reference_exact_loss)}</strong><span>exact reference loss</span></article></div>
        </div>
        <div class="trace-card">
          <div><p class="overline">Characteristic VQE output</p><strong>Energy should trend down</strong><span>Illustrative convergence trace</span></div>
          <div class="trace-demo" aria-label="Illustrative descending VQE energy trace"><i style="height:88%"></i><i style="height:72%"></i><i style="height:60%"></i><i style="height:51%"></i><i style="height:46%"></i><i style="height:43%"></i></div>
        </div>
      </div>
      <p class="vqe-honesty"><b>Why no VQE number here?</b> The current backend gives a stable exact feasible reference. A real VQE result would depend on the ansatz, optimizer, shot count, and hardware noise, so this panel labels the mapping without inventing a quantum run.</p>
    </article>
    <article class="plan-card">
      <div class="card-title"><div><p class="overline">Staffing decision</p><h3>Counters to open</h3></div><span class="table-hint">nominal → optimized</span></div>
      <div class="table-scroll"><table class="plan-table"><thead><tr><th>Period</th>${result.skill_totals.map((skill) => `<th><b>${skill.key}</b><small>${escapeHtml(skill.label)}</small></th>`).join('')}<th>Idle</th></tr></thead><tbody>${planTableRows}</tbody></table></div>
    </article>
    <details class="detail-card">
      <summary><div><p class="overline">Quantum check</p><h3>QAE expected shortfall at nominal capacity</h3></div><span>View estimates</span></summary>
      <div class="detail-content"><p class="detail-note">The estimate is the noiseless ancilla amplitude from the notebook's exact payoff encoding; the interval shows the selected epsilon envelope.</p><div class="table-scroll"><table class="qae-table"><thead><tr><th>Period</th>${result.skill_totals.map((skill) => `<th>${skill.key}<small>${escapeHtml(skill.label)}</small></th>`).join('')}</tr></thead><tbody>${qaeRows}</tbody></table></div></div>
    </details>
    <details class="detail-card">
      <summary><div><p class="overline">Eligibility</p><h3>Skill capacity &amp; decoded assignments</h3></div><span>View roster</span></summary>
      <div class="detail-content"><div class="capacity-grid">${result.skill_totals.map((skill) => `<article><span>${skill.key}</span><div><strong>${skill.qualified_officers}</strong><small>${escapeHtml(skill.label)}-qualified</small></div></article>`).join('')}</div>${assignmentMarkup(result)}</div>
    </details>`;
  document.querySelectorAll('[data-scroll-vqe]').forEach((button) => button.addEventListener('click', () => $('#vqe-panel').scrollIntoView({behavior: 'smooth', block: 'center'})));
}

function costBar(label, score, maxTotal) {
  const totalWidth = 100 * score.total / maxTotal;
  const openWidth = score.total ? 100 * score.open_cost / score.total : 0;
  return `<div class="bar-row"><span>${label}</span><div class="bar-track"><div class="bar" style="width:${totalWidth}%"><i style="width:${openWidth}%"></i><b style="width:${100-openWidth}%"></b></div></div><strong>${number(score.total, 1)}</strong></div>`;
}

function assignmentMarkup(result) {
  return `<div class="assignment-list">${result.period_results.map((period) => {
    const entries = result.assignments[period.period];
    const groups = Object.fromEntries(SKILLS.map((key) => [key, []]));
    Object.entries(entries).forEach(([officer, skill]) => groups[skill].push(officer));
    return `<article><h4>${escapeHtml(period.period)}</h4><div>${SKILLS.map((key) => `<p><b>${key}</b><span>${groups[key].map(escapeHtml).join(', ') || 'None'}</span></p>`).join('')}</div></article>`;
  }).join('')}</div>`;
}

function showTab(tab) {
  activeTab = tab;
  document.querySelectorAll('.step-nav button').forEach((button) => button.classList.toggle('active', button.dataset.tab === tab));
  document.querySelectorAll('.editor-tab').forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${tab}`));
}

function addPeriod() {
  collectProblem();
  if (problem.periods.length >= 12) return;
  let index = problem.periods.length + 1;
  let name = `Period ${index}`;
  while (problem.periods.includes(name)) name = `Period ${++index}`;
  problem.periods.push(name);
  problem.demand[name] = Object.fromEntries(SKILLS.map((key) => [key, 0]));
  renderDemandEditor();
  markDefault(false);
}

function addClass() {
  collectProblem();
  problem.officer_classes.push({name: `Class ${problem.officer_classes.length + 1}`, count: 1, skills: [...SKILLS]});
  renderOfficerEditor();
  markDefault(false);
}

function closeAllPopovers(except = null) {
  document.querySelectorAll('.help-popover, .field-popover').forEach((popover) => {
    if (popover !== except) popover.hidden = true;
  });
  if (except !== $('#method-popover')) $('#help-button').setAttribute('aria-expanded', 'false');
}

function toggleMainHelp(event) {
  event.stopPropagation();
  const popover = $('#method-popover');
  const willOpen = popover.hidden;
  closeAllPopovers(popover);
  popover.hidden = !willOpen;
  $('#help-button').setAttribute('aria-expanded', String(willOpen));
}

document.addEventListener('click', (event) => {
  const tab = event.target.closest('[data-tab]');
  if (tab) showTab(tab.dataset.tab);
  const removePeriod = event.target.closest('[data-remove-period]');
  if (removePeriod) {
    collectProblem();
    if (problem.periods.length > 1) {
      const removed = problem.periods.splice(Number(removePeriod.dataset.removePeriod), 1)[0];
      delete problem.demand[removed];
      renderDemandEditor(); markDefault(false);
    }
  }
  const removeClass = event.target.closest('[data-remove-class]');
  if (removeClass) {
    collectProblem();
    if (problem.officer_classes.length > 1) {
      problem.officer_classes.splice(Number(removeClass.dataset.removeClass), 1);
      renderOfficerEditor(); markDefault(false);
    }
  }
  const tipButton = event.target.closest('.tip');
  if (tipButton) {
    event.stopPropagation();
    const popover = tipButton.nextElementSibling;
    const willOpen = popover.hidden;
    closeAllPopovers(popover);
    popover.hidden = !willOpen;
  } else if (!event.target.closest('.help-popover, .help-wrap, .field-popover')) {
    closeAllPopovers();
  }
});

document.addEventListener('input', (event) => {
  if (event.target.closest('.editor-area')) markDefault(false);
});

$('#run-button').addEventListener('click', runModel);
$('#reset-button').addEventListener('click', loadDefaults);
$('#add-period').addEventListener('click', addPeriod);
$('#add-class').addEventListener('click', addClass);
$('#help-button').addEventListener('click', toggleMainHelp);
$('#close-help').addEventListener('click', (event) => { event.stopPropagation(); closeAllPopovers(); });
$('#load-json').addEventListener('click', () => $('#json-file').click());
$('#json-file').addEventListener('change', async (event) => {
  try {
    problem = JSON.parse(await event.target.files[0].text());
    renderEditors(); markDefault(false);
  } catch { $('#input-error').textContent = 'That file is not valid JSON.'; $('#input-error').hidden = false; }
  event.target.value = '';
});
$('#export-json').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify(collectProblem(), null, 2)], {type: 'application/json'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob); link.download = 'checkpoint-problem.json'; link.click(); URL.revokeObjectURL(link.href);
});

loadDefaults().catch((error) => {
  $('#input-error').textContent = `Could not start the app: ${error.message}`;
  $('#input-error').hidden = false;
});
