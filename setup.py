#!/usr/bin/env python

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

""" Live2D is a lightweight application for automated generation of 2D classes iteratively during collection of single particle electron microscopy data. It works in concert with Warp on-the-fly processing and uses cisTEM 2's 2d classification utilities.

After installation, run the application with ``live2d``. Server configurations and latest run data can be found in ``~/.live2d/`` (or ``%USERPROFILE%\.live2d\`` in windows land).

This live2d version is built against warp 1.0.7 and cisTEM 2 r1145. Changes to the interfaces of either app may require updating Live2D.
"""

from setuptools import setup, find_packages

requires = [
    'tornado>=6.0.2',
    "mrcfile>=1.1.2",
    "multiprocess>=0.70.8",
    "numpy>=1.16.2",
    "pandas>=0.24.2",
    "imageio>=2.5.0",
    "terminado>=0.8.1",
    "Sphinx==2.2.0",
    "uvloop==0.13.0"
]

setup(
    name="live2d",
    version="1.0.2",
    description="Web-interface (tornado driven) for on-the-fly 2d classification of single particle electron microscopy data using warp and cisTEM",
    author="Benjamin Barad",
    author_email="benjamin.barad@gmail.com",
    keywords="cryoem warp cistem tornado ",
    packages=find_packages(),
    install_requires=requires,
    python_requires=">=3.7",
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'live2d = live2d:main',
        ]
    }
)
