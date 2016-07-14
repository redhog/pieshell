import subprocess
import iterio
import pipe
import os

def datasource():
    yield "hello"
    yield "cruel"
    yield "world"
    

inr, inw = pipe.pipe_cloexec()
outr, outw = pipe.pipe_cloexec()
    
inh = iterio.LineOutputHandler(inw, datasource())
outh = iterio.LineInputHandler(outr)
proc = subprocess.Popen(["bash", "-c", "while read foo; do echo hej; echo $foo; done; echo nanana;"], stdin=inr, stdout=outw, stderr=outw)
os.close(inr)
os.close(outw)

for data in outh:
    print "READ", repr(data)
