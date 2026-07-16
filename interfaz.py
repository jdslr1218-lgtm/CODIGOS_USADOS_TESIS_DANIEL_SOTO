#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INTERFAZ PRINCIPAL - SISTEMA DE DETECCIÓN DE MICROPLÁSTICOS
Pantalla de inicio con 3 opciones: CNN, Sensores, Completo
"""

import tkinter as tk
import subprocess
import sys
import os
from datetime import datetime

# ================= CONFIGURACIÓN =================
COLOR_BG = "#2c3e50"
COLOR_BG_LIGHT = "#34495e"
COLOR_TEXT = "#ecf0f1"
COLOR_SI = "#27ae60"
COLOR_NO = "#e74c3c"
COLOR_PROB = "#f1c40f"
COLOR_CARD = "#2c3e50"
COLOR_BORDER = "#3d566e"

# ================= DETECCIÓN DE SENSORES (SIN ABRIR CÁMARA) =================
def verificar_sensores():
    """Verifica el estado real de los sensores sin abrir los dispositivos permanentemente"""
    sensores = {
        'camara': False,
        'mcp3008': False,
        'ina219': False,
        'modelo': False
    }
    
    # Verificar modelo TFLite
    try:
        BASE = os.path.dirname(os.path.abspath(__file__))
        MODEL = os.path.join(BASE, "modelo_microplasticos.tflite")
        if os.path.exists(MODEL):
            sensores['modelo'] = True
    except:
        pass
    
    # Verificar SPI (MCP3008) - abrir y cerrar inmediatamente
    try:
        import spidev
        spi = spidev.SpiDev()
        spi.open(0, 1)
        spi.close()
        sensores['mcp3008'] = True
    except:
        pass
    
    # Verificar INA219 (I2C) - leer un byte y cerrar
    try:
        import smbus2
        bus = smbus2.SMBus(1)
        # Intentar leer un byte del INA219 (dirección 0x40)
        bus.read_byte(0x40)
        bus.close()
        sensores['ina219'] = True
    except:
        pass
    
    # Verificar cámara - SIN ABRIRLA REALMENTE, solo verificar si el dispositivo existe
    # Para no bloquear la cámara, verificamos si el archivo de dispositivo existe
    # o si hay algún proceso usando la cámara
    try:
        # Verificar si el dispositivo de cámara existe
        if os.path.exists('/dev/video0') or os.path.exists('/dev/video1'):
            sensores['camara'] = True
    except:
        pass
    
    return sensores

# ================= VERIFICAR SENSORES =================
print("Verificando estado de los sensores...")
estado_sensores = verificar_sensores()

# ================= CLASE PRINCIPAL =================
class MenuPrincipal:
    def __init__(self):
        self.ventana = tk.Tk()
        self.ventana.title("Sistema de Detección de Microplásticos")
        self.ventana.configure(bg=COLOR_BG)
        self.ventana.geometry("1000x700+200+100")
        self.ventana.minsize(900, 600)
        
        # Configurar grid para centrar contenido
        self.ventana.grid_rowconfigure(0, weight=1)
        self.ventana.grid_rowconfigure(1, weight=0)
        self.ventana.grid_rowconfigure(2, weight=1)
        self.ventana.grid_columnconfigure(0, weight=1)
        
        # Frame principal
        main_container = tk.Frame(self.ventana, bg=COLOR_BG)
        main_container.grid(row=1, column=0, sticky="nsew")
        main_container.grid_columnconfigure(0, weight=1)
        main_container.grid_rowconfigure(0, weight=1)
        
        # Contenedor interno
        content_frame = tk.Frame(main_container, bg=COLOR_BG)
        content_frame.grid(row=0, column=0, padx=40, pady=20, sticky="nsew")
        content_frame.grid_columnconfigure(0, weight=1)
        
        # Título
        titulo = tk.Label(content_frame, text="SISTEMA DE DETECCIÓN DE MICROPLÁSTICOS",
                          bg=COLOR_BG, fg=COLOR_TEXT, font=("Arial", 20, "bold"))
        titulo.pack(pady=(20, 10))
        
        subtitulo = tk.Label(content_frame, text="Sistema inteligente basado en visión artificial y análisis de sensores",
                             bg=COLOR_BG, fg="#bdc3c7", font=("Arial", 11))
        subtitulo.pack(pady=(0, 40))
        
        # Frame para las tarjetas (3 columnas del mismo tamaño)
        cards_frame = tk.Frame(content_frame, bg=COLOR_BG)
        cards_frame.pack(fill="both", expand=True, pady=20)
        
        # Configurar 3 columnas con el mismo peso
        for i in range(3):
            cards_frame.grid_columnconfigure(i, weight=1, uniform="card")
        cards_frame.grid_rowconfigure(0, weight=1)
        
        # ===== TARJETA 1: MODO CNN =====
        cnn_card = tk.Frame(cards_frame, bg=COLOR_CARD, relief="solid", borderwidth=2)
        cnn_card.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        
        tk.Label(cnn_card, text="1. MODO CNN", bg=COLOR_CARD, fg=COLOR_SI,
                 font=("Arial", 16, "bold")).pack(pady=(25, 10))
        tk.Label(cnn_card, text="(SOLO VISIÓN ARTIFICIAL)", bg=COLOR_CARD, fg=COLOR_TEXT,
                 font=("Arial", 9, "italic")).pack()
        tk.Label(cnn_card, text="Detección de microplásticos\nsolo con cámara y modelo IA.",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 11), justify="center").pack(pady=(25, 30))
        
        btn_cnn = tk.Button(cnn_card, text="INICIAR", command=self.abrir_cnn,
                            bg=COLOR_SI, fg="white", font=("Arial", 12, "bold"),
                            relief="flat", padx=30, pady=10, cursor="hand2", bd=0)
        btn_cnn.pack(pady=(0, 25))
        
        # ===== TARJETA 2: MODO SENSORES =====
        sensores_card = tk.Frame(cards_frame, bg=COLOR_CARD, relief="solid", borderwidth=2)
        sensores_card.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        
        tk.Label(sensores_card, text="2. MODO SENSORES", bg=COLOR_CARD, fg=COLOR_PROB,
                 font=("Arial", 16, "bold")).pack(pady=(25, 10))
        tk.Label(sensores_card, text="(ANÁLISIS FÍSICO-QUÍMICO)", bg=COLOR_CARD, fg=COLOR_TEXT,
                 font=("Arial", 9, "italic")).pack()
        tk.Label(sensores_card, text="Monitoreo de parámetros del agua\n(TDS, temperatura, capacitancia).",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 11), justify="center").pack(pady=(25, 30))
        
        btn_sensores = tk.Button(sensores_card, text="INICIAR", command=self.abrir_sensores,
                                 bg=COLOR_PROB, fg="white", font=("Arial", 12, "bold"),
                                 relief="flat", padx=30, pady=10, cursor="hand2", bd=0)
        btn_sensores.pack(pady=(0, 25))
        
        # ===== TARJETA 3: SISTEMA COMPLETO =====
        completo_card = tk.Frame(cards_frame, bg=COLOR_CARD, relief="solid", borderwidth=2)
        completo_card.grid(row=0, column=2, padx=15, pady=15, sticky="nsew")
        
        tk.Label(completo_card, text="3. SISTEMA COMPLETO", bg=COLOR_CARD, fg="#3498db",
                 font=("Arial", 16, "bold")).pack(pady=(25, 10))
        tk.Label(completo_card, text="(CNN + SENSORES)", bg=COLOR_CARD, fg=COLOR_TEXT,
                 font=("Arial", 9, "italic")).pack()
        tk.Label(completo_card, text="Sistema integrado completo\ncon cámara y todos los sensores.",
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=("Arial", 11), justify="center").pack(pady=(25, 30))
        
        btn_completo = tk.Button(completo_card, text="INICIAR", command=self.abrir_completo,
                                 bg="#3498db", fg="white", font=("Arial", 12, "bold"),
                                 relief="flat", padx=30, pady=10, cursor="hand2", bd=0)
        btn_completo.pack(pady=(0, 25))
        
        # ========== PANEL DE ESTADO DEL SISTEMA ==========
        estado_frame = tk.Frame(content_frame, bg=COLOR_BG_LIGHT, relief="sunken", borderwidth=1)
        estado_frame.pack(fill="x", pady=30)
        
        tk.Label(estado_frame, text="ESTADO DEL SISTEMA", bg=COLOR_BG_LIGHT, fg=COLOR_TEXT,
                 font=("Arial", 12, "bold")).pack(anchor="w", padx=20, pady=(12, 10))
        
        # Frame para los 4 indicadores en fila
        indicadores_frame = tk.Frame(estado_frame, bg=COLOR_BG_LIGHT)
        indicadores_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        # Definir estado real de cada componente
        camara_estado = "Conectada" if estado_sensores.get('camara', False) else "Desconectada"
        sensores_estado = "Conectados" if (estado_sensores.get('mcp3008', False) or estado_sensores.get('ina219', False)) else "Desconectados"
        modelo_estado = "Cargado" if estado_sensores.get('modelo', False) else "No encontrado"
        almacenamiento_estado = "OK"
        
        indicadores = [
            ("📷 Cámara", camara_estado, COLOR_SI if estado_sensores.get('camara', False) else COLOR_NO),
            ("🔌 Sensores", sensores_estado, COLOR_SI if (estado_sensores.get('mcp3008', False) or estado_sensores.get('ina219', False)) else COLOR_NO),
            ("🧠 Modelo IA", modelo_estado, COLOR_SI if estado_sensores.get('modelo', False) else COLOR_NO),
            ("💾 Almacenamiento", almacenamiento_estado, COLOR_SI)
        ]
        
        for nombre, estado, color in indicadores:
            card = tk.Frame(indicadores_frame, bg="#2c3e50", relief="solid", borderwidth=1)
            card.pack(side="left", expand=True, fill="both", padx=6, pady=6)
            
            tk.Label(card, text=nombre, bg="#2c3e50", fg=COLOR_TEXT,
                     font=("Arial", 10, "bold")).pack(pady=(10, 5))
            tk.Label(card, text=estado, bg="#2c3e50", fg=color,
                     font=("Arial", 11, "bold")).pack(pady=(0, 10))
        
        # Versión
        version_frame = tk.Frame(content_frame, bg=COLOR_BG)
        version_frame.pack(fill="x", pady=(10, 20))
        
        tk.Label(version_frame, text="Versión 2.0.0", bg=COLOR_BG, fg="#7f8c8d",
                 font=("Arial", 8)).pack(side="left")
        tk.Label(version_frame, text=datetime.now().strftime("%d/%m/%Y %H:%M:%S"), bg=COLOR_BG, fg="#7f8c8d",
                 font=("Arial", 8)).pack(side="right")
    
    def abrir_cnn(self):
        """Abre modo CNN (solo visión artificial)"""
        self.ventana.destroy()
        subprocess.run(["python3", "modo_cnn.py"])
        sys.exit()
    
    def abrir_sensores(self):
        """Abre modo sensores (solo sensores)"""
        self.ventana.destroy()
        subprocess.run(["python3", "modo_sensores.py"])
        sys.exit()
    
    def abrir_completo(self):
        """Abre sistema completo (CNN + sensores)"""
        self.ventana.destroy()
        subprocess.run(["python3", "sistema_completo.py"])
        sys.exit()
    
    def iniciar(self):
        self.ventana.mainloop()

# ================= PUNTO DE ENTRADA =================
if __name__ == "__main__":
    app = MenuPrincipal()
    app.iniciar()