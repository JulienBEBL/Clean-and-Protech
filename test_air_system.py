import pytest
from unittest.mock import Mock
from controllers.air_system import AirSystemController
from config.settings import AIR_MODES

@pytest.fixture
def air_controller():
    gpio_mock = Mock()
    shift_reg_mock = Mock()
    return AirSystemController(gpio_mock, shift_reg_mock)

def test_set_mode(air_controller):
    air_controller.set_mode(1)
    assert air_controller.mode == 1
    air_controller.shift_register.update.assert_called_with(new_led_mask=2)
    
def test_set_electrovalve(air_controller):
    air_controller.set_electrovalve(True)
    air_controller.gpio.output.assert_called_with(air_controller.relay_pin, True)
    assert air_controller.ev_on == True

def test_update_from_button(air_controller):
    air_controller.last_button_state = 0
    air_controller.update_from_button(1)  # Rising edge
    assert air_controller.mode == 1
    air_controller.update_from_button(1)  # Still pressed
    assert air_controller.mode == 1  # Should not change
