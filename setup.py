from setuptools import setup, find_packages

requires = [
    'tornado>=6.0.2',
    "mrcfile>=1.1.2",
    "multiprocess>=0.70.8",
    "numpy>=1.16.2",
    "pandas>=0.24.2",
    "-e git+https://github.com/bbarad/pyem.git@58fc29e7b27a55d46ac78357b246f37819bfb3ee#egg=pyem",
    "scipy>=1.2.1",
    "terminado>=0.8.1",
]

setup(
    name="live_2d_classification",
    version="0.0",
    description="Web-interfaced (tornado driven) live 2d classification using warp and cistem",
    author="Benjamin Barad",
    author_email="baradb@gene.com",
    keywords="cryoem warp cistem tornado",
    packages=find_packages(),
    install_requires=requires,
    python_requires=">=3.5",
    entry_points={
        'console_scripts': [
            'serve_app = live_2d:main',
        ]
    }
)
