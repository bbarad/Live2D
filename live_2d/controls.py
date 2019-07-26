import asyncio
import base64
import json
import logging
import os
import sys
import xml.etree.ElementTree as ET

import tornado.template
loader = tornado.template.Loader(".")
# import processing_functions
log = logging.getLogger("live_2d")
def initialize_logger(config):
    log = logging.getLogger("live_2d")
    for handler in log.handlers:
        log.removeHandler(handler)
    # c_handler = logging.StreamHandler()
    # c_format=logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    # c_handler.setFormatter(c_format)
    # c_handler.setLevel(logging.DEBUG)

    filename = os.path.join(config["working_directory"], config["logfile"])
    f_handler = logging.FileHandler(filename, mode='a')
    f_format = logging.Formatter('%(message)s')
    f_handler.setFormatter(f_format)
    f_handler.setLevel(logging.INFO)

    # log.addHandler(c_handler)
    log.addHandler(f_handler)

    return log

# Configuration of live processing settings
def print_config(config):
    print(json.dumps(config, indent=2))

def load_config(filename="latest_run.json"):
    with open(filename) as configfile:
        config = json.load(configfile)
    # print_config(config)
    return config

def create_new_config(warp_folder, working_directory):
    # may want to change this to a template file processed by tornado eventually, easier to keep up to date.
    settingsfile = os.path.join(warp_folder, "previous.settings")
    tree = ET.parse(settingsfile)
    root = tree.getroot()
    try:
        pixel_size_raw = float(root.find("*[@Name='PixelSizeX']").get("Value"))
        bin = float(root.find("Import/*[@Name='BinTimes']").get("Value"))
        pixel_size = pixel_size_raw*(2**bin)
    except:
        log.error("Pixel size could not be extracted.")
        return False

    try:
        mask_radius = root.find("Picking/*[@Name='Diameter']").get("Value")
    except:
        log.error("Mask Radius could not be extracted.")
        return False

    try:
        assert root.find("Picking/*[@Name='DoExport']").get("Value") == "True"
        neural_net = root.find("Picking/*[@Name='ModelPath']").get("Value")
    except:
        log.error("No particles are set to export.")
        return False

    config = {
    "warp_folder": warp_folder,
    "working_directory": working_directory,
    "logfile": "logfile.txt",
    "process_count": 32,
    "settings": {
        "neural_net": neural_net,
        "pixel_size": pixel_size,
        "mask_radius": mask_radius,
        "high_res_initial": "40",
        "high_res_final": "8",
        "run_count_startup": "15",
        "run_count_refine": "5",
        "classification_type": "abinit",
        "particle_count_initial": "50000",
        "particle_count_update": "50000",
        "autocenter": True,
        "automask": False,
        "class_number": "50",
        "particles_per_class": "300"
    },
    "cycles": [],
    "counting": False,
    "job_status": "stopped",
    "force_abinit": False,
    "next_run_new_particles": False,
    "kill_job": False
    }
    return config

def change_warp_directory(warp_folder, config):
    if not os.path.isfile(os.path.join(warp_folder, "previous.settings")):
        log.warn(f"It doesn't look like there is a warp job set up to run in this folder: {warp_folder}. The user-requested folder change has been aborted until a previous.settings file is detected in the folder.")
        return False
    log.info("Found previous.settings file. Preparing to change folders.")
    working_directory = os.path.join(warp_folder, "classification")
    if not os.path.isdir(working_directory):
        os.mkdir(working_directory)
    configfile = os.path.join(working_directory, "latest_run.json")
    new_config = {}
    if os.path.isfile(configfile):
        log.info("Detected an existing config file in that warp folder, so we're loading that one.")
        new_config = load_config(configfile)
        new_config["job_status"] = "stopped"
        new_config["kill_job"] = False
    else:
        log.info("There doesn't appear to be a config yet - generating one.")
        working_directory = os.path.join(warp_folder, "classification")
        new_config = create_new_config(warp_folder, working_directory)
        if not new_config:
            return False
    config.update(new_config)
    return True


async def initialize(config = load_config()):
    message = {}
    message["type"] = "init"
    message["gallery_data"] = await generate_gallery_html(config)
    message["settings"] = await generate_settings_message(config)
    return message

async def generate_job_finished_message(config):
    message = {}
    message["type"] = "settings_update"
    message["settings"] = await generate_settings_message(config)
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
    assert os.path.isfile(os.path.join(config["warp_folder"], f"allparticles_{data['neural_net']}.star"))
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
    return message


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
        try:
            entry["count"] = current_gal["particle_count_per_class"][i+1]
        except:
            entry["count"] = 0

        current_gal["entries"].append(entry)
    string_loader = loader.load("classmodule.html")
    return string_loader.generate(current_gallery=current_gal, classification_list = [(int(i["number"]), i["block_type"], i["particle_count"]) for i in config["cycles"]], cachename=config["warp_folder"][-6:]).decode("utf-8")
