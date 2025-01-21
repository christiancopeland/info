class NewsFeed {
    constructor() {
        this.newsFeed = document.getElementById('newsFeed');
        this.articles = []; // Store articles for filtering
        this.initialize();
    }

    async initialize() {
        this.setupSearchInterface();
        await this.loadNews();
        this.setupSearchListeners();
    }

    setupSearchInterface() {
        // First, check if search container already exists
        const existingSearch = this.newsFeed.parentNode.querySelector('.news-search-container');
        if (existingSearch) {
            console.log('Search interface already exists');
            // Use existing elements
            this.searchInput = existingSearch.querySelector('#newsSearchInput');
            this.sourceFilter = existingSearch.querySelector('#sourceFilter');
            this.dateFromFilter = existingSearch.querySelector('#dateFromFilter');
            this.dateToFilter = existingSearch.querySelector('#dateToFilter');
            return;
        }

        // Create search container above news feed
        const searchContainer = document.createElement('div');
        searchContainer.className = 'news-search-container';
        searchContainer.innerHTML = `
            <div class="search-controls">
                <input type="text" id="newsSearchInput" placeholder="Search news..." class="news-search-input">
                <div class="search-filters">
                    <select id="sourceFilter" class="news-filter">
                        <option value="">All Sources</option>
                    </select>
                    <input type="date" id="dateFromFilter" class="news-filter" placeholder="From Date">
                    <input type="date" id="dateToFilter" class="news-filter" placeholder="To Date">
                </div>
            </div>
        `;
        
        this.newsFeed.parentNode.insertBefore(searchContainer, this.newsFeed);
        
        // Store references to search elements
        this.searchInput = document.getElementById('newsSearchInput');
        this.sourceFilter = document.getElementById('sourceFilter');
        this.dateFromFilter = document.getElementById('dateFromFilter');
        this.dateToFilter = document.getElementById('dateToFilter');
    }

    async loadNews() {
        try {
            const response = await fetch('/api/v1/news/articles', {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('Failed to load news');
            }

            this.articles = await response.json(); // Store articles
            this.updateSourceFilters(); // Populate source filter options
            this.renderNewsFeed(this.articles);
            
        } catch (error) {
            console.error('Error loading news:', error);
            this.articles = [];
            this.renderNewsFeed([]);
        }
    }

    updateSourceFilters() {
        // Get unique sources
        const sources = [...new Set(this.articles.map(article => {
            const sourceUrl = new URL(article.source_site);
            return sourceUrl.hostname.replace('www.', '');
        }))];

        // Add options to source filter
        sources.forEach(source => {
            const option = document.createElement('option');
            option.value = source;
            option.textContent = source;
            this.sourceFilter.appendChild(option);
        });
    }

    setupSearchListeners() {
        // Debounce search to avoid too many updates
        let searchTimeout;
        
        const performSearch = () => {
            const searchTerm = this.searchInput.value.toLowerCase();
            const selectedSource = this.sourceFilter.value;
            const fromDate = this.dateFromFilter.value;
            const toDate = this.dateToFilter.value;

            const filtered = this.articles.filter(article => {
                // Text search
                const matchesSearch = !searchTerm || 
                    article.title.toLowerCase().includes(searchTerm) ||
                    article.heading.toLowerCase().includes(searchTerm);

                // Source filter
                const sourceUrl = new URL(article.source_site);
                const sourceDomain = sourceUrl.hostname.replace('www.', '');
                const matchesSource = !selectedSource || sourceDomain === selectedSource;

                // Date filter
                const articleDate = new Date(article.scraped_at).toISOString().split('T')[0];
                const matchesFromDate = !fromDate || articleDate >= fromDate;
                const matchesToDate = !toDate || articleDate <= toDate;

                return matchesSearch && matchesSource && matchesFromDate && matchesToDate;
            });

            this.renderNewsFeed(filtered);
        };

        // Setup event listeners with debouncing for text search
        this.searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(performSearch, 300);
        });

        // Immediate search for filters
        this.sourceFilter.addEventListener('change', performSearch);
        this.dateFromFilter.addEventListener('change', performSearch);
        this.dateToFilter.addEventListener('change', performSearch);
    }

    renderNewsFeed(articles) {
        if (!this.newsFeed) return;
        
        this.newsFeed.innerHTML = '';
        
        if (!articles.length) {
            this.newsFeed.innerHTML = '<div class="empty-state">No news articles available</div>';
            return;
        }

        articles.forEach(article => {
            const sourceUrl = new URL(article.source_site);
            const sourceDomain = sourceUrl.hostname.replace('www.', '');
            
            const item = document.createElement('div');
            item.className = 'news-item';
            
            item.innerHTML = `
                <div class="news-metadata">
                    <span class="news-source">${sourceDomain}</span>
                    <span class="news-date">${new Date(article.scraped_at).toLocaleDateString()}</span>
                </div>
                <h4 class="news-title">${article.title}</h4>
                <p class="news-heading">${article.heading}</p>
                <a href="${article.url}" target="_blank" class="news-link">Read more</a>
            `;
            
            this.newsFeed.appendChild(item);
        });
    }
}

// Initialize news feed when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.newsFeed = new NewsFeed();
});
