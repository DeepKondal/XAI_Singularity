#!/bin/bash
set -e

# Check if P_VALUE is set
if [ -z "$P_VALUE" ]; then
    echo "P_VALUE is not set, using default value of 50"
    P_VALUE=50
fi

# Set weights for all versions of all services
export DATAPROCESS_V1_WEIGHT=$P_VALUE
export DATAPROCESS_V2_WEIGHT=$((100 - P_VALUE))
export MODELSERVER_V1_WEIGHT=$P_VALUE
export MODELSERVER_V2_WEIGHT=$((100 - P_VALUE))
export XAI_SERVICE_V1_WEIGHT=$P_VALUE
export XAI_SERVICE_V2_WEIGHT=$((100 - P_VALUE))

# Replace environment variables in kong.yml.template to create kong.yml
envsubst < /etc/kong/kong.yml.template > /etc/kong/kong.yml

# Print the final kong.yml for debugging
cat /etc/kong/kong.yml

# Prepare Kong with the new configuration
kong prepare -p /usr/local/kong

# Start Kong
exec kong start --nginx-conf /usr/local/kong/nginx.conf --vv
