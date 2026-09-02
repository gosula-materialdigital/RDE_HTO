"""Entry point for the heat-treatment (HTO) rdetoolkit dataset structuring run."""
import rdetoolkit

from modules.data_transformation import my_hto_func

rdetoolkit.workflows.run(custom_dataset_function=my_hto_func)
