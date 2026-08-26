from decimal import Decimal
from django.test import TestCase, Client
from billing.models import (
    Company, Customer, Supplier, Product, HSNSACMaster,
    Invoice, InvoiceItem, Quotation, QuotationItem,
    SalesOrder, SalesOrderItem, PurchaseBill, PurchaseBillItem,
    PurchaseOrder, PurchaseOrderItem, CreditNote
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
            description="Computers & Hardware",
            gst_rate=Decimal('18.00'),
            is_active=True
        )
        self.hsn_5 = HSNSACMaster.objects.create(
            code="1001",
            description="Goods 5%",
            gst_rate=Decimal('5.00'),
            is_active=True
        )
        self.prod_200_18 = Product.objects.create(
            company=self.company,
            name="IT Equipment 18%",
            selling_price=Decimal('200.00'),
            hsn_sac=self.hsn_18
        )
        self.prod_1000_5 = Product.objects.create(
            company=self.company,
            name="Item 5%",
            selling_price=Decimal('1000.00'),
            hsn_sac=self.hsn_5
        )

    def test_case_a_basic_interstate(self):
        """
        TEST A: Unit Price = ₹200, Qty = 1, Discount = ₹0, GST = 18%, Interstate
        Expected: Subtotal ₹200.00, Taxable ₹200.00, IGST ₹36.00, Grand Total ₹236.00
        """
        res = calculate_line_item_financials(
            quantity=1, rate=200, discount=0, gst_rate=18,
            company_state_code="21", pos_state_code="27"
        )
        self.assertEqual(res['line_subtotal'], Decimal('200.00'))
        self.assertEqual(res['line_discount'], Decimal('0.00'))
        self.assertEqual(res['line_taxable'], Decimal('200.00'))
        self.assertEqual(res['igst_amount'], Decimal('36.00'))
        self.assertEqual(res['cgst_amount'], Decimal('0.00'))
        self.assertEqual(res['sgst_amount'], Decimal('0.00'))
        self.assertEqual(res['line_total'], Decimal('236.00'))

    def test_case_b_discount_interstate(self):
        """
        TEST B: Unit Price = ₹200, Qty = 1, Discount = ₹20, GST = 18%, Interstate
        Expected: Subtotal ₹200.00, Discount ₹20.00, Taxable ₹180.00, IGST ₹32.40, Grand Total ₹212.40
        """
        res = calculate_line_item_financials(
            quantity=1, rate=200, discount=20, gst_rate=18,
            company_state_code="21", pos_state_code="27"
        )
        self.assertEqual(res['line_subtotal'], Decimal('200.00'))
        self.assertEqual(res['line_discount'], Decimal('20.00'))
        self.assertEqual(res['line_taxable'], Decimal('180.00'))
        self.assertEqual(res['igst_amount'], Decimal('32.40'))
        self.assertEqual(res['line_total'], Decimal('212.40'))

    def test_case_c_quantity_interstate(self):
        """
        TEST C: Unit Price = ₹200, Qty = 3, Discount = ₹0, GST = 18%, Interstate
        Expected: Subtotal ₹600.00, Taxable ₹600.00, IGST ₹108.00, Grand Total ₹708.00
        """
        res = calculate_line_item_financials(
            quantity=3, rate=200, discount=0, gst_rate=18,
            company_state_code="21", pos_state_code="27"
        )
        self.assertEqual(res['line_subtotal'], Decimal('600.00'))
        self.assertEqual(res['line_taxable'], Decimal('600.00'))
        self.assertEqual(res['igst_amount'], Decimal('108.00'))
        self.assertEqual(res['line_total'], Decimal('708.00'))

    def test_case_d_quantity_plus_discount_interstate(self):
        """
        TEST D: Unit Price = ₹200, Qty = 3, Discount = ₹50, GST = 18%, Interstate
        Expected: Subtotal ₹600.00, Discount ₹50.00, Taxable ₹550.00, IGST ₹99.00, Grand Total ₹649.00
        """
        res = calculate_line_item_financials(
            quantity=3, rate=200, discount=50, gst_rate=18,
            company_state_code="21", pos_state_code="27"
        )
        self.assertEqual(res['line_subtotal'], Decimal('600.00'))
        self.assertEqual(res['line_discount'], Decimal('50.00'))
        self.assertEqual(res['line_taxable'], Decimal('550.00'))
        self.assertEqual(res['igst_amount'], Decimal('99.00'))
        self.assertEqual(res['line_total'], Decimal('649.00'))

    def test_case_e_intrastate_transaction(self):
        """
        TEST E: Unit Price = ₹200, Qty = 1, Discount = ₹0, GST = 18%, Intrastate
        Expected: Subtotal ₹200.00, Taxable ₹200.00, CGST ₹18.00, SGST ₹18.00, IGST ₹0.00, Grand Total ₹236.00
        """
        res = calculate_line_item_financials(
            quantity=1, rate=200, discount=0, gst_rate=18,
            company_state_code="21", pos_state_code="21"
        )
        self.assertEqual(res['line_subtotal'], Decimal('200.00'))
        self.assertEqual(res['line_taxable'], Decimal('200.00'))
        self.assertEqual(res['cgst_amount'], Decimal('18.00'))
        self.assertEqual(res['sgst_amount'], Decimal('18.00'))
        self.assertEqual(res['igst_amount'], Decimal('0.00'))
        self.assertEqual(res['line_total'], Decimal('236.00'))

    def test_case_f_multiple_products_different_gst(self):
        """
        TEST F: Multiple products with different GST rates.
        Product A: Taxable ₹1000, GST 5% -> IGST ₹50
        Product B: Taxable ₹2000, GST 18% -> IGST ₹360
        Expected: Subtotal ₹3000, Total Taxable ₹3000, Total IGST ₹410, Grand Total ₹3410
        """
        inv = Invoice.objects.create(
            company=self.company,
            customer=self.customer_inter,
            invoice_number="INV-FULL-F",
            invoice_date="2026-08-01",
            due_date="2026-08-31",
            place_of_supply="Maharashtra",
            place_of_supply_code="27"
        )
        InvoiceItem.objects.create(
            invoice=inv, product=self.prod_1000_5, quantity=Decimal('1.00'), rate=Decimal('1000.00'),
            discount=Decimal('0.00'), taxable_value=Decimal('0.00'), gst_rate=Decimal('5.00'),
            total_amount=Decimal('0.00')
        )
        InvoiceItem.objects.create(
            invoice=inv, product=self.prod_200_18, quantity=Decimal('10.00'), rate=Decimal('200.00'),
            discount=Decimal('0.00'), taxable_value=Decimal('0.00'), gst_rate=Decimal('18.00'),
            total_amount=Decimal('0.00')
        )
        recalculate_invoice_totals(inv)

        self.assertEqual(inv.subtotal, Decimal('3000.00'))
        self.assertEqual(inv.discount_total, Decimal('0.00'))
        self.assertEqual(inv.taxable_value, Decimal('3000.00'))
        self.assertEqual(inv.igst_total, Decimal('410.00'))
        self.assertEqual(inv.grand_total, Decimal('3410.00'))

        summary, total_qty = build_hsn_sac_tax_summary(inv.items.all(), "21", "27")
        self.assertEqual(len(summary), 2)

    def test_quotation_service_and_recalculate_consistency(self):
        """
        Verify QuotationService saves exact mathematical fields in database matching expectation.
        """
        data = {
            'customer_id': self.customer_inter.id,
            'quotation_number': 'QTN-TEST-999',
            'date': '2026-08-01',
            'valid_until': '2026-08-31',
            'items': [
                {
                    'product_id': self.prod_200_18.id,
                    'quantity': 3,
                    'rate': 200,
                    'discount': 50
                }
            ]
        }
        res = QuotationService.create_quotation(self.company, None, data)
        self.assertTrue(res['success'])
        
        q = Quotation.objects.get(id=res['quotation_id'])
        self.assertEqual(q.subtotal, Decimal('600.00'))
        self.assertEqual(q.discount_total, Decimal('50.00'))
        self.assertEqual(q.taxable_value, Decimal('550.00'))
        self.assertEqual(q.igst_total, Decimal('99.00'))
        self.assertEqual(q.grand_total, Decimal('649.00'))
