import asyncio
import json
import logging
import time
import tracemalloc
from datetime import datetime

import websockets
from geopy.distance import geodesic
from imutils.video import VideoStream
import os

from models import Database
from path import absolute_path
from train import FaceTrainer
from utils import save_screenshot, host_address

tracemalloc.start()
logging.basicConfig(level=logging.INFO)


class WebSocketManager:
    def __init__(self):
        self.web_clients = set()
        self.apk_clients = set()
        self.locations = {}

    async def register(self, websocket, data):
        if data["state"] == "apk":
            self.apk_clients.add(websocket)
            self.locations[websocket] = (data["latitude"], data["longitude"])
        else:
            self.web_clients.add(websocket)
        logging.info(
            f"Registered a {data['state']} client. Total web: {len(self.web_clients)}, apk: {len(self.apk_clients)}"
        )
        print(str(websocket.path))
        print(data)

    async def unregister(self, websocket):
        if websocket in self.apk_clients:
            self.apk_clients.remove(websocket)
            del self.locations[websocket]
        elif websocket in self.web_clients:
            self.web_clients.remove(websocket)
        logging.info(
            f"Unregistered a client. Remaining web: {len(self.web_clients)}, apk: {len(self.apk_clients)}"
        )

    async def send_to_all(self, message):
        for web_client in self.web_clients:
            if web_client.open:
                await web_client.send(message)

    async def send_to_nearest_client(self, message):
        nearest_client, _ = self.find_nearest_client()
        if nearest_client and nearest_client.open:
            await nearest_client.send(message)

    def find_nearest_client(self):
        camera_location = (41.0649, 71.4782)
        nearest_distance = float("inf")
        nearest_client = None
        for ws, location in self.locations.items():
            if not isinstance(location, tuple) or len(location) != 2:
                logging.error(type(location))
                logging.error(f"Invalid location data: {location}")
                continue

            try:
                lat, long = float(location[0]), float(location[1])
            except ValueError:
                logging.error(f"Invalid coordinates: {location}")
                continue

            location = (lat, long)
            distance = geodesic(camera_location, location).kilometers

            if distance < nearest_distance:
                nearest_distance = distance
                nearest_client = ws

        return nearest_client, nearest_distance


class FaceRecognition:
    def __init__(self, main_stream):
        self.index = main_stream.index
        self.known_face_names = main_stream.known_face_names
        self.face_model = main_stream.face_model

    def process_frame(self, frame):
        faces = self.face_model.get(frame)
        detected_faces = set()
        for face in faces:
            result = self.process_face(face)
            if result:
                detected_faces.add(result)
        return detected_faces

    async def process_face(self, face):
        embedding = face.embedding
        similarity, index = self.index.search(embedding.reshape(1, -1), 1)
        if similarity[0, 0] < 500:
            return self.known_face_names[index[0, 0]]
        return None


class AlertManager:
    def __init__(self, websocket_manager):
        self.websocket_manager = websocket_manager
        self.last_alert_time = {}
        self.face_last_seen = {}
        self.database = Database()

    async def handle_alert(self, detected_face, frame, url):
        now = datetime.now()
        last_alert_time = self.last_alert_time.get(detected_face, datetime.min)
        time_since_last_alert = (now - last_alert_time).total_seconds()

        time_since_last_seen = (
                now - self.face_last_seen.get(detected_face, datetime.min)
        ).total_seconds()

        if time_since_last_seen > 5 and time_since_last_alert > 3:
            await self.send_alert(detected_face, url)
            year, month, day = datetime.now().timetuple()[:3]
            path = (
                f"../media/screenshots/criminals/{detected_face}/{year}/{month}/{day}"
            )
            image_name = save_screenshot(frame, path=path, camera_url=url)
            camera_object = self.database.get_camera(url)
            if camera_object:
                camera_object = camera_object[0]
            self.database.insert_records(
                image=f"{host_address}{image_name[2:]}",
                date_recorded=datetime.now(),
                criminal=int(detected_face),
                camera=camera_object
            )
            self.last_alert_time[detected_face] = now

        self.face_last_seen[detected_face] = now

    async def send_alert(self, detected_face, url):
        details = self.database.get_details(detected_face)
        camera = self.database.get_camera(url)
        camera_details = camera or None
        camera_context = {
            "id": camera_details[0],
            "name": camera_details[1],
            "url": camera_details[2],
            "longitude": camera_details[3],
            "latitude": camera_details[4],
            "image": host_address + "/" + camera_details[-1]
        }
        context = {
            "id": details[0],
            "first_name": details[1],
            "last_name": details[2],
            "middle_name": details[-1],
            "age": details[3],
            "description": details[4],
            "date_joined": str(details[5]),
            "url": url,
            "camera": camera_context,
        }

        print("Context: ", context)
        await self.websocket_manager.send_to_all(
            json.dumps(context)
        )
        await self.websocket_manager.send_to_nearest_client(
            json.dumps(context)
        )


class MainStream:
    def __init__(self, root_dir, camera_urls):
        self.websocket_manager = WebSocketManager()
        self.urls = camera_urls
        self.trainer = FaceTrainer(root_dir)
        self.index = self.trainer.index
        self.known_face_names = self.trainer.known_face_names
        self.face_model = self.trainer.face_model
        self.alert_manager = AlertManager(self.websocket_manager)
        self.face_recognition = FaceRecognition(self)

    async def detect_and_process_faces(self, frame, url):
        faces = self.face_model.get(frame)
        detected_faces = await asyncio.gather(
            *(self.face_recognition.process_face(face) for face in faces)
        )
        detected_faces = set(filter(None, detected_faces))

        for result in detected_faces:
            await self.alert_manager.handle_alert(result, frame, url)

    async def continuous_stream_faces(self, url):
        cap = VideoStream(url).start()
        screenshot_interval = 5  # Interval to take a screenshot in seconds
        last_screenshot_time = time.time()
        try:
            while True:
                frame = cap.read()
                if frame is None:
                    continue

                current_time = time.time()
                if current_time - last_screenshot_time >= screenshot_interval:
                    save_screenshot(frame, path="../media/screenshots/suspends", camera_url=url)
                    last_screenshot_time = current_time

                await self.detect_and_process_faces(frame, url)
        except (KeyboardInterrupt, websockets.exceptions.ConnectionClosedError):
            logging.info(f"Stream {url} terminated.")
        finally:
            cap.stop()

    async def multiple_cameras(self):
        tasks = [self.continuous_stream_faces(url) for url in self.urls]
        await asyncio.gather(*tasks)


async def websocket_server(websocket, path):
    manager = stream.websocket_manager
    try:
        logging.info("Attempt to connect received.")
        message = await websocket.recv()
        data = json.loads(message) or None
        await manager.register(websocket, data)

        while True:
            # Here you can add any additional message handling logic if needed
            await asyncio.sleep(10)

    except websockets.exceptions.ConnectionClosedError as e:
        logging.error(f"Connection closed: {e}")
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error: {e}")
    finally:
        await manager.unregister(websocket)


# Function to list all image paths in a specific directory
def list_image_paths(directory):
    relative_paths = [os.path.join(directory, f) for f in os.listdir(directory) if
                      os.path.isfile(os.path.join(directory, f))]
    absolute_paths = [path.replace('../', host_address + "/", 1) for path in relative_paths]
    return absolute_paths


async def send_image_paths(websocket, path):
    sent_image_paths = set()
    while True:
        current_image_paths = set(list_image_paths("../media/screenshots/suspends/"))
        new_paths = current_image_paths - sent_image_paths  # Determine new files that haven't been sent
        for image_path in new_paths:
            image_name = os.path.basename(image_path)
            camera_url = image_name.split('|')[-1].rstrip('.jpg')
            camera_object = database.get_by_similar(camera_url)
            message = {"image_path": image_path, "camera_object": camera_object}
            await websocket.send(json.dumps(message))
            sent_image_paths.add(image_path)
        await asyncio.sleep(5)


# Modify the image_path_server coroutine to pass the database object to send_image_paths
async def image_path_server(websocket, path):
    consumer_task = asyncio.ensure_future(send_image_paths(websocket, path))
    done, pending = await asyncio.wait([consumer_task], return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()


async def main():
    image_server = await websockets.serve(image_path_server, "0.0.0.0", 5678)
    ws_server = await websockets.serve(websocket_server, "0.0.0.0", 5000)
    camera_streams = [await stream.continuous_stream_faces(url) for url in stream.urls]
    await asyncio.gather(ws_server, image_server, *camera_streams)


if __name__ == "__main__":
    database = Database()
    camera_urls = database.get_camera_urls()
    stream = MainStream(absolute_path + "/criminals/", camera_urls)
    asyncio.run(main())
