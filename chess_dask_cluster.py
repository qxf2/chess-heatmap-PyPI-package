"""
This module is for parallelizing the calculation of heatmap for each ply in a game
using dask tasks and parallelizing multiple games in PGNs
"""
import os
import errno
import json
import base64
import yaml
from dask.distributed import LocalCluster
from dask.distributed import Client
from dask.distributed import get_client, as_completed
from dask.distributed import TimeoutError
from distributed import wait
from dask import config
import coiled
from .chess_util import ChessUtil
from .chess_image_generator import ChessImageGenerator


class ChessDaskCluster:
    "Class for using dask tasks to parallelize calculation of heatmap"
    @staticmethod
    def get_game_data(result_list, ply_count):
        "Preparing the data for all plies in all the games"

        game_data = {}
        game_data["white"] = []
        game_data["black"] = []
        game_data["max_white_value"] = 0
        game_data["max_black_value"] = 0

        for each in range(ply_count):
            ply_mapwhite = [[0 for x in range(8)] for y in range(8)]
            ply_mapblack = [[0 for x in range(8)] for y in range(8)]
            game_data["white"].append(ply_mapwhite)
            game_data["black"].append(ply_mapblack)
        for result_for_square in result_list:
            ply_no = result_for_square["ply"]
            square_index = result_for_square["square"]
            row = square_index//8
            column = square_index%8
            if "white" in result_for_square:
                power = result_for_square["white"]
                if power > game_data["max_white_value"]:
                    game_data["max_white_value"] = power
                game_data["white"][ply_no][7-row][column] = power
            else:
                power = result_for_square["black"]
                if power > game_data["max_black_value"]:
                    game_data["max_black_value"] = power
                game_data["black"][ply_no][7-row][7-column] = power

        return game_data

    @staticmethod
    def analyse_game_in_worker(game_dict):
        """
        For a game, for every ply, generate tasks to be run in parallel in a dask cluster.
        One task is created per ply. A worker client is used here because this method
        itself is run inside a worker
        """
        game = game_dict["game"]
        game_no = game_dict["game_no"]
        timeout = game_dict["timeout"]
        tasks_for_game = ChessUtil.generate_ply_info_list_for_game(game)
        worker_client = get_client()
        task_futures = worker_client.map(ChessUtil.find_control_for_square,
                                        tasks_for_game["game_tasks"])
        game_data = None
        try:
            wait(task_futures, timeout)
            control_list_for_game = worker_client.gather(task_futures)
            game_results = []
            for ply_list in control_list_for_game:
                game_results.extend(ply_list)
            game_data = ChessDaskCluster.get_game_data(game_results, tasks_for_game["ply_count"])
            game_data["filename"] = str(game_no) + " " + game.headers["Event"]
        except TimeoutError:
            print("Game timed out: " + str(game_no))
        return game_data

    def __init__(self):
        config_file = os.path.join(os.getcwd(), "config", "config.yaml")
        if not os.path.isfile(config_file):
            raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), config_file)
        with open(config_file) as file:
            self.config_values = yaml.full_load(file)
        if not "cluster_name" in self.config_values:
            self.config_values["cluster_name"] = "chess-cluster"
        if not "software_environment_name" in self.config_values:
            self.config_values["software_environment_name"] = "chess-env"
        if not "n_workers" in self.config_values:
            self.config_values["n_workers"] = 50
        if not "worker_cpu" in self.config_values:
            self.config_values["worker_cpu"] = 1
        if not "worker_memory" in self.config_values:
            self.config_values["worker_memory"] = 8
        if not "scheduler_memory" in self.config_values:
            self.config_values["scheduler_memory"] = 16
        if not "scheduler_cpu" in self.config_values:
            self.config_values["scheduler_cpu"] = 4
        if not "game_batch_size" in self.config_values:
            self.config_values["game_batch_size"] = 30
        if not "timeout_per_game" in self.config_values:
            self.config_values["timeout_per_game"] = 60
        if not "debug" in self.config_values:
            self.config_values["debug"] = False

        if self.config_values["use_local_cluster"]:
            cluster = LocalCluster(n_workers=self.config_values["n_workers"],
                                    threads_per_worker=1)
        else:
            coiled.create_software_environment(name=self.config_values["software_environment_name"],
                                                pip="requirements.txt")
            cluster = coiled.Cluster(name=self.config_values["cluster_name"],
                                    n_workers=self.config_values["n_workers"],
                                    worker_cpu=self.config_values["worker_cpu"],
                                    worker_memory=str(self.config_values["worker_memory"])
                                                        +"GiB",
                                    scheduler_memory=str(self.config_values["scheduler_memory"])
                                                        +"GiB",
                                    scheduler_cpu=self.config_values["scheduler_cpu"],
                                    software=self.config_values["software_environment_name"])

        self.client = Client(cluster)

    def analyse_games_in_cluster(self, game_list):
        "Find control heatmap for all the games passed, in parallel in a dask cluster"
        game_no = 0
        game_futures = []
        all_game_results = []
        game_master_list = []
        timeout = self.config_values["timeout_per_game"]
        for game in game_list:
            game_master_list.append({"game": game, "game_no": game_no, "timeout": timeout})
            game_no = game_no + 1
        index = 1
        batch = []
        for game in game_master_list:
            batch.append(game)
            if index % self.config_values["game_batch_size"] == 0:
                game_futures = self.client.map(ChessDaskCluster.analyse_game_in_worker, batch)
                all_game_results.extend(self.client.gather(game_futures))
                batch = []
                print("Completed games till " + str(index))
            index = index + 1
        if batch:
            game_futures = self.client.map(ChessDaskCluster.analyse_game_in_worker, batch)
            all_game_results.extend(self.client.gather(game_futures))
        
        if self.config_values["debug"]:
            print("Completed computation, starting image creation")
            with open('results.json', 'w', encoding='utf-8') as file_handle:
                json.dump(all_game_results, file_handle, ensure_ascii=False, indent=4)

        image_futures = self.client.map(ChessImageGenerator.create_gif, all_game_results)
        for image_future in as_completed(image_futures):
            image_data = image_future.result()
            with open(image_data["filename"], 'wb') as file_handle:
                file_handle.write(base64.decodebytes(image_data["bytes"]))
                file_handle.close
            print("Successfully created: " + image_data["filename"])
