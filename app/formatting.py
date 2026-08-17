"""Small display-string helpers shared between the server-rendered pages
(for the first paint, before JS runs) and the JSON API (for the JS-driven
re-render on every poll), so the title logic only lives in one place.
"""


def dashboard_title(display_name: str | None) -> str:
    """"Powerlifting Dashboard", or "<Name>'s Powerlifting Dashboard" (or
    "<Name>' Powerlifting Dashboard" if the name already ends in s/S) when a
    display name is configured in Settings.
    """
    name = (display_name or "").strip()
    if not name:
        return "Powerlifting Dashboard"
    suffix = "'" if name[-1].lower() == "s" else "'s"
    return f"{name}{suffix} Powerlifting Dashboard"
