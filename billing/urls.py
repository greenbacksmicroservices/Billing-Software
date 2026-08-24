from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('login/', views.UnifiedLoginView.as_view(), name='login'),
    path('admin/login/', views.UnifiedLoginView.as_view(), name='admin_login'),
    path('company/login/', views.UnifiedLoginView.as_view(), name='company_login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.UserProfileView.as_view(), name='profile'),
    path('change-password/', views.UserChangePasswordView.as_view(), name='change_password'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('forgot-password/verify/', views.verify_otp_view, name='verify_otp'),
    path('forgot-password/reset/', views.reset_password_view, name='reset_password'),
    path('company/dashboard/chart-data/', views.CompanyDashboardChartDataView.as_view(), name='company_dashboard_chart_data'),
    path('admin/dashboard/chart-data/', views.AdminDashboardChartDataView.as_view(), name='admin_dashboard_chart_data'),

    # Admin Panel
    path('admin/dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('admin/delivery/', views.AdminDeliveryView.as_view(), name='admin_delivery'),
    path('admin/companies/', views.AdminCompaniesListView.as_view(), name='admin_companies_list'),
    path('admin/companies/add/', views.AdminCompanyCreateView.as_view(), name='admin_company_add'),
    path('admin/companies/<int:pk>/', views.AdminCompanyDetailView.as_view(), name='admin_company_view'),
    path('admin/companies/<int:pk>/edit/', views.AdminCompanyUpdateView.as_view(), name='admin_company_edit'),
    path('admin/companies/<int:pk>/status/<str:status>/', views.admin_company_status_change, name='admin_company_status'),
    path('admin/companies/<int:pk>/login-as/', views.admin_login_as_company, name='admin_login_as_company'),
    
    path('admin/plans/', views.AdminPlansView.as_view(), name='admin_plans'),
    path('admin/plans/add/', views.AdminPlanCreateView.as_view(), name='admin_plan_add'),
    path('admin/plans/<int:pk>/edit/', views.AdminPlanUpdateView.as_view(), name='admin_plan_edit'),
    path('admin/plans/<int:pk>/delete/', views.AdminPlanDeleteView.as_view(), name='admin_plan_delete'),

    path('admin/users/', views.AdminUsersView.as_view(), name='admin_users'),
    path('admin/tickets/', views.AdminTicketsView.as_view(), name='admin_tickets'),
    path('admin/tickets/<int:pk>/reply/', views.admin_ticket_reply, name='admin_ticket_reply'),
    path('admin/reports/', views.AdminReportsView.as_view(), name='admin_reports'),
    path('admin/audit-logs/', views.AdminAuditLogsView.as_view(), name='admin_audit_logs'),
    path('admin/settings/', views.AdminSettingsView.as_view(), name='admin_settings'),

    path('admin/hsn-sac-codes/', views.AdminHSNSACListView.as_view(), name='admin_hsn_sac_list'),
    path('admin/hsn-sac-codes/add/', views.admin_hsn_sac_add, name='admin_hsn_sac_add'),
    path('admin/hsn-sac-codes/<int:pk>/detail/', views.admin_hsn_sac_detail, name='admin_hsn_sac_detail'),
    path('admin/hsn-sac-codes/<int:pk>/edit/', views.admin_hsn_sac_edit, name='admin_hsn_sac_edit'),
    path('admin/hsn-sac-codes/<int:pk>/status/<str:status>/', views.admin_hsn_sac_status_change, name='admin_hsn_sac_status'),
    path('admin/hsn-sac-codes/<int:pk>/delete/', views.admin_hsn_sac_delete, name='admin_hsn_sac_delete'),
    path('admin/hsn-sac-codes/bulk-preview/', views.admin_hsn_sac_bulk_preview, name='admin_hsn_sac_bulk_preview'),
    path('admin/hsn-sac-codes/bulk-import/', views.admin_hsn_sac_bulk_import, name='admin_hsn_sac_bulk_import'),
    path('admin/hsn-sac-codes/export-error-report/', views.admin_hsn_sac_export_error_report, name='admin_hsn_sac_export_error_report'),
    path('admin/hsn-sac-codes/sample-template/', views.admin_hsn_sac_sample_template, name='admin_hsn_sac_sample_template'),
    path('admin/users/<int:pk>/change-password/', views.admin_user_change_password, name='admin_user_change_password'),
    path('api/delete/<str:model_name>/<int:pk>/', views.api_generic_delete, name='api_generic_delete'),
    path('api/profile/photo/upload/', views.api_profile_photo_upload, name='api_profile_photo_upload'),
    path('api/profile/photo/remove/', views.api_profile_photo_remove, name='api_profile_photo_remove'),
    path('api/company/branding/upload/', views.api_company_branding_upload, name='api_company_branding_upload'),
    path('api/company/branding/remove/', views.api_company_branding_remove, name='api_company_branding_remove'),
    path('api/company/customers/<int:pk>/unpaid-invoices/', views.api_customer_unpaid_invoices, name='api_customer_unpaid_invoices'),
    path('api/company/suppliers/<int:pk>/unpaid-bills/', views.api_supplier_unpaid_bills, name='api_supplier_unpaid_bills'),

    # Company Panel
    path('company/dashboard/', views.CompanyDashboardView.as_view(), name='company_dashboard'),
    path('company/delivery/', views.CompanyDeliveryView.as_view(), name='company_delivery'),
    path('company/settings/', views.CompanySettingsView.as_view(), name='company_settings'),

    # Customers & Suppliers
    path('company/customers/', views.CustomerListView.as_view(), name='customer_list'),
    path('company/customers/search/', views.customer_search_api, name='customer_search_api'),
    path('company/suppliers/search/', views.supplier_search_api, name='supplier_search_api'),
    path('company/hsn-sac/search/', views.hsn_sac_search_api, name='hsn_sac_search_api'),
    path('company/categories/search/', views.category_search_api, name='category_search_api'),
    path('company/categories/quick-add/', views.category_quick_add, name='category_quick_add'),
    path('company/brands/search/', views.brand_search_api, name='brand_search_api'),
    path('company/brands/quick-add/', views.brand_quick_add, name='brand_quick_add'),
    path('api/states/search/', views.indian_states_search_api, name='indian_states_search_api'),

    path('company/customers/quick-add/', views.customer_quick_add, name='customer_quick_add'),
    path('company/customers/add/', views.CustomerCreateView.as_view(), name='customer_add'),
    path('company/customers/<int:pk>/edit/', views.CustomerUpdateView.as_view(), name='customer_edit'),
    path('company/customers/<int:pk>/', views.CustomerDetailView.as_view(), name='customer_view'),

    path('company/suppliers/', views.SupplierListView.as_view(), name='supplier_list'),
    path('company/suppliers/add/', views.SupplierCreateView.as_view(), name='supplier_add'),
    path('company/suppliers/quick-add/', views.supplier_quick_add, name='supplier_quick_add'),
    path('company/suppliers/<int:pk>/edit/', views.SupplierUpdateView.as_view(), name='supplier_edit'),
    path('company/suppliers/<int:pk>/', views.SupplierDetailView.as_view(), name='supplier_view'),

    # Products & Inventory Masters
    path('company/products/', views.ProductListView.as_view(), name='product_list'),
    path('company/products/add/', views.ProductCreateView.as_view(), name='product_add'),
    path('company/products/<int:pk>/edit/', views.ProductUpdateView.as_view(), name='product_edit'),
    path('company/products/<int:pk>/duplicate/', views.product_duplicate, name='product_duplicate'),
    path('company/products/<int:pk>/adjust-stock/', views.product_adjust_stock, name='product_adjust_stock'),
    path('company/products/scan/', views.product_scan_barcode, name='product_scan_barcode'),
    path('company/products/hsn-lookup/', views.hsn_lookup, name='hsn_lookup'),
    path('company/products/sample-template/', views.company_product_sample_template, name='company_product_sample_template'),
    path('company/products/bulk-preview/', views.company_product_bulk_preview, name='company_product_bulk_preview'),
    path('company/products/bulk-import/', views.company_product_bulk_import, name='company_product_bulk_import'),
    path('company/products/download-error-report/', views.company_product_download_error_report, name='company_product_download_error_report'),

    path('company/warehouses/', views.WarehouseListView.as_view(), name='warehouse_list'),
    path('company/warehouses/add/', views.WarehouseCreateView.as_view(), name='warehouse_add'),
    path('company/warehouses/<int:pk>/edit/', views.WarehouseUpdateView.as_view(), name='warehouse_edit'),
    path('company/stock-ledger/', views.StockLedgerView.as_view(), name='stock_ledger'),

    # Sales Transactions
    path('company/quotations/', views.QuotationListView.as_view(), name='quotation_list'),
    path('company/quotations/add/', views.QuotationCreateView.as_view(), name='quotation_add'),
    path('company/quotations/<int:pk>/', views.QuotationDetailView.as_view(), name='quotation_view'),
    path('company/quotations/<int:pk>/edit/', views.QuotationUpdateView.as_view(), name='quotation_edit'),
    path('company/quotations/<int:pk>/pdf/', views.QuotationPDFView.as_view(), name='quotation_pdf'),
    path('company/quotations/<int:pk>/convert/', views.quotation_convert_to_invoice, name='quotation_convert'),
    path('company/quotations/<int:pk>/convert-so/', views.quotation_convert_to_sales_order, name='quotation_convert_so'),

    path('company/sales-orders/', views.SalesOrderListView.as_view(), name='sales_order_list'),
    path('company/sales-orders/add/', views.SalesOrderCreateView.as_view(), name='sales_order_add'),
    path('company/sales-orders/<int:pk>/', views.SalesOrderDetailView.as_view(), name='sales_order_view'),
    path('company/sales-orders/<int:pk>/pdf/', views.SalesOrderPDFView.as_view(), name='sales_order_pdf'),
    path('company/sales-orders/<int:pk>/convert/', views.sales_order_convert_to_invoice, name='sales_order_convert'),

    path('company/invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
    path('company/invoices/add/', views.InvoiceCreateView.as_view(), name='invoice_add'),
    path('company/invoices/<int:pk>/', views.InvoiceDetailView.as_view(), name='invoice_view'),
    path('company/invoices/<int:pk>/pdf/', views.InvoicePDFView.as_view(), name='invoice_pdf'),
    path('company/invoices/<int:pk>/cancel/', views.invoice_cancel, name='invoice_cancel'),
    path('company/invoices/<int:pk>/post/', views.invoice_post, name='invoice_post'),

    path('company/credit-notes/', views.CreditNoteListView.as_view(), name='credit_note_list'),
    path('company/credit-notes/add/', views.CreditNoteCreateView.as_view(), name='credit_note_add'),
    path('company/credit-notes/<int:pk>/', views.CreditNoteDetailView.as_view(), name='credit_note_view'),
    path('company/credit-notes/<int:pk>/pdf/', views.CreditNotePDFView.as_view(), name='credit_note_pdf'),

    # Purchase Transactions
    path('company/purchase-bills/', views.PurchaseBillListView.as_view(), name='purchase_bill_list'),
    path('company/purchase-bills/add/', views.PurchaseBillCreateView.as_view(), name='purchase_bill_add'),
    path('company/purchase-bills/<int:pk>/', views.PurchaseBillDetailView.as_view(), name='purchase_bill_view'),
    path('company/purchase-bills/<int:pk>/pdf/', views.PurchaseBillPDFView.as_view(), name='purchase_bill_pdf'),
    path('company/purchase-bills/<int:pk>/cancel/', views.purchase_bill_cancel, name='purchase_bill_cancel'),

    path('company/debit-notes/', views.DebitNoteListView.as_view(), name='debit_note_list'),
    path('company/debit-notes/add/', views.DebitNoteCreateView.as_view(), name='debit_note_add'),
    path('company/debit-notes/<int:pk>/', views.DebitNoteDetailView.as_view(), name='debit_note_view'),

    # Payments & Expenses
    path('company/payments/', views.PaymentListView.as_view(), name='payment_list'),
    path('company/payments/add-receipt/', views.PaymentReceiptCreateView.as_view(), name='payment_receipt_add'),
    path('company/payments/add-payment/', views.PaymentSupplierCreateView.as_view(), name='payment_supplier_add'),

    path('company/expenses/', views.ExpenseListView.as_view(), name='expense_list'),
    path('company/expenses/add/', views.ExpenseCreateView.as_view(), name='expense_add'),

    # GST Compliance
    path('company/gst/dashboard/', views.GSTDashboardView.as_view(), name='gst_dashboard'),
    path('company/gst/gstr1/', views.GSTR1View.as_view(), name='gst_report_gstr1'),
    path('company/gst/gstr3b/', views.GSTR3BView.as_view(), name='gst_report_gstr3b'),
    path('company/gst/calculate/', views.GSTCalculateView.as_view(), name='gst_calculate'),

    # Reports
    path('company/reports/', views.ReportsHubView.as_view(), name='reports_hub'),
    path('company/reports/profit-loss/', views.ProfitLossReportView.as_view(), name='report_profit_loss'),
    path('company/reports/hsn-sac/', views.HSNSACReportView.as_view(), name='report_hsn_sac'),

    # Company Accounts (My Account)
    path('company/my-account/', views.CompanyAccountsListView.as_view(), name='company_my_account'),
    path('company/my-account/add/', views.company_user_create_api, name='company_user_create_api'),
    path('company/my-account/<int:pk>/', views.company_user_detail_api, name='company_user_detail_api'),
    path('company/my-account/<int:pk>/edit/', views.company_user_edit_api, name='company_user_edit_api'),
    path('company/my-account/<int:pk>/change-password/', views.company_user_change_password_api, name='company_user_change_password_api'),

    # Transaction PDF Emailing
    path('company/quotations/<int:pk>/send-email/', views.company_quotation_send_email, name='quotation_send_email'),
    path('company/sales-orders/<int:pk>/send-email/', views.company_sales_order_send_email, name='sales_order_send_email'),
    path('company/invoices/<int:pk>/send-email/', views.company_invoice_send_email, name='invoice_send_email'),
    path('company/credit-notes/<int:pk>/send-email/', views.company_credit_note_send_email, name='credit_note_send_email'),
]
