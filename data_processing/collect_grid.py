import pyvisa
import os
import time
import csv
import re

rm = pyvisa.ResourceManager("@py")
print(rm.list_resources())
# Replace with your instrument VISA resource string
scope = rm.open_resource('USB0::62700::60986::SDS1MGDQ4R2387::0::INSTR')
scope.timeout = 5000

# Set trigger mode to single
scope.write("TRMD SINGLE")

component = "y"
rows = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
columns = range(1, 16)
captures = range(1, 4)


start_row = 7
start_col = 11

os.makedirs(f"./waveforms/{component}_component", exist_ok=True)

def extract_float(response):
    parts = response.split(" ")
    if len(parts) > 1:
        target = parts[1]
    else:
        target = response

    match = re.search(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", target)
    if match:
        return float(match.group(0))
    raise ValueError(f"Parse failure: {response}")

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
        
        # skip to start point
        if r_idx < start_row or r_idx <= start_row and c_idx < start_col:
            print(r_idx, start_row, c_idx, start_col)
            continue

        draw_grid(r_idx, c_idx)
        for capture in captures:
            print(f"Point {row},{col} Capture {capture}/3")
            input("Press enter to save waveform")

            while True:
                try:
                    vdiv_resp = scope.query("C1:VDIV?")
                    vdiv = extract_float(vdiv_resp)
                    
                    ofst_resp = scope.query("C1:OFST?")
                    voffset = extract_float(ofst_resp)
                    
                    sara_resp = scope.query("SARA?")
                    sara = extract_float(sara_resp)

                    print(f"Parameters: {vdiv} V/div | {sara} Sa/s")

                    scope.write("C1:WF? DAT2")
                    raw_data = scope.read_raw()

                    header_length = 16
                    waveform_data = raw_data[header_length:-2]

                    filename = f"waveforms/{component}_component/waveform_{row}{col}_{capture}.csv"
                    with open(filename, mode='w', newline='') as file:
                        writer = csv.writer(file)
                        writer.writerow(["Time (s)", "Voltage (V)"])
                        
                        for i, val in enumerate(waveform_data):
                            if val > 127:
                                code = val - 256
                            else:
                                code = val
                                
                            voltage = code * (vdiv / 25) - voffset
                            time_sec = i * (1 / sara)
                            writer.writerow([time_sec, voltage])

                    # Arm the trigger for the next capture
                    scope.write("ARM")

                    break
                except Exception as e:
                    print(f"Error reading data. Details: {e}")

            time.sleep(0.01)

draw_grid(len(rows), 0)
print("Collection complete.")
