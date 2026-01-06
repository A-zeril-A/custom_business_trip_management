# -*- coding: utf-8 -*-

import logging
import json
import requests
from requests.exceptions import SSLError as RequestsSSLError

from odoo import api, fields, models


_logger = logging.getLogger(__name__)


class BusinessTripDestination(models.Model):
    _name = "business.trip.destination"
    _description = "Business Trip Destination (Geonames)"
    _order = "name"

    name = fields.Char(required=True, index=True)
    country_name = fields.Char(index=True)
    geoname_id = fields.Char(index=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("geoname_id_uniq", "unique(geoname_id)", "This Geonames destination already exists."),
    ]

    def name_get(self):
        res = []
        for rec in self:
            # name is already stored as a display label like "Rome, Italy"
            res.append((rec.id, rec.name))
        return res

    @api.model
    def _geonames_search(self, search_term, limit=15, feature_class=None, feature_code=None):
        """Return list of dicts: {value, label, name, country_name} from Geonames."""
        icp = self.env["ir.config_parameter"].sudo()
        username = icp.get_param("custom_business_trip_management.geonames_username") or "azerila"
        timeout = float(icp.get_param("custom_business_trip_management.geonames_timeout") or 10.0)
        prefer_https = (icp.get_param("custom_business_trip_management.geonames_prefer_https") or "0") == "1"
        verify_ssl = (icp.get_param("custom_business_trip_management.geonames_verify_ssl") or "1") == "1"

        # IMPORTANT: Geonames JSON endpoint is searchJSON (search returns XML by default)
        https_url = "https://api.geonames.org/searchJSON"
        http_url = "http://api.geonames.org/searchJSON"
        api_url = https_url if prefer_https else http_url
        params = {
            "name_startsWith": search_term,
            "maxRows": int(limit),
            "style": "MEDIUM",
            "username": username,
            "orderby": "relevance",
        }
        if feature_class:
            params["featureClass"] = feature_class
        if feature_code:
            params["featureCode"] = feature_code
        _logger.info(
            "BT_DESTINATION: Geonames request url=%s https_preferred=%s verify_ssl=%s params=%s",
            api_url,
            prefer_https,
            verify_ssl,
            json.dumps(params),
        )

        def _do_request(url, verify):
            return requests.get(url, params=params, timeout=timeout, verify=verify)

        try:
            resp = _do_request(api_url, verify_ssl if api_url.startswith("https://") else True)
        except RequestsSSLError:
            # If HTTPS fails due to cert/hostname issues in a specific environment, fallback to HTTP.
            if api_url.startswith("https://"):
                _logger.warning("BT_DESTINATION: HTTPS SSL error; falling back to HTTP for Geonames.")
                resp = _do_request(http_url, True)
            else:
                raise
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception:
            # Log a small snippet to diagnose (HTML error page, rate limit, etc.)
            snippet = (resp.text or "")[:200].replace("\n", "\\n")
            raise RuntimeError(f"Geonames returned non-JSON response (status={resp.status_code}): {snippet}")

        # Geonames error payload sometimes contains {"status": {...}, "geonames": null}
        if isinstance(data, dict) and data.get("geonames") is None and data.get("status"):
            raise RuntimeError(
                f"Geonames API error {data['status'].get('value')}: {data['status'].get('message')}"
            )

        results = []
        for item in (data.get("geonames") or []):
            name = item.get("name")
            country_name = item.get("countryName")
            geoname_id = item.get("geonameId")
            if not name or not geoname_id:
                continue
            # For countries (featureClass=A, featureCode=PCLI), Geonames uses the country name as 'name'
            # and countryName may be missing or equal. Keep a clean label.
            if country_name and country_name != name:
                label = f"{name}, {country_name}"
            else:
                label = name
            results.append(
                {
                    "value": str(geoname_id),
                    "label": label,
                    "name": name,
                    "country_name": country_name,
                }
            )
        return results

    @api.model
    def _norm(self, s):
        return (s or "").strip().casefold()

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        """
        Native Odoo autocomplete for Many2one.
        We enrich results from Geonames and persist them so ids are stable.
        """
        args = list(args or [])

        icp = self.env["ir.config_parameter"].sudo()
        min_chars = int(icp.get_param("custom_business_trip_management.geonames_min_chars") or 1)

        # If no input, fallback to local records
        if not name:
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        # Optionally gate calls to reduce API load
        term = name.strip()
        if len(term) < min_chars:
            return []

        max_out = int(limit or 10)
        max_out = min(max_out, 15)
        norm_term = self._norm(term)

        # Keep the list small to reduce API calls; Many2one will call name_search frequently.
        api_limit = min(int(limit or 15), 15)

        try:
            # Match the old behavior: cities first; optionally include countries for 3+ chars.
            suggestions = self._geonames_search(term, limit=api_limit, feature_class="P")
            if len(term) >= 3:
                suggestions += self._geonames_search(term, limit=api_limit, feature_class="A", feature_code="PCLI")
        except Exception as e:
            _logger.warning("BT_DESTINATION: Geonames search failed for term=%r: %s", name, e)
            # Fallback to local only if the API fails (keeps UX usable while offline)
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        # Hard filter: keep only true prefix matches (defensive against noisy upstream)
        filtered = []
        seen_geo = set()
        for s in suggestions:
            geo = s.get("value")
            nm = self._norm(s.get("name") or s.get("label"))
            cn = self._norm(s.get("country_name"))
            if not geo or geo in seen_geo:
                continue
            # Accept only if city/country name starts with the typed term
            if nm.startswith(norm_term) or cn.startswith(norm_term):
                filtered.append(s)
                seen_geo.add(geo)

        suggestions = filtered[:api_limit]

        # Upsert records under sudo so normal users don't need create rights
        created_or_found_ids = []
        for s in suggestions:
            geo_id = s.get("value")
            label = s.get("label")
            country_name = s.get("country_name")
            if not geo_id or not label:
                continue

            rec = self.sudo().search([("geoname_id", "=", geo_id)], limit=1)
            if rec:
                # keep label updated if Geonames changes it
                if rec.name != label or (country_name and rec.country_name != country_name):
                    rec.sudo().write({"name": label, "country_name": country_name})
            else:
                rec = self.sudo().create({"name": label, "country_name": country_name, "geoname_id": geo_id})
            created_or_found_ids.append(rec.id)

        if not created_or_found_ids:
            return []

        # Preserve the API order in the dropdown
        ordered = self.browse(created_or_found_ids)
        return ordered.name_get()[:max_out]


