##### Disclaimer : This represents about a week of work, was not thoroughly tested at all, and may be full of bugs.


## Why? How?

On some "hard" reversing CTF challenges, visualizing clearly what a program is doing is often not a trivial task, especially with self-rewriting binaries using several processes communicating with each other using ptrace and/or pipes. This tool was created while trying to solve such kind of challenge, and it basically has three main purposes : 
- Visualizing what the binary is doing using a graph mode showing relationships between its different processes
- Dumping memory at a chosen state without triggering anti-debug measures (may still trigger time-based anti-debug)
- Starting the debugging of a binary from any syscall in any subprocess, bypassing all checks prior to this syscall

To do this, breakpoints are placed into the kernel of the Qemu machine, which will be triggered before and after any syscall. Here, arguments to the syscall and current PID are gathered and logged, and the program will either continue or give the user the ability to perform manual gdb commands.

Fun fact : Even when all syscalls in the whole Qemu machine are being logged this way, the bash prompt is still perfectly usable, just slower.

Less-fun fact : Some time-sensitive programs may not behave normally when using this tool, as the syscall interception makes everything noticeably slower.

### Current features :
- Trace all syscalls from a Qemu VM, or trace only the children of a given PID (like your current bash console on the machine)
- Resistant to some anti-debugging protections such as ptrace-based ones, as all extraction is done using breakpoints in the kernel
- Build a graph from those syscalls, mapping the different processes spawned in different boxes containing the syscalls they made
- Display heredity between processes with yellow lines
- Display ptrace interactions between processes with green lines
- Display pipe-based communication between processes with red lines
- Breakpoint after any chosen syscall, in order to alter return value or dump current process memory


This tool was only tested on Kali Linux but should work on most Linux distributions.
It is fully working with x86 64-bit ELF binaries, and should mostly work for x86 32-bit ELF binaries.

It should not be too hard to adapt it for some other architectures, I may implement this in a later update.

## Requirements :

- qemu
- gdb
- gef.py (https://github.com/hugsy/gef/blob/dev/gef.py, put it in /opt/gef.py, or you can change this path in the "gef_location" constant of sytrace.py)
- python3
- pyglet for python3 (`pip3 install pyglet`)

If for some reason I missed some dependencies (not unlikely), figure it out yourself and install stuff until it doesn't crash anymore

## Installation :

If you have the willpower to do so, you can build the qemu VM from scratch (any Linux will do), but you'll need to modify the breakpoint offsets in sytrace.py according to the kernel you are using.

Else, if you're lazy, after cloning this repository somewhere on your machine, download my pre-built Debian 10 qcow image and save it in "qemuv1/data/debian.qcow" :
https://drive.google.com/open?id=1wbQCuPg2ESQFsROhgAAQz-4y5wUKPye5

Then, you have two choices : 

To have internet on the qemu machine, follow the instructions in the qemuv1/install_inet.txt

Else, get to the "Usage" phase

## Usage :

### Process visualization

Open a new terminal and go to the qemuv1 directory.

If you followed the last part of the installation and want internet on the qemu machine, type :
```
./start
```
Else :
```
./start_no_inet
```

Now that the Qemu machine is booted, you can transfer files to it by placing them in qemuv1/share on the host machine : It will be synchronized with the /s directory on Qemu machine. For the rest of this demonstration, we will use programs already embedded in any Linux distribution.

In another terminal on your host machine, cd to the root directory of the project, and type : 
```
gdb -x sytrace.py
```

When it asks `Base PID for filtering? (empty for none) :`, if you want to log only the children of a given process (like your bash prompt), enter the PID of this process. The process itself won't be traced, only its children. To try the tool, we will monitor the whole OS : leave the field empty and press enter.

When it asks `Breakpoint ? (procnum:line,procnum2:line2... or empty for none) :`, leave empty for the moment, this will be explained later in the readme.

If you type stuff in the Qemu bash terminal, some output should appear on the gdb window, like this :
![](https://raw.githubusercontent.com/hexabeast/Sytrace/master/readme_images/gef.PNG)

Type a few commands, like "ls", "cat /etc/passwd", just to create some activity. When you're done, in the GDB window, ctrl+c then enter q to exit stop logging. A file named "syscall_log.txt" should be present in the current directory, containing syscalls, as they were displayed in the console with sytrace.py.

To display the graph mode, type :
```python3 graph_syscall.py```
It should create a graph similar to this :
<br><img src="https://raw.githubusercontent.com/hexabeast/Sytrace/master/readme_images/graph.PNG" height="400"><br>
You can zoom with mouse wheel, pan with left click, move the boxes around with left click, etc.

Each box is a process, yellow lines represent process parent/child relationships, green lines represent ptrace calls made by processes targeting other ones, and red lines represent inter-process communication using pipes. 

In our example above, there are only yellow lines as there was no ptrace or pipe-based communication.

Here is some summary of what the graph shows us :
![](https://raw.githubusercontent.com/hexabeast/Sytrace/master/readme_images/how_it_works.png)

We can see the isolated "cron stuff" process that was triggered automatically somewhere in the system as a background task. This is because we did not enable any filtering, so all the syscalls got logged, even those unrelated to what we were doing.


### Using breakpoints

In the current implementation, breakpoints only work if the traced program has a deterministic behaviour syscall-wise : Given the same input twice, the graph should look pretty much the same.
If it is the case, and you need to breakpoint somewhere, first do a run without breakpoint :
```
gdb -x sytrace.py
Base PID for filtering? (empty for none) : [BASH PID HERE]
Breakpoint ? (procnum:line,procnum2:line2... or empty for none) : [LEAVE EMPTY]
```
Launch the program to trace in the Qemu bash prompt, when the trace is over quit sytrace with ctrl+c, q.

Then, do :
```
python3 graph_syscall.py
```

Go to the syscall that you want to break at in the graph, and press the right button of your mouse on it. It should display two numbers in red, separated by a semicolon :
<br><img src="https://raw.githubusercontent.com/hexabeast/Sytrace/master/readme_images/break.png" height="200"><br>

It represents the process number (NOT the pid, 1 is first spawned process from capture start, 2 is second spawned process etc), and the position of the targeted syscall in this process.

Let's imagine you want to break at 3:17, then relaunch the tracer with :
```
gdb -x sytrace.py
Base PID for filtering? (empty for none) : [BASH PID HERE]
Breakpoint ? (procnum:line or empty for none) : 3:17
```
Relaunch the program to trace in the Qemu bash prompt, and the sytrace window should break on the chosen syscalls.

Now, you're in userland and can debug the program directly.
Let's say that now you want to dump the program memory from 0x40000000 to 0x40016000 for further analysis, because some code/strings got decrypted internally inside this range.
You can simply do :
```
dump memory filename.dump 0x40000000 0x40016000
```

filename.dump will contain the dumped memory.




Unfortunately, the only binaries I encountered demonstrating the full capabilities of this tool (ptrace detection, pipe communication etc.) are currently active challenges that I cannot use here as examples, as it would be considered information leakage.


Special thanks to macz for helping in the development/testing process.

For any question/remark related (or not) to the tool, you can contact me on Discord : hexabeast(#)2475
