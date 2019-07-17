import asyncio
from concurrent.futures import ThreadPoolExecutor
import datetime
from functools import partial
import json
import logging as log
import multiprocessing
import os
import sys

from tornado.httpserver import HTTPServer
import tornado.ioloop
from tornado.options import define, options, parse_command_line
from tornado.web import Application, RequestHandler, StaticFileHandler
from tornado.websocket import WebSocketHandler
import uvloop

from controls import initialize, load_config, get_new_gallery, update_settings, dump_json
import processing_functions

import socket_handlers
define('port', default=8181, help='port to listen on')
# Settings related to actually operating the webpage
settings = {
    "autoreload":"True",
    "websocket_ping_interval": 30,
}
starting_directory = os.getcwd()
config = load_config(os.path.join(sys.path[0],'latest_run.json'))
config["job_running"] = False
clients = set()

class_path_dict = {"path": os.path.join(config["working_directory"], "class_images")}

class SocketHandler(WebSocketHandler):
    def open(self):
        # message_data = initialize_data()
        clients.add(self)
        print("Socket Opened from {}".format(self.request.remote_ip))


    async def on_message(self, message):
        message_json = json.loads(message)
        type = message_json['command']
        data = message_json['data']
        return_data = "Dummy Return"
        if type == 'update_settings':
            return_data = await update_settings(config, data)
            for con in clients:
                con.write_message(return_data)
        elif type == 'start_job':
            print(config["job_running"])
            if config['job_running']:
                return_data = {"type":"alert", "data": "You tried to run a job when a job is already running"}
                for con in clients:
                    con.write_message(return_data)
            else:
                return_data = {"type": "job_started"}
                config["job_running"] = True
                for con in clients:
                    con.write_message(return_data)
                loop = tornado.ioloop.IOLoop.current()
                loop.spawn_callback(execute_job_loop, config)

            pass
        elif type == 'stop_job':
            pass
        elif type == 'get_gallery':
            print(data)
            return_data = await get_new_gallery(config, data)
            self.write_message(return_data)
        elif type == 'initialize':
            return_data = await initialize(config)
            self.write_message(return_data)
            pass
        else:
            print(message)
            pass

    def on_close(self):
        clients.remove(self)
        print("Socket Closed from {}".format(self.request.remote_ip))

class IndexHandler(RequestHandler):
    def get(self):
        self.render("index.html")

# class GalleryHandler(RequestHandler):
#     def get(self):
#         pass
async def tail_log(config, clients = None, line_count = 1000):
    logfile = os.path.join(config["working_directory"], config["logfile"])
    out = await asyncio.create_subprocess_shell("/usr/bin/tail -n {} {}".format(line_count, logfile), shell=True, stdout=asyncio.subprocess.PIPE)
    stdout,_ = await out.communicate()
    console_message = {}
    console_message["type"] = "console_update"
    console_message["data"] = stdout.decode("utf-8")
    for client in clients:
        # print("Client: {}".format(client))
        client.write_message(console_message)

async def execute_job_loop(config):
    """The main job loop. Should really only be run from a ThreadPoolExecutor or you will block the app for a LONG time."""
    loop = tornado.ioloop.IOLoop.current()
    executor = ThreadPoolExecutor(max_workers=1)
    log.basicConfig(filename=os.path.join(config["working_directory"], config["logfile"]), filemode='a', format='%(message)s', level=log.DEBUG)
    process_count = int(config["process_count"])
    working_directory = config["working_directory"]
    os.chdir(working_directory)

    # Check old classes:
    log.info("checking classes")
    stack_label = "combined_stack"
    if not config["cycles"]:
        log.info("Since no previous classes were found, this is an ab initio run")
        previous_classes_bool = False
        recent_class = "cycle_0"
        start_cycle_number = 0
        config["settings"]["classification_type"] = "abinit"
    else:
        config["cycles"].sort(key=lambda x: int(x["number"]))
        previous_classes_bool = True
        recent_class = config["cycles"][-1]["name"]
        start_cycle_number = int(config["cycles"][-1]["number"])
    log.info(start_cycle_number)
    # Import particles
    log.info("importing particles")
    total_particles =  await loop.run_in_executor(executor,partial(processing_functions.import_new_particles,stack_label=stack_label, warp_folder = config["warp_folder"], warp_star_filename="allparticles_{}.star".format(config["neural_net"]), working_directory = config["working_directory"], new_net = config["next_run_new_particles"]))
    config["next_run_new_particles"] = False
    # Generate new classes
    if config["force_abinit"]:
        config["settings"]["classification_type"] = "abinit"
        config["force_abinit"] = False
    if config["settings"]["classification_type"] == "abinit":
        merge_star = False
    else:
        merge_star = True
    if previous_classes_bool and not merge_star:
        start_cycle_number += 1
    print("generating star")
    new_star_file = await loop.run_in_executor(executor, partial(processing_functions.generate_star_file,stack_label=stack_label, working_directory = working_directory, previous_classes_bool = previous_classes_bool, merge_star=merge_star, recent_class=recent_class, start_cycle_number=start_cycle_number))
    particle_count, particles_per_process, class_fraction = await loop.run_in_executor(executor, partial(processing_functions.calculate_particle_statistics,filename=new_star_file, class_number=int(config["settings"]["class_number"]), particles_per_class=int(config["settings"]["particles_per_class"]), process_count=process_count))
    # Generate new classes!
    print("Generating Class")
    if config["settings"]["classification_type"] == "abinit":
        await loop.run_in_executor(executor, partial(processing_functions.generate_new_classes, start_cycle_number=start_cycle_number, class_number=int(config["settings"]["class_number"]), input_stack="{}.mrcs".format(stack_label), pixel_size=float(config["settings"]["pixel_size"]), low_res=300, high_res=int(config["settings"]["high_res_initial"]), new_star_file=new_star_file, working_directory = working_directory))

        await loop.run_in_executor(executor, processing_functions.make_photos,"cycle_{}".format(start_cycle_number),working_directory)
        new_cycle = {"name": "cycle_{}".format(start_cycle_number), "number": start_cycle_number, "settings": config["settings"], "high_res_limit": int(config["settings"]["high_res_initial"]), "block_type": "random_seed", "cycle_number_in_block": 1, "time": str(datetime.datetime.now()), "process_count": 1, "particle_count": total_particles}
        config["cycles"].append(new_cycle)
        dump_json(config)
        return_data = await get_new_gallery(config, {"gallery_number": start_cycle_number})
        log.info("Sending new gallery to clients")
        for client in clients:
            try:
                client.write_message(return_data)
            except:
                print("Couldn't send updates due to broken websocket: {}".format(client))
    # Startup Cycles
    print("Startup Cycles")
    if not config["settings"]["classification_type"] == "refine":
        resolution_cycle_count = int(config["settings"]["run_count_startup"])
        log.info("=====================================")
        log.info("Beginning Iterative 2D Classification")
        log.info("=====================================")
        log.info("Of the total {} particles, {:.0f}% will be classified into {} classes".format(particle_count, class_fraction*100, config["settings"]["class_number"]))
        log.info("Classification will begin at {}Å and step up to {}Å resolution over {} iterative cycles of classification".format(config["settings"]["high_res_initial"], config["settings"]["high_res_final"], resolution_cycle_count))
        log.info("{0} particles per process will be classified by {1} processes.".format(particles_per_process, config["process_count"]))
        for cycle_number in range(resolution_cycle_count):
            if config["kill_job"]:
                break
            low_res_limit = 300
            high_res_limit = int(config["settings"]["high_res_initial"])-(((int(config["settings"]["high_res_initial"])-int(config["settings"]["high_res_final"]))/(resolution_cycle_count-1))*cycle_number)
            filename_number = cycle_number + start_cycle_number
            print(filename_number)
            log.info("High Res Limit: {0:.2}".format(high_res_limit))
            log.info("Fraction of Particles: {0:.2}".format(class_fraction))
            pool = multiprocessing.Pool(processes=process_count)
            refine_job = partial(processing_functions.refine_2d_subjob, round=filename_number, input_star_filename = new_star_file, input_stack="{}.mrcs".format(stack_label), particles_per_process=particles_per_process, low_res_limit=low_res_limit, high_res_limit=high_res_limit, class_fraction=class_fraction, particle_count=particle_count, pixel_size=float(config["settings"]["pixel_size"]), angular_search_step=15, max_search_range=49.5, process_count=process_count,working_directory = working_directory)
            results_list = await loop.run_in_executor(executor, pool.map, refine_job, range(process_count))

            pool.close()
            log.info(results_list[0].decode('utf-8'))
            await loop.run_in_executor(executor,partial(processing_functions.merge_2d_subjob,filename_number, process_count=process_count))
            await loop.run_in_executor(executor,processing_functions.make_photos,"cycle_{}".format(filename_number+1),working_directory)
            new_star_file = await loop.run_in_executor(executor, partial(processing_functions.merge_star_files,filename_number, process_count=process_count, working_directory = config["working_directory"]))
            new_cycle = {"name": "cycle_{}".format(filename_number+1), "number": filename_number+1, "settings": config["settings"], "high_res_limit": high_res_limit, "block_type": "startup", "cycle_number_in_block": cycle_number+1, "time": str(datetime.datetime.now()), "process_count": process_count, "particle_count": total_particles}
            config["cycles"].append(new_cycle)
            dump_json(config)
            return_data = await get_new_gallery(config, {"gallery_number": filename_number+1})
            log.info("Sending new gallery to clients")
            for client in clients:
                try:
                    client.write_message(return_data)
                except:
                    print("Couldn't send updates due to broken websocket: {}".format(client))
        start_cycle_number = start_cycle_number + resolution_cycle_count

    # Refinement Cycles
    print("Refinement Cycles")

    refinement_cycle_count = int(config["settings"]["run_count_refine"])
    class_fraction = 1.0
    log.info("====================================================")
    log.info("Long 2D classifications to incorporate all particles")
    log.info("====================================================")
    log.info("All {} particles will be classified into {} classes at resolution {}Å".format(particle_count, config["settings"]["class_number"], config["settings"]["high_res_final"]))
    log.info("{0} particles per process will be classified by {1} processes.".format(particles_per_process, config["process_count"]))
    for cycle_number in range(refinement_cycle_count):
        if config["kill_job"]:
            break
        low_res_limit = 300
        high_res_limit = int(config["settings"]["high_res_final"])
        filename_number = cycle_number + start_cycle_number
        log.info("High Res Limit: {0}".format(high_res_limit))
        log.info("Fraction of Particles: {0:.2}".format(class_fraction))
        pool = multiprocessing.Pool(processes=int(config["process_count"]))
        refine_job = partial(processing_functions.refine_2d_subjob, round=filename_number, input_star_filename = new_star_file, input_stack="{}.mrcs".format(stack_label), particles_per_process=particles_per_process, low_res_limit=low_res_limit, high_res_limit=high_res_limit, class_fraction=class_fraction, particle_count=particle_count, pixel_size=float(config["settings"]["pixel_size"]), angular_search_step=15, max_search_range=49.5, process_count=process_count, working_directory = working_directory)
        results_list = await loop.run_in_executor(executor,pool.map,refine_job, range(process_count))
        pool.close()
        log.info(results_list[0].decode('utf-8'))
        await loop.run_in_executor(executor, partial(processing_functions.merge_2d_subjob, filename_number, process_count=int(config["process_count"])))
        await loop.run_in_executor(executor, processing_functions.make_photos, "cycle_{}".format(filename_number+1),config["working_directory"])
        new_star_file = await loop.run_in_executor(executor, partial(processing_functions.merge_star_files,filename_number, process_count=process_count, working_directory = working_directory))
        new_cycle = {"name": "cycle_{}".format(filename_number+1), "number": filename_number+1, "settings": config["settings"], "high_res_limit": high_res_limit, "block_type": "refinement", "cycle_number_in_block": cycle_number+1, "time": str(datetime.datetime.now()), "process_count": process_count, "particle_count": total_particles}
        config["cycles"].append(new_cycle)
        dump_json(config)
        return_data = await get_new_gallery(config, {"gallery_number": filename_number+1})
        log.info("Sending new gallery to clients")
        for client in clients:
            try:
                client.write_message(return_data)
            except:
                print("Couldn't send updates due to broken websocket: {}".format(client))
    config["job_running"] = False
    config["kill_job"] = False
    os.chdir(sys.path[0])
    for client in clients:
        client.write_message({"type": "job_finished"})




def main():
    """Construct and serve the tornado app"""
    parse_command_line()
    uvloop.install()
    app=Application([(r"/", IndexHandler),
        (r"/static/(.*)", StaticFileHandler, {"path": os.path.join(starting_directory, "static")}),
        (r"/gallery/(.*)", StaticFileHandler, class_path_dict),
        (r"/websocket", SocketHandler),
        ],**settings)
    app.listen(options.port)
    print('Listening on http://localhost:%i' % options.port)
    # tailed_callback = tornado.ioloop.PeriodicCallback(lambda: tail_log(config, clients), 5000)
    # tailed_callback.start()

    tornado.ioloop.IOLoop.current().start()



if __name__ == "__main__":
    main()
