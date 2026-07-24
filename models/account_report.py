import io

import xlsxwriter

from odoo import _, fields, models


class AccountReport(models.Model):
    _inherit = "account.report"

    _XMLID_CONCILIACION_BANCARIA = "account_reports.bank_reconciliation_report"
    _MARKUP_PAGOS_PENDIENTES = "less_unreconciled_payment_lines"
    _MARKUP_RECIBOS_PENDIENTES = "plus_unreconciled_payment_lines"

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

        saldo_banco = self._obtener_saldo_ultimo_extracto(opciones)
        pagos_pendientes = abs(self._obtener_importe_linea(lineas, self._MARKUP_PAGOS_PENDIENTES, indice_columna_importe))
        recibos_pendientes = self._obtener_importe_linea(lineas, self._MARKUP_RECIBOS_PENDIENTES, indice_columna_importe)
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
            "amount_formatted": self.format_value(importe, figure_type="monetary", blank_if_zero=False),
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

    def _obtener_saldo_ultimo_extracto(self, opciones):
        """Replica el calculo de balance_end del generador del reporte de
        conciliacion bancaria de 16 (account_bank_reconciliation_report.py)."""
        id_diario = opciones.get("bank_reconciliation_report_journal_id")
        if not id_diario:
            return 0.0

        diario = self.env["account.journal"].browse(id_diario)
        dominio_ultimo_extracto = [("date", "<=", opciones["date"]["date_to"])]
        if not opciones.get("all_entries"):
            dominio_ultimo_extracto.append(("move_id.state", "=", "posted"))
        ultimo_extracto = diario._get_last_bank_statement(domain=dominio_ultimo_extracto)
        if not ultimo_extracto:
            return 0.0

        fecha_reporte = fields.Date.from_string(opciones["date"]["date_to"])
        lineas_hasta_fecha = ultimo_extracto.line_ids.filtered(lambda linea: linea.date <= fecha_reporte)
        return ultimo_extracto.balance_start + sum(lineas_hasta_fecha.mapped("amount"))

    def _obtener_importe_linea(self, lineas, markup, indice_columna_importe):
        # En 16 las lineas del reporte bancario se identifican por el markup
        # de su id generico, no por xmlid como en 17.
        linea = next(
            (linea for linea in lineas if self._get_markup(linea.get("id")) == markup),
            None,
        )
        if linea is None:
            return 0.0

        columnas = linea.get("columns", [])
        if indice_columna_importe >= len(columnas):
            return 0.0

        columna = columnas[indice_columna_importe]
        if isinstance(columna, dict):
            return columna.get("no_format") or 0.0
        return 0.0

    def get_html(self, options, lines, additional_context=None, template=None):
        # En 16 no existe _get_pdf_export_html: export_to_pdf pasa por get_html,
        # asi que inyectamos aqui el contexto extra del PDF personalizado.
        if self._es_exportacion_personalizada(options):
            additional_context = {
                **(additional_context or {}),
                "lineas_resumen_personalizado": self._obtener_lineas_resumen_personalizado(options, lineas=lines),
                "lineas_firma": self._obtener_lineas_firma(),
            }
        return super().get_html(options, lines, additional_context=additional_context, template=template)

    def export_to_xlsx(self, options, response=None):
        # En 16 no existe el hook _inject_report_into_xlsx_sheet, por lo que en
        # modo personalizado replicamos el export estandar y añadimos las filas
        # de resumen y firmas antes de cerrar el workbook.
        if not self._es_exportacion_personalizada(options):
            return super().export_to_xlsx(options, response=response)

        # --- Copiado de account_reports 16.0, account.report.export_to_xlsx ---
        def write_with_colspan(sheet, x, y, value, colspan, style):
            if colspan == 1:
                sheet.write(y, x, value, style)
            else:
                sheet.merge_range(y, x, y, x + colspan - 1, value, style)
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {
            'in_memory': True,
            'strings_to_formulas': False,
        })
        sheet = workbook.add_worksheet(self.name[:31])

        title_format = workbook.add_format({'font_name': 'Arial', 'bold': True, 'bottom': 2})
        default_format_props = {'font_name': 'Arial', 'font_color': '#666666', 'font_size': 12}
        workbook_formats = {
            0: {
                'text': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 6}),
                'date': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 6, 'num_format': 'yyyy-mm-dd'}),
                'total': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 6}),
                'col1_text': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 6}),
                'col1_date': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 6, 'num_format': 'yyyy-mm-dd'}),
                'col1_total': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 6}),
            },
            1: {
                'text': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 1}),
                'date': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 1, 'num_format': 'yyyy-mm-dd'}),
                'total': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 1}),
                'col1_text': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 1, 'indent': 1}),
                'col1_date': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 1, 'indent': 1, 'num_format': 'yyyy-mm-dd'}),
                'col1_total': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 1}),
            },
            2: {
                'text': workbook.add_format({**default_format_props, 'bold': True}),
                'date': workbook.add_format({**default_format_props, 'bold': True, 'num_format': 'yyyy-mm-dd'}),
                'initial': workbook.add_format(default_format_props),
                'total': workbook.add_format({**default_format_props, 'bold': True}),
                'col1_text': workbook.add_format({**default_format_props, 'bold': True, 'indent': 2}),
                'col1_date': workbook.add_format({**default_format_props, 'bold': True, 'indent': 2, 'num_format': 'yyyy-mm-dd'}),
                'col1_initial': workbook.add_format({**default_format_props, 'indent': 2}),
                'col1_total': workbook.add_format({**default_format_props, 'bold': True, 'indent': 1}),
            },
            'default': {
                'text': workbook.add_format(default_format_props),
                'date': workbook.add_format({**default_format_props, 'num_format': 'yyyy-mm-dd'}),
                'total': workbook.add_format(default_format_props),
                'col1_text': workbook.add_format({**default_format_props, 'indent': 2}),
                'col1_date': workbook.add_format({**default_format_props, 'indent': 2, 'num_format': 'yyyy-mm-dd'}),
                'col1_total': workbook.add_format({**default_format_props, 'indent': 2}),
            },
        }

        #Set the first column width to 50
        sheet.set_column(0, 0, 50)

        y_offset = 0
        x_offset = 1 # 1 and not 0 to leave space for the line name
        print_mode_self = self.with_context(no_format=True, print_mode=True, prefetch_fields=False)
        print_options = print_mode_self._get_options(previous_options=options)
        lines = self._filter_out_folded_children(print_mode_self._get_lines(print_options))

        # Add headers.
        # For this, iterate in the same way as done in main_table_header template
        column_headers_render_data = self._get_column_headers_render_data(print_options)
        for header_level_index, header_level in enumerate(print_options['column_headers']):
            for header_to_render in header_level * column_headers_render_data['level_repetitions'][header_level_index]:
                colspan = header_to_render.get('colspan', column_headers_render_data['level_colspan'][header_level_index])
                write_with_colspan(sheet, x_offset, y_offset, header_to_render.get('name', ''), colspan, title_format)
                x_offset += colspan
            if print_options['show_growth_comparison']:
                write_with_colspan(sheet, x_offset, y_offset, '%', 1, title_format)
            y_offset += 1
            x_offset = 1

        for subheader in column_headers_render_data['custom_subheaders']:
            colspan = subheader.get('colspan', 1)
            write_with_colspan(sheet, x_offset, y_offset, subheader.get('name', ''), colspan, title_format)
            x_offset += colspan
        y_offset += 1
        x_offset = 1

        for column in print_options['columns']:
            colspan = column.get('colspan', 1)
            write_with_colspan(sheet, x_offset, y_offset, column.get('name', ''), colspan, title_format)
            x_offset += colspan
        y_offset += 1

        if print_options.get('order_column'):
            lines = self._sort_lines(lines, print_options)

        # Disable bold styling for the max level.
        max_level = max(line.get('level', -1) for line in lines) if lines else -1
        if max_level in {0, 1, 2}:
            # Total lines are supposed to be a level above, so we don't touch them.
            for wb_format in (s for s in workbook_formats[max_level] if 'total' not in s):
                workbook_formats[max_level][wb_format].set_bold(False)

        # Add lines.
        for y, line in enumerate(lines):
            level = line.get('level')
            if level == 0:
                y_offset += 1
            elif not level:
                level = 'default'
            elif isinstance(level, int) and not workbook_formats.get(level):
                workbook_formats[level] = {
                    **workbook_formats['default'],
                    'col1_text': workbook.add_format({**default_format_props, 'indent': level}),
                    'col1_date': workbook.add_format({**default_format_props, 'indent': level, 'num_format': 'yyyy-mm-dd'}),
                    'col1_total': workbook.add_format({**default_format_props, 'bold': True, 'indent': level - 1}),
                }
            line_id = self._parse_line_id(line.get('id'))
            is_initial_line = line_id[-1][0] == 'initial' if line_id else False
            is_total_line = line_id[-1][0] == 'total' if line_id else False

            # Write the first column, with a specific style to manage the indentation.
            cell_type, cell_value = self._get_cell_type_value(line)

            if cell_type == 'date':
                cell_format = workbook_formats[level]['col1_date']
            elif is_initial_line:
                cell_format = workbook_formats[level].get('col1_initial', workbook_formats[level]['col1_text'])
            elif is_total_line:
                cell_format = workbook_formats[level]['col1_total']
            else:
                cell_format = workbook_formats[level]['col1_text']

            write_method = sheet.write_datetime if cell_type == 'date' else sheet.write
            write_method(y + y_offset, 0, cell_value, cell_format)

            # Write all the remaining cells.
            columns = line['columns']
            if print_options['show_growth_comparison'] and 'growth_comparison_data' in line:
                columns += [line.get('growth_comparison_data')]
            for x, column in enumerate(columns, start=1):
                cell_type, cell_value = self._get_cell_type_value(column)

                if cell_type == 'date':
                    cell_format = workbook_formats[level]['date']
                elif is_initial_line:
                    cell_format = workbook_formats[level].get('initial', workbook_formats[level]['text'])
                elif is_total_line:
                    cell_format = workbook_formats[level]['total']
                else:
                    cell_format = workbook_formats[level]['text']

                write_method = sheet.write_datetime if cell_type == 'date' else sheet.write
                write_method(y + y_offset, x + line.get('colspan', 1) - 1, cell_value, cell_format)
        # --- Fin de la copia del export estandar de 16 ---

        self._escribir_resumen_y_firmas_xlsx(print_options, workbook, sheet, lineas=lines)

        workbook.close()
        output.seek(0)
        generated_file = output.read()
        output.close()

        return {
            'file_name': self.get_default_report_filename('xlsx'),
            'file_content': generated_file,
            'file_type': 'xlsx',
        }

    def _escribir_resumen_y_firmas_xlsx(self, options, workbook, sheet, lineas=None):
        lineas_resumen = self._obtener_lineas_resumen_personalizado(options, lineas=lineas)
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
