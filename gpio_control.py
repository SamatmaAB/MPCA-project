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

class RegistrationButton:
    def __init__(self, pin=22, callback=None):
        self.callback = callback
        if IS_RPI:
            self.btn = Button(pin, pull_up=True, bounce_time=0.1)
            # Link the physical button press to our callback
            if self.callback:
                self.btn.when_pressed = self.callback
        else:
            self.btn = None
            
    def trigger_mock(self):
        """Simulates a button press on PC via keyboard"""
        if self.callback:
            self.callback()

class AccessController:
    def __init__(self, unlock_pin=17, buzzer_pin=27, cooldown_sec=3.0):
        self.cooldown_sec = cooldown_sec
        self.is_cooling_down = False
        
        if IS_RPI:
            # We use LED class for Relay as well since it's just basic on/off output
            self.relay = LED(unlock_pin)
            self.buzzer = Buzzer(buzzer_pin)
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

    def approve_access(self):
        """Unlocks door/relay"""
        if self.is_cooling_down:
            return
            
        self.is_cooling_down = True
        logger.info(">>> ACCESS APPROVED <<<")
        # Trigger unlock for 2 seconds in a background thread to not block video feed
        threading.Thread(target=self._trigger_device, args=(self.relay, 2.0, "UNLOCK_RELAY"), daemon=True).start()

    def reject_access(self):
        """Sounds buzzer/alarm"""
        if self.is_cooling_down:
            return
            
        self.is_cooling_down = True
        logger.warning("!!! ACCESS REJECTED (INTRUDER) !!!")
        # Trigger buzzer for 1.5 seconds in a background thread
        threading.Thread(target=self._trigger_device, args=(self.buzzer, 1.5, "ALARM_BUZZER"), daemon=True).start()
