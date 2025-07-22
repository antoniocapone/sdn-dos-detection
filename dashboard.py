import tkinter as tk
from tkinter import ttk
import requests
import threading
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class DoSMonitorGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("DoS Monitor Dashboard")
        self.window_width = 1000
        self.window_height = 600
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
        x_cordinate = int((screen_width/2) - (self.window_width/2))
        y_cordinate = int((screen_height/2) - (self.window_height/2))
        self.master.geometry(f"{self.window_width}x{self.window_height}+{x_cordinate}+{y_cordinate}")
        self.master.configure(bg="#1e1e1e")

        self.status_frame = tk.Frame(self.master, bg="#1e1e1e")
        self.status_frame.pack(fill=tk.X, pady=5)

        self.connectivity_indicator = tk.Label(self.status_frame, text="Disconnected", bg="red", fg="white", width=15)
        self.connectivity_indicator.pack(side=tk.LEFT, padx=10)

        self.current_threshold_var = tk.StringVar()
        self.threshold_display = tk.Label(self.status_frame, textvariable=self.current_threshold_var, bg="#1e1e1e", fg="white")
        self.threshold_display.pack(side=tk.LEFT)

        self.threshold_entry = tk.Entry(self.status_frame)
        self.threshold_entry.pack(side=tk.LEFT, padx=10)
        self.set_button = tk.Button(self.status_frame, text="Update Threshold", command=self.update_threshold)
        self.set_button.pack(side=tk.LEFT)

        self.tree = ttk.Treeview(self.master, columns=("DPID", "Port", "Throughput", "Alarmed"), show='headings')
        for col in self.tree["columns"]:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150)
        self.tree.pack(expand=False, fill=tk.X, pady=10)

        self.fig, self.ax = plt.subplots(figsize=(8, 2))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.master)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.port_history = {}
        self.max_points = 20

        self.update_thread = threading.Thread(target=self.update_loop)
        self.update_thread.daemon = True
        self.update_thread.start()

    def update_threshold(self):
        try:
            new_threshold = int(self.threshold_entry.get())
            res = requests.post("http://localhost:5001/api/threshold", json={"threshold": new_threshold})
            if res.ok:
                self.current_threshold_var.set(f"Current Threshold: {new_threshold} B/s")
        except:
            pass

    def update_loop(self):
        while True:
            connected = False
            try:
                res = requests.get("http://localhost:5001/api/status")
                if res.ok:
                    connected = True
                    data = res.json()
                    ports = data["ports"]
                    threshold = data["threshold"]
                    self.current_threshold_var.set(f"Current Threshold: {threshold} B/s")
                    self.tree.delete(*self.tree.get_children())
                    for port_info in ports:
                        dpid = port_info["dpid"]
                        port = port_info["port"]
                        throughput = port_info["throughput"]
                        alarmed = "YES" if port_info["alarmed"] else "NO"
                        self.tree.insert("", "end", values=(dpid, port, f"{throughput:.2f}", alarmed))

                        key = f"{dpid}:{port}"
                        if key not in self.port_history:
                            self.port_history[key] = []
                        self.port_history[key].append(throughput)
                        if len(self.port_history[key]) > self.max_points:
                            self.port_history[key] = self.port_history[key][-self.max_points:]

                    self.update_plot()
            except:
                connected = False

            self.connectivity_indicator.config(
                text="Connected" if connected else "Disconnected",
                bg="green" if connected else "red"
            )
            time.sleep(2)

    def update_plot(self):
        self.ax.clear()
        for key, values in self.port_history.items():
            self.ax.plot(values, label=key)
        self.ax.set_title("Port Throughput History")
        self.ax.set_ylabel("B/s")
        self.ax.legend(loc='upper right', fontsize='x-small')
        self.canvas.draw()

import matplotlib
matplotlib.use("TkAgg")

root = tk.Tk()
app = DoSMonitorGUI(root)
root.mainloop()
