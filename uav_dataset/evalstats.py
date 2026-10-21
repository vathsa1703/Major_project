"""Statistics for honest comparisons: mean +/- 95% CI and paired differences."""
import math

import numpy as np

Z95 = 1.96          # normal approximation: fine for n >= 30 scenarios (we use 100)


def mean_ci(values):
    """(mean, half_width). Report as 'mean +/- half_width'. One run could be lucky, so we average over seeds."""
    v = np.asarray(values, dtype=float)
    if len(v) < 2:
        return float(v.mean()), 0.0
    return float(v.mean()), float(Z95 * v.std(ddof=1) / np.sqrt(len(v)))


def paired_diff(a, b):
    """Compare two strategies run on the SAME scenarios: mean and CI of (a - b) per scenario.
    Fairer than comparing two separate averages, because it cancels 'that scenario was easy for everyone'.
    Positive mean = a is better than b. The CI excluding 0 means the difference is not luck."""
    return mean_ci(np.asarray(a, dtype=float) - np.asarray(b, dtype=float))


def paired_p(a, b):
    """Two-sided p-value that the mean paired difference a - b is 0 (normal approximation, like the CI above).
    All differences equal: p = 1 if they are 0, else 0."""
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else 0.0
    if se == 0:
        return 1.0 if np.allclose(d, 0) else 0.0
    return float(math.erfc(abs(d.mean()) / se / math.sqrt(2)))


def holm(pvals):
    """Holm-Bonferroni adjusted p-values (same order as given). Compare each with 0.05: controls the chance of ANY
    false 'significant' among all the comparisons reported together."""
    p = np.asarray(pvals, dtype=float)
    order = np.argsort(p, kind="stable")
    adj = np.maximum.accumulate(np.minimum(1.0, p[order] * (len(p) - np.arange(len(p)))))
    out = np.empty_like(p)
    out[order] = adj
    return out
