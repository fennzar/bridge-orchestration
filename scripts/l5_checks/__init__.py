"""L5 edge-case checks package (138 tests across 14 categories)."""
from .sec import CHECKS as _SEC
from .sc import CHECKS as _SC
from .cons import CHECKS as _CONS
from .rr import CHECKS as _RR
from .conc import CHECKS as _CONC
from .watch import CHECKS as _WATCH
from .conf import CHECKS as _CONF
from .rec import CHECKS as _REC
from .asset import CHECKS as _ASSET
from .dex import CHECKS as _DEX
from .priv import CHECKS as _PRIV
from .load import CHECKS as _LOAD
from .timeouts import CHECKS as _TIME
from .fe import CHECKS as _FE

ALL_CHECKS: dict = {}
for _m in [_SEC, _SC, _CONS, _RR, _CONC, _WATCH, _CONF, _REC, _ASSET, _DEX, _PRIV, _LOAD, _TIME, _FE]:
    ALL_CHECKS.update(_m)

CATEGORY_MAP = {
    "SEC": sorted(_SEC), "SC": sorted(_SC),
    "CONS": sorted(_CONS), "RR": sorted(_RR), "CONC": sorted(_CONC),
    "WATCH": sorted(_WATCH), "CONF": sorted(_CONF), "REC": sorted(_REC),
    "ASSET": sorted(_ASSET), "DEX": sorted(_DEX),
    "PRIV": sorted(_PRIV), "LOAD": sorted(_LOAD), "TIME": sorted(_TIME),
    "FE": sorted(_FE),
}

SUBLEVEL_MAP = {
    "L5.1": sorted(list(_SEC) + list(_SC)),
    "L5.2": sorted(list(_CONS) + list(_RR) + list(_CONC)),
    "L5.3": sorted(list(_WATCH) + list(_CONF) + list(_REC)),
    "L5.4": sorted(list(_ASSET) + list(_DEX)),
    "L5.5": sorted(list(_PRIV) + list(_LOAD) + list(_TIME)),
    "L5.6": sorted(list(_FE)),
}
