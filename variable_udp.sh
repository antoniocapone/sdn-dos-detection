#!/bin/bash

# IP del target
SERVER_IP="10.0.0.3"
# Durata di ogni burst in secondi
DURATION=5

# Loop infinito
while true; do

    RATE=$(shuf -i 100-3000 -n 1)k
    echo "[UDP] Sending to $SERVER_IP at rate $RATE for $DURATION seconds"

    iperf -c "$SERVER_IP" -u -b "$RATE" -t "$DURATION"

    sleep 2
done
