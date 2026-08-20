from decimal import Decimal
from datetime import datetime, date
from django.db import transaction
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from .models import Quotation, QuotationItem, Customer, Product, AuditLog
from .utils import parse_money, quantize_amount, calculate_item_gst, log_action

class QuotationService:
    @classmethod
    def validate_quotation_payload(cls, company, data, exclude_quotation_id=None):
        errors = {}
        cleaned_data = {}

        # 1. Customer Validation
        customer_id = data.get('customer_id') or data.get('customer')
        if not customer_id:
            errors['customer'] = 'Customer is required.'
        else:
            try:
                customer_id_int = int(str(customer_id).strip())
                customer = Customer.objects.get(id=customer_id_int, company=company, is_active=True)
                cleaned_data['customer'] = customer
            except (Customer.DoesNotExist, ValueError, TypeError):
                errors['customer'] = 'Selected customer does not exist or is inactive.'

        # 2. Quotation Number Validation
        q_no = str(data.get('quotation_number') or '').strip()
        if not q_no:
            errors['quotation_number'] = 'Quotation number is required.'
        else:
            qs = Quotation.objects.filter(company=company, quotation_number=q_no)
            if exclude_quotation_id:
                qs = qs.exclude(id=exclude_quotation_id)
            if qs.exists():
                errors['quotation_number'] = f'Quotation number "{q_no}" already exists.'
            else:
                cleaned_data['quotation_number'] = q_no

        # 3. Quotation Date Validation
        q_date_raw = data.get('date') or data.get('quotation_date')
        if not q_date_raw:
            errors['date'] = 'Quotation date is required.'
        else:
            try:
                if isinstance(q_date_raw, (date, datetime)):
                    cleaned_data['date'] = q_date_raw if isinstance(q_date_raw, date) else q_date_raw.date()
                else:
                    cleaned_data['date'] = datetime.strptime(str(q_date_raw).strip(), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                errors['date'] = 'Invalid quotation date format (YYYY-MM-DD required).'

        # 4. Valid Until Date Validation
        valid_until_raw = data.get('valid_until')
        if not valid_until_raw:
            errors['valid_until'] = 'Valid until date is required.'
        else:
            try:
                if isinstance(valid_until_raw, (date, datetime)):
                    cleaned_data['valid_until'] = valid_until_raw if isinstance(valid_until_raw, date) else valid_until_raw.date()
                else:
                    cleaned_data['valid_until'] = datetime.strptime(str(valid_until_raw).strip(), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                errors['valid_until'] = 'Invalid expiry date format (YYYY-MM-DD required).'

        # 5. Notes & Terms
        cleaned_data['notes'] = (data.get('notes') or '').strip()
        cleaned_data['terms'] = (data.get('terms') or '').strip()

        # 6. Items Validation
        items_data = data.get('items')
        if isinstance(items_data, str):
            try:
                import json
                items_data = json.loads(items_data)
            except Exception:
                items_data = []
        if not items_data:
            items_raw_json = data.get('items_json')
            if items_raw_json:
                try:
                    import json
                    items_data = json.loads(items_raw_json)
                except Exception:
                    items_data = []

        if not items_data or not isinstance(items_data, list):
            errors['items'] = {'_non_field_': 'At least one valid item is required in the quotation.'}
        else:
            cleaned_items = []
            item_errors = {}

            for idx, item_raw in enumerate(items_data):
                row_errs = {}
                prod_id = item_raw.get('product_id') or item_raw.get('product')

                if not prod_id:
                    row_errs['product'] = 'Product is required.'
                    prod = None
                else:
                    try:
                        prod_id_int = int(str(prod_id).strip())
                        prod = Product.objects.get(id=prod_id_int, company=company, is_active=True)
                    except (Product.DoesNotExist, ValueError, TypeError):
                        row_errs['product'] = 'Selected product does not exist.'
                        prod = None

                try:
                    qty = parse_money(item_raw.get('quantity', 0))
                    if qty <= 0:
                        row_errs['quantity'] = 'Quantity must be greater than 0.'
                except (ValueError, TypeError):
                    row_errs['quantity'] = 'Invalid quantity.'
                    qty = Decimal('0.00')

                try:
                    rate = parse_money(item_raw.get('rate', 0))
                    if rate < 0:
                        row_errs['rate'] = 'Rate cannot be negative.'
                except (ValueError, TypeError):
                    row_errs['rate'] = 'Invalid rate.'
                    rate = Decimal('0.00')

                try:
                    disc = parse_money(item_raw.get('discount', 0))
                    if disc < 0:
                        row_errs['discount'] = 'Discount cannot be negative.'
                except (ValueError, TypeError):
                    row_errs['discount'] = 'Invalid discount.'
                    disc = Decimal('0.00')

                gross = qty * rate
                if disc > gross:
                    row_errs['discount'] = 'Discount cannot exceed line item total.'

                if row_errs:
                    item_errors[str(idx)] = row_errs
                elif prod:
                    cleaned_items.append({
                        'product': prod,
                        'quantity': qty,
                        'rate': rate,
                        'discount': disc
                    })

            if item_errors:
                errors['items'] = item_errors
            elif not cleaned_items:
                errors['items'] = {'_non_field_': 'Please add at least one valid product.'}
            else:
                cleaned_data['items'] = cleaned_items

        return cleaned_data, errors

    @classmethod
    @transaction.atomic
    def create_quotation(cls, company, user, data):
        cleaned_data, errors = cls.validate_quotation_payload(company, data)
        if errors:
            first_msg = 'Please correct the validation errors.'
            if isinstance(errors.get('customer'), str):
                first_msg = errors['customer']
            elif isinstance(errors.get('quotation_number'), str):
                first_msg = errors['quotation_number']
            elif isinstance(errors.get('items'), dict) and '_non_field_' in errors['items']:
                first_msg = errors['items']['_non_field_']
            return {
                'success': False,
                'status': 'error',
                'message': first_msg,
                'errors': errors
            }

        customer = cleaned_data['customer']
        q_no = cleaned_data['quotation_number']
        q_date = cleaned_data['date']
        valid_until = cleaned_data['valid_until']
        notes = cleaned_data['notes']
        terms = cleaned_data['terms']
        items = cleaned_data['items']

        quotation = Quotation.objects.create(
            company=company,
            customer=customer,
            quotation_number=q_no,
            date=q_date,
            valid_until=valid_until,
            notes=notes,
            terms=terms,
            status='DRAFT'
        )

        subtotal = Decimal('0.00')
        taxable_total = Decimal('0.00')
        cgst_total = Decimal('0.00')
        sgst_total = Decimal('0.00')
        igst_total = Decimal('0.00')
        cess_total = Decimal('0.00')

        company_state_code = str(company.state_code or '').strip().zfill(2)
        customer_state_code = str(customer.billing_state_code or company_state_code).strip().zfill(2)


        for item_data in items:
            prod = item_data['product']
            qty = item_data['quantity']
            rate = item_data['valid_rate'] if 'valid_rate' in item_data else item_data['rate']
            disc = item_data['discount']

            gross = qty * rate
            taxable_item = quantize_amount(gross - disc)
            gst_rate = prod.hsn_sac.gst_rate if prod.hsn_sac else Decimal('0.00')
            cess_rate = prod.hsn_sac.cess_rate if prod.hsn_sac else Decimal('0.00')

            cgst_item, sgst_item, igst_item, total_gst_item = calculate_item_gst(
                company_state_code,
                customer_state_code,
                taxable_item,
                gst_rate
            )
            cess_item = quantize_amount(taxable_item * (cess_rate / Decimal('100.00')))
            tot = quantize_amount(taxable_item + cgst_item + sgst_item + igst_item + cess_item)
            hsn_code = prod.hsn_sac.code if prod.hsn_sac else ''

            QuotationItem.objects.create(
                quotation=quotation,
                product=prod,
                quantity=qty,
                rate=rate,
                discount=disc,
                taxable_value=taxable_item,
                gst_rate=gst_rate,
                cgst_amount=cgst_item,
                sgst_amount=sgst_item,
                igst_amount=igst_item,
                hsn_sac_code=hsn_code,
                total_amount=tot
            )

            subtotal += gross
            taxable_total += taxable_item
            cgst_total += cgst_item
            sgst_total += sgst_item
            igst_total += igst_item
            cess_total += cess_item

        quotation.subtotal = quantize_amount(subtotal)
        quotation.taxable_value = quantize_amount(taxable_total)
        quotation.cgst_total = quantize_amount(cgst_total)
        quotation.sgst_total = quantize_amount(sgst_total)
        quotation.igst_total = quantize_amount(igst_total)
        quotation.grand_total = quantize_amount(taxable_total + cgst_total + sgst_total + igst_total + cess_total)
        quotation.status = 'SENT'
        quotation.save()

        if user:
            log_action(user, 'CREATE_QUOTATION', 'QUOTATION', quotation.id)


        return {
            'success': True,
            'status': 'success',
            'message': f"Sales quotation {quotation.quotation_number} saved successfully!",
            'quotation_id': quotation.id,
            'quotation_number': quotation.quotation_number,
            'redirect_url': '/company/quotations/'
        }


    @classmethod
    @transaction.atomic
    def update_quotation(cls, company, user, quotation, data):
        if quotation.status == 'CONVERTED':
            return {
                'success': False,
                'status': 'error',
                'message': 'Converted quotations cannot be modified.',
                'errors': {'status': 'Converted quotations cannot be modified.'}
            }

        cleaned_data, errors = cls.validate_quotation_payload(company, data, exclude_quotation_id=quotation.id)
        if errors:
            first_msg = 'Please correct the validation errors.'
            if isinstance(errors.get('customer'), str):
                first_msg = errors['customer']
            elif isinstance(errors.get('quotation_number'), str):
                first_msg = errors['quotation_number']
            return {
                'success': False,
                'status': 'error',
                'message': first_msg,
                'errors': errors
            }

        customer = cleaned_data['customer']
        quotation.customer = customer
        quotation.quotation_number = cleaned_data['quotation_number']
        quotation.date = cleaned_data['date']
        quotation.valid_until = cleaned_data['valid_until']
        quotation.notes = cleaned_data['notes']
        quotation.terms = cleaned_data['terms']


        quotation.items.all().delete()

        subtotal = Decimal('0.00')
        taxable_total = Decimal('0.00')
        cgst_total = Decimal('0.00')
        sgst_total = Decimal('0.00')
        igst_total = Decimal('0.00')
        cess_total = Decimal('0.00')

        company_state_code = str(company.state_code or '').strip().zfill(2)
        customer_state_code = str(customer.billing_state_code or company_state_code).strip().zfill(2)


        for item_data in cleaned_data['items']:
            prod = item_data['product']
            qty = item_data['quantity']
            rate = item_data['rate']
            disc = item_data['discount']

            gross = qty * rate
            taxable_item = quantize_amount(gross - disc)
            gst_rate = prod.hsn_sac.gst_rate if prod.hsn_sac else Decimal('0.00')
            cess_rate = prod.hsn_sac.cess_rate if prod.hsn_sac else Decimal('0.00')

            cgst_item, sgst_item, igst_item, total_gst_item = calculate_item_gst(
                company_state_code,
                customer_state_code,
                taxable_item,
                gst_rate
            )
            cess_item = quantize_amount(taxable_item * (cess_rate / Decimal('100.00')))
            tot = quantize_amount(taxable_item + cgst_item + sgst_item + igst_item + cess_item)
            hsn_code = prod.hsn_sac.code if prod.hsn_sac else ''

            QuotationItem.objects.create(
                quotation=quotation,
                product=prod,
                quantity=qty,
                rate=rate,
                discount=disc,
                taxable_value=taxable_item,
                gst_rate=gst_rate,
                cgst_amount=cgst_item,
                sgst_amount=sgst_item,
                igst_amount=igst_item,
                hsn_sac_code=hsn_code,
                total_amount=tot
            )

            subtotal += gross

            taxable_total += taxable_item
            cgst_total += cgst_item
            sgst_total += sgst_item
            igst_total += igst_item
            cess_total += cess_item


        quotation.subtotal = quantize_amount(subtotal)
        quotation.taxable_value = quantize_amount(taxable_total)
        quotation.cgst_total = quantize_amount(cgst_total)
        quotation.sgst_total = quantize_amount(sgst_total)
        quotation.igst_total = quantize_amount(igst_total)
        quotation.grand_total = quantize_amount(taxable_total + cgst_total + sgst_total + igst_total + cess_total)
        quotation.save()

        if user:
            log_action(user, 'UPDATE_QUOTATION', 'QUOTATION', quotation.id)

        return {
            'success': True,
            'status': 'success',
            'message': f"Sales quotation {quotation.quotation_number} updated successfully!",
            'quotation_id': quotation.id,
            'quotation_number': quotation.quotation_number,
            'redirect_url': '/company/quotations/'
        }
