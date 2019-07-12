import base64
import json
import os

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

async def initialize(config = load_config()):
    message = {}
    message["type"] = "init"
    message["gallery_data"] = await generate_gallery_html(config)
    message["settings"] = await generate_settings_message(config)
    return message

# This should not be async - I don't want a single other thing happening when I write out.
def dump_json(config):
    with open("latest_run.json") as jsonfile:
        json.write(config, jsonfile, indent=2)
    with open("{}/latest_run.json".format(config["working_directory"])) as jsonfile:
        json.write(config, jsonfile, indent=2)

async def generate_settings_message(config):
    message = config["settings"]
    message["warp_folder"] = config["warp_folder"]
    message["neural_net"] = config["neural_net"]
    message["job_running"] = config["job_running"]
    return message

async def generate_gallery_html(config, gallery_number_selected = None):
    current_gal = None
    if gallery_number_selected:
        for gallery in config["galleries"]:
            if gallery["number"] == gallery_number_selected:
                current_gal = gallery
    if not current_gal:
        current_gal = config["galleries"][-1]
    current_gal["entries"] = []
    for i in range(current_gal["class_count"]):
        entry = {}
        entry["name"] = "Class {}".format(i+1)
        filename = os.path.join(config["working_directory"], current_gal["name"], "{}.png".format(i+1))
        with open(filename, "rb") as imgfile:
            entry["data"] = base64.b64encode(imgfile.read())
            print(entry["data"])
        current_gal["entries"].append(entry)
    string_loader = loader.load("classmodule.html")
    return string_loader.generate(current_gallery=current_gal, classification_list = config["galleries"]).decode("utf-8")
