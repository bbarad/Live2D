### Process warp data to prepare for Frealign. Requires relion_preprocess and star_to_par.com
# import asyncio

import itertools
from functools import partial
from math import ceil
import multiprocessing
import os
import subprocess
from sys import argv
import time

import processing_functions_blocking_shell as processing_functions

# Process arguments and memorize the starting directory to move back to at the end of the script - NB if the script crashes the user gets dumped into the wrong place - I will need to fix that...

# Starting Info
warp_directory = "/local/scratch/krios/Warp_Transfers/TestData"
# star_file = "allparticles_BoxNet2Mask_20180918.star"
star_file = "allparticles_GenentechNet2Mask_20190627.star"
# star_file = "all_particles_short.star"
starting_directory = os.getcwd()
working_directory = "/local/scratch/krios/Warp_Transfers/TestData/classification"
stack_label = "combined_stack"
pixel_size = 1.2007
high_res_limit_initial = 40.0
high_res_limit_final = 8.0
low_res_limit = 300
process_count = 32
resolution_cycle_count = 10
classify_by_resolution = True
long_cycle_count = 5
run_long_cycles = True
class_number = 50
angular_search_step = 15.0
max_search_range = 49.5
particles_per_class_target = 300
get_new_particles_from_warp = True



times = []
times.append(time.time())

os.chdir(working_directory)

previous_classes_bool, recent_class, start_cycle_number = processing_functions.find_previous_classes()

if get_new_particles_from_warp:
    processing_functions.import_new_particles(stack_label=stack_label, warp_folder=warp_directory, warp_star_filename=star_file, working_directory=working_directory)
    new_star_file = processing_functions.generate_star_file(stack_label=stack_label, previous_classes_bool=previous_classes_bool, recent_class=recent_class)
    times.append(time.time())
    print("Generating stack files took {0:.1f} seconds".format(times[-1]-times[-2]))
else:
    new_star_file = recent_class

particle_count, particles_per_process, class_fraction = processing_functions.calculate_particle_statistics(filename=new_star_file, class_number=class_number, particles_per_class=particles_per_class_target, process_count=process_count)


if not previous_classes_bool:
    processing_functions.generate_new_classes(class_number=class_number, input_stack="{}.mrcs".format(stack_label), pixel_size = pixel_size, low_res = low_res_limit, high_res = high_res_limit_initial)
    times.append(time.time())
    print("Generating new classes took {0:.1f} seconds".format(times[-1]-times[-2]))
    new_star_file = "classes_0.star"

print(new_star_file)
if classify_by_resolution:
    print("=====================================")
    print("Beginning Iterative 2D Classification")
    print("=====================================")
    print("Of the total {} particles, {:.0f}% will be classified into {} classes".format(particle_count, class_fraction*100, class_number))
    print("Classification will begin at {}Å and step up to {}Å resolution over {} iterative cycles of classification".format(high_res_limit_initial, high_res_limit_final, resolution_cycle_count))
    print("{0} particles per process will be classified by {1} processes.".format(particles_per_process, process_count))
    for cycle_number in range(resolution_cycle_count):
        high_res_limit = high_res_limit_initial-((high_res_limit_initial-high_res_limit_final)/(resolution_cycle_count-1))*cycle_number
        filename_number = cycle_number + start_cycle_number
        # high_res_limit = high_res_limit_final
        print("High Res Limit: {0:.2}".format(high_res_limit))
        print("Fraction of Particles: {0:.2}".format(class_fraction))
        pool = multiprocessing.Pool(processes=process_count)
        refine_job = partial(processing_functions.refine_2d_subjob, round=filename_number, input_star_filename = new_star_file, input_stack="{}.mrcs".format(stack_label), particles_per_process=particles_per_process, low_res_limit=low_res_limit, high_res_limit=high_res_limit, class_fraction=class_fraction, particle_count=particle_count, pixel_size=pixel_size, angular_search_step=angular_search_step, max_search_range=max_search_range, process_count=process_count)
        results_list = pool.map(refine_job, range(process_count))
        pool.close()
        print(results_list[0].decode('utf-8'))
        processing_functions.merge_2d_subjob(filename_number, process_count=process_count)
        processing_functions.make_photos("classes_{}".format(filename_number+1),working_directory)
        new_star_file = processing_functions.merge_star_files(filename_number, process_count=process_count)
    start_cycle_number = start_cycle_number + resolution_cycle_count

if run_long_cycles:
    print("====================================================")
    print("Long 2D classifications to incorporate all particles")
    print("====================================================")
    print("All {} particles will be classified into {} classes at resolution {}Å".format(particle_count, class_number, high_res_limit_final))
    print("{0} particles per process will be classified by {1} processes.".format(particles_per_process, process_count))
    # 5 cycles of finalizing refinement to clean it up.
    for cycle_number in range(long_cycle_count):
        high_res_limit = high_res_limit_final
        print("High Res Limit: {0:.2}".format(high_res_limit))
        print("Fraction of Particles: {0:.2}".format(1.0))
        filename_number = cycle_number + start_cycle_number
        pool = multiprocessing.Pool(processes=process_count)
        refine_job = partial(processing_functions.refine_2d_subjob, round=filename_number, input_star_filename=new_star_file, input_stack="{}.mrcs".format(stack_label), particles_per_process=particles_per_process, low_res_limit=low_res_limit, high_res_limit=high_res_limit, class_fraction=1.0, particle_count=particle_count, pixel_size=pixel_size, angular_search_step=angular_search_step, max_search_range=max_search_range, process_count=process_count)
        results_list = pool.map(refine_job, range(process_count))
        print(results_list[0].decode('utf-8'))
        processing_functions.merge_2d_subjob(filename_number, process_count=process_count)
        processing_functions.make_photos("class_{}".format(filename_number+1),working_directory)
        new_star_file = processing_functions.merge_star_files(filename_number, process_count=process_count)
#
times.append(time.time())
os.chdir(starting_directory)
print("Total Runtime: {} seconds".format(times[-1]-times[0]))
