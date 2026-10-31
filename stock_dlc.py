# SPDX-FileCopyrightText: 2026 Ben Balter
# SPDX-License-Identifier: MIT
"""
Where to find the Furby Connect's stock DLC, which every build here starts from.

halloween.py, spooky_eyes.py, probe.py and the rest change a stock DLC rather
than write one from nothing, since a Furby needs the stock DLC's action table,
sequences and motor routines to play anything. The stock DLC is Hasbro's, so
this repo doesn't ship it: bring your own, at dlc/stock.dlc (gitignored) or
wherever FURBY_STOCK_DLC points.

Tests and CI use tools/synthetic_dlc.py instead, a stand-in with the same shape
and no Hasbro content, which can't go on a Furby.
"""

import os

ENV = "FURBY_STOCK_DLC"
DEFAULT = "./dlc/stock.dlc"
HOW = """\
No stock DLC at {path}. Everything here builds on the Furby Connect's own DLC,
which is Hasbro's, so this repo doesn't include it. To get one:

- The Furby Connect World app downloaded it as tu003410.dlc (English Furbies).
  Hasbro's servers stopped serving it (checked October 2026), so use a copy
  you already have, from an old phone or tablet's app data, a backup, or a
  Furby-hacking project you trust.
- Put it at dlc/stock.dlc, or point {env} at it:
      FURBY_STOCK_DLC=~/Downloads/tu003410.dlc uv run halloween.py

Just running the tests? They build their own stand-in (tools/synthetic_dlc.py)."""


def path():
    """The stock DLC's path: FURBY_STOCK_DLC if set, else dlc/stock.dlc."""
    return os.environ.get(ENV) or DEFAULT


def require(dlc_in=None):
    """dlc_in, or the stock DLC's path, if the file is there; otherwise stop and say how to get one."""
    dlc_in = dlc_in or path()
    if not os.path.exists(dlc_in):
        raise SystemExit(HOW.format(path=dlc_in, env=ENV))
    return dlc_in
