# Use the newer Python 3.12 runtime as a parent image
FROM python:3.12-slim

# --- Install Microsoft ODBC Driver for SQL Server (Updated with modern GPG key handling) ---

# Step 1: Update apt and install prerequisite packages.
# gnupg is needed for key management, apt-transport-https allows apt to use https repos.
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    apt-transport-https

# Step 2: Download and store the Microsoft GPG key in the recommended location.
# We download the key, de-armor it (convert it to the right format), and save it.
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg

# Step 3: Create the repository source file, explicitly pointing to the GPG key.
# The [signed-by=...] part tells apt which key to use for this specific repository.
RUN echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list

# Step 4: Update package lists again to include the new repository, then install the drivers.
# This apt-get update will now succeed because it can verify the Microsoft repo.
RUN apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev

# --- Application Setup (remains the same) ---
# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# Expose the port Streamlit will run on
EXPOSE 8501

# Define the command to run your app
CMD ["streamlit", "run", "main_app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]