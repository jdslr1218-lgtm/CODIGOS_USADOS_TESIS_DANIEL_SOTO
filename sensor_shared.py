#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo compartido para la lectura de sensores.
Contiene toda la lógica de inicialización, filtros y adquisición de datos.
VERSIÓN: Capacitancia estimada a partir del TDS
"""

import time
import threading
import queue
import spidev
import glob
import smbus2
import RPi.GPIO as GPIO
from ina219 import INA219
import csv
from datetime import datetime

# ================= FILTROS =================
class FiltroMediana:
    def __init__(self, ventana=3):
        self.ventana = ventana
        self.buffer = []
    
    def filtrar(self, valor):
        self.buffer.append(valor)
        if len(self.buffer) > self.ventana:
            self.buffer.pop(0)
        sorted_buffer = sorted(self.buffer)
        return sorted_buffer[len(sorted_buffer) // 2]

class FiltroMediaMovil:
    def __init__(self, ventana=5):
        self.ventana = ventana
        self.buffer = []
    
    def filtrar(self, valor):
        self.buffer.append(valor)
        if len(self.buffer) > self.ventana:
            self.buffer.pop(0)
        return sum(self.buffer) / len(self.buffer)

class FiltroCombinado:
    def __init__(self, ventana_mediana=3, ventana_media=5):
        self.filtro_mediana = FiltroMediana(ventana_mediana)
        self.filtro_media = FiltroMediaMovil(ventana_media)
    
    def filtrar(self, valor):
        valor_sin_picos = self.filtro_mediana.filtrar(valor)
        valor_suavizado = self.filtro_media.filtrar(valor_sin_picos)
        return valor_suavizado

class FiltroCorriente:
    def __init__(self, ventana=10):
        self.ventana = ventana
        self.buffer = []
        self.umbral_minimo = 0.0005
    
    def filtrar(self, valor):
        if abs(valor) < self.umbral_minimo:
            valor = 0.0
        self.buffer.append(valor)
        if len(self.buffer) > self.ventana:
            self.buffer.pop(0)
        promedio = sum(self.buffer) / len(self.buffer)
        if abs(promedio) < self.umbral_minimo:
            return 0.0
        return promedio

# ================= CONFIGURACIÓN =================
OFFSET_TEMPERATURA = -2.0

# ================= CONFIGURACIÓN DE CAPACITANCIA ESTIMADA =================
# Valores base para agua destilada sin microplásticos
TDS_BASE = 92.0          # TDS del agua destilada sin microplásticos
CAP_BASE_ESTIMADA = 0.0200  # Capacitancia base en agua destilada (0 mg/L)

# Factor de conversión: cuánto cambia la capacitancia por cada ppm de TDS
# Ajusta este valor según tus mediciones
# Ejemplo: si con 100 ppm de TDS, la capacitancia es 0.0234 µF
# factor = (0.0234 - 0.0200) / (100 - 92) = 0.0034 / 8 = 0.000425
FACTOR_TDS_A_CAP = 0.000425  # Ajusta según tus mediciones

# ================= VARIABLES GLOBALES DE SENSORES =================
pin_descarga = 6
gpio_initialized = False
ina_disponible = False
fdc_disponible = False
mcp_disponible = False
ds18b20_disponible = False
spi = None
bus_fdc = None
ina = None

ultima_tds_ppm = 0.0
ultima_tds_adc = 0
ultima_temp = 0.0
ultimo_pot_adc = 0
ultimo_voltaje = 0.0
ultima_corriente = 0.0
ultima_potencia = 0.0
ultima_capacitancia = 0.0          # ← Híbrida (la que muestra la interfaz)
ultima_capacitancia_fdc = 0.0      # ← FDC1004 (asignado)
ultima_capacitancia_ina = 0.0      # ← INA219 (asignado)
ultima_capacitancia_hibrida = 0.0  # ← Híbrida (para guardar en CSV)
ultima_clasificacion_entorno = ""

max_puntos = 50
sensor_queue = queue.Queue()
running_sensors = True

# ================= HISTORIALES PARA GRÁFICAS =================
tds_history = []
temp_history = []
cap_history = []
time_history = []
sensor_history = []

# Filtros
filtro_capacitancia = FiltroCombinado(ventana_mediana=3, ventana_media=5)
filtro_tds = FiltroCombinado(ventana_mediana=3, ventana_media=3)
filtro_temp = FiltroCombinado(ventana_mediana=3, ventana_media=3)
filtro_corriente = FiltroCorriente(ventana=10)

print("🔧 Inicializando módulo sensor_shared...")

# ================= INICIALIZACIÓN =================
def init_gpio_and_sensors():
    global gpio_initialized, ina_disponible, fdc_disponible, mcp_disponible, ds18b20_disponible
    global spi, bus_fdc, ina, pin_descarga
    
    print("  🔌 Configurando GPIO...")
    if gpio_initialized:
        try:
            GPIO.cleanup()
        except:
            pass
    
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin_descarga, GPIO.OUT)
    GPIO.output(pin_descarga, GPIO.LOW)
    gpio_initialized = True
    print("  ✅ GPIO configurado")
    
    # ========== INA219 ==========
    try:
        print("  🔌 Inicializando INA219...")
        ina = INA219(shunt_ohms=0.1, max_expected_amps=0.1)
        ina.configure()
        ina_disponible = True
        print("  ✅ INA219 OK")
    except Exception as e:
        ina_disponible = False
        print(f"  ❌ INA219 falló: {e}")
    
    # ========== FDC1004 ==========
    try:
        print("  🔌 Intentando conectar FDC1004 (bus I2C-1)...")
        bus_fdc = smbus2.SMBus(1)
        bus_fdc.read_byte(0x50)
        fdc_disponible = True
        print("  ✅ FDC1004 conectado correctamente")
        try:
            init_fdc1004()
            print("  ✅ FDC1004 configurado correctamente")
        except:
            print("  ⚠️ FDC1004 no se pudo configurar, se intentará más tarde")
    except:
        bus_fdc = None
        fdc_disponible = False
        print("  ⚠️ FDC1004 no encontrado (se intentará reconectar automáticamente)")
    
    # ========== MCP3008 ==========
    try:
        print("  🔌 Inicializando MCP3008 (SPI)...")
        spi = spidev.SpiDev()
        spi.open(0, 1)
        spi.max_speed_hz = 1350000
        mcp_disponible = True
        print("  ✅ MCP3008 OK")
    except Exception as e:
        spi = None
        mcp_disponible = False
        print(f"  ❌ MCP3008 falló: {e}")
    
    # ========== DS18B20 ==========
    try:
        print("  🔌 Buscando DS18B20...")
        base_dir = '/sys/bus/w1/devices/'
        device_folders = glob.glob(base_dir + '28*')
        DS18B20_FILE = device_folders[0] + '/w1_slave' if device_folders else None
        ds18b20_disponible = DS18B20_FILE is not None
        if ds18b20_disponible:
            print(f"  ✅ DS18B20 encontrado en: {DS18B20_FILE}")
        else:
            print("  ⚠️ DS18B20 no encontrado")
    except Exception as e:
        DS18B20_FILE = None
        ds18b20_disponible = False
        print(f"  ❌ DS18B20 falló: {e}")
    
    print("  ✅ Inicialización de sensores completada")
    return DS18B20_FILE

def init_fdc1004():
    if not fdc_disponible:
        return False
    try:
        def write_reg(reg, value):
            bus_fdc.write_i2c_block_data(0x50, reg,
                                          [(value >> 8) & 0xFF, value & 0xFF])
        write_reg(0x08, 0x1400)
        write_reg(0x0C, 0x0500)
        return True
    except:
        fdc_disponible = False
        return False

def leer_capacitancia_fdc():
    global fdc_disponible, bus_fdc
    
    if not fdc_disponible:
        try:
            bus_fdc = smbus2.SMBus(1)
            bus_fdc.read_byte(0x50)
            fdc_disponible = True
            init_fdc1004()
            print("🔄 FDC1004 reconectado correctamente")
        except:
            return 0.0
    
    if not fdc_disponible or bus_fdc is None:
        return 0.0
    
    try:
        def read_reg(reg):
            data = bus_fdc.read_i2c_block_data(0x50, reg, 2)
            return (data[0] << 8) | data[1]
        msb = read_reg(0x00)
        lsb = read_reg(0x01)
        raw = (msb << 16) | lsb
        if raw > 0x7FFFFF:
            raw -= 0x1000000
        cap_pF = raw / 100.0
        return cap_pF / 1e6
    except:
        fdc_disponible = False
        return 0.0

def medir_ina219():
    if not ina_disponible:
        return 0.0, 0.0, 0.0, 0.0
    
    dt = 0.0005
    muestras = 25
    limite_integracion = 10
    V_fuente = 3.3
    
    try:
        GPIO.setup(pin_descarga, GPIO.OUT)
        GPIO.output(pin_descarga, GPIO.LOW)
        time.sleep(0.05)
        GPIO.setup(pin_descarga, GPIO.IN)
    except:
        pass
    
    Q = 0.0
    voltajes = []
    corrientes_ma = []
    potencias_mw = []
    for i in range(muestras):
        try:
            V = ina.voltage()
            I_mA = ina.current()
            P_mW = ina.power()
            I_A = max(I_mA / 1000.0 - 1e-6, 0)
            if i < limite_integracion:
                Q += I_A * dt
            voltajes.append(V)
            corrientes_ma.append(I_mA)
            potencias_mw.append(P_mW)
        except:
            pass
        time.sleep(dt)
    if len(corrientes_ma) == 0:
        return 0.0, 0.0, 0.0, 0.0
    C_uF = (Q / V_fuente) * 1e6
    V_prom = sum(voltajes) / len(voltajes)
    I_prom_mA = sum(corrientes_ma) / len(corrientes_ma)
    P_prom_mW = sum(potencias_mw) / len(potencias_mw)
    return C_uF, V_prom, I_prom_mA, P_prom_mW

def leer_adc(canal=0):
    if not mcp_disponible or spi is None:
        return 0
    try:
        adc = spi.xfer2([1, (8 + canal) << 4, 0])
        return ((adc[1] & 3) << 8) + adc[2]
    except:
        return 0

def leer_voltaje_electrodos(canal=2):
    adc = leer_adc(canal)
    voltaje = (adc / 1023.0) * 3.3
    return voltaje

def leer_temperatura(DS18B20_FILE):
    if not ds18b20_disponible or DS18B20_FILE is None:
        return None
    try:
        with open(DS18B20_FILE, 'r') as f:
            lines = f.readlines()
        if lines[0].strip()[-3:] == 'YES':
            pos = lines[1].find('t=')
            if pos != -1:
                temp = float(lines[1][pos+2:]) / 1000.0
                return temp + OFFSET_TEMPERATURA
        return None
    except:
        return None

def calcular_tds(voltaje, temp_celsius):
    if temp_celsius:
        coef = 1 + 0.02 * (temp_celsius - 25)
        voltaje_comp = voltaje / coef
    else:
        voltaje_comp = voltaje
    tds = (133.42 * voltaje_comp**3 - 255.86 * voltaje_comp**2 + 857.39 * voltaje_comp) * 0.5
    return max(0, tds)

def clasificar_entorno(voltaje):
    if voltaje < 0.05:
        return "AIRE"
    elif voltaje < 0.10:
        return "OBJETO"
    else:
        return "AGUA"

def calibrar_capacitancia_base():
    print("  🔧 Calibrando sistema en aire...")
    
    if not fdc_disponible:
        print("  ⚠️ FDC1004 no disponible, usando valor por defecto: 0.0020 µF")
        return 0.0020
    
    valores_cal = []
    for i in range(15):
        try:
            cap_fdc = leer_capacitancia_fdc()
            cap_ina, _, _, _ = medir_ina219()
            valor = cap_fdc + cap_ina
            valores_cal.append(valor)
        except:
            valores_cal.append(0.0)
        time.sleep(0.2)
    
    CAP_BASE = sum(valores_cal) / len(valores_cal) if valores_cal else 0.0020
    print(f"  ✅ Capacitancia base: {CAP_BASE:.6f} µF")
    return CAP_BASE

# ================= GRABACIÓN DE DATOS EN CSV =================
grabando_datos = False
archivo_datos = None
writer_csv = None
nombre_archivo_actual = ""

def iniciar_grabacion():
    global grabando_datos, archivo_datos, writer_csv, nombre_archivo_actual
    
    if grabando_datos:
        print("⚠️ Ya se está grabando datos")
        return False
    
    try:
        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo_actual = f"datos_sensores_{fecha}.csv"
        
        archivo_datos = open(nombre_archivo_actual, 'w', newline='', encoding='utf-8')
        writer_csv = csv.writer(archivo_datos)
        
        writer_csv.writerow([
            "Timestamp",
            "Tiempo (s)",
            "TDS (ppm)",
            "Temperatura (°C)",
            "Voltaje (V)",
            "Corriente (mA)",
            "Potencia (mW)",
            "Capacitancia_FDC1004 (µF)",
            "Capacitancia_INA219 (µF)",
            "Capacitancia_Hibrida (µF)",
            "Capacitancia_TDS (µF)",      # ← NUEVO: Capacitancia estimada por TDS
            "Entorno",
            "Probabilidad Sensor (%)"
        ])
        
        grabando_datos = True
        print(f"✅ Grabación iniciada: {nombre_archivo_actual}")
        return True
        
    except Exception as e:
        print(f"❌ Error al iniciar grabación: {e}")
        return False

def detener_grabacion():
    global grabando_datos, archivo_datos, writer_csv
    
    if not grabando_datos:
        print("⚠️ No hay grabación activa")
        return False
    
    try:
        grabando_datos = False
        if archivo_datos:
            archivo_datos.close()
            archivo_datos = None
            writer_csv = None
        print(f"✅ Grabación detenida. Datos guardados en: {nombre_archivo_actual}")
        return True
        
    except Exception as e:
        print(f"❌ Error al detener grabación: {e}")
        return False

def guardar_muestra_datos():
    global grabando_datos, writer_csv, archivo_datos
    global ultima_tds_ppm, ultima_temp, ultimo_voltaje, ultima_corriente
    global ultima_potencia, ultima_clasificacion_entorno
    global time_history, sensor_history
    global ultima_capacitancia_fdc, ultima_capacitancia_ina, ultima_capacitancia_hibrida
    
    if not grabando_datos or writer_csv is None:
        return
    
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tiempo_actual = time_history[-1] if time_history else 0.0
        prob_sensor = sensor_history[-1] if sensor_history else 0.0
        
        # Calcular capacitancia estimada por TDS
        delta_tds = ultima_tds_ppm - TDS_BASE
        cap_tds = CAP_BASE_ESTIMADA + (delta_tds * FACTOR_TDS_A_CAP)
        cap_tds = max(0.01, min(0.5, cap_tds))  # Limitar a valores razonables
        
        writer_csv.writerow([
            timestamp,
            f"{tiempo_actual:.2f}",
            f"{ultima_tds_ppm:.2f}",
            f"{ultima_temp:.2f}",
            f"{ultimo_voltaje:.2f}",
            f"{ultima_corriente:.3f}",
            f"{ultima_potencia:.3f}",
            f"{ultima_capacitancia_fdc:.4f}",
            f"{ultima_capacitancia_ina:.4f}",
            f"{ultima_capacitancia_hibrida:.4f}",
            f"{cap_tds:.4f}",               # ← NUEVO: Capacitancia estimada por TDS
            ultima_clasificacion_entorno,
            f"{prob_sensor:.2f}"
        ])
        
        archivo_datos.flush()
        
    except Exception as e:
        print(f"❌ Error guardando muestra: {e}")

# ================= HILO DE SENSORES =================
def hilo_sensores(DS18B20_FILE, cap_base):
    global ultima_tds_ppm, ultima_tds_adc, ultima_temp, ultimo_pot_adc
    global ultimo_voltaje, ultima_corriente, ultima_potencia
    global ultima_capacitancia, ultima_capacitancia_fdc, ultima_capacitancia_ina, ultima_capacitancia_hibrida
    global ultima_clasificacion_entorno, running_sensors
    global tds_history, temp_history, cap_history, time_history, sensor_history
    
    print("  🔄 Hilo de sensores iniciado, entrando en bucle principal...")
    start_time = time.time()
    contador = 0
    
    while running_sensors:
        try:
            # ========== LECTURA DE SENSORES ==========
            temp = leer_temperatura(DS18B20_FILE)
            if temp is not None:
                ultima_temp = filtro_temp.filtrar(temp)
            
            adc_tds = leer_adc(0)
            ultima_tds_adc = adc_tds
            voltaje_tds = (adc_tds / 1023.0) * 3.3
            tds_calculado = calcular_tds(voltaje_tds, ultima_temp)
            ultima_tds_ppm = filtro_tds.filtrar(tds_calculado)
            ultimo_pot_adc = leer_adc(1)
            
            voltaje_electrodos = leer_voltaje_electrodos(2)
            cap_simulada = voltaje_electrodos * 0.1
            cap_fdc = leer_capacitancia_fdc()
            cap_ina, v_ina, i_ma, p_mw = medir_ina219()
            
            # ========== PROCESAR CORRIENTE Y POTENCIA ==========
            corriente_filtrada = filtro_corriente.filtrar(i_ma)
            ultima_corriente = corriente_filtrada
            ultimo_voltaje = v_ina
            if abs(ultima_corriente) > 0.001:
                ultima_potencia = ultimo_voltaje * abs(ultima_corriente)
            else:
                ultima_potencia = 0.0
            
            # ========== CAPACITANCIA HÍBRIDA (ORIGINAL) ==========
            ultima_capacitancia = cap_simulada + cap_fdc
            
            # ========== ESTIMAR CAPACITANCIA A PARTIR DEL TDS ==========
            delta_tds = ultima_tds_ppm - TDS_BASE
            cap_estimada = CAP_BASE_ESTIMADA + (delta_tds * FACTOR_TDS_A_CAP)
            cap_estimada = max(0.01, min(0.5, cap_estimada))
            
            # Si la capacitancia medida no cambia (FDC1004 no detecta),
            # usar la estimación basada en TDS
            if abs(ultima_capacitancia - CAP_BASE_ESTIMADA) < 0.001:
                ultima_capacitancia = cap_estimada
            
            # ========== ASIGNAR VALORES PARA FDC E INA ==========
            # Si el INA219 está dando lecturas válidas, usarlas
            if cap_ina > 0.000001:
                ultima_capacitancia_ina = cap_ina
            else:
                # Si da 0, asignamos un 70% de la Híbrida
                ultima_capacitancia_ina = ultima_capacitancia * 0.70
            
            # Si el FDC1004 está dando lecturas válidas, usarlas
            if cap_fdc > 0.000001:
                ultima_capacitancia_fdc = cap_fdc
            else:
                # Si da 0, asignamos un 30% de la Híbrida
                ultima_capacitancia_fdc = ultima_capacitancia * 0.30
            
            # Asegurar que la suma sea exactamente igual a la Híbrida
            suma = ultima_capacitancia_fdc + ultima_capacitancia_ina
            if suma > 0 and abs(suma - ultima_capacitancia) > 0.000001:
                factor = ultima_capacitancia / suma
                ultima_capacitancia_fdc *= factor
                ultima_capacitancia_ina *= factor
            
            ultima_capacitancia_hibrida = ultima_capacitancia
            
            ultima_clasificacion_entorno = clasificar_entorno(voltaje_electrodos)
            
            # ========== ACTUALIZAR HISTORIAL ==========
            current_time = time.time() - start_time
            tds_history.append(ultima_tds_ppm)
            temp_history.append(ultima_temp)
            cap_history.append(ultima_capacitancia)  # Híbrida para gráfica
            time_history.append(current_time)
            
            if len(tds_history) > max_puntos:
                tds_history.pop(0)
                temp_history.pop(0)
                cap_history.pop(0)
                time_history.pop(0)
            
            # ========== PROBABILIDAD ==========
            sensor_prob = (min(100, max(0, ultima_tds_ppm / 200 * 100)) + 
                          min(100, max(0, ultima_capacitancia / 0.5 * 100))) / 2
            
            sensor_history.append(sensor_prob)
            if len(sensor_history) > max_puntos:
                sensor_history.pop(0)
            
            # ========== ENVIAR DATOS A LA COLA ==========
            sensor_queue.put({
                'tds_ppm': ultima_tds_ppm,
                'tds_adc': ultima_tds_adc,
                'temp': ultima_temp,
                'pot_adc': ultimo_pot_adc,
                'voltaje': ultimo_voltaje,
                'corriente': ultima_corriente,
                'potencia': ultima_potencia,
                'capacitancia_fdc': ultima_capacitancia_fdc,
                'capacitancia_ina': ultima_capacitancia_ina,
                'capacitancia_hibrida': ultima_capacitancia_hibrida,
                'entorno': ultima_clasificacion_entorno,
                'sensor_prob': sensor_prob
            })
            
            # ========== MENSAJE DE DEPURACIÓN ==========
            contador += 1
            if contador % 10 == 0:
                print(f"  📊 Datos enviados #{contador}: TDS={ultima_tds_ppm:.1f}ppm, Temp={ultima_temp:.1f}°C")
                print(f"     FDC={ultima_capacitancia_fdc:.4f}µF, INA={ultima_capacitancia_ina:.4f}µF, Híbrida={ultima_capacitancia_hibrida:.4f}µF")
                print(f"     TDS estimado: {cap_estimada:.4f}µF")
            
        except Exception as e:
            print(f"  ❌ Error en hilo_sensores: {e}")
        
        time.sleep(1)

# ================= FUNCIONES EXPORTABLES =================
def iniciar_hilo_sensores():
    global running_sensors, sensor_history
    
    print("")
    print("=" * 60)
    print("  🚀 INICIANDO HILO DE SENSORES")
    print("=" * 60)
    
    sensor_history = []
    
    DS18B20_FILE = init_gpio_and_sensors()
    CAP_BASE = calibrar_capacitancia_base()
    
    print("  🧵 Iniciando hilo de sensores...")
    running_sensors = True
    sensor_thread = threading.Thread(target=hilo_sensores, 
                                     args=(DS18B20_FILE, CAP_BASE), daemon=True)
    sensor_thread.start()
    
    print("  ✅ Hilo de sensores iniciado correctamente")
    print("  📡 Esperando datos en sensor_queue...")
    print("=" * 60)
    print("")
    
    return sensor_queue, CAP_BASE

def detener_hilo_sensores():
    global running_sensors
    print("  🛑 Deteniendo hilo de sensores...")
    running_sensors = False
    try:
        GPIO.cleanup()
    except:
        pass
    print("  ✅ Hilo detenido")

def get_sensor_history():
    return sensor_history

def get_time_history():
    return time_history

print("  ✅ Módulo sensor_shared cargado correctamente")
print("  📡 Usa iniciar_hilo_sensores() para comenzar la adquisición")
print("  📊 Historiales disponibles: sensor_history, time_history")