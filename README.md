# Low-Cost Transcranial Magnetic Stimulation

![Graphical Abstract](figures/Graphical%20abstract.png)

Code, hardware, and data for the paper ["Low-Cost Transcranial Magnetic Stimulation"](TODO) (PREPRINT, SUBJECT TO CHANGES), (2026).

This repository contains the design and validation materials for a low-cost monophasic transcranial magnetic stimulation (TMS) stimulator. As of July 2027, the bill of materials (BOM) runs at USD 657.34. The repository includes the electrical design, controller firmware, and terminal control interface, fabrication files, LTspice simulations, raw magnetic-field measurements, and analysis code to characterize the system.

> [!CAUTION]
> This system contains a high-energy capacitor bank and generates high voltages and strong, rapidly changing magnetic fields. Contact with the system can cause severe injury or death, and stored energy can remain after charging is halted.
> Never rely on the computer interface or firmware as the primary safety mechanism. Work must be performed by trained personnel.
> Do not connect this research prototype to a person or animal.

## Cite
If you use this code, hardware, or data in your research, please cite the following paper:

> **Low-Cost Transcranial Magnetic Stimulation**
> Maxence Lapatrie, Yuzuha Isetani, Jathav Puvirajan, Antonella Catanzaro, Siqi Lyu, Han C. Nguyen, William   Mathieu, Milica Popovich.
> TODO

TODO BIBTEX

## Contact
I welcome any feedback on the paper or repository. If you have questions or require help running the code, please do not hesitate to contact me.

**Email me** at maxence (dot) lapatrie (at) mail (dot) mcgill (dot) ca.<br>
Or message me on **LinkedIn** [maxence-lapatrie](https://www.linkedin.com/in/maxence-lapatrie/).

## System overview
The design separates the build into three voltage domains: control domain, power domain, and high voltage domain. The domains are isolated from each other. The Arduino lives in the control domain and sends signals to the other two domains to control charging and discharging.

![Systems Overview](figures/Systems%20overview.png)

See the complete [schematic](schematics/tms_schematic.pdf) for a more detailed understanding of the circuit.

## Repository contents
| Path | Contents |
| --- | --- |
| [`2d_models/`](2d_models/) | FreeCAD, SVG, PDF, and PNG fabrication drawings for the coil windings and busbars |
| [`3d_models/`](3d_models/) | FreeCAD sources and printable STL files for the coil winder and pickup coil helpers |
| [`controller_arduino/`](controller_arduino/) | Arduino UNO R4 Minima firmware and the Python terminal user interface |
| [`data_processing/`](data_processing/) | Raw oscilloscope captures, acquisition scripts, data analysis notebooks, SimNIBS helpers, and generated figures |
| [`figures/`](figures/) | Build, software-interface, and validation figures used in this README |
| [`schematics/`](schematics/) | KiCad project, hierarchical schematics, and a three-page PDF export |
| [`simulations/`](simulations/) | LTspice models for the charger, discharge path, gate driver, and IL300 linear optocoupler |
| [`Safety_Checklists.pdf`](Safety_Checklists.pdf) | Project-specific inspection, pre-charge, and de-energization checklists |
| [`TMS_field_grid.pdf`](TMS_field_grid.pdf) | Coordinate grids used for magnetic-field measurements |
| [`requirements.txt`](requirements.txt) | Pinned Python analysis environment |

Editable source files are included wherever possible. The PDF, SVG, STL, and PNG files are provided for convenience.

## Software setup

### Analysis environment

Python 3.10 or newer is recommended.
```bash
git clone <REPOSITORY_URL>
cd <REPOSITORY_DIRECTORY>

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```
Additional dependencies not included above:
- SimNIBS 4.6 is required by `data_processing/create_simple_figure_of_8_coil.py` and `data_processing/plot_simnibs.py`. Run these scripts in the Python environment supplied with the SimNIBS installation.
- KiCad, LTspice, and FreeCAD are recommended if one desires to edit the design files.

### Controller interface

Compile and upload [`controller_arduino.ino`](controller_arduino/controller_arduino.ino) to an Arduino UNO R4 Minima. Before compiling, review the pin assignments and calibrate the following firmware constants against the assembled measurement and gate-driver circuits:

- `MAX_ADC`: capacitor-bank overvoltage threshold in ADC counts;
- `FIRE_DELAY_US`: delay used to obtain the required SCR gate-pulse width;
- `COMP_STOP_ACTIVE`: active level of the independent comparator trip.

`MAX_ADC` must be calculated from measured values:

```text
MAX_ADC = round((V_trip / divider_ratio) / V_ref * ADC_FULL_SCALE)
```

The values committed in the firmware and terminal interface document the tested configuration; they are not universal safe defaults. The `DEFAULT_MAX_ADC` value in `app.py` must match the firmware `MAX_ADC`, and the divider ratio shown by the interface must match the physical divider tap in use.

```bash
cd controller_arduino
python app.py --divider <MEASURED_DIVIDER_RATIO> \
  --vref <MEASURED_ADC_REFERENCE_V> \
  --max-adc <FIRMWARE_MAX_ADC>
```

Press `p` in the interface to select a port.

| Key | Command |
| --- | --- |
| `r` | Reset the controller state after all hardware trips are clear |
| `c` | Start or stop charging |
| `a` | Arm or unarm the discharge; arming also stops charging |
| `f` | Request one firing pulse while armed |
| `s` | Query controller status |
| `p` | Select a serial port |
| `d` | Disconnect |
| `q` | Quit |

![Controller interface and data-collection helper](figures/Python%20Apps.png)


## Data collection and analysis

The data used in our analyses is provided under [`data_processing/waveforms`](data_processing/waveforms). The MagVenture* components correspond to the data collected from the MRI-B91 MagVenture coil with the MagVenture MagPro X100 TMS. The other components correspond to the homemade coil under 24V and 1480V capacitor charges.

### Magnetic-field grid acquisition

[`collect_grid.py`](data_processing/collect_grid.py) automates oscilloscope captures at each location of a pre-programmed field-measurement grid. Before use:

1. Replace the VISA resource string with the identifier reported for the oscilloscope;
2. Select the measured field component;
3. Set `start_row` and `start_col` if resuming an interrupted acquisition; and
4. Confirm the oscilloscope channel, vertical scale, offset, sample rate, and binary-waveform format.

Each capture is stored as a CSV file with `Time (s)` and `Voltage (V)` columns.
Use [`TMS_field_grid.pdf`](TMS_field_grid.pdf) to help position your pickup coil.

### Deriving coil change of current

[`derive_didt.ipynb`](data_processing/derive_didt.ipynb):
1. Loads capacitor and three-axis pickup-coil waveforms;
2. Filters and maps the measured peak voltages;
3. Converts the measurements to empirical dB/dt maps;
4. Computes corresponding maps from a discretized figure-of-eight coil model; and
5. Estimates coil dI/dt by a global least-squares fit.

Change `user_local_dir` at the beginning of the notebook before running it. Select `homemade_coil` and `low_voltage` to match the dataset being analyzed.

### Other data analysis helpers

- [`plot_gate_pulses.ipynb`](data_processing/plot_gate_pulses.ipynb) compares the microcontroller and gate-resistor pulses and estimates the gate-current rise rate. It expects local files under `waveforms/gate_component/`.
- [`create_simple_figure_of_8_coil.py`](data_processing/create_simple_figure_of_8_coil.py) creates the line-segment TMS coil model used by SimNIBS.

## Example validation output

The repository includes raw low-voltage, high-voltage, and commercial-coil reference measurements. The figure below compares the measured and wire-segment-model dB/dt maps and shows the global least-squares fits used to estimate coil dI/dt at low and high capacitor-bank voltages:

![Empirical and modeled dB/dt maps with estimated coil dI/dt](figures/db_dt%20to%20di_dt.png)

## Safety documentation

Read [`Safety_Checklists.pdf`](Safety_Checklists.pdf) before inspecting or operating the physical system. These checklists document the procedures used for this prototype, but they are not a substitute for a complete, site-specific risk assessment or formal training.

## Licensing

The controller source files, data analysis code, and data collection code are licensed under the MIT SPDX license. The SimNIBS-derived coil-generation example retains its GPLv3 notice. All hardware files are licensed under the CERN-OHL-P-2.0 license. Project-authored data, figures, and documentation are licensed under the CC-BY-4.0 license. Read [LICENSE](LICENSE) for more information. 
