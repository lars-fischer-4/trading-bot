import numpy as np
from numba import njit


@njit(cache=True)
def simulate(o, h, l, c, entry, exit_, tp, sl, max_bars, fee, trail_start, trail_dist):
    """Long-only, eine Position. Einstieg zum Open der Folgekerze.
    Gibt (entry_idx, exit_idx, net_return) zurueck. Stop wird vor TP geprueft (konservativ)."""
    n = len(c)
    ei = np.empty(n, np.int64); xi = np.empty(n, np.int64); rr = np.empty(n, np.float64)
    k = 0
    i = 0
    while i < n - 1:
        if not entry[i]:
            i += 1
            continue
        j = i + 1
        ep = o[j]
        if ep <= 0:
            i += 1
            continue
        stop = ep * (1 - sl)
        target = ep * (1 + tp)
        peak = ep
        xp = -1.0
        x = j
        while x < n:
            if l[x] <= stop:
                xp = min(stop, o[x])
                break
            if h[x] >= target:
                xp = max(target, o[x])
                break
            if h[x] > peak:
                peak = h[x]
                if trail_start > 0 and peak >= ep * (1 + trail_start):
                    ns = peak * (1 - trail_dist)
                    if ns > stop:
                        stop = ns
            if x - j + 1 >= max_bars:
                xp = c[x]
                break
            if exit_[x] and x + 1 < n:
                x += 1
                xp = o[x]
                break
            x += 1
        if xp < 0:
            break
        ei[k] = j; xi[k] = x
        rr[k] = (xp / ep) * (1 - fee) / (1 + fee) - 1
        k += 1
        i = x + 1
    return ei[:k], xi[:k], rr[:k]


@njit(cache=True)
def simulate_limit(o, h, l, c, entry, lim, tp, sl, max_bars, fee_in, fee_tp, fee_sl):
    """Limit-Kauf: Signal auf Kerze i legt Kauforder zu lim[i] fuer Kerze i+1.
    Fuellung, wenn low[i+1] <= lim[i] (Preis = min(lim, open)).
    In der Fuellkerze wird nur der Stop geprueft (konservativ), TP erst ab der naechsten Kerze.
    TP als Limit-Verkauf (Maker), Stop/Zeit als Market (Taker)."""
    n = len(c)
    ei = np.empty(n, np.int64); xi = np.empty(n, np.int64); rr = np.empty(n, np.float64)
    k = 0
    i = 0
    while i < n - 1:
        if not entry[i]:
            i += 1
            continue
        j = i + 1
        if l[j] > lim[i]:
            i += 1
            continue
        ep = min(lim[i], o[j])
        stop = ep * (1 - sl)
        target = ep * (1 + tp)
        xp = -1.0
        f_out = fee_sl
        x = j
        if l[j] <= stop:
            xp = stop
        else:
            x = j + 1
            while x < n:
                if l[x] <= stop:
                    xp = min(stop, o[x])
                    break
                if h[x] >= target:
                    xp = max(target, o[x]); f_out = fee_tp
                    break
                if x - j >= max_bars:
                    xp = c[x]
                    break
                x += 1
        if xp < 0:
            break
        ei[k] = j; xi[k] = x
        rr[k] = (xp * (1 - f_out)) / (ep * (1 + fee_in)) - 1
        k += 1
        i = x + 1
    return ei[:k], xi[:k], rr[:k]
