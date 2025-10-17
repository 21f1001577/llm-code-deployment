# LLM Code Deployment — Phase 1 (FastAPI)

##  Setup (Local)

1. **Initialize the project**
   ```bash
   uv init
   uv add fastapi uvicorn python-dotenv PyGithub requests pydantic
   uv sync
   uv export > requirements.txt
