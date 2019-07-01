### Process warp data to prepare for Frealign. Requires relion_preprocess and star_to_par.com
# import asyncio

from functools import partial
from math import ceil
import multiprocessing
import os
import subprocess
from sys import argv
import time

# Process arguments and memorize the starting directory to move back to at the end of the script - NB if the script crashes the user gets dumped into the wrong place - I will need to fix that...

# Starting Info
warp_working_directory = "/local/scratch/krios/Warp_Transfers/TestData"
star_file = "allparticles_GenentechNet2Mask_20190627.star"
starting_directory = os.getcwd()
working_directory = "/local/scratch/baradb/outputdata"
pixel_size = 1.2007
high_res_limit_initial = 40.0
high_res_limit_final = 8
low_res_limit = 300
process_count = 32
cycle_count = 8
class_number = 50
angular_search_step = 15.0
max_search_range = 49.5
times = []
times.append(time.time())
# print("Combining Stacks of Particles")
# print("==============================")
# os.chdir(warp_working_directory)
#
# p = subprocess.call(['/gne/home/baradb/relion/build/bin/relion_preprocess --operate_on {0} --operate_out {1}/single_stacked'.format(star_file, working_directory)], shell=True) # Do not run shell=True outside of intranet!
#
# times.append(time.time())
# print("Time to produce the combined stack: {0.2f} s".format(times[-1]-times[-2]))
os.chdir(working_directory)
# Star to frealign makes the initial par file, which I am naming classes_0.par for the purposes of making the 2d classification numbered consistently.
p = subprocess.Popen("/gne/home/baradb/star_to_frealign.com", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
out, _ = p.communicate(input="single_stacked.star\nclasses_0.par\n{0}".format(pixel_size).encode('utf-8'))
times.append(time.time())
print(out.decode('utf-8'))
print("Time to produce the par file: {0:.2f} s".format(times[-1]-times[-2]))

# count the particles by lines in the file - I am 100% sure there is a better way to do this... but this works fast.
with open("classes_0.par") as f:
    for i,l in enumerate(f):
        pass
    particle_count = i+1
# particle_count = 5000
print(particle_count)
particles_per_process = int(ceil(particle_count / process_count))
print (particles_per_process)
class_fraction = 300.0 * class_number / particle_count
if class_fraction > 1:
    class_fraction = 1.0
print(class_fraction)

print("Preparing 2D Classes")
print("====================")
input = "\n".join([
    "single_stacked.mrcs", # Input MRCS stack
    "classes_0.par", # Input Par file
    os.devnull, # Input MRC classes
    os.devnull, # Output par file
    "classes_0.mrc", # Output MRC class
    str(class_number), # number of classes to generate for the first time - only use when starting a NEW classification
    "1", # First particle in stack to use
    "0", # Last particle in stack to use - 0 is the final.
    "1", # Fraction of particles to classify
    str(pixel_size), # Pixel Size
    "300", # keV
    "2.7", # Cs
    "0.07", # Amplitude Contrast
    "150", # Mask Radius in Angstroms
    str(low_res_limit), # Low Resolution Limit
    str(high_res_limit_initial), # High Resolution Limit
    "0", #
    "0",
    "0",
    "1",
    "2",
    "Yes", # Normalize?
    "Yes", # INVERT?
    "Yes",
    "No",
    "No.dat"
])
p = subprocess.Popen("/gne/home/rohoua/software/cisTEM2/r796_dbg/bin/refine2d", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
out,_ = p.communicate(input=input.encode('utf-8'))
print(out.decode('utf-8'))

print("Beginning 2D Classification")
print("===========================")

def refine_2d_subjob(process_number, round=0, particles_per_process = 1, high_res_limit = high_res_limit_initial, class_fraction = class_fraction):
    import time
    start_time = time.time()
    start = process_number*particles_per_process+1
    stop = (process_number+1)*particles_per_process
    if stop > particle_count:
        stop = particle_count
    # print(start,stop)
    input = "\n".join([
        "single_stacked.mrcs", # Input MRCS stack
        "classes_0.par".format(round), # Input Par file
        "classes_{0}.mrc".format(round), # Input MRC classes
        "/dev/null", # Output par file
        "classes_{0}.mrc".format(round+1), # Output MRC class
        "0", # number of classes to generate for the first time - only use when starting a NEW classification
        str(start), # First particle in stack to use
        str(stop), # Last particle in stack to use - 0 is the final.
        "{0:.2}".format(class_fraction), # Fraction of particles to classify
        str(pixel_size), # Pixel Size
        "300", # keV
        "2.7", # Cs
        "0.07", # Amplitude Contrast
        "150", # Mask Radius in Angstroms
        str(low_res_limit), # Low Resolution Limit
        str(high_res_limit), # High Resolution Limit
        "{0}".format(angular_search_step), #
        "{0}".format(max_search_range),
        "{0}".format(max_search_range),
        "1",
        "2",
        "Yes",
        "Yes",
        "Yes",
        "Yes",
        "dump_file_{0}.dat".format(process_number+1)
    ])
    # if process_number=0:
    #     print(input)
    p = subprocess.Popen("/gne/home/rohoua/software/cisTEM2/r796_dbg/bin/refine2d", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    out,_ = p.communicate(input=input.encode('utf-8'))
    end_time = time.time()
    time = end_time - start_time
    print("Successful return of process number {0} out of {1} in time {2:0.1f} seconds".format(process_number+1, process_count, time))
    return(out)

def merge_2d_subjob(round):
    input = "\n".join([
        "classes_{0}.mrc".format(round+1),
        "dump_file_.dat",
        str(process_count)
    ])
    p = subprocess.Popen("/gne/home/rohoua/software/cisTEM2/r796_dbg/bin/merge2d", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    out,_ = p.communicate(input=input.encode('utf-8'))
    print(out.decode('utf-8'))
    # p = subprocess.Popen("rm dump_file_*.dat", shell=True)

#
for cycle_number in range(cycle_count):
    high_res_limit = high_res_limit_initial-((high_res_limit_initial-high_res_limit_final)/(cycle_count-1))*cycle_number
    print("High Res Limit: {0:.3}".format(high_res_limit))
    print("Fraction of Particles: {0:.2}".format(class_fraction))
    pool = multiprocessing.Pool(processes=process_count)
    refine_job = partial(refine_2d_subjob, round=cycle_number, particles_per_process=particles_per_process, high_res_limit=high_res_limit, class_fraction=class_fraction)
    results_list = pool.map(refine_job, range(process_count))
    print(results_list[0].decode('utf-8'))
    merge_2d_subjob(cycle_number)

#
# os.chdir(starting_directory)
