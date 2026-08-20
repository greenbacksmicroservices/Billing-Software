import json
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from billing.models import (
    Company, SubscriptionPlan, Product, HSNSACMaster, Customer, Warehouse,
    Invoice, InvoiceItem, StockMovement, Supplier, PurchaseBill,
    CreditNote, CreditNoteItem, DebitNote, DebitNoteItem, CustomerLedger, SupplierLedger,
    GSTTransaction, Quotation, QuotationItem, SalesOrder, SalesOrderItem, Payment, Expense
)
from billing.utils import update_product_stock

CustomUser = get_user_model()

class DeletionFlowTestCase(TestCase):
    def setUp(self):
        # Setup basic SaaS plans and company
        self.plan = SubscriptionPlan.objects.create(
            name="Premium Plan",
            monthly_price=Decimal("1000.00"),
            user_limit=10,
            is_active=True
        )
        
        self.company = Company.objects.create(
            name="B1 Software Pvt Ltd",
            state="Maharashtra",
            state_code="27",
            pincode="400001",
            plan=self.plan,
            subscription_status="ACTIVE",
            is_active=True
        )
        
        self.admin_user = CustomUser.objects.create_user(
            username="b1_admin",
            password="password123",
            email="admin@b1.com",
            role="ADMIN",
            company=self.company,
            is_active=True
        )

        self.other_admin = CustomUser.objects.create_user(
            username="other_admin",
            password="password123",
            email="other@b1.com",
            role="ADMIN",
            company=self.company,
            is_active=True
        )

        self.warehouse = Warehouse.objects.create(
            company=self.company,
            name="Main WH",
            code="MWH",
            is_active=True
        )

        self.customer = Customer.objects.create(
            company=self.company,
            name="Test Customer",
            billing_address="123 Road",
            billing_city="Mumbai",
            billing_state="Maharashtra",
            billing_state_code="27",
            billing_pincode="400001",
            outstanding_balance=Decimal("0.00"),
            is_active=True
        )

        self.supplier = Supplier.objects.create(
            company=self.company,
            name="Test Supplier",
            address="456 Avenue",
            city="Mumbai",
            state="Maharashtra",
            state_code="27",
            pincode="400001",
            outstanding_balance=Decimal("0.00"),
            is_active=True
        )

        self.hsn = HSNSACMaster.objects.create(
            company=self.company,
            code="998311",
            description="Software Development Services",
            gst_rate=Decimal("18.00"),
            is_active=True
        )

        self.product = Product.objects.create(
            company=self.company,
            name="SaaS License",
            hsn_sac=self.hsn,
            purchase_price=Decimal("100.00"),
            selling_price=Decimal("200.00"),
            track_inventory=True,
            current_stock=Decimal("10.00"),
            is_active=True
        )

    def test_company_deactivation_vs_deletion(self):
        c = Client()
        # Create a superadmin user to delete the company
        sa = CustomUser.objects.create_user(
            username="sysadmin", password="password", role="SUPERADMIN", is_active=True
        )
        c.force_login(sa)

        # CASE A: Company with no dependencies (unlinked)
        unlinked_company = Company.objects.create(
            name="Unlinked Pvt Ltd",
            state="Maharashtra",
            state_code="27",
            pincode="400001",
            plan=self.plan,
            subscription_status="ACTIVE",
            is_active=True
        )
        res_del = c.post(reverse('api_generic_delete', args=['company', unlinked_company.id]))
        self.assertEqual(res_del.status_code, 200)
        data_del = res_del.json()
        self.assertTrue(data_del.get('success'))
        self.assertEqual(data_del.get('action'), 'deleted')
        self.assertEqual(data_del.get('message'), "Company deleted successfully.")
        self.assertFalse(Company.objects.filter(id=unlinked_company.id).exists())

        # CASE B: Company with dependencies (users/invoices)
        res_deact = c.post(reverse('api_generic_delete', args=['company', self.company.id]))
        self.assertEqual(res_deact.status_code, 200)
        data_deact = res_deact.json()
        self.assertTrue(data_deact.get('success'))
        self.assertEqual(data_deact.get('action'), 'deactivated')
        self.assertEqual(data_deact.get('message'), f"Company '{self.company.name}' was deactivated because it is linked to existing users or financial records.")
        
        # Verify database changed to inactive
        self.company.refresh_from_db()
        self.assertFalse(self.company.is_active)

    def test_company_list_excludes_inactive(self):
        c = Client()
        sa = CustomUser.objects.create_user(
            username="sysadmin2", password="password", role="SUPERADMIN", is_active=True
        )
        c.force_login(sa)
        
        # Initially company is active, so it shows up in list
        res = c.get(reverse('admin_companies_list'))
        self.assertContains(res, self.company.name)

        # Deactivate company
        self.company.is_active = False
        self.company.save()

        # Should NOT show up in list now
        res = c.get(reverse('admin_companies_list'))
        self.assertNotContains(res, self.company.name)

    def test_product_deactivation_vs_deletion(self):
        c = Client()
        c.force_login(self.admin_user)

        # Linked to nothing yet, so physical delete allowed
        res = c.post(reverse('api_generic_delete', args=['product', self.product.id]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get('action'), 'deleted')
        self.assertFalse(Product.objects.filter(id=self.product.id).exists())

        # Re-create and link
        prod = Product.objects.create(
            company=self.company, name="New SaaS", is_active=True
        )
        # Link to StockMovement
        StockMovement.objects.create(
            company=self.company, product=prod, warehouse=self.warehouse,
            quantity=Decimal("5.00"), movement_type="OPENING"
        )
        res_link = c.post(reverse('api_generic_delete', args=['product', prod.id]))
        self.assertEqual(res_link.status_code, 200)
        self.assertEqual(res_link.json().get('action'), 'deactivated')
        self.assertEqual(res_link.json().get('message'), f"Product '{prod.name}' was deactivated because it is linked to existing users or financial records.")
        prod.refresh_from_db()
        self.assertFalse(prod.is_active)

    def test_payment_deletion_reverts_accounting(self):
        c = Client()
        c.force_login(self.admin_user)

        # Setup Invoice and Payment
        self.customer.outstanding_balance = Decimal("118.00")
        self.customer.save()

        invoice = Invoice.objects.create(
            company=self.company, customer=self.customer, invoice_number="INV-PAY-01",
            invoice_date=date.today(), due_date=date.today(), status="PARTIALLY_PAID",
            grand_total=Decimal("118.00"), paid_amount=Decimal("50.00")
        )

        payment = Payment.objects.create(
            company=self.company, payment_type="RECEIPT", customer=self.customer,
            invoice=invoice, amount=Decimal("50.00"), payment_date=date.today(),
            payment_method="CASH"
        )

        # Create Ledger Entry for Payment
        CustomerLedger.objects.create(
            company=self.company, customer=self.customer, date=date.today(),
            entry_type="PAYMENT", reference_id=payment.id, reference_no="RCPT #1",
            credit=payment.amount
        )

        # Deleting payment
        res = c.post(reverse('api_generic_delete', args=['payment', payment.id]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get('action'), 'deleted')

        # Check invoice status and paid_amount reverted
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("0.00"))
        self.assertEqual(invoice.status, "POSTED")

        # Check customer outstanding balance restored
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.outstanding_balance, Decimal("168.00")) # 118 + 50

        # Check ledger entry deleted
        self.assertFalse(CustomerLedger.objects.filter(entry_type="PAYMENT", reference_id=payment.id).exists())

    def test_credit_note_cancellation(self):
        c = Client()
        c.force_login(self.admin_user)

        invoice = Invoice.objects.create(
            company=self.company, customer=self.customer, invoice_number="INV-CN-01",
            invoice_date=date.today(), due_date=date.today(), status="POSTED",
            taxable_value=Decimal("100.00"), grand_total=Decimal("118.00")
        )
        
        cn = CreditNote.objects.create(
            company=self.company, invoice=invoice, note_number="CN-01",
            note_date=date.today(), status="POSTED", subtotal=Decimal("50.00"),
            grand_total=Decimal("59.00")
        )

        # Simulate creation balance effect
        self.customer.outstanding_balance -= cn.grand_total
        self.customer.save()

        # Create GSTTransaction and Ledger entries
        GSTTransaction.objects.create(
            company=self.company, transaction_type="CREDIT_NOTE", reference_id=cn.id,
            reference_no=cn.note_number, date=cn.note_date, taxable_value=-cn.subtotal,
            is_cancelled=False
        )
        CustomerLedger.objects.create(
            company=self.company, customer=self.customer, entry_type="CREDIT_NOTE",
            reference_id=cn.id, reference_no=cn.note_number, date=cn.note_date,
            credit=cn.grand_total
        )

        # Deleting POSTED credit note should cancel it
        res = c.post(reverse('api_generic_delete', args=['credit_note', cn.id]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get('action'), 'deactivated')

        cn.refresh_from_db()
        self.assertEqual(cn.status, "CANCELLED")

        # Verify customer outstanding restored
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.outstanding_balance, Decimal("0.00")) # -59 + 59 = 0

        # Verify GSTTransaction cancelled
        gt = GSTTransaction.objects.get(transaction_type="CREDIT_NOTE", reference_id=cn.id)
        self.assertTrue(gt.is_cancelled)

        # Verify CustomerLedger deleted
        self.assertFalse(CustomerLedger.objects.filter(entry_type="CREDIT_NOTE", reference_id=cn.id).exists())

    def test_superadmin_deletes_last_admin(self):
        c = Client()
        sa = CustomUser.objects.create_user(
            username="sysadmin3", password="password", role="SUPERADMIN", is_active=True
        )
        c.force_login(sa)

        # other_admin is also an admin. Let's make other_admin inactive.
        self.other_admin.is_active = False
        self.other_admin.save()

        # admin_user is now the last active Company Admin.
        # Superadmin tries to deactivate him - should be allowed!
        res = c.post(reverse('api_generic_delete', args=['user', self.admin_user.id]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get('action'), 'deactivated')
        self.assertEqual(res.json().get('message'), f"User '{self.admin_user.username}' was deactivated because it is linked to existing users or financial records.")
        self.admin_user.refresh_from_db()
        self.assertFalse(self.admin_user.is_active)

    def test_save_quotation_and_validation(self):
        c = Client()
        c.force_login(self.admin_user)

        # Successful quotation save
        payload = {
            'customer_id': self.customer.id,
            'quotation_number': 'QTN-2026-X100',
            'date': date.today().strftime('%Y-%m-%d'),
            'valid_until': (date.today() + timedelta(days=15)).strftime('%Y-%m-%d'),
            'notes': 'Terms: Cash on delivery.',
            'items': [
                {'product_id': self.product.id, 'quantity': 5, 'rate': 220, 'discount': 10}
            ]
        }
        res = c.post(reverse('quotation_add'), data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        self.assertTrue(Quotation.objects.filter(company=self.company, quotation_number='QTN-2026-X100').exists())

        # Failed quotation save (missing customer)
        payload_invalid = payload.copy()
        payload_invalid['customer_id'] = ''
        res_fail = c.post(reverse('quotation_add'), data=json.dumps(payload_invalid), content_type='application/json')
        self.assertEqual(res_fail.status_code, 400)
        self.assertFalse(res_fail.json().get('success'))
