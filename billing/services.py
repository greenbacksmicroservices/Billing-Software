from decimal import Decimal
from datetime import datetime, date
from django.db import transaction
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from .models import (
    Quotation, QuotationItem, QuotationPredefinedTerm, QuotationSelectedTerm, Customer, Product, AuditLog,
    PurchaseOrder, PurchaseOrderItem, Supplier, Warehouse, PurchaseBill, PurchaseBillItem
)
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

                gst_rate = parse_money(item_raw.get('gst_rate', prod.hsn_sac.gst_rate if (prod and prod.hsn_sac) else Decimal('18.00')))

                if row_errs:
                    item_errors[str(idx)] = row_errs
                elif prod:
                    cleaned_items.append({
                        'product': prod,
                        'quantity': qty,
                        'rate': rate,
                        'discount': disc,
                        'gst_rate': gst_rate
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
            gst_rate = parse_money(item_data.get('gst_rate', (prod.hsn_sac.gst_rate if prod and prod.hsn_sac else Decimal('18.00'))))
            cess_rate = prod.hsn_sac.cess_rate if (prod and prod.hsn_sac) else Decimal('0.00')
            is_tax_inc = getattr(prod, 'tax_inclusive', False) if prod else False
            if is_tax_inc:
                net_inc = max(Decimal('0.00'), gross - disc)
                taxable_item = quantize_amount(net_inc / (Decimal('1.00') + (gst_rate / Decimal('100.00'))))
            else:
                taxable_item = quantize_amount(gross - disc)

            cgst_item, sgst_item, igst_item, total_gst_item = calculate_item_gst(
                company_state_code,
                customer_state_code,
                taxable_item,
                gst_rate
            )
            cess_item = quantize_amount(taxable_item * (cess_rate / Decimal('100.00')))
            tot = quantize_amount(gross - disc) if is_tax_inc else quantize_amount(taxable_item + cgst_item + sgst_item + igst_item + cess_item)
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

        # Save Selected Terms
        selected_terms_data = data.get('selected_terms', [])
        if isinstance(selected_terms_data, str):
            try:
                import json
                selected_terms_data = json.loads(selected_terms_data)
            except Exception:
                selected_terms_data = []

        if not selected_terms_data and 'terms_list' in data:
            selected_terms_data = data.get('terms_list', [])

        QuotationSelectedTerm.objects.filter(quotation=quotation).delete()
        if selected_terms_data and isinstance(selected_terms_data, list):
            terms_to_create = []
            for idx, st in enumerate(selected_terms_data):
                if isinstance(st, dict):
                    t_text = str(st.get('term_text') or st.get('text') or '').strip()
                    is_cust = bool(st.get('is_custom', False))
                else:
                    t_text = str(st or '').strip()
                    is_cust = False
                if t_text:
                    terms_to_create.append(QuotationSelectedTerm(
                        quotation=quotation,
                        term_text=t_text,
                        display_order=idx + 1,
                        is_custom=is_cust
                    ))
            if terms_to_create:
                QuotationSelectedTerm.objects.bulk_create(terms_to_create)

        from .utils import recalculate_quotation_totals
        recalculate_quotation_totals(quotation)

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
            gst_rate = parse_money(item_data.get('gst_rate', (prod.hsn_sac.gst_rate if prod and prod.hsn_sac else Decimal('18.00'))))
            cess_rate = prod.hsn_sac.cess_rate if (prod and prod.hsn_sac) else Decimal('0.00')
            is_tax_inc = getattr(prod, 'tax_inclusive', False) if prod else False
            if is_tax_inc:
                net_inc = max(Decimal('0.00'), gross - disc)
                taxable_item = quantize_amount(net_inc / (Decimal('1.00') + (gst_rate / Decimal('100.00'))))
            else:
                taxable_item = quantize_amount(gross - disc)

            cgst_item, sgst_item, igst_item, total_gst_item = calculate_item_gst(
                company_state_code,
                customer_state_code,
                taxable_item,
                gst_rate
            )
            cess_item = quantize_amount(taxable_item * (cess_rate / Decimal('100.00')))
            tot = quantize_amount(gross - disc) if is_tax_inc else quantize_amount(taxable_item + cgst_item + sgst_item + igst_item + cess_item)
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
        quotation.save()

        # Save Selected Terms
        selected_terms_data = data.get('selected_terms', [])
        if isinstance(selected_terms_data, str):
            try:
                import json
                selected_terms_data = json.loads(selected_terms_data)
            except Exception:
                selected_terms_data = []

        if not selected_terms_data and 'terms_list' in data:
            selected_terms_data = data.get('terms_list', [])

        QuotationSelectedTerm.objects.filter(quotation=quotation).delete()
        if selected_terms_data and isinstance(selected_terms_data, list):
            terms_to_create = []
            for idx, st in enumerate(selected_terms_data):
                if isinstance(st, dict):
                    t_text = str(st.get('term_text') or st.get('text') or '').strip()
                    is_cust = bool(st.get('is_custom', False))
                else:
                    t_text = str(st or '').strip()
                    is_cust = False
                if t_text:
                    terms_to_create.append(QuotationSelectedTerm(
                        quotation=quotation,
                        term_text=t_text,
                        display_order=idx + 1,
                        is_custom=is_cust
                    ))
            if terms_to_create:
                QuotationSelectedTerm.objects.bulk_create(terms_to_create)

        from .utils import recalculate_quotation_totals
        recalculate_quotation_totals(quotation)

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


class PurchaseOrderService:
    @classmethod
    def generate_po_number(cls, company):
        fin_year = getattr(company, 'financial_year', str(date.today().year))
        count = PurchaseOrder.objects.filter(company=company).count() + 1
        po_no = f"PO-{fin_year}-{str(count).zfill(5)}"
        while PurchaseOrder.objects.filter(company=company, po_number=po_no).exists():
            count += 1
            po_no = f"PO-{fin_year}-{str(count).zfill(5)}"
        return po_no

    @classmethod
    def validate_purchase_order_payload(cls, company, data, exclude_po_id=None):
        errors = {}
        cleaned_data = {}

        # 1. Supplier Validation & Snapshot
        supplier_id = data.get('supplier_id') or data.get('supplier')
        supplier_obj = None
        if supplier_id:
            try:
                supplier_id_int = int(str(supplier_id).strip())
                supplier_obj = Supplier.objects.get(id=supplier_id_int, company=company, is_active=True)
                cleaned_data['supplier'] = supplier_obj
                cleaned_data['supplier_name_snapshot'] = supplier_obj.business_name or supplier_obj.name
                cleaned_data['supplier_phone_snapshot'] = supplier_obj.mobile or ''
                cleaned_data['supplier_email_snapshot'] = supplier_obj.email or ''
                cleaned_data['supplier_gstin_snapshot'] = supplier_obj.gstin or ''
                cleaned_data['supplier_pan_snapshot'] = supplier_obj.pan or ''
                cleaned_data['supplier_address_snapshot'] = supplier_obj.address or ''
                cleaned_data['supplier_state_snapshot'] = supplier_obj.state or ''
                cleaned_data['supplier_state_code_snapshot'] = supplier_obj.state_code or ''
            except (Supplier.DoesNotExist, ValueError, TypeError):
                supplier_obj = None

        if not supplier_obj:
            manual_name = str(data.get('supplier_company_name') or data.get('manual_supplier_name') or data.get('supplier_name') or '').strip()
            if manual_name:
                cleaned_data['supplier'] = None
                cleaned_data['supplier_name_snapshot'] = manual_name
                cleaned_data['supplier_phone_snapshot'] = str(data.get('supplier_phone') or '').strip()
                cleaned_data['supplier_email_snapshot'] = str(data.get('supplier_email') or '').strip()
                cleaned_data['supplier_gstin_snapshot'] = str(data.get('supplier_gstin') or '').strip()
                cleaned_data['supplier_pan_snapshot'] = str(data.get('supplier_pan') or '').strip()
                cleaned_data['supplier_address_snapshot'] = str(data.get('supplier_address') or '').strip()
                
                raw_state = str(data.get('supplier_state') or '').strip()
                raw_code = str(data.get('supplier_state_code') or '').strip()
                if '(' in raw_state and ')' in raw_state:
                    try:
                        parts = raw_state.split('(')
                        raw_state = parts[0].strip()
                        if not raw_code:
                            raw_code = parts[1].replace(')', '').strip()
                    except Exception:
                        pass

                cleaned_data['supplier_state_snapshot'] = raw_state
                cleaned_data['supplier_state_code_snapshot'] = raw_code.zfill(2) if raw_code else ''
            else:
                errors['supplier'] = 'Supplier is required. Please select an existing supplier or enter a company name.'

        # 2. PO Number Validation
        po_no = str(data.get('po_number') or '').strip()
        if not po_no:
            errors['po_number'] = 'Purchase Order number is required.'
        else:
            qs = PurchaseOrder.objects.filter(company=company, po_number=po_no)
            if exclude_po_id:
                qs = qs.exclude(id=exclude_po_id)
            if qs.exists():
                errors['po_number'] = f'Purchase Order number "{po_no}" already exists.'
            else:
                cleaned_data['po_number'] = po_no

        # 3. Dates Validation
        po_date_raw = data.get('po_date') or data.get('date')
        if not po_date_raw:
            errors['po_date'] = 'Purchase Order date is required.'
        else:
            try:
                if isinstance(po_date_raw, (date, datetime)):
                    cleaned_data['po_date'] = po_date_raw if isinstance(po_date_raw, date) else po_date_raw.date()
                else:
                    cleaned_data['po_date'] = datetime.strptime(str(po_date_raw).strip(), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                errors['po_date'] = 'Invalid PO date format (YYYY-MM-DD required).'

        exp_del_raw = data.get('expected_delivery_date')
        if exp_del_raw:
            try:
                if isinstance(exp_del_raw, (date, datetime)):
                    cleaned_data['expected_delivery_date'] = exp_del_raw if isinstance(exp_del_raw, date) else exp_del_raw.date()
                else:
                    cleaned_data['expected_delivery_date'] = datetime.strptime(str(exp_del_raw).strip(), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                errors['expected_delivery_date'] = 'Invalid expected delivery date format.'
        else:
            cleaned_data['expected_delivery_date'] = None

        sup_ref_date_raw = data.get('supplier_reference_date')
        if sup_ref_date_raw:
            try:
                if isinstance(sup_ref_date_raw, (date, datetime)):
                    cleaned_data['supplier_reference_date'] = sup_ref_date_raw if isinstance(sup_ref_date_raw, date) else sup_ref_date_raw.date()
                else:
                    cleaned_data['supplier_reference_date'] = datetime.strptime(str(sup_ref_date_raw).strip(), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                errors['supplier_reference_date'] = 'Invalid supplier reference date format.'
        else:
            cleaned_data['supplier_reference_date'] = None

        # 4. Warehouse Validation
        wh_id = data.get('warehouse_id') or data.get('warehouse')
        if wh_id:
            try:
                cleaned_data['warehouse'] = Warehouse.objects.get(id=int(wh_id), company=company, is_active=True)
            except Exception:
                cleaned_data['warehouse'] = None
        else:
            cleaned_data['warehouse'] = None

        # Helper function for Terms
        def process_terms(term_raw):
            if isinstance(term_raw, list):
                return "\n".join([str(t).strip() for t in term_raw if str(t).strip()])
            if isinstance(term_raw, str):
                s = term_raw.strip()
                if s.startswith('[') and s.endswith(']'):
                    try:
                        import json
                        parsed = json.loads(s)
                        if isinstance(parsed, list):
                            return "\n".join([str(t).strip() for t in parsed if str(t).strip()])
                    except Exception:
                        pass
                return s
            return ""

        # 5. Terms, Notes & Strings
        cleaned_data['supplier_reference'] = str(data.get('supplier_reference') or '').strip()
        cleaned_data['payment_terms'] = process_terms(data.get('payment_terms'))
        cleaned_data['delivery_terms'] = process_terms(data.get('delivery_terms'))
        cleaned_data['warranty_terms'] = process_terms(data.get('warranty_terms'))
        cleaned_data['return_terms'] = process_terms(data.get('return_terms'))
        cleaned_data['special_instructions'] = str(data.get('special_instructions') or '').strip()
        cleaned_data['shipping_method'] = str(data.get('shipping_method') or '').strip()
        cleaned_data['place_of_supply'] = str(data.get('place_of_supply') or '').strip()
        cleaned_data['notes'] = str(data.get('notes') or '').strip()
        cleaned_data['internal_notes'] = str(data.get('internal_notes') or '').strip()
        
        status_val = str(data.get('status') or 'DRAFT').upper().strip()
        valid_statuses = [choice[0] for choice in PurchaseOrder.STATUS_CHOICES]
        if status_val not in valid_statuses:
            status_val = 'DRAFT'
        cleaned_data['status'] = status_val

        # 6. Items Validation & Tax Calculation
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
            errors['items'] = {'_non_field_': 'At least one valid item is required in the Purchase Order.'}
        else:
            cleaned_items = []
            item_errors = {}

            company_state_code = str(company.state_code or '').strip().zfill(2)
            supplier_obj = cleaned_data.get('supplier')
            supplier_state_code = str(cleaned_data.get('supplier_state_code_snapshot') or (supplier_obj.state_code if supplier_obj else company_state_code)).strip().zfill(2)

            for idx, item_raw in enumerate(items_data):
                row_errs = {}
                prod_id = item_raw.get('product_id') or item_raw.get('product')
                prod = None

                if prod_id and str(prod_id).upper() != 'OTHER':
                    try:
                        prod_id_int = int(str(prod_id).strip())
                        prod = Product.objects.get(id=prod_id_int, company=company, is_active=True)
                    except (Product.DoesNotExist, ValueError, TypeError):
                        prod = None

                product_name_snapshot = str(item_raw.get('product_name') or item_raw.get('name') or (prod.name if prod else '')).strip()
                if not product_name_snapshot and not prod:
                    row_errs['product'] = 'Product selection or product name is required.'

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
                        row_errs['rate'] = 'Purchase rate cannot be negative.'
                except (ValueError, TypeError):
                    row_errs['rate'] = 'Invalid purchase rate.'
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

                gst_rate = parse_money(item_raw.get('gst_rate', (prod.hsn_sac.gst_rate if (prod and prod.hsn_sac) else 18)))
                desc_snap = str(item_raw.get('description') or (prod.description if prod else '')).strip()
                hsn_snap = str(item_raw.get('hsn_sac') or (prod.hsn_sac.code if (prod and prod.hsn_sac) else '')).strip()
                uqc_snap = str(item_raw.get('uqc') or (prod.unit.code if (prod and prod.unit) else 'PCS')).strip()

                if row_errs:
                    item_errors[str(idx)] = row_errs
                else:
                    is_tax_inc = getattr(prod, 'tax_inclusive', False) if prod else False
                    if is_tax_inc:
                        net_inc = max(Decimal('0.00'), gross - disc)
                        taxable_item = quantize_amount(net_inc / (Decimal('1.00') + (gst_rate / Decimal('100.00'))))
                    else:
                        taxable_item = quantize_amount(gross - disc)

                    cgst_item, sgst_item, igst_item, _ = calculate_item_gst(
                        company_state_code,
                        supplier_state_code,
                        taxable_item,
                        gst_rate
                    )
                    line_total = quantize_amount(gross - disc) if is_tax_inc else quantize_amount(taxable_item + cgst_item + sgst_item + igst_item)

                    cleaned_items.append({
                        'product': prod,
                        'product_name_snapshot': product_name_snapshot,
                        'description_snapshot': desc_snap,
                        'hsn_sac_snapshot': hsn_snap,
                        'uqc_snapshot': uqc_snap,
                        'quantity': qty,
                        'rate': rate,
                        'discount': disc,
                        'taxable_amount': taxable_item,
                        'gst_rate': gst_rate,
                        'cgst_amount': cgst_item,
                        'sgst_amount': sgst_item,
                        'igst_amount': igst_item,
                        'cess_amount': Decimal('0.00'),
                        'total_amount': line_total,
                        'row_index': item_raw.get('row_index', idx + 1)
                    })

            if item_errors:
                errors['items'] = item_errors
            elif not cleaned_items:
                errors['items'] = {'_non_field_': 'Please add at least one valid product.'}
            else:
                cleaned_data['items'] = cleaned_items

        return cleaned_data, errors

    @classmethod
    def create_purchase_order(cls, company, user, data, files=None):
        cleaned_data, errors = cls.validate_purchase_order_payload(company, data)
        if errors:
            return {'success': False, 'status': 'error', 'errors': errors, 'message': 'Validation failed. Please correct errors.'}

        items = cleaned_data.pop('items')
        
        subtotal = Decimal('0.00')
        discount_total = Decimal('0.00')
        taxable_amount = Decimal('0.00')
        cgst_total = Decimal('0.00')
        sgst_total = Decimal('0.00')
        igst_total = Decimal('0.00')
        cess_total = Decimal('0.00')

        calculated_grand = Decimal('0.00')
        for item in items:
            subtotal += item['quantity'] * item['rate']
            discount_total += item['discount']
            taxable_amount += item['taxable_amount']
            cgst_total += item['cgst_amount']
            sgst_total += item['sgst_amount']
            igst_total += item['igst_amount']
            cess_total += item['cess_amount']
            calculated_grand += item['total_amount']

        apply_round = data.get('round_off_applied')
        if apply_round is None and 'round_off' in data:
            try:
                apply_round = (Decimal(str(data.get('round_off') or 0)) != Decimal('0.00'))
            except Exception:
                apply_round = False

        if apply_round:
            rounded_grand = quantize_amount(round(calculated_grand))
            round_off = quantize_amount(rounded_grand - calculated_grand)
        else:
            rounded_grand = quantize_amount(calculated_grand)
            round_off = Decimal('0.00')

        cleaned_data['subtotal'] = quantize_amount(subtotal)
        cleaned_data['discount_total'] = quantize_amount(discount_total)
        cleaned_data['taxable_amount'] = quantize_amount(taxable_amount)
        cleaned_data['cgst_total'] = quantize_amount(cgst_total)
        cleaned_data['sgst_total'] = quantize_amount(sgst_total)
        cleaned_data['igst_total'] = quantize_amount(igst_total)
        cleaned_data['cess_total'] = quantize_amount(cess_total)
        cleaned_data['round_off'] = round_off
        cleaned_data['grand_total'] = rounded_grand
        cleaned_data['company'] = company
        cleaned_data['created_by'] = user if user and user.is_authenticated else None

        with transaction.atomic():
            po = PurchaseOrder.objects.create(**cleaned_data)
            for idx, item in enumerate(items):
                row_idx = item.pop('row_index', idx + 1)
                item_obj = PurchaseOrderItem.objects.create(
                    purchase_order=po,
                    **item
                )
                if files:
                    photo_file = (
                        files.get(f'item_photo_{row_idx}') or
                        files.get(f'item_photo_row_{row_idx}') or
                        files.get(f'item_photo_{idx}') or
                        files.get(f'item_photo_row_{idx}') or
                        files.get(f'item_photo_{idx + 1}') or
                        files.get(f'item_photo_row_{idx + 1}')
                    )
                    if photo_file:
                        item_obj.item_image = photo_file
                        item_obj.save()

            if user:
                log_action(user, 'CREATE_PURCHASE_ORDER', 'PURCHASE_ORDER', po.id)

        return {
            'success': True,
            'status': 'success',
            'message': f"Purchase Order {po.po_number} created successfully!",
            'po_id': po.id,
            'po_number': po.po_number,
            'redirect_url': f'/company/purchase-orders/{po.id}/'
        }

    @classmethod
    def update_purchase_order(cls, company, user, po_id, data, files=None):
        po = get_object_or_404(PurchaseOrder, id=po_id, company=company)
        cleaned_data, errors = cls.validate_purchase_order_payload(company, data, exclude_po_id=po.id)
        if errors:
            return {'success': False, 'status': 'error', 'errors': errors, 'message': 'Validation failed. Please correct errors.'}

        items = cleaned_data.pop('items')

        subtotal = Decimal('0.00')
        discount_total = Decimal('0.00')
        taxable_amount = Decimal('0.00')
        cgst_total = Decimal('0.00')
        sgst_total = Decimal('0.00')
        igst_total = Decimal('0.00')
        cess_total = Decimal('0.00')

        for item in items:
            subtotal += item['quantity'] * item['rate']
            discount_total += item['discount']
            taxable_amount += item['taxable_amount']
            cgst_total += item['cgst_amount']
            sgst_total += item['sgst_amount']
            igst_total += item['igst_amount']
            cess_total += item['cess_amount']

        calculated_grand = taxable_amount + cgst_total + sgst_total + igst_total + cess_total
        apply_round = data.get('round_off_applied')
        if apply_round is None and 'round_off' in data:
            try:
                apply_round = (Decimal(str(data.get('round_off') or 0)) != Decimal('0.00'))
            except Exception:
                apply_round = False

        if apply_round:
            rounded_grand = quantize_amount(round(calculated_grand))
            round_off = quantize_amount(rounded_grand - calculated_grand)
        else:
            rounded_grand = quantize_amount(calculated_grand)
            round_off = Decimal('0.00')

        cleaned_data['subtotal'] = quantize_amount(subtotal)
        cleaned_data['discount_total'] = quantize_amount(discount_total)
        cleaned_data['taxable_amount'] = quantize_amount(taxable_amount)
        cleaned_data['cgst_total'] = quantize_amount(cgst_total)
        cleaned_data['sgst_total'] = quantize_amount(sgst_total)
        cleaned_data['igst_total'] = quantize_amount(igst_total)
        cleaned_data['cess_total'] = quantize_amount(cess_total)
        cleaned_data['round_off'] = round_off
        cleaned_data['grand_total'] = rounded_grand

        with transaction.atomic():
            for key, val in cleaned_data.items():
                setattr(po, key, val)
            po.save()

            po.items.all().delete()
            for idx, item in enumerate(items):
                row_idx = item.pop('row_index', idx + 1)
                item_obj = PurchaseOrderItem.objects.create(
                    purchase_order=po,
                    **item
                )
                if files:
                    photo_file = (
                        files.get(f'item_photo_{row_idx}') or
                        files.get(f'item_photo_row_{row_idx}') or
                        files.get(f'item_photo_{idx}') or
                        files.get(f'item_photo_row_{idx}') or
                        files.get(f'item_photo_{idx + 1}') or
                        files.get(f'item_photo_row_{idx + 1}')
                    )
                    if photo_file:
                        item_obj.item_image = photo_file
                        item_obj.save()

            if user:
                log_action(user, 'UPDATE_PURCHASE_ORDER', 'PURCHASE_ORDER', po.id)

            if user:
                log_action(user, 'UPDATE_PURCHASE_ORDER', 'PURCHASE_ORDER', po.id)

        return {
            'success': True,
            'status': 'success',
            'message': f"Purchase Order {po.po_number} updated successfully!",
            'po_id': po.id,
            'po_number': po.po_number,
            'redirect_url': f'/company/purchase-orders/{po.id}/'
        }

    @classmethod
    def duplicate_purchase_order(cls, company, user, po_id):
        po = get_object_or_404(PurchaseOrder, id=po_id, company=company)
        new_po_no = cls.generate_po_number(company)

        with transaction.atomic():
            new_po = PurchaseOrder.objects.create(
                company=company,
                supplier=po.supplier,
                supplier_name_snapshot=po.supplier_name_snapshot,
                supplier_phone_snapshot=po.supplier_phone_snapshot,
                supplier_email_snapshot=po.supplier_email_snapshot,
                supplier_gstin_snapshot=po.supplier_gstin_snapshot,
                supplier_pan_snapshot=po.supplier_pan_snapshot,
                supplier_address_snapshot=po.supplier_address_snapshot,
                supplier_state_snapshot=po.supplier_state_snapshot,
                supplier_state_code_snapshot=po.supplier_state_code_snapshot,
                po_number=new_po_no,
                po_date=date.today(),
                expected_delivery_date=po.expected_delivery_date,
                supplier_reference=po.supplier_reference,
                supplier_reference_date=po.supplier_reference_date,
                payment_terms=po.payment_terms,
                delivery_terms=po.delivery_terms,
                warranty_terms=po.warranty_terms,
                return_terms=po.return_terms,
                special_instructions=po.special_instructions,
                shipping_method=po.shipping_method,
                warehouse=po.warehouse,
                place_of_supply=po.place_of_supply,
                state=po.state,
                state_code=po.state_code,
                subtotal=po.subtotal,
                discount_total=po.discount_total,
                taxable_amount=po.taxable_amount,
                cgst_total=po.cgst_total,
                sgst_total=po.sgst_total,
                igst_total=po.igst_total,
                cess_total=po.cess_total,
                round_off=po.round_off,
                grand_total=po.grand_total,
                notes=po.notes,
                internal_notes=po.internal_notes,
                status='DRAFT',
                created_by=user if user and user.is_authenticated else None
            )

            for item in po.items.all():
                PurchaseOrderItem.objects.create(
                    purchase_order=new_po,
                    product=item.product,
                    product_name_snapshot=item.product_name_snapshot,
                    description_snapshot=item.description_snapshot,
                    hsn_sac_snapshot=item.hsn_sac_snapshot,
                    uqc_snapshot=item.uqc_snapshot,
                    quantity=item.quantity,
                    rate=item.rate,
                    discount=item.discount,
                    taxable_amount=item.taxable_amount,
                    gst_rate=item.gst_rate,
                    cgst_amount=item.cgst_amount,
                    sgst_amount=item.sgst_amount,
                    igst_amount=item.igst_amount,
                    cess_amount=item.cess_amount,
                    total_amount=item.total_amount
                )

            if user:
                log_action(user, 'DUPLICATE_PURCHASE_ORDER', 'PURCHASE_ORDER', new_po.id)

        return new_po

    @classmethod
    def convert_to_purchase_bill(cls, company, user, po_id):
        po = get_object_or_404(PurchaseOrder, id=po_id, company=company)
        if po.converted_to_purchase_bill:
            return {
                'success': False,
                'status': 'error',
                'message': f"Purchase Order {po.po_number} has already been converted to Purchase Bill {po.converted_to_purchase_bill.supplier_bill_no}.",
                'bill_id': po.converted_to_purchase_bill.id
            }

        bill_no = f"PB-{po.po_number}"
        # Ensure unique supplier_bill_no per supplier
        counter = 1
        orig_bill_no = bill_no
        while PurchaseBill.objects.filter(company=company, supplier=po.supplier, supplier_bill_no=bill_no).exists():
            bill_no = f"{orig_bill_no}-{counter}"
            counter += 1

        with transaction.atomic():
            bill = PurchaseBill.objects.create(
                company=company,
                supplier=po.supplier,
                supplier_bill_no=bill_no,
                bill_date=date.today(),
                due_date=po.expected_delivery_date or date.today(),
                subtotal=po.subtotal,
                discount_total=po.discount_total,
                taxable_value=po.taxable_amount,
                cgst_total=po.cgst_total,
                sgst_total=po.sgst_total,
                igst_total=po.igst_total,
                cess_total=po.cess_total,
                round_off=po.round_off,
                grand_total=po.grand_total,
                paid_amount=Decimal('0.00'),
                status='DRAFT',
                notes=f"Converted from Purchase Order {po.po_number} on {date.today().strftime('%Y-%m-%d')}"
            )

            for item in po.items.all():
                PurchaseBillItem.objects.create(
                    purchase_bill=bill,
                    product=item.product,
                    quantity=item.quantity,
                    rate=item.rate,
                    discount=item.discount,
                    taxable_value=item.taxable_amount,
                    gst_rate=item.gst_rate,
                    cgst_amount=item.cgst_amount,
                    sgst_amount=item.sgst_amount,
                    igst_amount=item.igst_amount,
                    hsn_sac_code=item.hsn_sac_snapshot,
                    total_amount=item.total_amount
                )

            po.converted_to_purchase_bill = bill
            po.status = 'RECEIVED'
            po.save()

            if user:
                log_action(user, 'CONVERT_PO_TO_BILL', 'PURCHASE_ORDER', po.id)

        return {
            'success': True,
            'status': 'success',
            'message': f"Purchase Order {po.po_number} converted to Purchase Bill {bill.supplier_bill_no} successfully!",
            'bill_id': bill.id,
            'redirect_url': f'/company/purchase-bills/{bill.id}/'
        }

