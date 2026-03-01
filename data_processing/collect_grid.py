import pyvisa
import os
import time
import csv

rm = pyvisa.ResourceManager("@py")
print(rm.list_resources())
# Replace with your instrument VISA resource string
scope = rm.open_resource('USB0::62700::60986::SDS1MGDQ4R2387::0::INSTR')
scope.timeout = 5000

rows = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
columns = range(1, 16)
captures = range(1, 4)

os.makedirs("./waveforms", exist_ok=True)


def draw_grid(current_r, current_c):
    os.system('clear')
    print("  " + " ".join([f"{c:2}" for c in columns]))
    for r_idx, r in enumerate(rows):
        line = f"{r} "
        for c_idx, c in enumerate(columns):
            if r_idx < current_r or (r_idx == current_r and c_idx < current_c):
                line += " X "
            elif r_idx == current_r and c_idx == current_c:
                line += " O "
            else:
                line += " . "
        print(line)
    print("\n")


for r_idx, row in enumerate(rows):
    for c_idx, col in enumerate(columns):
        draw_grid(r_idx, c_idx)
        for capture in captures:
            print(f"Point {row},{col} Capture {capture}/3")
            input("Press Enter after capturing")

            scope.write("C1:WF? DAT2")
            raw_data = scope.read_raw()

            header_length = 16
            waveform_data = raw_data[header_length:-2]

            filename = f"waveforms/waveform_{row}{col}_{capture}.csv"
            with open(filename, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["Index", "Raw_Value"])
                for i, val in enumerate(waveform_data):
                    writer.writerow([i, val])

            time.sleep(0.01)

draw_grid(len(rows), 0)
print("Collection complete.")
