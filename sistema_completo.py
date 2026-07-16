#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SISTEMA COMPLETO - DETECTOR DE MICROPLÁSTICOS
Dashboard integrado: CNN + Sensores + Fusión + Gráficas + Historial
VERSIÓN OPTIMIZADA: CNN en hilo separado + gráfica cada 5 frames
"""

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
import cv2
import numpy as np
import time
import os
import sys
import subprocess
import threading
import queue
from datetime import datetime

# ================= IMPORTAR MÓDULO COMPARTIDO DE SENSORES =================
from sensor_shared import (
    sensor_queue, iniciar_hilo_sensores, detener_hilo_sensores,
    max_puntos, sensor_history, time_history
)

# ================= GRÁFICAS =================
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# ================= CNN =================
from picamera2 import Picamera2
from tflite_runtime.interpreter import Interpreter

# ================= CONFIGURACIÓN GENERAL =================
BASE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(BASE, "modelo_microplasticos.tflite")
CAPTURAS = os.path.join(BASE, "capturas_completo")

IMG_SIZE = 224
THRESHOLD_SI = 0.4
THRESHOLD_PROB = 0.2

# Colores
COLOR_BG = "#0f0f1a"
COLOR_CARD = "#1a1a2e"
COLOR_CARD_LIGHT = "#16213e"
COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_SEC = "#8888aa"
COLOR_SI = "#27ae60"
COLOR_NO = "#e74c3c"
COLOR_PROB = "#f1c40f"
COLOR_ACCENT = "#3498db"
COLOR_CNN = "#27ae60"
COLOR_SENSOR = "#f1c40f"
COLOR_FUSION = "#3498db"

os.makedirs(CAPTURAS, exist_ok=True)

# ================= VARIABLES GLOBALES =================
# CNN
contador_si = 0
contador_no = 0
contador_prob = 0
running = True
detection_paused = False
current_frame = None
ultima_confianza = 0.0
ultima_clasificacion = "NO"
ultima_forma = "indefinido"
ultima_tamano = "indefinido"
imagenes_procesadas = 0

# Fusión
peso_cnn = 0.6
peso_sensor = 0.4
cnn_history = []
fusion_history = []

# Colas
cnn_queue = queue.Queue()
cnn_queue_resultados = queue.Queue()
cnn_running = True

# ================= INICIAR SENSORES =================
print("⏳ Iniciando sistema de sensores...")
sensor_queue, CAP_BASE = iniciar_hilo_sensores()
print("✅ Hilo de sensores iniciado correctamente")
running_sensors = True

# ================= INICIALIZAR CÁMARA =================
def init_camara():
    try:
        picam = Picamera2()
        picam.stop()
        picam.close()
        time.sleep(0.5)
    except:
        pass
    
    picam = Picamera2()
    picam.configure(picam.create_video_configuration(
        main={"size": (640, 480), "format": "RGB888"}))
    picam.start()
    time.sleep(1)
    return picam

# ================= INICIALIZAR MODELO =================
def init_modelo():
    interpreter = Interpreter(model_path=MODEL)
    interpreter.allocate_tensors()
    input_idx = interpreter.get_input_details()[0]["index"]
    output_idx = interpreter.get_output_details()[0]["index"]
    return interpreter, input_idx, output_idx

picam = init_camara()
interpreter, input_idx, output_idx = init_modelo()

# ================= FUNCIONES CNN =================
def detectar_objetos(imagen):
    gris = cv2.cvtColor(imagen, cv2.COLOR_RGB2GRAY)
    gris = cv2.GaussianBlur(gris, (5, 5), 0)
    bordes = cv2.Canny(gris, 30, 100)
    kernel = np.ones((3, 3), np.uint8)
    bordes = cv2.dilate(bordes, kernel, iterations=1)
    contornos, _ = cv2.findContours(bordes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contornos, bordes

def analizar_objeto(contornos):
    if len(contornos) == 0:
        return "indefinido", "indefinido"
    c = max(contornos, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < 50:
        return "indefinido", "pequeno"
    perim = cv2.arcLength(c, True)
    if perim == 0:
        return "indefinido", "medio"
    circularidad = (4 * np.pi * area) / (perim ** 2)
    rect = cv2.minAreaRect(c)
    ancho, alto = rect[1]
    if min(ancho, alto) > 0:
        relacion = max(ancho, alto) / min(ancho, alto)
        if relacion > 3:
            forma = "fibrosa"
        elif circularidad > 0.7:
            forma = "circular"
        else:
            forma = "fragmento"
    else:
        forma = "fragmento"
    if area < 500:
        tam = "pequeno"
    elif area < 2000:
        tam = "medio"
    elif area < 5000:
        tam = "grande"
    else:
        tam = "muy grande"
    return forma, tam

# ================= HILO DE CNN =================
def hilo_cnn():
    global current_frame, ultima_confianza, ultima_clasificacion
    global ultima_forma, ultima_tamano, imagenes_procesadas
    global contador_si, contador_no, contador_prob
    
    print("  🧵 Hilo de CNN iniciado...")
    
    while cnn_running:
        try:
            frame_data = cnn_queue.get(timeout=0.5)
            if frame_data is None:
                continue
                
            frame, timestamp = frame_data
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            contornos, _ = detectar_objetos(rgb)
            forma, tamano = analizar_objeto(contornos)
            
            start_inf = time.time()
            img = cv2.resize(rgb, (IMG_SIZE, IMG_SIZE))
            img = img.astype(np.float32) / 255.0
            img = np.expand_dims(img, 0)
            interpreter.set_tensor(input_idx, img)
            interpreter.invoke()
            p = float(interpreter.get_tensor(output_idx)[0][0])
            tiempo_inf = (time.time() - start_inf) * 1000
            
            is_micro = p >= 0.5
            conf = p if is_micro else 1 - p
            
            if conf >= THRESHOLD_SI:
                if is_micro:
                    clasificacion = "SI"
                    color_box_rgb = (39, 174, 96)
                else:
                    clasificacion = "NO"
                    color_box_rgb = (231, 76, 60)
            else:
                clasificacion = "PROBABLE"
                color_box_rgb = (241, 196, 15)
            
            ultima_confianza = conf
            ultima_clasificacion = clasificacion
            ultima_forma = forma
            ultima_tamano = tamano
            current_frame = frame.copy()
            
            if clasificacion == "SI":
                contador_si += 1
            elif clasificacion == "NO":
                contador_no += 1
            else:
                contador_prob += 1
            imagenes_procesadas += 1
            
            cnn_queue_resultados.put({
                'cnn_prob': conf * 100,
                'clasificacion': clasificacion,
                'forma': forma,
                'tamano': tamano,
                'tiempo_inf': tiempo_inf,
                'contornos': contornos,
                'color_box_rgb': color_box_rgb,
                'frame': rgb
            })
            
        except queue.Empty:
            continue
        except Exception as e:
            print(f"  ❌ Error en hilo_cnn: {e}")

# ================= INTERFAZ PRINCIPAL =================
class DashboardCompleto:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SISTEMA COMPLETO - DETECTOR DE MICROPLÁSTICOS")
        self.root.configure(bg=COLOR_BG)
        self.root.geometry("1600x900+50+30")
        self.root.minsize(1400, 800)
        
        self.running = True
        self.detection_paused = False
        self.prev_time = time.time()
        self.current_frame = None
        self.ultima_confianza = 0.0
        self.ultima_clasificacion = "NO"
        self.ultima_forma = "indefinido"
        self.ultima_tamano = "indefinido"
        self.imagenes_procesadas = 0
        self.frame_count = 0
        
        self.contador_si = 0
        self.contador_no = 0
        self.contador_prob = 0
        
        self.setup_ui()
        self.update_sensores()
        self.update_video()
    
    def setup_ui(self):
        self.root.grid_columnconfigure(0, weight=3)
        self.root.grid_columnconfigure(1, weight=2)
        self.root.grid_rowconfigure(0, weight=1)
        
        left_panel = tk.Frame(self.root, bg=COLOR_BG)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        cam_frame = tk.Frame(left_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
        cam_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        tk.Label(cam_frame, text="VISTA DE CÁMARA (TIEMPO REAL)",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(anchor="nw", padx=10, pady=5)
        
        # Contenedor de video con tamaño fijo
        self.video_frame = tk.Frame(cam_frame, bg="black", relief="solid", borderwidth=1, height=400)
        self.video_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.video_frame.pack_propagate(False)  # <--- EVITA QUE EL CONTENEDOR SE REDIMENSIONE
        
        self.video_label = tk.Label(self.video_frame, bg="black")
        self.video_label.place(x=0, y=0, width=400, height=300)
        
        control_frame = tk.Frame(cam_frame, bg=COLOR_CARD)
        control_frame.pack(fill="x", padx=10, pady=10)
        
        self.detener_btn = tk.Button(control_frame, text="⏸️ DETENER CÁMARA", command=self.toggle_camara,
                                     bg="#34495e", fg="white", font=("Arial", 9, "bold"), relief="flat", padx=10, pady=5)
        self.detener_btn.pack(side="left", padx=5)
        
        self.pausar_btn = tk.Button(control_frame, text="⏸️ PAUSAR DETECCIÓN", command=self.toggle_deteccion,
                                    bg="#34495e", fg="white", font=("Arial", 9, "bold"), relief="flat", padx=10, pady=5)
        self.pausar_btn.pack(side="left", padx=5)
        
        capturar_btn = tk.Button(control_frame, text="📸 CAPTURAR", command=self.capturar_imagen,
                                 bg="#34495e", fg="white", font=("Arial", 9, "bold"), relief="flat", padx=10, pady=5)
        capturar_btn.pack(side="left", padx=5)
        
        self.fps_label = tk.Label(control_frame, text="FPS: 0.0", bg=COLOR_CARD, fg=COLOR_ACCENT,
                                  font=("Consolas", 9, "bold"))
        self.fps_label.pack(side="right", padx=10)
        
        # ========== RESTO DE LA UI (SENSORES, CNN, PANEL DERECHO) ==========
        sensores_frame = tk.Frame(left_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
        sensores_frame.pack(fill="x", pady=(0, 10))
        
        tk.Label(sensores_frame, text="MÉTODOS DE SENSORES (TIEMPO REAL)",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(anchor="nw", padx=10, pady=5)
        
        sensor_grid = tk.Frame(sensores_frame, bg=COLOR_CARD)
        sensor_grid.pack(fill="x", padx=10, pady=10)
        
        self.tds_var = tk.StringVar(value="---")
        self.temp_var = tk.StringVar(value="---")
        self.voltaje_var = tk.StringVar(value="---")
        self.corriente_var = tk.StringVar(value="---")
        self.potencia_var = tk.StringVar(value="---")
        self.cap_var = tk.StringVar(value="---")
        self.entorno_var = tk.StringVar(value="---")
        
        labels = [
            ("💧 TDS:", self.tds_var, "ppm"),
            ("🌡️ Temp:", self.temp_var, "°C"),
            ("⚡ Voltaje:", self.voltaje_var, "V"),
            ("🔌 Corriente:", self.corriente_var, "mA"),
            ("⚙️ Potencia:", self.potencia_var, "mW"),
            ("🧪 Capacitancia:", self.cap_var, "µF"),
            ("🌍 Entorno:", self.entorno_var, "")
        ]
        
        for i, (text, var, unit) in enumerate(labels):
            row = i // 2
            col = i % 2
            frame = tk.Frame(sensor_grid, bg=COLOR_CARD_LIGHT, relief="solid", borderwidth=1)
            frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            tk.Label(frame, text=text, bg=COLOR_CARD_LIGHT, fg=COLOR_TEXT_SEC,
                     font=("Arial", 10)).pack(side="left", padx=10, pady=8)
            tk.Label(frame, textvariable=var, bg=COLOR_CARD_LIGHT, fg=COLOR_ACCENT,
                     font=("Arial", 12, "bold")).pack(side="left", padx=5)
            if unit:
                tk.Label(frame, text=unit, bg=COLOR_CARD_LIGHT, fg=COLOR_TEXT_SEC,
                         font=("Arial", 9)).pack(side="left")
        
        sensor_grid.grid_columnconfigure(0, weight=1)
        sensor_grid.grid_columnconfigure(1, weight=1)
        
        cnn_result_frame = tk.Frame(left_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
        cnn_result_frame.pack(fill="x", pady=(0, 10))
        
        tk.Label(cnn_result_frame, text="RESULTADO CNN",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(anchor="nw", padx=10, pady=5)
        
        cnn_grid = tk.Frame(cnn_result_frame, bg=COLOR_CARD)
        cnn_grid.pack(fill="x", padx=10, pady=10)
        
        self.cnn_confianza_var = tk.StringVar(value="0%")
        self.forma_var = tk.StringVar(value="---")
        self.tamano_var = tk.StringVar(value="---")
        self.color_var = tk.StringVar(value="---")
        self.tiempo_var = tk.StringVar(value="---")
        
        cnn_labels = [
            ("CONFIANZA (CNN):", self.cnn_confianza_var, "%"),
            ("Forma:", self.forma_var, ""),
            ("Tamaño:", self.tamano_var, ""),
            ("Color detectado:", self.color_var, ""),
            ("Tiempo inferencia:", self.tiempo_var, "ms")
        ]
        
        for i, (text, var, unit) in enumerate(cnn_labels):
            frame = tk.Frame(cnn_grid, bg=COLOR_CARD)
            frame.pack(anchor="w", pady=2)
            tk.Label(frame, text=text, bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
                     font=("Arial", 10)).pack(side="left")
            tk.Label(frame, textvariable=var, bg=COLOR_CARD, fg=COLOR_SI,
                     font=("Arial", 10, "bold")).pack(side="left", padx=5)
            if unit:
                tk.Label(frame, text=unit, bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
                         font=("Arial", 9)).pack(side="left")
        
        # PANEL DERECHO
        right_panel = tk.Frame(self.root, bg=COLOR_BG)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        comparacion_frame = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
        comparacion_frame.pack(fill="x", pady=(0, 10))
        
        tk.Label(comparacion_frame, text="COMPARACIÓN DE MÉTODOS",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(anchor="nw", padx=10, pady=5)
        
        comp_grid = tk.Frame(comparacion_frame, bg=COLOR_CARD)
        comp_grid.pack(fill="x", padx=10, pady=10)
        
        self.cnn_prob_var = tk.StringVar(value="0%")
        self.sensor_prob_var = tk.StringVar(value="0%")
        self.diff_var = tk.StringVar(value="0%")
        self.concordancia_var = tk.StringVar(value="0%")
        self.fusion_prob_var = tk.StringVar(value="0%")
        
        tk.Label(comp_grid, text="CNN (Visión Artificial):", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
                 font=("Arial", 10)).grid(row=0, column=0, sticky="w", pady=3)
        tk.Label(comp_grid, textvariable=self.cnn_prob_var, bg=COLOR_CARD, fg=COLOR_CNN,
                 font=("Arial", 12, "bold")).grid(row=0, column=1, sticky="w", padx=10)
        
        tk.Label(comp_grid, text="Sensores (Físico-Químico):", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
                 font=("Arial", 10)).grid(row=1, column=0, sticky="w", pady=3)
        tk.Label(comp_grid, textvariable=self.sensor_prob_var, bg=COLOR_CARD, fg=COLOR_SENSOR,
                 font=("Arial", 12, "bold")).grid(row=1, column=1, sticky="w", padx=10)
        
        tk.Label(comp_grid, text="Diferencia:", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
                 font=("Arial", 10)).grid(row=2, column=0, sticky="w", pady=3)
        tk.Label(comp_grid, textvariable=self.diff_var, bg=COLOR_CARD, fg=COLOR_NO,
                 font=("Arial", 12, "bold")).grid(row=2, column=1, sticky="w", padx=10)
        
        tk.Label(comp_grid, text="CONCORDANCIA ENTRE MÉTODOS:", bg=COLOR_CARD, fg=COLOR_TEXT,
                 font=("Arial", 10, "bold")).grid(row=3, column=0, sticky="w", pady=10)
        tk.Label(comp_grid, textvariable=self.concordancia_var, bg=COLOR_CARD, fg=COLOR_SI,
                 font=("Arial", 14, "bold")).grid(row=3, column=1, sticky="w", padx=10)
        
        tk.Label(comp_grid, text="RESULTADO FINAL (FUSIÓN):", bg=COLOR_CARD, fg=COLOR_TEXT,
                 font=("Arial", 10, "bold")).grid(row=4, column=0, sticky="w", pady=10)
        tk.Label(comp_grid, textvariable=self.fusion_prob_var, bg=COLOR_CARD, fg=COLOR_FUSION,
                 font=("Arial", 16, "bold")).grid(row=4, column=1, sticky="w", padx=10)
        
        graph_frame = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
        graph_frame.pack(fill="x", pady=(0, 10))
        
        tk.Label(graph_frame, text="GRÁFICO DE PROBABILIDADES (TIEMPO REAL)",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(anchor="nw", padx=10, pady=5)
        
        self.fig = Figure(figsize=(6, 3), facecolor=COLOR_CARD, dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(COLOR_CARD_LIGHT)
        self.ax.set_xlabel('Tiempo (s)', fontsize=8)
        self.ax.set_ylabel('Probabilidad (%)', fontsize=8)
        self.ax.tick_params(labelsize=7)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        
        historial_frame = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
        historial_frame.pack(fill="x", pady=(0, 10))
        
        tk.Label(historial_frame, text="HISTORIAL RECIENTE",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(anchor="nw", padx=10, pady=5)
        
        columns = ("Hora", "CNN (%)", "Sensores (%)", "Fusión (%)", "Resultado")
        self.historial_tree = ttk.Treeview(historial_frame, columns=columns, show="headings", height=4)
        for col in columns:
            self.historial_tree.heading(col, text=col)
            self.historial_tree.column(col, width=80, anchor="center")
        self.historial_tree.pack(fill="x", padx=10, pady=10)
        
        resumen_frame = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
        resumen_frame.pack(fill="x", pady=(0, 10))
        
        tk.Label(resumen_frame, text="RESUMEN ESTADÍSTICO (SESIÓN ACTUAL)",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(anchor="nw", padx=10, pady=5)
        
        resumen_grid = tk.Frame(resumen_frame, bg=COLOR_CARD)
        resumen_grid.pack(fill="x", padx=10, pady=10)
        
        self.microplastico_var = tk.StringVar(value="0")
        self.no_microplastico_var = tk.StringVar(value="0")
        self.total_var = tk.StringVar(value="0")
        
        tk.Label(resumen_grid, text="Microplásticos:", bg=COLOR_CARD, fg=COLOR_SI,
                 font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=3)
        tk.Label(resumen_grid, textvariable=self.microplastico_var, bg=COLOR_CARD, fg=COLOR_SI,
                 font=("Arial", 12, "bold")).grid(row=0, column=1, sticky="w", padx=10)
        
        tk.Label(resumen_grid, text="No microplásticos:", bg=COLOR_CARD, fg=COLOR_NO,
                 font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", pady=3)
        tk.Label(resumen_grid, textvariable=self.no_microplastico_var, bg=COLOR_CARD, fg=COLOR_NO,
                 font=("Arial", 12, "bold")).grid(row=1, column=1, sticky="w", padx=10)
        
        tk.Label(resumen_grid, text="Total procesados:", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
                 font=("Arial", 10, "bold")).grid(row=2, column=0, sticky="w", pady=3)
        tk.Label(resumen_grid, textvariable=self.total_var, bg=COLOR_CARD, fg=COLOR_ACCENT,
                 font=("Arial", 12, "bold")).grid(row=2, column=1, sticky="w", padx=10)
        
        volver_btn = tk.Button(right_panel, text="🏠 VOLVER AL MENÚ", command=self.volver_menu,
                              bg="#e67e22", fg="white", font=("Arial", 11, "bold"),
                              relief="flat", padx=20, pady=10, cursor="hand2")
        volver_btn.pack(fill="x", pady=(10, 0))
    
    def toggle_camara(self):
        global running
        self.running = not self.running
        if self.running:
            self.detener_btn.config(text="⏸️ DETENER CÁMARA")
        else:
            self.detener_btn.config(text="▶️ INICIAR CÁMARA")
    
    def toggle_deteccion(self):
        self.detection_paused = not self.detection_paused
        if self.detection_paused:
            self.pausar_btn.config(text="▶️ REANUDAR")
        else:
            self.pausar_btn.config(text="⏸️ PAUSAR DETECCIÓN")
    
    def capturar_imagen(self):
        if self.current_frame is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(CAPTURAS, f"captura_{timestamp}.jpg")
            cv2.imwrite(filename, cv2.cvtColor(self.current_frame, cv2.COLOR_RGB2BGR))
            messagebox.showinfo("Captura", f"Imagen guardada:\n{filename}")
    
    def agregar_historial(self, cnn_prob, sensor_prob, fusion_prob):
        hora = datetime.now().strftime("%H:%M:%S")
        if fusion_prob >= 60:
            resultado = "Microplástico"
        elif fusion_prob >= 40:
            resultado = "Probable"
        else:
            resultado = "No microplástico"
        
        self.historial_tree.insert("", 0, values=(hora, f"{cnn_prob:.0f}%", f"{sensor_prob:.0f}%", 
                                                  f"{fusion_prob:.0f}%", resultado))
        if len(self.historial_tree.get_children()) > 10:
            last = self.historial_tree.get_children()[-1]
            self.historial_tree.delete(last)
    
    def volver_menu(self):
        global running, running_sensors, cnn_running, picam
        self.running = False
        running_sensors = False
        cnn_running = False
        
        try:
            picam.stop()
            time.sleep(0.5)
            picam.close()
        except:
            pass
        
        detener_hilo_sensores()
        
        time.sleep(0.5)
        self.root.destroy()
        subprocess.run(["python3", "interfaz.py"])
        sys.exit()
    
    def update_sensores(self):
        try:
            sd = sensor_queue.get_nowait()
            self.tds_var.set(f"{sd['tds_ppm']:.1f}")
            self.temp_var.set(f"{sd['temp']:.1f}")
            self.voltaje_var.set(f"{sd['voltaje']:.2f}")
            
            corriente_val = sd['corriente']
            if abs(corriente_val) < 0.001:
                corriente_val = 0.0
            self.corriente_var.set(f"{corriente_val:.3f}")
            
            potencia_val = sd['potencia']
            if potencia_val < 0.001:
                potencia_val = 0.0
            self.potencia_var.set(f"{potencia_val:.3f}")
            
            self.cap_var.set(f"{sd['capacitancia_hibrida']:.4f}")
            self.entorno_var.set(sd['entorno'])
            
            sensor_prob = sd.get('sensor_prob', 0)
            self.sensor_prob_var.set(f"{sensor_prob:.0f}%")
            
            if len(sensor_history) > max_puntos:
                sensor_history.pop(0)
            
        except:
            pass
        self.root.after(500, self.update_sensores)
    
    def update_video(self):
        global running, picam, cnn_running
        
        if not self.running:
            self.root.after(100, self.update_video)
            return
        
        try:
            frame = picam.capture_array()
            
            if not self.detection_paused and cnn_running:
                try:
                    cnn_queue.put_nowait((frame, time.time()))
                except queue.Full:
                    pass
            
            rgb_display = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.current_frame = frame.copy()
            
            try:
                resultado = cnn_queue_resultados.get_nowait()
                
                cnn_prob = resultado['cnn_prob']
                clasificacion = resultado['clasificacion']
                forma = resultado['forma']
                tamano = resultado['tamano']
                tiempo_inf = resultado['tiempo_inf']
                contornos = resultado['contornos']
                color_box_rgb = resultado['color_box_rgb']
                rgb = resultado['frame']
                
                self.cnn_confianza_var.set(f"{cnn_prob:.0f}%")
                self.cnn_prob_var.set(f"{cnn_prob:.0f}%")
                self.forma_var.set(forma)
                self.tamano_var.set(tamano)
                self.tiempo_var.set(f"{tiempo_inf:.1f}")
                
                self.contador_si = contador_si
                self.contador_no = contador_no
                self.contador_prob = contador_prob
                self.imagenes_procesadas = imagenes_procesadas
                self.ultima_clasificacion = clasificacion
                
                self.microplastico_var.set(str(self.contador_si))
                self.no_microplastico_var.set(str(self.contador_no))
                self.total_var.set(str(self.imagenes_procesadas))
                
                sensor_prob_str = self.sensor_prob_var.get().replace("%", "")
                sensor_prob = float(sensor_prob_str) if sensor_prob_str else 0
                
                fusion_prob = cnn_prob * peso_cnn + sensor_prob * peso_sensor
                self.fusion_prob_var.set(f"{fusion_prob:.0f}%")
                self.diff_var.set(f"{abs(cnn_prob - sensor_prob):.0f}%")
                
                if abs(cnn_prob - sensor_prob) < 15:
                    concordancia = 95
                elif abs(cnn_prob - sensor_prob) < 30:
                    concordancia = 80
                else:
                    concordancia = 65
                self.concordancia_var.set(f"{concordancia}%")
                
                self.agregar_historial(cnn_prob, sensor_prob, fusion_prob)
                
                cnn_history.append(cnn_prob)
                if len(cnn_history) > max_puntos:
                    cnn_history.pop(0)
                
                fusion_history.append(fusion_prob)
                if len(fusion_history) > max_puntos:
                    fusion_history.pop(0)
                
                if len(sensor_history) < len(cnn_history):
                    sensor_history.extend([0] * (len(cnn_history) - len(sensor_history)))
                if len(sensor_history) > max_puntos:
                    sensor_history.pop(0)
                
                self.frame_count += 1
                if self.frame_count % 5 == 0:
                    self.ax.clear()
                    self.ax.set_facecolor(COLOR_CARD_LIGHT)
                    self.ax.set_xlabel('Tiempo (s)', fontsize=8)
                    self.ax.set_ylabel('Probabilidad (%)', fontsize=8)
                    self.ax.legend(loc='upper left', fontsize=7)
                    self.ax.tick_params(labelsize=7)
                    self.ax.set_ylim([0, 105])
                    
                    t = list(range(len(cnn_history)))
                    min_len = min(len(t), len(cnn_history), len(sensor_history), len(fusion_history))
                    
                    if min_len > 1:
                        self.ax.plot(t[-min_len:], cnn_history[-min_len:], 
                                    color=COLOR_CNN, linewidth=2, label="CNN")
                        self.ax.plot(t[-min_len:], sensor_history[-min_len:], 
                                    color=COLOR_SENSOR, linewidth=2, label="Sensores")
                        self.ax.plot(t[-min_len:], fusion_history[-min_len:], 
                                    color=COLOR_FUSION, linewidth=2, label="Fusión")
                    else:
                        self.ax.text(0.5, 0.5, "Esperando datos...", 
                                    horizontalalignment='center',
                                    verticalalignment='center',
                                    transform=self.ax.transAxes,
                                    fontsize=10, color='gray')
                    
                    self.canvas.draw()
                
                # Dibujar contornos
                color_bgr = (color_box_rgb[2], color_box_rgb[1], color_box_rgb[0])
                if len(contornos) > 0:
                    cv2.drawContours(rgb, contornos, -1, color_bgr, 2)
                cv2.rectangle(rgb, (10,10), (rgb.shape[1]-10, rgb.shape[0]-10), color_bgr, 3)
                cv2.putText(rgb, f"{clasificacion}: {cnn_prob:.1f}%", (30,40),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, color_bgr, 2)
                
                # ========== MOSTRAR IMAGEN CON TAMAÑO CONTROLADO ==========
                # Obtener el tamaño del contenedor
                frame_width = self.video_frame.winfo_width()
                frame_height = self.video_frame.winfo_height()
                
                if frame_width < 10:
                    frame_width = 550
                if frame_height < 10:
                    frame_height = 400
                
                # Calcular relación de aspecto
                img_ratio = rgb.shape[1] / rgb.shape[0]  # 640/480 = 1.333
                frame_ratio = frame_width / frame_height
                
                if frame_ratio > img_ratio:
                    new_width = int(frame_height * img_ratio)
                    new_height = frame_height
                else:
                    new_width = frame_width
                    new_height = int(frame_width / img_ratio)
                
                # Redimensionar
                try:
                    img_pil = Image.fromarray(rgb)
                    img_pil = img_pil.resize((new_width, new_height), Image.Resampling.LANCZOS)
                except:
                    try:
                        img_pil = Image.fromarray(rgb)
                        img_pil = img_pil.resize((new_width, new_height), Image.LANCZOS)
                    except:
                        img_pil = Image.fromarray(rgb)
                        img_pil = img_pil.resize((new_width, new_height))
                
                imgtk = ImageTk.PhotoImage(image=img_pil)
                self.video_label.imgtk = imgtk
                self.video_label.configure(image=imgtk)
                
                # Centrar la imagen en el contenedor con place()
                x_offset = (frame_width - new_width) // 2
                y_offset = (frame_height - new_height) // 2
                self.video_label.place(x=x_offset, y=y_offset, width=new_width, height=new_height)
                
            except queue.Empty:
                # Mostrar frame sin procesar
                frame_width = self.video_frame.winfo_width()
                frame_height = self.video_frame.winfo_height()
                
                if frame_width < 10:
                    frame_width = 550
                if frame_height < 10:
                    frame_height = 400
                
                img_ratio = rgb_display.shape[1] / rgb_display.shape[0]
                frame_ratio = frame_width / frame_height
                
                if frame_ratio > img_ratio:
                    new_width = int(frame_height * img_ratio)
                    new_height = frame_height
                else:
                    new_width = frame_width
                    new_height = int(frame_width / img_ratio)
                
                try:
                    img_pil = Image.fromarray(rgb_display)
                    img_pil = img_pil.resize((new_width, new_height), Image.Resampling.LANCZOS)
                except:
                    try:
                        img_pil = Image.fromarray(rgb_display)
                        img_pil = img_pil.resize((new_width, new_height), Image.LANCZOS)
                    except:
                        img_pil = Image.fromarray(rgb_display)
                        img_pil = img_pil.resize((new_width, new_height))
                
                imgtk = ImageTk.PhotoImage(image=img_pil)
                self.video_label.imgtk = imgtk
                self.video_label.configure(image=imgtk)
                
                x_offset = (frame_width - new_width) // 2
                y_offset = (frame_height - new_height) // 2
                self.video_label.place(x=x_offset, y=y_offset, width=new_width, height=new_height)
            
            # Calcular FPS
            now = time.time()
            fps = 1 / (now - self.prev_time) if (now - self.prev_time) > 0 else 0
            self.fps_label.config(text=f"FPS: {fps:.1f}")
            self.prev_time = now
            
        except Exception as e:
            print(f"Error en update_video: {e}")
        
        if self.running:
            self.root.after(30, self.update_video)
    
    def run(self):
        self.root.mainloop()

# ================= INICIAR HILO DE CNN =================
print("⏳ Iniciando hilo de CNN...")
cnn_thread = threading.Thread(target=hilo_cnn, daemon=True)
cnn_thread.start()
print("✅ Hilo de CNN iniciado correctamente")

# ================= PUNTO DE ENTRADA =================
if __name__ == "__main__":
    app = DashboardCompleto()
    app.run()