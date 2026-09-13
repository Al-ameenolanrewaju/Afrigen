/**
 * BrandContext - Frontend Middleware for Sprint 7 AI Brand Workspace
 * 
 * Handles reading the active brand from localStorage, updating the UI switchers,
 * and dynamically injecting brand context into raw prompts before generation.
 */

class BrandContextMiddleware {
    constructor() {
        this.storageKey = 'afrigen_brands';
        this.activeBrandKey = 'afrigen_active_brand_id';
        this.brands = [];
        this.activeBrandId = localStorage.getItem(this.activeBrandKey) || '';
    }

    getBrands() {
        return this.brands;
    }

    getActiveBrand() {
        if (!this.activeBrandId) return null;
        return this.brands.find(b => String(b.id) === String(this.activeBrandId)) || null;
    }

    setActiveBrand(id) {
        this.activeBrandId = String(id || '');
        localStorage.setItem(this.activeBrandKey, this.activeBrandId);
        this.updateSwitchers();
    }

    async load() {
        const response = await fetch('/api/brands');
        if (!response.ok) throw new Error('Unable to load brands');
        const data = await response.json();
        this.brands = data.brands || [];
        if (this.activeBrandId && !this.getActiveBrand()) this.activeBrandId = '';
        this.updateSwitchers();
        document.dispatchEvent(new CustomEvent('brand-context-loaded'));
    }

    async saveBrand(brandData) {
        const response = await fetch('/api/brands', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(brandData)
        });
        if (!response.ok) throw new Error('Unable to save brand');
        const data = await response.json();
        this.brands.push({...brandData, ...data.brand});
        this.updateSwitchers();
    }

    async deleteBrand(id) {
        const response = await fetch(`/api/brands/${id}`, {method: 'DELETE'});
        if (!response.ok) throw new Error('Unable to delete brand');
        this.brands = this.brands.filter(b => String(b.id) !== String(id));
        if (String(this.activeBrandId) === String(id)) this.setActiveBrand('');
        this.updateSwitchers();
    }

    /**
     * Injects the active brand's identity into the raw user prompt.
     * This is the core magic that satisfies the "reuse existing generation APIs" constraint.
     */
    inject(rawPrompt) {
        const brand = this.getActiveBrand();
        if (!brand) return rawPrompt; // Pass-through if no brand is active

        let injection = `[SYSTEM: YOU MUST STRICTLY ADHERE TO THE FOLLOWING BRAND IDENTITY]\n`;
        injection += `Brand Name: ${brand.name}\n`;
        
        if (brand.industry) injection += `Industry: ${brand.industry}\n`;
        if (brand.voice) injection += `Voice & Tone: ${brand.voice}\n`;
        if (brand.colors) injection += `Brand Colors: ${brand.colors}\n`;
        if (brand.audience) injection += `Target Audience: ${brand.audience}\n`;
        if (brand.instructions) injection += `Custom Instructions: ${brand.instructions}\n`;
        
        injection += `[END BRAND IDENTITY]\n\n`;
        
        return injection + rawPrompt;
    }

    /**
     * Hydrates the desktop and mobile UI switchers.
     * Needs to be called on DOMContentLoaded.
     */
    updateSwitchers() {
        const desktopSwitcher = document.getElementById('desktopBrandSwitcher');
        const mobileSwitcher = document.getElementById('mobileBrandSwitcher');
        
        const renderOptions = (selectEl) => {
            if (!selectEl) return;
            selectEl.innerHTML = `<option value="">Personal Workspace</option>`;
            this.brands.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b.id;
                opt.textContent = b.name;
                if (b.id === this.activeBrandId) opt.selected = true;
                selectEl.appendChild(opt);
            });
            
            // Re-attach event listener without duplicating
            selectEl.onchange = (e) => {
                this.setActiveBrand(e.target.value);
                // Optional: Show a toast or reload the page to refresh context
                window.location.reload(); 
            };
        };

        renderOptions(desktopSwitcher);
        renderOptions(mobileSwitcher);
    }
}

// Instantiate globally
window.BrandContext = new BrandContextMiddleware();

document.addEventListener('DOMContentLoaded', () => {
    window.BrandContext.load().catch(error => console.error(error));
});
