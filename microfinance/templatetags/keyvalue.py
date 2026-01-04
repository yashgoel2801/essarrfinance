from django import template
register = template.Library()
@register.filter
def keyvalue(dictionary, key):
    if not isinstance(dictionary, dict):
        return 0
    result = dictionary.get(key)
    # If result is a dict (nested), return it; otherwise return 0 if None
    if result is None:
        return 0
    return result
