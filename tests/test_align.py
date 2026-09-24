import numpy as np
import pytest

from dictify.align import dtw, median_filter


def reference_dtw(x):
    """Straight port of mlx_whisper.timing.dtw_cpu + backtrace (numba-free)."""
    n, m = x.shape
    cost = np.ones((n + 1, m + 1), dtype=np.float32) * np.inf
    trace = -np.ones((n + 1, m + 1), dtype=np.float32)
    cost[0, 0] = 0
    for j in range(1, m + 1):
        for i in range(1, n + 1):
            c0, c1, c2 = cost[i - 1, j - 1], cost[i - 1, j], cost[i, j - 1]
            if c0 < c1 and c0 < c2:
                c, t = c0, 0
            elif c1 < c0 and c1 < c2:
                c, t = c1, 1
            else:
                c, t = c2, 2
            cost[i, j] = x[i - 1, j - 1] + c
            trace[i, j] = t
    i, j = trace.shape[0] - 1, trace.shape[1] - 1
    trace[0, :] = 2
    trace[:, 0] = 1
    result = []
    while i > 0 or j > 0:
        result.append((i - 1, j - 1))
        if trace[i, j] == 0:
            i, j = i - 1, j - 1
        elif trace[i, j] == 1:
            i -= 1
        else:
            j -= 1
    return np.array(result)[::-1, :].T


@pytest.mark.parametrize("shape", [(1, 1), (1, 7), (6, 1), (12, 40), (37, 90)])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_dtw_matches_reference(shape, seed):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(shape).astype(np.float32)
    assert np.array_equal(dtw(x), reference_dtw(x))


def test_dtw_ties_match_reference():
    x = np.random.default_rng(5).integers(0, 3, size=(15, 30)).astype(np.float32)
    assert np.array_equal(dtw(x), reference_dtw(x))


def test_median_filter_reflect():
    x = np.array([[1, 9, 2, 8, 3, 7, 4]], dtype=np.float32)
    out = median_filter(x, 3)
    # reflect padding: [9, 1, 9, 2, 8, 3, 7, 4, 7]
    assert out.tolist() == [[9, 2, 8, 3, 7, 4, 7]]
    assert out.shape == x.shape


def test_median_filter_short_input_passthrough():
    x = np.ones((2, 3, 2), dtype=np.float32)
    assert median_filter(x, 7) is x
