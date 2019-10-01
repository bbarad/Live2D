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

import glob
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
    if string.startswith("_".encode("utf-8")):
        return True
    if string.startswith("#".encode("utf-8")):
        return True
    if string.startswith("data_".encode("utf-8")):
        return True
    if string.startswith("loop_".encode("utf-8")):
        return True
    if string.isspace():
        return True
    return False


def make_photos(basename, working_directory):
    if not os.path.isdir(os.path.join(working_directory, "class_images")):
        os.mkdir(os.path.join(working_directory, "class_images"))
    if not os.path.isdir(os.path.join(working_directory, "class_images", basename)):
        os.mkdir(os.path.join(working_directory, "class_images", basename))
    photo_dir = os.path.join(working_directory, "class_images", basename)
    with mrcfile.open("{}.mrc".format(basename), "r") as stack:
        for index, item in enumerate(stack.data):
            imageio.imwrite(os.path.join(photo_dir, "{}.png".format(index+1)), item)
    return photo_dir


def change_warp_folder(new_folder):
    pass


def load_star_as_dataframe(star_filename):
    """Generate a pandas dataframe from a star file with one single data loop.
    Written for high efficiency. Star headers have the leading _ stripped and are turned into the pandas header.
    Extra comment lines after the header loop_ are currently unsupported and should be removed. before loading.

    Args:
        star_filename (str): Filename of the star file from Warp (relion style)
    returns:
        :py:class:`pandas.Dataframe`: dataframe from the star file.
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


def import_new_particles(stack_label, warp_folder, warp_star_filename, working_directory, new_net=False):
    """Function to generate new image stacks based only on the results of the first stack. Also, while I am doing it, I will write out a base star file to use for appending and/or regenerating for further class files.
    I am doing everything using a memory mapped mrc file. This does not allow easy appending, so I am writing directly to the memory map once it is created as a numpy mmap, then I am reloading as an mrcfile mmap and fixing the header."""
    print("=======================================")
    print("Combining Stacks of Particles from Warp")
    print("=======================================")
    start_time = time.time()
    combined_filename = "{}/{}.mrcs".format(working_directory, stack_label)
    previous_file = os.path.isfile(combined_filename)
    if new_net:
        # Hack to overwrite the old file if you switch to a new neural net.
        previous_file = False
    os.chdir(warp_folder)
    total_particles = load_star_as_dataframe(warp_star_filename)
    print(len(total_particles))
    stacks_filenames = total_particles["rlnImageName"].str.rsplit("@").str.get(-1)

    # MAKE PRELIMINARY STACK IF ITS NOT THERE
    if not previous_file:
        print("Copying first mrcs file to generate seed for combined stack")
        shutil.copy(stacks_filenames[0], combined_filename)

    # GET INFO ABOUT STACKS
    with mrcfile.mmap(combined_filename, "r", permissive=True) as mrcs:
        prev_par = int(mrcs.header.nz)
        print("Previous Particles: {}".format(prev_par))
        new_particles_count = len(total_particles) - prev_par
        print("Total Particles to Import: {}".format(new_particles_count))
        offset = mrcs.data.base.size()
        # print("Bytes Offset: {}".format(offset))
        data_dtype = mrcs.data.dtype
        # print("dtype: {}".format(data_dtype))
        # print("dtype size: {}".format(data_dtype.itemsize))
        shape = (new_particles_count, mrcs.header.ny, mrcs.header.nx)

    # OPEN THE MEMMAP AND ITERATIVELY ADD NEW PARTICLES
    mrcfile_raw = np.memmap(combined_filename, dtype=data_dtype, offset=offset, shape=shape, mode="r+")
    new_offset = 0
    new_filenames = stacks_filenames[prev_par:].unique()
    for index, filename in enumerate(new_filenames):
        with mrcfile.mmap(filename, "r", permissive=True) as partial_mrcs:
            _ = partial_mrcs.header.nx
            _ = partial_mrcs.header.ny
            z = partial_mrcs.header.nz
            print("Filename {} ({} of {}) contributing {} particles starting at {}".format(filename, index+1, len(new_filenames), z, new_offset))
            mrcfile_raw[new_offset:new_offset+z, :, :] = partial_mrcs.data
            new_offset = new_offset+z
    mrcfile_raw.flush()
    del mrcfile_raw
    # FIX THE HEADER
    with mrcfile.mmap(combined_filename, "r+", permissive=True) as mrcs:
        mrcs.header.nz = mrcs.header.mz = len(total_particles)

    os.chdir(working_directory)
    # WRITE OUT STAR FILE
    with open("{}/{}.star".format(working_directory, stack_label), "w") as file:
        file.write("\0\ndata_\n\0\nloop_\n")
        input = ["{} #{}".format(value, index+1) for index, value in enumerate([
            "_cisTEMPositionInStack",
            "_cisTEMAnglePsi",
            "_cisTEMAngleTheta",
            "_cisTEMAnglePhi",
            "_cisTEMXShift",
            "_cisTEMYShift",
            "_cisTEMDefocus1",
            "_cisTEMDefocus2",
            "_cisTEMDefocusAngle",
            "_cisTEMPhaseShift",
            "_cisTEMImageActivity",
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
        ])]
        file.write("\n".join(input))
        file.write("\n")
        for row in total_particles.itertuples(index=True):
            row_data = [
                str(row.Index+1),
                "0.00",
                "0.00",
                "0.00",
                "-0.00",
                "-0.00",
                str(row.rlnDefocusU),
                str(row.rlnDefocusV),
                str(row.rlnDefocusAngle),
                "0.0",
                "0",
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
            ]
            file.write("\t".join(row_data))
            file.write("\n")

    end_time = time.time()
    print("Total Time: {}s".format(end_time - start_time))


def generate_new_classes(class_number=50, input_stack="combined_stack.mrcs", pixel_size=1.2007, low_res=300, high_res=40):
    print("====================")
    print("Preparing 2D Classes")
    print("====================")
    input = "\n".join([
        input_stack,  # Input MRCS stack
        "classes_0.star",  # Input Star file
        os.devnull,  # Input MRC classes
        os.devnull,  # Output star file
        "classes_0.mrc",  # Output MRC class
        str(class_number),  # number of classes to generate for the first time - only use when starting a NEW classification
        "1",  # First particle in stack to use
        "0",  # Last particle in stack to use - 0 is the final.
        "1",  # Fraction of particles to classify
        str(pixel_size),  # Pixel Size
        # "300", # keV
        # "2.7", # Cs
        # "0.07", # Amplitude Contrast
        "150",  # Mask Radius in Angstroms
        str(low_res),  # Low Resolution Limit
        str(high_res),  # High Resolution Limit
        "0",  # Angular Search
        "0",  # XY search
        "1",  # Tuning
        "2",  # Tuning
        "Yes",  # Normalize?
        "Yes",  # INVERT?
        "No",  # Exclude blank edges
        "Yes",  # Automask
        "Yes",  # Autocenter
        "No",  # Dump Dats
        "No.dat",  # Datfilename,
        "1",  # max threads
    ])
    p = subprocess.Popen("/gne/home/rohoua/software/cisTEM2/r813/bin/refine2d", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    out, _ = p.communicate(input=input.encode('utf-8'))
    print(out.decode('utf-8'))


def refine_2d_subjob(process_number, round=0, input_star_filename="classes_0.star", input_stack="combined_stack.mrcs", particles_per_process=100, low_res_limit=300, high_res_limit=40, class_fraction=1.0, particle_count=20000, pixel_size=1, angular_search_step=15.0, max_search_range=49.5, process_count=32):
    import time
    start_time = time.time()
    start = process_number*particles_per_process+1
    stop = (process_number+1)*particles_per_process
    if stop > particle_count:
        stop = particle_count
    input = "\n".join([
        input_stack,  # Input MRCS stack
        input_star_filename,  # Input Star file
        "classes_{0}.mrc".format(round),  # Input MRC classes
        "partial_classes_{0}_{1}.star".format(round+1, process_number),  # Output Star file
        "classes_{0}.mrc".format(round+1),  # Output MRC classes
        "0",  # number of classes to generate for the first time - only use when starting a NEW classification
        str(start),  # First particle in stack to use
        str(stop),  # Last particle in stack to use - 0 is the final.
        "{0:.2}".format(class_fraction),  # Fraction of particles to classify
        str(pixel_size),  # Pixel Size
        # "300", # keV
        # "2.7", # Cs
        # "0.07", # Amplitude Contrast
        "150",  # Mask Radius in Angstroms
        str(low_res_limit),  # Low Resolution Limit
        str(high_res_limit),  # High Resolution Limit
        "{0}".format(angular_search_step),  # Angular Search
        "{0}".format(max_search_range),  # XY Search
        "1",  # Tuning
        "2",  # Tuning
        "Yes",  # Normalize
        "Yes",  # invert
        "No",  # Exclude blank edges
        "Yes",  # Automask
        "Yes",  # Autocenter
        "Yes",  # Dump Dat
        "dump_file_{0}.dat".format(process_number+1),
        "1",  # Max threads
    ])
    # if process_number=0:
    #     print(input)
    p = subprocess.Popen("/gne/home/rohoua/software/cisTEM2/r813/bin/refine2d", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    out, _ = p.communicate(input=input.encode('utf-8'))
    end_time = time.time()
    time = end_time - start_time
    print("Successful return of process number {0} out of {1} in time {2:0.1f} seconds".format(process_number+1, process_count, time))
    return(out)


def merge_star_files(cycle, process_count=32):
    filename = "classes_{}.star".format(cycle+1)
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
    print("Finished writing classes_{}.star".format(cycle+1))
    return "classes_{}.star".format(cycle+1)


def merge_2d_subjob(cycle, process_count=32):
    input = "\n".join([
        "classes_{0}.mrc".format(cycle+1),
        "dump_file_.dat",
        str(process_count)
    ])
    p = subprocess.Popen("/gne/home/rohoua/software/cisTEM2/r813/bin/merge2d", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    out, _ = p.communicate(input=input.encode('utf-8'))
    print(out.decode('utf-8'))
    for i in range(process_count):
        p = subprocess.Popen("/bin/rm dump_file_{}.dat".format(i+1), shell=True)


def calculate_particle_statistics(filename, class_number=50, particles_per_class=300, process_count=32):
    with open(filename, "rb") as f:
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
    with open(output_filename, 'w') as append_file:
        old_header_length = 0
        with open(old_particles) as f:
            for i, l in enumerate(f):
                append_file.write(l)
                if isheader(l):
                    old_header_length += 1
        old_particle_count = i+1-old_header_length
        new_particles_count = 0
        print(old_particle_count)
        new_header_length = 0
        with open(new_particles) as f2:
            for i, l in enumerate(f2):
                if isheader(l):
                    new_header_length += 1
                    continue
                if i == new_header_length + old_particle_count:
                    print(i)
                if i > new_header_length + old_particle_count:
                    append_file.write(l)
                    new_particles_count += 1
        print(new_particles_count)
    return new_particles_count+old_particle_count


def find_previous_classes():
    file_list = glob.glob("classes_*.star")
    if len(file_list) > 0:
        previous_classes_bool = True
        recent_class = sorted(file_list, key=lambda f: int(f.rsplit(os.path.extsep, 1)[0].rsplit("_")[1]))[-1]
        cycle_number = int(recent_class.rsplit(os.path.extsep, 1)[0].rsplit("_")[1])
    else:
        previous_classes_bool = False
        recent_class = "classes_0.star"
        cycle_number = 0
    return previous_classes_bool, recent_class, cycle_number


def generate_star_file(stack_label, previous_classes_bool=False, recent_class="classes_0.star"):
    """Wrapper logic to either append particles or generate a whole new class.
    Uses find_previous_classes and append_new_particles and import_new_particles to do all the heavy lifting."""
    star_file = "{}.star".format(stack_label)
    if previous_classes_bool:
        print("It looks like previous jobs have been run in this directory. The most recent output class is: {}".format(recent_class))
        new_star_file = os.path.splitext(recent_class)[0]+"_appended.star"
        print("Instead of classes_0.star, the new particles will be appended to the end of that par file and saved as {}".format(new_star_file))
        _ = append_new_particles(old_particles=recent_class, new_particles=star_file, output_filename=new_star_file)
    else:
        print("No previous classes were found. A new par file will be generated at classes_0.star")
        new_star_file = "classes_0.star"
        shutil.copy(star_file, new_star_file)
    return new_star_file


if __name__ == "__main__":
    print("This is a function library and should not be called directly.")
