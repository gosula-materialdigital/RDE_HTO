"""Entry point for the heat-treatment (HTO) rdetoolkit dataset structuring run."""
import rdetoolkit

from modules.data_transformation import my_hto_func

# 1. Input files: furnace CSVs are placed manually in data/inputdata
#    (no ELN fetch yet). rdetoolkit picks them up as input files and copies
#    them to data/raw itself.

# 2. Run the RDE structuring pipeline on inputdata
rdetoolkit.workflows.run(custom_dataset_function=my_hto_func)
