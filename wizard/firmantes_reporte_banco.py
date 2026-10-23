# -*- coding: utf-8 -*-

from odoo import fields, models
import base64

class FirmantesReporteBanco(models.TransientModel):
    _name = "l10n_gt.reporte.banco.firmantes.wizard"
    _description = "Firmantes del reporte de Conciliación Bancaria"

    hecho_por_id = fields.Many2one("hr.employee", string="Hecho por", required=True)
    revisado_por_id = fields.Many2one("hr.employee", string="Revisado por", required=True)
    autorizado_por_id = fields.Many2one("hr.employee", string="Autorizado por", required=True)
    archivo = fields.Binary(readonly=True)
    nombre_archivo = fields.Char(readonly=True)

    def action_generar(self):
        self.ensure_one()
        options = dict(self.env.context["options"])
        formato_reporte = self.env.context["formato_reporte"]
        options["modo_personalizado"] = True

        reporte = self.env["account.report"].browse(options["report_id"]).with_context(
            hecho_por_id=self.hecho_por_id.id,
            revisado_por_id=self.revisado_por_id.id,
            autorizado_por_id=self.autorizado_por_id.id,
        )
        if formato_reporte == "pdf":
            resultado = reporte.export_to_pdf(options)
        else:
            resultado = reporte.export_to_xlsx(options)

        self.archivo = base64.b64encode(resultado["file_content"])
        self.nombre_archivo = resultado["file_name"]
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content?model={self._name}&id={self.id}&field=archivo&filename_field=nombre_archivo&download=true",
            "target": "self",
        }