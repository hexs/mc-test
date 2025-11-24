from datetime import datetime
from FX3U import FX3U

plc = FX3U("192.168.3.254", 1027)

# อ่าน X0..X7
x_vals = plc.read_x(0, 8)
print(datetime.now(), "X0..X7 =", x_vals)

# ปิด Y0..Y7 ทีละบิต
for i in range(8):
    plc.write_y(i, 0)
    print(datetime.now(), f"Y{i} = 0")

# อ่าน Y0..Y7
y_vals = plc.read_y(0, 8)
print(datetime.now(), "Y0..Y7 =", y_vals)

# เปิด Y0..Y7 ทีละบิต
for i in range(8):
    plc.write_y(i, 1)
    print(datetime.now(), f"Y{i} = 1")

# อ่าน Y0..Y7 อีกครั้ง
y_vals = plc.read_y(0, 8)
print(datetime.now(), "Y0..Y7 =", y_vals)

# อ่าน D0..D9
d_vals = plc.read_d(0, 10)
print(datetime.now(), "D0..D9 =", d_vals)

# เขียน D5 = D5+1
d_vals = plc.read_d(0, 10)
new_val = d_vals[5] + 1
plc.write_d(5, new_val)
print(datetime.now(), "Wrote D5 =", new_val)

# อ่าน D0..D9 อีกครั้ง
d_vals = plc.read_d(0, 10)
print(datetime.now(), "D0..D9 =", d_vals)

plc.close()
