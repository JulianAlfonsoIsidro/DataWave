"""Part5_Personas pipeline: persona segmentation over the lead population.

Clusters leads into interpretable personas (k-prototypes) from reused
``outputs/`` artifacts and ``data/`` inputs, profiles and names each persona,
and exports a per-lead labeled CSV. Pure pipeline package (``PYTHONPATH=src``);
adds no modelling to the Part 1/3/4 APIs it reuses read-only.
"""
