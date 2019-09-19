#!/usr/bin/env python
""" Live2D is a lightweight application for automated generation of 2D classes iteratively during collection of single particle electron microscopy data. It works in concert with Warp on-the-fly processing and uses cisTEM 2's 2d classification utilities.

After installation, run the application with ``live2d``. Server configurations and latest run data can be found in ``~/.live2d/`` (or ``%USERPROFILE%\.live2d`` in windows land)
"""

from setuptools import setup, find_packages

requires = [
    'tornado>=6.0.2',
    "mrcfile>=1.1.2",
    "multiprocess>=0.70.8",
    "numpy>=1.16.2",
    "pandas>=0.24.2",
    "pyem @ git+https://github.com/bbarad/pyem.git@58fc29e7b27a55d46ac78357b246f37819bfb3ee#egg=pyem",
    "scipy>=1.2.1",
    "terminado>=0.8.1",
    "Sphinx==2.2.0",
    "uvloop==0.13.0"
]

setup(
    name="live2d",
    version="0.9",
    description="Web-interface (tornado driven) for on-the-fly 2d classification of single particle electron microscopy data using warp and cistem",
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
