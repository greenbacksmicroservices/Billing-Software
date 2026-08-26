document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');

    // On desktop, default to expanded sidebar on menu navigation (prevent auto-collapsing on page change)
    if (sidebar && window.innerWidth > 768) {
        if (sessionStorage.getItem('sidebar_collapsed') === 'true') {
            sidebar.classList.add('collapsed');
        } else {
            sidebar.classList.remove('collapsed');
        }
    }

    // Global Sidebar Toggle Function (Failsafe for header button click)
    window.toggleAppSidebar = function(e) {
        if (e) {
            e.preventDefault();
        }
        const sidebarEl = document.getElementById('sidebar');
        if (!sidebarEl) return;

        if (window.innerWidth <= 768) {
            sidebarEl.classList.toggle('open');
        } else {
            const isCollapsed = sidebarEl.classList.toggle('collapsed');
            sessionStorage.setItem('sidebar_collapsed', isCollapsed ? 'true' : 'false');
            localStorage.setItem('sidebar_collapsed', isCollapsed ? 'true' : 'false');
        }
    };

    // Sidebar toggle logic (Event Delegation)
    document.addEventListener('click', (e) => {
        const toggleBtn = e.target.closest('#toggle-sidebar');
        if (!toggleBtn) return;
        window.toggleAppSidebar(e);
    });

    // Close mobile sidebar when clicking outside
    document.addEventListener('click', (e) => {
        const sidebarEl = document.getElementById('sidebar');
        const toggleBtn = e.target.closest('#toggle-sidebar');
        if (window.innerWidth <= 768 && sidebarEl && sidebarEl.classList.contains('open')) {
            if (!sidebarEl.contains(e.target) && !toggleBtn) {
                sidebarEl.classList.remove('open');
            }
        }
    });

    // --- HEADER PROFILE DROPDOWN TOGGLE (EVENT DELEGATION) ---
    document.addEventListener('click', (e) => {
        const profileBtn = e.target.closest('#profile-btn');
        const profileDropdown = document.getElementById('profile-dropdown');

        // 1. Click on header profile trigger button (#profile-btn ONLY)
        if (profileBtn) {
            e.preventDefault();
            e.stopPropagation();
            if (profileDropdown) {
                profileDropdown.classList.toggle('open');
            }
            return;
        }

        // 2. Click INSIDE the profile dropdown panel
        if (profileDropdown && profileDropdown.contains(e.target)) {
            // If an <a> link was clicked, close the dropdown and let navigation proceed
            const link = e.target.closest('a');
            if (link) {
                profileDropdown.classList.remove('open');
            }
            return;
        }

        // 3. Click OUTSIDE both trigger button and dropdown panel
        if (profileDropdown) {
            profileDropdown.classList.remove('open');
        }
    });

    // --- DARK MODE TOGGLE (EVENT DELEGATION) ---
    document.addEventListener('click', (e) => {
        const darkToggle = e.target.closest('#dark-mode-toggle');
        if (!darkToggle) return;

        e.preventDefault();
        e.stopPropagation();

        const root = document.documentElement;
        const isDark = root.classList.toggle('dark');
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
        
        updateDarkModeToggleUI();
    });

    function updateDarkModeToggleUI() {
        const root = document.documentElement;
        const switchEl = document.querySelector('#dark-mode-toggle .theme-switch');
        if (switchEl) {
            if (root.classList.contains('dark')) {
                switchEl.classList.add('active');
            } else {
                switchEl.classList.remove('active');
            }
        }
    }

    updateDarkModeToggleUI();

    // --- SIDEBAR DROPDOWN ACCORDION LOGIC (EVENT DELEGATION) ---
    document.addEventListener('click', (e) => {
        const toggle = e.target.closest('.dropdown-toggle');
        if (!toggle) return; // Not a dropdown toggle click

        const parent = toggle.closest('.sidebar-item.dropdown');
        if (!parent) return;

        // Prevent default navigation if toggle is an <a> tag
        e.preventDefault();
        e.stopPropagation();

        // If sidebar is collapsed on desktop, hover handles it
        if (sidebar && sidebar.classList.contains('collapsed') && window.innerWidth > 768) {
            return;
        }

        const isAlreadyOpen = parent.classList.contains('open');

        // 1. Close all other open dropdowns (Accordion requirement: one open at a time)
        document.querySelectorAll('.sidebar-item.dropdown').forEach(item => {
            if (item !== parent) {
                item.classList.remove('open');
                const toggleEl = item.querySelector('.dropdown-toggle');
                if (toggleEl) toggleEl.setAttribute('aria-expanded', 'false');
                const subMenu = item.querySelector('.sidebar-sub-menu');
                if (subMenu) subMenu.style.maxHeight = '0px';
            }
        });

        // 2. Toggle current dropdown state
        const subMenu = parent.querySelector('.sidebar-sub-menu');
        if (isAlreadyOpen) {
            parent.classList.remove('open');
            toggle.setAttribute('aria-expanded', 'false');
            if (subMenu) subMenu.style.maxHeight = '0px';
        } else {
            parent.classList.add('open');
            toggle.setAttribute('aria-expanded', 'true');
            if (subMenu) {
                subMenu.style.maxHeight = 'none';
                const trueHeight = subMenu.scrollHeight;
                subMenu.style.maxHeight = '0px';
                subMenu.offsetHeight; // Force reflow
                subMenu.style.maxHeight = trueHeight + 'px';
            }
        }
    });

    // --- ACTIVE PAGE AUTO-EXPAND ON REFRESH & LOAD ---
    function initActiveSidebarMenu() {
        const currentPath = window.location.pathname;
        const subLinks = document.querySelectorAll('.sub-link');
        let activeParent = null;

        subLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (link.classList.contains('sub-item-active') || link.classList.contains('active') || (href && href !== '#' && currentPath === href)) {
                link.classList.add('sub-item-active');
                const parent = link.closest('.sidebar-item.dropdown');
                if (parent) {
                    activeParent = parent;
                }
            }
        });

        // Expand only the active parent dropdown
        document.querySelectorAll('.sidebar-item.dropdown').forEach(item => {
            const toggle = item.querySelector('.dropdown-toggle');
            const subMenu = item.querySelector('.sidebar-sub-menu');
            if (item === activeParent) {
                item.classList.add('open');
                if (toggle) toggle.setAttribute('aria-expanded', 'true');
                if (subMenu) {
                    subMenu.style.maxHeight = 'none';
                    const trueHeight = subMenu.scrollHeight;
                    subMenu.style.maxHeight = trueHeight + 'px';
                }
            } else {
                item.classList.remove('open');
                if (toggle) toggle.setAttribute('aria-expanded', 'false');
                if (subMenu) subMenu.style.maxHeight = '0px';
            }
        });

        // Highlight top-level sidebar items
        document.querySelectorAll('.sidebar-item:not(.dropdown)').forEach(item => {
            const link = item.querySelector('.sidebar-link');
            if (link) {
                const href = link.getAttribute('href');
                if (item.classList.contains('active') || (href && href !== '#' && (currentPath === href || (href !== '/' && currentPath.startsWith(href))))) {
                    item.classList.add('active');
                } else {
                    item.classList.remove('active');
                }
            }
        });
    }

    initActiveSidebarMenu();

    // Automatically fade out message toasts
    const messages = document.querySelectorAll('.message-item');
    messages.forEach(msg => {
        setTimeout(() => {
            msg.style.transition = 'opacity 0.5s ease';
            msg.style.opacity = '0';
            setTimeout(() => msg.remove(), 500);
        }, 4000);
    });
});

// --- GLOBAL INDIAN NUMBER FORMATTING UTILITIES ---
window.parseIndianNumber = function(val) {
    if (val === null || val === undefined || val === '') return 0;
    if (typeof val === 'number') return val;
    const clean = String(val).replace(/[^0-9.-]/g, '');
    const num = parseFloat(clean);
    return isNaN(num) ? 0 : num;
};

window.formatIndianNumber = function(val, decimals = 2) {
    if (val === null || val === undefined || val === '') return '';
    let num = window.parseIndianNumber(val);
    const isNegative = num < 0;
    num = Math.abs(num);

    let strVal = (decimals !== null && decimals >= 0) ? num.toFixed(decimals) : String(num);
    let parts = strVal.split('.');
    let intPart = parts[0];
    let decPart = parts.length > 1 ? '.' + parts[1] : '';

    let formattedInt = '';
    if (intPart.length <= 3) {
        formattedInt = intPart;
    } else {
        let last3 = intPart.substring(intPart.length - 3);
        let rest = intPart.substring(0, intPart.length - 3);
        let groups = [];
        while (rest.length > 2) {
            groups.unshift(rest.substring(rest.length - 2));
            rest = rest.substring(0, rest.length - 2);
        }
        if (rest.length > 0) {
            groups.unshift(rest);
        }
        formattedInt = groups.join(',') + ',' + last3;
    }

    let result = formattedInt + decPart;
    return isNegative ? '-' + result : result;
};

window.formatIndianCurrency = function(val, decimals = 2) {
    if (val === null || val === undefined || val === '') return '₹0.00';
    const formatted = window.formatIndianNumber(val, decimals);
    if (!formatted) return '₹0.00';
    if (formatted.startsWith('-')) {
        return '-₹' + formatted.substring(1);
    }
    return '₹' + formatted;
};

window.cleanCurrencyInput = function(val) {
    if (val === null || val === undefined || val === '') return '0.00';
    if (typeof val === 'number') return val.toFixed(2);
    const clean = String(val).replace(/[^0-9.-]/g, '');
    const num = parseFloat(clean);
    return isNaN(num) ? '0.00' : num.toFixed(2);
};

window.parseMoney = window.parseIndianNumber;
window.formatMoney = window.formatIndianCurrency;

// --- GLOBAL CSRF COOKIE HELPER ---
window.getCookie = function(name = 'csrftoken') {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
};

// --- GLOBAL BUTTON LOADING STATE HELPER ---
window.setButtonLoading = function(btn, isLoading, loadingText = 'Saving...') {
    if (!btn) return;
    if (isLoading) {
        if (!btn.dataset.originalHtml) {
            btn.dataset.originalHtml = btn.innerHTML;
        }
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${loadingText}`;
    } else {
        btn.disabled = false;
        if (btn.dataset.originalHtml) {
            btn.innerHTML = btn.dataset.originalHtml;
        }
    }
};

// --- GLOBAL TOAST NOTIFICATION HELPER ---
if (typeof window.showToast !== 'function') {
    window.showToast = function(type, message) {
        let wrapper = document.getElementById('toast-wrapper');
        if (!wrapper) {
            wrapper = document.createElement('div');
            wrapper.className = 'toast-wrapper';
            wrapper.id = 'toast-wrapper';
            document.body.appendChild(wrapper);
        }
        const toast = document.createElement('div');
        toast.className = `toast-item ${type}`;
        let icon = 'fa-circle-info';
        if (type === 'success') icon = 'fa-circle-check';
        if (type === 'error' || type === 'danger') icon = 'fa-circle-exclamation';
        if (type === 'warning') icon = 'fa-triangle-exclamation';

        toast.innerHTML = `
            <i class="fa-solid ${icon}"></i>
            <div class="toast-message">${message}</div>
            <button class="toast-close-btn" onclick="this.parentElement.remove()">&times;</button>
        `;
        wrapper.appendChild(toast);
        setTimeout(() => {
            if (toast && toast.parentElement) toast.remove();
        }, 4500);
    };
}

// --- GLOBAL DOUBLE SUBMISSION GUARD FOR REGULAR POST FORMS ---
document.addEventListener('submit', (e) => {
    const form = e.target;
    if (form && form.method && form.method.toUpperCase() === 'POST' && !e.defaultPrevented) {
        const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
        if (submitBtn && !submitBtn.disabled) {
            const btnText = submitBtn.innerText.trim() || 'Submitting...';
            const actionText = btnText.toLowerCase().includes('create') ? 'Creating...' : 
                               btnText.toLowerCase().includes('save') ? 'Saving...' : 
                               btnText.toLowerCase().includes('update') ? 'Updating...' : 'Submitting...';
            window.setButtonLoading(submitBtn, true, actionText);
        }
    }
});

// --- GLOBAL INDIAN MONEY PARSER & FORMATTER ---
window.parseMoney = function(val) {
    if (val === null || val === undefined) return 0;
    if (typeof val === 'number') return isNaN(val) ? 0 : val;
    let s = String(val).trim()
        .replace(/[₹$€£\u20B9\u00A0]/g, '')
        .replace(/\b(inr|rupees?)\b/gi, '')
        .replace(/rs\.?/gi, '')
        .replace(/,/g, '')
        .replace(/\s+/g, '');
    if (s === '' || s === '-') return 0;
    let num = parseFloat(s);
    return isNaN(num) ? 0 : num;
};

window.formatIndianCurrency = function(num) {
    if (num === null || num === undefined || isNaN(num)) return '₹0.00';
    let isNeg = num < 0;
    let absNum = Math.abs(num);
    let fixed = absNum.toFixed(2);
    let parts = fixed.split('.');
    let intPart = parts[0];
    let decPart = '.' + parts[1];
    if (intPart.length > 3) {
        let last3 = intPart.substring(intPart.length - 3);
        let other = intPart.substring(0, intPart.length - 3);
        let groups = [];
        while (other.length > 2) {
            groups.unshift(other.substring(other.length - 2));
            other = other.substring(0, other.length - 2);
        }
        if (other.length > 0) groups.unshift(other);
        intPart = groups.join(',') + ',' + last3;
    }
    return (isNeg ? '-₹' : '₹') + intPart + decPart;
};

// Safe UI display / text helpers
window.setElementDisplay = function(id, value) {
    if (!id) return;
    let el = document.getElementById(id);
    if (!el && id === 'cn-error-msg') {
        const modalBody = document.querySelector('#credit-note-modal .modal-body');
        if (modalBody) {
            el = document.createElement('div');
            el.id = 'cn-error-msg';
            el.className = 'message-item error';
            el.style.display = 'none';
            el.style.marginBottom = '1rem';
            modalBody.insertBefore(el, modalBody.firstChild);
        }
    }
    if (el) {
        el.style.display = value;
    }
};

window.setElementText = function(id, text) {
    if (!id) return;
    let el = document.getElementById(id);
    if (!el && id === 'cn-error-msg') {
        const modalBody = document.querySelector('#credit-note-modal .modal-body');
        if (modalBody) {
            el = document.createElement('div');
            el.id = 'cn-error-msg';
            el.className = 'message-item error';
            el.style.display = 'none';
            el.style.marginBottom = '1rem';
            modalBody.insertBefore(el, modalBody.firstChild);
        }
    }
    if (el) {
        el.innerText = text;
    }
};

// --- GLOBAL UNIVERSAL TABLE EXPORT HELPER (EXCEL & CSV) ---
window.exportTableData = function(format, customFilename) {
    const table = document.querySelector('#table-container table.custom-table, table.custom-table');
    if (!table) {
        if (typeof window.showToast === 'function') {
            window.showToast('error', 'No table data found to export.');
        } else {
            alert('No table data found to export.');
        }
        return;
    }

    let rawTitle = customFilename || document.title || 'Exported_Table';
    rawTitle = rawTitle.replace(/GBL Billing|GST Billing System|-/gi, '').trim() || 'Data_Export';
    const title = rawTitle.replace(/[^a-zA-Z0-9_-]/g, '_');
    const dateStr = new Date().toISOString().slice(0, 10);
    const filename = `${title}_${dateStr}.${format === 'excel' ? 'csv' : 'csv'}`;

    const headers = [];
    const headerCells = table.querySelectorAll('thead tr th');
    const skipIndices = [];

    headerCells.forEach((th, idx) => {
        const text = th.innerText.trim();
        if (text.toLowerCase() === 'actions' || text.toLowerCase() === 'action') {
            skipIndices.push(idx);
        } else {
            headers.push(text);
        }
    });

    const rowsData = [];
    const bodyRows = table.querySelectorAll('tbody tr');

    bodyRows.forEach(tr => {
        const cells = tr.querySelectorAll('td');
        if (cells.length <= 1 && skipIndices.length > 0) return;
        
        const row = [];
        cells.forEach((td, idx) => {
            if (skipIndices.includes(idx)) return;
            let text = td.innerText.trim();
            text = text.replace(/\n+/g, ' | ').replace(/\s+/g, ' ');
            row.push(text);
        });
        if (row.length > 0) {
            rowsData.push(row);
        }
    });

    if (rowsData.length === 0) {
        if (typeof window.showToast === 'function') {
            window.showToast('warning', 'Table has no data to export.');
        } else {
            alert('Table has no data to export.');
        }
        return;
    }

    let csvContent = '\uFEFF'; // UTF-8 BOM for Microsoft Excel compatibility
    csvContent += headers.map(h => `"${h.replace(/"/g, '""')}"`).join(',') + '\r\n';

    rowsData.forEach(row => {
        csvContent += row.map(cell => `"${cell.replace(/"/g, '""')}"`).join(',') + '\r\n';
    });

    const mimeType = format === 'excel' ? 'text/csv;charset=utf-8;' : 'text/csv;charset=utf-8;';
    const blob = new Blob([csvContent], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    if (typeof window.showToast === 'function') {
        window.showToast('success', `Exported ${rowsData.length} records to ${filename}!`);
    }
};


