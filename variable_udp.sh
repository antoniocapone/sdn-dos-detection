#!/bin/bash

# IP del server (modifica se diverso)
SERVER_IP="10.0.0.3"
# Durata di ogni burst in secondi
DURATION=5

# Loop infinito
while true; do
    # Estrai un bitrate casuale tra 100kbit/s e 3Mbit/s
    RATE=$(shuf -i 100-3000 -n 1)k
    echo "[UDP] Sending to $SERVER_IP at rate $RATE for $DURATION seconds"

    # Avvia il traffico UDP con iperf
    iperf -c "$SERVER_IP" -u -b "$RATE" -t "$DURATION"

    # Pausa di 2 secondi tra un burst e l'altro
    sleep 2
done
