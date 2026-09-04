from decimal import Decimal
from django.test import TestCase
from billing.models import (
    Company, Customer, Supplier, Product, HSNSACMaster,
    Invoice, InvoiceItem, Quotation, PurchaseBill, PurchaseBillItem, CreditNote
)
from billing.utils import (
    calculate_line_item_financials,
    calculate_item_gst,
    build_hsn_sac_tax_summary,
    recalculate_invoice_totals,
    recalculate_generic_document_totals
)
from billing.services import QuotationService, PurchaseOrderService

class GSTMatrixCalculationTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Alpha Corp",
            state="Odisha",
            state_code="21",
            financial_year="2026-27"
        )
        self.customer_intra = Customer.objects.create(
            company=self.company,
            name="Intra-State Customer",
            billing_state="Odisha",
            billing_state_code="21"
        )
        self.customer_inter = Customer.objects.create(
            company=self.company,
            name="Inter-State Customer",
            billing_state="Maharashtra",
            billing_state_code="27"
        )
        self.hsn_18 = HSNSACMaster.objects.create(
            code="8471",
            description="Hardware 18%",
            gst_rate=Decimal('18.00'),
            is_active=True
        )
        self.hsn_12 = HSNSACMaster.objects.create(
            code="8472",
            description="Goods 12%",
            gst_rate=Decimal('12.00'),
            is_active=True
        )
        self.hsn_5 = HSNSACMaster.objects.create(
            code="1001",
            description="Goods 5%",
            gst_rate=Decimal('5.00'),
            is_active=True
        )
        self.hsn_0 = HSNSACMaster.objects.create(
            code="9999",
            description="Exempt 0%",
            gst_rate=Decimal('0.00'),
            is_active=True
        )
        self.hsn_cess = HSNSACMaster.objects.create(
            code="8703",
            description="Luxury Motor Vehicles",
            gst_rate=Decimal('28.00'),
            cess_rate=Decimal('12.00'),
            is_active=True
        )

    def test_case_1_gst_exclusive_5(self):
        """1. GST-exclusive 5%"""
        res = calculate_line_item_financials(
            quantity=1, rate=179, discount=0, gst_rate=5,
            is_tax_inclusive=False, company_state_code="21", pos_state_code="21"
        )
        self.assertEqual(res['line_subtotal'], Decimal('179.00'))
        self.assertEqual(res['line_taxable'], Decimal('179.00'))
        self.assertEqual(res['cgst_amount'], Decimal('4.48'))
        self.assertEqual(res['sgst_amount'], Decimal('4.48'))
        self.assertEqual(res['igst_amount'], Decimal('0.00'))
        self.assertEqual(res['line_total'], Decimal('187.96'))

    def test_case_2_gst_exclusive_12(self):
        """2. GST-exclusive 12%"""
        res = calculate_line_item_financials(
            quantity=1, rate=100, discount=0, gst_rate=12,
            is_tax_inclusive=False, company_state_code="21", pos_state_code="21"
        )
        self.assertEqual(res['line_subtotal'], Decimal('100.00'))
        self.assertEqual(res['line_taxable'], Decimal('100.00'))
        self.assertEqual(res['cgst_amount'], Decimal('6.00'))
        self.assertEqual(res['sgst_amount'], Decimal('6.00'))
        self.assertEqual(res['line_total'], Decimal('112.00'))

    def test_case_3_gst_exclusive_18(self):
        """3. GST-exclusive 18%"""
        res = calculate_line_item_financials(
            quantity=1, rate=100, discount=0, gst_rate=18,
            is_tax_inclusive=False, company_state_code="21", pos_state_code="21"
        )
        self.assertEqual(res['line_subtotal'], Decimal('100.00'))
        self.assertEqual(res['line_taxable'], Decimal('100.00'))
        self.assertEqual(res['cgst_amount'], Decimal('9.00'))
        self.assertEqual(res['sgst_amount'], Decimal('9.00'))
        self.assertEqual(res['line_total'], Decimal('118.00'))

    def test_case_4_gst_inclusive_5(self):
        """4. GST-inclusive 5%"""
        res = calculate_line_item_financials(
            quantity=1, rate=179, discount=0, gst_rate=5,
            is_tax_inclusive=True, company_state_code="21", pos_state_code="21"
        )
        self.assertEqual(res['line_subtotal'], Decimal('179.00'))
        self.assertEqual(res['line_taxable'], Decimal('170.48'))
        self.assertEqual(res['cgst_amount'], Decimal('4.26'))
        self.assertEqual(res['sgst_amount'], Decimal('4.26'))
        self.assertEqual(res['igst_amount'], Decimal('0.00'))
        self.assertEqual(res['line_total'], Decimal('179.00'))

    def test_case_5_gst_inclusive_12(self):
        """5. GST-inclusive 12%"""
        res = calculate_line_item_financials(
            quantity=1, rate=112, discount=0, gst_rate=12,
            is_tax_inclusive=True, company_state_code="21", pos_state_code="21"
        )
        self.assertEqual(res['line_subtotal'], Decimal('112.00'))
        self.assertEqual(res['line_taxable'], Decimal('100.00'))
        self.assertEqual(res['cgst_amount'], Decimal('6.00'))
        self.assertEqual(res['sgst_amount'], Decimal('6.00'))
        self.assertEqual(res['line_total'], Decimal('112.00'))

    def test_case_6_gst_inclusive_18(self):
        """6. GST-inclusive 18%"""
        res = calculate_line_item_financials(
            quantity=1, rate=118, discount=0, gst_rate=18,
            is_tax_inclusive=True, company_state_code="21", pos_state_code="21"
        )
        self.assertEqual(res['line_subtotal'], Decimal('118.00'))
        self.assertEqual(res['line_taxable'], Decimal('100.00'))
        self.assertEqual(res['cgst_amount'], Decimal('9.00'))
        self.assertEqual(res['sgst_amount'], Decimal('9.00'))
        self.assertEqual(res['line_total'], Decimal('118.00'))

    def test_case_7_intrastate(self):
        """7. Intra-state (CGST + SGST, IGST = 0)"""
        cgst, sgst, igst, total = calculate_item_gst("21", "21", Decimal('1000.00'), Decimal('18.00'))
        self.assertEqual(cgst, Decimal('90.00'))
        self.assertEqual(sgst, Decimal('90.00'))
        self.assertEqual(igst, Decimal('0.00'))
        self.assertEqual(total, Decimal('180.00'))

    def test_case_8_interstate(self):
        """8. Inter-state (IGST only, CGST = SGST = 0)"""
        cgst, sgst, igst, total = calculate_item_gst("21", "27", Decimal('1000.00'), Decimal('18.00'))
        self.assertEqual(cgst, Decimal('0.00'))
        self.assertEqual(sgst, Decimal('0.00'))
        self.assertEqual(igst, Decimal('180.00'))
        self.assertEqual(total, Decimal('180.00'))

    def test_case_9_discount_before_gst(self):
        """9. Discount + GST (Discount applied BEFORE GST)"""
        res = calculate_line_item_financials(
            quantity=1, rate=1000, discount=100, gst_rate=18,
            is_tax_inclusive=False, company_state_code="21", pos_state_code="21"
        )
        self.assertEqual(res['line_subtotal'], Decimal('1000.00'))
        self.assertEqual(res['line_discount'], Decimal('100.00'))
        self.assertEqual(res['line_taxable'], Decimal('900.00'))
        self.assertEqual(res['cgst_amount'], Decimal('81.00'))
        self.assertEqual(res['sgst_amount'], Decimal('81.00'))
        self.assertEqual(res['line_total'], Decimal('1062.00'))

    def test_case_10_multiple_products_different_gst(self):
        """10. Multiple products with different GST rates"""
        prod_a = Product.objects.create(company=self.company, name="A", selling_price=Decimal('100.00'), hsn_sac=self.hsn_5)
        prod_b = Product.objects.create(company=self.company, name="B", selling_price=Decimal('500.00'), hsn_sac=self.hsn_18)
        prod_c = Product.objects.create(company=self.company, name="C", selling_price=Decimal('200.00'), hsn_sac=self.hsn_0)

        inv = Invoice.objects.create(
            company=self.company, customer=self.customer_intra,
            invoice_number="INV-MULTI-10", invoice_date="2026-08-01", due_date="2026-08-31",
            place_of_supply="Odisha", place_of_supply_code="21"
        )
        InvoiceItem.objects.create(invoice=inv, product=prod_a, quantity=Decimal('1'), rate=Decimal('100.00'), discount=Decimal('0'), taxable_value=Decimal('0'), gst_rate=Decimal('5.00'), total_amount=Decimal('0'))
        InvoiceItem.objects.create(invoice=inv, product=prod_b, quantity=Decimal('1'), rate=Decimal('500.00'), discount=Decimal('0'), taxable_value=Decimal('0'), gst_rate=Decimal('18.00'), total_amount=Decimal('0'))
        InvoiceItem.objects.create(invoice=inv, product=prod_c, quantity=Decimal('1'), rate=Decimal('200.00'), discount=Decimal('0'), taxable_value=Decimal('0'), gst_rate=Decimal('0.00'), total_amount=Decimal('0'))
        
        recalculate_invoice_totals(inv)

        self.assertEqual(inv.subtotal, Decimal('800.00'))
        self.assertEqual(inv.discount_total, Decimal('0.00'))
        self.assertEqual(inv.taxable_value, Decimal('800.00'))
        self.assertEqual(inv.cgst_total, Decimal('47.50'))  # 2.50 + 45.00
        self.assertEqual(inv.sgst_total, Decimal('47.50'))  # 2.50 + 45.00
        self.assertEqual(inv.igst_total, Decimal('0.00'))
        self.assertEqual(inv.grand_total, Decimal('895.00'))

    def test_case_11_cess(self):
        """11. Cess calculation"""
        res = calculate_line_item_financials(
            quantity=1, rate=1000, discount=0, gst_rate=28, cess_rate=12,
            is_tax_inclusive=False, company_state_code="21", pos_state_code="21"
        )
        self.assertEqual(res['line_taxable'], Decimal('1000.00'))
        self.assertEqual(res['cgst_amount'], Decimal('140.00'))
        self.assertEqual(res['sgst_amount'], Decimal('140.00'))
        self.assertEqual(res['cess_amount'], Decimal('120.00'))
        self.assertEqual(res['line_total'], Decimal('1400.00'))

    def test_case_12_round_off(self):
        """12. Round-off calculation"""
        prod = Product.objects.create(company=self.company, name="Item", selling_price=Decimal('1179.60'), hsn_sac=self.hsn_0)
        inv = Invoice.objects.create(
            company=self.company, customer=self.customer_intra,
            invoice_number="INV-ROUND-12", invoice_date="2026-08-01", due_date="2026-08-31",
            place_of_supply="Odisha", place_of_supply_code="21"
        )
        InvoiceItem.objects.create(invoice=inv, product=prod, quantity=Decimal('1'), rate=Decimal('1179.60'), discount=Decimal('0'), taxable_value=Decimal('0'), gst_rate=Decimal('0.00'), total_amount=Decimal('0'))
        
        # Rounding enabled
        recalculate_generic_document_totals(inv, apply_round_off=True)
        self.assertEqual(inv.grand_total, Decimal('1180.00'))
        self.assertEqual(inv.round_off, Decimal('0.40'))

        # Rounding disabled
        recalculate_generic_document_totals(inv, apply_round_off=False)
        self.assertEqual(inv.grand_total, Decimal('1179.60'))
        self.assertEqual(inv.round_off, Decimal('0.00'))

    def test_case_13_zero_gst(self):
        """13. Zero GST (0%)"""
        res = calculate_line_item_financials(
            quantity=1, rate=500, discount=0, gst_rate=0,
            is_tax_inclusive=False, company_state_code="21", pos_state_code="21"
        )
        self.assertEqual(res['line_subtotal'], Decimal('500.00'))
        self.assertEqual(res['line_taxable'], Decimal('500.00'))
        self.assertEqual(res['cgst_amount'], Decimal('0.00'))
        self.assertEqual(res['sgst_amount'], Decimal('0.00'))
        self.assertEqual(res['igst_amount'], Decimal('0.00'))
        self.assertEqual(res['line_total'], Decimal('500.00'))

    def test_case_14_gst_exempt_product(self):
        """14. GST-exempt product"""
        prod_exempt = Product.objects.create(company=self.company, name="Exempt Item", selling_price=Decimal('250.00'), hsn_sac=self.hsn_0)
        inv = Invoice.objects.create(
            company=self.company, customer=self.customer_intra,
            invoice_number="INV-EXEMPT-14", invoice_date="2026-08-01", due_date="2026-08-31",
            place_of_supply="Odisha", place_of_supply_code="21"
        )
        InvoiceItem.objects.create(invoice=inv, product=prod_exempt, quantity=Decimal('2'), rate=Decimal('250.00'), discount=Decimal('0'), taxable_value=Decimal('0'), gst_rate=Decimal('0.00'), total_amount=Decimal('0'))
        recalculate_invoice_totals(inv)
        self.assertEqual(inv.subtotal, Decimal('500.00'))
        self.assertEqual(inv.cgst_total, Decimal('0.00'))
        self.assertEqual(inv.grand_total, Decimal('500.00'))

    def test_case_15_credit_note(self):
        """15. Credit note calculation"""
        inv = Invoice.objects.create(
            company=self.company, customer=self.customer_intra,
            invoice_number="INV-CN-ORIG", invoice_date="2026-08-01", due_date="2026-08-31",
            place_of_supply="Odisha", place_of_supply_code="21"
        )
        prod = Product.objects.create(company=self.company, name="P1", selling_price=Decimal('100.00'), hsn_sac=self.hsn_18)
        InvoiceItem.objects.create(invoice=inv, product=prod, quantity=Decimal('1'), rate=Decimal('100.00'), discount=Decimal('0'), taxable_value=Decimal('0'), gst_rate=Decimal('18.00'), total_amount=Decimal('0'))
        recalculate_invoice_totals(inv)

        cn = CreditNote.objects.create(
            company=self.company, invoice=inv, note_number="CN-001", note_date="2026-08-05",
            reason="SALES_RETURN", subtotal=Decimal('100.00'), taxable_value=Decimal('100.00'),
            cgst_total=Decimal('9.00'), sgst_total=Decimal('9.00'), igst_total=Decimal('0.00'),
            grand_total=Decimal('118.00')
        )
        self.assertEqual(cn.grand_total, Decimal('118.00'))

    def test_case_16_invoice_edit(self):
        """16. Invoice edit recalculation"""
        prod = Product.objects.create(company=self.company, name="Edit Item", selling_price=Decimal('100.00'), hsn_sac=self.hsn_18)
        inv = Invoice.objects.create(
            company=self.company, customer=self.customer_intra,
            invoice_number="INV-EDIT-16", invoice_date="2026-08-01", due_date="2026-08-31",
            place_of_supply="Odisha", place_of_supply_code="21"
        )
        item = InvoiceItem.objects.create(invoice=inv, product=prod, quantity=Decimal('1'), rate=Decimal('100.00'), discount=Decimal('0'), taxable_value=Decimal('0'), gst_rate=Decimal('18.00'), total_amount=Decimal('0'))
        recalculate_invoice_totals(inv)
        self.assertEqual(inv.grand_total, Decimal('118.00'))

        # Edit item quantity to 2
        item.quantity = Decimal('2')
        item.save()
        recalculate_invoice_totals(inv)
        self.assertEqual(inv.subtotal, Decimal('200.00'))
        self.assertEqual(inv.cgst_total, Decimal('18.00'))
        self.assertEqual(inv.sgst_total, Decimal('18.00'))
        self.assertEqual(inv.grand_total, Decimal('236.00'))

    def test_case_17_quotation_service(self):
        """17. Quotation service & generic document totals integration"""
        prod = Product.objects.create(company=self.company, name="QS Item", selling_price=Decimal('200.00'), hsn_sac=self.hsn_18)
        data = {
            'customer_id': self.customer_inter.id,
            'quotation_number': 'QTN-TEST-17',
            'date': '2026-08-01',
            'valid_until': '2026-08-31',
            'items': [{'product_id': prod.id, 'quantity': 1, 'rate': 200, 'discount': 0}]
        }
        res = QuotationService.create_quotation(self.company, None, data)
        self.assertTrue(res['success'])
        q = Quotation.objects.get(id=res['quotation_id'])
        self.assertEqual(q.subtotal, Decimal('200.00'))
        self.assertEqual(q.igst_total, Decimal('36.00'))
        self.assertEqual(q.grand_total, Decimal('236.00'))
