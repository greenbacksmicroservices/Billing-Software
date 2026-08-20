import decimal
from django import template

register = template.Library()

@register.filter(name='indian_number')
def indian_number(val, decimals=2):
    if val is None or val == '':
        return ''
    try:
        if isinstance(val, (int, float, str)):
            d_val = decimal.Decimal(str(val))
        else:
            d_val = decimal.Decimal(val)
    except Exception:
        return str(val)

    is_negative = d_val < 0
    d_val = abs(d_val)

    if decimals is not None and decimals >= 0:
        fmt = f"%.{decimals}f"
        str_val = fmt % d_val
        parts = str_val.split('.')
        int_part = parts[0]
        dec_part = '.' + parts[1] if len(parts) > 1 else ''
    else:
        str_val = str(d_val)
        parts = str_val.split('.')
        int_part = parts[0]
        dec_part = '.' + parts[1] if len(parts) > 1 and parts[1] != '0' else ''

    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted_int = ','.join(groups) + ',' + last3

    res = formatted_int + dec_part
    if is_negative:
        res = '-' + res
    return res


@register.filter(name='indian_currency')
def indian_currency(val, decimals=2):
    if val is None or val == '':
        return '₹0.00'
    res = indian_number(val, decimals)
    if not res:
        return '₹0.00'
    if res.startswith('-'):
        return '-₹' + res[1:]
    return '₹' + res


@register.filter(name='indian_qty')
def indian_qty(val):
    if val is None or val == '':
        return '0'
    return indian_number(val, decimals=0)
