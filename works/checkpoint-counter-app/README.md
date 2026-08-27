# Checkpoint Counter Lab

Checkpoint Counter Lab is a local browser application for exploring uncertainty-aware checkpoint counter staffing. It is based on `QAE/checkpoint_counter_final.ipynb`, with supporting QAE concepts taken from `QAE/2409.07183v1.pdf`.

The default problem follows the notebook's demand, cost, and skill structure. The source material is inconsistent about roster size: its class table totals 31, while the stated problem size is 30. This local default uses the stated 30-officer version by setting Class 1 to 23 officers.

- 30 officers in five skill classes
- four checkpoint types: Human (A), Motorcycle (B), Car (C), and Truck (D)
- Morning, Lunch, Afternoon, and Night demand
- five-point stochastic demand with skill-specific coefficients of variation
- the notebook's counter-opening costs, shortage penalties, and solver settings

With the local 30-officer defaults and the seeded SA settings, the application returns:

| Plan | Open cost | Expected shortfall cost | Total |
| --- | ---: | ---: | ---: |
| Nominal mean-case | 97.00 | 122.00 | **219.00** |
| Optimized | 120.00 | 49.50 | **169.50** |

That is a **49.50-unit (22.6%) reduction** in total expected loss.

## What you can change

The left-side editor supports:

- nominal demand for every checkpoint type and period;
- adding, removing, and renaming periods;
- officer-class counts and skill eligibility;
- checkpoint labels, demand volatility (CV), open cost, and shortage penalty;
- five demand-scenario probabilities;
- QAE epsilon/alpha, QUBO penalty, SA reads/sweeps, and random seed;
- importing or exporting the complete problem as JSON.

The results emphasize the loss comparison, recommended counter counts, exact cost breakdown, QAE shortfall checks, a clearly labeled VQE view, skill capacity, and decoded officer assignments. Short explanations use in-page speech bubbles and expandable result sections, so no browser alert or modal dialog interrupts normal use.

The equation cards are typeset from TeX with pinned KaTeX 0.18.4 assets loaded from jsDelivr. If the CDN is unavailable, the same equations remain visible as readable text fallbacks.

## Run locally

Requirements:

- Python 3.10 or newer
- `numpy`, `dimod`, and `dwave-samplers` (installed by `requirements.txt`)

From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765) in a browser. The server binds to localhost only.

## Docker and Cloud Run

The included `Dockerfile` runs the application as a non-root user, listens on `0.0.0.0`, and reads the Cloud Run `PORT` environment variable (`8080` in the image).

Build and test it locally from this directory:

```powershell
docker build -t checkpoint-counter-app .
docker run --rm -p 8080:8080 checkpoint-counter-app
```

Then open [http://localhost:8080](http://localhost:8080). When configuring a Git-based Cloud Run deployment, select `checkpoint-counter-app/Dockerfile` as the Dockerfile source location if this application remains inside the repository's `checkpoint-counter-app` directory. That directory must be used as the Docker build context.

### Publish from the Google Cloud console

The simplest console-only workflow is continuous deployment from a Git repository:

1. Push this project to GitHub, GitLab, or Bitbucket. Keep `Dockerfile`, `app.py`, `model.py`, `requirements.txt`, and `static/` together inside `checkpoint-counter-app/`.
2. In Google Cloud Console, select the target project and enable the **Cloud Run API** and **Cloud Build API** when prompted.
3. Open **Cloud Run**, click **Deploy container**, choose **Service**, and select **Continuously deploy new revisions from a source repository**.
4. Click **Set up with Cloud Build** (or Developer Connect for a supported provider), authenticate the repository provider, and select the repository.
5. Choose the deployment branch. For **Build type**, select **Dockerfile**. Set the source location to `checkpoint-counter-app/Dockerfile`; the containing `checkpoint-counter-app` directory is the Docker build context.
6. Return to the service form and set a permanent service name and region. Under container settings, use container port `8080` if the field is shown. No custom `PORT` value is required because Cloud Run supplies it.
7. For a public website, choose **Allow public access**. Keep authentication required if the application should remain private.
8. Click **Create**. Follow the build/deployment status on the service details page, then open the generated HTTPS URL.
9. Later pushes to the selected branch trigger a new Docker build and Cloud Run revision automatically.

If your organization does not permit repository connections, build and push the image to Artifact Registry first, then choose **Deploy one revision from an existing container image** in the Cloud Run form.

### If the result area is empty

Reload the page once. The frontend now accepts both the current API response and older responses that do not include `vqe_view`, so the staffing result remains visible during a server upgrade. If the page shows a restart message, stop the old process, run `python app.py` again, and reload. Failed runs are displayed in the result area with a **Try again** button instead of leaving an endless loading placeholder.

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

### QUBO and simulated annealing

As in the notebook, the exact shortfall curve is fitted with

```text
L_hat(n) = a2*n^2 + a1*n + a0.
```

Following `checkpoint_counter_final.ipynb`, the application creates one binary variable `x[o,s,t]` for every officer, eligible skill, and time period. It expands `n[s,t] = sum_o x[o,s,t]` into linear and pairwise terms and builds

```text
H_QUBO = alpha * sum c[s] x[o,s,t]
       + P_one * sum x[o,s,t] x[o,s',t]
       + sum p[s] * L_hat[s,t](sum_o x[o,s,t]).
```

Skill eligibility is enforced by omitting ineligible variables. The pairwise `P_one` term penalizes assigning one officer to more than one skill in a period.

The QUBO dictionary is converted with `dimod.BinaryQuadraticModel.from_qubo` and sampled by `dwave.samplers.SimulatedAnnealingSampler`. Defaults match the notebook: 200 reads, 400 sweeps, and seed 7. The lowest-energy sample is decoded and checked for double-booking; if it is infeasible, the API asks for a larger penalty or sampling budget. Because SA is heuristic, the result is the best sampled plan, not a proof of the global optimum. The final comparison is evaluated against the exact discrete shortfall curve, just like the notebook's final validation.

The editable `one_officer_penalty` is therefore active in the app's QUBO, not merely retained as notebook metadata.

### VQE view

The result page also explains how the same QUBO could be handled by a Variational Quantum Eigensolver:

1. map binary staffing variables to an Ising Hamiltonian;
2. prepare a parameterized ansatz state;
3. estimate the Hamiltonian expectation value through measurements;
4. update the circuit parameters with a classical optimizer;
5. sample low-energy bitstrings and check staffing feasibility.

The panel reports the direct-mapping scale (logical qubits and Hamiltonian terms), the exact evaluation of the SA plan, and the characteristic VQE outputs: an energy-convergence trace and candidate bitstrings. It is deliberately labeled **VQE not executed**. The backend does not fabricate a VQE result; a real value would depend on the ansatz, optimizer, shot count, and hardware noise.

## API

- `GET /api/health` - server status
- `GET /api/defaults` - default editable problem JSON
- `POST /api/solve` - validate and solve a submitted problem JSON

Invalid input returns HTTP 400 with an English error message.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The test suite checks the current default roster totals, worked stochastic distribution, reproducible seeded SA output, explicit QUBO size, decoded assignment eligibility, custom-cost behavior, and validation errors.

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
