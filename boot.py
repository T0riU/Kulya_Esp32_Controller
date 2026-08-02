import machine
from time import sleep

print('RC for KULYA')
print("ESP32 Started")

seconds_to_start = 3

print('starting in ',seconds_to_start) 
for i in range(seconds_to_start):
   print('.')
   sleep(1)
else:
    import sender   