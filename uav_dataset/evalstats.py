"""Statistics for honest comparisons: mean +/- 95% CI and paired differences."""
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
