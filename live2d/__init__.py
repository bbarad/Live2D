#! /usr/bin/env python

#
# Copyright 2019 Genentech Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Live 2D classification
===================================
Startup: ``python __init__.py --port=8181``

Operate a websocket-driven asynchronous web server to perform 2D classification
of single particle electron microscopy data using cisTEM_ in concert with motion correction, CTF estimation, and particle picking from Warp_.

Uses a subclass of :py:class:`tornado.websocket.WebSocketHandler` to pass messages between server and client. Server receives json-formatted messages of the format ``{"command": command_type, "data": arbitrary_data}``

Server sends json-formatted messages with the format ``{"type": command_type, OTHER_HEADER: other_data, ...}``

**Documentation**:``../readme.md`` contains an extended user guide. ``../docs/`` contains technical documentation.

Author: Benjamin Barad <benjamin.barad@gmail.com>/<baradb@gene.com>

.. _Warp: http://www.warpem.com/warp/
.. _cisTEM: https://cistem.org/
"""

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import datetime
from functools import partial
import json
import logging
import multiprocessing
import os
import shutil
import sys
import time

from tornado.httpserver import HTTPServer
import tornado.ioloop
from tornado.options import define, parse_command_line, OptionParser
from tornado.web import Application, RequestHandler, StaticFileHandler
from tornado.websocket import WebSocketHandler, WebSocketClosedError
import uvloop

from .controls import initialize, load_config, get_new_gallery, dump_json, update_settings, generate_job_finished_message, change_warp_directory, generate_settings_message, initialize_logger, update_config_from_warp
from . import processing_functions

def define_options():
    options = OptionParser()
    options.define('port', default=8181, type=int, help='port to listen on')
    options.define('microscope_name', default="", type=str, help='Name of the microscope')
    options.define('warp_prefix', help="Parent folder of all warp folders in the user facility's organization scheme.", group="folders")
    options.define('warp_suffix', default=None, help="Child of the session-specific folder where warp output will be kept. Depends on workflow.", type=str, group="folders")
    options.define('live2d_prefix', help="Parent where live2d output folders will be generated. If this is the same as the warp_prefix, a live_2d suffix is recommended.", group="folders")
    options.define('live2d_suffix', default=None, help="Child of the session-specific folder where live2d output will be saved.", type=str, group="folders")
    options.define('listening_period_ms', default=120000, type=int, help='How long to wait between automatic job trigger checks, in ms')
    options.define('tail_log_period_ms', default=15000, type=int, help='How long to wait between sending the latest log lines to the clients, in ms')
    options.define('websocket_ping_interval', default=30, type=int, help='Period between ping pongs to keep connections alive, in seconds', group='settings')
    options.define('process_pool_size', default=32, type=int, help='Total number of logical processors to use for multi-process refine2d jobs')
    # Settings related to actually operating the webpage
    options.parse_config_file(os.path.join(config_folder, "server_settings.conf"), final=False)
    options.parse_command_line()
    return options

install_directory = os.path.realpath(os.path.dirname(__file__))
starting_directory = os.path.realpath(sys.path[0])
stack_label = "combined_stack"
clients = set()
class_path_dict = {}


class SocketHandler(WebSocketHandler):
    """Primary Web Server control class - every new client will make initialize of these classes.
    Extends :py:class:`tornado.websocket.WebSocketHandler`
    """
    def open(self):
        """Adds new client to a global clients set when socket is opened."""
        # message_data = initialize_data()
        clients.add(self)
        print("Socket Opened from {}".format(self.request.remote_ip))


    async def on_message(self, message):
        """
        Receives json-formatted messages of the format {"command": command_type, "data": arbitrary_data}

        All messages returned are json-formatted messages with the format ``{"type": command_type, OTHER_HEADER: other_data, ...}``

        Args:
            message (stream object): JSON-encoded message from a client.
        """
        message_json = json.loads(message)
        type = message_json['command']
        data = message_json['data']
        return_data = "Dummy Return"
        if type == 'start_job':
            # Lots of server-side validation that is mirrored client-side.
            print(config["job_status"])
            if config['job_status'] == "running":
                return_data = {"type":"alert", "data": "You tried to run a job when a job is already running"}
                await self.write_message(return_data)
            elif config['job_status'] == "killed":
                return_data = {"type":"alert", "data": "The job has been killed and will finish at the end of this cycle, which may take a few minutes. Once it is stopped you can begin again."}
                await self.write_message(return_data)
                # TODO: offer to hard kill the job, and warn user that this may significantly impact project directory.
            elif config['job_status'] == "stopped" or config['job_status'] == "listening":
                config["job_status"] = "running"
                return_data = await update_settings(config, data)
                await message_all_clients(return_data)
                return_data_2 = {"type": "job_started"}
                await self.write_message(return_data_2)
                loop = tornado.ioloop.IOLoop.current()
                loop.add_callback(execute_job_loop, config)

            else:
                live2dlog.info("Malformed job status - didn't start job")
            pass
        elif type == "listen":
            if config["job_status"] == "stopped":
                config["job_status"]="listening"
                config["counting"] = False
                return_data = await update_settings(config, data)
                await self.write_message({"type":"alert","data":"Waiting for new particles"})
                await message_all_clients(return_data)

        elif type == 'kill_job':
            # WAIT FOR COUNTING TO FINISH IN CASE A JOB FAILS TO FINISH.
            while config["counting"]:
                asyncio.sleep(1)
            if config["job_status"] == "running":
                config["kill_job"] = True # This makes me happy.
                config["job_status"] = "killed"
                await message_all_clients({"type": "kill_received"})
            elif config["job_status"] == "listening" and not config["counting"]:
                config["job_status"] = "killed"
                await message_all_clients({"type": "kill_received"})
                live2dlog.info("Importing newest particles before halting")
                assert update_config_from_warp(config)
                total_particles =  await tornado.ioloop.IOLoop.current().run_in_executor(executor,partial(processing_functions.import_new_particles,stack_label=stack_label, warp_folder = config["warp_folder"], warp_star_filename="allparticles_{}.star".format(config["settings"]["neural_net"]), working_directory = config["working_directory"], new_net = config["next_run_new_particles"])) #await
                config["job_status"] = "stopped"
                message = {}
                message["type"] = "settings_update"
                message["settings"] = await generate_settings_message(config)
                print(message)
                await message_all_clients(message)

        elif type == 'get_gallery':
            print(data)
            return_data = await get_new_gallery(config, data)
            await self.write_message(return_data)
        elif type == 'initialize':
            return_data = await initialize(config, options.microscope_name)
            await self.write_message(return_data)
            pass
        elif type == 'change_directory':
            print(data)
            if data == None:
                return
            if options.warp_suffix:
                new_warp_folder = os.path.join(options.warp_prefix, data, options.warp_suffix)
            else:
                new_warp_folder = os.path.join(options.warp_prefix, data)
            print(new_warp_folder)
            if options.live2d_suffix:
                new_working_folder = os.path.join(options.live2d_prefix, data, options.live2d_suffix)
            else:
                new_working_folder = os.path.join(options.live2d_prefix, data)
            print(new_working_folder)
            config_accepted = change_warp_directory(new_warp_folder, new_working_folder, config)
            live2dlog.debug(f"Trying to change to folder {data}")
            if not config_accepted:
                await self.write_message({"type": "alert", "data": f"The folder {new_warp_folder} you selected doesn't have a previous.settings file from a warp job, so the change was aborted. Check your session name, and check whether your warp_prefix and warp_suffix are set up correctly."})
            else:
                initialize_logger(config)
                live2dlog.info(f"Moving to warp directory: {config['warp_folder']}")
                return_data = await initialize(config)
                class_path_dict["path"] = os.path.join(config["working_directory"], "class_images")
                await message_all_clients({"type":"alert", "data": "Changing warp directory"})
                await message_all_clients(return_data)
                dump_json(config)
        elif type == 'update_settings':
            if (config["job_status"] == 'stopped' or config["job_status"] == 'listening'):
                await self.write_message({"type":"alert", "data":"Updating Settings"})
                return_data = await update_settings(config, data)
                await message_all_clients(return_data)
            else:
                return_data = {"type":"alert", "data": "You can't update settings with jobs running or waiting to kill."}
                await self.write_message(return_data)
        else:
            print(message)
            await self.write_message({"type":"alert", "data": "The backend doesn't understand that message"})
            pass

    def on_close(self):
        """Remove sockets from the clients list to minimize errors."""
        clients.remove(self)
        print("Socket Closed from {}".format(self.request.remote_ip))

class IndexHandler(RequestHandler):
    """Core class to respond to new clients."""
    def get(self):
        """Minimal handler for setting up the very first connection via an HTTP request before setting up the websocket connection for all future interactions."""
        self.render("index.html")

# class GalleryHandler(RequestHandler):
#     def get(self):
#         pass
async def tail_log(config, clients = None, line_count = 1000):
    """Grab the last 1000 lines of the logfile (set in config) via a subprocess call, then send it as text to the console on the webapp.

    Args:
        config (dict): the global config object
        clients (dict): dictionary of websockethandler instances that are open, to which the log will be sent.
        line_count (int): number of lines to tail."""
    logfile = os.path.join(config["working_directory"], config["logfile"])
    out = await asyncio.create_subprocess_shell("/usr/bin/tail -n {} {}".format(line_count, logfile), shell=True, stdout=asyncio.subprocess.PIPE)
    stdout,_ = await out.communicate()
    console_message = {}
    console_message["type"] = "console_update"
    console_message["data"] = stdout.decode("utf-8")
    await message_all_clients(console_message)

async def listen_for_particles(config, clients):
    """Measure the number of particles in the ``allparticles_$NEURALNET.star`` stack and compare it to the last classification cycle to determine how many new particles are present. If the number is greater than the user-set thresholds, send out a classification job.
    Args:
        config (dict): the global config object
        clients (dict): dictionary of :py:class:`SocketHandler` instances that are open, to which the log will be sent.
    """
    print("Listening for Particles?")
    if not config["job_status"] == "listening":
        print("not set to listening")
        config["counting"] = False
        return
    if config["counting"]:
        print("listen job hasn't returned yet...")
        return
    config["counting"] = True
    if config["cycles"]:
        particle_count_to_fire = int(config["settings"]["particle_count_update"])
        current_particle_count = config["cycles"][-1]["particle_count"]
    else:
        particle_count_to_fire = int(config["settings"]["particle_count_initial"])
        current_particle_count = 0
    try:
        warp_stack_filename = os.path.join(config["warp_folder"], "allparticles_{}.star".format(config["settings"]["neural_net"]))
        new_particle_count = await processing_functions.particle_count_difference(warp_stack_filename, current_particle_count)
        live2dlog.info(f"New Particles Detected: {new_particle_count}")
        print(new_particle_count)
        if new_particle_count >= particle_count_to_fire:
            live2dlog.info(f"Job triggering automatically as {new_particle_count} particles have been added by Warp since last import.")
            config["job_status"] = "running"
            message = {}
            message["type"] = "settings_update"
            message["settings"] = await generate_settings_message(config)
            await message_all_clients(message)
            loop = tornado.ioloop.IOLoop.current()
            loop.add_callback(execute_job_loop, config)
        config["counting"] = False
    except Exception:
        live2dlog.error("Automated Particle Counting and Job Submission Failed")
        config["counting"] = False
        raise



async def execute_job_loop(config):
    """The main job loop.

    Combines new particles picked by warp into a single growing stack iteratively, then sends out a series of refine2d and merge2d jobs based on the settings entries of the config object. Uses multiprocessing to generate pools to split jobs into as many processes as are set by the process_count setting. Sends out processpoolexecutors where possible (and threadpoolexecutors elsewhere) to split off each individual cisTEM run from the main thread to keep the webapp responsive.

    Webapp slowdowns still frequently happen at the beginning and end of cisTEM jobs - I believe these are actually related to disk and memory IO limitations, as cisTEM can hit those hard.

    Results are written to the config classifications entry as they come in, and the config is written to file at the end of each cycle of classification.

    Args:
        config (dict): the global configuration file.

    """
    # log = logging.getLogger("live_2d")
    # print(options.port)
    try:
        loop = tornado.ioloop.IOLoop.current()
        process_count = options.process_pool_size
        live2dlog.info("============================")
        live2dlog.info("Beginning Classification Job")
        live2dlog.info("============================")
        # Check old classes:
        # live2dlog.info("checking classes")
        if not config["cycles"]:
            # live2dlog.info("Since no previous classes were found, this is an ab initio run")
            previous_classes_bool = False
            recent_class = "cycle_0"
            start_cycle_number = 0
            config["settings"]["classification_type"] = "abinit"
        else:
            config["cycles"].sort(key=lambda x: int(x["number"]))
            previous_classes_bool = True
            recent_class = config["cycles"][-1]["name"]
            start_cycle_number = int(config["cycles"][-1]["number"])
        # Import particles
        # live2dlog.info("importing particles")
        assert update_config_from_warp(config)
        total_particles =  await loop.run_in_executor(executor,partial(processing_functions.import_new_particles,stack_label=stack_label, warp_folder = config["warp_folder"], warp_star_filename="allparticles_{}.star".format(config["settings"]["neural_net"]), working_directory = config["working_directory"], new_net = config["next_run_new_particles"])) #await

        config["next_run_new_particles"] = False
        dump_json(config)
        # Generate new classes
        if config["force_abinit"]:
            live2dlog.info("Classification type choice is disregarded because ab initio classification is required for these user settings.")
            config["settings"]["classification_type"] = "abinit"
            config["force_abinit"] = False
        if config["settings"]["classification_type"] == "abinit":
            merge_star = False
        else:
            merge_star = True
        if previous_classes_bool and not merge_star:
            start_cycle_number += 1
        live2dlog.info(f"The classification type for this run will be {config['settings']['classification_type']}.")
        new_star_file = await loop.run_in_executor(executor, partial(processing_functions.generate_star_file,stack_label=stack_label, working_directory = config["working_directory"], previous_classes_bool = previous_classes_bool, merge_star=merge_star, recent_class=recent_class, start_cycle_number=start_cycle_number))
        particle_count, particles_per_process, class_fraction = await loop.run_in_executor(executor, partial(processing_functions.calculate_particle_statistics,filename=os.path.join(config["working_directory"],new_star_file), class_number=int(config["settings"]["class_number"]), particles_per_class=int(config["settings"]["particles_per_class"]), process_count=process_count))
        if config["settings"]["classification_type"] == "seeded":
            class_fraction = 1.0
        # Generate new classes!
        if config["settings"]["classification_type"] == "abinit" and not config["kill_job"]:
            live2dlog.info("============================")
            live2dlog.info("Preparing Initial 2D Classes")
            live2dlog.info("============================")
            await loop.run_in_executor(executor, partial(processing_functions.generate_new_classes, start_cycle_number=start_cycle_number, class_number=int(config["settings"]["class_number"]), input_stack="{}.mrcs".format(stack_label), pixel_size=float(config["settings"]["pixel_size"]), low_res=300, high_res=int(config["settings"]["high_res_initial"]), new_star_file=new_star_file, working_directory = config["working_directory"],automask = config["settings"]["automask"], autocenter=config["settings"]["autocenter"]))

            await loop.run_in_executor(executor, processing_functions.make_photos,"cycle_{}".format(start_cycle_number),config["working_directory"])
            classified_count_per_class = [0]*(int(config["settings"]["class_number"])+1) # All classes are empty for the initialization!
            new_cycle = {"name": "cycle_{}".format(start_cycle_number), "number": start_cycle_number, "settings": config["settings"], "high_res_limit": int(config["settings"]["high_res_initial"]), "block_type": "random_seed", "cycle_number_in_block": 1, "time": str(datetime.datetime.now()), "process_count": 1, "particle_count": total_particles, "particle_count_per_class": classified_count_per_class, "fraction_used": class_fraction}
            config["cycles"].append(new_cycle)
            dump_json(config)
            return_data = await get_new_gallery(config, {"gallery_number": start_cycle_number})
            live2dlog.info("Sending new gallery to clients")
            await message_all_clients(return_data)
        # Startup Cycles
        if not config["settings"]["classification_type"] == "refine":
            resolution_cycle_count = int(config["settings"]["run_count_startup"])
            live2dlog.info("=====================================")
            live2dlog.info("Beginning Iterative 2D Classification")
            live2dlog.info("=====================================")
            live2dlog.info("Of the total {} particles, {:.0f}% will be classified into {} classes".format(particle_count, class_fraction*100, config["settings"]["class_number"]))
            live2dlog.info("Classification will begin at {}Å and step up to {}Å resolution over {} iterative cycles of classification".format(config["settings"]["high_res_initial"], config["settings"]["high_res_final"], resolution_cycle_count))
            live2dlog.info("{0} particles per process will be classified by {1} processes.".format(particles_per_process*class_fraction, process_count))
            for cycle_number in range(resolution_cycle_count):
                if config["kill_job"]:
                    live2dlog.info("Job Killed - Cycle Skipped")
                    continue
                low_res_limit = 300
                high_res_limit = int(config["settings"]["high_res_initial"])-(((int(config["settings"]["high_res_initial"])-int(config["settings"]["high_res_final"]))/(resolution_cycle_count-1))*cycle_number)
                filename_number = cycle_number + start_cycle_number
                live2dlog.info("===================================================")
                live2dlog.info("Sending a new classification job out for processing")
                live2dlog.info("===================================================")
                live2dlog.info("High Res Limit: {0:.2}".format(high_res_limit))
                live2dlog.info("Fraction of Particles: {0:.2}".format(class_fraction))
                live2dlog.info(f"Number of Particles: {particle_count}")
                live2dlog.info(f"Dispatching job at {datetime.datetime.now()}")
                pool = multiprocessing.Pool(processes=process_count)
                refine_job = partial(processing_functions.refine_2d_subjob, round=filename_number, input_star_filename = new_star_file, input_stack="{}.mrcs".format(stack_label), particles_per_process=particles_per_process, low_res_limit=low_res_limit, high_res_limit=high_res_limit, class_fraction=class_fraction, particle_count=particle_count, pixel_size=float(config["settings"]["pixel_size"]), angular_search_step=15, max_search_range=49.5, process_count=process_count,working_directory = config["working_directory"],automask = config["settings"]["automask"], autocenter=config["settings"]["autocenter"])
                results_list = await loop.run_in_executor(executor2, pool.map, refine_job, range(process_count))

                pool.close()
                live2dlog.info(results_list[0].decode('utf-8'))
                await loop.run_in_executor(executor,partial(processing_functions.merge_2d_subjob,filename_number, config["working_directory"], process_count=process_count))
                await loop.run_in_executor(executor,processing_functions.make_photos,"cycle_{}".format(filename_number+1),config["working_directory"])
                new_star_file = await loop.run_in_executor(executor, partial(processing_functions.merge_star_files,filename_number, process_count=process_count, working_directory = config["working_directory"]))
                classified_count_per_class = await loop.run_in_executor(executor, processing_functions.count_particles_per_class, new_star_file)
                new_cycle = {"name": "cycle_{}".format(filename_number+1), "number": filename_number+1, "settings": config["settings"], "high_res_limit": high_res_limit, "block_type": "startup", "cycle_number_in_block": cycle_number+1, "time": str(datetime.datetime.now()), "process_count": process_count, "particle_count": total_particles, "particle_count_per_class":classified_count_per_class, "fraction_used": class_fraction}
                config["cycles"].append(new_cycle)
                dump_json(config)
                return_data = await get_new_gallery(config, {"gallery_number": filename_number+1})
                live2dlog.info("Sending new gallery to clients")
                await message_all_clients(return_data)

                ## IMPORT NEW PARTICLES
                live2dlog.info("Getting new particles between jobs")
                assert update_config_from_warp(config)
                if config["next_run_new_particles"] == True:
                    live2dlog.info("Complete particle reimport is needed and will be deferred until the next full job trigger")
                    continue
                total_particles =  await loop.run_in_executor(executor,partial(processing_functions.import_new_particles,stack_label=stack_label, warp_folder = config["warp_folder"], warp_star_filename="allparticles_{}.star".format(config["settings"]["neural_net"]), working_directory = config["working_directory"], new_net = config["next_run_new_particles"])) #await
                dump_json(config)
                new_star_file = await loop.run_in_executor(executor, partial(processing_functions.generate_star_file,stack_label=stack_label, working_directory = config["working_directory"], previous_classes_bool = True, merge_star=True, recent_class=config["cycles"][-1]["name"], start_cycle_number=start_cycle_number))
                particle_count, particles_per_process, class_fraction = await loop.run_in_executor(executor, partial(processing_functions.calculate_particle_statistics,filename=os.path.join(config["working_directory"],new_star_file), class_number=int(config["settings"]["class_number"]), particles_per_class=int(config["settings"]["particles_per_class"]), process_count=process_count))
                if config["settings"]["classification_type"] == "seeded":
                    class_fraction = 1.0

            start_cycle_number = start_cycle_number + resolution_cycle_count

        # Refinement Cycles
        refinement_cycle_count = int(config["settings"]["run_count_refine"])
        class_fraction = 1.0
        live2dlog.info("==========================================================")
        live2dlog.info("2D class refinement at final resolution with all particles")
        live2dlog.info("==========================================================")
        live2dlog.info("All {} particles will be classified into {} classes at resolution {}Å".format(particle_count, config["settings"]["class_number"], config["settings"]["high_res_final"]))
        live2dlog.info("{0} particles per process will be classified by {1} processes.".format(particles_per_process, config["process_count"]))
        for cycle_number in range(refinement_cycle_count):
            if config["kill_job"]:
                live2dlog.info("Job Killed - Cycle Skipped")
                continue
            live2dlog.info("===================================================")
            live2dlog.info("Sending a new classification job out for processing")
            live2dlog.info("===================================================")
            low_res_limit = 300
            high_res_limit = int(config["settings"]["high_res_final"])
            filename_number = cycle_number + start_cycle_number
            live2dlog.info("High Res Limit: {0}".format(high_res_limit))
            live2dlog.info("Fraction of Particles: {0:.2}".format(class_fraction))
            live2dlog.info(f"Number of Particles: {particle_count}")
            live2dlog.info(f"Dispatching job at {datetime.datetime.now()}")
            pool = multiprocessing.Pool(processes=int(config["process_count"]))
            refine_job = partial(processing_functions.refine_2d_subjob, round=filename_number, input_star_filename = new_star_file, input_stack="{}.mrcs".format(stack_label), particles_per_process=particles_per_process, low_res_limit=low_res_limit, high_res_limit=high_res_limit, class_fraction=class_fraction, particle_count=particle_count, pixel_size=float(config["settings"]["pixel_size"]), angular_search_step=15, max_search_range=49.5, process_count=process_count, working_directory = config["working_directory"],automask = config["settings"]["automask"], autocenter=config["settings"]["autocenter"])
            results_list = await loop.run_in_executor(executor2,pool.map,refine_job, range(process_count))
            pool.close()
            live2dlog.info(results_list[30].decode('utf-8'))
            await loop.run_in_executor(executor, partial(processing_functions.merge_2d_subjob, filename_number,config["working_directory"], process_count=int(config["process_count"])))
            await loop.run_in_executor(executor, processing_functions.make_photos, "cycle_{}".format(filename_number+1),config["working_directory"])
            new_star_file = await loop.run_in_executor(executor, partial(processing_functions.merge_star_files,filename_number, process_count=process_count, working_directory = config["working_directory"]))
            classified_count_per_class = await loop.run_in_executor(executor, processing_functions.count_particles_per_class, new_star_file)
            new_cycle = {"name": "cycle_{}".format(filename_number+1), "number": filename_number+1, "settings": config["settings"], "high_res_limit": high_res_limit, "block_type": "refinement", "cycle_number_in_block": cycle_number+1, "time": str(datetime.datetime.now()), "process_count": process_count, "particle_count": total_particles, "particle_count_per_class": classified_count_per_class, "fraction_used": class_fraction}
            config["cycles"].append(new_cycle)
            dump_json(config)
            return_data = await get_new_gallery(config, {"gallery_number": filename_number+1})
            live2dlog.info("Sending new gallery to clients")
            await message_all_clients(return_data)

            ## IMPORT NEW PARTICLES
            live2dlog.info("Getting new particles between jobs")
            assert update_config_from_warp(config)
            if config["next_run_new_particles"] == True:
                live2dlog.info("Complete particle reimport is needed and will be deferred until the next full job trigger")
                continue
            total_particles =  await loop.run_in_executor(executor,partial(processing_functions.import_new_particles,stack_label=stack_label, warp_folder = config["warp_folder"], warp_star_filename="allparticles_{}.star".format(config["settings"]["neural_net"]), working_directory = config["working_directory"], new_net = config["next_run_new_particles"])) #await
            dump_json(config)
            new_star_file = await loop.run_in_executor(executor, partial(processing_functions.generate_star_file,stack_label=stack_label, working_directory = config["working_directory"], previous_classes_bool = True, merge_star=True, recent_class=config["cycles"][-1]["name"], start_cycle_number=start_cycle_number))
            particle_count, particles_per_process, _ = await loop.run_in_executor(executor, partial(processing_functions.calculate_particle_statistics,filename=os.path.join(config["working_directory"],new_star_file), class_number=int(config["settings"]["class_number"]), particles_per_class=int(config["settings"]["particles_per_class"]), process_count=process_count))
            class_fraction = 1.0

        if config["settings"]["classification_type"] == "abinit":
            config["settings"]["classification_type"] = "seeded"
        if config["kill_job"]:
            config["job_status"] = "stopped"
            config["kill_job"] = False
        else:
            config["job_status"] = "listening"
            config["kill_job"] = False
        live2dlog.info("Done with job - sending result to all clients")
        return_message = await generate_job_finished_message(config)
        await message_all_clients(return_message)
    except Exception:
        live2dlog.exception("Job Loop Failed")
        if config["kill_job"]:
            config["job_status"] = "stopped"
            config["kill_job"] = False
        else:
            config["job_status"] = "listening"
            config["kill_job"] = False
        raise

async def message_all_clients(message, clients = clients):
    """
    Send a message to all open clients, and close any that respond with closed state.

    Args:
        message (str or dict): a websocket-friendly message.
        clients (set): a set of websockethandler instances that should represent every open session.
    """
    for client in list(clients):
        try:
            client.write_message(message)
        except WebSocketClosedError:
            logging.warn(f"Could not write a message to client {client} due to a WebSocketClosedError. Removing that client from the client list.")
            clients.remove(client)



def main():
    """Construct and serve the tornado app"""
    global config_folder
    config_folder = os.path.join(os.path.expanduser("~"), ".live2d")
    if not os.path.exists(config_folder):
        print(f"Didn't find a .live2d config folder. Making one now at {config_folder}.")
        os.mkdir(config_folder)
    server_config = os.path.join(config_folder, "server_settings.conf")
    if not os.path.exists(server_config):
        print(f"Didn't find a server_settings.conf file. Copying over the default one to the .live2d config folder now ({server_config}). Modify this script with desired paths and rerun.")
        shutil.copyfile(os.path.join(install_directory, "server_settings.conf"), server_config)
        return
    latest_run = os.path.join(config_folder, "latest_run.json")
    if not os.path.exists(latest_run):
        print(f"Didn't find a latest_settings.json file in the config folder. Copying over the default one to the .live2d config folder now ({latest_run}).")
        shutil.copyfile(os.path.join(install_directory, "latest_run.json.template"), latest_run)

    global config
    config = load_config(latest_run)
    config["job_status"] = "stopped"
    config["kill_job"] = False
    config["counting"] = False
    class_path_dict["path"] = os.path.join(config["working_directory"], "class_images")
    global live2dlog
    live2dlog = initialize_logger(config)

    global options
    options = define_options()
    uvloop.install()
    app=Application([(r"/", IndexHandler),
        (r"/static/(.*)", StaticFileHandler, {"path": os.path.join(os.path.dirname(__file__), "static")}),
        (r"/gallery/(.*)", StaticFileHandler, class_path_dict),
        (r"/websocket", SocketHandler),
        ],**options.group_dict('settings'))
    app.listen(options.port)
    print('Listening on http://localhost:%i' % options.port)

    global executor
    global executor2
    executor = ProcessPoolExecutor(max_workers=1)
    executor2 = ThreadPoolExecutor(max_workers=1)

    tailed_callback = tornado.ioloop.PeriodicCallback(lambda: tail_log(config, clients), options.tail_log_period_ms)
    tailed_callback.start()

    listening_callback = tornado.ioloop.PeriodicCallback(lambda: listen_for_particles(config, clients), options.listening_period_ms)
    listening_callback.start()

    tornado.ioloop.IOLoop.current().start()



if __name__ == "__main__":
    print("executing main")
    main()
