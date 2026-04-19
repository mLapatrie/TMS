import pyvista as pv
from simnibs import mesh_io
import numpy as np
import sys

# 1. Load the mesh
msh_path = '/home/maxence/Downloads/simnibs4_examples/simnibs_simulation/ernie_TMS_1-0001_MagVenture_C-B60_scalar.msh'
try:
    msh = mesh_io.read_msh(msh_path)
except Exception as e:
    print(f"Error reading mesh: {e}")
    sys.exit(1)

# 2. Extract geometry
points = msh.nodes.node_coord
# Use tetrahedral elements (type 4) for volume
cells = msh.elm.node_number_list[msh.elm.elm_type == 4] - 1
cells_pv = np.hstack(np.column_stack((np.full(cells.shape[0], 4), cells)))
cell_type = np.full(cells.shape[0], 10, dtype=np.uint8) # VTK_TETRA

brain = pv.UnstructuredGrid(cells_pv, cell_type, points)

# 3. Corrected Data Mapping for SimNIBS 4.6 (.values instead of .data)
found_key = None

def get_simnibs_data(data_obj):
    """Helper to find data array in 4.6 objects."""
    # Check for underlying array (usually .values or .data)
    for attr in ['values', 'data']:
        if hasattr(data_obj, attr):
            return getattr(data_obj, attr)
    return None

# Check Node Data
if hasattr(msh, 'nodedata') and msh.nodedata:
    for data_array in msh.nodedata:
        name = getattr(data_array, 'field_name', None) or getattr(data_array, 'name', 'unknown')
        if any(x in name for x in ['E', 'mag', 'norm']):
            val = get_simnibs_data(data_array)
            if val is not None:
                brain.point_data[name] = val
                found_key = name
                break

# Fallback to Element Data
if not found_key and hasattr(msh, 'elmdata') and msh.elmdata:
    for data_array in msh.elmdata:
        name = getattr(data_array, 'field_name', None) or getattr(data_array, 'name', 'unknown')
        if any(x in name for x in ['E', 'mag', 'norm']):
            val = get_simnibs_data(data_array)
            if val is not None:
                brain.cell_data[name] = val
                found_key = name
                break

if not found_key:
    if msh.nodedata:
        print("Diagnostic - NodeData attributes:", dir(msh.nodedata[0]))
    raise KeyError("Could not find E-field data values.")

# 4. Render and Export
plotter = pv.Plotter(off_screen=True)
# Apply a threshold to hide low-field noise if desired: brain.threshold(0.1)
plotter.add_mesh(brain, scalars=found_key, cmap="jet", smooth_shading=True)
plotter.view_xy() # Top-down view
plotter.add_scalar_bar(title=f"{found_key} (V/m)")

# Export with transparency
plotter.screenshot("tms_final_render.png", transparent_background=True, window_size=[2500, 2500])
print(f"Successfully exported {found_key} to tms_final_render.png")
