"""A report-guided CA–Markov scenario model on a fixed categorical grid.

Kernels describe where influence SPREADS from a source cell (north is row -1).
They are passed to convolution, so a weight southeast of the centre spreads
influence southeast. Model scores are not calibrated probabilities or area quotas.
"""

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import convolve

CLASSES = ("agri", "cforet", "dforet", "hforet", "rockybeach", "sand", "water", "wet_sand", "ghost")
NODATA, SAND, GHOST = -1, 5, 8
SAND_KERNEL = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 3.0], [0.0, 1.0, 4.0]])
AGRI_KERNEL = np.array([[1.0, 2.0, 1.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
GENERIC_KERNEL = np.ones((3, 3), float)
GENERIC_KERNEL[1, 1] = 0


@dataclass(frozen=True)
class Rules:
    resistance: tuple = (0.20, 0.25, 0.50, 0.25, 0.50, 0.10, 1.0, 1.0, 0.20)
    locked: tuple = (0, 6, 7)
    allocation: str = "argmax"
    rule: str = "neighbours"

    def validate(self):
        values = np.asarray(self.resistance, float)
        if (
            values.shape != (9,)
            or not np.isfinite(values).all()
            or ((values < 0) | (values > 1)).any()
        ):
            raise ValueError("Specify nine finite resistance values in [0, 1].")
        if any(not isinstance(i, (int, np.integer)) or i < 0 or i > 8 for i in self.locked):
            raise ValueError("Locked classes must be integer codes 0..8.")
        if self.allocation not in ("argmax", "sample"):
            raise ValueError("allocation must be argmax or sample.")
        if self.rule not in ("neighbours", "own_row"):
            raise ValueError("rule must be neighbours or own_row.")


def check_array(array):
    a = np.asarray(array)
    if a.ndim != 2 or not np.issubdtype(a.dtype, np.integer):
        raise ValueError("Land cover must be a two-dimensional integer array.")
    if not np.isin(a, np.arange(-1, 9)).all():
        raise ValueError("Use -1 for outside/NoData, 0..7 for land cover, 8 for explicit Ghost.")
    return a


def transition_counts(a, b, n=8):
    a, b = check_array(a), check_array(b)
    if a.shape != b.shape:
        raise ValueError("Transition maps must use the same grid.")
    mask = (a >= 0) & (a < n) & (b >= 0) & (b < n)
    return np.bincount(a[mask].astype(np.int64) * n + b[mask], minlength=n * n).reshape(n, n)


def estimate_transition(maps, years, aggregation="mean"):
    """Mean period probabilities (report convention) or pooled transition counts.

    An absent source class contributes no evidence to the mean; a class never
    observed as a source retains itself. Only genuine classes 0..7 are fitted.
    """
    if len(years) < 2 or any(b - a != 5 for a, b in zip(years[:-1], years[1:])):
        raise ValueError("Transition estimation requires increasing five-year intervals.")
    counts = np.stack([transition_counts(maps[a], maps[b]) for a, b in zip(years[:-1], years[1:])])
    totals = counts.sum(axis=2, keepdims=True)
    if aggregation == "pooled":
        raw = counts.sum(axis=0).astype(float)
        sums = raw.sum(axis=1, keepdims=True)
        T = np.divide(raw, sums, out=np.zeros_like(raw), where=sums > 0)
    elif aggregation == "mean":
        p = np.divide(counts, totals, out=np.zeros_like(counts, dtype=float), where=totals > 0)
        support = (totals > 0).sum(axis=0)
        T = np.divide(p.sum(axis=0), support, out=np.zeros((8, 8)), where=support > 0)
    else:
        raise ValueError("aggregation must be mean or pooled.")
    absent = T.sum(axis=1) == 0
    T[absent, np.flatnonzero(absent)] = 1
    return T


def neighbourhood_support(r):
    """Normalised incoming support for each target class, with constant-zero borders."""
    support = np.zeros((9, *r.shape), float)
    for target in range(8):
        kernel = SAND_KERNEL if target == SAND else AGRI_KERNEL if target == 0 else GENERIC_KERNEL
        support[target] = (
            convolve((r == target).astype(float), kernel, mode="constant", cval=0.0) / kernel.sum()
        )
    return support


def source_influence(r):
    """Spread of each source class onto its neighbours, normalised by kernel sum."""
    influence = np.zeros((8, *r.shape), float)
    for source in range(8):
        kernel = SAND_KERNEL if source == SAND else AGRI_KERNEL if source == 0 else GENERIC_KERNEL
        influence[source] = (
            convolve((r == source).astype(float), kernel, mode="constant", cval=0.0) / kernel.sum()
        )
    return influence


def neighbour_scores(r, T, rules):
    """Report formula, summed over the classes found around each pixel:

        score[tc] = sum_fc influence[fc] * T[fc, tc] * (1 - R[fc])

    Each neighbouring class "pushes" the pixel towards the classes it tends to
    become. A forest pixel with sand upwind gets a sand score from the sand row
    of T; one surrounded by forest keeps a high forest score.
    """
    influence = source_influence(r)
    weight = T * (1 - np.asarray(rules.resistance[:8]))[:, None]
    scores = np.zeros((9, *r.shape), float)
    scores[:8] = np.tensordot(weight.T, influence, axes=1)
    for cls in rules.locked:
        if cls < 8:
            current = r == cls
            scores[:, current] = 0
            scores[cls, current] = 1
    ghost = r == GHOST
    if GHOST in rules.locked:
        scores[:, ghost] = 0
        scores[GHOST, ghost] = 1
    else:
        # Ghost can only become sand, and only if sand wins the local vote.
        wins = scores[:8, ghost].argmax(axis=0) == SAND
        has_sand = scores[SAND, ghost] > 0
        scores[:, ghost] = 0
        scores[SAND, ghost] = (wins & has_sand).astype(float)
        scores[GHOST, ghost] = (~(wins & has_sand)).astype(float)
    return scores


def own_row_scores(r, T, rules):
    """Alternative rule: each pixel uses only its own class row of T.

    Off-diagonal: (1-R_source) * T[source,target] * target-neighbour support.
    Diagonal: T[source,source]. With typical persistence (T[i,i] > 0.5) this
    rule almost never changes a pixel, so it is kept only for comparison.
    """
    support = neighbourhood_support(r)
    scores = np.zeros((9, *r.shape), float)
    for source in range(8):
        current = r == source
        if source in rules.locked:
            scores[source, current] = 1
            continue
        resistance = rules.resistance[source]
        for target in range(8):
            if target == source:
                scores[target, current] = T[source, source]
            else:
                scores[target, current] = (
                    (1 - resistance) * T[source, target] * support[target, current]
                )
    ghost = r == GHOST
    if GHOST in rules.locked:
        scores[GHOST, ghost] = 1
    else:
        p_sand = (1 - rules.resistance[GHOST]) * support[SAND, ghost]
        scores[SAND, ghost] = p_sand
        scores[GHOST, ghost] = 1 - p_sand
    return scores


def step(raster, T, rules=Rules(), rng=None):
    """One synchronous five-year update with the selected scoring rule.

    Locked classes keep their state, NoData stays NoData, and a pixel with no
    evidence at all keeps its class. Ties favour persistence.
    """
    r = check_array(raster)
    rules.validate()
    T = np.asarray(T, float)
    if (
        T.shape != (8, 8)
        or not np.isfinite(T).all()
        or (T < 0).any()
        or not np.allclose(T.sum(axis=1), 1)
    ):
        raise ValueError("T must be a finite nonnegative 8x8 row-stochastic matrix.")
    if rules.allocation == "sample" and rng is None:
        raise ValueError("Provide a seeded numpy Generator for sampled allocation.")
    if rules.rule == "neighbours":
        scores = neighbour_scores(r, T, rules)
    else:
        scores = own_row_scores(r, T, rules)
    # Never create land outside the valid domain. Uninformative cells retain state.
    valid = r >= 0
    totals = scores.sum(axis=0)
    no_evidence = valid & (totals == 0)
    for cls in range(9):
        scores[cls, no_evidence & (r == cls)] = 1
    if rules.allocation == "sample":
        probability = np.divide(
            scores, scores.sum(axis=0), out=np.zeros_like(scores), where=scores.sum(axis=0) > 0
        )
        u = rng.random(r.shape)
        new = (np.cumsum(probability, axis=0) < u).sum(axis=0).clip(max=8).astype(np.int16)
    else:
        best = scores.max(axis=0)
        # Prefer persistence in a tie, rather than always giving class 0 the tie.
        new = scores.argmax(axis=0).astype(np.int16)
        for cls in range(9):
            keep = (r == cls) & np.isclose(scores[cls], best, rtol=0, atol=1e-14)
            new[keep] = cls
    new[~valid] = NODATA
    return new


def forecast(maps, years, future_years, rules=Rules(), mode="dynamic", aggregation="mean", seed=42):
    """Report-style rolling updates; simulated maps never become observed evidence.

    dynamic: last four maps, including previous simulations.
    fixed: transitions estimated once from the supplied observed years.
    """
    if mode not in ("dynamic", "fixed"):
        raise ValueError("mode must be dynamic or fixed.")
    last = years[-1]
    if list(future_years) != list(range(last + 5, last + 5 * (len(future_years) + 1), 5)):
        raise ValueError("Forecast dates must be consecutive five-year steps after the base year.")
    history = {year: check_array(maps[year]).copy() for year in years}
    sequence = list(years)
    fixed = estimate_transition(history, years, aggregation)
    rng = np.random.default_rng(seed)
    outputs, audit = {}, []
    for year in future_years:
        window = sequence[-4:] if mode == "dynamic" else list(years)
        T = estimate_transition(history, window, aggregation) if mode == "dynamic" else fixed
        outputs[year] = step(history[sequence[-1]], T, rules, rng)
        audit.append(
            {
                "year": year,
                "transition_years": window,
                "contains_simulated_history": any(y not in years for y in window),
                "matrix": T.tolist(),
            }
        )
        history[year] = outputs[year]
        sequence.append(year)
    return outputs, audit
