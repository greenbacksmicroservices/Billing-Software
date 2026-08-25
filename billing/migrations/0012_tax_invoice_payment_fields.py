from django.db import migrations, models
from decimal import Decimal

def populate_historical_invoice_payments(apps, schema_editor):
    Invoice = apps.get_model('billing', 'Invoice')
    for invoice in Invoice.objects.all():
        paid = invoice.paid_amount or Decimal('0.00')
        grand = invoice.grand_total or Decimal('0.00')
        
        invoice.advance_amount = Decimal('0.00')
        invoice.amount_paid_now = paid
        invoice.total_payment_received = paid
        
        balance = max(Decimal('0.00'), grand - paid)
        invoice.balance_due = balance
        
        if grand > Decimal('0.00') and paid > Decimal('0.00'):
            invoice.payment_percentage = (paid / grand * Decimal('100.00')).quantize(Decimal('0.01'))
        else:
            invoice.payment_percentage = Decimal('0.00')
            
        if paid == Decimal('0.00'):
            invoice.payment_status = 'UNPAID'
        elif paid >= grand:
            invoice.payment_status = 'PAID'
        else:
            invoice.payment_status = 'PARTIALLY_PAID'
            
        invoice.save()

class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0011_purchaseorderitem_item_image_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='advance_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=15),
        ),
        migrations.AddField(
            model_name='invoice',
            name='amount_paid_now',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=15),
        ),
        migrations.AddField(
            model_name='invoice',
            name='payment_percentage',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=5),
        ),
        migrations.AddField(
            model_name='invoice',
            name='total_payment_received',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=15),
        ),
        migrations.AddField(
            model_name='invoice',
            name='balance_due',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=15),
        ),
        migrations.AddField(
            model_name='invoice',
            name='payment_status',
            field=models.CharField(choices=[('UNPAID', 'Unpaid'), ('PARTIALLY_PAID', 'Partially Paid'), ('PAID', 'Paid')], default='UNPAID', max_length=20),
        ),
        migrations.RunPython(populate_historical_invoice_payments, reverse_code=migrations.RunPython.noop),
    ]
