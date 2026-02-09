#!/usr/bin/python3
#--------------------------------------
#  lcd_i2c.py
#  LCD driver using I2C backpack (PCF8574 style).
#  Defaults: 20x4, address 0x27, I2C bus 1.
#  Added:
#   - backlight_on()
#   - backlight_off()
#--------------------------------------

import smbus
import time


class LCDI2C_backpack(object):
  # --- Defaults (20x4 @ 0x27) ---
  I2C_ADDR  = 0x27  # I2C device address (default)
  LCD_WIDTH = 20    # Characters per line (default 20)

  # Mode
  LCD_CHR = 1  # Sending data (characters)
  LCD_CMD = 0  # Sending command

  # LCD RAM addresses for each line (20x4)
  LCD_LINE_1 = 0x80
  LCD_LINE_2 = 0xC0
  LCD_LINE_3 = 0x94
  LCD_LINE_4 = 0xD4

  # Backlight masks
  LCD_BACKLIGHT_ON  = 0x08
  LCD_BACKLIGHT_OFF = 0x00

  ENABLE = 0b00000100

  # Timing constants
  E_PULSE = 0.0005
  E_DELAY = 0.0005

  # I2C bus (Pi: usually 1)
  bus = smbus.SMBus(1)

  LCD_CURSORSHIFT = 0x10
  LCD_DISPLAYMOVE = 0x08
  LCD_MOVERIGHT = 0x04
  LCD_MOVELEFT = 0x00

  LCD_ENTRYSHIFTINCREMENT = 0x01
  LCD_ENTRYMODESET = 0x04

  def __init__(self, I2C_ADDR: int = 0x27):
    self.I2C_ADDR = I2C_ADDR
    self._backlight = self.LCD_BACKLIGHT_ON  # default ON
    self.init()
    self.clear()

  def init(self):
    # Initialise display
    self.lcd_byte(0x33, self.LCD_CMD)  # Initialise
    self.lcd_byte(0x32, self.LCD_CMD)  # Initialise
    self.lcd_byte(0x06, self.LCD_CMD)  # Cursor move direction
    self.lcd_byte(0x0C, self.LCD_CMD)  # Display On, Cursor Off, Blink Off
    self.lcd_byte(0x28, self.LCD_CMD)  # Data length, number of lines, font size
    self.lcd_byte(0x01, self.LCD_CMD)  # Clear display
    time.sleep(self.E_DELAY)

  # -------- Added API --------

  def backlight_on(self):
    """Allumer la LED/backlight."""
    self._backlight = self.LCD_BACKLIGHT_ON
    # Petit write pour appliquer immédiatement
    self.bus.write_byte(self.I2C_ADDR, self._backlight)

  def backlight_off(self):
    """Eteindre la LED/backlight."""
    self._backlight = self.LCD_BACKLIGHT_OFF
    self.bus.write_byte(self.I2C_ADDR, self._backlight)

  # --------------------------

  def lcd_byte(self, bits, mode):
    # Send byte to data pins
    # mode = 1 for character, 0 for command

    bits_high = mode | (bits & 0xF0) | self._backlight
    bits_low  = mode | ((bits << 4) & 0xF0) | self._backlight

    # High bits
    self.bus.write_byte(self.I2C_ADDR, bits_high)
    self.lcd_toggle_enable(bits_high)

    # Low bits
    self.bus.write_byte(self.I2C_ADDR, bits_low)
    self.lcd_toggle_enable(bits_low)

  def lcd_toggle_enable(self, bits):
    time.sleep(self.E_DELAY)
    self.bus.write_byte(self.I2C_ADDR, (bits | self.ENABLE))
    time.sleep(self.E_PULSE)
    self.bus.write_byte(self.I2C_ADDR, (bits & ~self.ENABLE))
    time.sleep(self.E_DELAY)

  def scrollDisplayRight(self):
    self.lcd_byte(self.LCD_CURSORSHIFT | self.LCD_DISPLAYMOVE | self.LCD_MOVERIGHT, self.LCD_CMD)

  def scrollDisplayLeft(self):
    self.lcd_byte(self.LCD_CURSORSHIFT | self.LCD_DISPLAYMOVE | self.LCD_MOVELEFT, self.LCD_CMD)

  def message(self, text):
    for char in text:
      if char == '\n':
        self.lcd_byte(self.LCD_LINE_2, self.LCD_CMD)  # next line
      else:
        self.lcd_byte(ord(char), self.LCD_CHR)

  def lcd_string(self, message, line):
    message = (message or "").ljust(self.LCD_WIDTH, " ")
    self.lcd_byte(line, self.LCD_CMD)
    for i in range(self.LCD_WIDTH):
      self.lcd_byte(ord(message[i]), self.LCD_CHR)

  def clear(self):
    self.lcd_byte(0x01, self.LCD_CMD)
