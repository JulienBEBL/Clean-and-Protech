#!/usr/bin/python3

import time
from time import monotonic

from utils.logging import setup_logging
from utils.helpers import format_mmss, throttle

from drivers.gpio import GPIOController
from drivers.shift_register import ShiftRegister
from drivers.mcp3008 import MCP3008Controller
from drivers.lcd import LCDController
from drivers.flow_sensor import FlowSensor

from controllers.valves import ValveController
from controllers.air_system import AirSystemController
from controllers.flow_meter import FlowMeterController
from controllers.user_input import UserInputController

from models.state import SystemState
from models.program import IrrigationProgram

from config.settings import (
    MOTOR_PINS, PROGRAM_DURATION_SEC, DISPLAY_PERIOD_S,
    AIR_MODES, V4V_POS_STEPS, Direction
)

# Initialize logging
log = setup_logging()

# Initialize hardware components
gpio = GPIOController()
shift_register = ShiftRegister(gpio)
mcp_controller = MCP3008Controller()
lcd = LCDController()
flow_sensor = FlowSensor(gpio)

# Initialize controllers
valve_controller = ValveController(gpio, shift_register)
air_controller = AirSystemController(gpio, shift_register)
flow_meter = FlowMeterController(flow_sensor)
user_input = UserInputController(mcp_controller)

# Initialize system state
system_state = SystemState()

# Define programs
def create_programs():
    programs = []
    
    def prg_1():
        # Implementation of program 1
        pass
        
    def prg_2():
        # Implementation of program 2
        pass
        
    # ... other programs
        
    programs.append(IrrigationProgram(1, "Program 1", 
                                     ["eau", "cuve", "pompeOUT", "clientD", "egout"], 
                                     ["clientG", "boue"], prg_1))
                                     
    programs.append(IrrigationProgram(2, "Program 2", 
                                     ["clientD", "boue", "egout"], 
                                     ["eau", "cuve", "pompeOUT", "clientG"], prg_2))
                                     
    # ... other programs
    
    return programs

programs = create_programs()

def initialize_system():
    """Initialize the system hardware"""
    log.info("Initializing system")
    
    # Apply initial air mode
    air_controller.set_mode(0)
    air_controller.set_electrovalve(False)
    
    # Display initialization message
    lcd.display_message("Initialization", "In progress...")
    
    # Reset shift register
    shift_register.update(new_dir_mask=0x00, new_led_mask=0x01)
    time.sleep(0.5)
    
    # Initialize all valves
    for valve_name in MOTOR_PINS.keys():
        lcd.display_message("MAZ motor:", valve_name)
        valve_controller.set_direction(valve_name, Direction.CLOSE)
        valve_controller.move_valve(valve_name, STEP_MAZ, MAZ_DELAY)
        time.sleep(2 * WAIT_DELAY)
        valve_controller.move_valve(valve_name, STEP_MICRO_MAZ, MAZ_DELAY)
        time.sleep(WAIT_DELAY)
        
    system_state.v4v_position = 0
    
    lcd.display_message("Initialization", "OK")
    log.info("Initialization OK")
    time.sleep(1)
    
    show_idle_prompt()

def show_idle_prompt():
    """Show idle prompt once"""
    if not system_state.idle_prompt_shown:
        lcd.display_message("Choose a", "program:")
        system_state.idle_prompt_shown = True

def update_run_display(program_number: int, start_time: float, current_time: float):
    """Update display during program execution"""
    global system_state
    
    if (current_time - system_state.last_display_switch) >= DISPLAY_PERIOD_S:
        system_state.display_toggle = not system_state.display_toggle
        system_state.last_display_switch = current_time
        lcd.clear()

    elapsed = int(current_time - start_time)
    remain = max(0, PROGRAM_DURATION_SEC - elapsed)

    if not system_state.display_toggle:
        # Screen A: Program info
        lcd.display_line(1, f"Program {program_number}")
        lcd.display_line(2, f"Total 05:00  R:{format_mmss(remain)}")
    else:
        # Screen B: Flow info
        lcd.display_line(1, f"Flow {flow_meter.instant_flow_rate:4.1f} L/min")
        lcd.display_line(2, f"Total {flow_meter.total_volume:6.2f} L")

def safe_shutdown():
    """Safe system shutdown"""
    try:
        log.info("[SHUTDOWN] EV OFF + closing valves")
        air_controller.set_electrovalve(False)
        time.sleep(1)
        valve_controller.close_all_valves_except_v4v()
        lcd.display_message("Total volume:", f"{flow_meter.total_volume:.2f} L")
        log.info(f"[SHUTDOWN] Total = {flow_meter.total_volume:.2f} L")
    except Exception as e:
        log.error(f"[SHUTDOWN] Error: {e}")

def main_loop():
    """Main program loop"""
    try:
        initialize_system()
        
        while True:
            # Update user input
            user_input.update()
            
            # Update air system
            air_controller.update_from_button(user_input.air_button_state)
            air_controller.tick(monotonic())
            
            # Update shift register
            shift_register.update()
            
            # Handle program selection
            if user_input.program_number == 0:
                show_idle_prompt()
            else:
                system_state.idle_prompt_shown = False
                
            # Execute selected program if confirmed
            program_num = user_input.program_number
            if program_num > 0 and user_input.confirm_program(program_num):
                program = next((p for p in programs if p.number == program_num), None)
                if program:
                    program.execute()
                    
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        log.warning("EXIT BY CTRL-C")
    except Exception as e:
        log.error(f"EXIT BY ERROR: {e}")
    finally:
        safe_shutdown()
        time.sleep(5)
        shift_register.update(new_dir_mask=0x00, new_led_mask=0x00)
        mcp_controller.close()
        gpio.cleanup()
        log.info("END OF PROGRAM")

if __name__ == "__main__":
    main_loop()
