FROM kong:latest

USER root

# Install envsubst
RUN apt-get update && \
    apt-get install -y gettext-base && \
    rm -rf /var/lib/apt/lists/*

# Copy configuration template and entrypoint script
COPY kong.yml.template /etc/kong/kong.yml.template
COPY docker-entrypoint.sh /docker-entrypoint.sh

# Set the default P_VALUE for traffic distribution
# ARG P_VAL=50
# ENV P_VALUE=${P_VAL}

# Make the entrypoint script executable
RUN chmod +x /docker-entrypoint.sh

USER kong

EXPOSE 8000 8443 8005 8444

ENTRYPOINT ["/docker-entrypoint.sh"]
