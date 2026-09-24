"""NumPy replacements for the numba/scipy helpers mlx_whisper uses for word timestamps.

The Mac bundle leaves numba and scipy out (~200 MB). These produce the same results as
mlx_whisper.timing.dtw / median_filter; DTW is vectorized over anti-diagonals, since each
cell only depends on the two previous diagonals.
"""
from __future__ import annotations

import numpy as np


def median_filter(x: np.ndarray, filter_width: int) -> np.ndarray:
    """Median filter along the last axis with reflect padding (output has x's shape)."""
    pad = filter_width // 2
    if x.shape[-1] <= pad:
        return x
    padded = np.pad(x, [(0, 0)] * (x.ndim - 1) + [(pad, pad)], mode="reflect")
    windows = np.lib.stride_tricks.sliding_window_view(padded, filter_width, axis=-1)
    return np.median(windows, axis=-1).astype(np.float32)


def dtw(x: np.ndarray) -> np.ndarray:
    """Dynamic time warping path through cost matrix x, as a (2, L) array of indices."""
    x = np.asarray(x, dtype=np.float32)
    n, m = x.shape
    cost = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
    trace = np.full((n + 1, m + 1), -1, dtype=np.int8)
    cost[0, 0] = 0
    for k in range(2, n + m + 1):  # cells with i + j == k
        i = np.arange(max(1, k - m), min(n, k - 1) + 1)
        if i.size == 0:
            continue
        j = k - i
        c0, c1, c2 = cost[i - 1, j - 1], cost[i - 1, j], cost[i, j - 1]
        t = np.where((c0 < c1) & (c0 < c2), 0, np.where((c1 < c0) & (c1 < c2), 1, 2)).astype(np.int8)
        cost[i, j] = x[i - 1, j - 1] + np.choose(t, [c0, c1, c2])
        trace[i, j] = t
    return _backtrace(trace)


def _backtrace(trace: np.ndarray) -> np.ndarray:
    i, j = trace.shape[0] - 1, trace.shape[1] - 1
    trace[0, :] = 2
    trace[:, 0] = 1
    path = []
    while i > 0 or j > 0:
        path.append((i - 1, j - 1))
        t = trace[i, j]
        if t == 0:
            i -= 1
            j -= 1
        elif t == 1:
            i -= 1
        elif t == 2:
            j -= 1
        else:
            raise ValueError("Unexpected trace value")
    return np.array(path[::-1]).T
