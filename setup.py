#! /usr/bin/python

from setuptools import setup, find_packages
import os.path

VERSION = "0.2.13"

with open(os.path.join(os.path.dirname(__file__), "README.md"), "r") as rf:
    with open(os.path.join(os.path.dirname(__file__), "pieshell", "README.md"), "w") as wf:
        README = rf.read()
        wf.write(README)
        
with open(os.path.join(os.path.dirname(__file__), "pieshell", "version.py"), "w") as wf:
    wf.write("version = '%s'\n" % (VERSION,)) 
    
setup(
    name = "pieshell",
    description = "Pieshell is a Python shell environment that combines the expressiveness of shell pipelines with the power of python iterators. It can be used both as an interactive shell and as an ordinary python module replacing e.g. subprocess.Popen",
    long_description_content_type = "text/markdown",
    long_description = README,
    keywords = "Python shell pipelines suprocess",
    install_requires = ['python-slugify'],
    extras_require = {
        'linux': ['signalfd'],
        'ps': ['psutil'],
        'completion': ['jedi'],
        'ptpython': ['ptpython']
    },
    version = VERSION,
    author = "Egil Moeller",
    author_email = "egil.moller@piratpartiet.se",
    license = "GPL",
    url = "https://github.com/redhog/pieshell",
    packages = find_packages(),
    package_data={'pieshell': ['*.md', '*.json', '*/*.pysh']},
    entry_points={
        'console_scripts': [
            'pieshell = pieshell.shell:main',
        ],
        'pieshell.builtin': [
            "cd = pieshell.pipeline.builtins:CdBuiltin",
            "bg = pieshell.pipeline.builtins:BgBuiltin",
            "fg = pieshell.pipeline.builtins:FgBuiltin",
            "clear_dir_cache = pieshell.pipeline.builtins:ClearDirCacheBuiltin",
            "bashsource = pieshell.pipeline.builtins:BashSource",
            "subshell = pieshell.pipeline.builtins:SubShell",
            "remote = pieshell.pipeline.builtins:Remote",
        ]
    },
    scripts = ["pieshell/resources/get_completions"]
)
