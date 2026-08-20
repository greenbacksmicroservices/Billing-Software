from django import forms
from django.db import models
from django.db.models import Q
from decimal import Decimal, InvalidOperation
from .models import Company, CustomUser, Product, Customer, Supplier, Warehouse, SubscriptionPlan, Expense
from .utils import parse_money

class MoneyDecimalField(forms.DecimalField):
    """
    Form field that parses formatted Indian currency values (e.g. '₹64,900.00', '64,900.00', '64900.00')
    into numeric Python Decimal objects without throwing validation errors.
    """
    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return parse_money(value)
        except (ValueError, TypeError, InvalidOperation):
            raise forms.ValidationError(
                self.error_messages['invalid'],
                code='invalid',
                params={'value': value},
            )

def make_money_field(db_field, **kwargs):
    if isinstance(db_field, models.DecimalField):
        kwargs['form_class'] = MoneyDecimalField
    return db_field.formfield(**kwargs)

class MoneyModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in list(self.fields.items()):
            if isinstance(field, forms.DecimalField) and not isinstance(field, MoneyDecimalField):
                money_field = MoneyDecimalField(
                    max_digits=getattr(field, 'max_digits', None),
                    decimal_places=getattr(field, 'decimal_places', None),
                    required=field.required,
                    widget=field.widget,
                    label=field.label,
                    initial=field.initial,
                    help_text=field.help_text,
                    error_messages=field.error_messages,
                    min_value=getattr(field, 'min_value', None),
                    max_value=getattr(field, 'max_value', None),
                )
                self.fields[name] = money_field


class CompanyForm(MoneyModelForm):
    class Meta:
        model = Company
        fields = [
            'name', 'trade_name', 'business_type', 'gst_status', 'gstin', 'pan',
            'email', 'mobile', 'website', 'address', 'city', 'state', 'state_code', 'pincode',
            'logo', 'bank_name', 'account_holder', 'account_number', 'ifsc', 'branch', 'upi_id',
            'invoice_prefix', 'invoice_next_number', 'invoice_padding', 'financial_year',
            'terms_and_conditions', 'authorized_signature_name', 'signature', 'stamp'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'terms_and_conditions': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in ['address', 'terms_and_conditions', 'logo', 'signature', 'stamp']:
                field.widget.attrs['class'] = 'form-control'


class ProductForm(MoneyModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'product_type', 'sku', 'barcode', 'category', 'brand', 'hsn_sac', 'unit',
            'description', 'image', 'purchase_price', 'selling_price', 'mrp', 'wholesale_price',
            'retail_price', 'min_selling_price', 'tax_inclusive', 'track_inventory',
            'allow_negative_stock', 'min_stock', 'max_stock'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, company, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter foreign keys by company
        from .models import Category, Brand, Unit, HSNSACMaster
        self.fields['category'].queryset = Category.objects.filter(company=company)
        self.fields['brand'].queryset = Brand.objects.filter(company=company)
        self.fields['unit'].queryset = Unit.objects.filter(company=company)
        self.fields['hsn_sac'].queryset = HSNSACMaster.objects.filter(Q(company=company) | Q(company__isnull=True), is_active=True)
        
        for field_name, field in self.fields.items():
            if field_name != 'name':
                field.required = False
            if field_name not in ['description', 'image', 'tax_inclusive', 'track_inventory', 'allow_negative_stock']:
                field.widget.attrs['class'] = 'form-control'


class CustomerForm(MoneyModelForm):
    class Meta:
        model = Customer
        fields = [
            'name', 'business_name', 'customer_type', 'gstin', 'pan', 'email', 'mobile',
            'alternate_mobile', 'billing_address', 'billing_city', 'billing_state',
            'billing_state_code', 'billing_pincode', 'shipping_address', 'shipping_city',
            'shipping_state', 'shipping_state_code', 'shipping_pincode', 'credit_limit',
            'credit_days', 'opening_balance', 'opening_balance_type'
        ]
        widgets = {
            'billing_address': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'shipping_address': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name != 'name':
                field.required = False
            if field_name not in ['billing_address', 'shipping_address']:
                field.widget.attrs['class'] = 'form-control'

    def clean(self):
        cleaned_data = super().clean()
        gstin = cleaned_data.get('gstin')
        billing_state_code = cleaned_data.get('billing_state_code')
        if gstin and billing_state_code:
            gstin = gstin.strip()
            billing_state_code = billing_state_code.strip().zfill(2)
            gstin_state_code = gstin[:2]
            if gstin_state_code != billing_state_code:
                self.add_error('gstin', f"GSTIN state code '{gstin_state_code}' does not match selected Billing State Code '{billing_state_code}'.")
        return cleaned_data


class SupplierForm(MoneyModelForm):
    class Meta:
        model = Supplier
        fields = [
            'name', 'business_name', 'supplier_type', 'gstin', 'pan', 'email', 'mobile',
            'alternate_mobile', 'address', 'city', 'state', 'state_code', 'pincode',
            'payment_terms', 'opening_balance', 'opening_balance_type'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name != 'name':
                field.required = False
            if field_name not in ['address']:
                field.widget.attrs['class'] = 'form-control'

    def clean(self):
        cleaned_data = super().clean()
        gstin = cleaned_data.get('gstin')
        state_code = cleaned_data.get('state_code')
        if gstin and state_code:
            gstin = gstin.strip()
            state_code = state_code.strip().zfill(2)
            gstin_state_code = gstin[:2]
            if gstin_state_code != state_code:
                self.add_error('gstin', f"GSTIN state code '{gstin_state_code}' does not match selected State Code '{state_code}'.")
        return cleaned_data


class WarehouseForm(MoneyModelForm):
    class Meta:
        model = Warehouse
        fields = ['name', 'code', 'address', 'manager', 'contact', 'is_active']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in ['address', 'is_active']:
                field.widget.attrs['class'] = 'form-control'


class PlanForm(MoneyModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = [
            'name', 'description', 'monthly_price', 'yearly_price', 'gst_rate',
            'user_limit', 'invoice_limit', 'product_limit', 'customer_limit',
            'trial_days', 'inventory_enabled', 'gst_reports_enabled',
            'e_invoice_enabled', 'e_way_bill_enabled', 'advanced_reports_enabled',
            'accounting_enabled', 'is_active'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in ['description', 'inventory_enabled', 'gst_reports_enabled', 'e_invoice_enabled', 'e_way_bill_enabled', 'advanced_reports_enabled', 'accounting_enabled', 'is_active']:
                field.widget.attrs['class'] = 'form-control'


class ExpenseForm(MoneyModelForm):
    class Meta:
        model = Expense
        fields = [
            'category', 'amount', 'gst_rate', 'vendor', 'payment_method',
            'reference_no', 'description', 'attachment'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, company, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import ExpenseCategory
        self.fields['category'].queryset = ExpenseCategory.objects.filter(company=company)
        for field_name, field in self.fields.items():
            if field_name not in ['description', 'attachment']:
                field.widget.attrs['class'] = 'form-control'
