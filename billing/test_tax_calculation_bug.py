from decimal import Decimal
from django.test import TestCase
from billing.models import Company, Customer, Product, HSNSACMaster, Invoice, InvoiceItem, Quotation, QuotationItem, SalesOrder, SalesOrderItem
from billing.utils import (
    calculate_line_item_financials,
    recalculate_invoice_totals,
    recalculate_quotation_totals,
    recalculate_sales_order_totals
)

class TaxCalculationBugTestCase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Test Company",
            state="Maharashtra",
            state_code="27",
            financial_year="2025-26"
        )
        self.customer_intra = Customer.objects.create(
            company=self.company,
            name="Intra Customer",
            billing_state="Maharashtra",
            billing_state_code="27"
        )
        self.customer_inter = Customer.objects.create(
            company=self.company,
            name="Inter Customer",
            billing_state="Gujarat",
            billing_state_code="24"
        )
        self.hsn_18 = HSNSACMaster.objects.create(
            code="1818",
            description="18 Percent HSN",
            gst_rate=Decimal('18.00'),
            is_active=True
        )
        self.hsn_5 = HSNSACMaster.objects.create(
            code="0505",
            description="5 Percent HSN",
            gst_rate=Decimal('5.00'),
            is_active=True
        )
        self.prod_18 = Product.objects.create(
            company=self.company,
            name="Product 18%",
            selling_price=Decimal('200.00'),
            hsn_sac=self.hsn_18
        )
        self.prod_5 = Product.objects.create(
            company=self.company,
            name="Product 5%",
            selling_price=Decimal('500.00'),
            hsn_sac=self.hsn_5
        )

    def test_1_basic_calculation(self):
        """
        TEST 1: Price = ₹200, Qty = 1, Discount = ₹0, GST = 18%
        Expected: Subtotal = ₹200, Taxable = ₹200, GST = ₹36, Grand Total = ₹236
        """
        res = calculate_line_item_financials(
            quantity=1, rate=200, discount=0, gst_rate=18,
            company_state_code="27", pos_state_code="24"
        )
        self.assertEqual(res['line_subtotal'], Decimal('200.00'))
        self.assertEqual(res['line_discount'], Decimal('0.00'))
        self.assertEqual(res['line_taxable'], Decimal('200.00'))
        self.assertEqual(res['igst_amount'], Decimal('36.00'))
        self.assertEqual(res['line_total'], Decimal('236.00'))

    def test_2_discount_calculation(self):
        """
        TEST 2: Price = ₹200, Qty = 1, Discount = ₹20, GST = 18%
        Expected: Subtotal = ₹200, Taxable = ₹180, GST = ₹32.40, Grand Total = ₹212.40
        """
        res = calculate_line_item_financials(
            quantity=1, rate=200, discount=20, gst_rate=18,
            company_state_code="27", pos_state_code="24"
        )
        self.assertEqual(res['line_subtotal'], Decimal('200.00'))
        self.assertEqual(res['line_discount'], Decimal('20.00'))
        self.assertEqual(res['line_taxable'], Decimal('180.00'))
        self.assertEqual(res['igst_amount'], Decimal('32.40'))
        self.assertEqual(res['line_total'], Decimal('212.40'))

    def test_3_quantity_calculation(self):
        """
        TEST 3: Price = ₹200, Qty = 3, Discount = ₹0, GST = 18%
        Expected: Subtotal = ₹600, Taxable = ₹600, GST = ₹108, Grand Total = ₹708
        """
        res = calculate_line_item_financials(
            quantity=3, rate=200, discount=0, gst_rate=18,
            company_state_code="27", pos_state_code="24"
        )
        self.assertEqual(res['line_subtotal'], Decimal('600.00'))
        self.assertEqual(res['line_discount'], Decimal('0.00'))
        self.assertEqual(res['line_taxable'], Decimal('600.00'))
        self.assertEqual(res['igst_amount'], Decimal('108.00'))
        self.assertEqual(res['line_total'], Decimal('708.00'))

    def test_4_discount_plus_quantity_calculation(self):
        """
        TEST 4: Price = ₹200, Qty = 3, Discount = ₹50, GST = 18%
        Expected: Subtotal = ₹600, Taxable = ₹550, GST = ₹99, Grand Total = ₹649
        """
        res = calculate_line_item_financials(
            quantity=3, rate=200, discount=50, gst_rate=18,
            company_state_code="27", pos_state_code="24"
        )
        self.assertEqual(res['line_subtotal'], Decimal('600.00'))
        self.assertEqual(res['line_discount'], Decimal('50.00'))
        self.assertEqual(res['line_taxable'], Decimal('550.00'))
        self.assertEqual(res['igst_amount'], Decimal('99.00'))
        self.assertEqual(res['line_total'], Decimal('649.00'))

    def test_5_multiple_products(self):
        """
        TEST 5: Two products with different GST rates.
        Product A: ₹1000 x 2 = ₹2000, Disc = ₹100, Taxable = ₹1900, GST 18% = ₹342
        Product B: ₹500 x 1 = ₹500, Disc = ₹0, Taxable = ₹500, GST 5% = ₹25
        Aggregated: Subtotal = ₹2500, Discount = ₹100, Taxable = ₹2400, Total GST = ₹367, Grand Total = ₹2767
        """
        inv = Invoice.objects.create(
            company=self.company,
            customer=self.customer_inter,
            invoice_number="INV-TEST-05",
            invoice_date="2025-01-01",
            due_date="2025-01-31",
            place_of_supply="Gujarat",
            place_of_supply_code="24"
        )
        InvoiceItem.objects.create(
            invoice=inv, product=self.prod_18, quantity=Decimal('2.00'), rate=Decimal('1000.00'),
            discount=Decimal('100.00'), taxable_value=Decimal('0.00'), gst_rate=Decimal('18.00'),
            total_amount=Decimal('0.00')
        )
        InvoiceItem.objects.create(
            invoice=inv, product=self.prod_5, quantity=Decimal('1.00'), rate=Decimal('500.00'),
            discount=Decimal('0.00'), taxable_value=Decimal('0.00'), gst_rate=Decimal('5.00'),
            total_amount=Decimal('0.00')
        )
        recalculate_invoice_totals(inv)

        self.assertEqual(inv.subtotal, Decimal('2500.00'))
        self.assertEqual(inv.discount_total, Decimal('100.00'))
        self.assertEqual(inv.taxable_value, Decimal('2400.00'))
        self.assertEqual(inv.igst_total, Decimal('367.00'))
        self.assertEqual(inv.grand_total, Decimal('2767.00'))

    def test_6_interstate_transaction(self):
        """
        TEST 6: Interstate transaction (Company 27 vs Customer 24).
        Expected: CGST = 0, SGST = 0, IGST = correct amount
        """
        res = calculate_line_item_financials(
            quantity=1, rate=1000, discount=0, gst_rate=18,
            company_state_code="27", pos_state_code="24"
        )
        self.assertEqual(res['cgst_amount'], Decimal('0.00'))
        self.assertEqual(res['sgst_amount'], Decimal('0.00'))
        self.assertEqual(res['igst_amount'], Decimal('180.00'))

    def test_7_intrastate_transaction(self):
        """
        TEST 7: Intra-state transaction (Company 27 vs Customer 27).
        Expected: IGST = 0, CGST = 50% GST, SGST = 50% GST
        """
        res = calculate_line_item_financials(
            quantity=1, rate=1000, discount=0, gst_rate=18,
            company_state_code="27", pos_state_code="27"
        )
        self.assertEqual(res['igst_amount'], Decimal('0.00'))
        self.assertEqual(res['cgst_amount'], Decimal('90.00'))
        self.assertEqual(res['sgst_amount'], Decimal('90.00'))

    def test_percentage_discount(self):
        """
        TEST 6 (Percentage discount): Unit Price = ₹1,000, Qty = 2, Subtotal = ₹2,000, Discount = 10%
        Expected: Discount Amount = ₹200, Taxable Amount = ₹1,800, GST 18% = ₹324, Grand Total = ₹2,124
        """
        res = calculate_line_item_financials(
            quantity=2, rate=1000, discount="10%", gst_rate=18,
            company_state_code="27", pos_state_code="24"
        )
        self.assertEqual(res['line_subtotal'], Decimal('2000.00'))
        self.assertEqual(res['line_discount'], Decimal('200.00'))
        self.assertEqual(res['line_taxable'], Decimal('1800.00'))
        self.assertEqual(res['igst_amount'], Decimal('324.00'))
        self.assertEqual(res['line_total'], Decimal('2124.00'))

    def test_requirement_21_qty_progression_intrastate(self):
        """
        Req 21: Product Rate ₹300, GST 18%, Intra-state (27 to 27)
        Qty 1: Subtotal ₹300, CGST ₹27, SGST ₹27, IGST ₹0, Grand Total ₹354
        Qty 2: Subtotal ₹600, CGST ₹54, SGST ₹54, IGST ₹0, Grand Total ₹708
        Qty 5: Subtotal ₹1500, CGST ₹135, SGST ₹135, IGST ₹0, Grand Total ₹1770
        """
        # Qty 1
        r1 = calculate_line_item_financials(quantity=1, rate=300, discount=0, gst_rate=18, company_state_code="27", pos_state_code="27")
        self.assertEqual(r1['line_subtotal'], Decimal('300.00'))
        self.assertEqual(r1['cgst_amount'], Decimal('27.00'))
        self.assertEqual(r1['sgst_amount'], Decimal('27.00'))
        self.assertEqual(r1['igst_amount'], Decimal('0.00'))
        self.assertEqual(r1['line_total'], Decimal('354.00'))

        # Qty 2
        r2 = calculate_line_item_financials(quantity=2, rate=300, discount=0, gst_rate=18, company_state_code="27", pos_state_code="27")
        self.assertEqual(r2['line_subtotal'], Decimal('600.00'))
        self.assertEqual(r2['cgst_amount'], Decimal('54.00'))
        self.assertEqual(r2['sgst_amount'], Decimal('54.00'))
        self.assertEqual(r2['igst_amount'], Decimal('0.00'))
        self.assertEqual(r2['line_total'], Decimal('708.00'))

        # Qty 5
        r5 = calculate_line_item_financials(quantity=5, rate=300, discount=0, gst_rate=18, company_state_code="27", pos_state_code="27")
        self.assertEqual(r5['line_subtotal'], Decimal('1500.00'))
        self.assertEqual(r5['cgst_amount'], Decimal('135.00'))
        self.assertEqual(r5['sgst_amount'], Decimal('135.00'))
        self.assertEqual(r5['igst_amount'], Decimal('0.00'))
        self.assertEqual(r5['line_total'], Decimal('1770.00'))

    def test_requirement_22_interstate_calculation(self):
        """
        Req 22: Qty 5, Rate ₹300, GST 18%, Inter-state (27 to 24)
        Gross Subtotal = ₹1500, IGST = ₹270, CGST = ₹0, SGST = ₹0, Grand Total = ₹1770
        """
        res = calculate_line_item_financials(quantity=5, rate=300, discount=0, gst_rate=18, company_state_code="27", pos_state_code="24")
        self.assertEqual(res['line_subtotal'], Decimal('1500.00'))
        self.assertEqual(res['cgst_amount'], Decimal('0.00'))
        self.assertEqual(res['sgst_amount'], Decimal('0.00'))
        self.assertEqual(res['igst_amount'], Decimal('270.00'))
        self.assertEqual(res['line_total'], Decimal('1770.00'))

    def test_requirement_23_multiple_products_aggregation(self):
        """
        Req 23: Multiple products with different GST rates.
        Row 1: Charger Qty 3, Rate ₹300, GST 18% -> Gross ₹900, GST ₹162
        Row 2: Kurkuri Qty 2, Rate ₹150, GST 5% -> Gross ₹300, GST ₹15
        Row 3: Earphone Qty 1, Rate ₹1600, GST 18% -> Gross ₹1600, GST ₹288
        Gross Subtotal = ₹2800, Total GST = ₹465, Grand Total = ₹3265
        """
        prod_charger = Product.objects.create(company=self.company, name="USE Charger", selling_price=Decimal('300.00'), hsn_sac=self.hsn_18)
        prod_kurkuri = Product.objects.create(company=self.company, name="Kurkuri", selling_price=Decimal('150.00'), hsn_sac=self.hsn_5)
        prod_earphone = Product.objects.create(company=self.company, name="Earphone", selling_price=Decimal('1600.00'), hsn_sac=self.hsn_18)

        inv = Invoice.objects.create(
            company=self.company,
            customer=self.customer_inter,
            invoice_number="INV-REQ-23",
            invoice_date="2025-01-01",
            due_date="2025-01-31",
            place_of_supply="Gujarat",
            place_of_supply_code="24"
        )
        InvoiceItem.objects.create(invoice=inv, product=prod_charger, quantity=Decimal('3.00'), rate=Decimal('300.00'), discount=Decimal('0.00'), taxable_value=Decimal('0.00'), gst_rate=Decimal('18.00'), total_amount=Decimal('0.00'))
        InvoiceItem.objects.create(invoice=inv, product=prod_kurkuri, quantity=Decimal('2.00'), rate=Decimal('150.00'), discount=Decimal('0.00'), taxable_value=Decimal('0.00'), gst_rate=Decimal('5.00'), total_amount=Decimal('0.00'))
        InvoiceItem.objects.create(invoice=inv, product=prod_earphone, quantity=Decimal('1.00'), rate=Decimal('1600.00'), discount=Decimal('0.00'), taxable_value=Decimal('0.00'), gst_rate=Decimal('18.00'), total_amount=Decimal('0.00'))

        recalculate_invoice_totals(inv)

        self.assertEqual(inv.subtotal, Decimal('2800.00'))
        self.assertEqual(inv.igst_total, Decimal('465.00'))
        self.assertEqual(inv.grand_total, Decimal('3265.00'))
