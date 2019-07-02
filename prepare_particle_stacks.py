### Process warp data to prepare for Frealign. Requires relion_preprocess and star_to_par.com

import glob
import os
import subprocess
import time


warp_working_directory = "/local/scratch/krios/Warp_Transfers/TestData"
star_file = "all_particles_short.star"
starting_directory = os.getcwd()
working_directory = "/local/scratch/baradb/outputdata"
pixel_size = 1.2007

times = []
times.append(time.time())
# print("Combining Stacks of Particles from Warp")
# print("==============================")
# os.chdir(warp_working_directory)
#
# p = subprocess.call(['/gne/home/baradb/relion/build/bin/relion_preprocess --operate_on {0} --operate_out {1}/single_stacked'.format(star_file, working_directory)], shell=True) # Do not run shell=True outside of intranet!
#
# times.append(time.time())
# print("Time to produce the combined stack: {0:.2f} s".format(times[-1]-times[-2]))
os.chdir(working_directory)

# Check if previous classes_N.par files exist
file_list = glob.glob("classes_*.par")
recent_job = sorted(file_list, key=lambda f: int(f.rsplit(os.path.extsep, 1)[0].rsplit("_",1)[-1]))[-1]
if len(file_list) > 0:
    print("It looks like previous jobs have been run in this directory. The most recent output class is: {}".format(recent_job))
    print("Instead of classes_0.par, the new particles will be appended to the end of that par file and saved as {}".format(os.path.splitext(recent_job)[0]+"_appended.par"))




# Star to frealign makes the initial par file, which I am naming classes_0.par for the purposes of making the 2d classification numbered consistently.
# p = subprocess.Popen("/gne/home/baradb/star_to_frealign.com", shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
# out, _ = p.communicate(input="single_stacked.star\nclasses_0.par\n{0}".format(pixel_size).encode('utf-8'))
# times.append(time.time())
# print(out.decode('utf-8'))
# print("Time to produce the par file: {0:.2f} s".format(times[-1]-times[-2]))
