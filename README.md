This repository contains the source code for the "SDN DoS Detection" project, developed for the "Network and Cloud Infrastructures" course at "Università degli Studi di Napoli Federico II", during the 2024/25 academic year.

A real-time Denial of Service (DoS) detection and mitigation system built using *Software Defined Networking (SDN)* principles. This project leverages *Mininet* to simulate a network environment, *Ryu* as the SDN controller, and the *OpenFlow* protocol to dynamically monitor and control traffic at the network edge.

---

## 📌 Project Overview

This system detects UDP-based DoS attacks by monitoring the *throughput of switch ports* and applying countermeasures automatically. When excessive traffic is detected from a specific host or port, the controller installs a blocking rule using OpenFlow to halt malicious traffic in real-time. A dynamic threshold is used to trigger alerts, which can be updated through a RESTful API.

---

## ⚙ Components

- *Mininet* — Network emulator used to create a virtual topology of hosts and switches.
- *Ryu Controller* — Python-based OpenFlow controller that handles detection, reaction, and REST API exposure.
- *Tkinter GUI* — User interface to monitor the system status, visualize real-time throughput graphs, and dynamically adjust detection thresholds.
- *REST API* — Exposes the internal state of the controller to external tools like the GUI.

---

## 🧠 Features

- 📡 *Live traffic monitoring* on each switch port via OpenFlow stats.
- 🔒 *Automatic blocking* of ports exceeding a configurable traffic threshold.
- ♻ *Unblocking* of ports once traffic normalizes.
- 🖥 *Real-time GUI* displaying the status of each port, current throughput, and system connectivity.
- 🧮 *Graphical throughput visualization* with dynamic updates.
- 🧵 Multithreaded architecture for efficient monitoring and responsiveness.


