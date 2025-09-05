import pytest
from unittest.mock import Mock, MagicMock
from controllers.valves import ValveController
from config.settings import Direction

@pytest.fixture
def valve_controller():
    gpio_mock = Mock()
    shift_reg_mock = Mock()
    return ValveController(gpio_mock, shift_reg_mock)

def test_set_direction(valve_controller):
    valve_controller.set_direction("V4V", Direction.OPEN)
    valve_controller.shift_register.set_direction.assert_called_with(0, Direction.OPEN)
    
    valve_controller.set_direction("V4V", Direction.CLOSE)
    valve_controller.shift_register.set_direction.assert_called_with(0, Direction.CLOSE)

def test_move_valve(valve_controller):
    valve_controller.move_valve("V4V", 10, 0.001)
    assert valve_controller.gpio.output.call_count == 20  # 10 steps * 2 (on/off)
