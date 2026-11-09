"""Entry point for the BatteryTray installer."""

from __future__ import annotations

import sys

from installer.wizard import main


if __name__ == '__main__':
    sys.exit(main())
