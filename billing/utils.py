from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import urllib.parse
from django.db.models import Q
from .models import AuditLog, StockMovement, Product, HSNSACMaster

def parse_money(value):
    """
    Central money parser that safely converts any monetary representation into a Decimal.
    Handles: None, Decimal, int, float, string ('5,000', '₹5,00,000.00', ' ₹ 5,00,000.00 ', '-₹500.00', 'Rs. 5,000', 'INR 50000', etc.)
    """
    if value is None:
        return Decimal('0.00')

    if isinstance(value, Decimal):
        return value

    if isinstance(value, int):
        return Decimal(value)

    if isinstance(value, float):
        return Decimal(str(value))

    s_val = str(value).strip()
    if not s_val:
        return Decimal('0.00')

    # Handle parenthesis format for negative numbers like (500.00) or (₹500.00)
    is_neg = False
    if s_val.startswith('(') and s_val.endswith(')'):
        is_neg = True
        s_val = s_val[1:-1].strip()
    elif s_val.startswith('-'):
        is_neg = True
        s_val = s_val[1:].strip()

    import re
    # Strip currency symbols (₹, $, €, £), currency abbreviations (INR, Rs., Rs, Rupees), commas, NBSP, and whitespace
    clean_val = re.sub(r'(?i)\b(inr|rupees?)\b', '', s_val)
    clean_val = re.sub(r'(?i)rs\.?', '', clean_val)
    clean_val = re.sub(r'[₹$€£\u20B9\u00A0]', '', clean_val)
    clean_val = clean_val.replace('%', '').replace(',', '').replace(' ', '').strip()

    # If minus sign was after currency symbol like ₹-500
    if clean_val.startswith('-'):
        is_neg = not is_neg
        clean_val = clean_val[1:].strip()

    if not clean_val:
        return Decimal('0.00')

    try:
        dec = Decimal(clean_val)
        return -dec if is_neg else dec
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid monetary value: '{value}'")


def format_money(value, decimals=2):
    """
    Formats a Decimal or numeric value into standard Indian Currency string format.
    Example: Decimal('64900.00') -> '₹64,900.00'
    """
    try:
        d = parse_money(value)
    except ValueError:
        return '₹0.00'
    
    is_neg = d < 0
    d = abs(d)
    
    fmt_str = f"%.{decimals}f" % d if decimals is not None else str(d)
    parts = fmt_str.split('.')
    int_part = parts[0]
    dec_part = '.' + parts[1] if len(parts) > 1 else ''

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

    res = '₹' + formatted_int + dec_part
    return '-' + res if is_neg else res


def serialize_decimal(value):
    """
    Safely serializes a monetary Decimal or numeric value to string format for APIs/JSON.
    Example: Decimal('64900.00') -> '64900.00'
    """
    try:
        d = parse_money(value)
        return str(d)
    except ValueError:
        return '0.00'


def quantize_amount(val):
    """
    Rounds a decimal amount to 2 decimal places safely.
    """
    if val is None:
        return Decimal('0.00')
    try:
        return parse_money(val).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except ValueError:
        return Decimal('0.00')


def calculate_gst(hsn_sac_code, taxable_value, supplier_state_code, place_of_supply_code, company=None):
    """
    Computes GST details dynamically according to the HSN/SAC master.
    """
    hsn_obj = HSNSACMaster.objects.filter(
        Q(code=hsn_sac_code) & (Q(company=company) | Q(company__isnull=True))
    ).first()
    
    if not hsn_obj:
        raise ValueError(f"GST rate is not configured for HSN/SAC code '{hsn_sac_code}'.")
        
    gst_rate = hsn_obj.gst_rate
    cess_rate = hsn_obj.cess_rate
    
    # Standardize codes
    supp_code = str(supplier_state_code or '').strip().zfill(2)
    pos_code = str(place_of_supply_code or '').strip().zfill(2)
    
    taxable_val = Decimal(str(taxable_value))
    
    # Calculate base tax amounts
    total_gst = (taxable_val * (gst_rate / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    cess_amount = (taxable_val * (cess_rate / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    if supp_code == pos_code:
        # Intra-state
        tax_type = "CGST_SGST"
        cgst_rate = hsn_obj.get_cgst_rate()
        sgst_rate = hsn_obj.get_sgst_rate()
        igst_rate = Decimal('0.00')
        
        cgst_amount = (total_gst / Decimal('2.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        sgst_amount = (total_gst / Decimal('2.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        igst_amount = Decimal('0.00')
    else:
        # Inter-state
        tax_type = "IGST"
        cgst_rate = Decimal('0.00')
        sgst_rate = Decimal('0.00')
        igst_rate = hsn_obj.get_igst_rate()
        
        cgst_amount = Decimal('0.00')
        sgst_amount = Decimal('0.00')
        igst_amount = total_gst
        
    total_tax = cgst_amount + sgst_amount + igst_amount + cess_amount
    grand_total = taxable_val + total_tax
    
    return {
        'hsn_sac': hsn_sac_code,
        'gst_rate': gst_rate,
        'cess_rate': cess_rate,
        'taxable_value': taxable_val,
        'tax_type': tax_type,
        'cgst_rate': cgst_rate,
        'sgst_rate': sgst_rate,
        'igst_rate': igst_rate,
        'cgst_amount': cgst_amount,
        'sgst_amount': sgst_amount,
        'igst_amount': igst_amount,
        'cess_amount': cess_amount,
        'total_tax': total_tax,
        'grand_total': grand_total
    }


def calculate_item_gst(company_state_code, pos_state_code, taxable_value, gst_rate):
    """
    Computes GST amounts based on state codes.
    If intra-state: splits CGST and SGST/UTGST.
    If inter-state: applies IGST.
    """
    taxable_value = Decimal(taxable_value)
    gst_rate = Decimal(gst_rate)
    
    total_gst = quantize_amount(taxable_value * (gst_rate / Decimal('100.00')))
    
    # Standardize codes
    comp_code = str(company_state_code).strip().zfill(2)
    pos_code = str(pos_state_code).strip().zfill(2)
    
    if comp_code == pos_code:
        # Intra-state
        cgst = quantize_amount(total_gst / Decimal('2.00'))
        sgst = quantize_amount(total_gst / Decimal('2.00'))
        igst = Decimal('0.00')
    else:
        # Inter-state
        cgst = Decimal('0.00')
        sgst = Decimal('0.00')
        igst = total_gst
        
    return cgst, sgst, igst, total_gst


def recalculate_invoice_totals(invoice, advance_amount=None, amount_paid_now=None, payment_percentage=None, advance_paid=None, payment_status=None):
    """
    Recalculates invoice totals, GST breakdowns, round off, and payment settlement fields.
    Updates invoice in-memory. Caller is responsible for calling invoice.save().
    """
    items = invoice.items.all()
    subtotal = Decimal('0.00')
    discount_total = Decimal('0.00')
    taxable_value = Decimal('0.00')
    cgst_total = Decimal('0.00')
    sgst_total = Decimal('0.00')
    igst_total = Decimal('0.00')
    cess_total = Decimal('0.00')
    
    for item in items:
        # Item total calculations
        qty = Decimal(item.quantity)
        rate = Decimal(item.rate)
        disc_amt = Decimal(item.discount)
        
        # Calculate gross & taxable
        gross = qty * rate
        taxable = gross - disc_amt
        
        # If product is tax_inclusive, strip tax from rate on backend
        if item.product and item.product.tax_inclusive:
            taxable = gross / (Decimal('1.00') + (Decimal(item.gst_rate) / Decimal('100.00')))
            taxable = taxable - disc_amt
            
        item.taxable_value = quantize_amount(taxable)
        
        # Calculate GST distribution
        cgst, sgst, igst, total_gst = calculate_item_gst(
            invoice.company.state_code,
            invoice.place_of_supply_code,
            item.taxable_value,
            item.gst_rate
        )
        
        item.cgst_amount = cgst
        item.sgst_amount = sgst
        item.igst_amount = igst
        item.cess_amount = quantize_amount(item.taxable_value * (item.product.hsn_sac.cess_rate / Decimal('100.00')) if (item.product and item.product.hsn_sac and hasattr(item.product.hsn_sac, 'cess_rate')) else Decimal('0.00'))
        item.total_amount = quantize_amount(item.taxable_value + cgst + sgst + igst + item.cess_amount)
        item.save()
        
        subtotal += gross
        discount_total += disc_amt
        taxable_value += item.taxable_value
        cgst_total += item.cgst_amount
        sgst_total += item.sgst_amount
        igst_total += item.igst_amount
        cess_total += item.cess_amount
        
    invoice.subtotal = quantize_amount(subtotal)
    invoice.discount_total = quantize_amount(discount_total)
    invoice.taxable_value = quantize_amount(taxable_value)
    invoice.cgst_total = quantize_amount(cgst_total)
    invoice.sgst_total = quantize_amount(sgst_total)
    invoice.igst_total = quantize_amount(igst_total)
    invoice.cess_total = quantize_amount(cess_total)
    
    # Calculate gross before round off
    gross_total = invoice.taxable_value + invoice.cgst_total + invoice.sgst_total + invoice.igst_total + invoice.cess_total
    
    # Apply standard rounding
    rounded_total = quantize_amount(gross_total.quantize(Decimal('1.'), rounding=ROUND_HALF_UP))
    invoice.round_off = quantize_amount(rounded_total - gross_total)
    invoice.grand_total = rounded_total

    # --- Payment Details Calculation ---
    if advance_paid in (False, 'false', 'False', 'no', 'No', '0'):
        adv_val = Decimal('0.00')
    elif advance_amount is not None and str(advance_amount).strip() != '':
        adv_val = parse_money(advance_amount)
    else:
        adv_val = invoice.advance_amount or Decimal('0.00')

    if adv_val < Decimal('0.00'):
        raise ValueError("Advance payment amount cannot be negative.")

    pct_val = Decimal('0.00')
    paid_now_val = Decimal('0.00')

    has_paid_now_param = amount_paid_now is not None and str(amount_paid_now).strip() != ''
    has_pct_param = payment_percentage is not None and str(payment_percentage).strip() != ''

    if has_paid_now_param:
        paid_now_val = parse_money(amount_paid_now)
        if paid_now_val < Decimal('0.00'):
            raise ValueError("Amount paid now cannot be negative.")
        if invoice.grand_total > Decimal('0.00'):
            pct_val = quantize_amount((paid_now_val / invoice.grand_total) * Decimal('100.00'))
    elif has_pct_param:
        pct_val = parse_money(payment_percentage)
        if pct_val < Decimal('0.00') or pct_val > Decimal('100.00'):
            raise ValueError("Payment percentage must be between 0% and 100%.")
        if invoice.grand_total > Decimal('0.00'):
            paid_now_val = quantize_amount(invoice.grand_total * (pct_val / Decimal('100.00')))
    else:
        paid_now_val = invoice.amount_paid_now or Decimal('0.00')
        pct_val = invoice.payment_percentage or Decimal('0.00')
        if invoice.grand_total > Decimal('0.00') and paid_now_val > Decimal('0.00') and pct_val == Decimal('0.00'):
            pct_val = quantize_amount((paid_now_val / invoice.grand_total) * Decimal('100.00'))

    # Dropdown override handling
    if payment_status == 'PAID':
        paid_now_val = max(Decimal('0.00'), invoice.grand_total - adv_val)
    elif payment_status == 'UNPAID':
        adv_val = Decimal('0.00')
        paid_now_val = Decimal('0.00')

    total_rec = quantize_amount(adv_val + paid_now_val)
    if total_rec > invoice.grand_total:
        raise ValueError("Payment amount cannot exceed the invoice total.")

    bal_due = quantize_amount(max(Decimal('0.00'), invoice.grand_total - total_rec))

    if total_rec == Decimal('0.00'):
        pmt_status = 'UNPAID'
    elif total_rec >= invoice.grand_total:
        pmt_status = 'PAID'
    else:
        pmt_status = 'PARTIALLY_PAID'

    if payment_status in ('UNPAID', 'PARTIALLY_PAID', 'PAID') and not has_paid_now_param and not has_pct_param:
        pmt_status = payment_status

    invoice.advance_amount = adv_val
    invoice.amount_paid_now = paid_now_val
    invoice.payment_percentage = pct_val
    invoice.total_payment_received = total_rec
    invoice.balance_due = bal_due
    invoice.paid_amount = total_rec
    invoice.payment_status = pmt_status

    if invoice.status not in ('CANCELLED', 'DRAFT'):
        if pmt_status == 'PAID':
            invoice.status = 'PAID'
        elif pmt_status == 'PARTIALLY_PAID':
            invoice.status = 'PARTIALLY_PAID'
        else:
            invoice.status = 'POSTED'

    invoice.save()


def recalculate_purchase_totals(bill):
    """
    Recalculates all mathematical fields of a PurchaseBill from its items.
    """
    items = bill.items.all()
    subtotal = Decimal('0.00')
    discount_total = Decimal('0.00')
    taxable_value = Decimal('0.00')
    cgst_total = Decimal('0.00')
    sgst_total = Decimal('0.00')
    igst_total = Decimal('0.00')
    cess_total = Decimal('0.00')
    
    for item in items:
        qty = Decimal(item.quantity)
        rate = Decimal(item.rate)
        disc_amt = Decimal(item.discount)
        
        gross = qty * rate
        taxable = gross - disc_amt
        
        item.taxable_value = quantize_amount(taxable)
        
        # Supplier purchase tax logic matching Supplier state vs Company state
        cgst, sgst, igst, total_gst = calculate_item_gst(
            bill.company.state_code,
            bill.supplier.state_code,
            item.taxable_value,
            item.gst_rate
        )
        
        item.cgst_amount = cgst
        item.sgst_amount = sgst
        item.igst_amount = igst
        item.cess_amount = quantize_amount(item.taxable_value * (item.product.hsn_sac.cess_rate / Decimal('100.00')) if item.product and item.product.hsn_sac else Decimal('0.00'))
        item.total_amount = quantize_amount(item.taxable_value + cgst + sgst + igst + item.cess_amount)
        item.save()
        
        subtotal += gross
        discount_total += disc_amt
        taxable_value += item.taxable_value
        cgst_total += item.cgst_amount
        sgst_total += item.sgst_amount
        igst_total += item.igst_amount
        cess_total += item.cess_amount
        
    bill.subtotal = quantize_amount(subtotal)
    bill.discount_total = quantize_amount(discount_total)
    bill.taxable_value = quantize_amount(taxable_value)
    bill.cgst_total = quantize_amount(cgst_total)
    bill.sgst_total = quantize_amount(sgst_total)
    bill.igst_total = quantize_amount(igst_total)
    bill.cess_total = quantize_amount(cess_total)
    
    gross_total = bill.taxable_value + bill.cgst_total + bill.sgst_total + bill.igst_total + bill.cess_total
    rounded_total = quantize_amount(gross_total.quantize(Decimal('1.'), rounding=ROUND_HALF_UP))
    bill.round_off = quantize_amount(rounded_total - gross_total)
    bill.grand_total = rounded_total
    bill.save()


def update_product_stock(product_id):
    """
    Tallies all StockMovement records for a product and updates the product's current_stock cache.
    """
    product = Product.objects.get(id=product_id)
    if not product.track_inventory:
        return
        
    total_stock = Decimal('0.00')
    movements = StockMovement.objects.filter(product=product)
    for move in movements:
        total_stock += Decimal(move.quantity)
        
    product.current_stock = total_stock
    product.save()


def generate_upi_qr_string(upi_id, business_name, amount, invoice_no):
    """
    Generates standard Indian UPI deep-link URL.
    """
    if not upi_id:
        return None
    params = {
        'pa': upi_id,
        'pn': business_name,
        'am': str(amount),
        'cu': 'INR',
        'tn': f"Invoice {invoice_no}"
    }
    encoded = urllib.parse.urlencode(params)
    return f"upi://pay?{encoded}"


import datetime
from uuid import UUID
from django.db import models

def sanitize_for_json(obj):
    """
    Recursively converts Decimal, Date/Datetime, Model instances, UUIDs, etc.
    into JSON-serializable Python data structures while retaining monetary precision.
    """
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, models.Model):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(item) for item in obj]
    if isinstance(obj, (int, float, bool, str)):
        return obj
    return str(obj)


def log_action(user, action, module, record_id=None, old_values=None, new_values=None, company=None, request=None):
    """
    Creates an audit log entry for a transaction or auth event.
    """
    ip = None
    ua = None
    if request:
        # Get IP Address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        # Get User Agent
        ua = request.META.get('HTTP_USER_AGENT')
        
    AuditLog.objects.create(
        company=company or (user.company if user and hasattr(user, 'company') else None),
        user=user if user and user.is_authenticated else None,
        action=action,
        module=module,
        record_id=str(record_id) if record_id else None,
        old_values=sanitize_for_json(old_values) if old_values is not None else None,
        new_values=sanitize_for_json(new_values) if new_values is not None else None,
        ip_address=ip,
        user_agent=ua
    )


def record_invoice_accounting(invoice):
    from .models import GSTTransaction, CustomerLedger, Payment
    company = invoice.company
    
    # Delete existing transactions for this invoice if any to prevent duplicate accumulation
    GSTTransaction.objects.filter(company=company, transaction_type='SALES', reference_id=invoice.id).delete()
    
    for item in invoice.items.all():
        hsn_code = getattr(item, 'hsn_sac_code', None) or (item.product.hsn_sac.code if item.product and item.product.hsn_sac else '')
        unit_code = item.product.unit.code if item.product and item.product.unit else 'NOS'
        GSTTransaction.objects.create(
            company=company,
            transaction_type='SALES',
            reference_id=invoice.id,
            reference_no=invoice.invoice_number,
            date=invoice.invoice_date,
            gstin=invoice.customer.gstin,
            party_name=invoice.customer.name,
            place_of_supply=invoice.place_of_supply,
            product_name=item.product.name,
            hsn_sac_code=hsn_code,
            uqc_unit=unit_code,
            quantity=item.quantity,
            taxable_value=item.taxable_value,
            gst_rate=item.gst_rate,
            cgst_amount=item.cgst_amount,
            sgst_amount=item.sgst_amount,
            igst_amount=item.igst_amount,
            cess_amount=item.cess_amount,
            is_cancelled=(invoice.status == 'CANCELLED')
        )
        
    CustomerLedger.objects.update_or_create(
        company=company,
        customer=invoice.customer,
        entry_type='INVOICE',
        reference_id=invoice.id,
        defaults={
            'reference_no': invoice.invoice_number,
            'date': invoice.invoice_date,
            'description': f"Sales Invoice {invoice.invoice_number}",
            'debit': invoice.grand_total,
            'credit': Decimal('0.00'),
            'running_balance': invoice.customer.outstanding_balance
        }
    )

    if invoice.total_payment_received > Decimal('0.00'):
        pmt_obj, _ = Payment.objects.update_or_create(
            company=company,
            invoice=invoice,
            payment_type='RECEIPT',
            defaults={
                'customer': invoice.customer,
                'amount': invoice.total_payment_received,
                'payment_date': invoice.invoice_date,
                'payment_method': invoice.payment_method or 'CASH',
                'reference_no': f"PAY-{invoice.invoice_number}",
                'notes': f"Payment for Invoice {invoice.invoice_number}"
            }
        )
        CustomerLedger.objects.update_or_create(
            company=company,
            customer=invoice.customer,
            entry_type='PAYMENT',
            reference_id=pmt_obj.id,
            defaults={
                'reference_no': pmt_obj.reference_no or f"PAY-{invoice.invoice_number}",
                'date': invoice.invoice_date,
                'description': f"Payment received for Invoice {invoice.invoice_number}",
                'debit': Decimal('0.00'),
                'credit': invoice.total_payment_received,
                'running_balance': invoice.customer.outstanding_balance
            }
        )
    else:
        old_pmts = Payment.objects.filter(company=company, invoice=invoice, payment_type='RECEIPT')
        for old_pmt in old_pmts:
            CustomerLedger.objects.filter(company=company, entry_type='PAYMENT', reference_id=old_pmt.id).delete()
        old_pmts.delete()


def cancel_invoice_accounting(invoice):
    from .models import GSTTransaction, CustomerLedger
    from datetime import date
    company = invoice.company
    GSTTransaction.objects.filter(company=company, reference_id=invoice.id, transaction_type='SALES').update(is_cancelled=True)
    
    CustomerLedger.objects.create(
        company=company,
        customer=invoice.customer,
        entry_type='CREDIT_NOTE',
        reference_id=invoice.id,
        reference_no=f"CNL-{invoice.invoice_number}",
        date=date.today(),
        description=f"Cancellation of Invoice {invoice.invoice_number}",
        debit=Decimal('0.00'),
        credit=invoice.grand_total,
        running_balance=invoice.customer.outstanding_balance
    )


def record_purchase_accounting(bill):
    from .models import GSTTransaction, SupplierLedger
    company = bill.company
    
    GSTTransaction.objects.filter(company=company, transaction_type='PURCHASE', reference_id=bill.id).delete()
    
    for item in bill.items.all():
        hsn_code = getattr(item, 'hsn_sac_code', None) or (item.product.hsn_sac.code if item.product and item.product.hsn_sac else '')
        unit_code = item.product.unit.code if item.product and item.product.unit else 'NOS'
        GSTTransaction.objects.create(
            company=company,
            transaction_type='PURCHASE',
            reference_id=bill.id,
            reference_no=bill.supplier_bill_no,
            date=bill.bill_date,
            gstin=bill.supplier.gstin,
            party_name=bill.supplier.name,
            place_of_supply=company.state,
            product_name=item.product.name,
            hsn_sac_code=hsn_code,
            uqc_unit=unit_code,
            quantity=item.quantity,
            taxable_value=item.taxable_value,
            gst_rate=item.gst_rate,
            cgst_amount=item.cgst_amount,
            sgst_amount=item.sgst_amount,
            igst_amount=item.igst_amount,
            cess_amount=getattr(item, 'cess_amount', Decimal('0.00')),
            is_cancelled=(bill.status == 'CANCELLED')
        )
        
    SupplierLedger.objects.update_or_create(
        company=company,
        supplier=bill.supplier,
        entry_type='BILL',
        reference_id=bill.id,
        defaults={
            'reference_no': bill.supplier_bill_no,
            'date': bill.bill_date,
            'description': f"Purchase Bill {bill.supplier_bill_no}",
            'debit': Decimal('0.00'),
            'credit': bill.grand_total,
            'running_balance': bill.supplier.outstanding_balance
        }
    )


def cancel_purchase_accounting(bill):
    from .models import GSTTransaction, SupplierLedger
    from datetime import date
    company = bill.company
    GSTTransaction.objects.filter(company=company, reference_id=bill.id, transaction_type='PURCHASE').update(is_cancelled=True)
    
    SupplierLedger.objects.create(
        company=company,
        supplier=bill.supplier,
        entry_type='DEBIT_NOTE',
        reference_id=bill.id,
        reference_no=f"CNL-{bill.supplier_bill_no}",
        date=date.today(),
        description=f"Cancellation of Purchase Bill {bill.supplier_bill_no}",
        debit=bill.grand_total,
        credit=Decimal('0.00'),
        running_balance=bill.supplier.outstanding_balance
    )


def record_payment_accounting(payment):
    from .models import CustomerLedger, SupplierLedger
    company = payment.company
    
    if payment.payment_type == 'RECEIPT':
        CustomerLedger.objects.update_or_create(
            company=company,
            customer=payment.customer,
            entry_type='PAYMENT',
            reference_id=payment.id,
            defaults={
                'reference_no': payment.reference_no or f"PAY-{payment.id}",
                'date': payment.payment_date,
                'description': f"Receipt {payment.reference_no or ''}",
                'debit': Decimal('0.00'),
                'credit': payment.amount,
                'running_balance': payment.customer.outstanding_balance
            }
        )
    else:
        SupplierLedger.objects.update_or_create(
            company=company,
            supplier=payment.supplier,
            entry_type='PAYMENT',
            reference_id=payment.id,
            defaults={
                'reference_no': payment.reference_no or f"PAY-{payment.id}",
                'date': payment.payment_date,
                'description': f"Payment {payment.reference_no or ''}",
                'debit': payment.amount,
                'credit': Decimal('0.00'),
                'running_balance': payment.supplier.outstanding_balance
            }
        )


def record_credit_note_accounting(note):
    from .models import GSTTransaction, CustomerLedger
    company = note.company
    
    GSTTransaction.objects.filter(company=company, transaction_type='CREDIT_NOTE', reference_id=note.id).delete()
    
    GSTTransaction.objects.create(
        company=company,
        transaction_type='CREDIT_NOTE',
        reference_id=note.id,
        reference_no=note.note_number,
        date=note.note_date,
        gstin=note.invoice.customer.gstin,
        party_name=note.invoice.customer.name,
        place_of_supply=note.invoice.place_of_supply,
        product_name="Adjustment / Sales Return",
        taxable_value=-note.subtotal,
        gst_rate=Decimal('18.00'),
        cgst_amount=-note.cgst_total,
        sgst_amount=-note.sgst_total,
        igst_amount=-note.igst_total,
        cess_amount=Decimal('0.00'),
        is_cancelled=(note.status == 'CANCELLED')
    )
    
    CustomerLedger.objects.update_or_create(
        company=company,
        customer=note.invoice.customer,
        entry_type='CREDIT_NOTE',
        reference_id=note.id,
        defaults={
            'reference_no': note.note_number,
            'date': note.note_date,
            'description': f"Credit Note {note.note_number} ({note.get_reason_display()})",
            'debit': Decimal('0.00'),
            'credit': note.grand_total,
            'running_balance': note.invoice.customer.outstanding_balance
        }
    )


def record_debit_note_accounting(note):
    from .models import GSTTransaction, SupplierLedger
    company = note.company
    
    GSTTransaction.objects.filter(company=company, transaction_type='DEBIT_NOTE', reference_id=note.id).delete()
    
    GSTTransaction.objects.create(
        company=company,
        transaction_type='DEBIT_NOTE',
        reference_id=note.id,
        reference_no=note.note_number,
        date=note.note_date,
        gstin=note.purchase_bill.supplier.gstin,
        party_name=note.purchase_bill.supplier.name,
        place_of_supply=company.state,
        product_name="Adjustment / Purchase Return",
        taxable_value=-note.subtotal,
        gst_rate=Decimal('18.00'),
        cgst_amount=-note.cgst_total,
        sgst_amount=-note.sgst_total,
        igst_amount=-note.igst_total,
        cess_amount=Decimal('0.00'),
        is_cancelled=(note.status == 'CANCELLED')
    )
    
    SupplierLedger.objects.update_or_create(
        company=company,
        supplier=note.purchase_bill.supplier,
        entry_type='DEBIT_NOTE',
        reference_id=note.id,
        defaults={
            'reference_no': note.note_number,
            'date': note.note_date,
            'description': f"Debit Note {note.note_number} ({note.get_reason_display()})",
            'debit': note.grand_total,
            'credit': Decimal('0.00'),
            'running_balance': note.purchase_bill.supplier.outstanding_balance
        }
    )


def build_products_json(products):
    """
    Safely converts a queryset of Product objects into a JSON string
    without risk of string interpolation or unescaped quote syntax errors.
    """
    import json
    products_list = []
    for p in products:
        products_list.append({
            'id': p.id,
            'name': p.name,
            'price': float(p.selling_price or 0),
            'purchase_price': float(p.purchase_price or 0),
            'gst_rate': float(p.hsn_sac.gst_rate) if p.hsn_sac else 0.0,
            'cess_rate': float(p.hsn_sac.cess_rate) if p.hsn_sac else 0.0,
            'hsn_code': p.hsn_sac.code if p.hsn_sac else '',
            'tax_inclusive': bool(p.tax_inclusive)
        })
    return json.dumps(products_list)


INDIAN_STATES_AND_UTS = [
    {'code': '01', 'name': 'Jammu and Kashmir', 'display': 'Jammu and Kashmir (01)'},
    {'code': '02', 'name': 'Himachal Pradesh', 'display': 'Himachal Pradesh (02)'},
    {'code': '03', 'name': 'Punjab', 'display': 'Punjab (03)'},
    {'code': '04', 'name': 'Chandigarh', 'display': 'Chandigarh (04)'},
    {'code': '05', 'name': 'Uttarakhand', 'display': 'Uttarakhand (05)'},
    {'code': '06', 'name': 'Haryana', 'display': 'Haryana (06)'},
    {'code': '07', 'name': 'Delhi', 'display': 'Delhi (07)'},
    {'code': '08', 'name': 'Rajasthan', 'display': 'Rajasthan (08)'},
    {'code': '09', 'name': 'Uttar Pradesh', 'display': 'Uttar Pradesh (09)'},
    {'code': '10', 'name': 'Bihar', 'display': 'Bihar (10)'},
    {'code': '11', 'name': 'Sikkim', 'display': 'Sikkim (11)'},
    {'code': '12', 'name': 'Arunachal Pradesh', 'display': 'Arunachal Pradesh (12)'},
    {'code': '13', 'name': 'Nagaland', 'display': 'Nagaland (13)'},
    {'code': '14', 'name': 'Manipur', 'display': 'Manipur (14)'},
    {'code': '15', 'name': 'Mizoram', 'display': 'Mizoram (15)'},
    {'code': '16', 'name': 'Tripura', 'display': 'Tripura (16)'},
    {'code': '17', 'name': 'Meghalaya', 'display': 'Meghalaya (17)'},
    {'code': '18', 'name': 'Assam', 'display': 'Assam (18)'},
    {'code': '19', 'name': 'West Bengal', 'display': 'West Bengal (19)'},
    {'code': '20', 'name': 'Jharkhand', 'display': 'Jharkhand (20)'},
    {'code': '21', 'name': 'Odisha', 'display': 'Odisha (21)'},
    {'code': '22', 'name': 'Chhattisgarh', 'display': 'Chhattisgarh (22)'},
    {'code': '23', 'name': 'Madhya Pradesh', 'display': 'Madhya Pradesh (23)'},
    {'code': '24', 'name': 'Gujarat', 'display': 'Gujarat (24)'},
    {'code': '25', 'name': 'Daman and Diu', 'display': 'Daman and Diu (25)'},
    {'code': '26', 'name': 'Dadra and Nagar Haveli and Daman and Diu', 'display': 'Dadra and Nagar Haveli and Daman and Diu (26)'},
    {'code': '27', 'name': 'Maharashtra', 'display': 'Maharashtra (27)'},
    {'code': '28', 'name': 'Andhra Pradesh (Old)', 'display': 'Andhra Pradesh (Old) (28)'},
    {'code': '29', 'name': 'Karnataka', 'display': 'Karnataka (29)'},
    {'code': '30', 'name': 'Goa', 'display': 'Goa (30)'},
    {'code': '31', 'name': 'Lakshadweep', 'display': 'Lakshadweep (31)'},
    {'code': '32', 'name': 'Kerala', 'display': 'Kerala (32)'},
    {'code': '33', 'name': 'Tamil Nadu', 'display': 'Tamil Nadu (33)'},
    {'code': '34', 'name': 'Puducherry', 'display': 'Puducherry (34)'},
    {'code': '35', 'name': 'Andaman and Nicobar Islands', 'display': 'Andaman and Nicobar Islands (35)'},
    {'code': '36', 'name': 'Telangana', 'display': 'Telangana (36)'},
    {'code': '37', 'name': 'Andhra Pradesh', 'display': 'Andhra Pradesh (37)'},
    {'code': '38', 'name': 'Ladakh', 'display': 'Ladakh (38)'},
    {'code': '97', 'name': 'Other Territory', 'display': 'Other Territory (97)'},
    {'code': '99', 'name': 'Centre Jurisdiction', 'display': 'Centre Jurisdiction (99)'},
]

INDIAN_STATE_CODE_MAP = {item['code']: item['name'] for item in INDIAN_STATES_AND_UTS}
INDIAN_STATE_NAME_MAP = {item['name'].lower(): item['code'] for item in INDIAN_STATES_AND_UTS}

def get_state_code_for_name(state_name):
    if not state_name:
        return None
    cleaned = state_name.strip().lower()
    return INDIAN_STATE_NAME_MAP.get(cleaned)

def parse_state_and_code(val, fallback_code=None):
    """
    Parses input string like 'Odisha (21)', '21', or 'Odisha'
    and returns tuple (state_name, 2-digit state_code).
    """
    if not val:
        if fallback_code:
            code_fmt = str(fallback_code).strip().zfill(2)
            name = INDIAN_STATE_CODE_MAP.get(code_fmt, '')
            return name, code_fmt
        return '', ''

    str_val = str(val).strip()
    if '(' in str_val and ')' in str_val:
        try:
            name_part = str_val.rsplit('(', 1)[0].strip()
            code_part = str_val.rsplit('(', 1)[1].replace(')', '').strip().zfill(2)
            if code_part in INDIAN_STATE_CODE_MAP:
                return INDIAN_STATE_CODE_MAP[code_part], code_part
            return name_part, code_part
        except Exception:
            pass

    if str_val.isdigit() or len(str_val) <= 2:
        code_fmt = str_val.zfill(2)
        if code_fmt in INDIAN_STATE_CODE_MAP:
            return INDIAN_STATE_CODE_MAP[code_fmt], code_fmt

    code_match = INDIAN_STATE_NAME_MAP.get(str_val.lower())
    if code_match:
        return INDIAN_STATE_CODE_MAP[code_match], code_match

    return str_val, str(fallback_code or '').strip().zfill(2)

def format_state_display(state_name, state_code):
    s_name, s_code = parse_state_and_code(state_name, fallback_code=state_code)
    if s_name and s_code:
        return f"{s_name} ({s_code})"
    elif s_name:
        return s_name
    elif s_code:
        return f"State ({s_code})"
    return ""

def validate_state_and_code(state_name, state_code):
    """
    Validates that state_name and state_code match official GST state mapping.
    Returns (is_valid, expected_code_or_message).
    """
    if not state_code:
        return False, "State code is required."
    code_formatted = str(state_code).strip().zfill(2)
    expected_name = INDIAN_STATE_CODE_MAP.get(code_formatted)
    if not expected_name:
        return False, f"Invalid GST State Code '{code_formatted}'."
    
    if state_name:
        st_clean = state_name.strip().lower()
        exp_clean = expected_name.lower()
        if st_clean != exp_clean and st_clean not in exp_clean and exp_clean not in st_clean:
            return False, f"State Code '{code_formatted}' ({expected_name}) does not match selected State '{state_name}'."
            
    return True, code_formatted


def parse_product_specifications(description):
    """
    Parses key-value specifications from product description string.
    Returns dict with 'specs' (list of {'key', 'value'}) and 'notes' (list of non-kv strings).
    """
    if not description:
        return {'specs': [], 'notes': []}
    
    lines = [l.strip() for l in str(description).splitlines() if l.strip()]
    specs = []
    notes = []
    
    for line in lines:
        if ':' in line:
            parts = line.split(':', 1)
            key = parts[0].strip()
            val = parts[1].strip()
            if key and val and len(key) <= 35:
                specs.append({'key': key, 'value': val})
            else:
                notes.append(line)
        elif '=' in line:
            parts = line.split('=', 1)
            key = parts[0].strip()
            val = parts[1].strip()
            if key and val and len(key) <= 35:
                specs.append({'key': key, 'value': val})
            else:
                notes.append(line)
        else:
            notes.append(line)
            
    return {'specs': specs, 'notes': notes}


DEFAULT_PREDEFINED_QUOTATION_TERMS = [
    "Payment must be made according to the agreed payment terms.",
    "Quotation is valid only for the specified validity period.",
    "Prices are subject to applicable GST/taxes.",
    "Delivery will be made according to the agreed schedule.",
    "Any additional work or requirements may be charged separately.",
    "Goods/services once confirmed cannot be cancelled without mutual agreement.",
    "Any dispute will be subject to the applicable jurisdiction."
]

def get_or_create_predefined_quotation_terms(company=None):
    from django.db import models
    from .models import QuotationPredefinedTerm
    existing = QuotationPredefinedTerm.objects.filter(
        models.Q(company=company) | models.Q(company__isnull=True),
        is_active=True
    )
    if not existing.exists():
        terms_to_create = []
        for idx, text in enumerate(DEFAULT_PREDEFINED_QUOTATION_TERMS):
            terms_to_create.append(QuotationPredefinedTerm(
                company=company,
                term_text=text,
                display_order=idx + 1,
                is_active=True
            ))
        QuotationPredefinedTerm.objects.bulk_create(terms_to_create)
        existing = QuotationPredefinedTerm.objects.filter(
            models.Q(company=company) | models.Q(company__isnull=True),
            is_active=True
        )
    return existing.order_by('display_order', 'id')


def recalculate_quotation_totals(quotation):
    items = quotation.items.all()
    subtotal = Decimal('0.00')
    discount_total = Decimal('0.00')
    taxable_value = Decimal('0.00')
    cgst_total = Decimal('0.00')
    sgst_total = Decimal('0.00')
    igst_total = Decimal('0.00')
    cess_total = Decimal('0.00')

    for item in items:
        qty = Decimal(item.quantity)
        rate = Decimal(item.rate)
        disc_amt = Decimal(item.discount)
        
        gross = qty * rate
        taxable = gross - disc_amt
        
        if item.product and getattr(item.product, 'tax_inclusive', False):
            taxable = gross / (Decimal('1.00') + (Decimal(item.gst_rate) / Decimal('100.00')))
            taxable = taxable - disc_amt

        item.taxable_value = quantize_amount(taxable)
        
        cgst, sgst, igst, total_gst = calculate_item_gst(
            quotation.company.state_code,
            quotation.customer.billing_state_code or quotation.company.state_code,
            item.taxable_value,
            item.gst_rate
        )
        item.cgst_amount = cgst
        item.sgst_amount = sgst
        item.igst_amount = igst
        
        cess_rate_val = item.product.hsn_sac.cess_rate if (item.product and item.product.hsn_sac and hasattr(item.product.hsn_sac, 'cess_rate')) else Decimal('0.00')
        item.cess_amount = quantize_amount(item.taxable_value * (Decimal(cess_rate_val) / Decimal('100.00')))
        item.total_amount = quantize_amount(item.taxable_value + cgst + sgst + igst + item.cess_amount)
        item.save()

        subtotal += gross
        discount_total += disc_amt
        taxable_value += item.taxable_value
        cgst_total += item.cgst_amount
        sgst_total += item.sgst_amount
        igst_total += item.igst_amount
        cess_total += item.cess_amount

    quotation.subtotal = quantize_amount(subtotal)
    quotation.discount_total = quantize_amount(discount_total)
    quotation.taxable_value = quantize_amount(taxable_value)
    quotation.cgst_total = quantize_amount(cgst_total)
    quotation.sgst_total = quantize_amount(sgst_total)
    quotation.igst_total = quantize_amount(igst_total)
    quotation.cess_total = quantize_amount(cess_total)

    gross_total = quotation.taxable_value + quotation.cgst_total + quotation.sgst_total + quotation.igst_total + quotation.cess_total
    rounded_total = quantize_amount(gross_total.quantize(Decimal('1.'), rounding=ROUND_HALF_UP))
    quotation.round_off = quantize_amount(rounded_total - gross_total)
    quotation.grand_total = rounded_total
    quotation.save()


