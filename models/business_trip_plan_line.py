# -*- coding: utf-8 -*-

from odoo import models, fields, api
import json
import logging

_logger = logging.getLogger(__name__)


class BusinessTripPlanLine(models.Model):
    """Persistent model for business trip plan line items"""
    _name = 'business.trip.plan.line'
    _description = 'Business Trip Plan Line'
    _order = 'item_date, id'

    trip_id = fields.Many2one('business.trip', string='Trip', required=True, ondelete='cascade')
    
    # Type of travel arrangement
    item_type = fields.Selection([
        ('transport_air', 'Air Travel'),
        ('transport_train', 'Train Travel'),
        ('transport_bus', 'Bus Travel'),
        ('transport_car', 'Car Rental'),
        ('transport_taxi', 'Taxi/Local Transport'),
        ('transport_other', 'Other Transportation'),
        ('accommodation', 'Accommodation'),
        ('accommodation_airbnb', 'Airbnb/Rental'),
        ('meals', 'Meals'),
        ('meals_per_diem', 'Per Diem Allowance'),
        ('visa_fee', 'Visa Fee'),
        ('conference', 'Conference/Event Fee'),
        ('parking', 'Parking'),
        ('insurance', 'Travel Insurance'),
        ('internet', 'Internet/Communication'),
        ('translation', 'Translation Services'),
        ('entertainment', 'Entertainment/Activities'),
        ('shopping', 'Shopping Allowance'),
        ('currency_exchange', 'Currency Exchange Fee'),
        ('other', 'Other'),
        ('custom', 'Custom Item'),
    ], string='Item Type', required=True)
    
    # For custom item types
    custom_type = fields.Char(string='Custom Item Type', help="Define if item type is 'Custom'.")
    
    # Direction for transportation
    direction = fields.Selection([
        ('outbound', 'Outbound'),
        ('inbound', 'Return'),
        ('local', 'Local'),
        ('transit', 'Transit/Connection'),
        ('round_trip', 'Round Trip'),
        ('na', 'N/A')
    ], string='Direction', default='na')
    
    # Details
    description = fields.Char(string='Description', required=True)
    item_date = fields.Date(string='Date', required=True)
    
    # Transportation details
    from_location = fields.Char(string='From')
    to_location = fields.Char(string='To')
    carrier = fields.Char(string='Carrier/Provider', help="Airline, train, or service provider.")
    reference_number = fields.Char(string='Reference/Booking Number', help="Booking/ticket reference.")
    departure_time = fields.Float(string='Departure Time', help="Departure time (e.g., 9.5 for 9:30).")
    arrival_time = fields.Float(string='Arrival Time', help="Arrival time (e.g., 15.5 for 15:30).")
    travel_class = fields.Selection([
        ('economy', 'Economy'),
        ('business', 'Business'),
        ('first', 'First Class'),
        ('premium', 'Premium Economy'),
        ('standard', 'Standard'),
        ('other', 'Other')
    ], string='Travel Class')
    
    # Accommodation details
    nights = fields.Integer(string='Nights', default=1)
    accommodation_type = fields.Selection([
        ('hotel', 'Hotel'),
        ('airbnb', 'Airbnb/Vacation Rental'),
        ('corporate', 'Corporate Housing'),
        ('hostel', 'Hostel'),
        ('guesthouse', 'Guesthouse'),
        ('relatives', 'Relatives/Friends'),
        ('other', 'Other')
    ], string='Accommodation Type')
    
    # Cost details
    planned_cost = fields.Float(string='Planned Cost', required=False)
    currency_id = fields.Many2one('res.currency', related='trip_id.currency_id', readonly=True)
    cost_status = fields.Selection([
        ('estimated', 'Estimated'),
        ('quoted', 'Quoted'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid'),
        ('to_reimburse', 'To Reimburse')
    ], string='Cost Status', default='estimated')
    
    # Additional details
    is_reimbursable = fields.Boolean(string='Reimbursable', default=True, 
                                    help="Is this cost reimbursable to employee?")
    payment_method = fields.Selection([
        ('company', 'Company Paid'),
        ('employee', 'Employee Paid (Reimbursable)'),
        ('cash_advance', 'Cash Advance'),
        ('per_diem', 'Per Diem'),
        ('company_card', 'Company Card')
    ], string='Payment Method', default='company')
    
    # Helper fields
    attachment_ids = fields.Many2many('ir.attachment', 
                                     'business_trip_plan_line_persistent_attachment_rel',
                                     'line_id', 'attachment_id',
                                     string='Attachments')
    notes = fields.Text(string='Notes')
    
    # JSON field for storing type-specific details
    item_data_json = fields.Text(string='Item Details (JSON)', help="Internal: Stores item-specific details.")
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle any special creation logic"""
        return super(BusinessTripPlanLine, self).create(vals_list)
        
    def write(self, vals):
        """Override write to handle any special update logic"""
        return super(BusinessTripPlanLine, self).write(vals)
        
    def unlink(self):
        """Override unlink to handle any special deletion logic"""
        return super(BusinessTripPlanLine, self).unlink() 