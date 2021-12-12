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


class FlagVideoStreamTrack(VideoStreamTrack):
    """
    A video track that returns an animated flag.
    """

    def __init__(self):
        print("initialized server")

        super().__init__()  # don't forget this!
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
        
        # Create image
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


async def run(pc, player, recorder, signaling, role):
    def add_tracks():
        if player and player.audio:
            pc.addTrack(player.audio)

        if player and player.video:
            pc.addTrack(player.video)
        else:
            pc.addTrack(FlagVideoStreamTrack())

    @pc.on("track")
    def on_track(track):
        print("Receiving %s" % track.kind)
        recorder.addTrack(track)

    # connect signaling
    await signaling.connect()

    if role == "offer":
        # send offer
        add_tracks()
        await pc.setLocalDescription(await pc.createOffer())
        await signaling.send(pc.localDescription)

    # consume signaling
    while True:
        print("inside while loop")
        obj = await signaling.receive()

        if isinstance(obj, RTCSessionDescription):
            print("awaiting pc.setRemoteDescription")
            await pc.setRemoteDescription(obj)
            print("awaiting recorder.start")
            await recorder.start()

            if obj.type == "offer":
                # send answer
                add_tracks()
                print("awaiting pc.setLocalDescription")
                await pc.setLocalDescription(await pc.createAnswer())
                print("awaiting signaling.send")
                await signaling.send(pc.localDescription)
        elif isinstance(obj, RTCIceCandidate):
            print("awaiting pc.addIceCandidate(obj)")
            await pc.addIceCandidate(obj)
        elif obj is BYE:
            print("Exiting")
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Video stream from the command line")
    # parser.add_argument("role", choices=["offer", "answer"])
    parser.add_argument("--play-from", help="Read the media from a file and sent it."),
    parser.add_argument("--record-to", help="Write received media to a file."),
    parser.add_argument("--verbose", "-v", action="count")
    # add_signaling_arguments(parser)
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    # create signaling and peer connection
    signaling = TcpSocketSignaling("127.0.0.1",1234)
    # signaling = create_signaling(args)
    pc = RTCPeerConnection()

    # create media source
    if args.play_from:
        player = MediaPlayer(args.play_from)
    else:
        player = None

    # create media sink
    if args.record_to:
        recorder = MediaRecorder(args.record_to)
    else:
        recorder = MediaBlackhole()

    # run event loop
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            run(
                pc=pc,
                player=player,
                recorder=recorder,
                signaling=signaling,
                role="offer",
            )
        )
    except KeyboardInterrupt:
        pass
    finally:
        # cleanup
        loop.run_until_complete(recorder.stop())
        loop.run_until_complete(signaling.close())
        loop.run_until_complete(pc.close())
