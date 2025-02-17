# Use an official Python runtime as a parent image
FROM python:3.8-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8880 available to the world outside this container
EXPOSE 8880

# Define environment variable
#ENV NAME World

# Command to run the application
CMD ["uvicorn", "center_server:app", "--host", "0.0.0.0", "--port", "8880"]
