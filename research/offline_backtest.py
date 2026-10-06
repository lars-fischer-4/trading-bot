"""Freqtrade offline: Marktdaten aus den vorhandenen Kursdateien statt von der Boerse."""
import glob, os, sys
from freqtrade.exchange import exchange as exmod
from freqtrade.util import dt_ts

DATA = os.environ.get("BT_DATA", "data")
SYMS = sorted({os.path.basename(f).split("-")[0].replace("_", "/") for f in glob.glob(f"{DATA}/*-5m.feather")})

def market(sym):
    base, quote = sym.split("/")
    return {"id": base + "-" + quote, "symbol": sym, "base": base, "quote": quote, "baseId": base, "quoteId": quote,
            "type": "spot", "spot": True, "margin": False, "swap": False, "future": False, "option": False,
            "contract": False, "active": True, "linear": None, "inverse": None, "contractSize": None,
            "taker": 0.0025, "maker": 0.0015,
            "precision": {"amount": 1e-8, "price": 1e-10}, "limits": {"amount": {"min": 1e-8, "max": None},
            "price": {"min": None, "max": None}, "cost": {"min": 5, "max": None}, "leverage": {"min": None, "max": None}}, "info": {}}

def fake_reload(self, force=False, *, load_leverage_tiers=True):
    mk = [market(s) for s in SYMS]
    self._api.set_markets(mk)
    self._api_async.set_markets(mk)
    self._markets = self._api.markets
    self._last_markets_refresh = dt_ts()

exmod.Exchange.reload_markets = fake_reload
from freqtrade.main import main
main(sys.argv[1:])
