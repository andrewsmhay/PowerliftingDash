# Dashboard customisation QA inventory

## User-visible claims

1. Default dashboard displays lift, body composition, analytics, and trend widgets.
2. Edit dashboard exposes Save, Cancel, Reset to default, remove controls, and the widget tray.
3. Google Health widgets appear in the tray only when credentials are configured.
4. Dragging and resizing are enabled only in edit mode.
5. Settings contains the DOTS sex selector.
6. Charts resize after a GridStack resize.

## Functional checks

- Load the dashboard and confirm initial widget grid and analytics cards.
- Enter edit mode, confirm edit controls, tray groups, and remove controls.
- Add a tray widget, save, reload, cancel, and reset the layout.
- Verify a Google Health widget can appear in the configured tray.
- Resize a chart widget and confirm its canvas remains visible.
- Confirm the Settings selector is visible and retains its current choice.
- Exercise a narrow viewport and confirm controls remain reachable.

## Exploratory checks

- Save a layout containing a Google Health widget after credentials are removed, then reload and save again.
- Enter edit mode immediately after a polling interval and confirm the grid remains stable.
