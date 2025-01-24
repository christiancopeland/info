const NETWORK_COLORS = {
    node: '#4a90e2',
    highlightNode: '#64c2a6',
    edge: '#666666',
    text: '#ffffff'
};

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
                    <button class="view-relationships-btn" onclick="entityTracker.viewRelationships('${entity.name}')">
                        <i class="fas fa-project-diagram"></i>
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

    async viewRelationships(entityName) {
        try {
            const response = await fetch(`/api/v1/entities/${encodeURIComponent(entityName)}/relationships`);
            if (!response.ok) {
                throw new Error('Failed to fetch relationships');
            }

            const network = await response.json();
            this.displayRelationships(entityName, network);
        } catch (error) {
            console.error('Error fetching relationships:', error);
        }
    }

    displayRelationships(entityName, network) {
        // Normalize weights to 0-1 range for better visualization
        const weights = network.edges.map(e => e.weight);
        const maxWeight = Math.max(...weights);
        const minWeight = Math.min(...weights);
        const normalizeWeight = (weight) => {
            return maxWeight === minWeight ? 1 : (weight - minWeight) / (maxWeight - minWeight);
        };

        // Format percentages for display
        const formatPercent = (value) => `${(value * 100).toFixed(1)}%`;

        const relationshipsHtml = `
            <div class="relationships-view">
                <div class="relationships-header">
                    <h3>Relationships for "${entityName}"</h3>
                    <button class="back-btn" onclick="entityTracker.closeMentionsView()">
                        <i class="fas fa-arrow-left"></i> Back
                    </button>
                </div>
                <div class="network-visualization"></div>
                <div class="central-entities">
                    <h4>Most Connected Entities:</h4>
                    <ul>
                        ${network.central_entities.map(([entity, score]) => `
                            <li>
                                <span class="entity-name">${entity}</span>
                                <span class="entity-percentage">${formatPercent(score)}</span>
                            </li>
                        `).join('')}
                    </ul>
                </div>
                <div class="relationship-details">
                    ${network.edges.map(edge => {
                        const normalizedWeight = normalizeWeight(edge.weight);
                        const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
                        const targetId = typeof edge.target === 'object' ? edge.target.id : edge.target;
                        return `
                            <div class="relationship-item">
                                <div class="relationship-entities">
                                    ${sourceId} ↔ ${targetId}
                                </div>
                                <div class="relationship-strength">
                                    <div class="strength-bar-container">
                                        <div class="strength-bar" style="width: ${formatPercent(normalizedWeight)}"></div>
                                        <span class="strength-label">${formatPercent(normalizedWeight)}</span>
                                    </div>
                                </div>
                                ${edge.contexts ? `
                                    <div class="relationship-contexts">
                                        <strong>Example contexts:</strong>
                                        ${edge.contexts.slice(0, 2).map(ctx => `
                                            <div class="context-item">${ctx.context || 'No context available'}</div>
                                        `).join('')}
                                    </div>
                                ` : ''}
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;

        const entityList = document.getElementById('entityList');
        if (entityList) {
            entityList.innerHTML = relationshipsHtml;
            // Pass normalized weights to visualization
            const normalizedNetwork = {
                ...network,
                edges: network.edges.map(edge => ({
                    ...edge,
                    weight: normalizeWeight(edge.weight)
                }))
            };
            this.renderNetworkVisualization(normalizedNetwork, entityName);
        }
    }

    renderNetworkVisualization(network, centralEntity) {
        if (typeof d3 === 'undefined') {
            const container = document.querySelector('.network-visualization');
            container.innerHTML = `
                <div class="network-error">
                    <p>Network visualization could not be loaded.</p>
                </div>
            `;
            console.error('D3.js is required for network visualization');
            return;
        }

        const container = document.querySelector('.network-visualization');
        const width = container.clientWidth;
        const height = 300;

        // Clear any existing visualization
        container.innerHTML = '';

        // Add debug logging
        console.log('Network data:', network);
        console.log('Edge weights:', network.edges.map(e => e.weight));

        const svg = d3.select(container)
            .append('svg')
            .attr('width', width)
            .attr('height', height);

        // Create the force simulation with adjusted parameters
        const simulation = d3.forceSimulation(network.nodes)
            .force('link', d3.forceLink(network.edges)
                .id(d => d.id)
                .distance(50)) // Reduced distance between nodes
            .force('charge', d3.forceManyBody()
                .strength(-200)  // Reduced repulsion
                .distanceMax(150)) // Limit the repulsion range
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(30)); // Prevent node overlap

        // Create the links with proper width scaling
        const links = svg.append('g')
            .selectAll('line')
            .data(network.edges)
            .enter()
            .append('line')
            .attr('stroke', NETWORK_COLORS.edge)
            .attr('stroke-width', d => Math.max(1, d.weight * 5));

        // Create the nodes with 30% smaller sizes
        const nodes = svg.append('g')
            .selectAll('circle')
            .data(network.nodes)
            .enter()
            .append('circle')
            .attr('r', d => d.id === centralEntity ? 14 : 10) // Reduced from 20/15
            .attr('fill', d => d.id === centralEntity ? NETWORK_COLORS.highlightNode : NETWORK_COLORS.node)
            .call(d3.drag()
                .on('start', dragstarted)
                .on('drag', dragged)
                .on('end', dragended));

        // Adjust label positioning for smaller nodes
        const labels = svg.append('g')
            .selectAll('text')
            .data(network.nodes)
            .enter()
            .append('text')
            .text(d => d.id)
            .attr('font-size', '12px')
            .attr('fill', NETWORK_COLORS.text)
            .attr('text-anchor', 'middle')
            .attr('dy', 20); // Reduced from 25 to match smaller nodes

        // Update positions on each tick
        simulation.on('tick', () => {
            links
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            nodes
                .attr('cx', d => d.x)
                .attr('cy', d => d.y);

            labels
                .attr('x', d => d.x)
                .attr('y', d => d.y);
        });

        // Drag functions
        function dragstarted(event) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }

        function dragged(event) {
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }

        function dragended(event) {
            if (!event.active) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }
    }
}

// Initialize the entity tracker
const entityTracker = new EntityTracker();
