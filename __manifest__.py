# pyright: reportUnusedExpression=false
{
    'name': 'Business Trip Management',
    'version': '1.0.0',
    'license': 'LGPL-3',
    'summary': 'Redirects users to different business trip views based on role',
    'description': """
This module provides a dynamic redirection to business trip management views:
- Managers and supervisors are redirected to the admin dashboard.
- Employees are redirected to a predefined business trip form.
    """,
    'author': 'A_zeril_A',
    'category': 'Human Resources',
    'sequence': 1,
    'depends': ['base', 'web', 'formio', 'formio_sale', 'hr', 'hr_timesheet', 'project', 'project_timesheet_time_control', 'hr_timesheet_begin_end'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/business_trip_project_data.xml',
        'data/server_action.xml',
        'data/mail_data.xml',
        'data/cron_jobs.xml',
        'views/formio_access_views.xml',
        'views/business_trip_root_menu.xml',
        'views/wizard_views.xml',        
        'views/formio_form_business_trip_views.xml',
        'views/business_trip_action.xml',
        'views/business_trip_sale_order_views.xml',
        'views/business_trip_settings_views.xml',
        'views/menu_views.xml',
        'views/mail_templates.xml',
        'demo/demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_business_trip_management/static/src/js/custom_trip_redirect.js',
            'custom_business_trip_management/static/src/js/custom_trip_form_request.js',
            'custom_business_trip_management/static/src/css/custom_status_colors.css',
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
    'demo': [
        'demo/demo.xml',
    ],
    'post_init_hook': 'post_init_hook',
}
