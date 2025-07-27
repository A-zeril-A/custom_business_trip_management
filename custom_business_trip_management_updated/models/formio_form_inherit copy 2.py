from odoo import models, fields, api
from datetime import datetime, date
from odoo.exceptions import ValidationError

class FormioForm(models.Model):
    _inherit = 'formio.form'

    # Travel-specific status field (used only for business trip forms)
    trip_status = fields.Selection([
        ('to_be_started', 'To be Started'),
        ('ongoing', 'Ongoing'),
        ('finalised', 'Finalised'),
        ('blocked', 'Blocked'),
    ], string="Travel Status", default='to_be_started')

    # Final total cost of the business trip
    final_total_cost = fields.Monetary(string="Final Total Cost")

    # Currency of the trip cost
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id.id
    )

    # Read-only travel dates extracted from submission_data
    travel_start_date = fields.Date(
        string="Travel Start Date",
        compute="_compute_travel_dates",
        store=True,
    )
    travel_end_date = fields.Date(
        string="Travel End Date",
        compute="_compute_travel_dates",
        store=True,
    )

    @api.depends('submission_data')
    def _compute_travel_dates(self):
        for rec in self:
            # Handle submission_data as either string or dict
            if not rec.submission_data:
                data = {}
            elif isinstance(rec.submission_data, str):
                try:
                    import json
                    data = json.loads(rec.submission_data)
                except json.JSONDecodeError:
                    data = {}
            else:
                data = rec.submission_data
            
            
            
            try:
                # Look for any keys containing 'dataDiPartenza'
                start_date_keys = [k for k in data.keys() if 'dataDiPartenza' in k] if isinstance(data, dict) else []

                
                if start_date_keys:
                    partenza = data.get(start_date_keys[0])  # Use the first matching key
                    
                    if isinstance(partenza, dict):
                        try:
                            rec.travel_start_date = date(
                                int(partenza.get('year')),
                                int(partenza.get('month')),
                                int(partenza.get('day'))
                            )
                        except (ValueError, TypeError, AttributeError) as e:
                            rec.travel_start_date = False
                    elif isinstance(partenza, str):
                        try:
                            # Try multiple date formats
                            for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                                try:
                                    rec.travel_start_date = datetime.strptime(partenza, fmt).date()
                                    break
                                except ValueError:
                                    continue
                            else:  # If no format works
                                rec.travel_start_date = False
                        except Exception as e:
                            rec.travel_start_date = False
                    else:
                        rec.travel_start_date = False
                else:
                    rec.travel_start_date = False
            except Exception as e:
                rec.travel_start_date = False

            # تاریخ پایان - به دنبال هر کلیدی با 'arrivo' می‌گردیم
            try:
                # Look for any keys containing 'arrivo'
                end_date_keys = [k for k in data.keys() if 'arrivo' in k.lower()] if isinstance(data, dict) else []
                
                if end_date_keys:
                    ritorno = data.get(end_date_keys[0])  # Use the first matching key
                    
                    if isinstance(ritorno, dict):
                        try:
                            rec.travel_end_date = date(
                                int(ritorno.get('year')),
                                int(ritorno.get('month')),
                                int(ritorno.get('day'))
                            )
                        except (ValueError, TypeError, AttributeError) as e:
                            rec.travel_end_date = False
                    elif isinstance(ritorno, str):
                        try:
                            # Try multiple date formats
                            for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                                try:
                                    rec.travel_end_date = datetime.strptime(ritorno, fmt).date()
                                    break
                                except ValueError:
                                    continue
                            else:  # If no format works
                                rec.travel_end_date = False
                        except Exception as e:
                            rec.travel_end_date = False
                    else:
                        rec.travel_end_date = False
                else:

                    
                    # Fallback: Get aeroportoDiArrivo as a text destination without date
                    airport_keys = [k for k in data.keys() if 'aeroporto' in k.lower()]

                    
                    rec.travel_end_date = False
            except Exception as e:
                rec.travel_end_date = False
                
    def force_compute_dates(self):
        """Manual method to force recomputation of travel dates"""
        self._compute_travel_dates()