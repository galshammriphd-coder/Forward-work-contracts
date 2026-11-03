"""Statistical engine package.

Compatibility shim: factor_analyzer <= 0.5.1 calls sklearn's check_array with the
`force_all_finite` keyword, renamed to `ensure_all_finite` in scikit-learn 1.6+.
"""
from __future__ import annotations

import inspect

from sklearn.utils import validation as _validation

if "force_all_finite" not in inspect.signature(_validation.check_array).parameters:
    _orig_check_array = _validation.check_array

    def _check_array(*args, force_all_finite=None, **kwargs):
        if force_all_finite is not None and "ensure_all_finite" not in kwargs:
            kwargs["ensure_all_finite"] = force_all_finite
        return _orig_check_array(*args, **kwargs)

    import factor_analyzer.factor_analyzer as _fa_mod

    for _mod_name in ("factor_analyzer.factor_analyzer", "factor_analyzer.confirmatory_factor_analyzer", "factor_analyzer.rotator"):
        try:
            _m = __import__(_mod_name, fromlist=["*"])
            if hasattr(_m, "check_array"):
                _m.check_array = _check_array
        except ImportError:  # pragma: no cover
            pass
