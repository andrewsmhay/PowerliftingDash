from pathlib import Path
from playwright.sync_api import sync_playwright

base = "http://127.0.0.1:8091"
out = Path("/home/user/workspace/PowerliftingDash/docs/screenshots")
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    console_errors = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

    page.goto(base + "/", wait_until="networkidle")
    page.wait_for_selector(".grid-stack-item", state="visible")
    page.screenshot(path=str(out / "dashboard_customisation_default.png"), full_page=True)
    default_widgets = page.locator(".grid-stack-item").count()
    analytics_visible = page.locator("text=DOTS Score").count() == 1

    page.get_by_role("button", name="Edit dashboard").click()
    page.wait_for_selector("#widget-tray:not([hidden])")
    page.wait_for_selector(".widget-remove", state="visible")
    page.screenshot(path=str(out / "dashboard_customisation_edit.png"), full_page=True)
    health_tray_visible = page.locator("#widget-tray").get_by_text("Distance", exact=True).count() == 1
    remove_count = page.locator(".widget-remove").count()

    add_button = page.locator('.tray-add[data-widget-id="health.distance_km"]')
    add_button.click()
    page.wait_for_function("document.querySelectorAll('.grid-stack-item').length > 28")
    page.get_by_role("button", name="Save").click()
    page.wait_for_selector("#edit-dashboard-btn:not([hidden])")
    saved_count = page.locator(".grid-stack-item").count()

    page.get_by_role("button", name="Edit dashboard").click()
    page.get_by_role("button", name="Cancel").click()
    page.wait_for_selector("#edit-dashboard-btn:not([hidden])")

    page.get_by_role("button", name="Edit dashboard").click()
    page.get_by_role("button", name="Reset to default").click()
    page.wait_for_selector("#edit-dashboard-btn:not([hidden])")
    reset_count = page.locator(".grid-stack-item").count()

    page.goto(base + "/settings", wait_until="networkidle")
    page.wait_for_selector("#lifter_sex")
    page.screenshot(path=str(out / "settings_dots_sex.png"), full_page=True)
    selected_sex = page.locator("#lifter_sex").input_value()

    mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    mobile.goto(base + "/", wait_until="networkidle")
    mobile.wait_for_selector(".grid-stack-item", state="visible")
    mobile.screenshot(path=str(out / "dashboard_customisation_mobile.png"), full_page=False)
    mobile_width = mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    print({
        "default_widgets": default_widgets,
        "analytics_visible": analytics_visible,
        "health_tray_visible": health_tray_visible,
        "remove_count": remove_count,
        "saved_count": saved_count,
        "reset_count": reset_count,
        "selected_sex": selected_sex,
        "mobile_no_horizontal_overflow": mobile_width,
        "console_errors": console_errors,
    })
    browser.close()
