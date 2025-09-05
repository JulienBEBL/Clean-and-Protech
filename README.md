# Irrigation Control System

A modular Python-based irrigation control system for Raspberry Pi 4B.

## Features

- Control of multiple stepper motors via DM542T drivers
- Shift register (74HC595) for direction and LED control
- MCP3008 ADC for user input (buttons and selector)
- LCD display for system status
- Flow meter for water measurement
- Multiple irrigation programs
- Non-blocking air system control

## Installation

1. Clone the repository
2. Install dependencies:
pip install -r requirements.txt
3. Ensure all hardware is properly connected

## Usage

Run the main program:
python -m irrigation_control.main


## Testing

Run tests with pytest:
pytest tests/


## Architecture

The system is organized into several modules:

- `drivers/`: Hardware interface classes
- `controllers/`: System control logic
- `models/`: Data models and state management
- `utils/`: Utility functions and logging
- `config/`: Configuration settings
