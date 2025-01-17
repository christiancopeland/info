class ResearchSidebar {
    constructor() {
        this.sidebar = document.getElementById('research-sidebar');
        this.toggleButton = document.querySelector('.sidebar-toggle');
        
        if (!this.sidebar || !this.toggleButton) {
            console.error('Required sidebar elements not found:', {
                sidebar: !!this.sidebar,
                toggleButton: !!this.toggleButton
            });
            return;
        }

        this.setupEventListeners();
    }

    setupEventListeners() {
        // Sidebar toggle button
        this.toggleButton.addEventListener('click', () => {
            this.toggleSidebar();
            this.toggleButton.classList.toggle('clicked');
            console.log('Toggle button clicked state:', {
                isClicked: this.toggleButton.classList.contains('clicked'),
                position: window.getComputedStyle(this.toggleButton).left
            });
        });

        // Listen for project selection
        document.addEventListener('projectSelected', () => {
            console.log('Project selected, collapsing sidebar and updating toggle');
            this.collapseSidebar();
            this.toggleButton.classList.add('clicked');
            console.log('Toggle button state after project selection:', {
                isClicked: this.toggleButton.classList.contains('clicked'),
                position: window.getComputedStyle(this.toggleButton).left
            });
        });
    }

    toggleSidebar() {
        if (this.sidebar) {
            this.sidebar.classList.toggle('collapsed');
            console.log('Sidebar and toggle button states:', {
                sidebarCollapsed: this.sidebar.classList.contains('collapsed'),
                toggleClicked: this.toggleButton.classList.contains('clicked'),
                togglePosition: window.getComputedStyle(this.toggleButton).left
            });
        }
    }

    collapseSidebar() {
        if (this.sidebar && !this.sidebar.classList.contains('collapsed')) {
            this.sidebar.classList.add('collapsed');
            console.log('Sidebar and toggle button states after collapse:', {
                sidebarCollapsed: this.sidebar.classList.contains('collapsed'),
                toggleClicked: this.toggleButton.classList.contains('clicked'),
                togglePosition: window.getComputedStyle(this.toggleButton).left
            });
        }
    }
}

// Initialize sidebar when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.sidebarManager = new ResearchSidebar();
    console.log('Sidebar manager initialized with toggle button at:', 
        window.getComputedStyle(document.querySelector('.sidebar-toggle')).left
    );
});
