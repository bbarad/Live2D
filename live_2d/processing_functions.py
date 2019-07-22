import asyncio
import glob
import itertools
import logging as log
from math import ceil
import os
import shutil
import subprocess
import time

import mrcfile
import numpy as np
import pandas
from pyem import star
import scipy.misc
import sys



def isheader(string):
    # print(string)
    try:
        string = string.decode()
    except AttributeError:
        pass
    if string.startswith("_"):
        return True
    if string.startswith("#"):
        return True
    if string.startswith("data_"):
        return True
    if string.startswith("loop_"):
        return True
    if string.isspace():
        print(string)
        return True
    return False

def count_particles_per_class(star_filename):
    """Generate a list with the number of counts for a give class in that index.
    Adapted from https://stackoverflow.com/questions/46759464/fast-way-to-count-occurrences-of-all-values-in-a-pandas-dataframe"""
    with open(star_filename) as f:
        pos = 0
        cur_line = f.readline()
        while isheader(cur_line):
            pos = f.tell()
            cur_line = f.readline()
        f.seek(pos)
        df = pandas.read_csv(f, delim_whitespace=True)
        class_row = df.iloc[:,-1]
        class_counter = np.bincount(class_row.ravel())
        print(class_counter)
        print(len(class_counter))
    return class_counter




def particle_count_difference(larger_stack, smaller_stack):
    """Quickly determine the difference in number of particles"""
    with open(smaller_stack, "r") as f:
        i=0
        j = 0
        for i,l in enumerate(f):
            if isheader(l):
                j += 1
            pass
        smaller_particle_count = i+1-j

    with open(larger_stack, "r") as f2:
        i2=0
        j2 = 0
        for i2,l2 in enumerate(f2):
            if isheader(l):
                j2 += 1
            pass
        difference = i2+1-j2 - smaller_particle_count
    return difference


def make_photos(basename, working_directory):
    if not os.path.isdir(os.path.join(working_directory, "class_images")):
        os.mkdir(os.path.join(working_directory, "class_images"))
    if not os.path.isdir(os.path.join(working_directory,"class_images",basename)):
        os.mkdir(os.path.join(working_directory,"class_images",basename))
    photo_dir = os.path.join(working_directory,"class_images",basename)
    with mrcfile.open("{}.mrc".format(basename), "r") as stack:
        for index,item in enumerate(stack.data):
            scipy.misc.imsave(os.path.join(photo_dir,"{}.png".format(index+1)), item)
    return photo_dir

def import_new_particles(stack_label, warp_folder, warp_star_filename, working_directory, new_net=False):
    """Function to generate new image stacks based only on the results of the first stack. Also, while I am doing it, I will write out a base star file to use for appending and/or regenerating for further class files.
    I am doing everything using a memory mapped mrc file. This does not allow easy appending, so I am writing directly to the memory map once it is created as a numpy mmap, then I am reloading as an mrcfile mmap and fixing the header."""
    log.info("=======================================")
    log.info("Combining Stacks of Particles from Warp")
    log.info("=======================================")
    start_time = time.time()
    starting_directory = os.getcwd()
    combined_filename = os.path.join(working_directory,"{}.mrcs".format(stack_label))
    previous_file = os.path.isfile(combined_filename)
    if new_net:
        # Hack to overwrite the old file if you switch to a new neural net.
        previous_file = False
    os.chdir(warp_folder)
    total_particles = star.parse_star(warp_star_filename)
    log.info(len(total_particles))
    stacks_filenames = total_particles["rlnImageName"].str.rsplit("@").str.get(-1)

    # MAKE PRELIMINARY STACK IF ITS NOT THERE
    if not previous_file:
        print("Copying first mrcs file to generate seed for combined stack")
        shutil.copy(stacks_filenames[0], combined_filename)

    # GET INFO ABOUT STACKS
    with mrcfile.mmap(combined_filename, "r", permissive=True) as mrcs:
        prev_par = int(mrcs.header.nz)
        log.info("Previous Particles: {}".format(prev_par))
        new_particles_count = len(total_particles) - prev_par
        log.info("Total Particles to Import: {}".format(new_particles_count))
        offset = mrcs.data.base.size()
        # log.info("Bytes Offset: {}".format(offset))
        data_dtype = mrcs.data.dtype
        # log.info("dtype: {}".format(data_dtype))
        # log.info("dtype size: {}".format(data_dtype.itemsize))
        shape=(new_particles_count, mrcs.header.ny, mrcs.header.nx)

    # OPEN THE MEMMAP AND ITERATIVELY ADD NEW PARTICLES
    mrcfile_raw = np.memmap(combined_filename, dtype=data_dtype, offset=offset, shape=shape, mode="r+")
    new_offset=0
    new_filenames = stacks_filenames[prev_par:].unique()
    for index, filename in enumerate(new_filenames):
        # try:
            with mrcfile.mmap(filename, "r+", permissive=True) as partial_mrcs:
                try:
                    x = partial_mrcs.header.nx
                    y = partial_mrcs.header.ny
                    z = partial_mrcs.header.nz
                    log.info("Filename {} ({} of {}) contributing {} particles starting at {}".format(filename, index+1, len(new_filenames), z, new_offset))
                    mrcfile_raw[new_offset:new_offset+z,:,:] = partial_mrcs.data
                except: # If the file size is wrong, don't just assume its gonna be wrong...
                    info.warn("Particle stack header didn't match data")
                    partial_mrcs.update_header_from_data()
                    x = partial_mrcs.header.nx
                    y = partial_mrcs.header.ny
                    z = partial_mrcs.header.nz
                    log.info("Filename {} ({} of {}) contributing {} particles starting at {}".format(filename, index+1, len(new_filenames), z, new_offset))
                    mrcfile_raw[new_offset:new_offset+z,:,:] = partial_mrcs.data
                new_offset = new_offset+z
        # except:
        #     log.error(f"Failed to import {filename} (number {index+1} of {len(new_filenames)}) - will not import any more particles")
        #     break
    mrcfile_raw.flush()
    del mrcfile_raw
    # FIX THE HEADER
    with mrcfile.mmap(combined_filename, "r+", permissive=True) as mrcs:
        mrcs.header.nz = mrcs.header.mz = len(total_particles)

    os.chdir(working_directory)
    #WRITE OUT STAR FILE
    with open(os.path.join(working_directory,"{}.star".format(stack_label)),"w") as file:
        file.write("\0\ndata_\n\0\nloop_\n")
        input = ["{} #{}".format(value, index+1) for index,value in enumerate([
        "_cisTEMPositionInStack",
        "_cisTEMAnglePsi",
        "_cisTEMXShift",
        "_cisTEMYShift",
        "_cisTEMDefocus1",
        "_cisTEMDefocus2",
        "_cisTEMDefocusAngle",
        "_cisTEMPhaseShift",
        "_cisTEMOccupancy",
        "_cisTEMLogP",
        "_cisTEMSigma",
        "_cisTEMScore",
        "_cisTEMScoreChange",
        "_cisTEMPixelSize",
        "_cisTEMMicroscopeVoltagekV",
        "_cisTEMMicroscopeCsMM",
        "_cisTEMAmplitudeContrast",
        "_cisTEMBeamTiltX",
        "_cisTEMBeamTiltY",
        "_cisTEMImageShiftX",
        "_cisTEMImageShiftY",
        "_cisTEMBest2DClass",
        ])]
        file.write("\n".join(input))
        file.write("\n")
        for row in total_particles.itertuples(index=True):
            row_data = [
            str(row.Index+1),
            "0.00",
            "-0.00",
            "-0.00",
            str(row.rlnDefocusU),
            str(row.rlnDefocusV),
            str(row.rlnDefocusAngle),
            "0.0",
            "100.0",
            "-500",
            "1.0",
            "20.0",
            "0.0",
            "{:.4f}".format(row.rlnDetectorPixelSize),
            str(row.rlnVoltage),
            str(row.rlnSphericalAberration),
            str(row.rlnAmplitudeContrast),
            "0.0",
            "0.0",
            "0.0",
            "0.0",
            "0",
            ]
            file.write("\t".join(row_data))
            file.write("\n")
    os.chdir(starting_directory)
    end_time = time.time()
    log.info("Total Time: {}s".format(end_time - start_time))
    return len(total_particles)


def generate_new_classes(start_cycle_number=0, class_number=50, input_stack="combined_stack.mrcs", pixel_size=1.2007, low_res = 300, high_res = 40, new_star_file = "cycle_0.star", working_directory = "~"):
    log.info("====================")
    log.info("Preparing 2D Classes")
    log.info("====================")
    input = "\n".join([
        input_stack, # Input MRCS stack
        new_star_file, # Input Star file
        os.devnull, # Input MRC classes
        os.devnull, # Output star file
        "cycle_{}.mrc".format(start_cycle_number), # Output MRC class
        str(class_number), # number of classes to generate for the first time - only use when starting a NEW classification
        "1", # First particle in stack to use
        "0", # Last particle in stack to use - 0 is the final.
        "1", # Fraction of particles to classify
        str(pixel_size), # Pixel Size
        # "300", # keV
        # "2.7", # Cs
        # "0.07", # Amplitude Contrast
        "150", # Mask Radius in Angstroms
        str(low_res), # Low Resolution Limit
        str(high_res), # High Resolution Limit
        "0", #Angular Search
        "0", # XY search
        "1", # Tuning
        "2", # Tuning
        "Yes", # Normalize?
        "Yes", # INVERT?
        "No", #Exclude blank edges
        "Yes", #Automask
        "Yes", # Autocenter
        "No", # Dump Dats
        "No.dat", # Datfilename,
        "1", # max threads
    ])
    p = subprocess.Popen("/gne/home/rohoua/software/cisTEM2/r813/bin/refine2d", stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    out,_ = p.communicate(input=input.encode('utf-8'))
    log.info(out.decode('utf-8'))

def refine_2d_subjob(process_number, round=0, input_star_filename = "class_0.star", input_stack = "combined_stack.mrcs", particles_per_process = 100,low_res_limit=300, high_res_limit = 40, class_fraction = 1.0, particle_count=20000, pixel_size=1, angular_search_step=15.0, max_search_range=49.5, process_count=32, working_directory = "~"):
    import time
    start_time = time.time()
    start = process_number*particles_per_process+1
    stop = (process_number+1)*particles_per_process
    if stop > particle_count:
        stop = particle_count
    input = "\n".join([
        input_stack, # Input MRCS stack
        input_star_filename, # Input Star file
        "cycle_{0}.mrc".format(round), # Input MRC classes
        "partial_classes_{0}_{1}.star".format(round+1, process_number), # Output Star file
        "cycle_{0}.mrc".format(round+1), # Output MRC classes
        "0", # number of classes to generate for the first time - only use when starting a NEW classification
        str(start), # First particle in stack to use
        str(stop), # Last particle in stack to use - 0 is the final.
        "{0:.2}".format(class_fraction), # Fraction of particles to classify
        str(pixel_size), # Pixel Size
        # "300", # keV
        # "2.7", # Cs
        # "0.07", # Amplitude Contrast
        "150", # Mask Radius in Angstroms
        str(low_res_limit), # Low Resolution Limit
        str(high_res_limit), # High Resolution Limit
        "{0}".format(angular_search_step), #Angular Search
        "{0}".format(max_search_range), #XY Search
        "1", #Tuning
        "2", # Tuning
        "Yes", #Normalize
        "Yes", #invert
        "No", # Exclude blank edges
        "Yes", #Automask
        "Yes", #Autocenter
        "Yes", #Dump Dat
        "dump_file_{0}.dat".format(process_number+1),
        "1", # Max threads
    ])
    # if process_number=0:
    #     log.info(input)
    p = subprocess.Popen("/gne/home/rohoua/software/cisTEM2/r813/bin/refine2d", shell=True, stdout=asyncio.subprocess.PIPE, stdin=asyncio.subprocess.PIPE)
    out,_ = p.communicate(input=input.encode('utf-8'))
    end_time = time.time()
    time = end_time - start_time
    log.info("Successful return of process number {0} out of {1} in time {2:0.1f} seconds".format(process_number+1, process_count, time))
    return(out)

def merge_star_files(cycle, process_count=32, working_directory = "~"):
    filename = "cycle_{}.star".format(cycle+1)
    with open(filename, 'wb') as outfile:
        for process_number in range(process_count):
            with open("partial_classes_{}_{}.star".format(cycle+1, process_number), 'rb') as infile:
                if process_number == 0:
                    for line in infile:
                        outfile.write(line)
                else:
                    for line in infile:
                        if not isheader(line):
                            outfile.write(line)
            subprocess.Popen("/bin/rm partial_classes_{}_{}.star".format(cycle+1, process_number), shell=True)
    log.info("Finished writing cycle_{}.star".format(cycle+1))
    return os.path.join(working_directory, "cycle_{}.star".format(cycle+1))

def merge_2d_subjob(cycle, process_count=32):
    input = "\n".join([
        "cycle_{0}.mrc".format(cycle+1),
        "dump_file_.dat",
        str(process_count)
    ])
    p = subprocess.Popen("/gne/home/rohoua/software/cisTEM2/r813/bin/merge2d", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    out,_ = p.communicate(input=input.encode('utf-8'))
    log.info(out.decode('utf-8'))
    for i in range(process_count):
        p = subprocess.Popen("/bin/rm dump_file_{}.dat".format(i+1), shell=True)


def calculate_particle_statistics(filename, class_number=50, particles_per_class=300, process_count = 32):
    with open(filename, "r") as f:
        i=0
        j = 0
        for i,l in enumerate(f):
            if isheader(l):
                j += 1
            pass
        particle_count = i+1-j
    print(particle_count)
    particles_per_process = int(ceil(particle_count / process_count))

    class_fraction = particles_per_class * class_number / particle_count

    if class_fraction > 1:
        class_fraction = 1.0
    return particle_count, particles_per_process, class_fraction

def append_new_particles(old_particles, new_particles, output_filename):
    with open(output_filename, 'w') as append_file:
        old_header_length = 0
        log.info(old_particles)
        with open(old_particles) as f:
            for i,l in enumerate(f):
                append_file.write(l)
                if isheader(l):
                    old_header_length += 1
        old_particle_count = i+1-old_header_length
        new_particles_count = 0
        new_header_length = 0
        with open(new_particles) as f2:
            for i,l in enumerate(f2):
                if isheader(l):
                    new_header_length +=1
                    continue
                if i == new_header_length + old_particle_count:
                    log.info(i)
                if i > new_header_length + old_particle_count:
                    append_file.write(l)
                    new_particles_count += 1
    return new_particles_count+old_particle_count

# def find_previous_classes(config):
#     file_list = glob.glob("classes_*.star")
#     if len(file_list) > 0:
#         previous_classes_bool=True
#         recent_class = sorted(file_list, key=lambda f: int(f.rsplit(os.path.extsep, 1)[0].rsplit("_")[1]))[-1]
#         cycle_number = int(recent_class.rsplit(os.path.extsep, 1)[0].rsplit("_")[1])
#     else:
#         previous_classes_bool = False
#         recent_class = "classes_0.star"
#         cycle_number = 0
#     return previous_classes_bool, recent_class, cycle_number


def generate_star_file(stack_label, working_directory, previous_classes_bool=False, merge_star=True, recent_class = "cycle_0", start_cycle_number = 0):
    """Wrapper logic to either append particles or generate a whole new class.
    Uses find_previous_classes and append_new_particles and import_new_particles to do all the heavy lifting."""
    star_file = os.path.join(working_directory, "{}.star".format(stack_label))
    print (star_file)
    if previous_classes_bool and not merge_star:
        log.info("Previous classes will not be used, and a new star will be written at cycle_{}.star".format(start_cycle_number))
        new_star_file = os.path.join(working_directory, "cycle_{}.star".format(start_cycle_number))
        shutil.copy(star_file, new_star_file)
    elif previous_classes_bool:
        log.info("It looks like previous jobs have been run in this directory. The most recent output class is: {}.star".format(recent_class))
        new_star_file = os.path.join(working_directory,"{}_appended.star".format(recent_class))
        log.info("Instead of cycle_0.star, the new particles will be appended to the end of that star file and saved as {}".format("{}_appended.star".format(recent_class)))
        total_particles = append_new_particles(old_particles=os.path.join(working_directory,"{}.star".format(recent_class)), new_particles=star_file, output_filename = new_star_file)
    else:
        log.info("No previous classes were found. A new star file will be generated at cycle_0.star")
        new_star_file = os.path.join(working_directory,"cycle_0.star")
        shutil.copy(star_file, new_star_file)
    return new_star_file





if __name__=="__main__":
    log.info("This is a function library and should not be called directly.")
    # log.info("Testing particle import with streaming")
    # stack_label="streaming_combine"
    # warp_folder = "/local/scratch/krios/Warp_Transfers/TestData"
    # warp_star_filename = "allparticles_GenentechNet2Mask_20190627.star"
    # working_directory = "/gne/scratch/u/baradb/outputdata"
    # import_new_particles(stack_label, warp_folder, warp_star_filename, working_directory)
