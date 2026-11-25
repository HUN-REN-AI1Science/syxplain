"""Synthetic demonstration system for the Syxplain paper. Fictitious: no real measurements,
and the "previous study" in the *_prior descriptions does not exist.

A thin-film coating line. Process order and planted laws (true values; each measured
column adds its own instrument noise):

  chamber_pressure = 15 + precursor + 4*flow                               [Pa]
  rate             = 0.06*temp*precursor/(2.5 + precursor) - 0.4*flow      [nm/min]
  thickness        = rate * dep_time                                       [nm]
  grain_size       = -2 + 0.9*sqrt(thickness) + 0.05*anneal_temp - 0.015*power   [nm]
  sheet_resistance = 10*rho/thickness, rho = 20*(1 + 40/grain_size)        [ohm/sq]
                   = 200/thickness + 8000/(grain_size*thickness)
  transmittance    = 92*exp(-0.004*thickness)                              [%]

humidity has no effect on anything.
"""

import json

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

SEED, N = 20261119, 200
rng = np.random.default_rng(SEED)


def u(lo, hi):
    return rng.uniform(lo, hi, N)


precursor, temp, flow = u(1.0, 12.0), u(150.0, 250.0), u(0.5, 4.0)
power, dep_time, anneal_temp, humidity = (
    u(50.0, 300.0),
    u(5.0, 60.0),
    u(200.0, 500.0),
    u(20.0, 60.0),
)

t = {}  # true values
t["chamber_pressure"] = 15.0 + precursor + 4.0 * flow
t["rate"] = 0.06 * temp * precursor / (2.5 + precursor) - 0.4 * flow
t["thickness"] = t["rate"] * dep_time
t["grain_size"] = -2.0 + 0.9 * np.sqrt(t["thickness"]) + 0.05 * anneal_temp - 0.015 * power
t["sheet_resistance"] = 200.0 / t["thickness"] + 8000.0 / (t["grain_size"] * t["thickness"])
t["transmittance"] = 92.0 * np.exp(-0.004 * t["thickness"])
assert min(v.min() for v in t.values()) > 0

m = {  # measured values
    "chamber_pressure": t["chamber_pressure"] + rng.normal(0, 1.5, N),
    "rate": t["rate"] + rng.normal(0, 0.5, N),
    "thickness": t["thickness"] * (1 + rng.normal(0, 0.03, N)) + rng.normal(0, 1.0, N),
    "grain_size": t["grain_size"] + rng.normal(0, 1.5, N),
    "sheet_resistance": t["sheet_resistance"] * (1 + rng.normal(0, 0.04, N)),
    "transmittance": t["transmittance"] + rng.normal(0, 1.0, N),
}
df = pd.DataFrame(
    {
        "sample_id": np.arange(1, N + 1),
        "precursor": precursor.round(2),
        "temp": temp.round(1),
        "flow": flow.round(2),
        "power": power.round(0).astype(int),
        "dep_time": dep_time.round(1),
        "humidity": humidity.round(1),
        "chamber_pressure": m["chamber_pressure"].round(1),
        "rate": m["rate"].round(2),
        "thickness": m["thickness"].round(1),
        "anneal_temp": anneal_temp.round(0).astype(int),
        "grain_size": m["grain_size"].round(1),
        "sheet_resistance": np.array([float(f"{v:.4g}") for v in m["sheet_resistance"]]),
        "transmittance": m["transmittance"].round(1),
    }
)
assert (df.drop(columns="sample_id") > 0).all().all()
df.to_csv("coating_line.csv", index=False)
sh = df.copy()
sh["rate"] = rng.permutation(df["rate"].to_numpy())
sh.to_csv("coating_line_shuffled_rate.csv", index=False)


def r2(y, yhat):
    return float(1 - np.sum((y - yhat) ** 2) / np.sum((y - np.mean(y)) ** 2))


c = {k: df[k].to_numpy(float) for k in df.columns}


def refit(f, X, y, p0):
    p, _ = curve_fit(f, X, y, p0=p0, maxfev=20000)
    return r2(y, f(X, *p)), [float(f"{v:.4g}") for v in p]


ref = {}
ref["rate"] = {
    "planted": refit(
        lambda X, a, k, b: a * X[1] * X[0] / (k + X[0]) - b * X[2],
        (c["precursor"], c["temp"], c["flow"]),
        c["rate"],
        [0.05, 2, 0.3],
    ),
    "without_flow": refit(
        lambda X, a, k: a * X[1] * X[0] / (k + X[0]),
        (c["precursor"], c["temp"]),
        c["rate"],
        [0.05, 2],
    ),
    "prior_langmuir_only": refit(
        lambda p, rmax, k: rmax * p / (k + p), c["precursor"], c["rate"], [9, 2]
    ),
}
ref["thickness"] = {"planted_identity_no_fit": (r2(c["thickness"], c["rate"] * c["dep_time"]), [])}
ref["grain_size"] = {
    "planted": refit(
        lambda X, a, b, d, e: a + b * np.sqrt(X[0]) + d * X[1] - e * X[2],
        (c["thickness"], c["anneal_temp"], c["power"]),
        c["grain_size"],
        [0, 1, 0.05, 0.01],
    ),
    "prior_anneal_only": refit(
        lambda x, a, b: a + b * x, c["anneal_temp"], c["grain_size"], [0, 0.05]
    ),
}
Xs = (c["thickness"], c["grain_size"])
ls = np.log(c["sheet_resistance"])
p, _ = curve_fit(lambda X, a, b: np.log(a / X[0] + b / (X[0] * X[1])), Xs, ls, p0=[200, 8000])
q, _ = curve_fit(lambda d, a: np.log(a / d), c["thickness"], ls, p0=[400])
ref["sheet_resistance"] = {
    "planted_fit_in_log": (
        {
            "r2_raw": r2(c["sheet_resistance"], p[0] / Xs[0] + p[1] / (Xs[0] * Xs[1])),
            "r2_log": r2(ls, np.log(p[0] / Xs[0] + p[1] / (Xs[0] * Xs[1]))),
        },
        [float(f"{v:.4g}") for v in p],
    ),
    "prior_constant_resistivity_fit_in_log": (
        {
            "r2_raw": r2(c["sheet_resistance"], q[0] / c["thickness"]),
            "r2_log": r2(ls, np.log(q[0] / c["thickness"])),
        },
        [float(f"{v:.4g}") for v in q],
    ),
}
ref["transmittance"] = {
    "planted": refit(
        lambda d, a, b: a * np.exp(-b * d), c["thickness"], c["transmittance"], [90, 0.004]
    )
}
ref["chamber_pressure"] = {
    "planted": refit(
        lambda X, a, b, d: a + b * X[0] + d * X[1],
        (c["precursor"], c["flow"]),
        c["chamber_pressure"],
        [15, 1, 4],
    )
}

facts = {
    "seed": SEED,
    "rows": N,
    "r2_true_value_vs_measured": {k: r2(c[k], t[k]) for k in t},
    "reference_fits_on_measured_columns": ref,
    "ranges": {k: [float(df[k].min()), float(df[k].max())] for k in df.columns if k != "sample_id"},
    "corr_precursor_chamber_pressure": float(
        np.corrcoef(c["precursor"], c["chamber_pressure"])[0, 1]
    ),
}
with open("ground_truth.json", "w") as fh:
    json.dump(facts, fh, indent=1)

# ---- problem descriptions -------------------------------------------------------------
D = {
    "precursor": "Partial pressure of the precursor gas in the reactor, a process setting (Pa)",
    "temp": "Substrate temperature during deposition, a process setting (deg C)",
    "flow": "Carrier gas flow rate, a process setting (L/min)",
    "power": "Plasma power during deposition, a process setting (W)",
    "dep_time": "Duration of the deposition, a process setting (min)",
    "humidity": "Relative humidity of the laboratory air during the run (%)",
    "chamber_pressure": "Total chamber pressure read by the gauge during deposition (Pa)",
    "rate": "Film deposition rate measured in situ by a quartz crystal monitor (nm/min)",
    "thickness": "Film thickness after deposition, measured by ellipsometry (nm)",
    "anneal_temp": "Temperature of the annealing step after deposition, a process setting (deg C)",
    "grain_size": "Mean grain size of the annealed film, from X-ray diffraction (nm)",
    "sheet_resistance": "Sheet resistance of the annealed film, four-point probe (ohm per square)",
    "transmittance": "Optical transmittance of the annealed film at 550 nm (%)",
}
order = [
    "precursor",
    "temp",
    "flow",
    "power",
    "dep_time",
    "humidity",
    "chamber_pressure",
    "rate",
    "thickness",
    "anneal_temp",
    "grain_size",
]
upstream = {
    "chamber_pressure": order[:6],
    "rate": order[:7],
    "thickness": order[:8],
    "grain_size": order[:10],
    "sheet_resistance": order,
    "transmittance": order,
}
base = (
    "Thin-film coating line in a laboratory. Each row is one sample: a film is deposited in a "
    "plasma-assisted reactor under the listed process settings, its deposition rate is monitored "
    "in situ, the film is then annealed, and its thickness, grain size, sheet resistance and "
    "optical transmittance are measured. We want an interpretable equation for {what}, to choose "
    "settings for new samples."
)
L = ref["rate"]["prior_langmuir_only"][1]
prior = (
    " Background from earlier work on this type of coating line: a previous study reported that "
    f"(1) the deposition rate follows a Langmuir-type saturation in the precursor partial pressure, "
    f"rate = Rmax * precursor / (K + precursor), with Rmax = {L[0]:.1f} nm/min and K = {L[1]:.1f} Pa, "
    "with no significant dependence on substrate temperature between 150 and 250 deg C; "
    "(2) the thickness equals the deposition rate times the deposition time; "
    "(3) the grain size is set by the annealing temperature alone; "
    "(4) the film has a constant resistivity, so the sheet resistance is inversely proportional "
    "to the thickness; and (5) the transmittance decays exponentially with the thickness "
    "(Beer-Lambert law)."
)
for tgt, feats in upstream.items():
    for name, text in [("clean", base), ("prior", base + prior)]:
        problem = {
            "project_description": text.format(what="the " + D[tgt].split(",")[0].lower()),
            "target_variable": tgt,
            "features": {f: D[f] for f in feats},
        }
        with open(f"problem_{tgt}_{name}.json", "w") as fh:
            json.dump(problem, fh, indent=1)
print(json.dumps(facts, indent=1))
