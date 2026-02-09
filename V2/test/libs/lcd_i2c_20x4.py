#!/usr/bin/python3


import smbus
import time


class LCDI2C_backpack(object):
  # --- Defaults ---
  I2C_ADDR  = 0x27
  LCD_WIDTH = 20

  # Mode
  LCD_CHR = 1
  LCD_CMD = 0

  # LCD RAM addresses (20x4)
  LCD_LINE_1 = 0x80
  LCD_LINE_2 = 0xC0
  LCD_LINE_3 = 0x94
  LCD_LINE_4 = 0xD4

  # Backlight masks
  LCD_BACKLIGHT_ON  = 0x08
  LCD_BACKLIGHT_OFF = 0x00

  ENABLE = 0b00000100

  # Timing
  E_PULSE = 0.0005
  E_DELAY = 0.0005

  # I2C bus
  bus = smbus.SMBus(1)

  def __init__(self, I2C_ADDR: int = 0x27):
    self.I2C_ADDR = I2C_ADDR
    self._backlight = self.LCD_BACKLIGHT_ON
    self.init()
    self.clear()

  def init(self):
    self.lcd_byte(0x33, self.LCD_CMD)
    self.lcd_byte(0x32, self.LCD_CMD)
    self.lcd_byte(0x06, self.LCD_CMD)
    self.lcd_byte(0x0C, self.LCD_CMD)
    self.lcd_byte(0x28, self.LCD_CMD)
    self.lcd_byte(0x01, self.LCD_CMD)
    time.sleep(self.E_DELAY)

  # ---------- Backlight ----------

  def backlight_on(self):
    self._backlight = self.LCD_BACKLIGHT_ON
    self.bus.write_byte(self.I2C_ADDR, self._backlight)

  def backlight_off(self):
    self._backlight = self.LCD_BACKLIGHT_OFF
    self.bus.write_byte(self.I2C_ADDR, self._backlight)

  # ---------- High-level API ----------

  def write_centered(self, message: str, line: int):
    msg = (message or "")[:self.LCD_WIDTH]
    left_pad = (self.LCD_WIDTH - len(msg)) // 2
    out = (" " * left_pad + msg).ljust(self.LCD_WIDTH, " ")
    self.lcd_string(out, line)

  def lcd_string(self, message, line):
    message = (message or "").ljust(self.LCD_WIDTH, " ")
    self.lcd_byte(line, self.LCD_CMD)
    for i in range(self.LCD_WIDTH):
      self.lcd_byte(ord(message[i]), self.LCD_CHR)

  def clear(self):
    self.lcd_byte(0x01, self.LCD_CMD)

  # ---------- Low-level ----------

  def lcd_byte(self, bits, mode):
    bits_high = mode | (bits & 0xF0) | self._backlight
    bits_low  = mode | ((bits << 4) & 0xF0) | self._backlight

    self.bus.write_byte(self.I2C_ADDR, bits_high)
    self.lcd_toggle_enable(bits_high)

    self.bus.write_byte(self.I2C_ADDR, bits_low)
    self.lcd_toggle_enable(bits_low)

  def lcd_toggle_enable(self, bits):
    time.sleep(self.E_DELAY)
    self.bus.write_byte(self.I2C_ADDR, (bits | self.ENABLE))
    time.sleep(self.E_PULSE)
    self.bus.write_byte(self.I2C_ADDR, (bits & ~self.ENABLE))
    time.sleep(self.E_DELAY)
