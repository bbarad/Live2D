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

"""
Processing functions for Live 2D Classification
===============================================
This is a group of utility functions for the Live 2D Classification webserver related to processing EM data using output from warp and with cisTEM2 command line tools (called via subprocess execution).

cisTEM2 command line inputs are subject to change, so if jobs are not running a good place to start checking is in the functions :py:func:`generate_new_classes`, :py:func:`refine_2d_subjob`, and :py:func:`merge_2d_subjob`

These processing functions can be used independently of the web server, but the essential job loop logic is handled in :py:func:`live_2d.execute_job_loop`, not here.

Author: Benjamin Barad <benjamin.barad@gmail.com>/<baradb@gene.com>
"""

import asyncio
import errno
import logging
from math import ceil
import os
import shutil
import subprocess
import time

import mrcfile
import numpy as np
import pandas
import imageio


def isheader(string):
    """
    Check if a string looks like a star header line.

    Args:
        string (str): line of a star file
    Returns:
        true if the line looks like a star file header lines
        false if the line is expected to be a star file data line.
    """
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
        return True
    return False


def count_particles_per_class(star_filename):
    """Generate a list with the number of counts for a given class in that index.
    Adapted from https://stackoverflow.com/questions/46759464/fast-way-to-count-occurrences-of-all-values-in-a-pandas-dataframe

    Args:
        star_filename (str): Filename for cistem classification starfile
    Returns:
        list: List of counts for each class in its respective index, and unclassified count in index 0.
    """
    with open(star_filename) as f:
        pos = 0
        cur_line = f.readline()
        while isheader(cur_line):
            pos = f.tell()
            cur_line = f.readline()
        f.seek(pos)
        df = pandas.read_csv(f, delim_whitespace=True)
        class_row = df.iloc[:, -1]
        cr = class_row.ravel()
        cr[cr < 0] = 0
        class_counter = np.bincount(cr)
        class_counter_list = [int(i) for i in class_counter]
        live2dlog.info(f"Particles per class: {class_counter_list}")
    return class_counter_list


def load_star_as_dataframe(star_filename):
    """Generate a pandas dataframe from a star file with one single data loop.
    Written for high efficiency. Star headers have the leading _ stripped and are turned into the pandas header.
    Extra comment lines after the header loop_ are currently unsupported and should be removed. before loading.

    Args:
        star_filename (str): Filename of the star file from Warp (relion style)
    Return:
        :py:class:`pandas.Dataframe`: Pandas dataframe from the star file.
    """
    with open(star_filename) as f:
        pos = 0
        columns = []
        cur_line = f.readline()
        while not cur_line.startswith("loop_"):
            cur_line = f.readline()
        cur_line = f.readline()
        while cur_line.startswith("_"):
            pos = f.tell()
            columns.append(cur_line.split()[0][1:])
            cur_line = f.readline()
        f.seek(pos)
        df = pandas.read_csv(f, delim_whitespace=True, names=columns)
    return df


async def particle_count_difference(warp_stack, previous_number):
    """Quickly determine the difference in number of particles
    Efficiently counts the number of non-header lines in a star file and subtracts the previous number counted. Used primarily as a tool for automated job triggering when sufficient new particles have been picked by warp.

    Args:
        warp_stack (str): Filename of the current exported warp particles star file.
        previous_number (int): Number of particles in the latest classification run.
    Return:
        int: Number of particles that have not been previously classified.
    """
    with open(warp_stack, "r") as f:
        i = 0
        j = 0
        for i, l in enumerate(f):
            if isheader(l):
                j += 1
            pass
        total_particle_count = i+1-j
        difference = total_particle_count - previous_number

    return difference


def make_photos(basename, working_directory):
    """
    Convert MRC file with stack of classes to series of scaled PNGs for web viewing.

    Args:
        basename (str): name of desired folder within class_images - usually the same name as the mrc file.
        working_directory (str): the base directory where :py:mod:`live_2d` is working.
    Returns:
        str: Directory path with new PNGs written out.
    """
    live2dlog = logging.getLogger("live_2d")
    if not os.path.isdir(os.path.join(working_directory, "class_images")):
        os.mkdir(os.path.join(working_directory, "class_images"))
    if not os.path.isdir(os.path.join(working_directory, "class_images", basename)):
        os.mkdir(os.path.join(working_directory, "class_images", basename))
    photo_dir = os.path.join(working_directory, "class_images", basename)
    with mrcfile.open(os.path.join(working_directory, "{}.mrc".format(basename)), "r") as stack:
        for index, item in enumerate(stack.data):
            imageio.imwrite(os.path.join(photo_dir, "{}.png".format(index+1)), item)
    live2dlog.info(f"Exported class averages to web-friendly images stored in {photo_dir}")
    return photo_dir


def import_new_particles(stack_label, warp_folder, warp_star_filename, working_directory, new_net=False):
    """Iteratively combine new particle stacks generated by warp into a single monolithic stackfile that is appropriate for use with cisTEM2. Simultaneously generate a cisTEM formatted star file.

    Uses a memory mapped mrc file. This does not allow easy appending, so the function directly accesses the memory map once it is created as a numpy mmap, then reloads as an mrcfile mmap to fix the header.
    Args:
        stack_label (str): Name of combined stack file (without a suffix)
        warp_folder (str): Base folder where Warp outputs.
        warp_star_filename (str): Filename for exported particles starfile. Generally, use the ``allparticles_`` starfile.
        working_directory (str): Folder where combined stacks and star files will be written.
        new_net (bool): Flag for changes to warp that require recombination of all stacks instead of only new ones.
    Returns:
        int: Total number of particles in the combined stack.
    """
    live2dlog = logging.getLogger("live_2d")
    live2dlog.info("=======================================")
    live2dlog.info("Combining Stacks of Particles from Warp")
    live2dlog.info("=======================================")
    start_time = time.time()
    # starting_directory = os.getcwd()
    combined_filename = os.path.join(working_directory, "{}.mrcs".format(stack_label))
    previous_file = os.path.isfile(combined_filename)
    if new_net:
        # Hack to overwrite the old file if you switch to a new neural net.
        live2dlog.info("Due to config changes, forcing complete reimport of particles.")
        previous_file = False
    # os.chdir(warp_folder)
    total_particles = load_star_as_dataframe(os.path.join(warp_folder, warp_star_filename))
    stacks_filenames = total_particles["rlnImageName"].str.rsplit("@").str.get(-1)

    # MAKE PRELIMINARY STACK IF ITS NOT THERE
    if not previous_file:
        live2dlog.info("No previous particle stack is being appended.")
        live2dlog.info("Copying first mrcs file to generate seed for combined stack")
        shutil.copy(os.path.join(warp_folder, stacks_filenames[0]), combined_filename)

    # GET INFO ABOUT STACKS
    with mrcfile.mmap(combined_filename, "r", permissive=True) as mrcs:
        prev_par = int(mrcs.header.nz)
        live2dlog.info("Previous Particles: {}".format(prev_par))
        new_particles_count = len(total_particles) - prev_par
        live2dlog.info("Total Particles to Import: {}".format(new_particles_count))
        # print(prev_par * mrcs.header.nx * mrcs.header.ny * mrcs.data.dtype.itemsize+ mrcs.header.nbytes + mrcs.extended_header.nbytes)
        # print(mrcs.data.base.size())
        offset = prev_par * mrcs.header.nx * mrcs.header.ny * mrcs.data.dtype.itemsize + mrcs.header.nbytes + mrcs.extended_header.nbytes
        # live2dlog.info("Bytes Offset: {}".format(offset))
        data_dtype = mrcs.data.dtype
        # live2dlog.info("dtype: {}".format(data_dtype))
        # live2dlog.info("dtype size: {}".format(data_dtype.itemsize))
        shape = (new_particles_count, mrcs.header.ny, mrcs.header.nx)

    # OPEN THE MEMMAP AND ITERATIVELY ADD NEW PARTICLES
    mrcfile_raw = np.memmap(combined_filename, dtype=data_dtype, offset=offset, shape=shape, mode="r+")
    new_offset = 0
    new_filenames = stacks_filenames[prev_par:].unique()
    filename_counts = stacks_filenames[prev_par:].value_counts()
    for index, filename in enumerate(new_filenames):
        try_number = 0
        wanted_z = filename_counts[filename]
        while(True):
            with mrcfile.mmap(os.path.join(warp_folder, filename), "r+", permissive=True) as partial_mrcs:
                x = partial_mrcs.header.nx
                y = partial_mrcs.header.ny
                z = partial_mrcs.header.nz
                if not z == wanted_z:
                    if try_number >= 12:
                        raise IOError(errno.EIO, f"The data header didn't match the starfile: {z}, {wanted_z}")
                    live2dlog.warn(f"File {filename} has a header that doesn't match the number of particles in the star file.")
                    try_number += 1
                    time.sleep(10)
                    continue

                if not x*y*wanted_z == partial_mrcs.data.size:
                    if try_number >= 12:
                        raise IOError(errno.ETIME, "Took too long for Warp to correct the file. Killing job.")
                    live2dlog.warn(f"File {filename} seems to not be done writing from Warp. Waiting 10 seconds and trying again.")
                    try_number += 1
                    time.sleep(10)
                    continue

                mrcfile_raw[new_offset:new_offset+z, :, :] = partial_mrcs.data
                live2dlog.info("Filename {} ({} of {}) contributing {} particles starting at {}".format(filename, index+1, len(new_filenames), z, new_offset))
                # print("Filename {} ({} of {}) contributing {} particles starting at {}".format(filename, index+1, len(new_filenames), z, new_offset))
                new_offset = new_offset+z
                break

    mrcfile_raw.flush()
    del mrcfile_raw
    # FIX THE HEADER
    with mrcfile.mmap(combined_filename, "r+", permissive=True) as mrcs:
        assert os.stat(combined_filename).st_size == mrcs.header.nbytes+mrcs.extended_header.nbytes + mrcs.header.nx*mrcs.header.ny*len(total_particles)*mrcs.data.dtype.itemsize
        mrcs.header.nz = mrcs.header.mz = len(total_particles)

    # WRITE OUT STAR FILE
    live2dlog.info("Writing out new star file for combined stacks.")
    with open(os.path.join(working_directory, "{}.star".format(stack_label)), "w") as file:
        file.write(" \ndata_\n \nloop_\n")
        input = ["{} #{}".format(value, index+1) for index, value in enumerate([
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
    # os.chdir(starting_directory)
    end_time = time.time()
    live2dlog.info("Total Time To Import New Particles: {}s".format(end_time - start_time))
    return len(total_particles)


def generate_new_classes(start_cycle_number=0, class_number=50, input_stack="combined_stack.mrcs", pixel_size=1.2007, mask_radius=150, low_res=300, high_res=40, new_star_file="cycle_0.star", working_directory="~", automask=False, autocenter=True):
    """
    Call out to cisTEM2 ``refine2d`` using :py:func:`subprocess.Popen` to generate a new set of *Ab Initio* classes.

    Args:
        start_cycle_number (int): Iteration number of the classification (indexes from 0 in :py:func:`execute_job_loop`)
        class_number (int): Number of class seeds to generate (default 50)
        input_stack (str): Filename of combined monolithic particle stack
        pixel_size (int): Pixel size of image files, in Å.
        mask_radius (int): Radius in Å to use for mask (default 150).
        low_res (float): Low resolution cutoff for classification, in Å.
        high_res (float): High resolution cutoff for classification, in Å.
        new_star_file (str): Filename of starting cisTEM-formatted star file.
        working_directory (str): Directory where data will output.
        automask (bool): Automatically mask class averages
        autocenter (bool): Automatically center class averages to center of mass.
    Returns:
        str: STDOUT of :py:func:`subprocess.Popen` call to ``refine2d``.
    """
    live2dlog = logging.getLogger("live_2d")
    automask_text = "No"
    if automask is True:
        automask_text = "Yes"
    autocenter_text = "No"
    if autocenter is True:
        autocenter_text = "Yes"
    input = "\n".join([
        os.path.join(working_directory, input_stack),  # Input MRCS stack
        os.path.join(working_directory, new_star_file),  # Input Star file
        os.devnull,  # Input MRC classes
        os.devnull,  # Output star file
        os.path.join(working_directory, "cycle_{}.mrc".format(start_cycle_number)),  # Output MRC class
        str(class_number),  # number of classes to generate for the first time - only use when starting a NEW classification
        "1",  # First particle in stack to use
        "0",  # Last particle in stack to use - 0 is the final.
        "1",  # Fraction of particles to classify
        str(pixel_size),  # Pixel Size
        # "300", # keV
        # "2.7", # Cs
        # "0.07", # Amplitude Contrast
        str(mask_radius),  # Mask Radius in Angstroms
        str(low_res),  # Low Resolution Limit
        str(high_res),  # High Resolution Limit
        "0",  # Angular Search
        "0",  # XY search
        "1",  # Tuning
        "2",  # Tuning
        "Yes",  # Normalize?
        "Yes",  # INVERT?
        "No",  # Exclude blank edges
        automask_text,  # Automask
        autocenter_text,  # Autocenter
        "No",  # Dump Dats
        "No.dat",  # Datfilename
        "1",  # max threads
    ])
    p = subprocess.Popen("refine2d", stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    out, _ = p.communicate(input=input.encode('utf-8'))
    live2dlog.info(out.decode('utf-8'))


def refine_2d_subjob(process_number, round=0, input_star_filename="class_0.star", input_stack="combined_stack.mrcs", particles_per_process=100, mask_radius=150, low_res_limit=300, high_res_limit=40, class_fraction=1.0, particle_count=20000, pixel_size=1, angular_search_step=15.0, max_search_range=49.5, smoothing_factor=1.0, process_count=32, working_directory="~", automask=False, autocenter=True):
    """
    Call out to cisTEM2 ``refine2d`` using :py:func:`subprocess.Popen` to generate a new partial set of *Refined* classes for a slice of a particle stack (used in parallel with other slices).

    Args:
        start_cycle_number (int): Iteration number of the classification (indexes from 0 in :py:func:`execute_job_loop`)
        input_stack (str): Filename of combined monolithic particle stack
        particles_per_process (int): Number of particles to classify in this job.
        process_count (int): How many processes have run before this one (assumes other processes have classified the same number of particles).
        mask_radius (int): Radius in Å to use for mask (default 150).
        low_res (float): Low resolution cutoff for classification, in Å.
        high_res (float): High resolution cutoff for classification, in Å.
        class_fraction (float): Fraction of particles [0-1] in a section to classify. Values below 1 improve speed but have lower SNR in final classes.
        particle_count (int): Total number of particles in dataset.
        pixel_size (int): Pixel size of image files, in Å.
        angular_search_step (float): Angular step in degrees for the classification.
        max_search_range (float): XY search range in Å for the classification.
        working_directory (str): Directory where data will output.
        automask (bool): Automatically mask class averages
        autocenter (bool): Automatically center class averages to center of mass.
    Returns:
        str: STDOUT of :py:func:`subprocess.Popen` call to ``refine2d``.
    """
    start_time = time.time()
    live2dlog = logging.getLogger("live_2d")
    start = process_number*particles_per_process+1
    stop = (process_number+1)*particles_per_process
    if stop > particle_count:
        stop = particle_count

    automask_text = "No"
    if automask is True:
        automask_text = "Yes"
    autocenter_text = "No"
    if autocenter is True:
        autocenter_text = "Yes"

    input = "\n".join([
        os.path.join(working_directory, input_stack),  # Input MRCS stack
        os.path.join(working_directory, input_star_filename),  # Input Star file
        os.path.join(working_directory, "cycle_{0}.mrc".format(round)),  # Input MRC classes
        os.path.join(working_directory, "partial_classes_{0}_{1}.star".format(round+1, process_number)),  # Output Star file
        os.path.join(working_directory, "cycle_{0}.mrc".format(round+1)),  # Output MRC classes
        "0",  # number of classes to generate for the first time - only use when starting a NEW classification
        str(start),  # First particle in stack to use
        str(stop),  # Last particle in stack to use - 0 is the final.
        "{0:.2}".format(class_fraction),  # Fraction of particles to classify
        str(pixel_size),  # Pixel Size
        # "300", # keV
        # "2.7", # Cs
        # "0.07", # Amplitude Contrast
        str(mask_radius),  # Mask Radius in Angstroms
        str(low_res_limit),  # Low Resolution Limit
        str(high_res_limit),  # High Resolution Limit
        "{0}".format(angular_search_step),  # Angular Search
        "{0}".format(max_search_range),  # XY Search
        "{:.2f}".format(smoothing_factor),  # Tuning
        "2",  # Tuning
        "Yes",  # Normalize
        "Yes",  # Invert
        "No",  # Exclude blank edges
        automask_text,  # Automask
        autocenter_text,  # Autocenter
        "Yes",  # Dump Dat
        os.path.join(working_directory, "dump_file_{0}.dat".format(process_number+1)),
        "1",  # Max threads
    ])

    # if process_number=0:
    #     live2dlog.info(input)
    p = subprocess.Popen("refine2d", shell=True, stdout=asyncio.subprocess.PIPE, stdin=asyncio.subprocess.PIPE)
    out, _ = p.communicate(input=input.encode('utf-8'))
    end_time = time.time()
    total_time = end_time - start_time
    live2dlog.info("Successful return of process number {0} out of {1} in time {2:0.1f} seconds".format(process_number+1, process_count, total_time))
    return(out)


def merge_star_files(cycle: int, process_count: int, working_directory: str):
    """
    Combine output partial class star files from a parallelized ``refine2d`` job into a single monolithic cisTEM2 classification star file.

    Args:
        cycle (int): Iteration number for finding the partial classes and writing out the result.
        process_count (int): Number of processes used for parallelizing the ``refine2d`` job.
        working_directory (str): directory where new classes will be output.
    Returns:
        str: path to new classification star file.
    """
    live2dlog = logging.getLogger("live_2d")
    filename = os.path.join(working_directory, "cycle_{}.star".format(cycle+1))
    with open(filename, 'wb') as outfile:
        for process_number in range(process_count):
            with open(os.path.join(working_directory, "partial_classes_{}_{}.star".format(cycle+1, process_number)), 'rb') as infile:
                if process_number == 0:
                    for line in infile:
                        outfile.write(line)
                else:
                    for line in infile:
                        if not isheader(line):
                            outfile.write(line)
            try:
                os.remove(os.path.join(working_directory, "partial_classes_{}_{}.star".format(cycle+1, process_number)))
            except e as e:
                live2dlog.warn("Failed to remove file partial_classes_{}_{}.star".format(cycle+1, process_number))
    live2dlog.info("Finished writing cycle_{}.star".format(cycle+1))
    return filename


def merge_2d_subjob(cycle, working_directory, process_count=32):
    """
    Call out to cisTEM2 ``merge2d`` using :py:func:`subprocess.Popen` to complete a new set of *Refined* class ``.mrc`` files from partial classes output from ``refine2d``.

    Args:
        cycle (int): Iteration number for finding the partial classes and writing out the result.
        process_count (int): Number of processes used for parallelizing the ``refine2d`` job.
    """
    input = "\n".join([
        os.path.join(working_directory, "cycle_{0}.mrc".format(cycle+1)),
        os.path.join(working_directory, "dump_file_.dat"),
        str(process_count)
    ])
    p = subprocess.Popen("merge2d", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    out, _ = p.communicate(input=input.encode('utf-8'))
    live2dlog.info(out.decode('utf-8'))
    for i in range(process_count):
        try:
            os.remove(os.path.join(working_directory, "dump_file_{}.dat".format(i+1)))
        except e as e:
            live2dlog.warn("Failed to remove file dump_file_{}.dat".format(i+1))


def calculate_particle_statistics(filename, class_number=50, particles_per_class=300, process_count=32):
    """
    Determine fraction of total particles to classify for ab initio classifications, and number of particles that will be classified per process, and total number of particles in the monolithic stack.

    Args:
        filename (str): Monolithic particle star file
        class_number (int): Number of classes
        particles_per_class (int): Target number of particles per class
        process_count (int): Number of processes used for parallelization.
    Returns:
        int: Number of particles in stacks
        int: Number of particles per process.
        float: Fraction of particles in each process to actually classify.
    """
    with open(filename, "r") as f:
        i = 0
        j = 0
        for i, l in enumerate(f):
            if isheader(l):
                j += 1
            pass
        particle_count = i+1-j
    particles_per_process = int(ceil(particle_count / process_count))

    class_fraction = particles_per_class * class_number / particle_count

    if class_fraction > 1:
        class_fraction = 1.0
    return particle_count, particles_per_process, class_fraction


def append_new_particles(old_particles, new_particles, output_filename):
    """
    Merge new particles in an unclassified cisTEM2 star file onto the end of a star file generated during classification, to allow iterative refinement to incorporate new particles.

    Args:
        old_particles (str): Output particle star file from classification.
        new_particles (str): Monolithic star file containing all particles including new ones.
        output_filename (str): Filename for new combined star file.
    Returns:
        int: Total number of particles in new star file.
    """
    live2dlog = logging.getLogger("live_2d")

    with open(output_filename, 'w') as append_file:
        old_header_length = 0
        live2dlog.info(old_particles)
        with open(old_particles) as f:
            for i, l in enumerate(f):
                append_file.write(l)
                if isheader(l):
                    old_header_length += 1
        old_particle_count = i+1-old_header_length
        new_particles_count = 0
        new_header_length = 0
        with open(new_particles) as f2:
            for i, l in enumerate(f2):
                if isheader(l):
                    new_header_length += 1
                    continue
                if i == new_header_length + old_particle_count:
                    live2dlog.info(i)
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


def generate_star_file(stack_label, working_directory, previous_classes_bool=False, merge_star=True, recent_class="cycle_0", start_cycle_number=0):
    """Logic to either append particles or generate a whole new class.
    Uses :py:func:`find_previous_classes` and :py:func:`append_new_particles` and :py:func:`import_new_particles` to do all the heavy lifting.

    Args:
        stack_label (str): Base name (without extension) of monolithic particle stack combined from warp particle stacks.
        working_directory (str): Directory where :py:mod:`live_2d` will output.
        previous_classes_bool (bool): Have previous classifications been run?
        merge_star (bool): Should previous classifications be used?
        recent_class (str): Base name (without extension) of most recently completed classification output.
        start_cycle_number (int): Cycle number for naming new file if ``merge_star`` is ``false``
    Returns:
        str: filename of new combined star file.
    """
    live2dlog = logging.getLogger("live_2d")
    star_file = os.path.join(working_directory, "{}.star".format(stack_label))
    if previous_classes_bool and not merge_star:
        live2dlog.info("Previous classes will not be used, and a new star will be written at cycle_{}.star".format(start_cycle_number))
        new_star_file = os.path.join(working_directory, "cycle_{}.star".format(start_cycle_number))
        shutil.copy(star_file, new_star_file)
    elif previous_classes_bool:
        live2dlog.info("It looks like previous jobs have been run in this directory. The most recent output star file is: {}.star".format(recent_class))
        new_star_file = os.path.join(working_directory, "{}_appended.star".format(recent_class))
        live2dlog.info("Instead of cycle_0.star, the new particle information will be appended to the end of that star file and saved as {}".format("{}_appended.star".format(recent_class)))
        total_particles = append_new_particles(old_particles=os.path.join(working_directory, "{}.star".format(recent_class)), new_particles=star_file, output_filename=new_star_file)
        live2dlog.info(f"Total particles in new cycle: {total_particles}")
    else:
        live2dlog.info("No previous classification cycles were found. A new classification star file will be generated at cycle_0.star")
        new_star_file = os.path.join(working_directory, "cycle_0.star")
        shutil.copy(star_file, new_star_file)
    return new_star_file


if __name__ == "__main__":
    live2dlog = logging.getLogger("live_2d")
    live2dlog.info("This is a function library and should not be called directly.")
    import_new_particles("combined_stack_test.mrcs", "/gne/data/cryoem/DATA_COLLECTIONS/WARP/190730_Proteasome_Krios_grid_001803_session_000794/", "allparticles_GenentechNet2Mask_20190730.star", "/gne/data/cryoem/DATA_COLLECTIONS/WARP/190730_Proteasome_Krios_grid_001803_session_000794/classification", new_net=True)
    # live2dlog.info("Testing particle import with streaming")
    # stack_label="streaming_combine"
    # warp_folder = "/local/scratch/krios/Warp_Transfers/TestData"
    # warp_star_filename = "allparticles_GenentechNet2Mask_20190627.star"
    # working_directory = "/gne/scratch/u/baradb/outputdata"
    # import_new_particles(stack_label, warp_folder, warp_star_filename, working_directory)
