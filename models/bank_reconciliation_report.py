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
                "name": _("PDF P."),
                "sequence": 15,
                "action": "export_file",
                "action_param": "exportar_a_pdf_personalizado",
                "file_export_type": _("PDF"),
            },
            {
                "name": _("XLSX P."),
                "sequence": 25,
                "action": "export_file",
                "action_param": "exportar_a_xlsx_personalizado",
                "file_export_type": _("XLSX"),
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

    def _custom_line_postprocessor(self, report, options, lines):
        lines = super()._custom_line_postprocessor(report, options, lines)
        if not options.get("modo_personalizado"):
            return lines

        indices_columna_contacto = self._obtener_indices_columna_contacto(options)
        if not indices_columna_contacto:
            return lines

        # En 16 las lineas de detalle apuntan a account.bank.statement.line,
        # account.payment o account.move (no a account.move.line como en 17).
        modelos_detalle = ("account.bank.statement.line", "account.payment", "account.move")
        linea_a_registro = {}
        ids_por_modelo = {modelo: set() for modelo in modelos_detalle}
        for linea in lines:
            modelo, modelo_id = report._get_model_info_from_id(linea.get("id"))
            if modelo in ids_por_modelo and modelo_id:
                linea_a_registro[linea["id"]] = (modelo, modelo_id)
                ids_por_modelo[modelo].add(modelo_id)

        registros_por_modelo = {
            modelo: {
                registro.id: registro
                for registro in self.env[modelo].browse(list(ids_modelo))
            }
            for modelo, ids_modelo in ids_por_modelo.items()
        }

        for linea in lines:
            nombre_contacto = ""
            modelo_y_id = linea_a_registro.get(linea.get("id"))
            if modelo_y_id:
                modelo, modelo_id = modelo_y_id
                registro = registros_por_modelo[modelo].get(modelo_id)
                if registro:
                    nombre_contacto = self._obtener_nombre_contacto_desde_registro(modelo, registro)

            for indice_columna in indices_columna_contacto:
                if indice_columna < len(linea["columns"]):
                    linea["columns"][indice_columna] = {
                        "name": nombre_contacto,
                        "no_format": nombre_contacto,
                        "class": "",
                    }

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

    def _obtener_nombre_contacto_desde_registro(self, modelo, registro):
        contacto = registro.partner_id.commercial_partner_id
        if contacto:
            return contacto.display_name

        if modelo == "account.bank.statement.line":
            contacto_inferido = registro._retrieve_partner()
            if contacto_inferido:
                return contacto_inferido.display_name
            return registro.partner_name or ""

        return ""
