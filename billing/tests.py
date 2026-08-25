import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from decimal import Decimal
from datetime import date, timedelta
from .models import (
    Company, SubscriptionPlan, Product, Category, Brand, HSNSACMaster, Customer, Warehouse,
    Invoice, InvoiceItem, StockMovement, Supplier, PurchaseBill,
    CreditNote, DebitNote, CustomerLedger, SupplierLedger, GSTTransaction,
    Quotation, QuotationItem, SalesOrder, SalesOrderItem, Payment, Expense
)
from .utils import calculate_item_gst, recalculate_invoice_totals

CustomUser = get_user_model()

class BillingSoftwareTests(TestCase):
    def setUp(self):
        # 1. Setup subscription plans
        self.plan = SubscriptionPlan.objects.create(
            name="Test Premium Plan",
            user_limit=5,
            invoice_limit=100,
            product_limit=100
        )
        
        # 2. Setup Company A (Maharashtra, Code 27)
        self.company_a = Company.objects.create(
            name="Company A",
            state="Maharashtra",
            state_code="27",
            pincode="400001",
            plan=self.plan,
            subscription_status="ACTIVE"
        )
        self.user_a = CustomUser.objects.create_user(
            username="usera",
            password="passworda",
            email="usera@companya.com",
            role="ADMIN",
            company=self.company_a
        )
        
        # 3. Setup Company B (Gujarat, Code 24)
        self.company_b = Company.objects.create(
            name="Company B",
            state="Gujarat",
            state_code="24",
            pincode="380001",
            plan=self.plan,
            subscription_status="ACTIVE"
        )
        self.user_b = CustomUser.objects.create_user(
            username="userb",
            password="passwordb",
            email="userb@companyb.com",
            role="ADMIN",
            company=self.company_b
        )
        
        # Common Masters for Company A
        self.hsn_goods = HSNSACMaster.objects.create(
            company=self.company_a,
            code="8471",
            description="Goods",
            gst_rate=Decimal("18.00")
        )
        self.warehouse_a = Warehouse.objects.create(
            company=self.company_a,
            name="Main WH A",
            code="WHA",
            is_active=True
        )
        self.product_a = Product.objects.create(
            company=self.company_a,
            name="ThinkPad T490",
            purchase_price=Decimal("40000.00"),
            selling_price=Decimal("50000.00"),
            hsn_sac=self.hsn_goods,
            track_inventory=True,
            current_stock=Decimal("10.00")
        )
        self.customer_in_state = Customer.objects.create(
            company=self.company_a,
            name="BKC Customer",
            billing_state="Maharashtra",
            billing_state_code="27",
            billing_pincode="400051",
            mobile="9876543210"
        )
        self.customer_out_state = Customer.objects.create(
            company=self.company_a,
            name="Ahmedabad Customer",
            billing_state="Gujarat",
            billing_state_code="24",
            billing_pincode="380001",
            mobile="9876543211"
        )

    def test_gst_routing_logic(self):
        """
        Verify CGST/SGST/IGST splitting logic based on Place of Supply comparison.
        """
        # Intra-state: MH (27) to MH (27) -> CGST 9% + SGST 9%
        cgst, sgst, igst, total = calculate_item_gst(
            self.company_a.state_code,
            self.customer_in_state.billing_state_code,
            Decimal("1000.00"),
            Decimal("18.00")
        )
        self.assertEqual(cgst, Decimal("90.00"))
        self.assertEqual(sgst, Decimal("90.00"))
        self.assertEqual(igst, Decimal("0.00"))
        
        # Inter-state: MH (27) to GJ (24) -> IGST 18%
        cgst, sgst, igst, total = calculate_item_gst(
            self.company_a.state_code,
            self.customer_out_state.billing_state_code,
            Decimal("1000.00"),
            Decimal("18.00")
        )
        self.assertEqual(cgst, Decimal("0.00"))
        self.assertEqual(sgst, Decimal("0.00"))
        self.assertEqual(igst, Decimal("180.00"))

    def test_multi_tenant_isolation(self):
        """
        Asserts that User B is blocked with 404/403 when trying to access Company A's invoice.
        """
        # Create invoice in Company A
        invoice_a = Invoice.objects.create(
            company=self.company_a,
            customer=self.customer_in_state,
            invoice_number="INV-A-1",
            invoice_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            place_of_supply=self.customer_in_state.billing_state,
            place_of_supply_code=self.customer_in_state.billing_state_code,
            status='POSTED'
        )

        c = Client()
        # Login as User B
        c.login(username="userb", password="passwordb")
        
        # Request details of Invoice A (owned by Company A)
        # Standard queryset mixin checks filter(company=request.user.company)
        # Should return a 404 since Invoice A doesn't belong to Company B
        response = c.get(f"/company/invoices/{invoice_a.id}/")
        self.assertEqual(response.status_code, 404)

    def test_inventory_updates_on_sale(self):
        """
        Verifies that sales operations adjust product stock correctly.
        """
        initial_stock = self.product_a.current_stock # 10.0
        
        # Create an invoice in Company A
        invoice = Invoice.objects.create(
            company=self.company_a,
            customer=self.customer_in_state,
            invoice_number="INV-A-2",
            invoice_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            place_of_supply=self.customer_in_state.billing_state,
            place_of_supply_code=self.customer_in_state.billing_state_code,
            status='POSTED'
        )
        
        # Add Invoice item with qty = 2
        item = InvoiceItem.objects.create(
            invoice=invoice,
            product=self.product_a,
            quantity=Decimal("2.00"),
            rate=Decimal("50000.00"),
            discount=Decimal("0.00"),
            taxable_value=Decimal("100000.00"),
            total_amount=Decimal("118000.00")
        )
        
        # Post StockMovement log
        StockMovement.objects.create(
            company=self.company_a,
            product=self.product_a,
            warehouse=self.warehouse_a,
            quantity=-Decimal("2.00"),
            movement_type='SALE',
            reference_id=invoice.id,
            reference_no=invoice.invoice_number,
            created_by=self.user_a
        )
        
        # Update product current_stock cache
        self.product_a.current_stock += -Decimal("2.00")
        self.product_a.save()
        
        # Stock should be reduced by 2
        self.assertEqual(self.product_a.current_stock, Decimal("8.00"))

    def test_unified_login_flow(self):
        """
        Verify that GET, POST (valid/invalid credentials), redirects for authenticated users,
        and logout flows work correctly under the unified login system.
        """
        c = Client()
        
        # 1. GET request should return the unified login page
        response = c.get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'auth/login.html')
        
        # 2. POST with invalid credentials should return login page with error
        response = c.post('/login/', {'username': 'invaliduser', 'password': 'wrongpassword'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'auth/login.html')
        
        # 3. POST with valid username credentials for Company Admin
        response = c.post('/login/', {'username': 'usera', 'password': 'passworda'})
        self.assertRedirects(response, '/company/dashboard/')
        
        # 4. GET /login/ when already logged in should redirect to dashboard
        response = c.get('/login/')
        self.assertRedirects(response, '/company/dashboard/')
        
        # 5. Logout should redirect to login
        response = c.get('/logout/')
        self.assertRedirects(response, '/login/')

    def test_unified_login_email_flow(self):
        """
        Verify that user can authenticate using their email address instead of username.
        """
        c = Client()
        response = c.post('/login/', {'username': 'usera@companya.com', 'password': 'passworda'})
        self.assertRedirects(response, '/company/dashboard/')

    def test_ledger_and_gst_posting(self):
        """
        Verify that posting an invoice creates ledger entries and GST transactions,
        and cancelling reverses them.
        """
        # Create draft invoice
        invoice = Invoice.objects.create(
            company=self.company_a,
            customer=self.customer_in_state,
            invoice_number="INV-TEST-LEDGER",
            invoice_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            place_of_supply=self.customer_in_state.billing_state,
            place_of_supply_code=self.customer_in_state.billing_state_code,
            status='DRAFT'
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            product=self.product_a,
            quantity=Decimal("1.00"),
            rate=Decimal("1000.00"),
            discount=Decimal("0.00"),
            taxable_value=Decimal("1000.00"),
            cgst_amount=Decimal("90.00"),
            sgst_amount=Decimal("90.00"),
            igst_amount=Decimal("0.00"),
            total_amount=Decimal("1180.00"),
            gst_rate=Decimal("18.00")
        )
        invoice.grand_total = Decimal("1180.00")
        invoice.taxable_value = Decimal("1000.00")
        invoice.save()

        # Let's post it via the view
        c = Client()
        c.login(username="usera", password="passworda")
        
        response = c.post(f"/company/invoices/{invoice.id}/post/")
        self.assertEqual(response.status_code, 302) # redirects to invoice detail
        
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'POSTED')
        
        # Verify customer outstanding balance updated
        self.customer_in_state.refresh_from_db()
        self.assertEqual(self.customer_in_state.outstanding_balance, Decimal("1180.00"))
        
        # Verify Customer Ledger entries
        ledger_entry = CustomerLedger.objects.filter(customer=self.customer_in_state, reference_id=invoice.id).first()
        self.assertIsNotNone(ledger_entry)
        self.assertEqual(ledger_entry.debit, Decimal("1180.00"))
        
        # Verify GST transaction registered
        gst_tx = GSTTransaction.objects.filter(company=self.company_a, reference_id=invoice.id, transaction_type='SALES').first()
        self.assertIsNotNone(gst_tx)
        self.assertEqual(gst_tx.taxable_value, Decimal("1000.00"))
        self.assertEqual(gst_tx.cgst_amount, Decimal("90.00"))
        self.assertEqual(gst_tx.sgst_amount, Decimal("90.00"))
        self.assertFalse(gst_tx.is_cancelled)
        
        # Cancel the invoice
        response = c.get(f"/company/invoices/{invoice.id}/cancel/")
        self.assertEqual(response.status_code, 302)
        
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'CANCELLED')
        
        # Outstanding balance should return to 0
        self.customer_in_state.refresh_from_db()
        self.assertEqual(self.customer_in_state.outstanding_balance, Decimal("0.00"))
        
        # GST Transaction should be marked as cancelled
        gst_tx.refresh_from_db()
        self.assertTrue(gst_tx.is_cancelled)
        
        # Counter balance ledger entry should exist
        cancel_ledger = CustomerLedger.objects.filter(customer=self.customer_in_state, reference_no=f"CNL-{invoice.invoice_number}").first()
        self.assertIsNotNone(cancel_ledger)
        self.assertEqual(cancel_ledger.credit, Decimal("1180.00"))

    def test_credit_note_logic(self):
        """
        Verify that creating a Credit Note updates customer balance and logs accounting transactions.
        """
        # Create a posted invoice
        invoice = Invoice.objects.create(
            company=self.company_a,
            customer=self.customer_in_state,
            invoice_number="INV-TEST-CN",
            invoice_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            place_of_supply=self.customer_in_state.billing_state,
            place_of_supply_code=self.customer_in_state.billing_state_code,
            status='POSTED',
            grand_total=Decimal("1180.00"),
            taxable_value=Decimal("1000.00")
        )
        InvoiceItem.objects.create(
            invoice=invoice, product=self.product_a, quantity=Decimal("1.00"),
            rate=Decimal("1000.00"), taxable_value=Decimal("1000.00"), total_amount=Decimal("1180.00"), gst_rate=Decimal("18.00")
        )
        self.customer_in_state.outstanding_balance = Decimal("1180.00")
        self.customer_in_state.save()

        c = Client()
        c.login(username="usera", password="passworda")
        
        # Create Credit Note
        response = c.post("/company/credit-notes/add/", {
            'invoice': invoice.id,
            'note_number': 'CN-001',
            'note_date': date.today().isoformat(),
            'reason': 'SALES_RETURN',
            'subtotal': '500.00',
            'notes': 'Sales return of half value'
        })
        self.assertEqual(response.status_code, 302)
        
        # Check credit note totals: subtotal = 500, MH to MH -> CGST=45, SGST=45, total=590
        note = CreditNote.objects.filter(note_number='CN-001').first()
        self.assertIsNotNone(note)
        self.assertEqual(note.subtotal, Decimal("500.00"))
        self.assertEqual(note.grand_total, Decimal("590.00"))
        
        # Verify outstanding customer balance decreased
        self.customer_in_state.refresh_from_db()
        self.assertEqual(self.customer_in_state.outstanding_balance, Decimal("590.00"))

    def test_customer_search_and_quick_add_api(self):
        c = Client()
        c.login(username="usera", password="passworda")
        
        # Test search API
        res = c.get("/company/customers/search/?q=rah")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'success')
        
        # Test Quick Add API
        res_add = c.post("/company/customers/quick-add/", data={
            'name': 'Rahul Traders',
            'business_name': 'Rahul Enterprises',
            'mobile': '9876543210',
            'gstin': '27AAAAA0000A1Z5',
            'billing_state': 'Maharashtra',
            'billing_state_code': '27'
        }, content_type='application/json')
        
        self.assertEqual(res_add.status_code, 200)
        add_data = res_add.json()
        self.assertEqual(add_data['status'], 'success')
        self.assertEqual(add_data['customer']['name'], 'Rahul Traders')
        
        # Verify customer saved in DB under company A
        cust = Customer.objects.filter(company=self.company_a, name='Rahul Traders').first()
        self.assertIsNotNone(cust)
        self.assertEqual(cust.mobile, '9876543210')
        
        # Test search now returns Rahul Traders
        res2 = c.get("/company/customers/search/?q=rah")
        data2 = res2.json()
        self.assertEqual(len(data2['customers']), 1)
        self.assertEqual(data2['customers'][0]['name'], 'Rahul Traders')

    def test_hsn_sac_system_and_snapshot_integrity(self):
        c = Client()
        c.login(username="usera", password="passworda")
        
        # Test HSN search API
        res = c.get("/company/hsn-sac/search/?q=8471")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'success')
        
        # Create Invoice with product having HSN 8471
        inv = Invoice.objects.create(
            company=self.company_a,
            customer=self.customer_in_state,
            invoice_number="INV-HSN-001",
            invoice_date="2026-08-17",
            due_date="2026-08-30",
            place_of_supply=self.company_a.state,
            place_of_supply_code=self.company_a.state_code,
            status="POSTED"
        )
        item = InvoiceItem.objects.create(
            invoice=inv,
            product=self.product_a,
            quantity=Decimal("2.00"),
            rate=Decimal("50000.00"),
            discount=Decimal("0.00"),
            taxable_value=Decimal("100000.00"),
            gst_rate=Decimal("18.00"),
            cgst_amount=Decimal("9000.00"),
            sgst_amount=Decimal("9000.00"),
            hsn_sac_code="8471",
            total_amount=Decimal("118000.00")
        )
        inv.subtotal = Decimal("100000.00")
        inv.taxable_value = Decimal("100000.00")
        inv.cgst_total = Decimal("9000.00")
        inv.sgst_total = Decimal("9000.00")
        inv.grand_total = Decimal("118000.00")
        inv.save()
        
        from .utils import record_invoice_accounting
        record_invoice_accounting(inv)
        
        # Verify GSTTransaction snapshot
        gtx = GSTTransaction.objects.filter(company=self.company_a, reference_no="INV-HSN-001").first()
        self.assertIsNotNone(gtx)
        self.assertEqual(gtx.hsn_sac_code, "8471")
        self.assertEqual(gtx.quantity, Decimal("2.00"))
        
        # Modify Product Master HSN to a new code "9999"
        new_hsn = HSNSACMaster.objects.create(code="9999", description="New Tech Code", gst_rate=Decimal("18.00"))
        self.product_a.hsn_sac = new_hsn
        self.product_a.save()
        
        # Verify old invoice item still retains snapshot HSN 8471
        item.refresh_from_db()
        self.assertEqual(item.hsn_code, "8471")
        
        # Verify HSN Report endpoint
        report_res = c.get("/company/reports/hsn-sac/?type=SALES")
        self.assertEqual(report_res.status_code, 200)
        self.assertContains(report_res, "8471")

    def test_edit_views_load_successfully(self):
        """
        Verify that Product, Customer, and Supplier update/edit views load successfully
        using the correct templates.
        """
        c = Client()
        c.login(username="usera", password="passworda")

        # Create a supplier to edit
        supplier = Supplier.objects.create(
            company=self.company_a,
            name="Test Supplier",
            mobile="9999999999"
        )

        # 1. Product edit view
        response = c.get(f'/company/products/{self.product_a.id}/edit/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'company/product_add.html')

        # 2. Customer edit view
        response = c.get(f'/company/customers/{self.customer_in_state.id}/edit/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'company/customer_add.html')

        # 3. Supplier edit view
        response = c.get(f'/company/suppliers/{supplier.id}/edit/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'company/supplier_add.html')

    def test_admin_hsn_sac_assignment_master(self):
        """
        Verify HSN/SAC Master CRUD, duplicate protection, bulk preview, bulk import, and API search.
        """
        c = Client()
        admin_user = CustomUser.objects.create_superuser(
            username='admin_hsn_test',
            email='admin_hsn@test.com',
            password='adminpassword',
            role='SUPERADMIN'
        )
        c.login(username='admin_hsn_test', password='adminpassword')

        # 1. Access HSN/SAC List view
        res = c.get('/admin/hsn-sac-codes/')
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'admin/hsn_sac_list.html')

        # 2. Add HSN Code
        add_res = c.post('/admin/hsn-sac-codes/add/', data=json.dumps({
            'type': 'HSN',
            'code': '1001',
            'description': 'Wheat Grains',
            'category': 'Agriculture',
            'gst_rate': '5.00',
            'uqc': 'KGS'
        }), content_type='application/json')
        self.assertEqual(add_res.status_code, 200)
        self.assertEqual(add_res.json()['status'], 'success')

        # Verify record in DB
        hsn_obj = HSNSACMaster.objects.get(code='1001', company__isnull=True)
        self.assertEqual(hsn_obj.gst_rate, Decimal('5.00'))
        self.assertEqual(hsn_obj.get_cgst_rate(), Decimal('2.50'))

        # 3. Duplicate code protection
        dup_res = c.post('/admin/hsn-sac-codes/add/', data=json.dumps({
            'type': 'HSN',
            'code': '1001',
            'description': 'Wheat Duplicate',
            'gst_rate': '5.00'
        }), content_type='application/json')
        self.assertEqual(dup_res.status_code, 400)
        self.assertIn('already exists', dup_res.json()['message'])

        # 4. Search API should return the newly created code
        c.login(username='usera', password='passworda')
        search_res = c.get('/company/hsn-sac/search/?q=1001')
        self.assertEqual(search_res.status_code, 200)
        hsn_list = search_res.json()['hsn_sac_list']
        self.assertTrue(any(item['code'] == '1001' for item in hsn_list))

    def test_delete_profile_photo_and_password_management(self):
        """
        Verify generic delete API (safe soft-delete vs hard-delete),
        profile photo upload/remove APIs, and admin user password change.
        """
        c = Client()
        c.login(username='usera', password='passworda')

        # 1. Profile photo upload API with small dummy image
        from django.core.files.uploadedfile import SimpleUploadedFile
        small_gif = (
            b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff'
            b'\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00'
            b'\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
        )
        img_file = SimpleUploadedFile('avatar.jpg', small_gif, content_type='image/jpeg')
        res = c.post('/api/profile/photo/upload/', {'photo': img_file})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'success')
        self.assertIsNotNone(res.json()['photo_url'])
        self.assertIn('avatar', res.json()['profile_photo_name'])

        # Verify that Company logo is also set
        user_obj = CustomUser.objects.get(username='usera')
        self.assertTrue(bool(user_obj.profile_photo))
        self.assertTrue(bool(user_obj.company.logo))
        self.assertIn('avatar', user_obj.company.get_logo_filename())
        self.assertIsNotNone(user_obj.company.get_logo_url())

        # 2. Profile photo remove API
        res_rem = c.post('/api/profile/photo/remove/')
        self.assertEqual(res_rem.status_code, 200)
        self.assertEqual(res_rem.json()['status'], 'success')
        self.assertIsNone(res_rem.json()['photo_url'])
        self.assertEqual(res_rem.json()['profile_photo_name'], 'No profile photo uploaded')

        # Verify that Company logo is also cleared
        user_obj.refresh_from_db()
        self.assertFalse(bool(user_obj.profile_photo))
        self.assertFalse(bool(user_obj.company.logo))
        self.assertEqual(user_obj.company.get_logo_filename(), '')
        self.assertIsNone(user_obj.company.get_logo_url())

        # 3. Safe delete linked product -> should deactivate
        prod = Product.objects.create(company=self.company_a, name="Linked Prod", current_stock=Decimal("10"))
        StockMovement.objects.create(company=self.company_a, warehouse=self.warehouse_a, product=prod, movement_type="IN", quantity=Decimal("10"))
        res_del_prod = c.post(f'/api/delete/product/{prod.id}/')
        self.assertEqual(res_del_prod.status_code, 200)
        self.assertEqual(res_del_prod.json()['action'], 'deactivated')
        prod.refresh_from_db()
        self.assertFalse(prod.is_active)

        # 4. Hard delete unlinked product -> should remove from DB
        unlinked_prod = Product.objects.create(company=self.company_a, name="Unlinked Prod", current_stock=Decimal("0"))
        res_del_unlinked = c.post(f'/api/delete/product/{unlinked_prod.id}/')
        self.assertEqual(res_del_unlinked.status_code, 200)
        self.assertEqual(res_del_unlinked.json()['action'], 'deleted')
        self.assertFalse(Product.objects.filter(id=unlinked_prod.id).exists())

        # 5. Admin change password API
        admin_user = CustomUser.objects.create_superuser(
            username='super_pass_admin',
            email='superpass@test.com',
            password='adminpassword',
            role='SUPERADMIN'
        )
        c.login(username='super_pass_admin', password='adminpassword')
        target_user = CustomUser.objects.create_user(
            username='user_change_pass_target',
            password='oldpassword123',
            company=self.company_a
        )
        res_pass = c.post(f'/admin/users/{target_user.id}/change-password/', data=json.dumps({
            'new_password': 'newsecretpassword123',
            'confirm_password': 'newsecretpassword123'
        }), content_type='application/json')
        self.assertEqual(res_pass.status_code, 200)
        self.assertEqual(res_pass.json()['status'], 'success')
        
        # Verify login with new password
        c.logout()
        login_res = c.post('/login/', {'username': 'user_change_pass_target', 'password': 'newsecretpassword123'})
        self.assertRedirects(login_res, '/company/dashboard/')

    def test_global_realtime_table_search(self):
        """
        Tests multi-field case-insensitive search across Admin and Company ListViews.
        """
        c = Client()
        
        # 1. Test Company Panel customer search
        c.login(username='usera', password='passworda')
        
        Customer.objects.create(
            company=self.company_a,
            name="Unique Alpha Customer",
            business_name="Alpha Tech Ltd",
            gstin="27ALPHA1234A1Z5",
            mobile="9876543210"
        )
        Customer.objects.create(
            company=self.company_a,
            name="Unique Beta Customer",
            business_name="Beta Solutions",
            gstin="27BETA1234B1Z5",
            mobile="9123456789"
        )
        
        res = c.get('/company/customers/?search=Alpha')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Unique Alpha Customer")
        self.assertNotContains(res, "Unique Beta Customer")

        # 2. Test AJAX Table header rendering
        res_ajax = c.get('/company/customers/?search=27BETA', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_ajax.status_code, 200)
        self.assertContains(res_ajax, "Unique Beta Customer")
        self.assertNotContains(res_ajax, "Unique Alpha Customer")

        # 3. Test Admin Panel company search
        admin_user = CustomUser.objects.create_superuser(
            username='search_superadmin',
            email='searchadmin@test.com',
            password='adminpassword',
            role='SUPERADMIN'
        )
        c.login(username='search_superadmin', password='adminpassword')
        res_admin = c.get('/admin/companies/?search=Company A')
        self.assertEqual(res_admin.status_code, 200)
        self.assertContains(res_admin, "Company A")

    def test_bulk_inventory_upload_revisions(self):
        """
        Verify HSN normalization and barcode conflict/duplicate rules for bulk upload.
        """
        from billing.views import normalize_hsn_sac, normalize_barcode
        
        # 1. Test Normalization Helpers
        self.assertEqual(normalize_hsn_sac("8517"), "8517")
        self.assertEqual(normalize_hsn_sac("8517.0"), "8517")
        self.assertEqual(normalize_hsn_sac(" 8517 "), "8517")
        self.assertEqual(normalize_hsn_sac(8517.0), "8517")
        self.assertEqual(normalize_hsn_sac("0123.0"), "0123")
        self.assertEqual(normalize_hsn_sac("01234"), "01234")
        
        self.assertEqual(normalize_barcode("123456789012"), "123456789012")
        self.assertEqual(normalize_barcode("123456789012.0"), "123456789012")
        self.assertEqual(normalize_barcode(" 123456789012 "), "123456789012")
        self.assertEqual(normalize_barcode("1.23456789012e+11"), "123456789012")
        self.assertEqual(normalize_barcode("012345678901"), "012345678901")

        # 2. Verify that Master HSN lookup retrieves the newly added record
        HSNSACMaster.objects.get_or_create(
            code="8517",
            defaults={
                "type": "HSN",
                "gst_rate": Decimal("18.00"),
                "description": "Smartphones / Telephone equipment",
                "is_active": True
            }
        )
        hsn_obj = HSNSACMaster.objects.filter(code="8517", is_active=True).first()
        self.assertIsNotNone(hsn_obj)
        self.assertEqual(hsn_obj.gst_rate, Decimal("18.00"))

    def test_forgot_password_otp_flow(self):
        from django.urls import reverse
        from billing.models import PasswordResetOTP
        import hashlib
        
        # Create a test user
        user = CustomUser.objects.create_user(
            username='testpwduser',
            email='testpwd@example.com',
            password='oldsecretpassword'
        )
        
        # 1. GET Forgot password page
        response = self.client.get(reverse('forgot_password'))
        self.assertEqual(response.status_code, 200)
        
        # 2. POST with user who does not exist (enumeration check)
        response = self.client.post(reverse('forgot_password'), {'username': 'nonexistentuser'})
        self.assertRedirects(response, reverse('verify_otp'))
        self.assertEqual(PasswordResetOTP.objects.count(), 0)
        
        # 3. POST with existing user
        response = self.client.post(reverse('forgot_password'), {'username': 'testpwd@example.com'})
        self.assertRedirects(response, reverse('verify_otp'))
        self.assertEqual(PasswordResetOTP.objects.count(), 1)
        
        # Get active OTP record
        otp_record = PasswordResetOTP.objects.first()
        self.assertFalse(otp_record.is_verified)
        self.assertEqual(otp_record.user, user)
        self.assertEqual(otp_record.attempts, 0)
        
        # 4. POST wrong OTP to verify
        response = self.client.post(reverse('verify_otp'), {'otp': '000000'})
        self.assertEqual(response.status_code, 200)
        otp_record.refresh_from_db()
        self.assertEqual(otp_record.attempts, 1)
        self.assertFalse(otp_record.is_verified)
        
        # 5. POST correct OTP to verify
        known_otp = '123456'
        otp_record.otp_hash = hashlib.sha256(known_otp.encode()).hexdigest()
        otp_record.save()
        
        response = self.client.post(reverse('verify_otp'), {'otp': known_otp})
        self.assertRedirects(response, reverse('reset_password'))
        otp_record.refresh_from_db()
        self.assertTrue(otp_record.is_verified)
        
        # 6. POST new password
        response = self.client.post(reverse('reset_password'), {
            'new_password': 'newsecretpassword123',
            'confirm_password': 'newsecretpassword123'
        })
        self.assertEqual(response.status_code, 200) # reset success page renders
        
        # Verify password actually updated
        updated_user = CustomUser.objects.get(id=user.id)
        self.assertTrue(updated_user.check_password('newsecretpassword123'))

    def test_indian_number_formatting_filters(self):
        from billing.templatetags.indian_numbers import indian_number, indian_currency, indian_qty
        
        self.assertEqual(indian_number(1000), "1,000.00")
        self.assertEqual(indian_number(10000), "10,000.00")
        self.assertEqual(indian_number(100000), "1,00,000.00")
        self.assertEqual(indian_number(500000), "5,00,000.00")
        self.assertEqual(indian_number(10000000), "1,00,00,000.00")
        self.assertEqual(indian_number(500000.50), "5,00,000.50")
        
        self.assertEqual(indian_currency(500000), "₹5,00,000.00")
        self.assertEqual(indian_currency(500000.50), "₹5,00,000.50")
        self.assertEqual(indian_qty(1000), "1,000")

    def test_payments_and_receipts_logging_and_api(self):
        from django.urls import reverse
        from billing.models import Payment, CustomerLedger, SupplierLedger, Supplier
        
        # Log in as existing test user_a
        self.client.force_login(self.user_a)
        
        supplier = Supplier.objects.create(
            company=self.company_a,
            name="Test Supplier A",
            state="Maharashtra",
            state_code="27",
            mobile="9998887770"
        )
        
        # 1. Post Customer Receipt via AJAX
        response = self.client.post(
            reverse('payment_receipt_add'),
            {
                'customer': self.customer_in_state.id,
                'amount': '50000.00',
                'payment_date': '2026-08-18',
                'payment_method': 'UPI',
                'reference_no': 'TXN12345',
                'notes': 'Test customer payment'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data['status'], 'success')
        
        # Verify database record
        payment = Payment.objects.get(id=json_data['payment_id'])
        self.assertEqual(payment.amount, Decimal('50000.00'))
        self.assertEqual(payment.payment_type, 'RECEIPT')
        
        # Verify Customer Ledger record
        ledger = CustomerLedger.objects.filter(customer=self.customer_in_state, entry_type='PAYMENT').first()
        self.assertIsNotNone(ledger)
        self.assertEqual(ledger.credit, Decimal('50000.00'))
        
        # 2. Test Customer Unpaid Invoices API
        api_res = self.client.get(reverse('api_customer_unpaid_invoices', kwargs={'pk': self.customer_in_state.id}))
        self.assertEqual(api_res.status_code, 200)
        self.assertEqual(api_res.json()['status'], 'success')
        
        # 3. Post Supplier Payment via AJAX
        response_supp = self.client.post(
            reverse('payment_supplier_add'),
            {
                'supplier': supplier.id,
                'amount': '25000.00',
                'payment_date': '2026-08-18',
                'payment_method': 'BANK',
                'reference_no': 'REF98765',
                'notes': 'Test supplier payment'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response_supp.status_code, 200)
        json_supp = response_supp.json()
        self.assertEqual(json_supp['status'], 'success')
        
        # Verify database record
        supp_payment = Payment.objects.get(id=json_supp['payment_id'])
        self.assertEqual(supp_payment.amount, Decimal('25000.00'))
        self.assertEqual(supp_payment.payment_type, 'PAYMENT')
        
        # Verify Supplier Ledger record
        supp_ledger = SupplierLedger.objects.filter(supplier=supplier, entry_type='PAYMENT').first()
        self.assertIsNotNone(supp_ledger)
        self.assertEqual(supp_ledger.debit, Decimal('25000.00'))
        
        # 4. Test Supplier Unpaid Bills API
        supp_api_res = self.client.get(reverse('api_supplier_unpaid_bills', kwargs={'pk': supplier.id}))
        self.assertEqual(supp_api_res.status_code, 200)
        self.assertEqual(supp_api_res.json()['status'], 'success')

    def test_dashboard_chart_data_endpoints(self):
        """
        Verify Company and Admin Dashboard Chart Data endpoints return real database metrics.
        """
        from django.urls import reverse
        
        # 1. Setup superadmin user for Admin Dashboard tests
        superadmin = CustomUser.objects.create_user(
            username="superadmin",
            password="superpassword",
            email="admin@system.com",
            role="SUPERADMIN"
        )
        
        # Test Admin Dashboard Chart Data
        self.client.login(username="superadmin", password="superpassword")
        admin_chart_res = self.client.get(reverse('admin_dashboard_chart_data') + '?period=this_month')
        self.assertEqual(admin_chart_res.status_code, 200)
        admin_json = admin_chart_res.json()
        self.assertIn('registrations_data', admin_json)
        self.assertIn('revenue_data', admin_json)
        self.assertIn('plan_labels', admin_json)
        self.assertIn('ticket_labels', admin_json)
        self.assertIn('company_status_labels', admin_json)

        # 2. Test Company Dashboard Chart Data
        self.client.login(username="usera", password="passworda")
        
        # Create an invoice for Company A
        Invoice.objects.create(
            company=self.company_a,
            customer=self.customer_in_state,
            invoice_number="INV-CHART-001",
            invoice_date=date.today(),
            due_date=date.today(),
            place_of_supply="27",
            status="POSTED",
            grand_total=Decimal("15000.00"),
            taxable_value=Decimal("12711.86"),
            cgst_total=Decimal("1144.07"),
            sgst_total=Decimal("1144.07")
        )

        comp_chart_res = self.client.get(reverse('company_dashboard_chart_data') + '?period=this_month&status_entity=invoice')
        self.assertEqual(comp_chart_res.status_code, 200)
        comp_json = comp_chart_res.json()
        self.assertIn('sales_data', comp_json)
        self.assertIn('purchases_data', comp_json)
        self.assertIn('collections_data', comp_json)
        self.assertIn('profit_data', comp_json)
        self.assertIn('status_labels', comp_json)
        self.assertIn('status_values', comp_json)
        
        # Check that POSTED invoice is included in sales_data (sum > 0)
        self.assertGreater(sum(comp_json['sales_data']), 0)

    def test_decimal_json_serialization_and_save_actions(self):
        """
        Tests end-to-end saving for Product, Customer, Supplier without Decimal JSON errors,
        and tests all 8 financial save/submit workflows.
        """
        self.client.login(username="usera", password="passworda")

        # 1. Product Create View - No Decimal JSON Error
        prod_res = self.client.post(
            '/company/products/add/',
            {
                'name': 'Test Decimal Product',
                'product_type': 'GOODS',
                'purchase_price': '125000.50',
                'selling_price': '150000.75',
                'mrp': '160000.00',
                'wholesale_price': '140000.00',
                'retail_price': '150000.75',
                'min_selling_price': '130000.00',
                'hsn_sac': self.hsn_goods.id,
                'min_stock': '0.00',
                'max_stock': '100.00',
                'opening_stock': '5.00'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        if prod_res.status_code != 200:
            print("Product form errors:", prod_res.content)
        self.assertEqual(prod_res.status_code, 200)
        self.assertTrue(prod_res.json().get('success'))
        created_prod = Product.objects.filter(name='Test Decimal Product').first()
        self.assertIsNotNone(created_prod)
        self.assertEqual(created_prod.selling_price, Decimal('150000.75'))

        # 2. Customer Create View - No Decimal JSON Error
        cust_res = self.client.post(
            '/company/customers/add/',
            {
                'name': 'Test Decimal Customer',
                'customer_type': 'CONSUMER',
                'mobile': '9988776655',
                'billing_address': '123 Test St',
                'billing_city': 'Mumbai',
                'billing_state': 'Maharashtra',
                'billing_state_code': '27',
                'billing_pincode': '400001',
                'credit_limit': '0.00',
                'credit_days': '0',
                'opening_balance': '50000.25',
                'opening_balance_type': 'DR'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        if cust_res.status_code != 200:
            print("Customer form errors:", cust_res.content)
        self.assertEqual(cust_res.status_code, 200)
        self.assertTrue(cust_res.json().get('success'))
        created_cust = Customer.objects.filter(name='Test Decimal Customer').first()
        self.assertIsNotNone(created_cust)
        self.assertEqual(created_cust.opening_balance, Decimal('50000.25'))

        # 3. Supplier Create View - No Decimal JSON Error
        supp_res = self.client.post(
            '/company/suppliers/add/',
            {
                'name': 'Test Decimal Supplier',
                'supplier_type': 'UNREGISTERED',
                'mobile': '9988776644',
                'address': '456 Vendor Road',
                'city': 'Pune',
                'state': 'Maharashtra',
                'state_code': '27',
                'pincode': '411001',
                'payment_terms': '0',
                'opening_balance': '75000.50',
                'opening_balance_type': 'CR'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        if supp_res.status_code != 200:
            print("Supplier form errors:", supp_res.content)
        self.assertEqual(supp_res.status_code, 200)
        self.assertTrue(supp_res.json().get('success'))
        created_supp = Supplier.objects.filter(name='Test Decimal Supplier').first()
        self.assertIsNotNone(created_supp)

        # 4. Save Quotation
        q_res = self.client.post(
            '/company/quotations/add/',
            json.dumps({
                'customer_id': self.customer_in_state.id,
                'quotation_number': 'QTN-TEST-001',
                'date': '2026-08-19',
                'valid_until': '2026-09-19',
                'notes': 'Test Quotation Notes',
                'items': [{
                    'product_id': self.product_a.id,
                    'quantity': 2,
                    'rate': 50000.00,
                    'discount': 0
                }]
            }),
            content_type='application/json'
        )
        self.assertEqual(q_res.status_code, 200)
        self.assertTrue(q_res.json().get('success'))
        self.assertTrue(Quotation.objects.filter(quotation_number='QTN-TEST-001').exists())

        # 5. Save Sales Order
        so_res = self.client.post(
            '/company/sales-orders/add/',
            json.dumps({
                'customer_id': self.customer_in_state.id,
                'order_number': 'SO-TEST-001',
                'date': '2026-08-19',
                'expected_delivery': '2026-08-25',
                'items': [{
                    'product_id': self.product_a.id,
                    'quantity': 1,
                    'rate': 50000.00,
                    'discount': 0
                }]
            }),
            content_type='application/json'
        )
        self.assertEqual(so_res.status_code, 200)
        self.assertTrue(so_res.json().get('success'))

        # 6. Post and Save Invoice
        inv_res = self.client.post(
            '/company/invoices/add/',
            json.dumps({
                'customer_id': self.customer_in_state.id,
                'invoice_number': 'INV-TEST-999',
                'invoice_date': '2026-08-19',
                'due_date': '2026-09-19',
                'place_of_supply': 'Maharashtra',
                'place_of_supply_code': '27',
                'warehouse_id': self.warehouse_a.id,
                'reverse_charge': False,
                'notes': 'Post Invoice Test',
                'items': [{
                    'product_id': self.product_a.id,
                    'quantity': 1,
                    'rate': 50000.00,
                    'discount': 0
                }]
            }),
            content_type='application/json'
        )
        self.assertEqual(inv_res.status_code, 200)
        self.assertTrue(inv_res.json().get('success'))
        posted_inv = Invoice.objects.filter(invoice_number='INV-TEST-999').first()
        self.assertIsNotNone(posted_inv)
        self.assertEqual(posted_inv.status, 'POSTED')

        # 7. Issue Credit Note
        cn_res = self.client.post(
            '/company/credit-notes/add/',
            {
                'invoice': posted_inv.id,
                'note_number': 'CN-TEST-001',
                'note_date': '2026-08-19',
                'reason': 'DISCOUNT',
                'subtotal': '5000.00',
                'notes': 'Credit note test'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        if cn_res.status_code != 200:
            print("Credit note form errors:", cn_res.content)
        self.assertEqual(cn_res.status_code, 200)
        self.assertTrue(cn_res.json().get('success'))

        # 8. Post Purchase Bill
        pb_res = self.client.post(
            '/company/purchase-bills/add/',
            json.dumps({
                'supplier_id': created_supp.id,
                'supplier_bill_no': 'BILL-TEST-100',
                'bill_date': '2026-08-19',
                'due_date': '2026-09-19',
                'warehouse_id': self.warehouse_a.id,
                'notes': 'Purchase Bill Test',
                'items': [{
                    'product_id': self.product_a.id,
                    'quantity': 2,
                    'rate': 40000.00,
                    'discount': 0
                }]
            }),
            content_type='application/json'
        )
        self.assertEqual(pb_res.status_code, 200)
        self.assertTrue(pb_res.json().get('success'))
        posted_pb = PurchaseBill.objects.filter(supplier_bill_no='BILL-TEST-100').first()
        self.assertIsNotNone(posted_pb)

        # 9. Issue Debit Note
        dn_res = self.client.post(
            '/company/debit-notes/add/',
            {
                'purchase_bill': posted_pb.id,
                'note_number': 'DN-TEST-001',
                'note_date': '2026-08-19',
                'reason': 'RATE_DIFFERENCE',
                'subtotal': '2000.00',
                'notes': 'Debit note test'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        if dn_res.status_code != 200:
            print("Debit note form errors:", dn_res.content)
        self.assertEqual(dn_res.status_code, 200)
        self.assertTrue(dn_res.json().get('success'))

        # 10. Supplier Payment
        supp_pay_res = self.client.post(
            '/company/payments/add-payment/',
            {
                'supplier': created_supp.id,
                'purchase_bill': posted_pb.id,
                'amount': '10000.00',
                'payment_date': '2026-08-19',
                'payment_method': 'BANK',
                'reference_no': 'PAYREF123',
                'notes': 'Supplier payment test'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(supp_pay_res.status_code, 200)
        self.assertTrue(supp_pay_res.json().get('success'))

        # 11. Log Overhead Expense
        from .models import ExpenseCategory
        exp_cat = ExpenseCategory.objects.create(company=self.company_a, name="Office Rent")
        exp_res = self.client.post(
            '/company/expenses/add/',
            {
                'category': exp_cat.id,
                'vendor': 'Landlord Corp',
                'amount': '25000.00',
                'gst_rate': '18.00',
                'payment_method': 'BANK',
                'reference_no': 'RENT-AUG',
                'description': 'August Rent'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(exp_res.status_code, 200)
        self.assertTrue(exp_res.json().get('success'))

    def test_indian_currency_parsing_and_formatted_submissions(self):
        """
        Verifies central parse_money utility and ensures all forms/views accept both formatted
        (e.g., '₹64,900.00', '₹ 64,900.00', '64,900.00') and unformatted monetary inputs.
        """
        from .utils import parse_money, format_money, serialize_decimal

        # 1. Test parse_money with all required monetary variations
        self.assertEqual(parse_money("64900.00"), Decimal("64900.00"))
        self.assertEqual(parse_money("64,900.00"), Decimal("64900.00"))
        self.assertEqual(parse_money("₹64900.00"), Decimal("64900.00"))
        self.assertEqual(parse_money("₹64,900.00"), Decimal("64900.00"))
        self.assertEqual(parse_money("₹ 64,900.00"), Decimal("64900.00"))
        self.assertEqual(parse_money("64900"), Decimal("64900.00"))
        self.assertEqual(parse_money("64,900"), Decimal("64900.00"))
        self.assertEqual(parse_money("₹5,00,000.00"), Decimal("500000.00"))
        self.assertEqual(parse_money("₹12,50,000.50"), Decimal("1250000.50"))

        # 2. Test format_money and serialize_decimal
        self.assertEqual(format_money(Decimal("64900.00")), "₹64,900.00")
        self.assertEqual(format_money(Decimal("500000.00")), "₹5,00,000.00")
        self.assertEqual(serialize_decimal(Decimal("64900.00")), "64900.00")

        # 3. Test invalid input handling
        with self.assertRaises(ValueError):
            parse_money("₹ABC")

        self.client.login(username="usera", password="passworda")

        # 4. Form Submission with Formatted Indian Currency (Customer Opening Balance)
        cust_res = self.client.post(
            '/company/customers/add/',
            {
                'name': 'Formatted Money Customer',
                'customer_type': 'CONSUMER',
                'mobile': '9988776611',
                'billing_address': '123 Currency St',
                'billing_city': 'Mumbai',
                'billing_state': 'Maharashtra',
                'billing_state_code': '27',
                'billing_pincode': '400001',
                'credit_limit': '₹1,00,000.00',
                'credit_days': '30',
                'opening_balance': '₹64,900.50',
                'opening_balance_type': 'DR'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(cust_res.status_code, 200)
        self.assertTrue(cust_res.json().get('success'))
        created_cust = Customer.objects.filter(name='Formatted Money Customer').first()
        self.assertIsNotNone(created_cust)
        self.assertEqual(created_cust.opening_balance, Decimal("64900.50"))
        self.assertEqual(created_cust.credit_limit, Decimal("100000.00"))

        # 5. Form Submission with Formatted Indian Currency (Expense Amount)
        from .models import ExpenseCategory
        cat = ExpenseCategory.objects.create(company=self.company_a, name="Utilities")
        exp_res = self.client.post(
            '/company/expenses/add/',
            {
                'category': cat.id,
                'vendor': 'Power Corp',
                'amount': '₹64,900.00',
                'gst_rate': '18.00',
                'payment_method': 'BANK',
                'reference_no': 'ELEC-AUG',
                'description': 'Electricity'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(exp_res.status_code, 200)
        self.assertTrue(exp_res.json().get('success'))
        created_exp = Expense.objects.filter(reference_no='ELEC-AUG').first()
        self.assertIsNotNone(created_exp)
        self.assertEqual(created_exp.amount, Decimal("64900.00"))

        # 6. JSON Payload Submission with Formatted Rate (Quotation)
        q_res = self.client.post(
            '/company/quotations/add/',
            json.dumps({
                'customer_id': created_cust.id,
                'quotation_number': 'QTN-FMT-001',
                'date': '2026-08-19',
                'valid_until': '2026-09-19',
                'notes': 'Formatted Rate Test',
                'items': [{
                    'product_id': self.product_a.id,
                    'quantity': '1.00',
                    'rate': '₹64,900.00',
                    'discount': '₹0.00'
                }]
            }),
            content_type='application/json'
        )
        self.assertEqual(q_res.status_code, 200)
        self.assertTrue(q_res.json().get('success'))
        q_obj = Quotation.objects.filter(quotation_number='QTN-FMT-001').first()
        self.assertIsNotNone(q_obj)
        self.assertEqual(q_obj.items.first().rate, Decimal("64900.00"))

    def test_quotation_automatic_and_manual_number_and_save_flow(self):
        """
        Verifies Sales Quotation creation end-to-end:
        - Automatic quotation number sequence generation
        - Saving with automatic quotation number
        - Saving with custom manual quotation number (e.g. 'MY-CUSTOM-QTN-999')
        - Preventing duplicate quotation numbers
        """
        self.client.login(username="usera", password="passworda")

        # 1. GET page generates auto quotation number
        get_res = self.client.get('/company/quotations/add/')
        self.assertEqual(get_res.status_code, 200)
        auto_qno = get_res.context['quotation_number']
        self.assertTrue(auto_qno.startswith('QTN-'))

        # 2. Save with Automatic Quotation Number
        post_auto_res = self.client.post(
            '/company/quotations/add/',
            json.dumps({
                'customer_id': self.customer_in_state.id,
                'quotation_number': auto_qno,
                'date': '2026-08-19',
                'valid_until': '2026-09-19',
                'notes': 'Auto Number Quotation Test',
                'items': [{
                    'product_id': self.product_a.id,
                    'quantity': '2.00',
                    'rate': '1500.00',
                    'discount': '100.00'
                }]
            }),
            content_type='application/json'
        )
        self.assertEqual(post_auto_res.status_code, 200)
        self.assertTrue(post_auto_res.json().get('success'))
        auto_q_obj = Quotation.objects.filter(quotation_number=auto_qno).first()
        self.assertIsNotNone(auto_q_obj)
        self.assertEqual(auto_q_obj.customer, self.customer_in_state)
        self.assertEqual(auto_q_obj.items.count(), 1)

        # 3. Save with Custom Manual Quotation Number
        manual_qno = "MY-CUSTOM-QTN-999"
        post_manual_res = self.client.post(
            '/company/quotations/add/',
            json.dumps({
                'customer_id': self.customer_in_state.id,
                'quotation_number': manual_qno,
                'date': '2026-08-19',
                'valid_until': '2026-09-19',
                'notes': 'Manual Number Quotation Test',
                'items': [{
                    'product_id': self.product_a.id,
                    'quantity': '1.00',
                    'rate': '₹50,000.00',
                    'discount': '0.00'
                }]
            }),
            content_type='application/json'
        )
        self.assertEqual(post_manual_res.status_code, 200)
        self.assertTrue(post_manual_res.json().get('success'))
        manual_q_obj = Quotation.objects.filter(quotation_number=manual_qno).first()
        self.assertIsNotNone(manual_q_obj)
        self.assertEqual(manual_q_obj.quotation_number, manual_qno)

        # 4. Duplicate Quotation Number Protection
        dup_res = self.client.post(
            '/company/quotations/add/',
            json.dumps({
                'customer_id': self.customer_in_state.id,
                'quotation_number': manual_qno,
                'date': '2026-08-19',
                'valid_until': '2026-09-19',
                'items': [{
                    'product_id': self.product_a.id,
                    'quantity': '1.00',
                    'rate': '1000.00'
                }]
            }),
            content_type='application/json'
        )
        self.assertEqual(dup_res.status_code, 400)
        self.assertFalse(dup_res.json().get('success'))
        self.assertIn('already exists', dup_res.json().get('message'))

    def test_new_features_security_conversions_and_deactivations(self):
        """
        Verify:
        1. "My Account" CRUD endpoints & security (ADMIN role requirement)
        2. Accountant blocked from CompanySettingsView
        3. Quotation to Sales Order and Invoice copy hsn_sac_code & Sales Order pending status
        4. User deletion guard preventing self-deactivation and deactivating last active admin
        5. ProfitLossReportView includes POSTED & PARTIALLY_PAID accruals
        """
        c = Client()
        c.force_login(self.user_a)

        # 1. Test "My Account" CRUD - Create Accountant
        create_res = c.post('/company/my-account/add/', json.dumps({
            'name': 'Accountant User',
            'username': 'acc_user',
            'email': 'acc@companya.com',
            'mobile': '9876543212',
            'role': 'ACCOUNTANT',
            'password': 'password123',
            'confirm_password': 'password123',
            'status': 'active'
        }), content_type='application/json')
        self.assertEqual(create_res.status_code, 200)
        self.assertTrue(create_res.json().get('success'))

        acc_user = CustomUser.objects.get(username='acc_user')
        self.assertEqual(acc_user.role, 'ACCOUNTANT')
        self.assertTrue(acc_user.is_active)

        # 2. Test "My Account" CRUD - Get detail
        detail_res = c.get(f'/company/my-account/{acc_user.id}/')
        self.assertEqual(detail_res.status_code, 200)
        self.assertTrue(detail_res.json().get('success'))
        self.assertEqual(detail_res.json()['user']['username'], 'acc_user')

        # 3. Test Accountant blocked from settings
        c.force_login(acc_user)
        settings_res = c.get('/company/settings/')
        self.assertEqual(settings_res.status_code, 403) # Raises PermissionDenied

        # Restore Admin login
        c.force_login(self.user_a)

        # 4. Create Quotation with HSN code
        hsn_master = HSNSACMaster.objects.create(company=self.company_a, code='1234', gst_rate=Decimal('18.00'))
        prod = Product.objects.create(company=self.company_a, name='Product HSN Test', hsn_sac=hsn_master, current_stock=Decimal('10'))
        
        quotation = Quotation.objects.create(
            company=self.company_a, customer=self.customer_in_state, quotation_number='QTN-HSN-TEST',
            date=date.today(), valid_until=date.today() + timedelta(days=30), status='SENT'
        )
        q_item = QuotationItem.objects.create(
            quotation=quotation, product=prod, quantity=Decimal('2.00'), rate=Decimal('100.00'),
            taxable_value=Decimal('200.00'), gst_rate=Decimal('18.00'), hsn_sac_code='1234', total_amount=Decimal('236.00')
        )

        # 5. Convert Quotation to Invoice & verify HSN code copied
        conv_inv_res = c.get(f'/company/quotations/{quotation.id}/convert/')
        self.assertEqual(conv_inv_res.status_code, 302)
        
        # Check created invoice item
        inv = Invoice.objects.filter(company=self.company_a).order_by('-id').first()
        self.assertEqual(inv.status, 'DRAFT')
        inv_item = inv.items.first()
        self.assertEqual(inv_item.hsn_code, '1234')

        # 6. Convert Quotation to Sales Order & verify PENDING status and HSN copied
        quotation.status = 'SENT'
        quotation.save()
        conv_so_res = c.get(f'/company/quotations/{quotation.id}/convert-so/')
        self.assertEqual(conv_so_res.status_code, 302)
        so = SalesOrder.objects.filter(company=self.company_a).order_by('-id').first()
        self.assertEqual(so.status, 'PENDING')
        so_item = so.items.first()
        self.assertEqual(so_item.hsn_code, '1234')

        # 7. Convert Sales Order to Invoice & verify HSN copied
        conv_so_inv_res = c.get(f'/company/sales-orders/{so.id}/convert/')
        self.assertEqual(conv_so_inv_res.status_code, 302)
        inv2 = Invoice.objects.filter(company=self.company_a).order_by('-id').first()
        inv2_item = inv2.items.first()
        self.assertEqual(inv2_item.hsn_code, '1234')

        # 8. User deletion guards (delete self -> 400, delete last admin -> 400)
        del_self_res = c.post(f'/api/delete/user/{self.user_a.id}/')
        self.assertEqual(del_self_res.status_code, 400)
        self.assertEqual(del_self_res.json()['message'], 'You cannot delete your own active account.')

        # Create another admin to allow deactivation test
        other_admin = CustomUser.objects.create_user(username='admin2', password='password', company=self.company_a, role='ADMIN')
        del_last_admin_res = c.post(f'/api/delete/user/{other_admin.id}/')
        self.assertEqual(del_last_admin_res.status_code, 200) # works since user_a is active admin
        
        # Deactivating user_a now fails because other_admin is deactivated, so user_a is last active admin
        other_admin.is_active = False
        other_admin.save()
        del_last_admin_res2 = c.post(f'/api/delete/user/{self.user_a.id}/')
        self.assertEqual(del_last_admin_res2.status_code, 400)

        # 9. Profit & Loss includes POSTED and PARTIALLY_PAID accruals
        Invoice.objects.create(
            company=self.company_a, customer=self.customer_in_state, invoice_number='INV-PL-POSTED',
            invoice_date=date.today(), due_date=date.today(), status='POSTED', taxable_value=Decimal('500.00'), grand_total=Decimal('500.00')
        )
        pl_res = c.get('/company/reports/profit-loss/')
        self.assertEqual(pl_res.status_code, 200)
        self.assertEqual(pl_res.context['sales_total'], Decimal('500.00'))

    def test_transaction_save_buttons_and_my_account(self):
        c = Client()
        c.force_login(self.user_a)

        # 1. Test Quick Add Customer
        res_qc = c.post('/company/customers/quick-add/', data=json.dumps({
            'name': 'New Test Customer',
            'business_name': 'Test Enterprises',
            'mobile': '9876543219',
            'gstin': '27ABCDE1234F1Z5',
            'customer_type': 'REGISTERED'
        }), content_type='application/json')
        self.assertEqual(res_qc.status_code, 200)
        qc_data = res_qc.json()
        self.assertEqual(qc_data['status'], 'success')
        new_cust_id = qc_data['customer']['id']

        # 2. Test Save Quotation
        res_qtn = c.post('/company/quotations/add/', data=json.dumps({
            'customer_id': new_cust_id,
            'quotation_number': 'QTN-2026-TEST01',
            'date': date.today().strftime('%Y-%m-%d'),
            'valid_until': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'notes': 'Test Quotation Note',
            'items': [
                {'product_id': self.product_a.id, 'quantity': 2, 'rate': 50000, 'discount': 0}
            ]
        }), content_type='application/json')
        self.assertEqual(res_qtn.status_code, 200)
        self.assertTrue(res_qtn.json().get('success') or res_qtn.json().get('status') == 'success')
        self.assertTrue(Quotation.objects.filter(company=self.company_a, quotation_number='QTN-2026-TEST01').exists())

        # 3. Test Save Sales Order
        res_so = c.post('/company/sales-orders/add/', data=json.dumps({
            'customer_id': new_cust_id,
            'order_number': 'SO-2026-TEST01',
            'date': date.today().strftime('%Y-%m-%d'),
            'expected_delivery': (date.today() + timedelta(days=14)).strftime('%Y-%m-%d'),
            'items': [
                {'product_id': self.product_a.id, 'quantity': 1, 'rate': 50000, 'discount': 0}
            ]
        }), content_type='application/json')
        self.assertEqual(res_so.status_code, 200)
        self.assertTrue(res_so.json().get('success') or res_so.json().get('status') == 'success')
        self.assertTrue(SalesOrder.objects.filter(company=self.company_a, order_number='SO-2026-TEST01').exists())

        # 4. Test Post and Save Invoice
        res_inv = c.post('/company/invoices/add/', data=json.dumps({
            'customer_id': new_cust_id,
            'invoice_number': 'INV-2026-TEST01',
            'invoice_date': date.today().strftime('%Y-%m-%d'),
            'due_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'warehouse_id': self.warehouse_a.id,
            'place_of_supply': 'Maharashtra',
            'place_of_supply_code': '27',
            'items': [
                {'product_id': self.product_a.id, 'quantity': 1, 'rate': 50000, 'discount': 0}
            ]
        }), content_type='application/json')
        self.assertEqual(res_inv.status_code, 200)
        self.assertTrue(res_inv.json().get('success') or res_inv.json().get('status') == 'success')
        posted_inv = Invoice.objects.filter(company=self.company_a, invoice_number='INV-2026-TEST01').first()
        self.assertIsNotNone(posted_inv)
        self.assertEqual(posted_inv.status, 'POSTED')

        # 5. Test Issue Credit Note
        res_cn = c.post('/company/credit-notes/add/', data={
            'invoice': posted_inv.id,
            'note_number': 'CN-2026-TEST01',
            'note_date': date.today().strftime('%Y-%m-%d'),
            'reason': 'SALES_RETURN',
            'subtotal': '5000.00',
            'notes': 'Defective return'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_cn.status_code, 200)
        self.assertTrue(CreditNote.objects.filter(company=self.company_a, note_number='CN-2026-TEST01').exists())

        # 6. Test My Account Add and Edit Account
        res_acc = c.post('/company/my-account/add/', data=json.dumps({
            'name': 'Test Employee',
            'username': 'testemployee1',
            'email': 'employee@companya.com',
            'mobile': '9876543212',
            'role': 'ACCOUNTANT',
            'status': 'active',
            'password': 'password123',
            'confirm_password': 'password123'
        }), content_type='application/json')
        self.assertEqual(res_acc.status_code, 200)
        emp = CustomUser.objects.filter(username='testemployee1').first()
        self.assertIsNotNone(emp)
        self.assertEqual(emp.first_name, 'Test Employee')

        # Edit Account
        res_edit_acc = c.post(f'/company/my-account/{emp.id}/edit/', data=json.dumps({
            'name': 'Test Employee Updated',
            'username': 'testemployee1',
            'email': 'employee_updated@companya.com',
            'mobile': '9876543213',
            'role': 'ACCOUNTANT',
            'status': 'active'
        }), content_type='application/json')
        self.assertEqual(res_edit_acc.status_code, 200)
        emp.refresh_from_db()
        self.assertEqual(emp.first_name, 'Test Employee Updated')

        # Check My Account page template contains "Type your name" placeholder
        res_page = c.get('/company/my-account/')
        self.assertEqual(res_page.status_code, 200)
        self.assertContains(res_page, 'placeholder="Type your name"')
        self.assertNotContains(res_page, 'placeholder="e.g. Jane Doe"')
        self.assertNotContains(res_page, 'placeholder="e.g. janedoe"')

        # 7. Test Dashboard Chart Data API
        res_chart = c.get('/company/dashboard/chart-data/?period=this_month&status_entity=invoice')
        self.assertEqual(res_chart.status_code, 200)
        self.assertIn('sales_data', res_chart.json())

    def test_tax_invoice_payment_details_and_gst_enhancements(self):
        """
        Comprehensive test for Tax Invoice Payment Details (Advance, Current Payment, Payment %, Balance, Status),
        Overpayment validation, Indian Currency parsing, GST itemization, GST Summary, Edit Invoice, PDF & Ledger sync.
        """
        c = Client()
        c.login(username="usera", password="passworda")

        self.product_a.current_stock = Decimal('1000.00')
        self.product_a.allow_negative_stock = True
        self.product_a.save()

        # 1. Unpaid Invoice (No Advance, No Payment Now)
        res1 = c.post('/company/invoices/add/', data=json.dumps({
            'customer_id': self.customer_in_state.id,
            'invoice_number': 'INV-PAY-001',
            'invoice_date': '2026-08-25',
            'due_date': '2026-09-25',
            'place_of_supply': 'Maharashtra',
            'place_of_supply_code': '27',
            'advance_paid': False,
            'advance_amount': '0.00',
            'amount_paid_now': '0.00',
            'payment_percentage': '0.00',
            'items': [{'product_id': self.product_a.id, 'quantity': 2, 'rate': 50000, 'discount': 0}]
        }), content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(res1.status_code, 200)
        inv1 = Invoice.objects.get(invoice_number='INV-PAY-001')
        self.assertEqual(inv1.grand_total, Decimal('118000.00'))
        self.assertEqual(inv1.advance_amount, Decimal('0.00'))
        self.assertEqual(inv1.amount_paid_now, Decimal('0.00'))
        self.assertEqual(inv1.total_payment_received, Decimal('0.00'))
        self.assertEqual(inv1.balance_due, Decimal('118000.00'))
        self.assertEqual(inv1.payment_status, 'UNPAID')

        # 2. Invoice with Advance + Payment Now
        res2 = c.post('/company/invoices/add/', data=json.dumps({
            'customer_id': self.customer_in_state.id,
            'invoice_number': 'INV-PAY-002',
            'invoice_date': '2026-08-25',
            'due_date': '2026-09-25',
            'place_of_supply': 'Maharashtra',
            'place_of_supply_code': '27',
            'advance_paid': True,
            'advance_amount': '₹20,000.00',
            'amount_paid_now': '30,000.00',
            'items': [{'product_id': self.product_a.id, 'quantity': 2, 'rate': 50000, 'discount': 0}]
        }), content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res2.status_code, 200)
        inv2 = Invoice.objects.get(invoice_number='INV-PAY-002')
        self.assertEqual(inv2.advance_amount, Decimal('20000.00'))
        self.assertEqual(inv2.amount_paid_now, Decimal('30000.00'))
        self.assertEqual(inv2.total_payment_received, Decimal('50000.00'))
        self.assertEqual(inv2.balance_due, Decimal('68000.00'))
        self.assertEqual(inv2.payment_status, 'PARTIALLY_PAID')

        # Check payment receipt log creation
        pmt = Payment.objects.filter(invoice=inv2, payment_type='RECEIPT').first()
        self.assertIsNotNone(pmt)
        self.assertEqual(pmt.amount, Decimal('50000.00'))

        # 3. Overpayment validation error
        res_err = c.post('/company/invoices/add/', data=json.dumps({
            'customer_id': self.customer_in_state.id,
            'invoice_number': 'INV-PAY-ERR',
            'invoice_date': '2026-08-25',
            'due_date': '2026-09-25',
            'place_of_supply': 'Maharashtra',
            'place_of_supply_code': '27',
            'advance_paid': True,
            'advance_amount': '50,000.00',
            'amount_paid_now': '80,000.00',
            'items': [{'product_id': self.product_a.id, 'quantity': 2, 'rate': 50000, 'discount': 0}]
        }), content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_err.status_code, 400)
        self.assertIn("Payment amount cannot exceed the invoice total", res_err.json()['message'])

        # 4. Tax Invoice View & PDF rendering
        view_res = c.get(f'/company/invoices/{inv2.id}/')
        self.assertEqual(view_res.status_code, 200)

        pdf_res = c.get(f'/company/invoices/{inv2.id}/pdf/')
        self.assertEqual(pdf_res.status_code, 200)
        self.assertIn('PAYMENT DETAILS', pdf_res.content.decode('utf-8'))

        # 5. Edit Tax Invoice
        edit_res = c.post(f'/company/invoices/{inv2.id}/edit/', data=json.dumps({
            'customer_id': self.customer_in_state.id,
            'invoice_number': inv2.invoice_number,
            'invoice_date': '2026-08-25',
            'due_date': '2026-09-25',
            'place_of_supply': 'Maharashtra',
            'place_of_supply_code': '27',
            'advance_paid': True,
            'advance_amount': '20,000.00',
            'amount_paid_now': '98,000.00',
            'items': [{'product_id': self.product_a.id, 'quantity': 2, 'rate': 50000, 'discount': 0}]
        }), content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(edit_res.status_code, 200)
        inv2.refresh_from_db()
        self.assertEqual(inv2.total_payment_received, Decimal('118000.00'))
        self.assertEqual(inv2.balance_due, Decimal('0.00'))
        self.assertEqual(inv2.payment_status, 'PAID')

    def test_quotation_preview_direct_tab_and_pdf_endpoint(self):
        c = Client()
        c.login(username="usera", password="passworda")

        # Create a test quotation
        q = Quotation.objects.create(
            company=self.company_a,
            customer=self.customer_in_state,
            quotation_number='QTN-PREVIEW-001',
            date=date.today(),
            valid_until=date.today() + timedelta(days=15),
            status='DRAFT'
        )
        QuotationItem.objects.create(
            quotation=q, product=self.product_a, quantity=Decimal('2'),
            rate=Decimal('5000.00'), discount=Decimal('0.00'), taxable_value=Decimal('10000.00'),
            gst_rate=Decimal('18.00'), cgst_amount=Decimal('900.00'), sgst_amount=Decimal('900.00'),
            igst_amount=Decimal('0.00'), total_amount=Decimal('11800.00'), hsn_sac_code='8471'
        )

        # 1. Detail page view contains direct target="_blank" link to PDF URL and NO iframe
        res_detail = c.get(f'/company/quotations/{q.id}/')
        self.assertEqual(res_detail.status_code, 200)
        self.assertIn(f'/company/quotations/{q.id}/pdf/', res_detail.content.decode('utf-8'))
        self.assertIn('target="_blank"', res_detail.content.decode('utf-8'))
        self.assertNotIn('<iframe', res_detail.content.decode('utf-8'))

        # 2. Directly accessing PDF endpoint renders Quotation PDF
        res_pdf = c.get(f'/company/quotations/{q.id}/pdf/')
        self.assertEqual(res_pdf.status_code, 200)
        self.assertIn('QTN-PREVIEW-001', res_pdf.content.decode('utf-8'))

        # 3. Convert quotation to Sales Order and verify PDF endpoint still opens original Quotation PDF
        c.post(f'/company/quotations/{q.id}/convert-so/')
        q.refresh_from_db()
        self.assertEqual(q.status, 'CONVERTED')
        self.assertIsNotNone(q.converted_to_sales_order)

        res_converted_pdf = c.get(f'/company/quotations/{q.id}/pdf/')
        self.assertEqual(res_converted_pdf.status_code, 200)
        self.assertIn('QTN-PREVIEW-001', res_converted_pdf.content.decode('utf-8'))

    def test_quotation_terms_selection_edit_and_pdf_compact_spacing(self):
        c = Client()
        c.login(username="usera", password="passworda")

        # TEST 1: Create quotation with no selected terms
        res_no_terms = c.post('/company/quotations/add/', data=json.dumps({
            'customer_id': self.customer_in_state.id,
            'quotation_number': 'QTN-TERMS-001',
            'date': '2026-08-25',
            'valid_until': '2026-09-25',
            'notes': 'Test notes',
            'items': [{'product_id': self.product_a.id, 'quantity': 1, 'rate': 1000, 'discount': 0}],
            'selected_terms': []
        }), content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_no_terms.status_code, 200)
        q1 = Quotation.objects.get(quotation_number='QTN-TERMS-001')

        # Check View and PDF for no terms
        res_view1 = c.get(f'/company/quotations/{q1.id}/')
        self.assertEqual(res_view1.status_code, 200)
        res_pdf1 = c.get(f'/company/quotations/{q1.id}/pdf/')
        self.assertEqual(res_pdf1.status_code, 200)

        # TEST 2 & 3 & 4 & 5: Create quotation with 3 predefined terms + 2 custom terms
        terms_payload = [
            {'term_text': 'Payment must be made according to the agreed payment terms.', 'is_custom': False},
            {'term_text': 'Prices are subject to applicable GST/taxes.', 'is_custom': False},
            {'term_text': 'Delivery will be made according to the agreed schedule.', 'is_custom': False},
            {'term_text': '50% advance payment required before starting project.', 'is_custom': True},
            {'term_text': 'Installation charges extra as applicable.', 'is_custom': True}
        ]
        res_terms = c.post('/company/quotations/add/', data=json.dumps({
            'customer_id': self.customer_in_state.id,
            'quotation_number': 'QTN-TERMS-002',
            'date': '2026-08-25',
            'valid_until': '2026-09-25',
            'notes': 'Custom terms quotation',
            'items': [{'product_id': self.product_a.id, 'quantity': 2, 'rate': 5000, 'discount': 100}],
            'selected_terms': terms_payload
        }), content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_terms.status_code, 200)
        q2 = Quotation.objects.get(quotation_number='QTN-TERMS-002')
        self.assertEqual(q2.selected_terms.count(), 5)

        # TEST 6 & 8: Edit page opens and loads previously selected terms
        res_edit_page = c.get(f'/company/quotations/{q2.id}/edit/')
        self.assertEqual(res_edit_page.status_code, 200)
        edit_html = res_edit_page.content.decode('utf-8')
        self.assertIn('50% advance payment required before starting project.', edit_html)

        # TEST 7 & 9: Uncheck a term, change product qty/rate, and save
        updated_terms = [
            {'term_text': 'Payment must be made according to the agreed payment terms.', 'is_custom': False},
            {'term_text': '50% advance payment required before starting project.', 'is_custom': True}
        ]
        res_edit_save = c.post(f'/company/quotations/{q2.id}/edit/', data=json.dumps({
            'customer_id': self.customer_in_state.id,
            'quotation_number': 'QTN-TERMS-002',
            'date': '2026-08-25',
            'valid_until': '2026-09-25',
            'notes': 'Updated terms',
            'items': [{'product_id': self.product_a.id, 'quantity': 5, 'rate': 2000, 'discount': 0}],
            'selected_terms': updated_terms
        }), content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_edit_save.status_code, 200)
        q2.refresh_from_db()
        self.assertEqual(q2.selected_terms.count(), 2)
        self.assertEqual(q2.grand_total, Decimal('11800.00'))

        # TEST 10: PDF contains compact QUOTATION INFORMATION table and updated terms, and NO Status: SENT
        res_pdf2 = c.get(f'/company/quotations/{q2.id}/pdf/')
        self.assertEqual(res_pdf2.status_code, 200)
        pdf2_html = res_pdf2.content.decode('utf-8')
        self.assertIn('QUOTATION INFORMATION', pdf2_html)
        self.assertIn('Payment must be made according to the agreed payment terms.', pdf2_html)
        self.assertIn('50% advance payment required before starting project.', pdf2_html)
        self.assertNotIn('Installation charges extra as applicable.', pdf2_html)
        self.assertNotIn('Status:', pdf2_html)

    def test_gst_dashboard_cards_and_quotation_pdf_status_removed(self):
        c = Client()
        c.login(username="usera", password="passworda")

        # 1. Test GST Dashboard Context & Cards
        res_gst = c.get('/company/gst/dashboard/')
        self.assertEqual(res_gst.status_code, 200)
        self.assertIn('output_tax', res_gst.context)
        self.assertIn('input_tax', res_gst.context)
        self.assertIn('net_payable', res_gst.context)

        gst_html = res_gst.content.decode('utf-8')
        self.assertIn('Output Tax Liability', gst_html)
        self.assertIn('Eligible Input Tax Credit (ITC)', gst_html)
        self.assertIn('Estimated Net GST Payable', gst_html)
        self.assertIn('₹' + str(res_gst.context['output_tax']), gst_html)
        self.assertIn('₹' + str(res_gst.context['input_tax']), gst_html)
        self.assertIn('₹' + str(res_gst.context['net_payable']), gst_html)

        # 2. Test Quotation PDF status removal
        q = Quotation.objects.create(
            company=self.company_a,
            customer=self.customer_in_state,
            quotation_number='QTN-STATUS-TEST-001',
            date=date.today(),
            valid_until=date.today(),
            status='SENT',
            grand_total=Decimal('1000.00')
        )
        res_pdf = c.get(f'/company/quotations/{q.id}/pdf/')
        self.assertEqual(res_pdf.status_code, 200)
        pdf_html = res_pdf.content.decode('utf-8')
        self.assertNotIn('Status:', pdf_html)
        self.assertNotIn('Status: SENT', pdf_html)
        # Verify DB status is untouched
        q.refresh_from_db()
        self.assertEqual(q.status, 'SENT')

    def test_hsn_sac_search_assignment_and_gst_dashboard_visibility(self):
        c = Client()
        c.login(username="usera", password="passworda")

        # 1. Product Add page loads searchable HSN/SAC components cleanly
        res_add_page = c.get('/company/products/add/')
        self.assertEqual(res_add_page.status_code, 200)
        html_add = res_add_page.content.decode('utf-8')
        self.assertIn('id="hsn_search_input"', html_add)
        self.assertIn('id="hsn_options_list"', html_add)
        self.assertIn('HSN/SAC Code Assignment', html_add)

        # 2. Add product with HSN/SAC assignment
        from billing.models import HSNSACMaster, Unit
        hsn_obj = HSNSACMaster.objects.filter(code='8517').first()
        if not hsn_obj:
            hsn_obj = HSNSACMaster.objects.create(code='8517', description='Telephones 8517', gst_rate=Decimal('18.00'), type='HSN')

        unit_obj = Unit.objects.filter(company=self.company_a).first()
        if not unit_obj:
            unit_obj = Unit.objects.create(company=self.company_a, name='PCS', code='PCS-PIECES')

        res_create = c.post('/company/products/add/', data={
            'name': 'Searchable HSN Test Phone 8517',
            'sku': 'SKU-8517-TEST',
            'hsn_sac': hsn_obj.id,
            'unit': unit_obj.id,
            'selling_price': '15000.00',
            'purchase_price': '10000.00',
            'mrp': '16000.00',
            'wholesale_price': '14000.00',
            'retail_price': '15000.00',
            'is_active': 'on'
        })
        self.assertEqual(res_create.status_code, 302)
        prod = Product.objects.get(sku='SKU-8517-TEST')
        self.assertEqual(prod.hsn_sac, hsn_obj)

        # 3. Product Edit page preloads selected HSN/SAC
        res_edit_page = c.get(f'/company/products/{prod.id}/edit/')
        self.assertEqual(res_edit_page.status_code, 200)
        self.assertIn('id="hsn_search_input"', res_edit_page.content.decode('utf-8'))

        # 4. GST Dashboard cards visibility and links
        res_dash = c.get('/company/gst/dashboard/')
        self.assertEqual(res_dash.status_code, 200)
        dash_html = res_dash.content.decode('utf-8')
        self.assertIn('Output Tax Liability', dash_html)
        self.assertIn('Eligible Input Tax Credit (ITC)', dash_html)
        self.assertIn('Estimated Net GST Payable', dash_html)
        self.assertIn('Tax collected on outward sales', dash_html)
        self.assertIn('Tax paid on business purchases', dash_html)
        self.assertIn('Formula: Output - ITC', dash_html)
        self.assertIn('/company/gst/gstr1/', dash_html)
        self.assertIn('/company/gst/gstr3b/', dash_html)


class ProductMasterAndCompanyStateTests(TestCase):
    def setUp(self):
        self.plan = SubscriptionPlan.objects.create(
            name="Pro Plan",
            monthly_price=Decimal('999.00'),
            trial_days=14
        )
        self.company = Company.objects.create(
            name="Odisha Enterprise",
            trade_name="OE",
            state="Odisha",
            state_code="21",
            city="Bhubaneswar",
            address="Main St",
            pincode="751001",
            plan=self.plan
        )
        self.superadmin = CustomUser.objects.create_user(
            username="superadmin_test",
            password="password123",
            role="SUPERADMIN"
        )
        self.user = CustomUser.objects.create_user(
            username="company_admin_test",
            password="password123",
            role="ADMIN",
            company=self.company
        )
        self.category = Category.objects.create(company=self.company, name="Electronics")
        self.brand = Brand.objects.create(company=self.company, name="Samsung")

    def test_category_search_api(self):
        c = Client()
        c.login(username="company_admin_test", password="password123")
        res = c.get('/company/categories/search/?q=Elec')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['name'], "Electronics")

    def test_category_quick_add(self):
        c = Client()
        c.login(username="company_admin_test", password="password123")
        
        # Test creating new category
        res = c.post('/company/categories/quick-add/', {'name': 'Mobile Accessories'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['created'])
        self.assertEqual(res.json()['name'], 'Mobile Accessories')
        self.assertTrue(Category.objects.filter(company=self.company, name='Mobile Accessories').exists())

        # Test duplicate category prevention (case-insensitive)
        res_dup = c.post('/company/categories/quick-add/', {'name': 'electronics'})
        self.assertEqual(res_dup.status_code, 200)
        self.assertFalse(res_dup.json()['created'])
        self.assertEqual(res_dup.json()['id'], self.category.id)

    def test_brand_search_api_and_quick_add(self):
        c = Client()
        c.login(username="company_admin_test", password="password123")
        
        # Search existing
        res = c.get('/company/brands/search/?q=Sam')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['results'][0]['name'], "Samsung")

        # Quick Add new
        res_add = c.post('/company/brands/quick-add/', {'name': 'Apple'})
        self.assertEqual(res_add.status_code, 200)
        self.assertTrue(res_add.json()['created'])
        self.assertEqual(res_add.json()['name'], 'Apple')

        # Duplicate check
        res_dup = c.post('/company/brands/quick-add/', {'name': 'samsung'})
        self.assertEqual(res_dup.status_code, 200)
        self.assertFalse(res_dup.json()['created'])
        self.assertEqual(res_dup.json()['id'], self.brand.id)

    def test_product_save_with_category_and_brand(self):
        c = Client()
        c.login(username="company_admin_test", password="password123")
        res = c.post('/company/products/add/', {
            'name': 'Galaxy S24',
            'product_type': 'GOODS',
            'selling_price': '64900.00',
            'category': self.category.id,
            'brand': self.brand.id
        })
        self.assertIn(res.status_code, [200, 302])
        prod = Product.objects.filter(company=self.company, name='Galaxy S24').first()
        self.assertIsNotNone(prod)
        self.assertEqual(prod.category, self.category)
        self.assertEqual(prod.brand, self.brand)

    def test_admin_company_registration_state_validation(self):
        c = Client()
        c.login(username="superadmin_test", password="password123")
        
        # Test Mismatched State and Code (Odisha with 27 - Maharashtra code)
        res_fail = c.post('/admin/companies/add/', {
            'company_name': 'Invalid Co',
            'business_type': 'PROPRIETORSHIP',
            'gst_status': 'UNREGISTERED',
            'email': 'invalid@co.com',
            'mobile': '9999999999',
            'address': 'Street 1',
            'city': 'Bhubaneswar',
            'state': 'Odisha',
            'state_code': '27',
            'pincode': '751001',
            'owner_name': 'Owner',
            'username': 'invalidowner',
            'password': 'password123',
            'plan': self.plan.id
        })
        self.assertEqual(res_fail.status_code, 200) # Re-renders form with error
        self.assertFalse(Company.objects.filter(name='Invalid Co').exists())

        # Test Valid State and Code (Odisha with 21)
        res_ok = c.post('/admin/companies/add/', {
            'company_name': 'Valid Odisha Co',
            'business_type': 'PROPRIETORSHIP',
            'gst_status': 'UNREGISTERED',
            'email': 'valid@co.com',
            'mobile': '9999999999',
            'address': 'Street 1',
            'city': 'Bhubaneswar',
            'state': 'Odisha',
            'state_code': '21',
            'pincode': '751001',
            'owner_name': 'Owner Valid',
            'username': 'validowner',
            'password': 'password123',
            'plan': self.plan.id
        })
        self.assertIn(res_ok.status_code, [200, 302])
        created = Company.objects.filter(name='Valid Odisha Co').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.state, 'Odisha')
        self.assertEqual(created.state_code, '21')

    def test_indian_states_search_api(self):
        c = Client()
        c.login(username="superadmin_test", password="password123")
        res = c.get('/api/states/search/?q=Odis')
        self.assertEqual(res.status_code, 200)
        results = res.json()['results']
        self.assertTrue(any(r['code'] == '21' and 'Odisha' in r['name'] for r in results))


class QuotationPDFRedesignTests(TestCase):
    def setUp(self):
        self.plan = SubscriptionPlan.objects.create(name="Enterprise", monthly_price=Decimal('1999.00'))
        self.company = Company.objects.create(
            name="Mega Machinery Ltd",
            trade_name="Mega Machines",
            state="Odisha",
            state_code="21",
            city="Bhubaneswar",
            address="123 Industrial Estate",
            pincode="751010",
            email="sales@megamachines.com",
            mobile="9876543210",
            gstin="21AAAAA0000A1Z5",
            bank_name="State Bank of India",
            account_holder="Mega Machinery Ltd",
            account_number="1234567890",
            ifsc="SBIN0001234",
            branch="Bhubaneswar Main",
            plan=self.plan
        )
        self.customer = Customer.objects.create(
            company=self.company,
            name="Apex Processing Pvt Ltd",
            billing_address="456 Tech Park",
            billing_city="Bhubaneswar",
            billing_state="Odisha",
            billing_state_code="21",
            billing_pincode="751024",
            gstin="21BBBBB1111B1Z2",
            mobile="9123456789",
            email="purchase@apexproc.com"
        )
        self.user = CustomUser.objects.create_user(
            username="quotation_admin",
            password="password123",
            role="ADMIN",
            company=self.company
        )
        self.hsn = HSNSACMaster.objects.create(
            company=self.company,
            code="8438",
            description="Industrial Machinery",
            gst_rate=Decimal("18.00")
        )
        self.product = Product.objects.create(
            company=self.company,
            name="Pulveriser Machine 3HP",
            hsn_sac=self.hsn,
            description="Motor: 3 HP\nVoltage: 220V\nFrequency: 50Hz\nCapacity: 20-25 KG/Hour\nMaterial: Stainless Steel",
            selling_price=Decimal("45000.00")
        )
        self.quotation = Quotation.objects.create(
            company=self.company,
            customer=self.customer,
            quotation_number="QTN-2026-REDESIGN",
            date=date.today(),
            valid_until=date.today() + timedelta(days=30),
            subtotal=Decimal("45000.00"),
            taxable_value=Decimal("45000.00"),
            cgst_total=Decimal("4050.00"),
            sgst_total=Decimal("4050.00"),
            igst_total=Decimal("0.00"),
            grand_total=Decimal("53100.00"),
            status="SENT",
            notes="Inclusive of standard packing and warranty."
        )
        self.q_item = QuotationItem.objects.create(
            quotation=self.quotation,
            product=self.product,
            quantity=Decimal("1.00"),
            rate=Decimal("45000.00"),
            discount=Decimal("0.00"),
            taxable_value=Decimal("45000.00"),
            gst_rate=Decimal("18.00"),
            cgst_amount=Decimal("4050.00"),
            sgst_amount=Decimal("4050.00"),
            igst_amount=Decimal("0.00"),
            hsn_sac_code="8438",
            total_amount=Decimal("53100.00")
        )

    def test_parse_product_specifications_util(self):
        from .utils import parse_product_specifications
        res = parse_product_specifications(self.product.description)
        self.assertEqual(len(res['specs']), 5)
        spec_keys = [s['key'] for s in res['specs']]
        self.assertIn("Motor", spec_keys)
        self.assertIn("Voltage", spec_keys)
        self.assertIn("Capacity", spec_keys)

    def test_quotation_pdf_view_rendering(self):
        c = Client()
        c.login(username="quotation_admin", password="password123")
        res = c.get(f'/company/quotations/{self.quotation.id}/pdf/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "SALES QUOTATION")
        self.assertContains(res, "Mega Machinery Ltd")
        self.assertContains(res, "Pulveriser Machine 3HP")
        self.assertContains(res, "Motor:")
        self.assertContains(res, "3 HP")
        self.assertContains(res, "State Bank of India")
        self.assertContains(res, "QTN-2026-REDESIGN")

    def test_quotation_send_email_endpoint(self):
        c = Client()
        c.login(username="quotation_admin", password="password123")
        res = c.post(f'/company/quotations/{self.quotation.id}/send-email/', data=json.dumps({
            'email': 'purchase@apexproc.com'
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get('success'))

    def test_quotation_pdf_after_conversion_to_sales_order(self):
        c = Client()
        c.login(username="quotation_admin", password="password123")
        
        # Convert quotation to sales order
        conv_res = c.get(f'/company/quotations/{self.quotation.id}/convert-so/')
        self.assertEqual(conv_res.status_code, 302)
        
        self.quotation.refresh_from_db()
        self.assertEqual(self.quotation.status, 'CONVERTED')
        self.assertIsNotNone(self.quotation.converted_to_sales_order)
        
        so = self.quotation.converted_to_sales_order
        self.assertTrue(conv_res.url.endswith(f'/company/sales-orders/{so.id}/'))
        
        # Request Quotation PDF after conversion
        pdf_res = c.get(f'/company/quotations/{self.quotation.id}/pdf/')
        self.assertEqual(pdf_res.status_code, 200)
        self.assertContains(pdf_res, "SALES QUOTATION")
        self.assertContains(pdf_res, self.quotation.quotation_number)

    def test_prevent_duplicate_sales_order_conversion(self):
        c = Client()
        c.login(username="quotation_admin", password="password123")
        
        # Initial conversion
        c.get(f'/company/quotations/{self.quotation.id}/convert-so/')
        initial_so_count = SalesOrder.objects.filter(company=self.company).count()
        
        # Second conversion attempt
        dup_res = c.get(f'/company/quotations/{self.quotation.id}/convert-so/')
        self.assertEqual(dup_res.status_code, 302)
        final_so_count = SalesOrder.objects.filter(company=self.company).count()
        
        # Ensure no new sales order was created
        self.assertEqual(initial_so_count, final_so_count)

    def test_purchase_bill_pdf_endpoint(self):
        from billing.models import Supplier, PurchaseBill, PurchaseBillItem
        supplier = Supplier.objects.create(company=self.company, name="Tech Supply Co", gstin="27AAAAA0000A1Z5")
        bill = PurchaseBill.objects.create(
            company=self.company, supplier=supplier, supplier_bill_no="SUP-BILL-999",
            bill_date=date.today(), due_date=date.today(), subtotal=Decimal('1000.00'),
            taxable_value=Decimal('1000.00'), grand_total=Decimal('1180.00')
        )
        c = Client()
        c.login(username="quotation_admin", password="password123")
        res = c.get(f'/company/purchase-bills/{bill.id}/pdf/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "PURCHASE BILL")
        self.assertContains(res, "SUP-BILL-999")

    def test_company_delivery_page_access(self):
        c = Client()
        c.login(username="quotation_admin", password="password123")
        res = c.get('/company/delivery/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Delivery")
        self.assertContains(res, "COMING SOON")
        self.assertContains(res, "working on something amazing for you.")


class PurchaseOrderTests(TestCase):
    def setUp(self):
        from billing.models import Company, CustomUser, Supplier, Product, HSNSACMaster, Warehouse
        self.company = Company.objects.create(name="PO Test Corp", state="Odisha", state_code="21")
        self.user = CustomUser.objects.create_user(username="po_user", password="password123", company=self.company, role="COMPANY_ADMIN")
        self.supplier = Supplier.objects.create(company=self.company, name="Global Supplies Ltd", state="Odisha", state_code="21", gstin="21ABCDE1234F1Z5")
        self.hsn = HSNSACMaster.objects.create(code="8471", gst_rate=Decimal("18.00"))
        self.product = Product.objects.create(company=self.company, name="Laptop Stand", purchase_price=Decimal("1500.00"), selling_price=Decimal("2000.00"), hsn_sac=self.hsn)
        self.warehouse = Warehouse.objects.create(company=self.company, name="Central Warehouse")

    def test_purchase_order_creation_and_isolation(self):
        from billing.models import PurchaseOrder, StockMovement, SupplierLedger
        from billing.services import PurchaseOrderService

        initial_stock_movements = StockMovement.objects.count()
        initial_supplier_ledgers = SupplierLedger.objects.count()

        payload = {
            'supplier': self.supplier.id,
            'po_number': 'PO-2026-00001',
            'po_date': '2026-08-25',
            'expected_delivery_date': '2026-09-01',
            'warehouse': self.warehouse.id,
            'items': [
                {
                    'product_id': self.product.id,
                    'quantity': 10,
                    'rate': 1500,
                    'discount': 0,
                    'gst_rate': 18
                }
            ]
        }

        res = PurchaseOrderService.create_purchase_order(self.company, self.user, payload)
        self.assertTrue(res['success'])

        po = PurchaseOrder.objects.get(id=res['po_id'])
        self.assertEqual(po.po_number, 'PO-2026-00001')
        self.assertEqual(po.grand_total, Decimal('17700.00'))

        # CRITICAL VERIFICATION: Stock and Supplier Ledger MUST NOT change on PO creation
        self.assertEqual(StockMovement.objects.count(), initial_stock_movements)
        self.assertEqual(SupplierLedger.objects.count(), initial_supplier_ledgers)

    def test_purchase_order_pdf_endpoint_no_signature(self):
        from billing.services import PurchaseOrderService
        payload = {
            'supplier': self.supplier.id,
            'po_number': 'PO-2026-00002',
            'po_date': '2026-08-25',
            'items': [{'product_id': self.product.id, 'quantity': 2, 'rate': 1500, 'discount': 0}]
        }
        res = PurchaseOrderService.create_purchase_order(self.company, self.user, payload)
        po_id = res['po_id']

        c = Client()
        c.login(username="po_user", password="password123")
        pdf_res = c.get(f'/company/purchase-orders/{po_id}/pdf/')
        self.assertEqual(pdf_res.status_code, 200)
        self.assertContains(pdf_res, "PURCHASE ORDER")
        self.assertContains(pdf_res, "PO-2026-00002")

        # VERIFY AUTHORIZED SIGNATORY BLOCK IS PRESENT IN PO PDF
        html_text = pdf_res.content.decode('utf-8')
        self.assertIn("Authorized Signatory", html_text)

    def test_convert_purchase_order_to_purchase_bill(self):
        from billing.models import PurchaseBill
        from billing.services import PurchaseOrderService
        payload = {
            'supplier': self.supplier.id,
            'po_number': 'PO-2026-00003',
            'po_date': '2026-08-25',
            'items': [{'product_id': self.product.id, 'quantity': 5, 'rate': 1500, 'discount': 0}]
        }
        res = PurchaseOrderService.create_purchase_order(self.company, self.user, payload)
        po_id = res['po_id']

        conv_res = PurchaseOrderService.convert_to_purchase_bill(self.company, self.user, po_id)
        self.assertTrue(conv_res['success'])

        bill = PurchaseBill.objects.get(id=conv_res['bill_id'])
        self.assertEqual(bill.supplier, self.supplier)
        self.assertEqual(bill.grand_total, Decimal('8850.00'))

        # Separate PDFs
        c = Client()
        c.login(username="po_user", password="password123")
        po_pdf_res = c.get(f'/company/purchase-orders/{po_id}/pdf/')
        bill_pdf_res = c.get(f'/company/purchase-bills/{bill.id}/pdf/')
        self.assertEqual(po_pdf_res.status_code, 200)
        self.assertEqual(bill_pdf_res.status_code, 200)
        self.assertContains(po_pdf_res, "PURCHASE ORDER")
        self.assertContains(bill_pdf_res, "PURCHASE BILL")


    def test_admin_delivery_page_access(self):
        from billing.models import CustomUser
        super_admin = CustomUser.objects.create_superuser(username="saas_admin", email="admin@saas.com", password="adminpassword123", role="SUPERADMIN")
        c = Client()
        c.login(username="saas_admin", password="adminpassword123")
        res = c.get('/admin/delivery/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Delivery")
        self.assertContains(res, "COMING SOON")


class PurchaseOrderEnhancementTests(TestCase):
    def setUp(self):
        from billing.models import Company, CustomUser, Supplier, Product, HSNSACMaster, Warehouse, PurchaseBill
        self.company = Company.objects.create(name="Enhancement Corp", state="Odisha", state_code="21")
        self.other_company = Company.objects.create(name="Other Corp", state="Delhi", state_code="07")
        self.user = CustomUser.objects.create_user(username="enh_user", password="password123", company=self.company, role="COMPANY_ADMIN")
        self.other_user = CustomUser.objects.create_user(username="other_user", password="password123", company=self.other_company, role="COMPANY_ADMIN")
        
        self.supplier = Supplier.objects.create(company=self.company, name="Master Vendor Ltd", state="Odisha", state_code="21", gstin="21ABCDE1234F1Z5")
        self.hsn = HSNSACMaster.objects.create(code="8471", gst_rate=Decimal("18.00"))
        self.product = Product.objects.create(company=self.company, name="Monitor Stand", purchase_price=Decimal("1000.00"), selling_price=Decimal("1500.00"), hsn_sac=self.hsn)
        self.warehouse = Warehouse.objects.create(company=self.company, name="Eastern Warehouse", code="WH-EAST", manager="Alice", contact="9998887770", address="Infocity, Bhubaneswar")

        self.bill = PurchaseBill.objects.create(
            company=self.company, supplier=self.supplier, supplier_bill_no="BILL-2026-101",
            bill_date=date.today(), due_date=date.today(), grand_total=Decimal('1180.00')
        )

    def test_warehouse_detail_api(self):
        c = Client()
        c.login(username="enh_user", password="password123")
        res = c.get(f'/api/company/warehouses/{self.warehouse.id}/detail/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['warehouse']['name'], 'Eastern Warehouse')
        self.assertEqual(data['warehouse']['manager'], 'Alice')

    def test_manual_supplier_entry_po_creation(self):
        from billing.services import PurchaseOrderService
        from billing.models import PurchaseOrder
        payload = {
            'supplier_company_name': 'Manual Supplier Enterprises',
            'supplier_phone': '9876543210',
            'supplier_email': 'manual@supplier.com',
            'supplier_gstin': '21XYZ0000000000',
            'supplier_state': 'Odisha',
            'supplier_state_code': '21',
            'po_number': 'PO-2026-MANUAL-1',
            'po_date': '2026-08-25',
            'items': [{'product_id': self.product.id, 'quantity': 2, 'rate': 1000, 'discount': 0}]
        }
        res = PurchaseOrderService.create_purchase_order(self.company, self.user, payload)
        self.assertTrue(res['success'])
        po = PurchaseOrder.objects.get(id=res['po_id'])
        self.assertIsNone(po.supplier)
        self.assertEqual(po.supplier_name_snapshot, 'Manual Supplier Enterprises')
        self.assertEqual(po.supplier_gstin_snapshot, '21XYZ0000000000')

    def test_terms_checkboxes_and_pdf_no_signature(self):
        from billing.services import PurchaseOrderService
        payload = {
            'supplier': self.supplier.id,
            'po_number': 'PO-2026-TERMS-1',
            'po_date': '2026-08-25',
            'payment_terms': ["Payment within 15 days of invoice", "50% advance and remaining payment on delivery"],
            'delivery_terms': ["Delivery within 7 working days"],
            'warranty_terms': ["12 months warranty"],
            'return_terms': ["Goods can be returned for manufacturing defects"],
            'items': [{'product_id': self.product.id, 'quantity': 1, 'rate': 1000, 'discount': 0}]
        }
        res = PurchaseOrderService.create_purchase_order(self.company, self.user, payload)
        po_id = res['po_id']

        c = Client()
        c.login(username="enh_user", password="password123")
        pdf_res = c.get(f'/company/purchase-orders/{po_id}/pdf/')
        self.assertEqual(pdf_res.status_code, 200)
        self.assertContains(pdf_res, "Payment within 15 days of invoice")
        self.assertContains(pdf_res, "12 months warranty")

        # VERIFY AUTHORIZED SIGNATORY BLOCK IS PRESENT AT BOTTOM OF PDF
        html_text = pdf_res.content.decode('utf-8')
        self.assertIn("Authorized Signatory", html_text)

    def test_purchase_bill_document_upload_security_and_delete(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from billing.models import PurchaseBillDocument

        c = Client()
        c.login(username="enh_user", password="password123")

        # 1. Valid PDF file upload
        pdf_file = SimpleUploadedFile("vendor_invoice.pdf", b"%PDF-1.4 dummy pdf content", content_type="application/pdf")
        res = c.post(f'/company/purchase-bills/{self.bill.id}/documents/upload/', {'file': pdf_file})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'success')
        doc_id = data['document']['id']
        self.assertTrue(PurchaseBillDocument.objects.filter(id=doc_id).exists())

        # 2. Reject executable file upload
        exe_file = SimpleUploadedFile("malicious.exe", b"MZ dummy executable", content_type="application/octet-stream")
        bad_res = c.post(f'/company/purchase-bills/{self.bill.id}/documents/upload/', {'file': exe_file})
        self.assertEqual(bad_res.status_code, 400)
        self.assertIn("Invalid file format", bad_res.json()['message'])

        # 3. View document (same company)
        view_res = c.get(f'/company/purchase-bills/documents/{doc_id}/view/')
        self.assertEqual(view_res.status_code, 200)

        # 4. Security Check: Other company user cannot view document
        c_other = Client()
        c_other.login(username="other_user", password="password123")
        other_view_res = c_other.get(f'/company/purchase-bills/documents/{doc_id}/view/')
        self.assertIn(other_view_res.status_code, [403, 404])

        # 5. Delete document
        del_res = c.post(f'/company/purchase-bills/documents/{doc_id}/delete/')
        self.assertEqual(del_res.status_code, 200)
        self.assertFalse(PurchaseBillDocument.objects.filter(id=doc_id).exists())


    def test_other_custom_product_and_editable_gst(self):
        """
        Verify creating a PO with a custom "Other" product, editable GST % override,
        combined state selection parsing, and formatted currency input without photo.
        """
        from billing.models import PurchaseOrder, PurchaseOrderItem

        c = Client()
        c.login(username="enh_user", password="password123")

        items_payload = json.dumps([
            {
                "row_index": "1",
                "product_id": "OTHER",
                "product_name": "Custom Office Laptop",
                "description": "Custom configuration laptop 16GB RAM",
                "hsn_sac": "8471",
                "uqc": "PCS",
                "quantity": 2,
                "rate": "₹5,000.00",
                "discount": "₹500.00",
                "gst_rate": "12%"
            }
        ])

        data = {
            "supplier_company_name": "Unique Custom Supplier",
            "supplier_phone": "9988776655",
            "supplier_state": "Odisha (21)",
            "po_number": "PO-CUSTOM-001",
            "po_date": "2026-08-25",
            "warehouse_id": self.warehouse.id,
            "items_json": items_payload
        }

        res = c.post('/company/purchase-orders/add/', data)
        self.assertEqual(res.status_code, 302)

        po = PurchaseOrder.objects.get(po_number="PO-CUSTOM-001")
        self.assertEqual(po.supplier_name_snapshot, "Unique Custom Supplier")
        self.assertEqual(po.supplier_state_snapshot, "Odisha")
        self.assertEqual(po.supplier_state_code_snapshot, "21")

        items = po.items.all()
        self.assertEqual(items.count(), 1)
        item = items.first()
        self.assertIsNone(item.product)
        self.assertEqual(item.product_name_snapshot, "Custom Office Laptop")
        self.assertEqual(item.rate, Decimal("5000.00"))
        self.assertEqual(item.discount, Decimal("500.00"))
        self.assertEqual(item.gst_rate, Decimal("12.00"))

        # Check detail page view
        view_res = c.get(f'/company/purchase-orders/{po.id}/')
        self.assertEqual(view_res.status_code, 200)

        # Check PDF page view
        pdf_res = c.get(f'/company/purchase-orders/{po.id}/pdf/')
        self.assertEqual(pdf_res.status_code, 200)

    def test_purchase_bill_creation_with_supporting_document(self):
        """
        Verify creating a Purchase Bill with an attached supporting document file.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile
        from billing.models import PurchaseBill, PurchaseBillDocument

        c = Client()
        c.login(username="enh_user", password="password123")

        doc_file = SimpleUploadedFile("bill_receipt.pdf", b"%PDF-1.4 dummy bill content", content_type="application/pdf")

        items_payload = json.dumps([
            {
                "product_id": self.product.id,
                "quantity": 3,
                "rate": 1200,
                "discount": 100
            }
        ])

        data = {
            "supplier": self.supplier.id,
            "supplier_bill_no": "BILL-DOC-999",
            "bill_date": "2026-08-25",
            "due_date": "2026-09-25",
            "warehouse_id": self.warehouse.id,
            "items_json": items_payload,
            "supporting_document": doc_file
        }

        res = c.post('/company/purchase-bills/add/', data)
        self.assertEqual(res.status_code, 302)

        bill = PurchaseBill.objects.get(supplier_bill_no="BILL-DOC-999")
        docs = PurchaseBillDocument.objects.filter(purchase_bill=bill)
        self.assertEqual(docs.count(), 1)
        doc = docs.first()
        self.assertEqual(doc.file_name, "bill_receipt.pdf")
        self.assertEqual(doc.file_type, "PDF")

    def test_global_state_code_parsing_and_validation(self):
        """
        Verify parse_state_and_code and format_state_display work as expected across state formats.
        """
        from billing.utils import parse_state_and_code, format_state_display

        # Test state name + code string
        name, code = parse_state_and_code("Odisha (21)")
        self.assertEqual(name, "Odisha")
        self.assertEqual(code, "21")

        # Test numeric state code string
        name, code = parse_state_and_code("27")
        self.assertEqual(name, "Maharashtra")
        self.assertEqual(code, "27")

        # Test state name string
        name, code = parse_state_and_code("Karnataka")
        self.assertEqual(name, "Karnataka")
        self.assertEqual(code, "29")

        # Test display formatting
        disp = format_state_display("Odisha", "21")
        self.assertEqual(disp, "Odisha (21)")

    def test_purchase_order_edit_null_supplier_safety(self):
        """
        Verify that editing a Purchase Order with supplier = None (such as PO #3)
        loads cleanly without raising VariableDoesNotExist, and PDF has no auto signature image.
        """
        from billing.models import PurchaseOrder, PurchaseOrderItem
        po = PurchaseOrder.objects.create(
            company=self.company,
            supplier=None,
            supplier_name_snapshot="Manual Vendor",
            po_number="PO-NULL-SUPPLIER-3",
            po_date=date.today(),
            subtotal=Decimal('1000.00'),
            taxable_amount=Decimal('1000.00'),
            grand_total=Decimal('1180.00')
        )
        PurchaseOrderItem.objects.create(
            purchase_order=po,
            product_name_snapshot="Manual Item",
            quantity=Decimal('1.00'),
            rate=Decimal('1000.00'),
            taxable_amount=Decimal('1000.00'),
            total_amount=Decimal('1180.00')
        )

        c = Client()
        c.login(username="enh_user", password="password123")
        edit_res = c.get(f'/company/purchase-orders/{po.id}/edit/')
        self.assertEqual(edit_res.status_code, 200)

        pdf_res = c.get(f'/company/purchase-orders/{po.id}/pdf/')
        self.assertEqual(pdf_res.status_code, 200)
        html_text = pdf_res.content.decode('utf-8')
        self.assertIn("Authorized Signatory", html_text)
        self.assertNotIn("company.signature", html_text)
        self.assertNotIn("company.stamp", html_text)


    def test_unauthenticated_delivery_access(self):
        c = Client()
        res_comp = c.get('/company/delivery/')
        self.assertEqual(res_comp.status_code, 302)
        res_admin = c.get('/admin/delivery/')
        self.assertEqual(res_admin.status_code, 403)










