/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { useService } from "@web/core/utils/hooks";
import { useState, onMounted, onWillUnmount } from "@odoo/owl";

/**
 * Destination Autocomplete Widget - Simple version
 * Extends CharField and adds autocomplete dropdown
 */
export class DestinationAutocompleteField extends CharField {
    static template = "web.CharField";  // Use default CharField template
    
    setup() {
        super.setup();
        this.rpc = useService("rpc");
        this.state = useState({
            suggestions: [],
            showDropdown: false,
            loading: false,
        });
        this.debounceTimeout = null;
        this.dropdownEl = null;
        
        onMounted(() => {
            this._createDropdown();
            this._attachEventListeners();
        });
        
        onWillUnmount(() => {
            this._cleanup();
        });
    }

    _createDropdown() {
        // Find the input element
        const inputEl = this.el?.querySelector('input');
        if (!inputEl) return;
        
        // Create dropdown container
        this.dropdownEl = document.createElement('div');
        this.dropdownEl.className = 'o_destination_autocomplete_dropdown';
        this.dropdownEl.style.cssText = `
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            max-height: 300px;
            overflow-y: auto;
            z-index: 1060;
            margin-top: 2px;
            display: none;
        `;
        
        // Make parent relative for positioning
        const parent = inputEl.closest('.o_field_widget') || inputEl.parentElement;
        if (parent) {
            parent.style.position = 'relative';
            parent.appendChild(this.dropdownEl);
        }
    }

    _attachEventListeners() {
        const inputEl = this.el?.querySelector('input');
        if (!inputEl) return;
        
        // Store bound functions for cleanup
        this._onInputHandler = (ev) => this._onInput(ev);
        this._onBlurHandler = () => this._hideDropdown();
        
        inputEl.addEventListener('input', this._onInputHandler);
        inputEl.addEventListener('blur', this._onBlurHandler);
    }

    _cleanup() {
        if (this.debounceTimeout) {
            clearTimeout(this.debounceTimeout);
        }
        if (this.dropdownEl && this.dropdownEl.parentElement) {
            this.dropdownEl.parentElement.removeChild(this.dropdownEl);
        }
    }

    _onInput(ev) {
        const value = ev.target.value;
        
        if (this.debounceTimeout) {
            clearTimeout(this.debounceTimeout);
        }
        
        if (!value || value.length < 2) {
            this._hideDropdown();
            return;
        }
        
        this._showLoading();
        
        this.debounceTimeout = setTimeout(async () => {
            await this._searchCities(value);
        }, 300);
    }

    async _searchCities(searchTerm) {
        try {
            const results = await this.rpc('/business_trip/api/geonames_cities', {
                search_term: searchTerm,
            });
            this._showSuggestions(results || []);
        } catch (error) {
            console.error("Error fetching cities:", error);
            this._showError();
        }
    }

    _showLoading() {
        if (!this.dropdownEl) return;
        this.dropdownEl.innerHTML = `
            <div style="padding: 12px; color: #6c757d; text-align: center;">
                <i class="fa fa-spinner fa-spin" style="margin-right: 8px;"></i>
                Searching cities...
            </div>
        `;
        this.dropdownEl.style.display = 'block';
    }

    _showError() {
        if (!this.dropdownEl) return;
        this.dropdownEl.innerHTML = `
            <div style="padding: 12px; color: #dc3545; text-align: center;">
                <i class="fa fa-exclamation-circle" style="margin-right: 8px;"></i>
                Error loading cities
            </div>
        `;
    }

    _showSuggestions(suggestions) {
        if (!this.dropdownEl) return;
        
        if (suggestions.length === 0) {
            this.dropdownEl.innerHTML = `
                <div style="padding: 12px; color: #6c757d; text-align: center;">
                    <i class="fa fa-info-circle" style="margin-right: 8px;"></i>
                    No cities found
                </div>
            `;
            this.dropdownEl.style.display = 'block';
            return;
        }
        
        let html = '';
        suggestions.forEach(suggestion => {
            html += `
                <div class="o_destination_suggestion" 
                     data-value="${this._escapeHtml(suggestion.label)}"
                     style="padding: 10px 14px; cursor: pointer; border-bottom: 1px solid #f1f3f4;">
                    <i class="fa fa-map-marker" style="color: #17a2b8; margin-right: 10px;"></i>
                    ${this._escapeHtml(suggestion.label)}
                </div>
            `;
        });
        
        this.dropdownEl.innerHTML = html;
        this.dropdownEl.style.display = 'block';
        
        // Add click handlers
        this.dropdownEl.querySelectorAll('.o_destination_suggestion').forEach(item => {
            item.addEventListener('mouseenter', (ev) => {
                ev.target.style.backgroundColor = '#f8f9fa';
            });
            item.addEventListener('mouseleave', (ev) => {
                ev.target.style.backgroundColor = '';
            });
            item.addEventListener('mousedown', (ev) => {
                ev.preventDefault();  // Prevent blur
                const value = ev.currentTarget.dataset.value;
                this._selectSuggestion(value);
            });
        });
    }

    _selectSuggestion(value) {
        const inputEl = this.el?.querySelector('input');
        if (inputEl) {
            inputEl.value = value;
            inputEl.dispatchEvent(new Event('input', { bubbles: true }));
            inputEl.dispatchEvent(new Event('change', { bubbles: true }));
        }
        this._hideDropdown();
    }

    _hideDropdown() {
        setTimeout(() => {
            if (this.dropdownEl) {
                this.dropdownEl.style.display = 'none';
            }
        }, 200);
    }

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

export const destinationAutocompleteField = {
    ...charField,
    component: DestinationAutocompleteField,
    displayName: "Destination Autocomplete",
    supportedTypes: ["char"],
};

registry.category("fields").add("destination_autocomplete", destinationAutocompleteField);
