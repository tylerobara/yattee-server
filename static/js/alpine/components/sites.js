document.addEventListener('alpine:init', () => {
    Alpine.data('sitesManager', () => ({
        sites: [],
        loading: true,
        view: 'list',

        editingSiteId: null,
        selectedExtractor: '',
        customName: '',
        customPattern: '',
        proxyStreaming: true,
        credentials: [],
        credentialDropdownOpen: false,
        validatingSiteId: null,

        get isEditing() {
            return this.editingSiteId !== null;
        },

        get showCustomFields() {
            return this.selectedExtractor === 'custom';
        },

        get formTitle() {
            return this.isEditing ? 'Edit Site' : 'Add Site';
        },

        async init() {
            await this.loadSites();
        },

        async loadSites() {
            this.loading = true;
            try {
                this.sites = await Alpine.store('api').get('/sites');
            } catch (err) {
                console.error('Failed to load sites:', err);
            } finally {
                this.loading = false;
            }
        },

        async toggleSite(siteId, enabled) {
            try {
                await Alpine.store('api').put(`/sites/${siteId}`, { enabled });
                Alpine.store('toast').success(enabled ? 'Site enabled' : 'Site disabled');
            } catch (err) {
                await this.loadSites();
            }
        },

        async validateSite(siteId) {
            this.validatingSiteId = siteId;
            try {
                const results = await Alpine.store('api').post(`/sites/${siteId}/validate`, {});
                const toast = Alpine.store('toast');
                if (!results.length) {
                    toast.success('No YouTube cookie credentials to validate');
                } else if (results.some(r => r.logged_in === false)) {
                    toast.error('Cookies are logged out — marked stale; upload a fresh jar');
                } else if (results.every(r => r.logged_in === true)) {
                    toast.success('Cookies are valid (logged in)');
                } else {
                    toast.error('Could not determine cookie state: ' + (results.find(r => r.error)?.error || 'unknown'));
                }
                await this.loadSites();
            } catch (err) {
                // Error handled by API store
            } finally {
                this.validatingSiteId = null;
            }
        },

        formatDate(iso) {
            if (!iso) return '';
            const d = new Date(iso);
            return isNaN(d) ? iso : d.toLocaleString();
        },

        async deleteSite(siteId) {
            if (!confirm('Delete this site and all its credentials?')) return;
            try {
                await Alpine.store('api').delete(`/sites/${siteId}`);
                Alpine.store('toast').success('Site deleted');
                await this.loadSites();
            } catch (err) {
                // Error handled by API store
            }
        },

        showAddForm() {
            this.resetForm();
            this.view = 'form';
        },

        async showEditForm(siteId) {
            try {
                const site = await Alpine.store('api').get(`/sites/${siteId}`);
                this.editingSiteId = siteId;

                const extractor = Alpine.store('app').getExtractorByPattern(site.extractor_pattern);
                if (extractor) {
                    this.selectedExtractor = extractor.id;
                } else {
                    this.selectedExtractor = 'custom';
                    this.customName = site.name;
                    this.customPattern = site.extractor_pattern;
                }

                this.proxyStreaming = site.proxy_streaming !== false;

                this.credentials = (site.credentials || []).map(c => ({
                    id: c.id,
                    credential_type: c.credential_type,
                    key: c.key,
                    value: '',
                    hasExisting: c.has_value,
                    status: c.status,
                    stale_since: c.stale_since,
                    last_validated_at: c.last_validated_at,
                    last_error: c.last_error
                }));

                this.view = 'form';
            } catch (err) {
                // Error handled by API store
            }
        },

        resetForm() {
            this.editingSiteId = null;
            this.selectedExtractor = '';
            this.customName = '';
            this.customPattern = '';
            this.proxyStreaming = true;
            this.proxyRecommended = false;
            this.credentials = [];
        },

        hideForm() {
            this.resetForm();
            this.view = 'list';
        },

        onExtractorChange() {
            if (this.selectedExtractor === 'custom') {
                this.proxyRecommended = false;
            } else if (this.selectedExtractor && !this.isEditing) {
                const extractor = Alpine.store('app').getExtractorById(this.selectedExtractor);
                if (extractor) {
                    if (extractor.suggested_credentials) {
                        this.credentials = extractor.suggested_credentials.map(type => ({
                            credential_type: type,
                            key: '',
                            value: ''
                        }));
                    }
                }
            }
        },

        addCredential(type) {
            const credType = Alpine.store('app').credentialTypes.find(t => t.value === type);
            this.credentials.push({
                credential_type: type,
                key: '',
                value: credType?.isFlag ? 'true' : ''
            });
            this.credentialDropdownOpen = false;
        },

        removeCredential(index) {
            this.credentials.splice(index, 1);
        },

        getCredentialType(value) {
            return Alpine.store('app').credentialTypes.find(t => t.value === value) || { label: value };
        },

        async saveSite() {
            let name, extractor_pattern;

            if (this.selectedExtractor === 'custom') {
                name = this.customName;
                extractor_pattern = this.customPattern;
                if (!name || !extractor_pattern) {
                    Alpine.store('toast').error('Name and extractor pattern are required');
                    return;
                }
            } else if (this.selectedExtractor) {
                const extractor = Alpine.store('app').getExtractorById(this.selectedExtractor);
                if (!extractor) {
                    Alpine.store('toast').error('Please select a valid site');
                    return;
                }
                name = extractor.name;
                extractor_pattern = extractor.pattern;
            } else {
                Alpine.store('toast').error('Please select a site');
                return;
            }

            try {
                if (this.editingSiteId) {
                    await this.updateSite(name, extractor_pattern);
                } else {
                    await this.createSite(name, extractor_pattern);
                }
                this.hideForm();
                await this.loadSites();
            } catch (err) {
                // Error handled by API store
            }
        },

        async createSite(name, extractor_pattern) {
            const credentials = this.credentials
                .filter(c => c.value)
                .map(c => ({
                    credential_type: c.credential_type,
                    key: c.key || null,
                    value: c.value
                }));

            await Alpine.store('api').post('/sites', {
                name,
                extractor_pattern,
                priority: 0,
                enabled: true,
                proxy_streaming: this.proxyStreaming,
                credentials
            });

            Alpine.store('toast').success('Site created');
        },

        async updateSite(name, extractor_pattern) {
            const siteId = this.editingSiteId;
            const api = Alpine.store('api');

            await api.put(`/sites/${siteId}`, {
                name,
                extractor_pattern,
                priority: 0,
                proxy_streaming: this.proxyStreaming
            });

            const site = await api.get(`/sites/${siteId}`);
            const keepIds = new Set();

            for (const cred of this.credentials) {
                if (cred.id && cred.hasExisting && !cred.value) {
                    keepIds.add(cred.id);
                }
            }

            // Add new values first: if the server rejects one (e.g. an already
            // logged-out cookie jar), the credential it was replacing survives.
            for (const cred of this.credentials) {
                if (cred.value) {
                    await api.post(`/sites/${siteId}/credentials`, {
                        credential_type: cred.credential_type,
                        key: cred.key || null,
                        value: cred.value
                    });
                }
            }

            for (const cred of site.credentials || []) {
                if (!keepIds.has(cred.id)) {
                    await api.delete(`/sites/${siteId}/credentials/${cred.id}`);
                }
            }

            Alpine.store('toast').success('Site updated');
        }
    }));
});
