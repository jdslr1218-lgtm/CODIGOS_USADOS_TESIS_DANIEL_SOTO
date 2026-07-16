#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MODO CNN - SISTEMA DE DETECCIÓN DE MICROPLÁSTICOS
Interfaz estilo dashboard con cámara en tiempo real
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
from datetime import datetime
from picamera2 import Picamera2
from tflite_runtime.interpreter import Interpreter

# ================= CONFIGURACIÓN =================
BASE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(BASE, "modelo_microplasticos.tflite")
LABELS = os.path.join(BASE, "labels.txt")
CAPTURAS = os.path.join(BASE, "capturas_cnn")

IMG_SIZE = 224
THRESHOLD_SI = 0.4
THRESHOLD_PROB = 0.2

# Colores
COLOR_BG = "#0f0f1a"
COLOR_CARD = "#1a1a2e"
COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_SEC = "#8888aa"
COLOR_SI = "#27ae60"
COLOR_NO = "#e74c3c"
COLOR_PROB = "#f1c40f"
COLOR_ACCENT = "#3498db"

os.makedirs(CAPTURAS, exist_ok=True)

# ================= LABELS =================
labels = {}
try:
    with open(LABELS, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if ':' in line:
                i, n = line.split(":", 1)
                labels[int(i)] = n.strip()
except:
    labels = {0: "no", 1: "si"}

# ================= MODELO TFLITE =================
interpreter = Interpreter(model_path=MODEL)
interpreter.allocate_tensors()
input_idx = interpreter.get_input_details()[0]["index"]
output_idx = interpreter.get_output_details()[0]["index"]

# ================= CÁMARA =================
# Cerrar cualquier instancia previa de cámara
try:
    picam = Picamera2()
    picam.stop()
    picam.close()
    time.sleep(0.5)
except:
    pass

picam = Picamera2()
picam.configure(
    picam.create_video_configuration(
        main={"size": (640, 480), "format": "RGB888"}
    )
)
picam.start()
time.sleep(1)

# ================= FUNCIONES =================
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

def agregar_texto_pil(imagen_rgb, texto, pos, color_rgb, size=16):
    img_pil = Image.fromarray(imagen_rgb)
    draw = ImageDraw.Draw(img_pil)
    try:
        font = ImageFont.truetype("arial.ttf", size)
    except:
        font = ImageFont.load_default()
    if '\n' in texto:
        y = pos[1]
        for linea in texto.split('\n'):
            draw.text((pos[0], y), linea, fill=color_rgb, font=font)
            y += size + 5
    else:
        draw.text(pos, texto, fill=color_rgb, font=font)
    return np.array(img_pil)

# ================= INTERFAZ =================
root = tk.Tk()
root.title("DETECTOR DE MICROPLÁSTICOS - MODO CNN")
root.configure(bg=COLOR_BG)
root.geometry("1300x750+100+50")
root.minsize(1100, 650)

contador_si = 0
contador_no = 0
contador_prob = 0
running = True
detection_paused = False
prev_time = time.time()
current_frame = None
ultima_confianza = 0.0
ultima_clasificacion = "NO"
ultima_forma = "indefinido"
ultima_tamano = "indefinido"
ultimas_detecciones = []
imagenes_procesadas = 0

root.grid_columnconfigure(0, weight=3)
root.grid_columnconfigure(1, weight=2)
root.grid_rowconfigure(0, weight=1)

# ================= PANEL IZQUIERDO =================
left_panel = tk.Frame(root, bg=COLOR_BG)
left_panel.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)

tk.Label(left_panel, text="VISTA DE CÁMARA (TIEMPO REAL)",
         bg=COLOR_BG, fg=COLOR_TEXT, font=("Arial", 14, "bold")).pack(anchor="nw", pady=(0, 10))

video_frame = tk.Frame(left_panel, bg="black", relief="solid", borderwidth=2)
video_frame.pack(expand=True, fill="both")
video_label = tk.Label(video_frame, bg="black")
video_label.pack(expand=True, fill="both")
video_label.config(width=640, height=480)

control_frame = tk.Frame(left_panel, bg=COLOR_BG)
control_frame.pack(fill="x", pady=10)

def crear_boton(frame, texto, comando, color="#34495e"):
    btn = tk.Button(frame, text=texto, command=comando, bg=color, fg="white",
                    font=("Arial", 10, "bold"), relief="flat", padx=20, pady=6, cursor="hand2")
    btn.pack(side="left", padx=5)
    return btn

fps_label = tk.Label(left_panel, text="FPS: 0.0", bg=COLOR_BG, fg=COLOR_TEXT_SEC,
                     font=("Consolas", 10, "bold"))
fps_label.pack(anchor="ne", pady=(5, 0))

detener_btn = crear_boton(control_frame, "⏸️ DETENER CÁMARA", lambda: detener_camara())
pausar_btn = crear_boton(control_frame, "⏸️ PAUSAR DETECCIÓN", lambda: pausar_deteccion())
capturar_btn = crear_boton(control_frame, "📸 CAPTURAR", lambda: capturar_imagen())

# ================= PANEL DERECHO =================
right_panel = tk.Frame(root, bg=COLOR_BG)
right_panel.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)

# Tarjeta de probabilidad
prob_card = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
prob_card.pack(fill="x", pady=(0, 15))

tk.Label(prob_card, text="PROBABILIDAD DE MICROPLÁSTICOS",
         bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(pady=(15, 5))

prob_text = tk.StringVar(value="0.0%")
prob_label = tk.Label(prob_card, textvariable=prob_text, bg=COLOR_CARD, fg=COLOR_SI,
                      font=("Arial", 48, "bold"))
prob_label.pack(pady=(0, 5))

clasif_text = tk.StringVar(value="CLASIFICACIÓN")
clasif_label = tk.Label(prob_card, textvariable=clasif_text, bg=COLOR_CARD, fg=COLOR_PROB,
                        font=("Arial", 16, "bold"))
clasif_label.pack(pady=(0, 15))

# Tarjeta de resumen
summary_card = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
summary_card.pack(fill="x", pady=(0, 15))

tk.Label(summary_card, text="RESUMEN DE DETECCIÓN",
         bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(pady=(10, 10))

summary_frame = tk.Frame(summary_card, bg=COLOR_CARD)
summary_frame.pack(fill="x", padx=20, pady=(0, 10))

si_text = tk.StringVar(value="0")
prob_text_sum = tk.StringVar(value="0")
no_text = tk.StringVar(value="0")

tk.Label(summary_frame, text="✅ Microplásticos detectados:", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 11)).grid(row=0, column=0, sticky="w", pady=5)
tk.Label(summary_frame, textvariable=si_text, bg=COLOR_CARD, fg=COLOR_SI,
         font=("Arial", 14, "bold")).grid(row=0, column=1, sticky="w", padx=10)

tk.Label(summary_frame, text="⚠️ Probables:", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 11)).grid(row=1, column=0, sticky="w", pady=5)
tk.Label(summary_frame, textvariable=prob_text_sum, bg=COLOR_CARD, fg=COLOR_PROB,
         font=("Arial", 14, "bold")).grid(row=1, column=1, sticky="w", padx=10)

tk.Label(summary_frame, text="❌ Descartados:", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 11)).grid(row=2, column=0, sticky="w", pady=5)
tk.Label(summary_frame, textvariable=no_text, bg=COLOR_CARD, fg=COLOR_NO,
         font=("Arial", 14, "bold")).grid(row=2, column=1, sticky="w", padx=10)

# Tarjeta de estadísticas
stats_card = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
stats_card.pack(fill="x", pady=(0, 15))

tk.Label(stats_card, text="ESTADÍSTICAS EN TIEMPO REAL",
         bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(pady=(10, 10))

stats_frame = tk.Frame(stats_card, bg=COLOR_CARD)
stats_frame.pack(fill="x", padx=20, pady=(0, 10))

fps_stat_text = tk.StringVar(value="0.0")
tiempo_text = tk.StringVar(value="0.0 ms")
imagenes_text = tk.StringVar(value="0")

tk.Label(stats_frame, text="FPS:", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 11)).grid(row=0, column=0, sticky="w", pady=5)
tk.Label(stats_frame, textvariable=fps_stat_text, bg=COLOR_CARD, fg=COLOR_ACCENT,
         font=("Arial", 12, "bold")).grid(row=0, column=1, sticky="w", padx=10)

tk.Label(stats_frame, text="Tiempo detección:", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 11)).grid(row=1, column=0, sticky="w", pady=5)
tk.Label(stats_frame, textvariable=tiempo_text, bg=COLOR_CARD, fg=COLOR_ACCENT,
         font=("Arial", 12, "bold")).grid(row=1, column=1, sticky="w", padx=10)

tk.Label(stats_frame, text="Imágenes procesadas:", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 11)).grid(row=2, column=0, sticky="w", pady=5)
tk.Label(stats_frame, textvariable=imagenes_text, bg=COLOR_CARD, fg=COLOR_ACCENT,
         font=("Arial", 12, "bold")).grid(row=2, column=1, sticky="w", padx=10)

tk.Label(stats_frame, text="Modelo IA:", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 11)).grid(row=3, column=0, sticky="w", pady=5)
tk.Label(stats_frame, text="TensorFlow Lite", bg=COLOR_CARD, fg=COLOR_ACCENT,
         font=("Arial", 11, "bold")).grid(row=3, column=1, sticky="w", padx=10)

estado_sistema = tk.StringVar(value="Ejecutando")
tk.Label(stats_frame, text="Estado:", bg=COLOR_CARD, fg=COLOR_TEXT_SEC,
         font=("Arial", 11)).grid(row=4, column=0, sticky="w", pady=5)
tk.Label(stats_frame, textvariable=estado_sistema, bg=COLOR_CARD, fg=COLOR_SI,
         font=("Arial", 11, "bold")).grid(row=4, column=1, sticky="w", padx=10)

# Tarjeta de últimas detecciones
history_card = tk.Frame(right_panel, bg=COLOR_CARD, relief="solid", borderwidth=1)
history_card.pack(fill="both", expand=True)

tk.Label(history_card, text="ÚLTIMAS DETECCIONES",
         bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 12, "bold")).pack(pady=(10, 5))

history_listbox = tk.Listbox(history_card, bg=COLOR_CARD, fg=COLOR_TEXT,
                              font=("Consolas", 10), relief="flat", height=6, bd=0)
history_listbox.pack(fill="both", expand=True, padx=15, pady=(0, 10))

# ===== BOTÓN VOLVER (CORREGIDO) =====
def volver_menu():
    global running, picam
    running = False
    
    # Detener la cámara correctamente
    try:
        picam.stop()
        time.sleep(0.5)
        picam.close()
    except:
        pass
    
    # Pequeña pausa para liberar recursos
    time.sleep(0.5)
    
    # Destruir la ventana
    root.destroy()
    
    # Limpiar GPIO
    try:
        import RPi.GPIO as GPIO
        GPIO.cleanup()
    except:
        pass
    
    # Pausa antes de volver al menú
    time.sleep(0.5)
    
    # Volver al menú principal
    subprocess.run(["python3", "interfaz.py"])
    sys.exit()

volver_btn = tk.Button(right_panel, text="🏠 VOLVER AL MENÚ", command=volver_menu,
                       bg="#e67e22", fg="white", font=("Arial", 11, "bold"),
                       relief="flat", padx=20, pady=10, cursor="hand2")
volver_btn.pack(fill="x", pady=(15, 0))

# ================= FUNCIONES DE CONTROL =================
def detener_camara():
    global running
    running = not running
    if running:
        detener_btn.config(text="⏸️ DETENER CÁMARA")
        estado_sistema.set("Ejecutando")
        update()
    else:
        detener_btn.config(text="▶️ INICIAR CÁMARA")
        estado_sistema.set("Detenida")

def pausar_deteccion():
    global detection_paused
    detection_paused = not detection_paused
    if detection_paused:
        pausar_btn.config(text="▶️ REANUDAR")
        estado_sistema.set("Detección pausada")
    else:
        pausar_btn.config(text="⏸️ PAUSAR DETECCIÓN")
        estado_sistema.set("Ejecutando")

def capturar_imagen():
    global current_frame, ultima_clasificacion, ultima_confianza, ultima_forma, ultima_tamano
    if current_frame is not None:
        frame_rgb = cv2.cvtColor(current_frame.copy(), cv2.COLOR_BGR2RGB)
        texto = (f"MODO CNN\n\n"
                 f"Clasificación: {ultima_clasificacion}\n"
                 f"Confianza: {ultima_confianza*100:.1f}%\n"
                 f"Forma: {ultima_forma}\n"
                 f"Tamaño: {ultima_tamano}\n"
                 f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        frame_con_texto = agregar_texto_pil(frame_rgb, texto, (20,20), (255,255,255), 14)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(CAPTURAS, f"captura_{timestamp}.jpg")
        cv2.imwrite(filename, cv2.cvtColor(frame_con_texto, cv2.COLOR_RGB2BGR))
        messagebox.showinfo("Captura", f"Imagen guardada:\n{filename}")

def actualizar_estadisticas():
    si_text.set(str(contador_si))
    no_text.set(str(contador_no))
    prob_text_sum.set(str(contador_prob))
    imagenes_text.set(str(imagenes_procesadas))

def agregar_historial(clasificacion, confianza):
    hora = datetime.now().strftime("%H:%M:%S")
    texto = f"{hora} - {clasificacion} ({confianza:.1f}%)"
    ultimas_detecciones.insert(0, texto)
    if len(ultimas_detecciones) > 8:
        ultimas_detecciones.pop()
    history_listbox.delete(0, tk.END)
    for item in ultimas_detecciones:
        history_listbox.insert(tk.END, item)

# ================= BUCLE PRINCIPAL =================
def update():
    global contador_si, contador_no, contador_prob, prev_time, current_frame
    global ultima_confianza, ultima_clasificacion, ultima_forma, ultima_tamano
    global running, imagenes_procesadas
    
    if not running:
        root.after(100, update)
        return
    
    try:
        frame = picam.capture_array()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        current_frame = frame.copy()
        imagenes_procesadas += 1
        
        contornos, _ = detectar_objetos(rgb)
        forma, tamano = analizar_objeto(contornos)
        ultima_forma = forma
        ultima_tamano = tamano
        
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
        ultima_confianza = conf
        
        if conf >= THRESHOLD_SI:
            if is_micro:
                clasificacion = "SI"
                color_display = COLOR_SI
                color_box_rgb = (39, 174, 96)
                contador_si += 1
                ultima_clasificacion = "SI"
            else:
                clasificacion = "NO"
                color_display = COLOR_NO
                color_box_rgb = (231, 76, 60)
                contador_no += 1
                ultima_clasificacion = "NO"
        elif conf >= THRESHOLD_PROB:
            clasificacion = "PROBABLE"
            color_display = COLOR_PROB
            color_box_rgb = (241, 196, 15)
            contador_prob += 1
            ultima_clasificacion = "PROBABLE"
        else:
            clasificacion = "PROBABLE"
            color_display = COLOR_PROB
            color_box_rgb = (241, 196, 15)
            contador_prob += 1
            ultima_clasificacion = "PROBABLE"
        
        prob_text.set(f"{conf*100:.1f}%")
        clasif_text.set(clasificacion)
        clasif_label.config(fg=color_display)
        prob_label.config(fg=color_display)
        
        now = time.time()
        fps = 1 / (now - prev_time) if (now - prev_time) > 0 else 0
        fps_stat_text.set(f"{fps:.1f}")
        fps_label.config(text=f"FPS: {fps:.1f}")
        tiempo_text.set(f"{tiempo_inf:.1f} ms")
        prev_time = now
        
        actualizar_estadisticas()
        
        if not detection_paused:
            agregar_historial(clasificacion, conf*100)
        
        color_bgr = (color_box_rgb[2], color_box_rgb[1], color_box_rgb[0])
        if len(contornos) > 0:
            cv2.drawContours(rgb, contornos, -1, color_bgr, 2)
        cv2.rectangle(rgb, (10,10), (rgb.shape[1]-10, rgb.shape[0]-10), color_bgr, 3)
        cv2.putText(rgb, f"{clasificacion}: {conf*100:.1f}%", (30,40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, color_bgr, 2)
        cv2.putText(rgb, f"FPS: {fps:.1f}", (rgb.shape[1]-80, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
        
        # Mostrar en GUI
        img_pil = Image.fromarray(rgb)
        try:
            img_pil.thumbnail((640, 480), Image.Resampling.LANCZOS)
        except AttributeError:
            try:
                img_pil.thumbnail((640, 480), Image.LANCZOS)
            except AttributeError:
                img_pil.thumbnail((640, 480), Image.ANTIALIAS)
        imgtk = ImageTk.PhotoImage(image=img_pil)
        video_label.imgtk = imgtk
        video_label.configure(image=imgtk)
        
    except Exception as e:
        print(f"Error: {e}")
    
    if running:
        root.after(30, update)

update()
root.mainloop()