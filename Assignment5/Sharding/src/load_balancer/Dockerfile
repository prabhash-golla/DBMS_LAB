# Stage 1: Build stage
FROM python:3.11-alpine3.19 as builder

ENV PYTHONUNBUFFERED 1

# Enable venv
RUN python -m venv /opt/venv
ENV PATH "/opt/venv/bin:$PATH"

# Copy only the requirements file to optimize caching
COPY requirements.txt /

# Install dependencies
RUN pip install --upgrade pip && \
	pip install --upgrade --no-cache-dir --requirement /requirements.txt

# Stage 2: Final stage
FROM postgres:16.2-alpine3.19 as runner

# Add postgres user to the root group
RUN adduser postgres root

# Set time zone
RUN ln -s /usr/share/zoneinfo/Asia/Kolkata /etc/localtime

# Install python
RUN apk --no-cache update && \
	apk add --no-cache python3

# Copy only the necessary files from the builder stage
COPY --from=builder /opt/venv /opt/venv
RUN rm -rf /opt/venv/bin/python && \
	ln -s /usr/bin/python /opt/venv/bin/python

# Set the environment variables
ENV PATH "/opt/venv/bin:$PATH"
ENV PYTHONPATH "/opt/venv/lib/python3.11/site-packages:$PYTHONPATH"
ENV PYTHONUNBUFFERED 1

# Entry point
COPY --chmod=777 my-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["my-entrypoint.sh"]

# Set the working directory
WORKDIR /app

# Set the init scripts
COPY --chmod=777 init/ /docker-entrypoint-initdb.d/

# Copy the application
COPY --chmod=777 . .

# Deploy the application
CMD ["./deploy.sh"]
