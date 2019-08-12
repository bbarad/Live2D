# Live 2D Classification from Warp
The Live2D tool is a lightweight python-based application to do semi-automated 2D
classification of cryoEM particles simultaneously with data collection. It operates using a web interface for the frontend and uses Warp and cisTEM 2 on the backend.

## Getting Started
These instructions will get Live2D functioning on your local machine. It is recommended to install one copy per microscope onto separate workstations - it is a CPU-heavy multi-process application and is currently tested for linux only (but should in theory work for windows). Performance scales well up to 32 cores tested.

This application cannot currently be installed on a cluster, but we are interested in extending it to do so.

### Prerequisites
* [cisTEM](https://cistem.org/) >= 2.0.0 - cisTEM version must be using STAR files instead of PAR files.
* [Warp](http://www.warpem.com/warp/) on a separate workstation (same computer behavior is untested, but warp is GPU-limited while live2D is CPU-limited, so they may place nice together).
  * The application requires that warp has been set up with `Pick Particles` and `Export Particle Coordinates` setting checked.
* Python 3

### Installation

Clone this repository.

Edit your `.bashrc` or `.zshrc` to ensure that the default shell has `refine2d` and `merge2d` in the `$PATH`.

```
cd $REPOSITORY
pip install requirements.txt
cd $live_2d
cp latest_run.json.template latest_run.json
```

You may want to edit `latest_run.json` and modify `process_number` - this is the number of processors that will be used for `refine2d` jobs, and should never be greater than the number of logical cores available to the workstation. By default, `process_number` is `32`, but increasing it will dramatically improve performance.

### Running the server
The application runs via a [Tornado](https://www.tornadoweb.org/en/stable/) server in python. By default, the application runs on port `8181`. This behavior is user configurable. The server must be run by a user with read and write permissions to the folder that Warp is working in.

```
python3 live_2d/__init__.py
```
or
```
python3 live_2d/__init__.py --port=$LIVE2D_PORT
```

__This application currently does not do any user authentication. Ensure that the port you choose is only accessible on the network. For additional security, make sure that the port is not exposed at all, and that the website can only be viewed from the local machine.__

This will launch the [Tornado](https://www.tornadoweb.org/en/stable/) server. After this, the website can be viewed in any modern browser (any with support for [websockets](https://caniuse.com/#feat=websockets)) at `http://$HOSTNAME:$LIVE2D_PORT` (or `http://$HOSTNAME` if you used port `8080`, or `http://localhost:$LIVE2D_PORT` if you are viewing on the same machine the server is running on). It is recommended to run the server in a detachable session (`screen` or `tmux` can help with this) in order to allow it run to for long periods of time - under ideal circumstances, the server should be able to do many live 2d classifications between re-initializations.

## Using the Server
The website is organized with user controls in a panel on the left and results in a larger panel on the right. When the application is first opened, no results are available, and none will be visible. The server has global state - that is, individual users for the most part are looking at the same information at all times. If you open a new page, on your phone, the same computer, or a different computer, it should present the same information to all of those pages. Within a page, you can stage settings changes (which get sent to the server and all other open clients on job submission) and browse through previous results.

### Setting up your job
The user's first action should be to change the directory by clicking the __Update Warp Directory__ button. This will open a modal with a dialog asking for a new warp folder. Enter the full path to the folder where warp is reading movies and writing out its results (you set that directory up in the Warp gui, but it may be a slightly different path depending on whether you use a `Samba` fileshare or other way to make files accessible to windows) and click __OK__. If Warp has run or is running in that folder, the server will read the `previous.settings` file output by warp in that folder and set up a new `classification` subfolder in the same directory that will house results from 2d classification.

One a warp folder is successfully opened, most 2d classification-related settings are automatically pulled from warp, including guessing that the mask radius is likely to be the same as the particle size used to pick particles in Warp. Remaining settings are laid out in the __User Settings__ and __Expert Settings__ tabs, which can be collapsed or expanded by clicking on them.

### Starting a job

Three buttons are available: __Start Job Now__, __Start Automatic Jobs__, and __Stop All Jobs__.
* __Start Job Now__ sends user-chosen settings to the server and then triggers an immediate 2D classification job, which iteratively runs `refine2d` at different resolution cutoffs and subsets of particles, mimicking the behavior of the 2D classification job in the cisTEM GUI. When this kind of job finishes, automatic jobs are automatically started.
* __Start Automatic Jobs__ sends user-chosen settings to the server and then tells the server to begin watching for new particles being picked by Warp. The server will trigger jobs automatically at regular intervals (which can be changed in the __Expert Settings__ tab).
* __Stop All Jobs__ immediately stops the system from watching for new particles from Warp, and will end any currently running jobs after the next iteration of `refine2d`. This can take a long time when many particles have been picked by warp, but in order to avoid unexpected behaviors, there is no current way to kill a job in the middle of a `refine2d` iteration. Killing and restarting the server will stop a job mid-run, but do this at your own risk! There is a chance damage the configuration settings file for the server, requiring manual       fixes                    

Clicking either of the __Start__ buttons will send the settings chosen by user, and are the only time user settings get sent to the server.

### Settings Overview

#### User Settings
Very good results can be achieved by only interacting with these two settings. Start with just these settings, and then move to __Expert Settings__ to improve performance only when necessary.

__Mask Radius__  
The radius of the circular mask applied to the class averages before new rounds of classification. This value should be a little bit larger than your particle.

__Classification Type__  
This setting switches between 3 macro programs for 2D classification.  
* _Ab Initio_ - Perform a classification from random seed classes, starting at low resolution (40Å by default) and iteratively increasing the resolution cutoff with a small set of the particles, followed by several rounds of classification with 100% of particles at high resolution (8Å by default). When no previous classes have been calculated for the current set of warp-generated particles, this is the required option. Before classes are clearly resolvable as different views of the target, this is a good default behavior. When an _Ab Initio_ job finishes, the setting for the next automated run is changed to _Seeded Startup_.
* _Seeded Startup_ - Perform a series of classifications that start at low resolution and iteratively improves, using the most recently generated classes as the starting point for classification, then perform several rounds of classification at the high resolution cutoff. Uses all particles from the beginning, unlike _Ab Initio_. This is the setting that should be used for the majority of the data collection, and is the default after the first job if automatic jobs are run from the beginning. Should not be used until enough particles have been collected to get clearly distinguishable class averages - generally around 50k particles is plenty, and sometimes this setting can be changed sooner than that if the classes look good. When hundreds of thousands to millions of particles have been collected, this setting can begin to take 10+ hours, and if the classes are already very good, new particles can instead be more efficiently incorporated with the _Refinement_ setting.
* _Refinement_ - Perform a series of classifications with the most recent set of classes as a starting point, with all classifications at the high resolution cutoff and using all particles. High chance of overfitting to local minima - only switch to this when the existing classes are very good and enough particles have been collected that seeded startups are prohibitively slow.

#### Expert Settings
__Initial High Res Limit__  
This is the high resolution limit used at the beginning of _Ab Initio_ and _Seeded Startup_ runs. Generally, leaving this at 40Å is best, but when a decent number of particles are picked and classes are good but not good enough yet for _Refinement_ raising this limit to 20Å or better and decreasing the corresponding number of __Startup Cycles__ can improve speed with minimal impact on quality.

__Final High Res Limit__  
This is the final high resolution limit for _Ab Initio_ and _Seeded Startup_ runs, which will iteratively increase resolution from the __Initial High Res Limit__ to this number, and the resolution limit used for all _Refinement_ classification jobs. Leaving it at 8Å is safe generally, but cisTEM lets you change it, so I thought I should too.

__Startup Cycles__  
The number of cycles in _Ab Initio_ and _Seeded Startup_ jobs to move from the __Initial High Res Limit__ to the __Final High Res Limit__. Resolution will increase linearly over this number of cycles (so 40 to 8 in 15 cycles means the resolution will improve by ~2.3Å per cycle). This number is ignored in _Refinement_ runs. For _Seeded Startup_ runs, you can decrease this number along with raising the __Initial High Res Limit__ to get faster classification and corresponding faster incorporation of new particles, at the cost of some risk of overfitting to local minima when the starting classes are poor.

__Refinement Cycles__  
The number of cycles to perform with all particles at the maximum resolution. _Refinement_ runs only use this number of jobs. For _Refinement_ jobs when hundreds of thousands of particles have been collected, decreasing this number so that new particles are incorporated more often is advised - I often drop it to 2 cycles in _Refinement_ mode after a million particles have been picked by Warp. It is a good idea to leave this number at 3 or above for _Ab Initio_ and _Seeded Startup_ runs, as the classes will often improve a lot in the first few high resolution classifications after starting from a low resolution seed.

__Particle Count Before Starting__  
This is the threshold number used by the automated job starter to trigger the first classification job for a warp run - when no classes exist at all. If you change your warp settings and have to do a new _Ab Initio_ run, this is not the setting that will be used in that case - this only gets used for the very first class. Despite this setting existing, the authors usually trigger the first job manually once sufficient particles (at least 15k, but the default is 50k) particles are picked.

__Additional Particle Count Before Update__  
Number of additional particles that need to be picked by warp before triggering a new job. Often late in runs more particles than this will be picked before a _Seeded Startup_ job completes, unless you change settings above. Early on, dropping this to 50k can give faster feedback on whether a good variety of views are getting picked by warp.

__Number of Classes__    
The number of classes to be generated during an _Ab Initio_ job. 50 is generally a good number, but this can be guided by previous cisTEM classifications of this or similar proteins.

__Initial Particles Per Class__  
The number of particles per class to be used for the startup runs in _Ab Initio_ jobs, when a subset of particles are used. 300 is the cisTEM default.

__Automask__  
This flag tells cisTEM to try to automatically mask class averages.

__Autocenter__
This flag tells cisTEM to automatically center class averages to their center of mass.


### Results Panel
The results panel is organized into two subpanels: __Classes__ and __Job Output__.

__Classes__  
This is the primary output subpanel for users to be focused on. When first loaded, it displays the latest set of class averages from live processing. At the top of the panel are two different ways of selecting previous classes, which is useful for following the trajectory of classification and seeing how addition of new particles has impacted classification (which may be useful for deciding when to stop). Below that is a small amount of metadata about the current classification displayed. Finally, all of the class averages are displayed in columns resized to ~180 pixels wide and tall. Clicking on a class average brings up a modal with the full size class average (up to the size of the results panel) as well as the number of particles in the class. In this view, the left and right arrow keys can switch between class averages. This view is recommended for determining the detail level available in the images.

__Job Output__  
This subpanel has the last 1000 lines of the processing log available. It can be used to get information about processing, and generally should have errors logged (See [When Something Goes Terribly Wrong](#when-something-goes-terribly-wrong)).

## When something goes terribly wrong
Sometimes something goes wrong - the filesystem breaks down for a moment, a websocket sends something really uninterpretable by the server, or someone updates cisTEM and suddenly all the paths are different!

When this happens, the easiest thing to do is generally to kill the server process with a `SIGINT` message (`ctrl+C` on linux/mac) and restart it. Generally, you will reinitialize with the same state as you were in before the crash (no need to repeat the setup), and can continue without problem. Occasionally, the program will not relaunch (or will soon crash again) for one of a few reasons.

1. Check that the warp folder is accessible and that the server account has write access - if either changes, the program will not work and will be very unhappy.
2. Check that the `latest_run.json` file in the folder the server runs from (usually the git repository folder) is correctly formed - occasionally an error can occur during writing and it will end up malformed. If this happens, copy the `latest_run.json` file from the `$WARP_FOLDER/classification/` directory into the server's base directory. You might lose the most recent class (if it was the one that the write failed on) but that should be the maximum amount of data you lose.
3. Check that the server account's path has `refine2d` and `merge2d` from cisTEM in it - generally, if `cisTEM` is in your path, they will be too.
4. Try pulling the latest version of the github repository - occasionally, something changes in `refine2d` or `merge2d`, and the inputs sent by live2d need to be changed accordingly. Generally we will stay on top of this, and you can get the fix quickly.
5. Open an issue on Roche Stash or Github. You may have found a novel bug.
