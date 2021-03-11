"""
This module produces a control heatmap for a chess game which shows which side
controls which squares how many times per ply/move in a Chess board
"""
from .chess_util import ChessUtil
from .chess_dask_cluster import ChessDaskCluster

class ChessControlHeatmap:
    "Class to generate the control heatmap based on the input PGN files"

    def generate_heatmap_images(self):
        "Fetches the input from files and starts to analyze the games"
        game_list = ChessUtil.get_games_from_pgn_files()
        dask_cluster = ChessDaskCluster()
        dask_cluster.analyse_games_in_cluster(game_list)
