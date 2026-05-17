from pathlib import Path


def test_app_jsx_has_react_binding_for_classic_transform():
    app_source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")
    assert 'import React, { useMemo, useState } from "react";' in app_source


def test_decorative_dashboard_icons_are_hidden_from_screen_readers():
    # Regression: ISSUE-002 - decorative lucide icons were exposed as anonymous images.
    # Found by /qa on 2026-05-18.
    # Report: .gstack/qa-reports/qa-report-localhost-2026-05-18.md
    app_source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")
    assert 'aria-hidden="true"' in app_source
