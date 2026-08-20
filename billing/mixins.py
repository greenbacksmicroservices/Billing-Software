from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

class CompanyRequiredMixin(LoginRequiredMixin):
    """
    Enforces that the user is logged in and belongs to a valid, active company.
    Admin users (SUPERADMIN role) are blocked from accessing company panels.
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        # Check if user is superadmin (system owner)
        if request.user.role == 'SUPERADMIN':
            raise PermissionDenied("System Superadmins cannot access Company Panel.")
            
        # Check if user belongs to an active company
        if not request.user.company or not request.user.company.is_active:
            raise PermissionDenied("You do not belong to an active business account.")
            
        # Check subscription status
        company = request.user.company
        if company.subscription_status == 'SUSPENDED':
            raise PermissionDenied("Your business subscription is suspended. Please contact admin.")
            
        return super().dispatch(request, *args, **kwargs)


class RoleRequiredMixin(CompanyRequiredMixin):
    """
    Limits view access to specific company roles.
    Example: allowed_roles = ['ADMIN', 'ACCOUNTANT']
    """
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        # First ensure they belong to a company
        response = super().dispatch(request, *args, **kwargs)
        if hasattr(response, 'rendered_content'): # if it returned a response, keep it
            pass
            
        if request.user.role not in self.allowed_roles and request.user.role != 'ADMIN':
            raise PermissionDenied("You do not have the required role permissions to access this page.")
            
        return super().dispatch(request, *args, **kwargs)


class CompanyQuerySetMixin:
    """
    Ensures that any model query is strictly filtered by the authenticated user's company context.
    Prevents cross-tenant URL manipulations.
    """
    def get_queryset(self):
        # Always filter the base queryset by the user's company
        queryset = super().get_queryset()
        return queryset.filter(company=self.request.user.company)


class PaginationMixin:
    """
    Mix in to handle entries-per-page (10/25/50/100) dynamically.
    """
    def get_paginate_by(self, queryset):
        try:
            limit = int(self.request.GET.get('entries', 10))
            if limit in [10, 25, 50, 100]:
                return limit
        except (ValueError, TypeError):
            pass
        return 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['entries'] = self.request.GET.get('entries', '10')
        return context


class AjaxFormMixin:
    """
    Handles both AJAX and standard Form POST submissions.
    Returns JSON response for AJAX/fetch requests and standard redirects for HTML forms.
    """
    success_message = "Record saved successfully."

    def is_ajax(self):
        return (
            self.request.headers.get('x-requested-with') == 'XMLHttpRequest' or
            'application/json' in self.request.headers.get('accept', '') or
            self.request.content_type == 'application/json'
        )

    def get_success_message(self, instance):
        if hasattr(self, 'success_message_custom'):
            return self.success_message_custom
        model_name = instance._meta.verbose_name.title() if hasattr(instance, '_meta') else 'Record'
        action = 'updated' if getattr(self, 'object', None) and self.request.method in ['POST', 'PUT'] and getattr(self, 'kwargs', {}).get('pk') else 'saved'
        return f"{model_name} {action} successfully."

    def form_valid(self, form):
        from django.contrib import messages
        from django.http import JsonResponse
        from django.db import transaction

        with transaction.atomic():
            # Automatically assign company if model has company field and user has company
            if hasattr(form.instance, 'company') and hasattr(self.request.user, 'company') and self.request.user.company:
                if not form.instance.company_id:
                    form.instance.company = self.request.user.company
            self.object = form.save()

        msg = self.get_success_message(self.object)
        if self.is_ajax():
            data = {'id': self.object.pk, 'str': str(self.object)}
            if hasattr(self.object, 'name'):
                data['name'] = self.object.name
            return JsonResponse({
                'success': True,
                'status': 'success',
                'message': msg,
                'data': data,
                'redirect_url': str(self.get_success_url())
            })
        
        messages.success(self.request, msg)
        return super().form_valid(form)

    def form_invalid(self, form):
        from django.http import JsonResponse
        if self.is_ajax():
            first_err = "Please correct the highlighted fields."
            for field, errs in form.errors.items():
                if errs:
                    first_err = f"{field}: {errs[0]}" if field != '__all__' else errs[0]
                    break
            return JsonResponse({
                'success': False,
                'status': 'error',
                'message': first_err,
                'errors': form.errors
            }, status=400)
        return super().form_invalid(form)

