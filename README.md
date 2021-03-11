# chess-heatmap-PyPI-package
This repository is related to the chess-heatmap project. It contains the python files which have been bundled as PyPI python package. The package is available with the name 'chess_heatmap_qxf2'

The chess-heatmap project uses dask collections and runs on a Coiled cluster. Dask tasks are submitted by Scheduler to workers. When the workers start working on the tasks, they need some associated files which are present on the client machine. So, bundled it as package. Workers install this package in their machines and can use the files. 
