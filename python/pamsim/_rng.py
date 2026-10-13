"""Small, fast, reproducible random number generator for the numba kernels.

Each simulated particle owns its own xoshiro256** stream (seeded through
``numpy.random.SeedSequence``), so results do not depend on how particles are
distributed over threads.  An RNG is the tuple ``(state, spare)``:
``state`` is the ``uint64[4]`` xoshiro state, ``spare`` a ``float64[2]``
holding a cached normal deviate (``spare[0] != 0`` means one is cached).
"""

import math

import numpy as np
from numba import njit, uint64

_INV_2_53 = 1.0 / 9007199254740992.0


def make_state(seed_sequence):
    """Create an RNG from a ``numpy.random.SeedSequence``."""
    s = seed_sequence.generate_state(4, dtype=np.uint64)
    if not np.any(s):
        s[0] = np.uint64(0x9E3779B97F4A7C15)
    return (np.ascontiguousarray(s), np.zeros(2))


@njit(inline="always")
def _rotl(x, k):
    return (x << uint64(k)) | (x >> uint64(64 - k))


@njit(inline="always")
def next_u64(rng):
    s = rng[0]
    result = _rotl(s[1] * uint64(5), 7) * uint64(9)
    t = s[1] << uint64(17)
    s[2] ^= s[0]
    s[3] ^= s[1]
    s[1] ^= s[2]
    s[0] ^= s[3]
    s[2] ^= t
    s[3] = _rotl(s[3], 45)
    return result


@njit(inline="always")
def uniform(rng):
    """Uniform double in [0, 1)."""
    return float(next_u64(rng) >> uint64(11)) * _INV_2_53


@njit(inline="always")
def normal(rng):
    """Standard normal deviate (Marsaglia polar method, pairs cached)."""
    sp = rng[1]
    if sp[0] != 0.0:
        sp[0] = 0.0
        return sp[1]
    while True:
        u = 2.0 * uniform(rng) - 1.0
        v = 2.0 * uniform(rng) - 1.0
        r = u * u + v * v
        if 0.0 < r < 1.0:
            break
    f = math.sqrt(-2.0 * math.log(r) / r)
    sp[0] = 1.0
    sp[1] = v * f
    return u * f


@njit
def geometric(rng, p, max_value):
    """Number of failures before the first success (like std::geometric_distribution).

    Values >= ``max_value`` are rejected and redrawn, which is what libstdc++
    does for ``geometric_distribution<unsigned short>``.
    """
    if p >= 1.0 or not (p > 0.0):
        return 0
    log1mp = math.log1p(-p)
    while True:
        k = math.floor(math.log(1.0 - uniform(rng)) / log1mp)
        if k < max_value:
            return int(k)
