import argparse
import asyncio
import logging
import math
import multiprocessing
import cv2
import numpy
from av import VideoFrame
from aiortc.mediastreams import MediaStreamError

from aiortc import (
    RTCIceCandidate,
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
)
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder
from aiortc.contrib.signaling import BYE, add_signaling_arguments, create_signaling, TcpSocketSignaling

def process_a(queue,cx,cy):
    image = queue.get()
    image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask_frame = cv2.inRange(image, (55, 10, 10),(65, 255, 255))
    contours, hierarchy = cv2.findContours(mask_frame, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea)
    M = cv2.moments(contours[-1])
    cv2.drawContours(mask_frame, contours, -1, (125, 125, 125), 2)
    cX, cY = -1, -1
    cX = int(M["m10"] / M["m00"])
    cY = int(M["m01"] / M["m00"])
    cv2.circle(mask_frame, (cX, cY), 7, (0, 0, 0), -1)
    cx.value = cX
    cy.value = cY
    
async def process_in_opencv(track):
    frame_num = 1
    q = multiprocessing.Queue()
    cx = multiprocessing.Value('d', 0.0)
    cy = multiprocessing.Value('d', 0.0)
    p = multiprocessing.Process(target = process_a,args=(q,cx,cy))
    while True:
        try:
            frame = await track.recv()
            image = frame.to_ndarray(format='rgb24')
            print("recieved frame",frame_num)
            cv2.imshow("Output frame", image)
            q.put(image)
            p.run()
            print("cx,cy : ",cx.value,cy.value)
            frame_num = frame_num + 1
            cv2.waitKey(1) 
        except MediaStreamError:
            print("MediaStreamError : ",MediaStreamError)
            return

class ClientReciever:
    """
    A media sink that consumes and discards all media.
    """
    def __init__(self):
        self.__tracks = {}

    def addTrack(self, track):
        if track not in self.__tracks:
            self.__tracks[track] = None

    async def start(self):
        for track, task in self.__tracks.items():
            if task is None:
                self.__tracks[track] = asyncio.ensure_future(process_in_opencv(track))

    async def stop(self):
        for task in self.__tracks.values():
            if task is not None:
                task.cancel()
        self.__tracks = {}

async def run(pc, recorder, signaling):
    @pc.on("track")
    def on_track(track):
        print("Receiving %s" % track.kind)
        recorder.addTrack(track)
    
    # connect signaling
    await signaling.connect()
    
    # consume signaling
    while True:
        obj = await signaling.receive()
        if isinstance(obj, RTCSessionDescription):
            await pc.setRemoteDescription(obj)
            await recorder.start()

            if obj.type == "offer":
                await pc.setLocalDescription(await pc.createAnswer())
                await signaling.send(pc.localDescription)
        elif obj is BYE:
            print("Exiting")
            break

if __name__ == "__main__":
    # create signaling and peer connection
    signaling = TcpSocketSignaling("127.0.0.1",1234)
    pc = RTCPeerConnection()
    
    # Media receiver
    recorder = ClientReciever()
    
    # run event loop
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run(pc=pc,recorder=recorder,signaling=signaling))
    except KeyboardInterrupt:
        pass
    finally:
        # cleanup
        loop.run_until_complete(recorder.stop())
        loop.run_until_complete(signaling.close())
        loop.run_until_complete(pc.close())
