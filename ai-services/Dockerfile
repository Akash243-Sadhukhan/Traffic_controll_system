FROM python:3.11-slim

# Install system dependencies for OpenCV and Mac support
# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ... (previous setup)
# 1. Set the working directory
WORKDIR /app

# 2. Copy the requirements and install (stays cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy the rest of the project files
COPY . .

# 4. Start the app from the src directory context
WORKDIR /app/src
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]