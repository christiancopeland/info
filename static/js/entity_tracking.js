class EntityTracker {
    constructor() {
        this.entityList = document.getElementById('entityList');
        this.setupUI();
        this.setupEventListeners();
        this.loadEntities();
    }

    setupUI() {
        // Add search and controls container with inline add entity form
        const controlsHtml = `
            <div class="entity-search-container">
                <div class="search-controls">
                    <div class="entity-add-form">
                        <input type="text" id="entityNameInput" class="entity-search-input" placeholder="Enter entity name">
                        <div class="search-filters">
                            <select class="entity-filter" id="entityTypeSelect">
                                <option value="CUSTOM">Custom</option>
                                <option value="PERSON">Person</option>
                                <option value="ORGANIZATION">Organization</option>
                            </select>
                            <button id="addEntityBtn" class="entity-add-btn">
                                <i class="fas fa-plus"></i> Add Entity
                            </button>
                        </div>
                    </div>
                    <div class="entity-filter-controls">
                        <input type="text" class="entity-search-input" placeholder="Search entities...">
                        <select class="entity-filter" id="entityTypeFilter">
                            <option value="ALL">All Types</option>
                            <option value="PERSON">Person</option>
                            <option value="ORGANIZATION">Organization</option>
                            <option value="CUSTOM">Custom</option>
                        </select>
                    </div>
                </div>
            </div>
            <div class="entities-list" id="entitiesList"></div>
        `;
        this.entityList.innerHTML = controlsHtml;
    }

    setupEventListeners() {
        // Add entity button click handler
        document.getElementById('addEntityBtn').addEventListener('click', () => this.addEntity());

        // Add search functionality
        const searchInput = document.querySelector('.entity-search-input:not(#entityNameInput)');
        searchInput.addEventListener('input', (e) => this.filterEntities(e.target.value));

        // Add type filter functionality
        const typeFilter = document.getElementById('entityTypeFilter');
        typeFilter.addEventListener('change', () => this.filterEntities(searchInput.value));
    }

    async addEntity() {
        const nameInput = document.getElementById('entityNameInput');
        const typeSelect = document.getElementById('entityTypeSelect');
        const name = nameInput.value;
        const type = typeSelect.value;

        if (!name.trim()) {
            // Show error
            return;
        }

        try {
            const response = await fetch('/api/v1/entities/track', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ name, entity_type: type })
            });

            if (!response.ok) {
                throw new Error('Failed to add entity');
            }

            const data = await response.json();
            this.addEntityToList(data);

            // Clear input after successful add
            nameInput.value = '';
        } catch (error) {
            console.error('Error adding entity:', error);
            // Show error to user
        }
    }

    addEntityToList(entity) {
        const entityElement = `
            <div class="entity-item" data-entity-id="${entity.entity_id}">
                <div class="entity-content">
                    <span class="entity-name">${entity.name}</span>
                    <span class="entity-type">${entity.entity_type || 'CUSTOM'}</span>
                </div>
                <div class="entity-actions">
                    <button class="view-mentions-btn" onclick="entityTracker.viewMentions('${entity.name}')">
                        <i class="fas fa-eye"></i>
                    </button>
                </div>
            </div>
        `;
        document.getElementById('entitiesList').insertAdjacentHTML('beforeend', entityElement);
    }

    async viewMentions(entityName) {
        try {
            const response = await fetch(`/api/v1/entities/${encodeURIComponent(entityName)}/mentions`);
            if (!response.ok) {
                throw new Error('Failed to fetch mentions');
            }

            const mentions = await response.json();
            console.log('Received mentions:', mentions); // Add this for debugging
            this.displayMentions(entityName, mentions);
        } catch (error) {
            console.error('Error fetching mentions:', error);
        }
    }

    displayMentions(entityName, mentions) {
        const mentionsHtml = `
            <div class="mentions-view">
                <div class="mentions-header">
                    <h3>Mentions of "${entityName}"</h3>
                    <button class="back-btn" onclick="entityTracker.closeMentionsView()">
                        <i class="fas fa-arrow-left"></i> Back
                    </button>
                </div>
                <div class="mentions-list">
                    ${mentions.length > 0 ? 
                        mentions.map(mention => `
                            <div class="mention-item">
                                <div class="mention-context">${mention.context || 'No context available'}</div>
                                <div class="mention-metadata">
                                    <span class="mention-doc">
                                        <i class="fas fa-file-alt"></i> ${mention.filename || 'Unknown document'}
                                    </span>
                                    <span class="mention-date">
                                        <i class="fas fa-clock"></i> ${mention.timestamp ? new Date(mention.timestamp).toLocaleDateString() : 'Unknown date'}
                                    </span>
                                </div>
                            </div>
                        `).join('') : 
                        '<div class="no-mentions">No mentions found for this entity.</div>'
                    }
                </div>
            </div>
        `;

        const entityList = document.getElementById('entityList');
        if (entityList) {
            entityList.innerHTML = mentionsHtml;
        } else {
            console.error('Entity list element not found');
        }
    }

    closeMentionsView() {
        // First, get the entity list container
        const entityList = document.getElementById('entityList');
        if (!entityList) {
            console.error('Entity list element not found');
            return;
        }

        // Set up the initial structure
        entityList.innerHTML = `
            <div class="entity-search-container">
                <div class="search-controls">
                    <div class="entity-add-form">
                        <input type="text" id="entityNameInput" class="entity-search-input" placeholder="Enter entity name">
                        <div class="search-filters">
                            <select class="entity-filter" id="entityTypeSelect">
                                <option value="CUSTOM">Custom</option>
                                <option value="PERSON">Person</option>
                                <option value="ORGANIZATION">Organization</option>
                            </select>
                            <button id="addEntityBtn" class="entity-add-btn">
                                <i class="fas fa-plus"></i> Add Entity
                            </button>
                        </div>
                    </div>
                    <div class="entity-filter-controls">
                        <input type="text" class="entity-search-input" placeholder="Search entities...">
                        <select class="entity-filter" id="entityTypeFilter">
                            <option value="ALL">All Types</option>
                            <option value="PERSON">Person</option>
                            <option value="ORGANIZATION">Organization</option>
                            <option value="CUSTOM">Custom</option>
                        </select>
                    </div>
                </div>
            </div>
            <div class="entities-list" id="entitiesList"></div>
        `;

        // Now that the DOM elements exist, set up event listeners and load entities
        this.setupEventListeners();
        this.loadEntities();
    }

    async loadEntities() {
        try {
            const response = await fetch('/api/v1/entities');
            if (!response.ok) {
                throw new Error('Failed to fetch entities');
            }

            const entities = await response.json();
            
            // Clear existing entities
            const entitiesList = document.getElementById('entitiesList');
            entitiesList.innerHTML = '';
            
            // Add each entity to the list
            entities.forEach(entity => this.addEntityToList(entity));
        } catch (error) {
            console.error('Error loading entities:', error);
        }
    }

    async refreshEntityList() {
        await this.loadEntities();
    }

    filterEntities(searchTerm) {
        const typeFilter = document.getElementById('entityTypeFilter').value;
        const entities = document.querySelectorAll('.entity-item');

        entities.forEach(entity => {
            const name = entity.querySelector('.entity-name').textContent.toLowerCase();
            const type = entity.querySelector('.entity-type').textContent;

            const matchesSearch = name.includes(searchTerm.toLowerCase());
            const matchesType = typeFilter === 'ALL' || type === typeFilter;

            entity.style.display = matchesSearch && matchesType ? 'flex' : 'none';
        });
    }
}

// Initialize the entity tracker
const entityTracker = new EntityTracker();
