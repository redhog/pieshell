import subprocess
import iterio
import os

def datasource():
    yield "hello"
    yield "cruel"
    yield "world"
    
    
inh = iterio.LineInputHandler(datasource())
outh = iterio.LineOutputHandler()
proc = subprocess.Popen(["bash", "-c", "while read foo; do echo hej; echo $foo; done; echo nanana;"], stdin=inh.pipe_fd, stdout=outh.pipe_fd, stderr=outh.pipe_fd)
os.close(inh.pipe_fd)
os.close(outh.pipe_fd)

for data in outh:
    print "READ", repr(data)
