# TMS

Schematics and simulations for a low-cost TMS device.

## kicad/
Contains KiCad schematics for the whole build.
tms_schematic.pdf contains the printed-out version of the schematics.
To edit, download Kicad: https://www.kicad.org/

## ltspice/
Contains LTspice files for simulations of the different parts of the system.
charge.asc simulates the ZVS and rectifier circuit.
discharge.asc simulates the discharge path; you can get the coil di/dt from it.
gate_driver.asc simulates the pulse circuit that activates the SCR.

## python_helpers/
Work in progress.
Contains discharge.py, a file that validates that the generated RLC circuit does not create conditions out of ratings for any of the components. 
