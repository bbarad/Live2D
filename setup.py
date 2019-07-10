from setuptools import setup, find_packages

requires = [
    'tornado',
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
