"""
Pytest configuration.

Why this file exists
--------------------
`filterwarnings = ["error"]` in pyproject.toml is deliberate: a warning raised by
our own code should fail the build. But the optional ML stack emits warnings the
first time it is imported — matplotlib's colormap API and dateutil's
`utcfromtimestamp`, both reached through `shap` — and that import happens inside
whichever test touches the model first.

Filtering those by module or message is unreliable, because pytest attributes an
import-time warning to the importing frame rather than to the library at fault.
Importing the stack once here, with warnings suppressed, addresses the cause
instead: by the time any test runs, the modules are already in `sys.modules` and
their import-time warnings have been and gone.

Nothing is silenced for our own code. A deprecation raised anywhere in `apix`
still fails the suite.
"""

from __future__ import annotations

import contextlib
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    # Optional extras — absent in CI, which installs only .[dev]. Their absence
    # is handled by the tests themselves, which skip rather than fail.
    with contextlib.suppress(ImportError):
        import shap  # noqa: F401
    with contextlib.suppress(ImportError):
        import sklearn.ensemble  # noqa: F401
