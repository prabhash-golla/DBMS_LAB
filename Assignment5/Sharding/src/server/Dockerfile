# use python alphine and store the builder
FROM python:3.11-alpine3.19 AS builder

ENV PYTHONUNBUFFERED 1

# use virtual env to insstall reqs
RUN python -m venv /opt/venv
ENV PATH "/opt/venv/bin:$PATH"

COPY requirements.txt /
RUN pip install --upgrade pip && \
	pip install --upgrade --no-cache-dir --requirement /requirements.txt

# runner
FROM postgres:16.2-alpine3.19 AS runner

# add to root group(sudo access needed)
RUN adduser postgres root
RUN ln -s /usr/share/zoneinfo/Asia/Kolkata /etc/localtime

WORKDIR /app

RUN apk --no-cache update && \
	apk add --no-cache python3

# get only the required things from builder( this reduced the size of the image)
COPY --from=builder /opt/venv /opt/venv
RUN rm -rf /opt/venv/bin/python && \
	ln -s /usr/bin/python /opt/venv/bin/python

# env variables
ENV PATH "/opt/venv/bin:$PATH"
ENV PYTHONPATH "/opt/venv/lib/python3.11/site-packages:$PYTHONPATH"
ENV PYTHONUNBUFFERED 1

# using entrypoint.sh to run for us
COPY --chmod=777 my-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["my-entrypoint.sh"]

WORKDIR /app
COPY --chmod=777 init/ /docker-entrypoint-initdb.d/
COPY --chmod=777 . .

# finally run deploy.sh(it sets up db and starts the server)
CMD ["./deploy.sh"]
