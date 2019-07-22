import asyncio
import base64
import json
import logging as log
import os
import sys

import tornado.template
loader = tornado.template.Loader(".")
# import processing_functions

# Configuration of live processing settings
def print_config(config):
    print(json.dumps(config, indent=2))

def load_config(filename="latest_run.json"):
    with open(filename) as configfile:
        config = json.load(configfile)
    # print_config(config)
    return config

async def change_warp_directory(folder_name):
    return {"type": "alert", "data": "Changing warp directory is not yet supported!"}

async def initialize(config = load_config()):
    message = {}
    message["type"] = "init"
    message["gallery_data"] = await generate_gallery_html(config)
    message["settings"] = await generate_settings_message(config)
    return message

async def generate_job_finished_message(config = load_config()):
    message = {}
    message["type"] = "settings_update"
    message["settings"] = await generate_settings_message(config)
    print(message)
    return message

async def get_new_gallery(config, data):
    message = {}
    message["type"] = "gallery_update"
    message["gallery_data"] = await generate_gallery_html(config, gallery_number_selected = int(data["gallery_number"]))
    return message

# This should not be async - I don't want a single other thing happening when I write out.
def dump_json(config):
    with open(os.path.join(sys.path[0],"latest_run.json"), "w") as jsonfile:
        json.dump(config, jsonfile, indent=2)
    with open(os.path.join(config["working_directory"], "latest_run.json"), "w") as jsonfile:
        json.dump(config, jsonfile, indent=2)

async def update_settings(config, data):
    if not data["neural_net"] == config["settings"]["neural_net"]:
        config["settings"]["neural_net"] = data["neural_net"]
        config["force_abinit"] = True
        config["next_run_new_particles"] = True
    for key in config["settings"].keys():
        try:
            config["settings"][key] = data[key]
        except:
            log.info("Setting not found to update: {}".format(key))
    dump_json(config)
    message = {}
    message["type"] = "settings_update"
    message["settings"] = await generate_settings_message(config)
    return message

async def generate_settings_message(config):
    message = {}
    message["settings"] = config["settings"]
    message["warp_folder"] = config["warp_folder"]
    message["job_status"] = config["job_status"]
    message["force_abinit"] = config["force_abinit"]
    print(message)
    return message

async def initialize_new_settings(config, warp_directory):
    return config

async def generate_gallery_html(config, gallery_number_selected = -1):
    # Catch new cycles
    if not config["cycles"]:
        return "<h3 class='text-center my-2'>New Classes Will Populate in This Tab</h3>"
    current_gal = {}
    if not gallery_number_selected == -1:
        for cycle in config["cycles"]:
            if cycle["number"] == gallery_number_selected:
                current_gal["name"] = cycle["name"]
                current_gal["number"] = int(cycle["number"])
                current_gal["class_count"] = int(cycle["settings"]["class_number"])
                current_gal["particle_count"] = cycle["particle_count"]
                current_gal["high_res_limit"] = cycle["high_res_limit"]
                current_gal["block_type"] = cycle["block_type"]
                current_gal["time"] = cycle["time"]
                try:
                    current_gal["particle_count_per_class"] = cycle["particle_count_per_class"]
                except:
                    current_gal["particle_count_per_class"] = ["Not Recorded"]*(current_gal["class_count"]+1)
    # Catch nonexistent number or non-supplied number and return the latest class.
    if not "number" in current_gal:
        cycle = config["cycles"][-1]
        current_gal["name"] = cycle["name"]
        current_gal["number"] = int(cycle["number"])
        current_gal["class_count"] = int(cycle["settings"]["class_number"])
        current_gal["particle_count"] = cycle["particle_count"]
        current_gal["high_res_limit"] = cycle["high_res_limit"]
        current_gal["block_type"] = cycle["block_type"]
        current_gal["time"] = cycle["time"]
        try:
            current_gal["particle_count_per_class"] = cycle["particle_count_per_class"]
        except:
            current_gal["particle_count_per_class"] = ["Not Recorded"]*(current_gal["class_count"]+1)
    current_gal["entries"] = []
    for i in range(current_gal["class_count"]):
        entry = {}
        entry["name"] = "Class {}".format(i+1)
        entry["url"] = os.path.join("/gallery/", current_gal["name"], "{}.png".format(i+1))

        entry["count"] = current_gal["particle_count_per_class"][i+1]

        current_gal["entries"].append(entry)
    string_loader = loader.load("classmodule.html")
    return string_loader.generate(current_gallery=current_gal, classification_list = [(int(i["number"]), i["block_type"], i["particle_count"]) for i in config["cycles"]]).decode("utf-8")
