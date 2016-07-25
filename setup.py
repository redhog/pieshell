#! /usr/bin/python

from setuptools import setup


setup(
    name = "pieshell",
    description = """Pieshell is a Python shell environment that combines the
expressiveness of shell pipelines with the prower of python iterators.

It can be used in two major ways:

* As an interactive shell replacing e.g. bash
* As an ordinary python module replacing e.g. subprocess.Popen
""",
    keywords = "Python shell pipelines suprocess",
    install_requires = [],
    version = "0.0.5",
    author = "Egil Moeller",
    author_email = "egil.moller@piratpartiet.se",
    license = "GPL",
    url = "https://github.com/redhog/pieshell",
    packages = ["pieshell"],
    entry_points={
        'console_scripts': [
            'pieshell = pieshell.shell:main',
        ],
    }
)
