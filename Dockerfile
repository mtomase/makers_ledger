# Use the newer Python 3.13 runtime as a parent image
FROM python:3.13-slim

# --- Install Microsoft ODBC Driver for SQL Server ---
# These commands are now updated for Debian 12 (Bookworm), the OS for the python:3.13 image.
RUN apt-get update && apt-get install -y curl gnupg

# Add Microsoft's official repository key
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -

# Add the Microsoft repository for Debian 12, which matches the new base image.
RUN curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list

# Update package lists and install the driver and its dependencies
RUN apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev

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