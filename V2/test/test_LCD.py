from time import sleep
from lcd_i2c_20x4 import LCD20x4I2C

lcd = LCD20x4I2C(i2c_address=0x27, i2c_port=1)  # adapte 0x27/0x3F selon ton i2cdetect

lcd.backlight_on()
lcd.clear()
lcd.write_centered(1, "CLEAN & PROTECH")
lcd.write_line(2, "Ligne 2: OK")
lcd.write_line(3, "Compteur:", col=0)

for i in range(5):
    lcd.write_line(3, f"Compteur: {i}   ", col=0)
    sleep(1)

lcd.clear_line(2)
lcd.write_centered(4, "FIN TEST")
sleep(2)

lcd.backlight_off()
lcd.clear()
