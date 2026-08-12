"""Shared numeric coercion, used by both the Sheets sync path and the manual
entry form so a value typed as "1,234" or left blank behaves identically
regardless of where it came from.
"""


def coerce_numeric(raw):
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace(",", "")
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None
