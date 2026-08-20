from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import urllib.parse
from django.db.models import Q
from .models import AuditLog, StockMovement, Product, HSNSACMaster

def parse_money(value):
    """
    Central money parser that safely converts any monetary representation into a Decimal.
    Handles: None, Decimal, int, float, string ('₹64,900.00', '64,900.00', '64900.00', '₹ 64,900.50', etc.)
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

    clean_val = s_val.replace('₹', '').replace(',', '').replace(' ', '').strip()
    if not clean_val:
        return Decimal('0.00')

    try:
        return Decimal(clean_val)
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


def recalculate_invoice_totals(invoice):
    """
    Recalculates all mathematical fields of an Invoice from its items.
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
        if item.product.tax_inclusive:
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
        item.cess_amount = quantize_amount(item.taxable_value * (item.product.hsn_sac.cess_rate / Decimal('100.00')) if item.product.hsn_sac else Decimal('0.00'))
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
        item.cess_amount = quantize_amount(item.taxable_value * (item.product.hsn_sac.cess_rate / Decimal('100.00')) if item.product.hsn_sac else Decimal('0.00'))
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
    from .models import GSTTransaction, CustomerLedger
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
