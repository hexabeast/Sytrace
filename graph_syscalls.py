#!/usr/bin/python3
import pyglet
from pyglet.gl import *
import re
import random
import sys
from collections import OrderedDict

filename = 'syscall_log.txt'
if len(sys.argv)>1:
    filename = sys.argv[1]

# Zooming constants
ZOOM_IN_FACTOR = 1.2
ZOOM_OUT_FACTOR = 1/ZOOM_IN_FACTOR

MAX_ZOOM = 500

ORIGINAL_WIDTH = 800
ORIGINAL_HEIGHT = 800

BOX_WIDTH = 3000
BOX_OFFSET = 500

HEADER_SIZE = 60
BASE_OFFSET = 10
FONT_SIZE = 30
FONT_SIZE2 = 50

LEFT = 1
RIGHT = 2
MIDDLE = 4

selected_box = None

main_batch = pyglet.graphics.Batch()
lineY_batch = None
lineG_batch = None
lineR_batch = None

pipes = {}
reads = {}
writes = {}

boxes = {}
processes = OrderedDict()
lines = []

class App(pyglet.window.Window):

    def __init__(self, width, height, *args, **kwargs):
        conf = Config(depth_size=16,
                      double_buffer=True)
        super().__init__(width, height, config=conf, *args, **kwargs)

        #Initialize camera values
        self.left   = 0
        self.right  = width
        self.bottom = 0
        self.top    = height
        self.zoom_level = 1
        self.zoomed_width  = width
        self.zoomed_height = height

    def init_gl(self, width, height):
        # Set clear color
        glClearColor(0/255, 0/255, 0/255, 0/255)

        # Set antialiasing
        #glEnable( GL_LINE_SMOOTH )
        #glEnable( GL_POLYGON_SMOOTH )
        #glHint( GL_LINE_SMOOTH_HINT, GL_NICEST )

        # Set alpha blending
        glEnable( GL_BLEND )
        glBlendFunc( GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA )

        # Set viewport
        glViewport( 0, 0, width, height )

    def on_resize(self, width, height):
        # Set window values
        #self.width  = width
        #self.height = height
        # Initialize OpenGL context
        self.init_gl(width, width)

    def mouse_unproject(self,x,y):
        # Initialize Projection matrix
        glMatrixMode( GL_PROJECTION )
        glLoadIdentity()

        # Initialize Modelview matrix
        glMatrixMode( GL_MODELVIEW )
        glLoadIdentity()
        # Save the default modelview matrix
        glPushMatrix()
        glOrtho( self.left, self.right, self.bottom, self.top, 1, -1 )
        pmat = (pyglet.gl.GLdouble * 16)()
        mvmat = (pyglet.gl.GLdouble * 16)()
        view = (pyglet.gl.GLint * 4)()
        px = (pyglet.gl.GLdouble)()
        py = (pyglet.gl.GLdouble)()
        pz = (pyglet.gl.GLdouble)()
        pyglet.gl.glGetDoublev(pyglet.gl.GL_MODELVIEW_MATRIX, mvmat)
        pyglet.gl.glGetDoublev(pyglet.gl.GL_PROJECTION_MATRIX, pmat)
        pyglet.gl.glGetIntegerv(pyglet.gl.GL_VIEWPORT, view)
        pyglet.gl.gluUnProject(x, y, 0, mvmat, pmat, view, px, py, pz)
        # Remove default modelview matrix
        glPopMatrix()

        return (px.value,py.value)

    def update_linelabel(self,x,y):
        for pid in boxes:
            if boxes[pid].collide(x,y):
                linenumber_label.text = str(boxes[pid].boxnumber)+":"+str(int((boxes[pid].y + boxes[pid].h - HEADER_SIZE-BASE_OFFSET*2 - y)//(FONT_SIZE+BASE_OFFSET)+1))
                linenumber_label.x = x
                linenumber_label.y = y
    
    def on_mouse_press(self,x, y, button, modifiers):
        global selected_box
        x,y = self.mouse_unproject(x,y)
        if button == pyglet.window.mouse.LEFT:
            for pid in boxes:
                if boxes[pid].collide(x,y):
                    if not selected_box:
                        boxes[pid].invisiblabels()
                    selected_box = boxes[pid]
                    return
            selected_box = None
        elif button == pyglet.window.mouse.RIGHT:
            self.update_linelabel(x,y)
    
    
    def on_mouse_release(self,x, y, button, modifiers):
        global selected_box
        if button == pyglet.window.mouse.LEFT:
            if selected_box:
                selected_box.updatelabelpos()
                selected_box = None
        elif button == pyglet.window.mouse.RIGHT:
                linenumber_label.text=""

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        global selected_box

        if buttons & pyglet.window.mouse.LEFT:
            if selected_box:
                selected_box.x += dx*self.zoom_level*ORIGINAL_WIDTH/self.width
                selected_box.y += dy*self.zoom_level*ORIGINAL_WIDTH/self.width
            else:
                self.left   -= dx*self.zoom_level*ORIGINAL_WIDTH/self.width
                self.right  -= dx*self.zoom_level*ORIGINAL_WIDTH/self.width
                self.bottom -= dy*self.zoom_level*ORIGINAL_WIDTH/self.width
                self.top    -= dy*self.zoom_level*ORIGINAL_WIDTH/self.width
        if buttons & pyglet.window.mouse.RIGHT:
            x,y = self.mouse_unproject(x,y)
            self.update_linelabel(x,y)

    def on_mouse_scroll(self, x, y, dx, dy):
        # Get scale factor
        f = ZOOM_OUT_FACTOR if dy > 0 else ZOOM_IN_FACTOR if dy < 0 else 1
        # If zoom_level is in the proper range
        if .2 < self.zoom_level*f < MAX_ZOOM:

            self.zoom_level *= f

            mouse_x = x/self.width
            mouse_y = y/self.width

            mouse_x_in_world = self.left   + mouse_x*self.zoomed_width
            mouse_y_in_world = self.bottom + mouse_y*self.zoomed_height

            self.zoomed_width  *= f
            self.zoomed_height *= f

            self.left   = mouse_x_in_world - mouse_x*self.zoomed_width
            self.right  = mouse_x_in_world + (1 - mouse_x)*self.zoomed_width
            self.bottom = mouse_y_in_world - mouse_y*self.zoomed_height
            self.top    = mouse_y_in_world + (1 - mouse_y)*self.zoomed_height

    def on_draw(self):
        global lineG_batch,lineY_batch,lineR_batch
        # Initialize Projection matrix
        glMatrixMode( GL_PROJECTION )
        glLoadIdentity()

        # Initialize Modelview matrix
        glMatrixMode( GL_MODELVIEW )
        glLoadIdentity()
        # Save the default modelview matrix
        glPushMatrix()

        # Clear window with ClearColor
        glClear( GL_COLOR_BUFFER_BIT )

        # Set orthographic projection matrix
        glOrtho( self.left, self.right, self.bottom, self.top, 1, -1 )

        lineY_batch = pyglet.graphics.Batch()
        lineG_batch = pyglet.graphics.Batch()
        lineR_batch = pyglet.graphics.Batch()
        # Draw
        for pid in boxes:
            boxes[pid].draw()
        draw_fd_lines()

        pyglet.gl.glLineWidth(3)
        glColor3ub( 255,200,0 )
        lineY_batch.draw()

        pyglet.gl.glLineWidth(1)
        glColor3ub( 50,255,0 )
        lineG_batch.draw()

        pyglet.gl.glLineWidth(1)
        glColor3ub( 255,50,0 )
        lineR_batch.draw()

        main_batch.draw()

        # Remove default modelview matrix
        glPopMatrix()

    def run(self):
        pyglet.app.run()

class Sysbox():
    def __init__(self,x,y,pid,ppid,children=[],boxnumber=-1):
        self.x,self.y = x,y
        self.header_size=HEADER_SIZE
        self.w,self.h = BOX_WIDTH,self.header_size
        self.labels = []
        self.pid = pid
        self.ppid = ppid
        self.forklines = []
        self.ptracelines = []
        self.boxnumber = boxnumber
    
    def draw_rectangle(self,x,y,w,h,color):
        glBegin( GL_TRIANGLES  )
        x,y = int(x),int(y)
        glColor3ub( color[0], color[1], color[2] )
        glVertex2i( x, y )
        glVertex2i( x, y+h )
        glVertex2i( x+w, y )
        glVertex2i( x+w, y )
        glVertex2i( x+w, y+h )
        glVertex2i( x, y+h)
        glEnd()

    def draw(self):
        
        for fl in self.forklines:
            if fl[1] in boxes:
                xpos = self.x
                if boxes[fl[1]].x>self.x:
                    xpos = self.x+self.w
                
                lineY_batch.add(2, pyglet.gl.GL_LINES, None,("v2f", (xpos, self.y+self.h-fl[0], boxes[fl[1]].x+boxes[fl[1]].w/2, boxes[fl[1]].y+boxes[fl[1]].h)))

        for fl in self.ptracelines:
            if fl[1] in boxes:
                xpos = self.x
                if boxes[fl[1]].x>self.x:
                    xpos = self.x+self.w

                xpos2 = boxes[fl[1]].x
                if self.x>boxes[fl[1]].x:
                    xpos2 = boxes[fl[1]].x+boxes[fl[1]].w

                lineG_batch.add(2, pyglet.gl.GL_LINES, None, ("v2f", (xpos, self.y+self.h-fl[0], xpos2, boxes[fl[1]].y+boxes[fl[1]].h-fl[2])))

        '''if self.ppid in boxes:
            pyglet.gl.glLineWidth(3)
            pyglet.graphics.draw(2, pyglet.gl.GL_LINES, ("v2f", (self.x+self.w/2, self.y+self.h, boxes[self.ppid].x+boxes[self.ppid].w/2, boxes[self.ppid].y)))'''
        self.draw_rectangle(self.x,self.y,self.w,self.h,(0xFF,0xFF,0xFF))
        """for label in self.labels:
            for l in label:
                l.draw()"""


    def collide(self,x,y):
        return self.x<x<self.x+self.w and self.y<y<self.y+self.h

    def buildlabels(self):
        lines = self.lines
        #self.labels.clear()
        offset = self.header_size+BASE_OFFSET*2
        self.h = self.header_size+BASE_OFFSET*2+(FONT_SIZE+BASE_OFFSET)*len(lines)
        self.headlabel = pyglet.text.Label("PROCNUM : "+str(self.boxnumber)+" - PID "+str(self.pid),font_name='Calibri',batch=main_batch,font_size=self.header_size-2*BASE_OFFSET,x=self.x+self.w/2, y=self.y+self.h-BASE_OFFSET,anchor_x='center', anchor_y='top',color=(0,90,30,255))
        for l in lines:
            sysname = l.split("\t")[0].split(" ")[1]
            col = (0,0,0,255)
            if sysname == "fork" or sysname == "vfork" or sysname == "exec" or sysname == "clone":
                col = (180,180,0,255)
            elif sysname == "ptrace":
                col = (0,220,0,255)
            elif sysname == "write":
                col = (220,0,0,255)
            elif sysname == "read":
                col = (0,0,220,255)
            label = pyglet.text.Label(l,batch=main_batch,width=self.w,font_name='Calibri',font_size=FONT_SIZE,x=self.x+BASE_OFFSET, y=self.y+self.h-offset,anchor_x='left', anchor_y='top',color=col)
            #print(dir(label))
            
            self.labels.append(label)
            offset+=FONT_SIZE+BASE_OFFSET
        #self.label = pyglet.text.Label('\n'.join(lines), width=10000, multiline=True,batch=main_batch,font_name='Calibri',font_size=FONT_SIZE,x=self.x+BASE_OFFSET, y=self.y+self.h-offset,anchor_x='left', anchor_y='top',color=(0,0,0,255))
        n = 0
        for l in lines:
            elems = l.replace("\t"," ").split(" ")
            num,syscall,ret = int(elems[0]), elems[1], elems[-1]
            if syscall == "fork" or syscall == "vfork" or syscall == "exec" or syscall == "clone":
                fork_h =  self.header_size+BASE_OFFSET*2+(FONT_SIZE+BASE_OFFSET)*n + FONT_SIZE/2
                self.forklines.append((fork_h,ret))
            
            if syscall == "ptrace":
                ptrace_h =  self.header_size+BASE_OFFSET*2+(FONT_SIZE+BASE_OFFSET)*n + FONT_SIZE/2
                ptrac_arg = elems[5]
                if not ptrac_arg in boxes:
                    continue
                n2 = 0
                for l in boxes[ptrac_arg].lines:
                    num2 = int(l.split(" ")[0])
                    if num2>num:
                        break
                    n2+=1
                remote_g = self.header_size+BASE_OFFSET*2+(FONT_SIZE+BASE_OFFSET)*n2 + FONT_SIZE/2
                self.ptracelines.append((ptrace_h,ptrac_arg,remote_g))
            n+=1

        



        

    def updatelabelpos(self):
        offset = self.header_size+BASE_OFFSET*2
        self.headlabel.x = self.x+self.w/2
        self.headlabel.y = self.y+self.h-BASE_OFFSET
        for label in self.labels:
            label.x = (self.x+BASE_OFFSET)
            label.y = (self.y+self.h-offset)
            offset+=FONT_SIZE+BASE_OFFSET
    
    def invisiblabels(self):
        self.headlabel.x = -100000
        self.headlabel.y = -100000
        for label in self.labels:
            label.x = -100000
            label.y = -100000
        

linenumber_label = pyglet.text.Label("",font_name='Calibri',batch=main_batch,font_size=FONT_SIZE2,x=-100000, y=-100000,anchor_x='center', anchor_y='bottom',color=(255,0,0,255))

for line in open(filename,'r').read().split("\n"):
    lines.append(line)

#Preprocess log files
c = 0
for line in lines:
    c+=1
    spl = line.split(" ")
    if len(spl)<5:continue
    pid = spl[2]
    ppid = spl[5]
    if not pid in processes:
        processes[pid] = {"ppid":ppid,"syscalls":[]}
        processes[pid]["children"] = []
        if ppid in processes:
            processes[ppid]["children"].append(pid)

    retpattern = '\tret ' 
    if retpattern in line:
        off = line.find(retpattern)+len(retpattern)
        child_proc = int(line[off:].split(' ')[0],16)
        after = " ".join(line[off:].split(' ')[1:])
        if len(after) > 0:
            after = " "+after
        line = line[:off]+str(child_proc)+after

    pidpattern = '\tpid ' 
    if pidpattern in line:
        off = line.find(pidpattern)+len(pidpattern)
        proc = int(line[off:].split('\t')[0],16)
        line = line[:off]+str(proc)+"\t"+"\t".join(line[off:].split('\t')[1:])

    match = re.search("pipe\t\*filedes 0x[0-9a-fA-F]+ -> ([0-9]+ [0-9]+)\t",line)
    if match:
        pipe = list(map(int,match.group(1).split(" ")))
        pipes[pipe[1]] = pipe[0]

    match = re.search("write\tfd (0x[0-9a-fA-F]+)\t",line)
    if match:
        fd = int(match.group(1),16)
        if not fd in writes:
            writes[fd] = []
        writes[fd].append({"num":c,"pid":pid,"offset":len(processes[pid]["syscalls"])})
    
    match = re.search("read\tfd (0x[0-9a-fA-F]+)\t",line)
    if match:
        fd = int(match.group(1),16)
        if not fd in reads:
            reads[fd] = []
        reads[fd].append({"num":c,"pid":pid,"offset":len(processes[pid]["syscalls"])})

    line = re.sub('PID : [0-9]* PPID : [0-9]* ',"",line)

    if len(line)>160:
        line = line[:160]

    line = ("0"*99+str(c))[-len(str(len(lines))):]+" "+line

    processes[pid]["syscalls"].append(line)

#Box creation
boxnumber = 0
for pid in processes:
    boxnumber+=1
    box = Sysbox(0,0,pid,processes[pid]["ppid"],boxnumber=boxnumber)
    box.lines = processes[pid]["syscalls"]
    boxes[pid] = box

for pid in processes:
    boxes[pid].buildlabels()

pids = [pid for pid in processes]

#Recursive function for box default positions
def placeboxes(boxpids,x,y):
    i=2
    for pid in boxpids:
        boxes[pid].x = x + BOX_OFFSET//2 + (BOX_OFFSET+BOX_WIDTH)*(i//2)*(1-2*(i%2))
        boxes[pid].y = y-boxes[pid].h-BOX_OFFSET
        boxes[pid].updatelabelpos()
        pids.remove(pid)
        i+=1
        placeboxes(processes[pid]["children"],boxes[pid].x+boxes[pid].w//2,boxes[pid].y)

#Box placement
xoffset = 0
while len(pids)>0:
    pid = pids.pop(0)
    boxes[pid].x = xoffset
    boxes[pid].updatelabelpos()
    
    placeboxes(processes[pid]["children"],boxes[pid].x+boxes[pid].w//2,boxes[pid].y)
    xoffset += BOX_WIDTH

#Draw red lines for interprocess pipe communication
def draw_fd_lines():
    for fl in fdlines:
        xpos1 = boxes[fl[0]].x
        if boxes[fl[1]].x>boxes[fl[0]].x:
            xpos1 = boxes[fl[0]].x+boxes[fl[0]].w

        xpos2 = boxes[fl[1]].x
        if boxes[fl[0]].x>boxes[fl[1]].x:
            xpos2 = boxes[fl[1]].x+boxes[fl[1]].w
        
        lineR_batch.add(2, pyglet.gl.GL_LINES, None,("v2f", (xpos1, boxes[fl[0]].y+boxes[fl[0]].h-fl[2], xpos2, boxes[fl[1]].y+boxes[fl[1]].h-fl[3])))

#Setup lines for interprocess pipe communication
fdlines = []
for fd in writes:
    for write in writes[fd]:
        if fd in pipes:
            if pipes[fd] in reads:
                best = None
                mindist = 20
                for read in reads[pipes[fd]]:
                    dist = read["num"]-write["num"]
                    if dist<0:
                        continue
                    if dist<mindist:
                        best = read
                        mindist = dist
                if best:
                    fd_h1 =  HEADER_SIZE+BASE_OFFSET*2+(FONT_SIZE+BASE_OFFSET)*write['offset'] + FONT_SIZE/2
                    fd_h2 =  HEADER_SIZE+BASE_OFFSET*2+(FONT_SIZE+BASE_OFFSET)*best['offset'] + FONT_SIZE/2
                    fdlines.append(((write['pid'],best['pid'],fd_h1,fd_h2)))


App(ORIGINAL_WIDTH, ORIGINAL_HEIGHT, resizable=True).run()