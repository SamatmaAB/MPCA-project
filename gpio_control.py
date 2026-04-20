import time
import threading
from utils import logger
import platform

# Mock for non-Raspberry Pi environments (like Windows)
if platform.system() == "Windows" or platform.system() == "Darwin":
    IS_RPI = False
    logger.warning("Running on Windows/Mac. Using Mock GPIO for testing.")
else:
    try:
        from gpiozero import LED, Buzzer, Button
        IS_RPI = True
    except (ImportError, NotImplementedError):
        IS_RPI = False
        logger.warning("gpiozero not found. Using Mock GPIO for testing.")



class AccessController:
    def __init__(self, unlock_pin=17, buzzer_pin=27, cooldown_sec=3.0):
        self.cooldown_sec = cooldown_sec
        self.is_cooling_down = False
        if IS_RPI:
            try:
                # We use LED class for Relay as well since it's just basic on/off output
                self.relay = LED(unlock_pin)
                self.buzzer = Buzzer(buzzer_pin)
            except Exception as e:
                logger.warning(f"Could not load physical GPIOs (Mocking instead): {e}")
                self.relay = None
                self.buzzer = None
        else:
            self.relay = None
            self.buzzer = None
            
    def _trigger_device(self, device, duration_sec, device_name):
        logger.info(f"[HARDWARE] Activating {device_name} for {duration_sec}s")
        if IS_RPI:
            device.on()
            time.sleep(duration_sec)
            device.off()
        else:
            time.sleep(duration_sec)
            
        # Give some time before accepting new commands to prevent stutter
        time.sleep(self.cooldown_sec)
        self.is_cooling_down = False
        logger.info(f"[{device_name}] Cooldown completed. Ready.")

    def _trigger_pulsing_device(self, device, duration_sec, device_name):
        logger.info(f"[HARDWARE] Activating Pulsing {device_name} for {duration_sec}s")
        end_time = time.time() + duration_sec
        if IS_RPI and device:
            while time.time() < end_time:
                device.on()
                time.sleep(0.1)
                device.off()
                time.sleep(0.1)
        else:
            time.sleep(duration_sec)
            
        time.sleep(self.cooldown_sec)
        self.is_cooling_down = False
        logger.info(f"[{device_name}] Cooldown completed. Ready.")

    def approve_access(self):
        """Unlocks door/relay"""
        if self.is_cooling_down:
            return
            
        self.is_cooling_down = True
        logger.info(">>> ACCESS APPROVED <<<")
        # Trigger unlock for 2 seconds in a background thread to not block video feed
        threading.Thread(target=self._trigger_device, args=(self.relay, 2.0, "UNLOCK_RELAY"), daemon=True).start()

    def reject_access(self):
        """Sounds rapid buzzer/alarm"""
        if self.is_cooling_down:
            return
            
        self.is_cooling_down = True
        logger.warning("!!! ACCESS REJECTED (INTRUDER) !!!")
        # Trigger rapid pulsing buzzer for 2 seconds
        threading.Thread(target=self._trigger_pulsing_device, args=(self.buzzer, 2.0, "ALARM_BUZZER"), daemon=True).start()

class EnvironmentSensors:
    def __init__(self, ir_pin=18, dht_pin=4, temp_threshold=50.0):
        self.temp_threshold = temp_threshold
        self.dht_device = None
        self.ir = None
        
        if IS_RPI:
            # IR Sensor Setup
            try:
                from gpiozero import DigitalInputDevice
                self.ir = DigitalInputDevice(ir_pin, pull_up=False)
            except Exception as e:
                logger.error(f"Failed to load IR sensor: {e}")

            # DHT-11 Sensor Setup
            try:
                import board
                import adafruit_dht
                # DHT-11 connected to GPIO 4 (board.D4)
                self.dht_device = adafruit_dht.DHT11(getattr(board, f"D{dht_pin}"))
            except Exception as e:
                logger.error(f"Failed to load DHT11 sensor (ensure adafruit-circuitpython-dht is installed): {e}")

    def is_ir_triggered(self):
        # RETURN TRUE FOR TESTING - Forces the system to stay continuously awake
        # Revert this to `return self.ir.is_active if IS_RPI and self.ir else False` in production
        return True

    def get_temperature(self):
        """Returns the temperature in Celsius from DHT-11."""
        if IS_RPI and self.dht_device:
            try:
                # DHT sensors often fail to read on first try due to timing; circuitpython handles this gracefully
                # but might still throw RuntimeError
                temp = self.dht_device.temperature
                if temp is not None:
                    return temp
                return 25.0
            except RuntimeError:
                # Common issue with DHT, just return default and try next loop
                return 25.0
            except Exception as e:
                return 25.0
        return 25.0

    def check_temp_alarm(self, access_controller):
        """Checks if temperature exceeds threshold and triggers the buzzer."""
        t = self.get_temperature()
        if t > self.temp_threshold:
            logger.warning(f"TEMPERATURE ALARM: {t}C exceeds limit {self.temp_threshold}C!")
            if hasattr(access_controller, 'buzzer') and access_controller.buzzer:
                threading.Thread(target=access_controller._trigger_device, args=(access_controller.buzzer, 3.0, "TEMP_ALARM"), daemon=True).start()
            return True
        return False

