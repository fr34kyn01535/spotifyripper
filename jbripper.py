#!/usr/bin/env python
# -*- coding: utf-8 -*-

from subprocess import call, Popen, PIPE
from spotify import Link, Image
from jukebox import Jukebox, container_loaded
import os, sys
import threading
import time
import datetime

import sys
reload(sys)  
sys.setdefaultencoding('Cp1252')

playback = False # set if you want to listen to the tracks that are currently ripped (start with "padsp ./jbripper.py ..." if using pulse audio)
output_folder = os.getcwd() + "/download/" # change if you want to change output folder
pipe = None
ripping = False
skipping = False
end_of_track = threading.Event()
currentTrack = None
started = None

def track_name(track):
    return u' '.join((track.artists()[0].name().strip()," - " ,track.name().strip(),".mp3")).encode('utf-8').strip() #track.name()+".mp3"
    
def folder_name(track):
    return u' '.join((track.artists()[0].name().strip(), "/" , track.album().name().strip())).encode('utf-8').strip()

def printstr(str): # print without newline
    sys.stdout.write(str)
    sys.stdout.flush()

def shell(cmdline): # execute shell commands (unicode support)
    call(cmdline, shell=True)

def rip_init(session, track):
    global pipe, ripping, skipping, output_folder, currentTrack, started
    currentTrack = track
    started = datetime.datetime.now()
    num_track = "%02d" % (track.index(),)
    mp3file = track_name(track)
    directory = output_folder + folder_name(track) + "/"
    fullpath = u' '.join((directory,mp3file)).encode('utf-8').strip()
    
    if os.path.isfile(fullpath):
        if isMp3Valid(fullpath):
            print("Skipping " + mp3file + " (already exists)")
            skipping = True  
        else:
            print("Repeating " + mp3file + " (file corrupt)")
            skipping = False
    else:
        print("Ripping " + mp3file + "...")
        skipping = False
        
    if not skipping:
        if not os.path.exists(directory):
            os.makedirs(directory)
        p = Popen("lame --silent -V2 -h -r - \""+ fullpath +"\"", stdin=PIPE, shell=True)
        pipe = p.stdin
        ripping = True
        f = open("ripping.status",'w')
        f.write(num_track+"|"+folder_name(track)+"|"+fullpath)
        f.close()
    
	

def rip_terminate(session, track):
    global ripping
    if pipe is not None:
        print('done')
        pipe.close()
    ripping = False
    f = open("ripping.status",'w')
    f.write("")
    f.close()

def rip(session, frames, frame_size, num_frames, sample_type, sample_rate, channels):
    if ripping:#printstr('.')
        max = float(currentTrack.duration()/1000)
        current = float(((datetime.datetime.now() - started).total_seconds())*1.5)
        sys.stdout.write(" "+str(int((100/max)*current))+"%     \r")
        sys.stdout.flush()
        pipe.write(frames)
        
def rip_id3(session, track): # write ID3 data
    global output_folder
    num_track = "%02d" % (track.index(),)
    mp3file = track_name(track)
    artist = track.artists()[0].name().encode('utf-8')
    album = track.album().name().encode('utf-8')
    title = track.name().encode('utf-8')
    year = track.album().year()
    directory =  output_folder + folder_name(track) + "/"

    # download cover
    image = session.image_create(track.album().cover())
    while not image.is_loaded(): # does not work from MainThread!
        time.sleep(0.1)
    fh_cover = open('cover.jpg','wb')
    fh_cover.write(image.data())
    fh_cover.close()

    # write id3 data
    cmd = "eyeD3" + \
          " --add-image cover.jpg:FRONT_COVER" + \
          " -t \"" + title + "\"" + \
          " -a \"" + artist + "\"" + \
          " -A \"" + album + "\"" + \
          " -n " + str(num_track) + \
          " -Y " + str(year) + \
          " \"" + directory + mp3file + "\""
    shell(cmd)
    # delete cover
    shell("rm -f cover.jpg")    

def isMp3Valid(file_path):
    is_valid = False

    f = open(file_path, 'rb')
    block = f.read(1024)
    frame_start = block.find(chr(255))
    block_count = 0 #abort after 64k
    while len(block)>0 and frame_start == -1 and block_count<64:
        block = f.read(1024)
        frame_start = block.find(chr(255))
        block_count+=1
        
    if frame_start > -1:
        frame_hdr = block[frame_start:frame_start+4]
        is_valid = frame_hdr[0] == chr(255)
        
        mpeg_version = ''
        layer_desc = ''
        uses_crc = False
        bitrate = 0
        sample_rate = 0
        padding = False
        frame_length = 0
        
        if is_valid:
            is_valid = ord(frame_hdr[1]) & 0xe0 == 0xe0 #validate the rest of the frame_sync bits exist
            
        if is_valid:
            if ord(frame_hdr[1]) & 0x18 == 0:
                mpeg_version = '2.5'
            elif ord(frame_hdr[1]) & 0x18 == 0x10:
                mpeg_version = '2'
            elif ord(frame_hdr[1]) & 0x18 == 0x18:
                mpeg_version = '1'
            else:
                is_valid = False
            
        if is_valid:
            if ord(frame_hdr[1]) & 6 == 2:
                layer_desc = 'Layer III'
            elif ord(frame_hdr[1]) & 6 == 4:
                layer_desc = 'Layer II'
            elif ord(frame_hdr[1]) & 6 == 6:
                layer_desc = 'Layer I'
            else:
                is_valid = False
        
        if is_valid:
            uses_crc = ord(frame_hdr[1]) & 1 == 0
            
            bitrate_chart = [
                [0,0,0,0,0],
                [32,32,32,32,8],
                [64,48,40,48,16],
                [96,56,48,56,24],
                [128,64,56,64,32],
                [160,80,64,80,40],
                [192,96,80,96,40],
                [224,112,96,112,56],
                [256,128,112,128,64],
                [288,160,128,144,80],
                [320,192,160,160,96],
                [352,224,192,176,112],
                [384,256,224,192,128],
                [416,320,256,224,144],
                [448,384,320,256,160]]
            bitrate_index = ord(frame_hdr[2]) >> 4
            if bitrate_index==15:
                is_valid=False
            else:
                bitrate_col = 0
                if mpeg_version == '1':
                    if layer_desc == 'Layer I':
                        bitrate_col = 0
                    elif layer_desc == 'Layer II':
                        bitrate_col = 1
                    else:
                        bitrate_col = 2
                else:
                    if layer_desc == 'Layer I':
                        bitrate_col = 3
                    else:
                        bitrate_col = 4
                bitrate = bitrate_chart[bitrate_index][bitrate_col]
                is_valid = bitrate > 0
        
        if is_valid:
            sample_rate_chart = [
                [44100, 22050, 11025],
                [48000, 24000, 12000],
                [32000, 16000, 8000]]
            sample_rate_index = (ord(frame_hdr[2]) & 0xc) >> 2
            if sample_rate_index != 3:
                sample_rate_col = 0
                if mpeg_version == '1':
                    sample_rate_col = 0
                elif mpeg_version == '2':
                    sample_rate_col = 1
                else:
                    sample_rate_col = 2
                sample_rate = sample_rate_chart[sample_rate_index][sample_rate_col]
            else:
                is_valid = False
        
        if is_valid:
            padding = ord(frame_hdr[2]) & 2
            
            padding_length = 0
            if layer_desc == 'Layer I':
                if padding:
                    padding_length = 4
                frame_length = (12 * bitrate * 1000 / sample_rate + padding_length) * 4
            else:
                if padding:
                    padding_length = 1
                frame_length = 144 * bitrate * 1000 / sample_rate + padding_length
            is_valid = frame_length > 0
            
            # Verify the next frame
            if(frame_start + frame_length < len(block)):
                is_valid = block[frame_start + frame_length] == chr(255)
            else:
                offset = (frame_start + frame_length) - len(block)
                block = f.read(1024)
                if len(block) > offset:
                    is_valid = block[offset] == chr(255)
                else:
                    is_valid = False
        
    f.close()
    return is_valid

class RipperThread(threading.Thread):
    def __init__(self, ripper):
        threading.Thread.__init__(self)
        self.ripper = ripper

    def run(self):
        global skipping
        # wait for container
        container_loaded.wait()
        container_loaded.clear()

        # create track iterator
        link = Link.from_string(sys.argv[3])
        if link.type() == Link.LINK_TRACK:
            track = link.as_track()
            itrack = iter([track])
        elif link.type() == Link.LINK_PLAYLIST:
            playlist = link.as_playlist()
            print('Loading playlist...'),
            while not playlist.is_loaded():
                time.sleep(0.1)
            print('done')
            itrack = iter(playlist)

        # ripping loop
        session = self.ripper.session
        for track in itrack:
                self.ripper.load_track(track)

                rip_init(session, track)

                if not skipping:
                    self.ripper.play()
                    end_of_track.wait()
                    end_of_track.clear() # TODO check if necessary
                    rip_terminate(session, track)
                    rip_id3(session, track)
                else:
                    rip_terminate(session, track)
                    skipping = False
                #print('\n\n')

        self.ripper.disconnect()

class Ripper(Jukebox):
    def __init__(self, *a, **kw):
        Jukebox.__init__(self, *a, **kw)
        self.ui = RipperThread(self) # replace JukeboxUI
        self.session.set_preferred_bitrate(1) # 160 bps

    def music_delivery_safe(self, session, frames, frame_size, num_frames, sample_type, sample_rate, channels):
        rip(session, frames, frame_size, num_frames, sample_type, sample_rate, channels)
        if playback:
            return Jukebox.music_delivery_safe(self, session, frames, frame_size, num_frames, sample_type, sample_rate, channels)
        else:
            return num_frames

    def end_of_track(self, session):
        Jukebox.end_of_track(self, session)
        end_of_track.set()


if __name__ == '__main__':
	if len(sys.argv) >= 3:
		ripper = Ripper(sys.argv[1],sys.argv[2]) # login
		ripper.connect()
	else:
		print "usage : \n"
		print "	  ./jbripper.py [username] [password] [spotify_url]"
		print "example : \n"
	 	print "   ./jbripper.py user pass spotify:track:52xaypL0Kjzk0ngwv3oBPR - for a single file"
		print "   ./jbripper.py user pass spotify:user:username:playlist:4vkGNcsS8lRXj4q945NIA4 - rips entire playlist"
