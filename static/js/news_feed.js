class NewsFeed {
    constructor() {
        this.newsFeed = document.getElementById('newsFeed');
        this.articles = []; // Store articles for filtering
        this.initialize();
        this.setupTabListener();
    }

    async initialize() {
        this.setupSearchInterface();
        this.setupRefreshButton();
        await this.loadNews();
        this.setupSearchListeners();
    }

    setupSearchInterface() {
        // First, check if search container already exists
        const existingSearch = this.newsFeed.parentNode.querySelector('.news-search-container');
        if (existingSearch) {
            console.log('Search interface already exists');
            // Use existing elements with more specific IDs
            this.searchInput = existingSearch.querySelector('#newsSearchInput');
            this.sourceFilter = existingSearch.querySelector('#newsSourceSelect');  // Changed ID
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
                    <select id="newsSourceSelect" class="news-filter">  <!-- Changed ID -->
                        <option value="">All Sources</option>
                    </select>
                    <input type="date" id="dateFromFilter" class="news-filter" placeholder="From Date">
                    <input type="date" id="dateToFilter" class="news-filter" placeholder="To Date">
                </div>
            </div>
        `;
        
        this.newsFeed.parentNode.insertBefore(searchContainer, this.newsFeed);
        
        // Store references to search elements with updated ID
        this.searchInput = document.getElementById('newsSearchInput');
        this.sourceFilter = document.getElementById('newsSourceSelect');  // Changed ID
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
            item.dataset.articleId = article.id;
            
            item.innerHTML = `
                <div class="news-metadata">
                    <span class="news-source">${sourceDomain}</span>
                    <span class="news-date">${new Date(article.scraped_at).toLocaleDateString()}</span>
                </div>
                <h4 class="news-title">${article.title}</h4>
                <p class="news-heading">${article.heading}</p>
                <div class="news-actions">
                    <a href="${article.url}" target="_blank" class="news-link">Read more</a>
                    <button class="analyze-button" data-article-id="${article.id}">
                        <i class="fas fa-brain"></i> Analyze
                    </button>
                </div>
                <div class="analysis-container" id="analysis-${article.id}" style="display: none;">
                    <div class="analysis-content"></div>
                    <div class="analysis-loading" style="display: none;">
                        <i class="fas fa-spinner fa-spin"></i> Generating analysis...
                    </div>
                </div>
            `;
            
            // Add click handler to the entire news item
            item.addEventListener('click', (event) => {
                // Don't trigger if clicking the "Read more" link
                if (event.target.classList.contains('news-link')) {
                    return;
                }

                // Remove selected class from all items
                document.querySelectorAll('.news-item').forEach(item => {
                    item.classList.remove('selected');
                });

                // Add selected class to clicked item
                item.classList.add('selected');

                // Call the select endpoint and send WebSocket command
                fetch(`/api/v1/news/articles/${article.id}/select`, {
                    method: 'POST',
                    credentials: 'include'
                }).then(response => {
                    if (response.ok) {
                        if (window.wsManager) {
                            window.wsManager.sendCommand('article_context', {
                                action: 'select',
                                articleId: article.id,
                                title: article.title,
                                url: article.url
                            });
                        }
                    }
                }).catch(error => {
                    console.error('Error selecting article:', error);
                });
            });
            
            // Add click handler for the "Read more" link
            const readMoreLink = item.querySelector('.news-link');
            readMoreLink.addEventListener('click', (event) => {
                event.stopPropagation();  // Prevent triggering the item click
                this.handleArticleClick(event, readMoreLink);
            });

            // Add analyze button click handler
            const analyzeButton = item.querySelector('.analyze-button');
            analyzeButton.addEventListener('click', async (event) => {
                event.stopPropagation();
                await this.handleAnalyzeClick(article);
            });
            
            this.newsFeed.appendChild(item);
        });
    }

    handleArticleClick(event, linkElement) {
        // Send WebSocket command before opening the article
        if (window.wsManager) {
            const articleData = {
                id: linkElement.closest('.news-item').dataset.articleId,
                title: linkElement.closest('.news-item').querySelector('.news-title').textContent,
                heading: linkElement.closest('.news-item').querySelector('.news-heading').textContent,
                url: linkElement.href
            };

            window.wsManager.sendCommand('article_context', {
                action: 'view',
                articleId: articleData.id,
                title: articleData.title,
                url: articleData.url
            });
        }
    }

    async handleAnalyzeClick(article) {
        console.log('Starting analysis for article:', article.id); // Debug log
        const analysisContainer = document.querySelector(`#analysis-${article.id}`);
        const analysisContent = analysisContainer.querySelector('.analysis-content');
        const loadingIndicator = analysisContainer.querySelector('.analysis-loading');

        // Show loading state
        analysisContainer.style.display = 'block';
        analysisContent.style.display = 'none';
        loadingIndicator.style.display = 'block';

        try {
            // First get the article content
            console.log('Fetching article content...'); // Debug log
            const contentResponse = await fetch(`/api/v1/news/articles/${article.id}/content`);
            if (!contentResponse.ok) {
                throw new Error('Failed to fetch article content');
            }
            const articleData = await contentResponse.json();
            
            // Generate new analysis
            const messages = [
                { 
                    role: "user", 
                    content: `Please analyze this news article:
Title: ${article.title}
URL: ${article.url}
Content: ${articleData.content}

Please provide a detailed analysis focusing on:
1. Key facts and claims
2. Sources cited
3. Context and background
4. Potential biases or missing information
5. Related topics for further research`
                }
            ];

            console.log('Sending analysis request with messages:', messages); // Debug log

            const analysisResponse = await fetch('/api/v1/research_assistant/generate-analysis-from-news-article', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages })
            });

            if (!analysisResponse.ok) {
                console.error('Analysis generation failed:', await analysisResponse.text()); // Debug log
                throw new Error('Failed to generate analysis');
            }

            const analysis = await analysisResponse.json();
            console.log('Analysis generated:', analysis); // Debug log
            const analysisText = analysis.analysis;

            // Store the analysis (overwriting any existing one)
            console.log('Storing new analysis...'); // Debug log
            await fetch(`/api/v1/news/articles/${article.id}/analysis`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: analysisText })
            });

            // Show analysis in both places
            console.log('Displaying analysis'); // Debug log
            analysisContent.innerHTML = marked.parse(analysisText);
            loadingIndicator.style.display = 'none';
            analysisContent.style.display = 'block';

            // Send to chat
            if (window.wsManager) {
                console.log('Sending analysis to chat'); // Debug log
                window.wsManager.appendMessage('assistant', `## Analysis of "${article.title}"\n\n${analysisText}`);
            }

        } catch (error) {
            console.error('Error handling analysis:', error); // Debug log
            analysisContent.innerHTML = '<div class="error">Failed to generate analysis. Please try again.</div>';
            loadingIndicator.style.display = 'none';
            analysisContent.style.display = 'block';
        }
    }

    setupTabListener() {
        // Listen for clicks on the News tab button
        const newsTabButton = document.querySelector('.tab-button[data-tab="newsTab"]');
        if (newsTabButton) {
            newsTabButton.addEventListener('click', () => {
                // Clear entity tab content while preserving structure
                const entityList = document.getElementById('entityList');
                if (entityList) {
                    entityList.innerHTML = ''; // Clear only the inner content
                }
                
                // Ensure news feed container exists
                if (!this.newsFeed) {
                    const newsTab = document.getElementById('newsTab');
                    if (newsTab) {
                        newsTab.innerHTML = '<div class="news-feed" id="newsFeed"></div>';
                        this.newsFeed = document.getElementById('newsFeed');
                    }
                }
                
                // Reinitialize the news feed interface
                this.setupSearchInterface();
                this.loadNews();
            });
        }
    }

    setupRefreshButton() {
        // First, check if the news header already exists
        let newsHeader = this.newsFeed.parentNode.querySelector('.news-header');
        if (!newsHeader) {
            newsHeader = document.createElement('div');
            newsHeader.className = 'news-header';
            this.newsFeed.parentNode.insertBefore(newsHeader, this.newsFeed);
        }

        // Add refresh button if it doesn't exist
        if (!newsHeader.querySelector('.refresh-button')) {
            const refreshButton = document.createElement('button');
            refreshButton.className = 'refresh-button';
            refreshButton.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
            refreshButton.addEventListener('click', async (e) => {
                if (refreshButton.classList.contains('loading')) return;
                
                refreshButton.classList.add('loading');
                try {
                    // Call the rescrape endpoint
                    const response = await fetch('/api/v1/news/articles/rescrape', {
                        method: 'POST'
                    });
                    
                    if (!response.ok) {
                        throw new Error('Failed to rescrape articles');
                    }
                    
                    const result = await response.json();
                    
                    // Show a notification with the results
                    const message = `Rescrape completed:\n${result.processed} processed\n${result.failed} failed`;
                    alert(message);
                    
                    // Reload the news feed
                    await this.loadNews();
                    
                } catch (error) {
                    console.error('Error rescraping articles:', error);
                    alert('Failed to rescrape articles. Please try again later.');
                } finally {
                    refreshButton.classList.remove('loading');
                }
            });
            
            newsHeader.appendChild(refreshButton);
        }
    }
}

// Initialize news feed when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.newsFeed = new NewsFeed();
});
