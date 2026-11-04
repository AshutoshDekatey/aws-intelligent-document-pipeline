"""Strict validation for the v0.1 two-decimal-currency invoice contract."""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


class InvalidInvoice(ValueError):
    pass


def validate(data):
    def fail(field):
        raise InvalidInvoice(f"Invalid field: {field}")

    def text(value, field):
        if not isinstance(value, str) or not value.strip() or len(value) > 500:
            fail(field)
        return value.strip()

    def number(value, field, money=True):
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            fail(field)
        try:
            result = Decimal(str(value))
            if not result.is_finite() or result < 0 or result > Decimal('1000000000'):
                fail(field)
            if money and result != result.quantize(Decimal('.01')):
                fail(field)
            return result
        except (InvalidOperation, ValueError):
            fail(field)

    fields = {'vendor', 'invoice_number', 'invoice_date', 'currency', 'line_items', 'subtotal', 'tax', 'total'}
    if not isinstance(data, dict) or set(data) != fields:
        fail('schema')
    out = {key: text(data[key], key) for key in ('vendor', 'invoice_number', 'invoice_date', 'currency')}
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', out['invoice_date']):
        fail('invoice_date')
    try:
        date.fromisoformat(out['invoice_date'])
    except ValueError:
        fail('invoice_date')
    if out['currency'] not in {'USD', 'EUR', 'GBP', 'INR', 'CAD', 'AUD'}:
        fail('currency')
    items = data['line_items']
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        fail('line_items')
    out['line_items'] = []
    subtotal = Decimal(0)
    for item in items:
        if not isinstance(item, dict) or set(item) != {'description', 'quantity', 'unit_price', 'amount'}:
            fail('line_item.schema')
        description = text(item['description'], 'description')
        quantity = number(item['quantity'], 'quantity', False)
        price = number(item['unit_price'], 'unit_price')
        amount = number(item['amount'], 'amount')
        if quantity <= 0 or (quantity * price).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) != amount:
            fail('line_item.arithmetic')
        subtotal += amount
        out['line_items'].append(dict(description=description, quantity=str(quantity), unit_price=f'{price:.2f}', amount=f'{amount:.2f}'))
    amounts = {key: number(data[key], key) for key in ('subtotal', 'tax', 'total')}
    if subtotal != amounts['subtotal'] or subtotal + amounts['tax'] != amounts['total']:
        fail('totals.arithmetic')
    out.update({key: f'{value:.2f}' for key, value in amounts.items()})
    return out
