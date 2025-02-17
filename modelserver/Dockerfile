# Use an official Python runtime as a parent image
FROM python:3.9

# Set the working directory in the container
WORKDIR /app


# Install any needed packages specified in requirements.txt
# First, make sure to update the package list and install the libraries needed for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
 && rm -rf /var/lib/apt/lists/*

 
# Copy the current directory contents into the container at /usr/src/app
COPY . /app



RUN pip install scikit-learn==1.3.2 scipy==1.11.4 torch torchvision torchaudio

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8002 available to the world outside this container
EXPOSE 8002

# Run model_server.py when the container launches
#CMD ["python", "model_server.py"]
CMD ["uvicorn", "model_server:app", "--host", "0.0.0.0", "--port", "8002"]
