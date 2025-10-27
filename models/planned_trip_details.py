# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PlannedTripAccommodationLine(models.Model):
    _name = 'planned.trip.accommodation.line'
    _description = 'Planned Trip Accommodation Line (by Organizer)'

    trip_id = fields.Many2one('business.trip', string='Business Trip', required=True, ondelete='cascade')
    name = fields.Char(string="Hotel/Place Name", required=True)
    address = fields.Text(string="Address")
    check_in_date = fields.Date(string="Check-in Date")
    check_out_date = fields.Date(string="Check-out Date")
    booking_reference = fields.Char(string="Booking Reference")
    cost = fields.Float(string="Cost")
    currency_id = fields.Many2one('res.currency', string='Currency', related='trip_id.currency_id', store=True)
    notes = fields.Text(string="Notes")
    attachment_ids = fields.Many2many('ir.attachment', 'planned_accom_line_ir_attachments_rel', 'line_id', 'attachment_id', string="Attachments")

class PlannedTripTransportLine(models.Model):
    _name = 'planned.trip.transport.line'
    _description = 'Planned Trip Transport Line (by Organizer)'

    trip_id = fields.Many2one('business.trip', string='Business Trip', required=True, ondelete='cascade')
    transport_type = fields.Selection([
        ('airplane', 'Airplane'),
        ('train', 'Train'),
        ('bus', 'Bus'),
        ('rental_car', 'Rental Car'),
        ('company_car', 'Company Car (Planned)'), # If organizer plans use of company car
        ('other', 'Other')
    ], string="Transport Type", required=True)
    
    # Common fields
    description = fields.Char(string="Description/Route", required=True) # e.g., "Flight BA245 LHR-JFK", "Train Rome-Florence"
    provider_name = fields.Char(string="Provider (Airline, Train Co., etc.)")
    booking_reference = fields.Char(string="Booking Ref/Ticket No.")
    departure_datetime = fields.Datetime(string="Departure Date & Time")
    arrival_datetime = fields.Datetime(string="Arrival Date & Time")
    cost = fields.Float(string="Cost")
    currency_id = fields.Many2one('res.currency', string='Currency', related='trip_id.currency_id', store=True)
    notes = fields.Text(string="Notes")
    attachment_ids = fields.Many2many('ir.attachment', 'planned_transport_line_ir_attachments_rel', 'line_id', 'attachment_id', string="Attachments")

    # Specific fields (can be made visible based on transport_type in view)
    # For Airplane
    flight_number = fields.Char(string="Flight Number")
    departure_airport_id = fields.Many2one('business.trip.airport', string="Departure Airport") # Assuming you might have an airport model
    arrival_airport_id = fields.Many2one('business.trip.airport', string="Arrival Airport")
    cabin_class = fields.Char(string="Cabin Class")
    
    # For Rental Car
    rental_company = fields.Char(string="Rental Company")
    car_category = fields.Char(string="Car Category/Model")
    pickup_location = fields.Char(string="Pickup Location")
    dropoff_location = fields.Char(string="Dropoff Location")

    # ... add more specific fields for other transport types if needed 