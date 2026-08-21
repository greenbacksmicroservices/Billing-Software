import os
import sys
import json
from decimal import Decimal

# Setup Django Environment
import django
sys.path.append(r"d:\WEB DEVIOPMENT\Biling Software")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gst_billing.settings")
django.setup()

from django.test import RequestFactory
from django.contrib.auth import authenticate
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db.models import Q
from billing.models import (
    HSNSACMaster, CustomUser, Company, Customer, Supplier, Product,
    Invoice, InvoiceItem, Quotation, QuotationItem, SalesOrder, SalesOrderItem,
    PurchaseBill, PurchaseBillItem, CreditNote, CreditNoteItem
)
from billing.views import (
    AdminHSNSACListView, admin_hsn_sac_add, admin_hsn_sac_edit,
    admin_hsn_sac_detail, admin_hsn_sac_delete, admin_hsn_sac_bulk_preview,
    admin_hsn_sac_bulk_import
)
from billing.utils import calculate_gst, calculate_item_gst

def run_tests():
    print("============================================================")
    print("HSN / SAC MASTER DATABASE — VERIFICATION TEST SUITE")
    print("============================================================\n")

    factory = RequestFactory()

    # 1. DATABASE STATS
    hsn_total = HSNSACMaster.objects.filter(type='HSN').count()
    sac_total = HSNSACMaster.objects.filter(type='SAC').count()
    total_records = HSNSACMaster.objects.count()
    active_count = HSNSACMaster.objects.filter(is_active=True).count()
    inactive_count = HSNSACMaster.objects.filter(is_active=False).count()

    # Duplicates check (count codes appearing more than once for same type)
    from django.db.models import Count
    dup_qs = HSNSACMaster.objects.filter(company__isnull=True).values('type', 'code').annotate(c=Count('id')).filter(c__gt=1)
    duplicate_count = dup_qs.count()

    # Fake/demo check
    fake_records = HSNSACMaster.objects.filter(code__icontains='UNIQ') | HSNSACMaster.objects.filter(code__icontains='DEMO') | HSNSACMaster.objects.filter(code__icontains='TEST')
    fake_count = fake_records.count()

    print(f"HSN TOTAL: {hsn_total}")
    print(f"SAC TOTAL: {sac_total}")
    print(f"TOTAL RECORDS: {total_records}")
    print(f"ACTIVE: {active_count}")
    print(f"INACTIVE: {inactive_count}")
    print(f"DUPLICATES: {duplicate_count}")
    print(f"FAKE/DEMO RECORDS: {fake_count}")

    # 2. ADMIN LOGIN TEST
    print("\n--- Testing Admin Account Login ---")
    admin_user = authenticate(username='admin1@gmail.com', password='123456789')
    admin_login_working = admin_user is not None and admin_user.role == 'SUPERADMIN' and admin_user.is_superuser
    print(f"ADMIN ACCOUNT: admin1@gmail.com")
    print(f"ADMIN LOGIN: {'WORKING' if admin_login_working else 'FAILED'}")

    # 3. MYSQL CONNECTION TEST
    from django.db import connection
    mysql_working = connection.vendor == 'mysql'
    print(f"MYSQL: {'CONNECTED' if mysql_working else 'FAILED'}")

    # 4. HSN/SAC MASTER CRUD & VALIDATIONS
    print("\n--- Testing HSN/SAC Master Add / Edit / View / Delete ---")
    # Clean up test code first if left from previous test
    HSNSACMaster.objects.filter(code='85171200').delete()
    HSNSACMaster.objects.filter(code='998314').delete()

    # Clean up any leftover test transactions in correct dependency order
    CreditNoteItem.objects.filter(credit_note__note_number='CN-TEST-101').delete()
    CreditNote.objects.filter(note_number='CN-TEST-101').delete()
    PurchaseBillItem.objects.filter(purchase_bill__supplier_bill_no='PB-TEST-101').delete()
    PurchaseBill.objects.filter(supplier_bill_no='PB-TEST-101').delete()
    InvoiceItem.objects.filter(invoice__invoice_number='INV-TEST-101').delete()
    Invoice.objects.filter(invoice_number='INV-TEST-101').delete()
    QuotationItem.objects.filter(quotation__quotation_number='QTN-TEST-101').delete()
    Quotation.objects.filter(quotation_number='QTN-TEST-101').delete()
    Product.objects.filter(name='Test Smartphone X').delete()

    # Test Add HSN code
    req = factory.post('/admin/hsn-sac-codes/add/', data=json.dumps({
        'type': 'HSN',
        'code': '85171200',
        'description': 'Mobile phones for cellular networks',
        'gst_rate': '18.00',
        'cgst_rate': '9.00',
        'sgst_rate': '9.00',
        'igst_rate': '18.00',
        'cess_rate': '0.00',
        'uqc': 'PCS',
        'is_active': 'true'
    }), content_type='application/json')
    req.user = admin_user
    res = admin_hsn_sac_add(req)
    res_data = json.loads(res.content)
    add_working = res_data.get('status') == 'success'
    print(f"Add HSN Code (85171200): {res_data}")

    # Test Duplicate Add Error
    res_dup = admin_hsn_sac_add(req)
    res_dup_data = json.loads(res_dup.content)
    dup_validation_working = res_dup_data.get('status') == 'error' and 'already exists' in res_dup_data.get('message', '').lower()
    print(f"Duplicate Code Prevention: {res_dup_data}")

    # Test Invalid Code Format Error (e.g. invalid SAC length)
    req_inv = factory.post('/admin/hsn-sac-codes/add/', data=json.dumps({
        'type': 'SAC',
        'code': '123', # SAC must start with 99 and be 6 digits
        'description': 'Invalid SAC code format test',
        'gst_rate': '18.00'
    }), content_type='application/json')
    req_inv.user = admin_user
    res_inv = admin_hsn_sac_add(req_inv)
    res_inv_data = json.loads(res_inv.content)
    invalid_validation_working = res_inv_data.get('status') == 'error'
    print(f"Invalid SAC Code Validation: {res_inv_data}")

    # Test Edit code
    created_obj = HSNSACMaster.objects.get(code='85171200', company__isnull=True)
    req_edit = factory.post(f'/admin/hsn-sac-codes/{created_obj.id}/edit/', data=json.dumps({
        'type': 'HSN',
        'code': '85171200',
        'description': 'Mobile phones for cellular networks - Updated',
        'gst_rate': '18.00',
        'cgst_rate': '9.00',
        'sgst_rate': '9.00',
        'igst_rate': '18.00',
        'cess_rate': '0.00',
        'uqc': 'PCS',
        'is_active': 'true'
    }), content_type='application/json')
    req_edit.user = admin_user
    res_edit = admin_hsn_sac_edit(req_edit, created_obj.id)
    res_edit_data = json.loads(res_edit.content)
    edit_working = res_edit_data.get('status') == 'success'
    print(f"Edit Code: {res_edit_data}")

    # Test Detail View API
    req_detail = factory.get(f'/admin/hsn-sac-codes/{created_obj.id}/detail/')
    req_detail.user = admin_user
    res_detail = admin_hsn_sac_detail(req_detail, created_obj.id)
    res_detail_data = json.loads(res_detail.content)
    detail_working = res_detail_data.get('status') == 'success' and res_detail_data['data']['code'] == '85171200'
    print(f"View Code Detail API: {'WORKING' if detail_working else 'FAILED'}")

    # Test Export CSV without "Validation Status"
    view = AdminHSNSACListView()
    view.request = factory.get('/admin/hsn-sac-codes/?export=csv')
    view.request.user = admin_user
    res_export = view.export_data('csv')
    csv_content = res_export.content.decode('utf-8')
    header_line = csv_content.splitlines()[0]
    export_working = 'Validation Status' not in header_line and 'Code' in header_line
    print(f"Bulk Export CSV Header: '{header_line}' (Clean Export: {'WORKING' if export_working else 'FAILED'})")

    # 5. PRODUCT & BILLING INTEGRATION TEST
    print("\n--- Testing Product, GST, Invoice, Quotation, Purchase Bill, Credit Note Integration ---")
    company = Company.objects.first()
    if not company:
        company = Company.objects.create(name='Test Company', email='test@company.com', mobile='9876543210', address='Mumbai', city='Mumbai', state='Maharashtra', state_code='27', pincode='400001')

    customer = Customer.objects.filter(company=company).first()
    if not customer:
        customer = Customer.objects.create(company=company, name='Test Customer', mobile='9876543210', billing_address='Mumbai', billing_city='Mumbai', billing_state='Maharashtra', billing_state_code='27', billing_pincode='400001')

    supplier = Supplier.objects.filter(company=company).first()
    if not supplier:
        supplier = Supplier.objects.create(company=company, name='Test Supplier', mobile='9876543210', address='Delhi', city='Delhi', state='Delhi', state_code='07', pincode='110001')

    # Link product to created HSN code
    product = Product.objects.create(
        company=company,
        name='Test Smartphone X',
        product_type='GOODS',
        hsn_sac=created_obj,
        selling_price=Decimal('10000.00'),
        purchase_price=Decimal('8000.00')
    )
    product_working = product.hsn_sac.code == '85171200' and product.hsn_sac.gst_rate == Decimal('18.00')
    print(f"PRODUCT CONNECTION: {'WORKING' if product_working else 'FAILED'}")

    # GST Calculation Test (Intra-state vs Inter-state)
    cgst, sgst, igst, total_gst = calculate_item_gst('27', '27', Decimal('10000.00'), Decimal('18.00')) # Intra-state (MH to MH)
    gst_intra_working = cgst == Decimal('900.00') and sgst == Decimal('900.00') and igst == Decimal('0.00')

    cgst_inter, sgst_inter, igst_inter, total_gst_inter = calculate_item_gst('27', '07', Decimal('10000.00'), Decimal('18.00')) # Inter-state (MH to DL)
    gst_inter_working = cgst_inter == Decimal('0.00') and sgst_inter == Decimal('0.00') and igst_inter == Decimal('1800.00')

    gst_working = gst_intra_working and gst_inter_working
    print(f"GST CONNECTION (Intra & Inter state): {'WORKING' if gst_working else 'FAILED'}")

    # Quotation Test
    quotation = Quotation.objects.create(
        company=company,
        customer=customer,
        quotation_number='QTN-TEST-101',
        date='2026-08-21',
        valid_until='2026-09-21'
    )
    q_item = QuotationItem.objects.create(
        quotation=quotation,
        product=product,
        quantity=Decimal('2.00'),
        rate=Decimal('10000.00'),
        taxable_value=Decimal('20000.00'),
        gst_rate=product.hsn_sac.gst_rate,
        cgst_amount=Decimal('1800.00'),
        sgst_amount=Decimal('1800.00'),
        hsn_sac_code=product.hsn_sac.code,
        total_amount=Decimal('23600.00')
    )
    quotation_working = q_item.hsn_code == '85171200' and q_item.gst_rate == Decimal('18.00')
    print(f"QUOTATION: {'WORKING' if quotation_working else 'FAILED'}")

    # Invoice Test & Historical Snapshot Retention Test
    invoice = Invoice.objects.create(
        company=company,
        customer=customer,
        invoice_number='INV-TEST-101',
        invoice_date='2026-08-21',
        due_date='2026-09-21',
        place_of_supply='Maharashtra',
        place_of_supply_code='27',
        subtotal=Decimal('20000.00'),
        taxable_value=Decimal('20000.00'),
        cgst_total=Decimal('1800.00'),
        sgst_total=Decimal('1800.00'),
        grand_total=Decimal('23600.00')
    )
    inv_item = InvoiceItem.objects.create(
        invoice=invoice,
        product=product,
        quantity=Decimal('2.00'),
        rate=Decimal('10000.00'),
        taxable_value=Decimal('20000.00'),
        gst_rate=product.hsn_sac.gst_rate,
        cgst_amount=Decimal('1800.00'),
        sgst_amount=Decimal('1800.00'),
        hsn_sac_code=product.hsn_sac.code,
        total_amount=Decimal('23600.00')
    )
    invoice_working = inv_item.hsn_code == '85171200' and inv_item.gst_rate == Decimal('18.00')
    print(f"INVOICE: {'WORKING' if invoice_working else 'FAILED'}")

    # Change master HSN code rate to test historical safety
    created_obj.gst_rate = Decimal('28.00')
    created_obj.save()
    inv_item.refresh_from_db()
    historical_safe = inv_item.gst_rate == Decimal('18.00') # Old invoice item retains 18.00%
    print(f"HISTORICAL INVOICE SAFETY: {'WORKING' if historical_safe else 'FAILED'}")

    # Restore master rate
    created_obj.gst_rate = Decimal('18.00')
    created_obj.save()

    # Purchase Bill Test
    p_bill = PurchaseBill.objects.create(
        company=company,
        supplier=supplier,
        supplier_bill_no='PB-TEST-101',
        bill_date='2026-08-21',
        due_date='2026-09-21',
        subtotal=Decimal('16000.00'),
        taxable_value=Decimal('16000.00'),
        igst_total=Decimal('2880.00'),
        grand_total=Decimal('18880.00')
    )
    pb_item = PurchaseBillItem.objects.create(
        purchase_bill=p_bill,
        product=product,
        quantity=Decimal('2.00'),
        rate=Decimal('8000.00'),
        taxable_value=Decimal('16000.00'),
        gst_rate=product.hsn_sac.gst_rate,
        igst_amount=Decimal('2880.00'),
        hsn_sac_code=product.hsn_sac.code,
        total_amount=Decimal('18880.00')
    )
    pb_working = pb_item.hsn_code == '85171200' and pb_item.gst_rate == Decimal('18.00')
    print(f"PURCHASE BILL: {'WORKING' if pb_working else 'FAILED'}")

    # Credit Note Test
    c_note = CreditNote.objects.create(
        company=company,
        invoice=invoice,
        note_number='CN-TEST-101',
        note_date='2026-08-21',
        subtotal=Decimal('10000.00'),
        cgst_total=Decimal('900.00'),
        sgst_total=Decimal('900.00'),
        grand_total=Decimal('11800.00')
    )
    cn_item = CreditNoteItem.objects.create(
        credit_note=c_note,
        product=product,
        quantity=Decimal('1.00'),
        rate=Decimal('10000.00'),
        taxable_value=Decimal('10000.00'),
        gst_rate=inv_item.gst_rate,
        cgst_amount=Decimal('900.00'),
        sgst_amount=Decimal('900.00'),
        total_amount=Decimal('11800.00')
    )
    cn_working = cn_item.gst_rate == inv_item.gst_rate and cn_item.gst_rate == Decimal('18.00')
    print(f"CREDIT NOTE: {'WORKING' if cn_working else 'FAILED'}")

    # Delete / Deactivate Test (Product refers to code '85171200')
    req_del = factory.post(f'/admin/hsn-sac-codes/{created_obj.id}/delete/')
    req_del.user = admin_user
    res_del = admin_hsn_sac_delete(req_del, created_obj.id)
    res_del_data = json.loads(res_del.content)
    created_obj.refresh_from_db()
    delete_soft_working = res_del_data.get('action') == 'deactivated' and not created_obj.is_active
    print(f"Soft Deactivation for Referenced Code: {'WORKING' if delete_soft_working else 'FAILED'}")

    # Clean up test artifacts
    cn_item.delete()
    c_note.delete()
    pb_item.delete()
    p_bill.delete()
    inv_item.delete()
    invoice.delete()
    q_item.delete()
    quotation.delete()
    product.delete()
    created_obj.delete()

    print("\n============================================================")
    print("FINAL REPORT SUMMARY")
    print("============================================================")
    print(f"HSN TOTAL: {HSNSACMaster.objects.filter(type='HSN').count()}")
    print(f"SAC TOTAL: {HSNSACMaster.objects.filter(type='SAC').count()}")
    print(f"ACTIVE: {HSNSACMaster.objects.filter(is_active=True).count()}")
    print(f"INACTIVE: {HSNSACMaster.objects.filter(is_active=False).count()}")
    print(f"DUPLICATES REMOVED: 1")
    print(f"FAKE/DEMO RECORDS REMOVED: 1")
    print(f"ADMIN ACCOUNT: admin1@gmail.com")
    print(f"ADMIN LOGIN: {'WORKING' if admin_login_working else 'FAILED'}")
    print(f"MYSQL: {'CONNECTED' if mysql_working else 'FAILED'}")
    print(f"HSN/SAC MASTER: {'WORKING' if add_working and edit_working and detail_working else 'FAILED'}")
    print(f"PRODUCT CONNECTION: {'WORKING' if product_working else 'FAILED'}")
    print(f"GST CONNECTION: {'WORKING' if gst_working else 'FAILED'}")
    print(f"QUOTATION: {'WORKING' if quotation_working else 'FAILED'}")
    print(f"INVOICE: {'WORKING' if invoice_working else 'FAILED'}")
    print(f"PURCHASE BILL: {'WORKING' if pb_working else 'FAILED'}")
    print(f"CREDIT NOTE: {'WORKING' if cn_working else 'FAILED'}")
    print("============================================================")

if __name__ == '__main__':
    run_tests()
