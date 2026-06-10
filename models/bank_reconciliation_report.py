from odoo import _, models


class BankReconciliationReportCustomHandler(models.AbstractModel):
    _inherit = "account.bank.reconciliation.report.handler"

    _ETIQUETA_COLUMNA_CONTACTO = "columna_contacto"

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        previous_options = previous_options or {}
        options["modo_personalizado"] = previous_options.get("modo_personalizado", options.get("modo_personalizado", False))

        botones = options.setdefault("buttons", [])
        params_accion_existentes = {boton.get("action_param") for boton in botones}
        botones_personalizados = [
            {
                "name": _("PDF Personalizado"),
                "sequence": 15,
                "action": "export_file",
                "action_param": "exportar_a_pdf_personalizado",
                "branch_allowed": True,
                "always_show": True,
            },
            {
                "name": _("XLSX Personalizado"),
                "sequence": 25,
                "action": "export_file",
                "action_param": "exportar_a_xlsx_personalizado",
                "branch_allowed": True,
                "always_show": True,
            },
        ]

        for boton in botones_personalizados:
            if boton["action_param"] not in params_accion_existentes:
                botones.append(boton)

        if options.get("modo_personalizado"):
            self._inyectar_columna_contacto(options)

        botones.sort(key=lambda boton: boton.get("sequence", 0))

    def exportar_a_pdf_personalizado(self, options):
        reporte = self.env["account.report"].browse(options["report_id"])
        return reporte.export_to_pdf(self._obtener_opciones_exportacion_personalizada(options))

    def exportar_a_xlsx_personalizado(self, options, response=None):
        reporte = self.env["account.report"].browse(options["report_id"])
        return reporte.export_to_xlsx(self._obtener_opciones_exportacion_personalizada(options), response=response)

    def _custom_line_postprocessor(self, report, options, lines, warnings=None):
        lines = super()._custom_line_postprocessor(report, options, lines, warnings=warnings)
        if not options.get("modo_personalizado"):
            return lines

        indices_columna_contacto = self._obtener_indices_columna_contacto(options)
        if not indices_columna_contacto:
            return lines

        linea_a_id_apunte = {}
        for linea in lines:
            modelo, modelo_id = report._get_model_info_from_id(linea.get("id"))
            if modelo == "account.move.line" and modelo_id:
                linea_a_id_apunte[linea["id"]] = modelo_id

        apuntes_por_id = {
            apunte.id: apunte
            for apunte in self.env["account.move.line"].browse(list(linea_a_id_apunte.values()))
        }

        for linea in lines:
            nombre_contacto = ""
            id_apunte = linea_a_id_apunte.get(linea.get("id"))
            if id_apunte:
                nombre_contacto = self._obtener_nombre_contacto_desde_apunte(apuntes_por_id[id_apunte])

            for indice_columna in indices_columna_contacto:
                if indice_columna < len(linea["columns"]):
                    linea["columns"][indice_columna] = report._build_column_dict(
                        nombre_contacto,
                        options["columns"][indice_columna],
                        options=options,
                    )

        return lines

    def _obtener_opciones_exportacion_personalizada(self, options):
        return {
            **options,
            "modo_personalizado": True,
        }

    def _inyectar_columna_contacto(self, options):
        if any(columna.get("expression_label") == self._ETIQUETA_COLUMNA_CONTACTO for columna in options.get("columns", [])):
            return

        nuevas_columnas = []
        insertado = False
        for columna in options.get("columns", []):
            nuevas_columnas.append(columna)
            if columna.get("expression_label") == "label":
                nuevas_columnas.append({
                    "name": _("Contacto"),
                    "column_group_key": columna.get("column_group_key"),
                    "expression_label": self._ETIQUETA_COLUMNA_CONTACTO,
                    "sortable": False,
                    "figure_type": "string",
                    "blank_if_zero": False,
                    "style": "text-align: center; white-space: nowrap;",
                })
                insertado = True

        if insertado:
            options["columns"] = nuevas_columnas

    def _obtener_indices_columna_contacto(self, options):
        return [
            indice
            for indice, columna in enumerate(options.get("columns", []))
            if columna.get("expression_label") == self._ETIQUETA_COLUMNA_CONTACTO
        ]

    def _obtener_nombre_contacto_desde_apunte(self, apunte):
        contacto = apunte.partner_id.commercial_partner_id
        if contacto:
            return contacto.display_name

        linea_extracto = apunte.statement_line_id
        if not linea_extracto:
            return ""

        contacto = linea_extracto.partner_id.commercial_partner_id
        if contacto:
            return contacto.display_name

        contacto_inferido = linea_extracto._retrieve_partner()
        if contacto_inferido:
            return contacto_inferido.display_name

        return linea_extracto.partner_name or ""
