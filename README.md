---
title: LLM Code Deployment
emoji: ⚙️
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
license: mit
---

# LLM Code Deployment

This Space hosts a FastAPI-based automation service for building and deploying
LLM-generated code projects. It uses the Hugging Face **Docker runtime** and 
runs automatically via Uvicorn on port 7860.


# LLM Code Deployment — Phase 1 (FastAPI)

##  Setup (Local)

1. **Initialize the project**
   ```bash
   uv init
   uv add fastapi uvicorn python-dotenv PyGithub requests pydantic
   uv sync
   uv export > requirements.txt
