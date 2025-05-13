{
    'name': 'Business Trip Management',
    'version': '1.0.0',
    'summary': 'Redirects users to different business trip views based on role',
    'description': """
This module provides a dynamic redirection to business trip management views:
- Managers and supervisors are redirected to the admin dashboard.
- Employees are redirected to a predefined business trip form.
    """,
    'author': 'A_zeril_A',
    'category': 'Human Resources',
    'sequence': 1,
    'depends': ['base', 'web', 'formio', 'formio_sale'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',     
        'views/business_trip_root_menu.xml',
        'views/business_trip_action.xml',
        'views/business_trip_sale_order_views.xml',
        'views/formio_form_business_trip_views.xml',
        'views/business_trip_settings_views.xml',
        'views/trip_status_wizard_views.xml',
        'views/required_fields_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_business_trip_management/static/src/js/custom_trip_redirect.js',
            'custom_business_trip_management/static/src/js/custom_trip_form_request.js',
        ],
        'web.assets_qweb': [
            'custom_business_trip_management/static/src/xml/business_trip_dialog.xml',
            'custom_business_trip_management/static/src/xml/business_trip_forms.xml',
        ],        
    },    
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/icon.png'],
}
