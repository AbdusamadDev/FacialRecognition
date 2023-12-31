from geopy.distance import distance
from string import ascii_letters
from dotenv import load_dotenv
import numpy as np
import insightface
import psycopg2
import random
import socket
import faiss
import os

load_dotenv()


def characters() -> list:
    letters = [chr(i) for i in list(range(97, 123)) + list(range(65, 91))]
    underscore = ["_"]
    digits = [str(k) for k in list(range(10))]
    return letters + underscore + digits


def host():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        public_ip = "http://" + str(s.getsockname()[0]) + ":8000"
    except Exception:
        public_ip = "Unable to get IP"
    finally:
        s.close()
    return public_ip


def get_face_encoding(img_np):
    model = insightface.app.FaceAnalysis()
    model.prepare(ctx_id=0)
    faces = model.get(img_np)
    if len(faces) == 0:
        print("No face found")
        return None
    return faces


def get_all_encodings_from_db():
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get("DBNAME"),
            user=os.environ.get("DBUSER"),
            password=os.environ.get("DBPASSWORD"),
            host=os.environ.get("DBHOST"),
            port=os.environ.get("DBPORT"),
        )
        cursor = conn.cursor()
        cursor.execute("SELECT criminal_id, encoding FROM api_encodings")
        encoding_data = cursor.fetchall()
        cursor.close()
        conn.close()
        names = [item[0] for item in encoding_data]
        encodings = np.array([np.array(item[1]) for item in encoding_data])
        return names, encodings
    except Exception as e:
        print(f"An error occurred: {e}")
        return None, None


def is_similar(new_encoding, threshold=400):
    existing_names, existing_encodings = get_all_encodings_from_db()
    if existing_encodings.size == 0:
        return None

    new_encoding = new_encoding.reshape(1, -1)
    index = faiss.IndexFlatL2(existing_encodings.shape[1])
    index.add(existing_encodings)
    D, I = index.search(new_encoding, 1)
    if D[0][0] < threshold:
        return existing_names[I[0][0]]

    return None


def find_nearest_location(target_location, locations):
    """
    Find the nearest location in a list of locations to a target location.

    Parameters:
    - target_location: A dictionary with "longitude" and "latitude" keys.
    - locations: A list of dictionaries with "longitude" and "latitude" keys.

    Returns:
    - The nearest location as a dictionary.
    """
    target_point = (target_location["latitude"], target_location["longitude"])

    nearest_location = min(
        locations,
        key=lambda loc: distance(target_point, (loc["latitude"], loc["longitude"])).km,
    )

    return nearest_location


def check_allowed_characters(value, exception):
    lower_cases = [chr(i) for i in range(97, 123)]
    capital_cases = [chr(j) for j in range(65, 91)]
    numbers = [str(k) for k in range(10)]
    others = ["_", "'", '"']
    allowed_chrs = lower_cases + capital_cases + numbers + others
    for letter in value:
        if letter not in allowed_chrs:
            raise exception


def get_unique_key(keys):
    pk = "".join(
        random.choice(ascii_letters + "".join(str(i) for i in range(10)))
        for _ in range(15)
    )
    if pk not in keys:
        return pk
    else:
        return get_unique_key(keys)


allowed_characters = characters()
host_address = host()
process_image = get_face_encoding
is_already_in = is_similar
is_allowed_chr = check_allowed_characters
