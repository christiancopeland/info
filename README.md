### Vision Statement
A comprehensive research and news monitoring platform that empowers journalists, investigators, and private citizens to conduct deep research while staying informed about relevant current events through automated tracking and analysis.

### Target Users
- Investigative journalists
- Private investigators
- Concerned citizens
- Amateur researchers

### Core Value Proposition
- Unified platform for document research and news monitoring
- Powerful search capabilities across multiple content types
- Automated entity tracking and alerting
- Research organization and synthesis tools


### How to use
- Install [Ollama]()
- Install [Docker](https://docs.docker.com/engine/) and pull the [Qdrant image](https://qdrant.tech/documentation/guides/installation/#)
- Clone and install Firecrawl locally, following this contributor's guide https://www.youtube.com/watch?v=LHqg5QNI4UY
- (Optional but recommended) Install [Conda](https://anaconda.org/anaconda/conda) or [Miniconda](https://www.anaconda.com/docs/getting-started/miniconda/install), and create an environment for the project 
- Install requirements in your conda environment after conda installing pip 
    - My preferred method to avoid conda installing:
    - ~/miniconda/envs/{env_name}/bin/pip install -r requirements.txt
- Run ./start_services.sh to start firecrawl and qdrant vector store
- Run sudo ollama serve, if bind address already in use, you're good to go  
- Run ./run_appcmd to start web server, and go to localhost:8000

### Issues
- If you have issues setting up and running locally, submit an issue and I will help you get it fixed up
