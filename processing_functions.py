import itertools
from math import ceil
import os
import subprocess

def import_new_particles(stack_label, warp_folder, warp_star_filename, working_directory):
    print("Combining Stacks of Particles from Warp")
    print("==============================")
    os.chdir(warp_folder)

    p = subprocess.call(['/gne/home/baradb/relion/build/bin/relion_preprocess --operate_on {0} --operate_out {1}/{2}'.format(warp_star_filename, working_directory, stack_label)], shell=True) # Do not run shell=True outside of intranet!

    os.chdir(working_directory)


def generate_new_classes(class_number=50, pixel_size=1.2007, low_res = 300, high_res = 40):
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
        str(low_res), # Low Resolution Limit
        str(high_res), # High Resolution Limit
        "0", #
        "0",
        "0",
        "1",
        "2",
        "Yes", # Normalize?
        "Yes", # INVERT?
        "No",
        "No",
        "No.dat"
    ])
    p = subprocess.Popen("/gne/home/rohoua/software/cisTEM2/r796_dbg/bin/refine2d", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    out,_ = p.communicate(input=input.encode('utf-8'))
    print(out.decode('utf-8'))

def refine_2d_subjob(process_number, round=0, particles_per_process = 100,low_res_limit=300, high_res_limit = 40, class_fraction = 1.0, particle_count=20000, pixel_size=1, angular_search_step=15.0, max_search_range=49.5, process_count=32, append=False):
    import time
    start_time = time.time()
    start = process_number*particles_per_process+1
    stop = (process_number+1)*particles_per_process
    if stop > particle_count:
        stop = particle_count
    # print(start,stop)
    if append:
        append_str="_appended"
    else:
        append_str=""
    input = "\n".join([
        "single_stacked.mrcs", # Input MRCS stack
        "classes_{0}{1}.par".format(round, append_str), # Input Par file
        "classes_{0}.mrc".format(round), # Input MRC classes
        "partial_classes_{0}_{1}.par".format(round+1, process_number), # Output par file
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
        "No",
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

def merge_par_files(cycle, process_count=32):
    filename = "classes_{}.par".format(cycle+1)
    with open(filename, 'wb') as outfile:
        for process_number in range(process_count):
            with open("partial_classes_{}_{}.par".format(cycle+1, process_number), 'rb') as infile:
                if process_number == 0:
                    for line in itertools.islice(infile, 0, None):
                        outfile.write(line)
                else:
                    for line in itertools.islice(infile, 28, None):
                        outfile.write(line)
            subprocess.Popen("/bin/rm partial_classes_{}_{}.par".format(cycle+1, process_number), shell=True)
    print("Finished writing classes_{}.par".format(cycle+1))

def merge_2d_subjob(cycle, process_count=32):
    input = "\n".join([
        "classes_{0}.mrc".format(cycle+1),
        "dump_file_.dat",
        str(process_count)
    ])
    p = subprocess.Popen("/gne/home/rohoua/software/cisTEM2/r796_dbg/bin/merge2d", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    out,_ = p.communicate(input=input.encode('utf-8'))
    print(out.decode('utf-8'))

def calculate_particle_statistics(filename, class_number=50, particles_per_class=300, process_count = 32):
    with open(filename) as f:
        for i,l in enumerate(f):
            pass
        particle_count = i+1

    particles_per_process = int(ceil(particle_count / process_count))

    class_fraction = 300.0 * class_number / particle_count

    if class_fraction > 1:
        class_fraction = 1.0
    return particle_count, particles_per_process, class_fraction

def append_new_particles(old_particles, new_particles, output_filename):
    with open(output_filename, 'w') as append_file:
        old_header_length = 0
        with open(old_particles) as f:
            for i,l in enumerate(f):
                append_file.write(l)
                if l.startswith("C"):
                    old_header_length += 1
                pass
        old_particle_count = i+1-old_header_length
        new_particles_count = 0
        print(old_particle_count)
        with open(new_particles) as f2:
            for l in itertools.islice(f2, old_particle_count, None):
                append_file.write(l)
                new_particles_count += 1
        print(new_particles_count)
    return new_particles_count+old_particle_count

def find_previous_classes():
    file_list = glob.glob("classes_*.par")
    if len(file_list) > 0:
        previous_classes_bool=True
        recent_class = sorted(file_list, key=lambda f: int(f.rsplit(os.path.extsep, 1)[0].rsplit("_")[1]))[-1]
        cycle_number = int(f.rsplit(os.path.extsep, 1)[0].rsplit("_")[1])
    else:
        previous_classes = False
        recent_class = ""
        cycle_number = 0
    return previous_classes_bool, recent_class, cycle_number


def generate_par_file(stack_label, pixel_size=1.0, previous_classes_bool=False, recent_class = "classes_0.par"):
    if previous_classes_bool:
        print("It looks like previous jobs have been run in this directory. The most recent output class is: {}".format(recent_class))
        new_par_file = os.path.splitext(recent_class)[0]+"_appended.par"
        print("Instead of classes_0.par, the new particles will be appended to the end of that par file and saved as {}".format(new_par_file))
        par_label = "temp.par"
        p = subprocess.Popen("/gne/home/baradb/star_to_frealign.com", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        out, _ = p.communicate(input="{0}.star\n{1}\n{2}".format(stack_label, par_label, pixel_size).encode('utf-8'))
        total_particles = append_new_particles(old_particles=recent_job, new_particles=par_label, output_filename = new_par_file)
        subprocess.Popen("/bin/rm {}".format(par_label), shell=True)
        print(out.decode('utf-8'))

        print("Time to produce the par file: {0:.2f} s".format(times[-1]-times[-2]))
    else:
        print("No previous classes were found. A new par file will be generated at classes_0.par")
        new_par_file = "classes_0.par"
        p = subprocess.Popen("/gne/home/baradb/star_to_frealign.com", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        out, _ = p.communicate(input="{0}.star\n{1}\n{2}".format(stack_label, new_par_file, pixel_size).encode('utf-8'))

    return new_par_file





if __name__=="__main__":
    print("This is a function library and should not be called directly.")
