# -*- coding: utf-8 -*-
{
    "name": "Conciliacion Bancaria",
    "version": "16.0.1.0.3",
    "summary": "Botones personalizados para el reporte de conciliacion bancaria",
    "category": "Accounting/Accounting",
    "author": "aquíH",
    "website": "https://www.aquih.com",
    "depends": ["account_reports", "hr"],
    "data": [
        "security/ir.model.access.csv",
        "data/account_report_templates.xml",
        "wizard/firmantes_reporte_banco_views.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "Other proprietary",
}
