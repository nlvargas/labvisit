from django import template

register = template.Library()


@register.filter
def clp(value):
    if value is None:
        return ""
    return "$" + f"{int(value):,}".replace(",", ".")
