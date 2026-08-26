# Checkpoint Counter Lab

Checkpoint Counter Lab is a local browser application for exploring uncertainty-aware checkpoint counter staffing. It is based on `QAE/checkpoint_counter_final.ipynb`, with supporting QAE concepts taken from `QAE/2409.07183v1.pdf`.

The default problem exactly preserves the notebook's current data:

- 31 officers in five skill classes
- four checkpoint types: Human (A), Motorcycle (B), Car (C), and Truck (D)
- Morning, Lunch, Afternoon, and Night demand
- five-point stochastic demand with skill-specific coefficients of variation
- the notebook's counter-opening costs, shortage penalties, and solver settings

With those defaults, the application reproduces the notebook's expected-loss comparison:

| Plan | Open cost | Expected shortfall cost | Total |
| --- | ---: | ---: | ---: |
| Nominal mean-case | 97.00 | 122.00 | **219.00** |
| Optimized | 124.00 | 39.50 | **163.50** |

That is a **55.50-unit (25.3%) reduction** in total expected loss.

## What you can change

The left-side editor supports:

- nominal demand for every checkpoint type and period;
- adding, removing, and renaming periods;
- officer-class counts and skill eligibility;
- checkpoint labels, demand volatility (CV), open cost, and shortage penalty;
- five demand-scenario probabilities;
- QAE epsilon/alpha and QUBO-related search settings;
- importing or exporting the complete problem as JSON.

The results emphasize the loss comparison, recommended counter counts, exact cost breakdown, QAE shortfall checks, skill capacity, and decoded officer assignments. Short explanations are kept in the `?` method dialog and expandable result sections so they do not dominate normal use.

## Run locally

Requirements:

- Python 3.10 or newer
- `numpy`

From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765) in a browser. The server binds to localhost only.

If Python is already configured with NumPy, `python app.py` is sufficient.

## Model details

### Demand distribution

For each period `t` and skill `s`, the nominal demand `D[s,t]` is expanded into five outcomes. The spread is

```text
spread = max(1, round(D[s,t] * CV[s]))
outcomes = D[s,t] + [-2, -1, 0, 1, 2] * spread
```

Negative demand is clipped to zero and duplicate clipped outcomes are merged.

### Expected shortfall and QAE encoding

For open-counter count `n`, exact expected shortfall is

```text
E[(D - n)+] = Σv p(v) max(v - n, 0).
```

The notebook loads `sqrt(p(v))` as state amplitudes and uses controlled `Ry` rotations to encode normalized shortfall on an objective ancilla. Its probability of measuring `1` is therefore the normalized expected payoff.

To keep this local application small and easy to run, the backend evaluates that noiseless statevector amplitude analytically instead of requiring Qiskit. The displayed QAE estimate is mathematically identical to the exact payoff-ancilla probability for this five-outcome model. The displayed interval is an epsilon-target envelope, not a hardware-noise or shot-sampling confidence interval.

### QUBO-compatible optimization

As in the notebook, the exact shortfall curve is fitted with

```text
L_hat(n) = a2*n^2 + a1*n + a0.
```

The application searches all reachable counter-count combinations under officer skill eligibility and selects the minimum of this same quadratic surrogate. This deterministic feasible search replaces simulated annealing, so repeated runs are stable and no penalty violation can slip into the decoded answer. The final comparison is evaluated against the exact discrete shortfall curve, just like the notebook's final validation.

The `one_officer_penalty` setting is retained and reported for notebook/JSON parity. Direct feasibility enforcement makes it unnecessary in the local solver.

## API

- `GET /api/health` - server status
- `GET /api/defaults` - default editable problem JSON
- `POST /api/solve` - validate and solve a submitted problem JSON

Invalid input returns HTTP 400 with an English error message.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The test suite checks the notebook roster totals, worked stochastic distribution, default 219.00/163.50 result, decoded assignment eligibility, custom-cost behavior, and validation errors.

## Project layout

```text
checkpoint-counter-app/
├── app.py                 # Local HTTP server and JSON API
├── model.py               # Demand, QAE payoff, surrogate, and staffing logic
├── requirements.txt
├── static/
│   ├── index.html         # Browser interface
│   ├── styles.css         # Responsive visual system
│   └── app.js             # Editors, API calls, and result rendering
└── tests/
    └── test_model.py
```

## Scope note

This is a decision-support simulator, not an operational roster system. It does not model breaks, shift continuity across periods, legal working-hour constraints, physical counter availability, or real quantum hardware noise unless you extend the submitted problem and backend accordingly.
