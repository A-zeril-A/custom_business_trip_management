# -*- coding: utf-8 -*-
from odoo import models, fields

class BusinessTripAirport(models.Model):
    _name = 'business.trip.airport'
    _description = 'Business Trip Airport/Station'
    _order = 'name'

    name = fields.Char(string="Airport/Station Name", required=True, translate=True)
    code = fields.Char(string="Code (e.g., IATA/ICAO)")
    city = fields.Char(string="City")
    country_id = fields.Many2one('res.country', string="Country")
    active = fields.Boolean(default=True)

    # You can add more fields like coordinates, type (airport, train station, bus terminal), etc. 