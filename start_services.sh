#!/bin/bash

# Redirect all background process output to logs and prevent stdin blocking
(trap 'kill 0' SIGINT; 
    # Start firecrawl workers and api
    cd ~/firecrawl/apps/api
    pnpm run workers > ~/workers.log 2>&1 < /dev/null &
    pnpm run start > ~/api.log 2>&1 < /dev/null &

    # Start qdrant
    cd ~/AI/local_stuff/InformationIngestion
    ./startqdrant > ~/qdrant.log 2>&1 < /dev/null &

    # Start ollama (ensure sudo doesn't prompt for password)
    cd ~/
    sudo ollama serve > ~/ollama.log 2>&1 < /dev/null &

    # Wait for all background processes
    wait
)