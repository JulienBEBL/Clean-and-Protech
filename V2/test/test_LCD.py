import time
from smbus2 import SMBus
from lcd_i2c import CharLCD

# I2C address for LCD
I2C_ADDRESS = 0x24
I2C_BUS = 1

# Initialize LCD (20x4 display)
lcd = CharLCD(address=I2C_ADDRESS, bus=SMBus(I2C_BUS), cols=20, rows=4)

def center_text(text, width=20):
    """Center text to fit LCD width"""
    return text.center(width)

def clear_and_display():
    """Clear LCD and display all rows"""
    lcd.clear()
    time.sleep(0.1)
    
    # Row 1
    row1 = center_text("Vidange Cuve travail")
    lcd.write_string(row1)
    
    # Move to row 2
    lcd.cursor_pos = (1, 0)
    row2 = center_text("Temps : 12:43")
    lcd.write_string(row2)
    
    # Move to row 3
    lcd.cursor_pos = (2, 0)
    row3 = center_text("Air : ON | Pompe : ON")
    lcd.write_string(row3)
    
    # Move to row 4
    lcd.cursor_pos = (3, 0)
    row4 = center_text("Q= 285L TOT= 1684L")
    lcd.write_string(row4)

if __name__ == "__main__":
    try:
        clear_and_display()
        print("LCD test completed successfully!")
        time.sleep(5)
        lcd.clear()
    except Exception as e:
        print(f"Error: {e}")