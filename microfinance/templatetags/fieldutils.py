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


GUARANTOR_FIELDS = (
    "Guarantor_Father_Name", "Guarantor_Mother_Name", "Guarantor_Local_Address",
    "Guarantor_Permanent_Address", "Guarantor_Occupation", "Guarantor_Designation",
    "Guarantor_Office_Address", "Guarantor_Phone_no", "Guarantor_Phone_no2",
    "Guarantor_Security_Docs",
)


@register.filter
def has_no_details(guarantor):
    """True when every detail field on a guarantor is a placeholder.

    30% of guarantor records (673 of 2,246) are in this state, so the template
    shows a short message rather than an empty grid.
    """
    return all(is_blank(getattr(guarantor, f, None)) for f in GUARANTOR_FIELDS)
