from libs.LCDI2C_backpack import LCDI2C_backpack

class LCDController:
    def __init__(self, address=0x27):
        self.lcd = LCDI2C_backpack(address)
        self.clear()
        
    def clear(self):
        self.lcd.clear()
        
    def display_message(self, line1: str, line2: str):
        self.lcd.lcd_string(line1, self.lcd.LCD_LINE_1)
        self.lcd.lcd_string(line2, self.lcd.LCD_LINE_2)
        
    def display_line(self, line: int, text: str):
        if line == 1:
            self.lcd.lcd_string(text, self.lcd.LCD_LINE_1)
        else:
            self.lcd.lcd_string(text, self.lcd.LCD_LINE_2)
