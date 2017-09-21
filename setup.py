#! /usr/bin/python

from setuptools import setup, find_packages
import os.path

versionfile = os.path.join(os.path.dirname(__file__), "pieshell/version.py")
with open(versionfile) as f:
    exec f.read()

setup(
    name = "pieshell",
    description = "Pieshell is a Python shell environment that combines the expressiveness of shell pipelines with the prower of python iterators. It can be used both as an interactive shell and as an ordinary python module replacing e.g. subprocess.Popen",
    keywords = "Python shell pipelines suprocess",
    install_requires = ["signalfd"],
    version = version,
    author = "Egil Moeller",
    author_email = "egil.moller@piratpartiet.se",
    license = "GPL",
    url = "https://github.com/redhog/pieshell",
    packages = find_packages(),
    entry_points={
        'console_scripts': [
            'pieshell = pieshell.shell:main',
        ],
    },
    scripts = ["contrib/get_completions"]
)
