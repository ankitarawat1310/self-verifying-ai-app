"""Reference implementation: invoices with server-computed totals."""
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

def _not_blank(value):
    if isinstance(value, str) and (not value.strip()):
        raise ValueError('must not be blank')
    return value
app = FastAPI(title='Invoices (reference)')
INVOICES: dict[str, dict] = {}

class LineIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    description: str = Field(min_length=1)
    quantity: StrictInt = Field(ge=1)
    unit_price: float = Field(ge=0)
    _check = field_validator('description')(_not_blank)

class InvoiceIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    customer: str = Field(min_length=1)
    line_items: list[LineIn] = Field(min_length=1)
    _check = field_validator('customer')(_not_blank)

class PaymentIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    amount: float = Field(gt=0)

def _total(lines: list[dict]) -> float:
    total = sum((Decimal(str(l['quantity'])) * Decimal(str(l['unit_price'])) for l in lines))
    return float(Decimal(total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def _get(invoice_id: str) -> dict:
    if invoice_id not in INVOICES:
        raise HTTPException(404, 'invoice not found')
    return INVOICES[invoice_id]

@app.post('/invoices', status_code=201)
def create_invoice(payload: InvoiceIn) -> dict:
    lines = [l.model_dump() for l in payload.line_items]
    invoice = {'id': uuid4().hex, 'customer': payload.customer, 'line_items': lines, 'total': _total(lines), 'status': 'draft'}
    INVOICES[invoice['id']] = invoice
    return invoice

@app.get('/invoices/{invoice_id}')
def read_invoice(invoice_id: str) -> dict:
    return _get(invoice_id)

@app.post('/invoices/{invoice_id}/line-items')
def add_line(invoice_id: str, payload: LineIn) -> dict:
    invoice = _get(invoice_id)
    if invoice['status'] != 'draft':
        raise HTTPException(409, 'only draft invoices can change')
    invoice['line_items'].append(payload.model_dump())
    invoice['total'] = _total(invoice['line_items'])
    return invoice

@app.post('/invoices/{invoice_id}/issue')
def issue(invoice_id: str) -> dict:
    invoice = _get(invoice_id)
    if invoice['status'] != 'draft' or not invoice['line_items']:
        raise HTTPException(409, 'only a draft with line items can be issued')
    invoice['status'] = 'issued'
    return invoice

@app.post('/invoices/{invoice_id}/pay')
def pay(invoice_id: str, payload: PaymentIn) -> dict:
    invoice = _get(invoice_id)
    if invoice['status'] != 'issued':
        raise HTTPException(400, 'only issued invoices can be paid')
    if Decimal(str(payload.amount)).quantize(Decimal('0.01')) != Decimal(str(invoice['total'])).quantize(Decimal('0.01')):
        raise HTTPException(422, 'amount must equal the invoice total')
    invoice['status'] = 'paid'
    return invoice
