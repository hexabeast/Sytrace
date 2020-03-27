from termcolor import colored
import string
import binascii
import re

################################################################## PARAMETERS #####################################################################
rw_strings = True

gef_location = "/opt/gef.py"

log_file_name = "syscall_log.txt"
logging = True

string_color = 'red'
read_color = 'cyan'
pid_color = 'white'
ppid_color = 'cyan'
ret_color = 'white'
argcolors = ["yellow","green","blue","magenta"]
string_escape_alphabet = r''' #$%&'()*+,-./0!"123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~'''

"""
do_syscall_64:
call    __fentry__
push    rbp
mov     rbp, rsi
push    rbx
call    off_FFFFFFFF82026418
mov     rax, gs:pid
mov     rax, [rax] <-------- break_before
"""
break_before = "*0xFFFFFFFF8100414A"

"""
mov     rax, ds:sys_call_table[rax*8]
mov     rdi, rbp
call    __indirect_thunk_start
mov     [rbp+80], rax
mov     rax, gs:pid
mov     rsi, [rax] <-------- break_after
"""
break_after = "*0xFFFFFFFF81004190"

break_before32 = "*0xFFFFFFFF8100425A"
break_after32 = "*0xFFFFFFFF810042A3"

break_before32_fast = "*0xFFFFFFFF81004340"
break_after32_fast = "*0xFFFFFFFF810043D5"

################################################################## INIT VARIABLES #####################################################################

goodpids = set()
syscalls = {}
syscalls32 = {}
pid,states = 0,{}
log_file = None
ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
procnumbers = {}
current_procnumber = 0
proc_syscall_amount = {}
memdump = {}

##################################################################### FUNCTIONS #####################################################################

def ask_filtering():
    gdb.execute('printf "Base PID for filtering? (empty for none) : "')
    basepid = input()
    if basepid != "":
        try:
            basepid = int(basepid)
            goodpids.add(basepid)
            return True
        except:
            print("Bad number !")
            exit()
    return False
pid_filtering = ask_filtering()

def ask_memdump():
    gdb.execute('printf "Breakpoint ? (procnum:line,procnum2:line2... or empty for none) : "')
    inpt = input()
    if inpt != "":
        try:
            for e in inpt.split(","):
                v1,v2 = e.split(":")
                if not int(v1) in memdump:
                    memdump[int(v1)] = []
                memdump[int(v1)].append(int(v2))
        except:
            print("Bad number !")
            exit()
ask_memdump()

def load_syscalls(arch):
    global syscalls, syscalls32
    rsyscalls = None
    if arch == "64":
        rsyscalls = open("syscalls.txt","r").read().split("\n")
    elif arch == "32":
        rsyscalls = open("syscalls32.txt","r").read().split("\n")
    for s in rsyscalls:
        s = s.split("|")
        rargs = s[2:]
        args = {}
        i=0
        for a in rargs:
            if a=="":
                continue
            t = a.split(" ")
            typ,val = "".join(t[:-1]),t[-1]
            args[i] = {"type":typ,"value":val}

            i+=1
        fullsyscall = {"name":s[1].replace("sys_",""),"args":args}
        if arch == "64":
            syscalls[int(s[0])] = fullsyscall
        elif arch == "32":
            syscalls32[int(s[0])] = fullsyscall


def escape_gdb_dump(st):
    sts = st.split("\n")
    arr = []
    for s in sts:
        if len(s)<2:
            continue
        cs = s.split(":")[1].split("\t")
        cs.remove("")
        arr.extend(map(lambda x:int(x,16),cs))
    arr = bytes(arr)
    nst = ""
    arr = arr.replace(b"\n",b"\\n").replace(b"\r",b"\\r").replace(b"\t",b"\\t")
    for l in [arr[i:i+1] for i in range(len(arr))]:
        if l in string_escape_alphabet.encode("utf8"):
            nst+=l.decode("utf8")
        else:
            nst+="\\x"+binascii.hexlify(l).decode("utf8")
    return nst

def nullstop(st):
    return st[:st.find("\\x00")]

class State():
    def __init__(self):
        self.rax = -1
        self.rdi = -1
        self.rsi = -1
        self.rdx = -1
        self.r10 = -1
        self.ppid = -1
        self.out = ""

    def regs(self):
        return (self.rax,self.rdi,self.rsi,self.rdx,self.r10)

    def setregs(self,l):
        self.rax,self.rdi,self.rsi,self.rdx,self.r10 = l

##################################################################### BREAKPOINTS #####################################################################

#This is reached near do_syscall_64 after gs:pid is loaded in rax. Gets pid, does pid filtering if enabled, then loads arguments and saves them in states[pid]
class syspoint(gdb.Breakpoint):
    typ = "64"
    def stop(self):
        global pid_filtering,current_procnumber

        pidreg = "rax"
        argreg = "rbp"
        if self.typ == "32":
            pidreg = "rdx"
        elif self.typ == "32_fast":
            pidreg = "r12"
            argreg = "rdi"
        pid = int(gdb.execute(r'printf "%d" , *(unsigned long long*)(*(unsigned long long*)($'+pidreg+r'+0x530)+0x38)', False, True))
        ppid = int(gdb.execute(r'printf "%d" , *(unsigned long long*)(*(unsigned long long*)(*(unsigned long long*)($'+pidreg+r'+0x4d8)+0x530)+0x38)', False, True))
        
        if not pid_filtering or ppid in goodpids:
            if not pid in goodpids:
                current_procnumber+=1
                procnumbers[pid] = current_procnumber
                goodpids.add(pid)
                proc_syscall_amount[pid] = 0
            states[pid] = State()
            states[pid].ppid = ppid
        else:
            return False

        proc_syscall_amount[pid]+=1
        
        regs = list(map(int,gdb.execute(r'printf "%llu:%llu:%llu:%llu:%llu" , *(unsigned long long *)($'+argreg+r'+0x78),*(unsigned long long *)($'+argreg+r'+0x70),*(unsigned long long *)($'+argreg+r'+0x68),*(unsigned long long *)($'+argreg+r'+0x60),*(unsigned long long *)($'+argreg+r'+0x58)', False, True).replace("ll","").split(":")))

        states[pid].setregs(regs)
        return False

#This is reached after the return from the actual syscall. Gets return value, sometimes prints some arg contents, and prints/logs the syscall
class retpoint(gdb.Breakpoint):
    typ = "64"
    def stop(self):

        retreg = "rbp"
        sys = syscalls
        if self.typ == "32":
            sys = syscalls32
        elif self.typ == "32_fast":
            retreg = "rbx"
            sys = syscalls32


        pid = int(gdb.execute(r'printf "%d" , *(unsigned long long*)(*(unsigned long long*)($rax+0x530)+0x38)', False, True))
        if not pid in states:
            return False

        rax,rdi,rsi,rdx,r10 = states[pid].regs()
        ret = int(gdb.execute(r'printf "%llu" , *(unsigned long long*)($'+retreg+r'+0x50)', False, True))
        ret = (ret & ((1 << 63) - 1)) - (ret & (1 << 63))

        out = colored("PID : "+str(pid),pid_color)+" "+colored("PPID : "+str(states[pid].ppid),ppid_color)+" "+colored(syscalls[rax]["name"], string_color)
        for i in range(len(syscalls[rax]["args"])):
            if i>3:
                break
            val = hex(states[pid].regs()[i+1])

            if rw_strings:
                try:
                    if "write" == syscalls[rax]["name"] and i == 1:
                        val=val+' -> '+colored('"'+escape_gdb_dump(gdb.execute(r'x/'+str(rdx)+'bx '+val, False, True))+'"',string_color, attrs=['bold'])
                    elif re.match("\*.*name.*", syscalls[rax]["args"][i]["value"]):
                        val=val+' -> '+colored('"'+nullstop(escape_gdb_dump(gdb.execute(r'x/64bx '+val, False, True)))+'"',string_color, attrs=['bold'])
                    elif "pipe" == syscalls[rax]["name"] and i == 0:
                        val=val+' -> '+colored(gdb.execute(r'x/2wu '+val, False, True).split(":")[1].replace("\t"," ").replace("\n","")[1:],string_color, attrs=['bold'])
                except:
                    val=val+' -> '+colored('"reading error"',"magenta")

            out+="\t"+colored(syscalls[rax]["args"][i]["value"]+" "+val,argcolors[i])
        out+="\t"+colored("ret "+hex(ret),ret_color)
        if rw_strings:
            try:
                
                if "read" == sys[rax]["name"]:
                    if ret<0:
                        out+=colored(" READ FAILED",ret_color)
                    else:
                        out+=colored(" -> ",ret_color)+colored('"'+escape_gdb_dump(gdb.execute(r'x/'+str(rdx)+'bx '+hex(rsi), False, True))+'"',read_color, attrs=['bold'])
            except:
                out+=colored(" -> ",ret_color)+colored('"reading error"',"magenta")
        print(out)
        if logging:
            log_file.write(ansi_escape.sub('', out+"\n"))
            log_file.flush()

        del states[pid]

        if procnumbers[pid] in memdump:
            if proc_syscall_amount[pid] in memdump[procnumbers[pid]] :
                #dump memory kdump2 0x40000000 0x40041D50
                #gdb.execute("gef config context.enable 1")
                #print("ZERO ZERO ZERO")
                #gdb.execute("patch qword $rbp+0x50 -1")
                return True

        return False

##################################################################### COMMANDS #####################################################################

load_syscalls("64")
load_syscalls("32")

if logging:
    log_file = open(log_file_name,"w")

gdb.execute("source "+gef_location)
gdb.execute("gef config context.enable 0")
gdb.execute("set arch i386:x86-64")
gdb.execute("gef-remote -q :1234")

syspoint(break_before).typ="64"
retpoint(break_after).typ="64"

syspoint(break_before32).typ="32"
retpoint(break_after32).typ="32"

syspoint(break_before32_fast).typ="32_fast"
retpoint(break_after32_fast).typ="32_fast"

gdb.execute("c")

######################################################################### END #########################################################################