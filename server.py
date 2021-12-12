import argparse
import asyncio
import logging
import math
import time
import cv2
import numpy
from av import VideoFrame

from aiortc import (
    RTCIceCandidate,
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
)
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder
from aiortc.contrib.signaling import BYE, add_signaling_arguments, create_signaling, TcpSocketSignaling


class BallVideoStreamTrack(VideoStreamTrack):
    """
    A video track that returns the ball bouncing across screen.
    """
    def __init__(self):
        super().__init__()  
        self.counter = 0
        self.height = 480
        self.width = 640
        
        # Ball params
        speed = 3
        self.dx = speed
        self.dy = speed
        self.cx = int(self.height/2)
        self.cy = int(self.width/2)
        self.radius = 30
        self.colour = (0,255,0)
        
    async def recv(self):
        pts, time_base = await self.next_timestamp()
        
        # Create an empty image
        image = numpy.zeros((self.height,self.width,3)).astype('uint8')
        
        # Update cx and cy
        self.cx += self.dx
        self.cy += self.dy
        if self.cy >=(self.height-self.radius) or (self.cy<=self.radius):
            self.dy *= -1
        if(self.cx>=(self.width-self.radius-1) or self.cx<=(self.radius)):
            self.dx *= -1
        image = cv2.circle(image, (self.cx,self.cy), self.radius, self.colour, -1)
        frame = VideoFrame.from_ndarray(image, format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
        self.counter += 1
        print("self.counter sender:",self.counter,self.cx,self.cy)
        time.sleep(1)
        return frame

    def _create_rectangle(self, width, height, color):
        data_bgr = numpy.zeros((height, width, 3), numpy.uint8)
        data_bgr[:, :] = color
        return data_bgr


async def run(pc, signaling):
    # connect signaling
    await signaling.connect()
    await pc.setLocalDescription(await pc.createOffer())
    await signaling.send(pc.localDescription)
    
    # consume signaling
    while True:
        obj = await signaling.receive()
        print(obj.type)
        if isinstance(obj, RTCSessionDescription):
            await pc.setRemoteDescription(obj)
        elif obj is BYE:
            break


if __name__ == "__main__":
    # create signaling and peer connection
    signaling = TcpSocketSignaling("127.0.0.1",1234)
    pc = RTCPeerConnection()
    pc.addTrack(BallVideoStreamTrack())
    
    # run event loop
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run(pc=pc,signaling=signaling))
    except KeyboardInterrupt:
        pass
    finally:
        # cleanup
        loop.run_until_complete(signaling.close())
        loop.run_until_complete(pc.close())
