import argparse
import asyncio
import logging
import math

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

frame_num = 0
async def process_in_opencv(track):
    while True:
        try:
            frame = await track.recv()
            array = frame.to_ndarray(format='rgb24')
            cv2.imshow("Output frame", array)
            print("recieved frame :",frame_num)
            # frame_num = frame_num + 1
            cv2.waitKey(1) 
        except MediaStreamError:
            return


class ClientReciever:
    """
    A media sink that consumes and discards all media.
    """
    def __init__(self):
        self.__tracks = {}

    def addTrack(self, track):
        """
        Add a track whose media should be discarded.

        :param track: A :class:`aiortc.MediaStreamTrack`.
        """
        if track not in self.__tracks:
            self.__tracks[track] = None

    async def start(self):
        """
        Start discarding media.
        """
        
        for track, task in self.__tracks.items():
            if task is None:
                print("type : ",type(track))
                self.__tracks[track] = asyncio.ensure_future(process_in_opencv(track))

    async def stop(self):
        """
        Stop discarding media.
        """
        for task in self.__tracks.values():
            if task is not None:
                task.cancel()
        self.__tracks = {}

async def run(pc, recorder, signaling, role):
    @pc.on("track")
    def on_track(track):
        print("Receiving %s" % track.kind)
        recorder.addTrack(track)

    # connect signaling
    await signaling.connect()

    if role == "offer":
        # send offer
        await pc.setLocalDescription(await pc.createOffer())
        await signaling.send(pc.localDescription)

    # consume signaling
    while True:
        obj = await signaling.receive()
        if isinstance(obj, RTCSessionDescription):
            await pc.setRemoteDescription(obj)
            await recorder.start()

            if obj.type == "offer":
                # send answer
                await pc.setLocalDescription(await pc.createAnswer())
                await signaling.send(pc.localDescription)
        elif isinstance(obj, RTCIceCandidate):
            await pc.addIceCandidate(obj)
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
        loop.run_until_complete(
            run(
                pc=pc,
                recorder=recorder,
                signaling=signaling,
                role="answer",
            )
        )
    except KeyboardInterrupt:
        pass
    finally:
        # cleanup
        loop.run_until_complete(recorder.stop())
        loop.run_until_complete(signaling.close())
        loop.run_until_complete(pc.close())
