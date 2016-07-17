#! /usr/bin/python

from setuptools import setup


setup(
    name = "pyshell",
    description = "Snakes on a shell.",
    keywords = "Python shell pipelines suprocess",
    install_requires = [],
    version = "0.0.1",
    author = "Egil Moeller",
    author_email = "egil.moller@piratpartiet.se",
    license = "GPL",
    url = "https://github.com/redhog/pyshell",
    packages = ["pyshell"],
    entry_points={
        'console_scripts': [
            'pyshell = pyshell.shell:main',
        ],
    }
)
