import time

#!/usr/bin/env python3
"""
Driver simple pour DM860T sur Raspberry Pi (RPi.GPIO, BCM mode).
Pins (BCM) : ENA=5, DIR=6, PULSE=13
Driver configuré pour 3200 pas par révolution (steps_per_rev=3200).
Usage minimal: créer StepperDM860T(...) et appeler rotate_revolutions / step / rotate_angle.
"""

import RPi.GPIO as GPIO


class StepperDM860T:
    def __init__(self, ena_pin: int, dir_pin: int, pulse_pin: int, steps_per_rev: int = 3200):
        # Utilisation de la numérotation BCM
        GPIO.setmode(GPIO.BCM)
        self.ENA = ena_pin
        self.DIR = dir_pin
        self.PULSE = pulse_pin
        self.steps_per_rev = int(steps_per_rev)

        GPIO.setup(self.ENA, GPIO.OUT, initial=GPIO.HIGH)   # ENA actif bas sur la plupart des drivers (LOW = enable)
        GPIO.setup(self.DIR, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.PULSE, GPIO.OUT, initial=GPIO.LOW)

        # Paramètres temporels
        self.min_pulse = 5e-6        # 5 microsecondes minimum (driver TTL)
        self.default_pulse = 50e-6   # 50 microsecondes par front (sûr)
        # note: la précision temporelle dépend de l'OS (Linux) et Python; pour haute vitesse, envisager hardware PWM.

    def enable(self):
        # Active le driver (ENA = LOW pour de nombreux drivers DM860T)
        GPIO.output(self.ENA, GPIO.LOW)

    def disable(self):
        # Désactive le driver (économie d'énergie et arrêt des sorties)
        GPIO.output(self.ENA, GPIO.HIGH)

    def set_direction(self, clockwise: bool = True):
        # Convention: True = CLOCKWISE (DIR = LOW), False = COUNTERCLOCKWISE (DIR = HIGH)
        # Ajuster selon câblage / besoin.
        GPIO.output(self.DIR, GPIO.LOW if clockwise else GPIO.HIGH)

    def _single_pulse(self, high_time: float, low_time: float):
        # Une impulsion complète (HIGH puis LOW)
        GPIO.output(self.PULSE, GPIO.HIGH)
        time.sleep(high_time)
        GPIO.output(self.PULSE, GPIO.LOW)
        time.sleep(low_time)

    def step(self, steps: int, rpm: float = 1.0):
        """
        Effectue un nombre de steps à la vitesse spécifiée en rpm.
        rpm : tours par minute
        steps : nombre de pas (int)
        """
        steps = int(abs(steps))
        if steps == 0:
            return

        if rpm <= 0:
            raise ValueError("rpm doit être > 0")

        # Calcul du délai entre fronts pour la vitesse voulue
        steps_per_second = (rpm * self.steps_per_rev) / 60.0
        if steps_per_second <= 0:
            raise ValueError("vitesse invalide calculée")

        period = 1.0 / steps_per_second  # période complète (HIGH+LOW)
        half_period = period / 2.0

        # Assurer au moins min_pulse
        high_time = max(self.min_pulse, min(self.default_pulse, half_period))
        low_time = max(self.min_pulse, half_period - high_time)
        if low_time < self.min_pulse:
            # si low_time trop petit, ajuster high_time
            low_time = self.min_pulse
            high_time = max(self.min_pulse, half_period - low_time)

        for _ in range(steps):
            self._single_pulse(high_time, low_time)

    def rotate_revolutions(self, revolutions: float, rpm: float = 1.0):
        # Tour complet = steps_per_rev
        steps = int(round(revolutions * self.steps_per_rev))
        self.step(steps, rpm)

    def rotate_angle(self, angle_deg: float, rpm: float = 1.0):
        # Angle en degrés
        revolutions = float(angle_deg) / 360.0
        self.rotate_revolutions(revolutions, rpm)

    def cleanup(self):
        # Remet les pins dans un état sûr
        try:
            self.disable()
        finally:
            GPIO.cleanup([self.ENA, self.DIR, self.PULSE])


if __name__ == "__main__":
    # Exemple d'utilisation minimal
    # Attention: utiliser ce script avec le driver correctement alimenté et la masse commune.
    ENA_PIN = 5
    DIR_PIN = 6
    PULSE_PIN = 13
    STEPS_PER_REV = 3200

    motor = StepperDM860T(ENA_PIN, DIR_PIN, PULSE_PIN, steps_per_rev=STEPS_PER_REV)
    try:
        motor.enable()
        motor.set_direction(clockwise=True)
        # tourner 1 révolution à 10 rpm
        motor.rotate_revolutions(1.0, rpm=10.0)
        time.sleep(0.5)
        motor.set_direction(clockwise=False)
        # tourner 0.5 révolution à 5 rpm
        motor.rotate_revolutions(0.5, rpm=5.0)
    except KeyboardInterrupt:
        pass
    finally:
        motor.cleanup()