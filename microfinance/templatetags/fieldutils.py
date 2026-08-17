from django import template

register = template.Library()

# Values that mean "nothing recorded" in this data. Records commonly carry a
# literal dot, dash or "not specified" instead of a blank.
PLACEHOLDERS = {"", ".", "-", "--", "none", "not specified", "n/a", "na", "nil"}


@register.filter
def is_blank(value):
    """True when a field carries no real information."""
    if value is None:
        return True
    return str(value).strip().lower() in PLACEHOLDERS
