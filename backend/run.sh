#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "Building shm_writer..."
make clean && make

echo "Cleaning old shared memory..."
rm -f /dev/shm/sysmon_shm

echo "Starting shm_writer..."
./shm_writer &
WRITER_PID=$!
trap 'kill $WRITER_PID 2>/dev/null' EXIT

sleep 2

echo "Initializing authentication..."
python3 -c "import auth; auth.print_startup_credentials()"

echo "Starting FastAPI server..."
/home/ajay/Desktop/SIH/env/bin/uvicorn main:app --app-dir /home/ajay/Desktop/SIH/backend --host 0.0.0.0 --port 8000
