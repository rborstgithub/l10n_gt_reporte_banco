from odoo import _, models


class AccountReport(models.Model):
    _inherit = "account.report"

    _XMLID_CONCILIACION_BANCARIA = "account_reports.bank_reconciliation_report"

    def _es_exportacion_personalizada(self, opciones):
        self.ensure_one()
        reporte_banco = self.env.ref(self._XMLID_CONCILIACION_BANCARIA, raise_if_not_found=False)
        return bool(reporte_banco and self == reporte_banco and opciones.get("modo_personalizado"))

    def _obtener_lineas_resumen_personalizado(self, opciones, lineas=None):
        self.ensure_one()
        if not self._es_exportacion_personalizada(opciones):
            return []

        if lineas is None:
            self_modo_impresion = self.with_context(no_format=True)
            lineas = self_modo_impresion._filter_out_folded_children(self_modo_impresion._get_lines(opciones))

        indice_columna_importe = next(
            (
                indice
                for indice, columna in enumerate(opciones.get("columns", []))
                if columna.get("expression_label") == "amount"
            ),
            None,
        )
        if indice_columna_importe is None:
            return []

        saldo_banco = self._obtener_importe_linea(lineas, "account_reports.last_statement_balance", indice_columna_importe)
        pagos_pendientes = abs(self._obtener_importe_linea(lineas, "account_reports.outstanding_payments", indice_columna_importe))
        recibos_pendientes = self._obtener_importe_linea(lineas, "account_reports.outstanding_receipts", indice_columna_importe)
        saldo_bancario_contabilidad = saldo_banco - pagos_pendientes + recibos_pendientes

        return [
            self._construir_linea_resumen_personalizado(opciones, _("Saldo segun banco:"), saldo_banco),
            self._construir_linea_resumen_personalizado(opciones, _("(-) Cheques en Circulacion:"), pagos_pendientes),
            self._construir_linea_resumen_personalizado(opciones, _("(+) Depositos en Transito:"), recibos_pendientes),
            self._construir_linea_resumen_personalizado(opciones, _("(=) Saldo bancario y Contabilidad"), saldo_bancario_contabilidad),
        ]

    def _construir_linea_resumen_personalizado(self, opciones, etiqueta, importe):
        return {
            "label": etiqueta,
            "amount": importe,
            "amount_formatted": self._format_value(opciones, importe, figure_type="monetary", blank_if_zero=False),
        }

    def _obtener_lineas_firma(self):
        self.ensure_one()
        return [
            {
                "title": _("Hecho Por"),
                "subtitle": _("Asistente Contable"),
            },
            {
                "title": _("Revisado Por"),
                "subtitle": _("Encargada de Créditos"),
            },
            {
                "title": _("Autorizado por"),
                "subtitle": _("Contadora General"),
            },
        ]

    def _obtener_importe_linea(self, lineas, xmlid, indice_columna_importe):
        try:
            linea = self._get_line_from_xml_id(lineas, xmlid)
        except StopIteration:
            return 0.0

        columna = linea.get("columns", [])[indice_columna_importe]
        if isinstance(columna, dict):
            return columna.get("no_format") or 0.0
        return 0.0

    def _get_pdf_export_html(self, options, lines, additional_context=None, template=None):
        if self._es_exportacion_personalizada(options):
            additional_context = {
                **(additional_context or {}),
                "lineas_resumen_personalizado": self._obtener_lineas_resumen_personalizado(options, lineas=lines),
                "lineas_firma": self._obtener_lineas_firma(),
            }
        return super()._get_pdf_export_html(options, lines, additional_context=additional_context, template=template)

    def _inject_report_into_xlsx_sheet(self, options, workbook, sheet):
        super()._inject_report_into_xlsx_sheet(options, workbook, sheet)

        if not self._es_exportacion_personalizada(options):
            return

        lineas_resumen = self._obtener_lineas_resumen_personalizado(options)
        lineas_firma = self._obtener_lineas_firma()
        if not lineas_resumen and not lineas_firma:
            return

        formato_etiqueta = workbook.add_format({
            "font_name": "Arial",
            "font_color": "#666666",
            "font_size": 12,
            "top": 1,
            "left": 1,
            "right": 1,
            "bottom": 1,
        })
        formato_importe = workbook.add_format({
            "font_name": "Arial",
            "font_color": "#666666",
            "font_size": 12,
            "num_format": "#,##0.00",
            "top": 1,
            "left": 1,
            "right": 1,
            "bottom": 1,
        })
        formato_etiqueta_total = workbook.add_format({
            "font_name": "Arial",
            "font_color": "#666666",
            "font_size": 12,
            "bold": True,
            "top": 1,
            "left": 1,
            "right": 1,
            "bottom": 1,
        })
        formato_importe_total = workbook.add_format({
            "font_name": "Arial",
            "font_color": "#666666",
            "font_size": 12,
            "bold": True,
            "num_format": "#,##0.00",
            "top": 1,
            "left": 1,
            "right": 1,
            "bottom": 1,
        })

        fila_inicio = (sheet.dim_rowmax or 0) + 2
        sheet.set_column(0, 0, 46)
        sheet.set_column(1, 1, 22)

        for desplazamiento_fila, linea_resumen in enumerate(lineas_resumen):
            es_total = desplazamiento_fila == len(lineas_resumen) - 1
            fila_actual = fila_inicio + desplazamiento_fila
            sheet.write(fila_actual, 0, linea_resumen["label"], formato_etiqueta_total if es_total else formato_etiqueta)
            sheet.write_number(fila_actual, 1, linea_resumen["amount"], formato_importe_total if es_total else formato_importe)

        if not lineas_firma:
            return

        formato_linea = workbook.add_format({
            "bottom": 1,
        })
        formato_titulo_firma = workbook.add_format({
            "font_name": "Arial",
            "font_color": "#000000",
            "font_size": 11,
        })
        formato_subtitulo_firma = workbook.add_format({
            "font_name": "Arial",
            "font_color": "#000000",
            "font_size": 11,
        })

        fila_inicio_firma = fila_inicio + len(lineas_resumen) + 3
        sheet.set_column(0, 0, 24)
        sheet.set_column(1, 1, 30)

        for desplazamiento_fila, linea_firma in enumerate(lineas_firma):
            fila_actual = fila_inicio_firma + (desplazamiento_fila * 5)
            sheet.set_row(fila_actual, 24)
            sheet.merge_range(fila_actual + 1, 0, fila_actual + 1, 1, "", formato_linea)
            sheet.write(fila_actual + 2, 0, linea_firma["title"], formato_titulo_firma)
            sheet.write(fila_actual + 3, 0, linea_firma["subtitle"], formato_subtitulo_firma)
