import os
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from decimal import Decimal

# --- ADMIN / SAAS SETTINGS MODELS ---

class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    yearly_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    
    # Limits
    user_limit = models.IntegerField(default=5)
    invoice_limit = models.IntegerField(default=100)
    product_limit = models.IntegerField(default=100)
    customer_limit = models.IntegerField(default=100)
    storage_limit_mb = models.IntegerField(default=512)
    trial_days = models.IntegerField(default=14)
    
    # Feature Flags
    inventory_enabled = models.BooleanField(default=True)
    gst_reports_enabled = models.BooleanField(default=True)
    e_invoice_enabled = models.BooleanField(default=False)
    e_way_bill_enabled = models.BooleanField(default=False)
    advanced_reports_enabled = models.BooleanField(default=False)
    accounting_enabled = models.BooleanField(default=False)
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Company(models.Model):
    BUSINESS_TYPES = [
        ('PROPRIETORSHIP', 'Sole Proprietorship'),
        ('PARTNERSHIP', 'Partnership'),
        ('LLP', 'Limited Liability Partnership'),
        ('PVT_LTD', 'Private Limited Company'),
        ('LTD', 'Public Limited Company'),
        ('OTHER', 'Other'),
    ]
    
    GST_STATUS_CHOICES = [
        ('REGISTERED', 'Registered Regular'),
        ('COMPOSITION', 'Composition Scheme'),
        ('UNREGISTERED', 'Unregistered'),
        ('CONSUMER', 'Consumer'),
    ]

    SUBSCRIPTION_STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('TRIAL', 'Trial'),
        ('SUSPENDED', 'Suspended'),
        ('EXPIRED', 'Expired'),
    ]

    # Business Information
    name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=200, blank=True, null=True)
    business_type = models.CharField(max_length=30, choices=BUSINESS_TYPES, default='PROPRIETORSHIP')
    gst_status = models.CharField(max_length=20, choices=GST_STATUS_CHOICES, default='UNREGISTERED')
    gstin = models.CharField(max_length=15, blank=True, null=True)
    pan = models.CharField(max_length=10, blank=True, null=True)
    email = models.EmailField()
    mobile = models.CharField(max_length=15)
    website = models.CharField(max_length=255, blank=True, null=True)
    other_website = models.CharField(max_length=255, blank=True, null=True)
    
    # Address
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    state_code = models.CharField(max_length=2)  # e.g., '27' for Maharashtra
    pincode = models.CharField(max_length=6)
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)
    signature = models.ImageField(upload_to='company_signatures/', blank=True, null=True)
    stamp = models.ImageField(upload_to='company_stamps/', blank=True, null=True)

    # Subscription
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True)
    subscription_start_date = models.DateField(blank=True, null=True)
    subscription_end_date = models.DateField(blank=True, null=True)
    subscription_status = models.CharField(max_length=20, choices=SUBSCRIPTION_STATUS_CHOICES, default='TRIAL')
    
    # Bank & UPI details
    bank_name = models.CharField(max_length=150, blank=True, null=True)
    account_holder = models.CharField(max_length=150, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    ifsc = models.CharField(max_length=20, blank=True, null=True)
    branch = models.CharField(max_length=150, blank=True, null=True)
    upi_id = models.CharField(max_length=100, blank=True, null=True)

    # Settings
    invoice_prefix = models.CharField(max_length=20, default='INV/')
    invoice_next_number = models.IntegerField(default=1)
    invoice_padding = models.IntegerField(default=5)
    financial_year = models.CharField(max_length=10, default='2026-27')
    terms_and_conditions = models.TextField(blank=True, null=True)
    authorized_signature_name = models.CharField(max_length=100, blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Companies'

    def __str__(self):
        return self.name

    def get_logo_url(self):
        if self.logo:
            try:
                import os, time
                timestamp = int(os.path.getmtime(self.logo.path)) if os.path.exists(self.logo.path) else int(time.time())
                return f"{self.logo.url}?v={timestamp}"
            except Exception:
                return self.logo.url
        return None

    def get_logo_filename(self):
        if self.logo:
            try:
                import os
                return os.path.basename(self.logo.name)
            except Exception:
                return str(self.logo.name)
        return ""

    def get_signature_url(self):
        if self.signature:
            try:
                import os, time
                timestamp = int(os.path.getmtime(self.signature.path)) if os.path.exists(self.signature.path) else int(time.time())
                return f"{self.signature.url}?v={timestamp}"
            except Exception:
                return self.signature.url
        return None

    def get_signature_filename(self):
        if self.signature:
            try:
                import os
                return os.path.basename(self.signature.name)
            except Exception:
                return str(self.signature.name)
        return ""

    def get_stamp_url(self):
        if self.stamp:
            try:
                import os, time
                timestamp = int(os.path.getmtime(self.stamp.path)) if os.path.exists(self.stamp.path) else int(time.time())
                return f"{self.stamp.url}?v={timestamp}"
            except Exception:
                return self.stamp.url
        return None

    def get_stamp_filename(self):
        if self.stamp:
            try:
                import os
                return os.path.basename(self.stamp.name)
            except Exception:
                return str(self.stamp.name)
        return ""



class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('SUPERADMIN', 'System Superadmin'),  # For Admin Panel Owner
        ('ADMIN', 'Company Admin'),           # Company Owner
        ('ACCOUNTANT', 'Accountant'),
        ('BILLING_STAFF', 'Billing Staff'),
        ('SALES_STAFF', 'Sales Staff'),
        ('INVENTORY_STAFF', 'Inventory Staff'),
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='users')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='ADMIN')
    mobile = models.CharField(max_length=15, blank=True, null=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    def is_company_user(self):
        return self.company is not None

    def get_profile_photo_url(self):
        if self.profile_photo:
            try:
                timestamp = int(self.updated_at.timestamp()) if self.updated_at else 1
                return f"{self.profile_photo.url}?v={timestamp}"
            except Exception:
                return self.profile_photo.url
        return None

    def get_profile_photo_filename(self):
        if self.profile_photo:
            try:
                return os.path.basename(self.profile_photo.name)
            except Exception:
                return str(self.profile_photo.name)
        return ""

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='otps')
    otp_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.IntegerField(default=0)
    is_verified = models.BooleanField(default=False)

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at


# --- MASTERS MODULE ---

class Category(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = 'Categories'
        unique_together = ('company', 'name')

    def __str__(self):
        return self.name


class Brand(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('company', 'name')

    def __str__(self):
        return self.name


class Unit(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)  # e.g., PCS, KG, LTR, BOX, MTR
    code = models.CharField(max_length=10)  # UQC code for GST e.g. BAG-BAGS

    class Meta:
        unique_together = ('company', 'name')

    def __str__(self):
        return self.name


class HSNSACMaster(models.Model):
    TYPES = [('HSN', 'HSN (Goods)'), ('SAC', 'SAC (Services)')]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True) # Null for system default
    code = models.CharField(max_length=20)
    description = models.TextField()
    type = models.CharField(max_length=3, choices=TYPES, default='HSN')
    category = models.CharField(max_length=100, blank=True, null=True)
    sub_category = models.CharField(max_length=100, blank=True, null=True)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    cgst_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    sgst_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    igst_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    cess_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    uqc = models.CharField(max_length=20, blank=True, null=True, default='PCS')
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_hsn_codes')
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    def get_cgst_rate(self):
        if self.cgst_rate is not None:
            return self.cgst_rate
        rate = self.gst_rate if self.gst_rate is not None else Decimal('18.00')
        return (rate / Decimal('2.00')).quantize(Decimal('0.01'))

    def get_sgst_rate(self):
        if self.sgst_rate is not None:
            return self.sgst_rate
        rate = self.gst_rate if self.gst_rate is not None else Decimal('18.00')
        return (rate / Decimal('2.00')).quantize(Decimal('0.01'))

    def get_igst_rate(self):
        if self.igst_rate is not None:
            return self.igst_rate
        return self.gst_rate if self.gst_rate is not None else Decimal('18.00')

    def save(self, *args, **kwargs):
        if self.gst_rate is None:
            self.gst_rate = Decimal('18.00')
        if self.cgst_rate is None:
            self.cgst_rate = (self.gst_rate / Decimal('2.00')).quantize(Decimal('0.01'))
        if self.sgst_rate is None:
            self.sgst_rate = (self.gst_rate / Decimal('2.00')).quantize(Decimal('0.01'))
        if self.igst_rate is None:
            self.igst_rate = self.gst_rate
        if self.cess_rate is None:
            self.cess_rate = Decimal('0.00')
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'HSN/SAC Master'
        verbose_name_plural = 'HSN/SAC Masters'
        constraints = [
            models.UniqueConstraint(
                fields=['type', 'code'],
                condition=models.Q(company__isnull=True),
                name='unique_system_hsn_sac_code'
            ),
            models.UniqueConstraint(
                fields=['company', 'type', 'code'],
                condition=models.Q(company__isnull=False),
                name='unique_company_hsn_sac_code'
            ),
        ]

    def __str__(self):
        rate = f"{self.gst_rate}%" if self.gst_rate is not None else "GST not configured"
        return f"{self.code} - {self.description[:30]} ({rate})"


class Product(models.Model):
    TYPES = [('GOODS', 'Goods'), ('SERVICES', 'Services')]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    product_type = models.CharField(max_length=10, choices=TYPES, default='GOODS')
    sku = models.CharField(max_length=100, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True)
    hsn_sac = models.ForeignKey(HSNSACMaster, on_delete=models.SET_NULL, null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)

    # Pricing
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    mrp = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    wholesale_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    retail_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    min_selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_inclusive = models.BooleanField(default=False)

    # Inventory
    track_inventory = models.BooleanField(default=True)
    allow_negative_stock = models.BooleanField(default=False)
    current_stock = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    min_stock = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    max_stock = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.category_id and self.company_id:
            try:
                cat, _ = Category.objects.get_or_create(company_id=self.company_id, name='General')
                self.category = cat
            except Exception:
                pass
        super().save(*args, **kwargs)

    def get_image_url(self):
        if self.image:
            try:
                import os, time
                if os.path.exists(self.image.path):
                    timestamp = int(os.path.getmtime(self.image.path))
                    return f"{self.image.url}?v={timestamp}"
                return self.image.url
            except Exception:
                return self.image.url
        return None



class Customer(models.Model):
    CUSTOMER_TYPES = [
        ('REGISTERED', 'Regular Registered'),
        ('COMPOSITION', 'Composition Scheme'),
        ('UNREGISTERED', 'Unregistered Business'),
        ('CONSUMER', 'Consumer / Retailer'),
        ('SEZ', 'SEZ Developer / Unit'),
        ('EXPORT', 'Overseas Export'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    business_name = models.CharField(max_length=200, blank=True, null=True)
    customer_type = models.CharField(max_length=20, choices=CUSTOMER_TYPES, default='CONSUMER')
    gstin = models.CharField(max_length=15, blank=True, null=True)
    pan = models.CharField(max_length=10, blank=True, null=True)
    
    email = models.EmailField(blank=True, null=True)
    mobile = models.CharField(max_length=15)
    alternate_mobile = models.CharField(max_length=15, blank=True, null=True)
    
    # Addresses
    billing_address = models.TextField()
    billing_city = models.CharField(max_length=100)
    billing_state = models.CharField(max_length=100)
    billing_state_code = models.CharField(max_length=2)
    billing_pincode = models.CharField(max_length=6)
    
    shipping_address = models.TextField(blank=True, null=True)
    shipping_city = models.CharField(max_length=100, blank=True, null=True)
    shipping_state = models.CharField(max_length=100, blank=True, null=True)
    shipping_state_code = models.CharField(max_length=2, blank=True, null=True)
    shipping_pincode = models.CharField(max_length=6, blank=True, null=True)

    # Credit limits & balances
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    credit_days = models.IntegerField(default=30)
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    opening_balance_type = models.CharField(max_length=2, choices=[('DR', 'Debit (Receivable)'), ('CR', 'Credit (Payable)')], default='DR')
    outstanding_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.business_name or 'Individual'}"


class Supplier(models.Model):
    SUPPLIER_TYPES = [
        ('REGISTERED', 'Regular Registered'),
        ('COMPOSITION', 'Composition Scheme'),
        ('UNREGISTERED', 'Unregistered Business'),
        ('SEZ', 'SEZ Developer / Unit'),
        ('EXPORT', 'Overseas Export'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    business_name = models.CharField(max_length=200, blank=True, null=True)
    supplier_type = models.CharField(max_length=20, choices=SUPPLIER_TYPES, default='REGISTERED')
    gstin = models.CharField(max_length=15, blank=True, null=True)
    pan = models.CharField(max_length=10, blank=True, null=True)
    
    email = models.EmailField(blank=True, null=True)
    mobile = models.CharField(max_length=15)
    alternate_mobile = models.CharField(max_length=15, blank=True, null=True)
    
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    state_code = models.CharField(max_length=2)
    pincode = models.CharField(max_length=6)

    payment_terms = models.IntegerField(default=30)  # Credit days
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    opening_balance_type = models.CharField(max_length=2, choices=[('DR', 'Debit (Receivable)'), ('CR', 'Credit (Payable)')], default='CR')
    outstanding_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.business_name or 'Individual'}"


class Warehouse(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    address = models.TextField(blank=True, null=True)
    manager = models.CharField(max_length=100, blank=True, null=True)
    contact = models.CharField(max_length=15, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class StockMovement(models.Model):
    TYPES = [
        ('OPENING', 'Opening Stock'),
        ('PURCHASE', 'Purchase'),
        ('SALE', 'Sale'),
        ('SALES_RETURN', 'Sales Return'),
        ('PURCHASE_RETURN', 'Purchase Return'),
        ('ADJUSTMENT', 'Stock Adjustment'),
        ('TRANSFER_IN', 'Warehouse Stock Transfer (In)'),
        ('TRANSFER_OUT', 'Warehouse Stock Transfer (Out)'),
        ('DAMAGE', 'Damage / Waste'),
        ('EXPIRY', 'Expired Stock'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_movements')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stock_movements')
    quantity = models.DecimalField(max_digits=12, decimal_places=2)  # Positive for additions, negative for reductions
    movement_type = models.CharField(max_length=20, choices=TYPES)
    reference_id = models.IntegerField(blank=True, null=True)  # Links to related Invoice ID, PurchaseBill ID, etc.
    reference_no = models.CharField(max_length=100, blank=True, null=True)  # Document number e.g., INV-001
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.product.name} ({self.get_movement_type_display()}): {self.quantity}"


# --- TRANSACTION MODULES ---

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('POSTED', 'Posted'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Paid'),
        ('CANCELLED', 'Cancelled'),
    ]

    PAYMENT_METHODS = [
        ('CASH', 'Cash'),
        ('BANK', 'Bank Transfer'),
        ('UPI', 'UPI'),
        ('CARD', 'Card'),
        ('CHEQUE', 'Cheque'),
        ('MIXED', 'Mixed Methods'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    invoice_number = models.CharField(max_length=50)
    invoice_date = models.DateField()
    due_date = models.DateField()
    
    # GST Fields
    place_of_supply = models.CharField(max_length=100) # State Name
    place_of_supply_code = models.CharField(max_length=2)  # State Code
    reverse_charge = models.BooleanField(default=False)
    
    # Financial Totals
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    discount_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    igst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cess_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    round_off = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # Payment Details Fields
    PAYMENT_STATUS_CHOICES = [
        ('UNPAID', 'Unpaid'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Paid'),
    ]
    advance_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    amount_paid_now = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    payment_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    total_payment_received = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    balance_due = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='UNPAID')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='CASH')
    
    notes = models.TextField(blank=True, null=True)
    terms = models.TextField(blank=True, null=True)
    
    # E-Invoice / E-Way Bill info
    irn = models.CharField(max_length=100, blank=True, null=True)
    ack_no = models.CharField(max_length=50, blank=True, null=True)
    ack_date = models.DateTimeField(blank=True, null=True)
    signed_qr_data = models.TextField(blank=True, null=True)
    
    eway_bill_no = models.CharField(max_length=20, blank=True, null=True)
    eway_bill_date = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'invoice_number')

    def outstanding_amount(self):
        if self.balance_due is not None and self.balance_due > Decimal('0.00'):
            return self.balance_due
        return max(Decimal('0.00'), self.grand_total - self.paid_amount)

    @property
    def total_tax(self):
        return (self.cgst_total or Decimal('0.00')) + (self.sgst_total or Decimal('0.00')) + (self.igst_total or Decimal('0.00')) + (self.cess_total or Decimal('0.00'))

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.name} (Total: {self.grand_total})"


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00')) # item level discount amount
    taxable_value = models.DecimalField(max_digits=12, decimal_places=2)
    
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cess_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    hsn_sac_code = models.CharField(max_length=20, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)

    @property
    def hsn_code(self):
        if self.hsn_sac_code:
            return self.hsn_sac_code
        if self.product and self.product.hsn_sac:
            return self.product.hsn_sac.code
        return ""

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


# --- OTHER TRANSACTION ENTITIES (QUOTATIONS, SO, CHALLAN, PROFORMA) ---

class Quotation(models.Model):
    STATUS_CHOICES = [('DRAFT', 'Draft'), ('SENT', 'Sent'), ('ACCEPTED', 'Accepted'), ('REJECTED', 'Rejected'), ('EXPIRED', 'Expired'), ('CONVERTED', 'Converted')]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    quotation_number = models.CharField(max_length=50)
    date = models.DateField()
    valid_until = models.DateField()
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    discount_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    igst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cess_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    round_off = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    notes = models.TextField(blank=True, null=True)
    terms = models.TextField(blank=True, null=True)
    payment_terms = models.CharField(max_length=255, blank=True, null=True, default='As specified in proposal')
    converted_to_invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True)
    converted_to_sales_order = models.ForeignKey('SalesOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='source_quotations')

    class Meta:
        unique_together = ('company', 'quotation_number')


class QuotationPredefinedTerm(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    term_text = models.TextField()
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'id']

    def __str__(self):
        return self.term_text[:50]


class QuotationSelectedTerm(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='selected_terms')
    predefined_term = models.ForeignKey(QuotationPredefinedTerm, on_delete=models.SET_NULL, null=True, blank=True)
    term_text = models.TextField()
    display_order = models.IntegerField(default=0)
    is_custom = models.BooleanField(default=False)

    class Meta:
        ordering = ['display_order', 'id']

    def __str__(self):
        return f"Term for {self.quotation.quotation_number}: {self.term_text[:30]}"


class QuotationItem(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=12, decimal_places=2)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    hsn_sac_code = models.CharField(max_length=20, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)

    @property
    def hsn_code(self):
        if self.hsn_sac_code:
            return self.hsn_sac_code
        if self.product and self.product.hsn_sac:
            return self.product.hsn_sac.code
        return ""


class SalesOrder(models.Model):
    STATUS_CHOICES = [('DRAFT', 'Draft'), ('PENDING', 'Pending Delivery'), ('PARTIALLY_DELIVERED', 'Partially Delivered'), ('DELIVERED', 'Delivered'), ('CANCELLED', 'Cancelled'), ('INVOICED', 'Invoiced')]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    order_number = models.CharField(max_length=50)
    order_date = models.DateField()
    expected_delivery = models.DateField()
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    discount_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    igst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cess_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    round_off = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    notes = models.TextField(blank=True, null=True)
    terms = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('company', 'order_number')


class SalesOrderItem(models.Model):
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=12, decimal_places=2)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cess_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    hsn_sac_code = models.CharField(max_length=20, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)

    @property
    def hsn_code(self):
        if self.hsn_sac_code:
            return self.hsn_sac_code
        if self.product and self.product.hsn_sac:
            return self.product.hsn_sac.code
        return ""


class DeliveryChallan(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    challan_number = models.CharField(max_length=50)
    date = models.DateField()
    transport_details = models.CharField(max_length=250, blank=True, null=True)
    vehicle_number = models.CharField(max_length=20, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    is_invoiced = models.BooleanField(default=False)

    class Meta:
        unique_together = ('company', 'challan_number')


class DeliveryChallanItem(models.Model):
    delivery_challan = models.ForeignKey(DeliveryChallan, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=20, blank=True, null=True)


class ProformaInvoice(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    proforma_number = models.CharField(max_length=50)
    date = models.DateField()
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    discount_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    igst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cess_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    round_off = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    terms = models.TextField(blank=True, null=True)
    is_converted = models.BooleanField(default=False)

    class Meta:
        unique_together = ('company', 'proforma_number')


class ProformaInvoiceItem(models.Model):
    proforma_invoice = models.ForeignKey(ProformaInvoice, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=12, decimal_places=2)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cess_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)


# --- PURCHASE MODULES ---

class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SENT', 'Sent'),
        ('CONFIRMED', 'Confirmed'),
        ('PARTIALLY_RECEIVED', 'Partially Received'),
        ('RECEIVED', 'Received'),
        ('CANCELLED', 'Cancelled'),
        ('CLOSED', 'Closed'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_orders')
    supplier_name_snapshot = models.CharField(max_length=200, null=True, blank=True)
    supplier_phone_snapshot = models.CharField(max_length=50, null=True, blank=True)
    supplier_email_snapshot = models.CharField(max_length=100, null=True, blank=True)
    supplier_gstin_snapshot = models.CharField(max_length=20, null=True, blank=True)
    supplier_pan_snapshot = models.CharField(max_length=20, null=True, blank=True)
    supplier_address_snapshot = models.TextField(null=True, blank=True)
    supplier_state_snapshot = models.CharField(max_length=100, null=True, blank=True)
    supplier_state_code_snapshot = models.CharField(max_length=10, null=True, blank=True)

    po_number = models.CharField(max_length=50)
    po_date = models.DateField()
    expected_delivery_date = models.DateField(null=True, blank=True)
    supplier_reference = models.CharField(max_length=100, null=True, blank=True)
    supplier_reference_date = models.DateField(null=True, blank=True)
    
    payment_terms = models.TextField(null=True, blank=True)
    delivery_terms = models.TextField(null=True, blank=True)
    warranty_terms = models.TextField(null=True, blank=True)
    return_terms = models.TextField(null=True, blank=True)
    special_instructions = models.TextField(null=True, blank=True)
    shipping_method = models.CharField(max_length=100, null=True, blank=True)
    
    warehouse = models.ForeignKey('Warehouse', on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_orders')
    place_of_supply = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    state_code = models.CharField(max_length=10, null=True, blank=True)
    
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    discount_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taxable_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    igst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cess_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    round_off = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    notes = models.TextField(null=True, blank=True)
    internal_notes = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='DRAFT')
    
    created_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_purchase_orders')
    converted_to_purchase_bill = models.ForeignKey('PurchaseBill', on_delete=models.SET_NULL, null=True, blank=True, related_name='source_purchase_orders')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def taxable_value(self):
        return self.taxable_amount

    @taxable_value.setter
    def taxable_value(self, val):
        self.taxable_amount = val

    class Meta:
        unique_together = ('company', 'po_number')
        ordering = ['-po_date', '-created_at']

    def __str__(self):
        return f"{self.po_number} - {self.supplier.name} ({self.grand_total})"


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    product_name_snapshot = models.CharField(max_length=255)
    item_image = models.ImageField(upload_to='purchase_order_item_photos/', null=True, blank=True)
    description_snapshot = models.TextField(null=True, blank=True)
    hsn_sac_snapshot = models.CharField(max_length=20, null=True, blank=True)
    uqc_snapshot = models.CharField(max_length=20, null=True, blank=True)
    
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cess_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)

    @property
    def taxable_value(self):
        return self.taxable_amount

    @taxable_value.setter
    def taxable_value(self, val):
        self.taxable_amount = val

    @property
    def hsn_code(self):
        if self.hsn_sac_snapshot:
            return self.hsn_sac_snapshot
        if self.product and self.product.hsn_sac:
            return self.product.hsn_sac.code
        return ""

    def __str__(self):
        return f"{self.product_name_snapshot} x {self.quantity}"


class PurchaseBill(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('POSTED', 'Posted'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Paid'),
        ('CANCELLED', 'Cancelled'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_bills')
    supplier_bill_no = models.CharField(max_length=50)
    bill_date = models.DateField()
    due_date = models.DateField()
    
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    discount_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    igst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cess_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    round_off = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    payment_method = models.CharField(max_length=50, default='CASH')
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('company', 'supplier_bill_no', 'supplier')

    def outstanding_amount(self):
        return max(Decimal('0.00'), self.grand_total - self.paid_amount)

    def __str__(self):
        return f"{self.supplier_bill_no} - {self.supplier.name} ({self.grand_total})"


class PurchaseBillItem(models.Model):
    purchase_bill = models.ForeignKey(PurchaseBill, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=12, decimal_places=2)
    
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cess_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    hsn_sac_code = models.CharField(max_length=20, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)

    @property
    def hsn_code(self):
        if self.hsn_sac_code:
            return self.hsn_sac_code
        if self.product and self.product.hsn_sac:
            return self.product.hsn_sac.code
        return ""


class PurchaseBillDocument(models.Model):
    purchase_bill = models.ForeignKey(PurchaseBill, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='purchase_bill_docs/')
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50)
    file_size = models.BigIntegerField(default=0)
    uploaded_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file_name} ({self.purchase_bill.supplier_bill_no})"



# --- CREDIT NOTES, DEBIT NOTES & RETURNS ---

class CreditNote(models.Model):
    REASONS = [
        ('SALES_RETURN', 'Sales Return'),
        ('DISCOUNT', 'Post-Sale Discount'),
        ('RATE_DIFFERENCE', 'Rate Difference / Price adjustment'),
        ('CANCELLATION', 'Invoice Cancellation'),
        ('OTHER', 'Other'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='credit_notes')
    note_number = models.CharField(max_length=50)
    note_date = models.DateField()
    reason = models.CharField(max_length=30, choices=REASONS, default='SALES_RETURN')
    
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    discount_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    igst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cess_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    round_off = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    status = models.CharField(max_length=20, choices=[('DRAFT', 'Draft'), ('POSTED', 'Posted'), ('CANCELLED', 'Cancelled')], default='DRAFT')
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('company', 'note_number')


class CreditNoteItem(models.Model):
    credit_note = models.ForeignKey(CreditNote, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=12, decimal_places=2)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cess_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)


class DebitNote(models.Model):
    REASONS = [
        ('PURCHASE_RETURN', 'Purchase Return'),
        ('DISCOUNT', 'Discount adjustment'),
        ('RATE_DIFFERENCE', 'Rate Difference'),
        ('OTHER', 'Other'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    purchase_bill = models.ForeignKey(PurchaseBill, on_delete=models.PROTECT, related_name='debit_notes')
    note_number = models.CharField(max_length=50)
    note_date = models.DateField()
    reason = models.CharField(max_length=30, choices=REASONS, default='PURCHASE_RETURN')
    
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    discount_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sgst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    igst_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    cess_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    round_off = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    status = models.CharField(max_length=20, choices=[('DRAFT', 'Draft'), ('POSTED', 'Posted'), ('CANCELLED', 'Cancelled')], default='DRAFT')
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('company', 'note_number')


class DebitNoteItem(models.Model):
    debit_note = models.ForeignKey(DebitNote, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=12, decimal_places=2)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cess_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)


# --- PAYMENTS & EXPENSES ---

class Payment(models.Model):
    TYPES = [('RECEIPT', 'Customer Receipt'), ('PAYMENT', 'Supplier Payment')]
    METHODS = [
        ('CASH', 'Cash'),
        ('BANK', 'Bank Transfer / NEFT'),
        ('UPI', 'UPI Payment'),
        ('CARD', 'Card'),
        ('CHEQUE', 'Cheque'),
        ('OTHER', 'Other'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    payment_type = models.CharField(max_length=10, choices=TYPES)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, blank=True, null=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, blank=True, null=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, blank=True, null=True, related_name='payments')
    purchase_bill = models.ForeignKey(PurchaseBill, on_delete=models.SET_NULL, blank=True, null=True, related_name='payments')
    
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=METHODS, default='CASH')
    reference_no = models.CharField(max_length=100, blank=True, null=True) # transaction ID, check number
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.payment_type} - {self.amount} ({self.payment_method})"


class ExpenseCategory(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = 'Expense Categories'
        unique_together = ('company', 'name')

    def __str__(self):
        return self.name


class Expense(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    gst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    vendor = models.CharField(max_length=200, blank=True, null=True)
    payment_method = models.CharField(max_length=50, default='CASH')
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    attachment = models.FileField(upload_to='expenses/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Expense: {self.category.name} - {self.amount}"


# --- SYSTEM MONITORING, AUDITING & NOTIFICATIONS ---

class AuditLog(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50) # e.g. LOGIN, CREATE, EDIT, CANCEL, DELETE
    module = models.CharField(max_length=100) # e.g. INVOICE, PRODUCT, CUSTOMER
    record_id = models.CharField(max_length=100, blank=True, null=True)
    old_values = models.JSONField(blank=True, null=True)
    new_values = models.JSONField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.action} on {self.module} at {self.timestamp}"


class Notification(models.Model):
    TYPES = [
        ('LOW_STOCK', 'Low Stock Alert'),
        ('OVERDUE_INVOICE', 'Invoice Overdue Notification'),
        ('PAYMENT_RECEIVED', 'Customer Payment Received'),
        ('SUBSCRIPTION', 'SaaS Subscription Event'),
        ('EINVOICE_ERR', 'E-Invoice Error'),
        ('EWAY_EXPIRY', 'E-Way Bill Expiry Warning'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPES, default='SUBSCRIPTION')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class SupportTicket(models.Model):
    PRIORITY_CHOICES = [('LOW', 'Low'), ('MEDIUM', 'Medium'), ('HIGH', 'High')]
    STATUS_CHOICES = [('OPEN', 'Open'), ('IN_PROGRESS', 'In Progress'), ('RESOLVED', 'Resolved'), ('CLOSED', 'Closed')]

    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    subject = models.CharField(max_length=250)
    description = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='MEDIUM')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Ticket #{self.id}: {self.subject} ({self.status})"


class Announcement(models.Model):
    subject = models.CharField(max_length=250)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)

    def __str__(self):
        return self.subject


class GSTTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('SALES', 'Sales Invoice'),
        ('PURCHASE', 'Purchase Bill'),
        ('CREDIT_NOTE', 'Credit Note'),
        ('DEBIT_NOTE', 'Debit Note'),
        ('EXPENSE', 'Expense'),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    reference_id = models.IntegerField()
    reference_no = models.CharField(max_length=100)
    date = models.DateField()
    gstin = models.CharField(max_length=15, blank=True, null=True)
    party_name = models.CharField(max_length=200, blank=True, null=True)
    place_of_supply = models.CharField(max_length=100, blank=True, null=True)
    product_name = models.CharField(max_length=200, blank=True, null=True)
    hsn_sac_code = models.CharField(max_length=20, blank=True, null=True)
    uqc_unit = models.CharField(max_length=20, blank=True, null=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    taxable_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cess_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    is_cancelled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def invoice_number(self):
        return self.reference_no

    @property
    def invoice_date(self):
        return self.date

    @property
    def cgst_total(self):
        return self.cgst_amount

    @property
    def sgst_total(self):
        return self.sgst_amount

    @property
    def igst_total(self):
        return self.igst_amount

    @property
    def customer(self):
        class DuckCustomer:
            def __init__(self, gstin, name):
                self.gstin = gstin
                self.name = name
        return DuckCustomer(self.gstin, self.party_name)

    def __str__(self):
        return f"{self.transaction_type} - {self.reference_no} ({self.taxable_value})"


class CustomerLedger(models.Model):
    ENTRY_TYPES = [
        ('INVOICE', 'Sales Invoice'),
        ('PAYMENT', 'Payment Receipt'),
        ('CREDIT_NOTE', 'Credit Note'),
        ('OPENING', 'Opening Balance'),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='ledger_entries')
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES)
    reference_id = models.IntegerField(null=True, blank=True)
    reference_no = models.CharField(max_length=100)
    date = models.DateField()
    description = models.TextField(blank=True, null=True)
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    running_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer.name} - {self.entry_type} - Debit: {self.debit} Credit: {self.credit}"


class SupplierLedger(models.Model):
    ENTRY_TYPES = [
        ('BILL', 'Purchase Bill'),
        ('PAYMENT', 'Supplier Payment'),
        ('DEBIT_NOTE', 'Debit Note'),
        ('OPENING', 'Opening Balance'),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='ledger_entries')
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES)
    reference_id = models.IntegerField(null=True, blank=True)
    reference_no = models.CharField(max_length=100)
    date = models.DateField()
    description = models.TextField(blank=True, null=True)
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    running_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.supplier.name} - {self.entry_type} - Debit: {self.debit} Credit: {self.credit}"


# --- GST APPLICATIONS ---

class GSTApplication(models.Model):
    STATUS_CHOICES = [
        ('Work Pending', 'Work Pending'),
        ('Work Done', 'Work Done'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='gst_applications', null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='gst_applications')
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField()
    message = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Work Pending')
    admin_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        comp = self.company.name if self.company else 'N/A'
        return f"{self.full_name} ({comp}) - {self.status}"
