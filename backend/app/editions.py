"""Editions this backend knows and the modules each one switches on.

The same names are declared in ``primer.yaml`` (``editions``); the machine
checks the passport's choice against them before the build, the backend checks
it again at start (contract 3 rule 11).
"""

EDITIONS: dict[str, tuple[str, ...]] = {"core": ()}
