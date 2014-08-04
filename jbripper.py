#!/usr/bin/env python
# -*- coding: utf8 -*-

from subprocess import call, Popen, PIPE
from spotify import Link, Image
from jukebox import Jukebox, container_loaded
import os, sys
import threading
import time

playback = False # set if you want to listen to the tracks that are currently ripped (start with "padsp ./jbripper.py ..." if using pulse audio)
output_folder = os.getcwd() + "/download/" # change if you want to change output folder
pipe = None
ripping = False
skipping = False
end_of_track = threading.Event()

def printstr(str): # print without newline
    sys.stdout.write(str)
    sys.stdout.flush()

def shell(cmdline): # execute shell commands (unicode support)
    call(cmdline, shell=True)

def rip_init(session, track):
    global pipe, ripping, skipping, output_folder
    num_track = "%02d" % (track.index(),)
    mp3file = track.name()+".mp3"
    directory = output_folder + track.artists()[0].name() + "/" + track.album().name() + "/"
    if not os.path.isfile(directory+mp3file):
        if not os.path.exists(directory):
            os.makedirs(directory)
        printstr("ripping " + mp3file + " ...")
        p = Popen("lame --silent -V2 -h -r - \""+ directory + mp3file+"\"", stdin=PIPE, shell=True)
        pipe = p.stdin
        ripping = True
        f = open("ripping.status",'w')
        f.write(num_track+"|"+track.artists()[0].name()+"|"+track.album().name()+"|"+directory+mp3file)
        f.close()
    else:
        printstr("skipping " + mp3file + " (already exists)")
        skipping = True
	

def rip_terminate(session, track):
    global ripping
    if pipe is not None:
        print(' done!')
        pipe.close()
    ripping = False
    f = open("ripping.status",'w')
    f.write("")
    f.close()

def rip(session, frames, frame_size, num_frames, sample_type, sample_rate, channels):
    if ripping:
        printstr('.')
        pipe.write(frames);

def rip_id3(session, track): # write ID3 data
    global output_folder
    num_track = "%02d" % (track.index(),)
    mp3file = track.name()+".mp3"
    artist = track.artists()[0].name()
    album = track.album().name()
    title = track.name()
    year = track.album().year()
    directory =  output_folder + track.artists()[0].name() + "/" + track.album().name() + "/"

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
          " -Q " + \
          " \"" + directory + mp3file + "\""
    shell(cmd)

    # delete cover
    shell("rm -f cover.jpg")    

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
            print('loading playlist ...')
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
                print('\n\n')

        self.ripper.disconnect()

class Ripper(Jukebox):
    def __init__(self, *a, **kw):
        Jukebox.__init__(self, *a, **kw)
        self.ui = RipperThread(self) # replace JukeboxUI
        self.session.set_preferred_bitrate(2) # 320 bps

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
