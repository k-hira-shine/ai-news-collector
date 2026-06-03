#!/usr/bin/env python3
"""docs/*.html に incident CSS が <style> 外へ漏れていないか検査。漏れがあれば exit 1。"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from incident_status import find_leaked_incident_css_files


def main() -> int:
    leaked = find_leaked_incident_css_files()
    if not leaked:
        print("OK: incident CSS leak not found in docs/*.html")
        return 0
    print("FAIL: incident CSS leaked outside <style> in:", ", ".join(sorted(leaked)))
    print("See .cursor/docs/incident-display-css-leak.md")
    print("Fix: python3 -c \"from incident_status import repair_leaked_incident_css_in_docs; repair_leaked_incident_css_in_docs()\"")
    return 1


if __name__ == "__main__":
    sys.exit(main())
