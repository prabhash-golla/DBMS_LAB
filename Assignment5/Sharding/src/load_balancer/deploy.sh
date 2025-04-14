#! /bin/bash
set -x
set -e

postgres &
while ! pg_isready ; do sleep 1; done
python loadBalancer.py &

jobs_array=$(jobs -p | tr '\n' ' ')

trap "kill -SIGTERM $jobs_array; wait; exit 0" SIGTERM
trap "kill -SIGINT  $jobs_array; wait; exit 0" SIGINT

wait
