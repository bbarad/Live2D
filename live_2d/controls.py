import json

# import processing_functions

# Configuration of live processing settings
with open("latest_run.json") as configfile:
    config = json.load(configfile)

async def initialize(config = config):
    message = {}
    message["type"] = "init"
    message["galleries"] = await generate_gallery_html(config)
    message["settings"] = config["settings"]
    return message

# This should not be async - I don't want a single other thing happening when I write out.
def dump():
    with open("latest_run.json") as jsonfile:
        json.write(config, jsonfile)

async def generate_gallery_html(config, gallery_selected = None):
    return r"<p>Placeholder</p>"
