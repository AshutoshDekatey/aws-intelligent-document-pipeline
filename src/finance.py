"""Financial schema for the v0.2 workflow, with the existing arithmetic rules."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from validation import validate

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Money = Annotated[str, StringConstraints(pattern=r'^\d{1,10}(\.\d{1,2})?$')]
Quantity = Annotated[str, StringConstraints(pattern=r'^\d{1,10}(\.\d{1,6})?$')]
Date = Annotated[str, StringConstraints(pattern=r'^\d{4}-\d{2}-\d{2}$')]


class LineItem(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    description: Text
    quantity: Quantity
    unit_price: Money
    amount: Money


class Invoice(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    vendor: Text
    invoice_number: Text
    invoice_date: Date
    currency: Literal['USD', 'EUR', 'GBP', 'INR', 'CAD', 'AUD']
    line_items: Annotated[list[LineItem], Field(min_length=1, max_length=30)]
    subtotal: Money
    tax: Money
    total: Money


def validate_invoice(fields):
    return validate(Invoice.model_validate(fields).model_dump())
