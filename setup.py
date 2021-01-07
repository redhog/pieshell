#! /usr/bin/python

from setuptools import setup, find_packages
import os.path


with open(os.path.join(os.path.dirname(__file__), "README.md"), "r") as rf:
    with open(os.path.join(os.path.dirname(__file__), "pieshell", "README.md"), "w") as wf:
        wf.write(rf.read())

setup(
    name = "pieshell",
    description = """Pieshell is a Python shell environment that combines the
expressiveness of shell pipelines with the power of python iterators.

It can be used in two major ways:

* As an interactive shell replacing e.g. bash
* As an ordinary python module replacing e.g. subprocess.Popen
""",
    keywords = "Python shell pipelines suprocess",
    install_requires = ["signalfd"],
    version = "0.0.6",
    author = "Egil Moeller",
    author_email = "egil.moller@piratpartiet.se",
    license = "GPL",
    url = "https://github.com/redhog/pieshell",
    packages = find_packages(),
    package_data={'pieshell': ['*.md']},
    entry_points={
        'console_scripts': [
            'pieshell = pieshell.shell:main',
        ],
    },
    scripts = ["contrib/get_completions"]
)
