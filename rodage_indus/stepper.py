"""
stepper.py — Pilotage bas-niveau des moteurs pour le rodage industriel.

Couche fine au-dessus de V4/libs/moteur.py. Expose deux fonctions
synchrones (bloquantes) utilisées par rodage.py :

    move_vanne_classique(motors, direction)  — ouverture ou fermeture complète
    move_vic_to_position(motors, ctx, pos)   — déplace la VIC vers une position (1..5)

Réutilise exactement les constantes de V4/config.py (steps, vitesses, rampes).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sys
from pathlib import Path

# Assure que V4/ est dans sys.path (géré par rodage.py, mais sécurité défensive)
_V4_ROOT = Path(__file__).resolve().parent.parent / "V4"
if str(_V4_ROOT) not in sys.path:
    sys.path.insert(0, str(_V4_ROOT))

import config as v4cfg

if TYPE_CHECKING:
    from libs.moteur import MotorController


def move_vanne_classique(motors: "MotorController", direction: str, name: str) -> None:
    """
    Course complète ouverture ou fermeture avec rampe.

    Args:
        motors    : MotorController déjà ouvert
        direction : 'ouverture' ou 'fermeture'
        name      : nom métier de la vanne (ex. 'RETOUR')
    """
    motors.move_steps_ramp(
        motor_name=name,
        steps=(
            v4cfg.MOTOR_OUVERTURE_STEPS
            if direction == "ouverture"
            else v4cfg.MOTOR_FERMETURE_STEPS
        ),
        direction=direction,
        speed_sps=(
            v4cfg.MOTOR_OUVERTURE_SPEED_SPS
            if direction == "ouverture"
            else v4cfg.MOTOR_FERMETURE_SPEED_SPS
        ),
        accel=(
            v4cfg.MOTOR_OUVERTURE_ACCEL_SPS
            if direction == "ouverture"
            else v4cfg.MOTOR_FERMETURE_ACCEL_SPS
        ),
        decel=(
            v4cfg.MOTOR_OUVERTURE_DECEL_SPS
            if direction == "ouverture"
            else v4cfg.MOTOR_FERMETURE_DECEL_SPS
        ),
    )


def move_vic_to_position(
    motors: "MotorController",
    current_steps: int,
    target_pos: int,
) -> int:
    """
    Déplace la VIC vers une position (1..5) en delta depuis current_steps.

    Args:
        motors        : MotorController déjà ouvert
        current_steps : position courante en pas (absolu)
        target_pos    : position cible (1..5), clé dans VIC_POSITIONS

    Returns:
        Nouvelle position absolue en pas.
    """
    target_steps = v4cfg.VIC_POSITIONS[target_pos]
    delta = target_steps - current_steps
    if delta == 0:
        return current_steps
    direction = "ouverture" if delta > 0 else "fermeture"
    motors.move_steps("VIC", abs(delta), direction, v4cfg.VIC_SPEED_SPS)
    return target_steps
