#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MODO SENSORES - SISTEMA DE DETECCIÓN DE MICROPLÁSTICOS
Interfaz estilo dashboard con gráficas en tiempo real
"""

import tkinter as tk
from tkinter import ttk
import time
import os
import sys
import subprocess
import queue
import csv
from datetime import datetime

# ================= IMPORTAR MÓDULO COMPARTIDO =================
from sensor_shared import (
    sensor_queue, iniciar_hilo_sensores, detener_hilo_sensores,
    max_puntos, tds_history, temp_history, cap_history, time_history,
    grabando_datos, iniciar_grabacion, detener_grabacion, guardar_muestra_datos
)

# ================= GRÁFICAS =================
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# ================= CONFIGURACIÓN =================
COLOR_BG = "#0f0f1a"
COLOR_CARD = "#1a1a2e"
COLOR_CARD_LIGHT = "#16213e"
COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_SEC = "#8888aa"
COLOR_SI = "#27ae60"
COLOR_NO = "#e74c3c"
COLOR_PROB = "#f1c40f"
COLOR_ACCENT = "#3498db"
COLOR_GRAPH_TDS = "#27ae60"
COLOR_GRAPH_TEMP = "#e74c3c"
COLOR_GRAPH_CAP = "#f1c40f"

# ================= INICIAR SENSORES =================
print("⏳ Iniciando sistema de sensores...")
sensor_queue, CAP_BASE = iniciar_hilo_sensores()
print("✅ Hilo de sensores iniciado correctamente")

# ================= INTERFAZ GRÁFICA =================
root = tk.Tk()
root.title("DETECTOR DE MICROPLÁSTICOS - MODO SENSORES")
root.configure(bg=COLOR_BG)
root.geometry("1400x850+100+50")
root.minsize(1200, 700)

root.grid_columnconfigure(0, weight=3)
root.grid_columnconfigure(1, weight=2)
root.grid_rowconfigure(0, weight=1)

# ================= PANEL IZQUIERDO =================
left_panel = tk.Frame(root, bg=COLOR_BG)
left_panel.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)

tk.Label(left_panel, text="LECTURA DE SENSORES (TIEMPO REAL)",
         bg=COLOR_BG, fg=COLOR_TEXT, font=("Arial", 16, "bold")).pack(anchor="nw", pady=(0, 15))

# Frame para las tarjetas de sensores (grid 3x2)
sensors_frame = tk.Frame(left_panel, bg=COLOR_BG)
sensors_frame.pack(fill="x", pady=(0, 15))

for i in range(3):
    sensors_frame.grid_columnconfigure(i, weight=1)

# Variables para mostrar
tds_var = tk.StringVar(value="---")
temp_var = tk.StringVar(value="---")
voltaje_var = tk.StringVar(value="---")
corriente_var = tk.StringVar(value="---")
potencia_var = tk.StringVar(value="---")
cap_var = tk.StringVar(value="---")
entorno_var = tk.StringVar(value="---")

# Tarjeta TDS
card_tds = tk.Frame(sensors_frame, bg=COLOR_CARD, relief="solid", borderwidth=1)
card_tds.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
tk.Label(card_tds, text="💧 TDS (ppm)", bg=COLOR_CARD, fg=COLOR_TEXT,
         font=("Arial", 11, "bold")).pack(pady=(10, 5))
tk.Label(card_tds, textvariable=tds_var, bg=COLOR_CARD, fg=COLOR_SI,
         font=("Arial", 28, "bold")).pack(pady=(0, 5))
tk.Label(card_tds, text="Range: 0 - 2000 ppm", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 9)).pack(pady=(0, 10))

# Tarjeta Temperatura
card_temp = tk.Frame(sensors_frame, bg=COLOR_CARD, relief="solid", borderwidth=1)
card_temp.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
tk.Label(card_temp, text="🌡️ TEMPERATURA", bg=COLOR_CARD, fg=COLOR_TEXT,
         font=("Arial", 11, "bold")).pack(pady=(10, 5))
tk.Label(card_temp, textvariable=temp_var, bg=COLOR_CARD, fg=COLOR_ACCENT,
         font=("Arial", 28, "bold")).pack(pady=(0, 5))
tk.Label(card_temp, text="Range: 0 - 50 °C", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 9)).pack(pady=(0, 10))

# Tarjeta Voltaje
card_volt = tk.Frame(sensors_frame, bg=COLOR_CARD, relief="solid", borderwidth=1)
card_volt.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")
tk.Label(card_volt, text="⚡ VOLTAJE", bg=COLOR_CARD, fg=COLOR_TEXT,
         font=("Arial", 11, "bold")).pack(pady=(10, 5))
tk.Label(card_volt, textvariable=voltaje_var, bg=COLOR_CARD, fg=COLOR_ACCENT,
         font=("Arial", 28, "bold")).pack(pady=(0, 5))
tk.Label(card_volt, text="Range: 0 - 5 V", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 9)).pack(pady=(0, 10))

# Tarjeta Corriente
card_curr = tk.Frame(sensors_frame, bg=COLOR_CARD, relief="solid", borderwidth=1)
card_curr.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")
tk.Label(card_curr, text="🔌 CORRIENTE", bg=COLOR_CARD, fg=COLOR_TEXT,
         font=("Arial", 11, "bold")).pack(pady=(10, 5))
tk.Label(card_curr, textvariable=corriente_var, bg=COLOR_CARD, fg=COLOR_ACCENT,
         font=("Arial", 28, "bold")).pack(pady=(0, 5))
tk.Label(card_curr, text="Range: 0 - 10 mA", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 9)).pack(pady=(0, 10))

# Tarjeta Potencia
card_pow = tk.Frame(sensors_frame, bg=COLOR_CARD, relief="solid", borderwidth=1)
card_pow.grid(row=1, column=1, padx=5, pady=5, sticky="nsew")
tk.Label(card_pow, text="⚙️ POTENCIA", bg=COLOR_CARD, fg=COLOR_TEXT,
         font=("Arial", 11, "bold")).pack(pady=(10, 5))
tk.Label(card_pow, textvariable=potencia_var, bg=COLOR_CARD, fg=COLOR_ACCENT,
         font=("Arial", 28, "bold")).pack(pady=(0, 5))
tk.Label(card_pow, text="Range: 0 - 1000 mW", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 9)).pack(pady=(0, 10))

# Tarjeta Capacitancia
card_cap = tk.Frame(sensors_frame, bg=COLOR_CARD, relief="solid", borderwidth=1)
card_cap.grid(row=1, column=2, padx=5, pady=5, sticky="nsew")
tk.Label(card_cap, text="🧪 CAPACITANCIA", bg=COLOR_CARD, fg=COLOR_TEXT,
         font=("Arial", 11, "bold")).pack(pady=(10, 5))
tk.Label(card_cap, textvariable=cap_var, bg=COLOR_CARD, fg=COLOR_PROB,
         font=("Arial", 28, "bold")).pack(pady=(0, 5))
tk.Label(card_cap, text="Range: 0 - 10 µF", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 9)).pack(pady=(0, 10))

# ================= GRÁFICAS =================
graph_frame = tk.Frame(left_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
graph_frame.pack(fill="both", expand=True, pady=(10, 0))

tk.Label(graph_frame, text="TENDENCIA DE PARÁMETROS",
         bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(anchor="nw", padx=10, pady=(10, 5))

fig = Figure(figsize=(8, 4), facecolor=COLOR_CARD, dpi=100)
fig.subplots_adjust(hspace=0.4, left=0.1, right=0.95, top=0.95, bottom=0.1)

ax1 = fig.add_subplot(311)
ax1.set_facecolor(COLOR_CARD_LIGHT)
ax1.set_ylabel('TDS (ppm)', color=COLOR_GRAPH_TDS, fontsize=8)
ax1.tick_params(axis='y', labelcolor=COLOR_GRAPH_TDS, labelsize=7)
ax1.tick_params(axis='x', labelsize=7)

ax2 = fig.add_subplot(312)
ax2.set_facecolor(COLOR_CARD_LIGHT)
ax2.set_ylabel('Temperatura (°C)', color=COLOR_GRAPH_TEMP, fontsize=8)
ax2.tick_params(axis='y', labelcolor=COLOR_GRAPH_TEMP, labelsize=7)
ax2.tick_params(axis='x', labelsize=7)

ax3 = fig.add_subplot(313)
ax3.set_facecolor(COLOR_CARD_LIGHT)
ax3.set_xlabel('Tiempo (s)', fontsize=8)
ax3.set_ylabel('Capacitancia (µF)', color=COLOR_GRAPH_CAP, fontsize=8)
ax3.tick_params(axis='y', labelcolor=COLOR_GRAPH_CAP, labelsize=7)
ax3.tick_params(axis='x', labelsize=7)

canvas = FigureCanvasTkAgg(fig, master=graph_frame)
canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

# ================= PANEL DERECHO =================
right_panel = tk.Frame(root, bg=COLOR_BG)
right_panel.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)

# ===== Probabilidad =====
prob_frame = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
prob_frame.pack(fill="x", pady=(0, 15))

tk.Label(prob_frame, text="PROBABILIDAD DE MICROPLÁSTICOS",
         bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(pady=(15, 5))

prob_text = tk.StringVar(value="0.0%")
tk.Label(prob_frame, textvariable=prob_text, bg=COLOR_CARD, fg=COLOR_PROB,
         font=("Arial", 36, "bold")).pack(pady=(0, 5))

# ===== ENTORNO =====
entorno_frame = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
entorno_frame.pack(fill="x", pady=(0, 15))

tk.Label(entorno_frame, text="ENTORNO",
         bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(pady=(10, 5))

entorno_label = tk.Label(entorno_frame, textvariable=entorno_var, bg=COLOR_CARD, fg=COLOR_PROB,
                         font=("Arial", 24, "bold"))
entorno_label.pack(pady=(0, 10))

# ===== Estado =====
status_frame = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
status_frame.pack(fill="x", pady=(0, 15))

tk.Label(status_frame, text="ESTADO",
         bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(pady=(10, 5))

status_label = tk.Label(status_frame, text="✅ Sistema funcionando", bg=COLOR_CARD, fg=COLOR_SI,
                        font=("Arial", 14, "bold"))
status_label.pack(pady=(0, 10))

# ===== Fecha/Hora =====
datetime_frame = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
datetime_frame.pack(fill="x", pady=(0, 15))

fecha_var = tk.StringVar(value=datetime.now().strftime("%d/%m/%Y"))
hora_var = tk.StringVar(value=datetime.now().strftime("%H:%M:%S"))

tk.Label(datetime_frame, textvariable=fecha_var, bg=COLOR_CARD, fg=COLOR_ACCENT,
         font=("Arial", 14, "bold")).pack(pady=(10, 5))
tk.Label(datetime_frame, textvariable=hora_var, bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 18, "bold")).pack(pady=(0, 10))

# ===== CONTROL DE GRABACIÓN (NUEVO EN PANEL DERECHO) =====
grabacion_frame = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
grabacion_frame.pack(fill="x", pady=(0, 15))

tk.Label(grabacion_frame, text="CONTROL DE GRABACIÓN",
         bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(pady=(10, 5))

# Frame para botones de grabación
botones_grabacion = tk.Frame(grabacion_frame, bg=COLOR_CARD)
botones_grabacion.pack(pady=(5, 10))

# Botón Iniciar Grabación
btn_iniciar = tk.Button(botones_grabacion, text="▶️ INICIAR TOMA DE DATOS", 
                        command=iniciar_grabacion,
                        bg="#27ae60", fg="white", font=("Arial", 10, "bold"),
                        relief="flat", padx=15, pady=8, cursor="hand2")
btn_iniciar.pack(side="left", padx=5)

# Botón Detener Grabación
btn_detener = tk.Button(botones_grabacion, text="⏹️ DETENER TOMA DE DATOS", 
                        command=detener_grabacion,
                        bg="#e74c3c", fg="white", font=("Arial", 10, "bold"),
                        relief="flat", padx=15, pady=8, cursor="hand2")
btn_detener.pack(side="left", padx=5)

# Etiqueta de estado de grabación
estado_grabacion_var = tk.StringVar(value="📊 Grabación: INACTIVA")
estado_grabacion_label = tk.Label(grabacion_frame, textvariable=estado_grabacion_var,
                                   bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
                                   font=("Arial", 10, "bold"))
estado_grabacion_label.pack(pady=(0, 10))

# ===== Botón volver =====
def volver_menu():
    # Detener grabación si está activa
    if grabando_datos:
        detener_grabacion()
    detener_hilo_sensores()
    root.destroy()
    subprocess.run(["python3", "interfaz.py"])
    sys.exit()

volver_btn = tk.Button(right_panel, text="🏠 VOLVER AL MENÚ", command=volver_menu,
                       bg="#e67e22", fg="white", font=("Arial", 11, "bold"),
                       relief="flat", padx=20, pady=10, cursor="hand2")
volver_btn.pack(fill="x", pady=(10, 0))

# ================= ACTUALIZACIÓN EN TIEMPO REAL =================
def update_datos():
    try:
        sd = sensor_queue.get_nowait()
        
        # Actualizar valores de la interfaz
        tds_var.set(f"{sd['tds_ppm']:.1f}")
        temp_var.set(f"{sd['temp']:.1f}")
        voltaje_var.set(f"{sd['voltaje']:.2f}")
        
        corriente_val = sd['corriente']
        if abs(corriente_val) < 0.001:
            corriente_val = 0.0
        corriente_var.set(f"{corriente_val:.3f}")
        
        potencia_val = sd['potencia']
        if potencia_val < 0.001:
            potencia_val = 0.0
        potencia_var.set(f"{potencia_val:.3f}")
        
        # ========== USAR LA CAPACITANCIA HÍBRIDA ==========
        cap_var.set(f"{sd['capacitancia_hibrida']:.4f}")
        entorno_var.set(sd['entorno'])
        
        # Probabilidad
        prob_val = min(100, max(0, (sd['tds_ppm'] / 200) * 100))
        prob_text.set(f"{prob_val:.1f}%")
        
        # Fecha/Hora
        fecha_var.set(datetime.now().strftime("%d/%m/%Y"))
        hora_var.set(datetime.now().strftime("%H:%M:%S"))
        
        # ========== GUARDAR DATOS SI ESTÁ GRABANDO ==========
        guardar_muestra_datos()
        
        # Actualizar estado de grabación
        if grabando_datos:
            estado_grabacion_var.set("📊 Grabación: ACTIVA")
            estado_grabacion_label.config(fg=COLOR_SI)
        else:
            estado_grabacion_var.set("📊 Grabación: INACTIVA")
            estado_grabacion_label.config(fg=COLOR_TEXT_SEC)
        
        # Actualizar gráficas
        ax1.clear()
        ax2.clear()
        ax3.clear()
        
        ax1.set_facecolor(COLOR_CARD_LIGHT)
        ax2.set_facecolor(COLOR_CARD_LIGHT)
        ax3.set_facecolor(COLOR_CARD_LIGHT)
        
        if len(time_history) > 1:
            ax1.plot(time_history, tds_history, color=COLOR_GRAPH_TDS, linewidth=2)
            ax1.set_ylabel('TDS (ppm)', color=COLOR_GRAPH_TDS, fontsize=8)
            ax1.tick_params(axis='y', labelcolor=COLOR_GRAPH_TDS, labelsize=7)
            
            ax2.plot(time_history, temp_history, color=COLOR_GRAPH_TEMP, linewidth=2)
            ax2.set_ylabel('Temperatura (°C)', color=COLOR_GRAPH_TEMP, fontsize=8)
            ax2.tick_params(axis='y', labelcolor=COLOR_GRAPH_TEMP, labelsize=7)
            
            ax3.plot(time_history, cap_history, color=COLOR_GRAPH_CAP, linewidth=2)
            ax3.set_xlabel('Tiempo (s)', fontsize=8)
            ax3.set_ylabel('Capacitancia (µF)', color=COLOR_GRAPH_CAP, fontsize=8)
            ax3.tick_params(axis='y', labelcolor=COLOR_GRAPH_CAP, labelsize=7)
        
        ax1.tick_params(axis='x', labelsize=7)
        ax2.tick_params(axis='x', labelsize=7)
        ax3.tick_params(axis='x', labelsize=7)
        
        canvas.draw()
        
    except queue.Empty:
        # No hay datos aún, no hacer nada
        pass
    except Exception as e:
        print(f"Error en update_datos: {e}")
    
    root.after(500, update_datos)

# Iniciar actualización
update_datos()

# Ejecutar
root.mainloop()