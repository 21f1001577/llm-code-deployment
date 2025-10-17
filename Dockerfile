# Use the official Python image
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for building some packages
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

# Copy only necessary files first (for caching)
COPY pyproject.toml uv.lock* requirements.txt* ./

# Install uv
RUN pip install uv

# Install project dependencies using uv (faster & reproducible)
RUN uv pip install --system -r requirements.txt || uv sync --frozen

# Copy the entire app
COPY . .

# Expose the default Hugging Face port
EXPOSE 7860

# Run the FastAPI app via uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
