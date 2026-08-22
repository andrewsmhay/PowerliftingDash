# Dashboard Customisation Implementation Report

## Delivered work

1. Vendored GridStack 12.3.3 locally and referenced the local stylesheet and script from the dashboard template.
2. Added the widget catalogue, configuration-sensitive default layout, Google Health gating, and all supplied card and chart widget definitions.
3. Added DOTS scoring, bodyweight ratios, current-date-anchored rate of change, and target date projection analytics.
4. Added SQLite migrations for `dashboard_layout` and `lifter_sex`, plus Google Health metric history retrieval.
5. Extended the dashboard data payload with stable widget IDs, analytics, health history, and Google Health configuration state.
6. Added dashboard layout and widget catalogue API routes, including layout validation, reset, and persistence of gated widgets.
7. Added sex selection to Settings with validation and persistence for DOTS calculation.
8. Rebuilt the dashboard as a GridStack layout with edit mode, widget tray, add and remove controls, save, cancel, reset, chart resize handling, and responsive one-column behaviour on narrow screens.
9. Added dashboard edit styling and removed unused fixed dashboard grid rules.
10. Added analytics, widget catalogue, layout route, and extended metrics tests.

## Correctness safeguards

- Every rendered or newly added GridStack item supplies its explicit widget ID to GridStack.
- Saved layouts merge configuration-gated positions that were skipped during rendering, preventing health widgets from being silently removed.
- Rate of change accepts the caller's current date and calculates its cut-off from that date, rather than from the most recent entry.
- The default layout evaluates Google Health configuration each time it is requested.

## Verification

- Full automated suite: **101 passed**, 3483 existing framework deprecation warnings, 13.34 seconds.
- Python static analysis: `pyflakes app/` completed with no findings.
- JavaScript syntax checks completed successfully for `dashboard.js`, `entry_form.js`, `settings.js`, and `targets.js`. The vendored GridStack bundle was intentionally excluded.
- Browser interaction checks passed with a configured demo profile: default dashboard render, analytics cards, Google Health tray items, add and save, cancel, reset, persisted sex selection, responsive mobile layout, and no browser console errors.

## Catalogue count note

The supplied exact catalogue contains 38 widgets: 25 always available entries and 13 Google Health-gated entries, consisting of 12 health fields plus one activity and recovery chart. This conflicts with the written 26 and 12 summary, so the implementation preserves the exact listed widget definitions and gates all health-derived items.

## Files created

- `app/analytics.py`: DOTS, ratio, trend-rate, and target-projection calculation helpers.
- `app/widgets.py`: widget catalogue and dynamic default dashboard layout.
- `app/static/css/gridstack.min.css`: locally vendored GridStack 12.3.3 stylesheet.
- `app/static/js/gridstack-all.js`: locally vendored GridStack 12.3.3 browser bundle.
- `tests/test_analytics.py`: unit tests for dashboard analytics.
- `tests/test_widgets.py`: widget catalogue and default layout tests.
- `tests/test_dashboard_layout_route.py`: dashboard layout and catalogue API tests.
- `docs/dashboard_qa_inventory.md`: browser QA coverage inventory.
- `docs/run_dashboard_visual_qa.py`: repeatable browser interaction and screenshot check.
- `docs/screenshots/dashboard_customisation_default.png`: desktop dashboard QA capture.
- `docs/screenshots/dashboard_customisation_edit.png`: edit-mode dashboard QA capture.
- `docs/screenshots/dashboard_customisation_mobile.png`: mobile dashboard QA capture.
- `docs/screenshots/settings_dots_sex.png`: settings sex-field QA capture.
- `docs/implementation_report.md`: this implementation report.

## Files modified

- `app/config.py`: added the rate-of-change window setting.
- `app/db.py`: added migrations and Google Health metric history helper.
- `app/metrics.py`: added stable widget IDs, analytics payload, health payload, and dashboard configuration state.
- `app/routes/api.py`: added dashboard APIs and lifter sex validation and persistence.
- `app/static/css/dashboard.css`: added GridStack, tray, edit-mode, chart, and responsive dashboard styles.
- `app/static/js/dashboard.js`: replaced the fixed dashboard client with GridStack customisation and widget rendering.
- `app/templates/base.html`: added a page-level extra head block.
- `app/templates/dashboard.html`: replaced the fixed dashboard markup with the configurable dashboard shell and local GridStack assets.
- `app/templates/settings.html`: added the DOTS sex field.
- `tests/test_metrics.py`: added stable-ID and analytics payload coverage.
